import argparse
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import requests
import xarray as xr
import yaml
import zarr
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from pystac_client.exceptions import APIError
from shapely.geometry import shape

# Load environment variables from .env file
load_dotenv(Path(__file__).parent.parent.parent / '.env')

from utils import (
    build_cubedataset_from_items,
    get_location_data,
    get_processed_locations,
    process_bounding_box,
    save_cube_with_retries,
    search_stac_items,
)


def load_config(config_path: str = None) -> Dict:
    if config_path is None:
        config_path = Path(__file__).parent / "pipeline_config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


DEFAULT_OUTPUT_SUBDIRS = {
    "s2": "S2L2A",
    "s2_cloudmask": "S2L2A_CLOUDMASK",
    "s1": "S1RTC",
    "copdem": "COPDEM",
    "esalc": "ESALC",
    "merged": "MERGED",
}


def resolve_output_dirs(cfg: Dict) -> Dict:
    base_output_dir = cfg.get("output_base_dir")
    explicit_output_dirs = cfg.get("output_dirs", {}) or {}

    if base_output_dir:
        output_subdirs = DEFAULT_OUTPUT_SUBDIRS.copy()
        output_subdirs.update(cfg.get("output_subdirs", {}) or {})

        derived_output_dirs = {
            key: os.path.join(base_output_dir, output_subdirs[key])
            for key in DEFAULT_OUTPUT_SUBDIRS
        }

        # Allow per-stage override if needed
        derived_output_dirs.update(explicit_output_dirs)
        cfg["output_dirs"] = derived_output_dirs
    else:
        cfg["output_dirs"] = explicit_output_dirs

    missing = [key for key in DEFAULT_OUTPUT_SUBDIRS if key not in cfg["output_dirs"]]
    if missing:
        raise ValueError(
            "Missing output directories for keys: "
            + ", ".join(missing)
            + ". Define output_base_dir (preferred) or full output_dirs."
        )

    return cfg


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def should_skip(location: str, processed: set, skip_existing: bool) -> bool:
    return skip_existing and location in processed


def build_date_range(event_date: str, inc_months: int, dec_months: int) -> Tuple[str, str]:
    event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
    start_date = (event_dt - relativedelta(months=inc_months)).strftime("%Y-%m-%d")
    end_date = (event_dt + relativedelta(months=dec_months)).strftime("%Y-%m-%d")
    return start_date, end_date


def maybe_filter_s2_items(items, bbox_latlon, enable: bool):
    if not enable or items is None:
        return items
    aoi_polygon = shape(bbox_latlon)
    return [item for item in items if shape(item.to_dict()["geometry"]).contains(aoi_polygon)]


def create_cube_for_location(
    location: str,
    lon: float,
    lat: float,
    start_date: str,
    end_date: str,
    collections: List[str],
    source: str,
    output_dir: str,
    edge_size: int,
    units: str,
    resolution: int,
    skip_existing: bool,
    processed_locations: set,
    s2_filter_contains_bbox: bool = False,
) -> bool:
    if should_skip(location, processed_locations, skip_existing):
        print(f"[SKIP] {location} already processed for {collections}")
        return False

    try:
        bbox_utm, bbox_latlon, epsg = process_bounding_box(
            edge_size, units, resolution, lat, lon, location
        )
    except ValueError as e:
        print(f"Skipping {location}: {e}")
        return False

    try:
        items = search_stac_items(
            source=source,
            bbox_latlon=bbox_latlon,
            start_date=start_date,
            end_date=end_date,
            collections=collections,
            location=location,
        )
    except APIError as e:
        print(f"[STAC-ERROR] {location}: {e} - skipping")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[HTTP-ERROR] {location}: {e} - skipping")
        return False
    except Exception as e:
        print(f"[UNEXPECTED] {location}: {e} - skipping")
        return False

    if not items:
        print(f"No items for {location} ({collections})")
        return False

    if "sentinel-2-l2a" in collections:
        items = maybe_filter_s2_items(items, bbox_latlon, s2_filter_contains_bbox)
        if not items:
            print(f"No items for {location} after S2 spatial filter")
            return False

    stac_url = "https://stac.dataspace.copernicus.eu/v1/" if source == "cdse" else "https://planetarycomputer.microsoft.com/api/stac/v1"

    try:
        cubedataset = build_cubedataset_from_items(
            items=items,
            data_collections=collections,
            bbox_utm=bbox_utm,
            epsg=epsg,
            resolution=resolution,
            stac_url=stac_url,
            start_date=start_date,
            end_date=end_date,
            location=location,
        )
    except Exception as e:
        print(f"[BUILD-ERROR] {location}: {e} - skipping")
        return False

    try:
        return save_cube_with_retries(cubedataset, location, start_date, end_date, base_output_dir=output_dir)
    except Exception as e:
        print(f"[SAVE-ERROR] {location}: {e} - skipping")
        return False


def run_cloud_mask(s2_dir: str, cloudmask_dir: str, skip_existing: bool) -> None:
    from cloud_mask import get_processed_locations_cloudmask, process_datacube

    ensure_dir(cloudmask_dir)
    processed = get_processed_locations_cloudmask(cloudmask_dir) if skip_existing else set()

    for fname in sorted(os.listdir(s2_dir)):
        if not fname.endswith(".zarr"):
            continue
        if "_cloudmask" in fname:
            continue
        zarr_path = os.path.join(s2_dir, fname)
        location_id = extract_location_id(fname)
        if skip_existing and location_id in processed:
            print(f"[SKIP] cloud mask already done for {location_id}")
            continue
        output_file = os.path.join(cloudmask_dir, f"{os.path.splitext(fname)[0]}_cloudmask.zarr")
        process_datacube(zarr_path, output_file)


def extract_location_id(zarr_name: str) -> str:
    match = re.match(r"^DC__(.+?)__", zarr_name)
    if not match:
        raise ValueError(f"Cannot parse location_id from {zarr_name}")
    return match.group(1)


def list_zarr_files(dir_path: str) -> List[str]:
    return sorted(
        [os.path.join(dir_path, f) for f in os.listdir(dir_path) if f.startswith("DC__") and f.endswith(".zarr")]
    )


def parse_prefix_and_date(path: str) -> Tuple[str, str]:
    fname = os.path.basename(path)
    pattern = r"^(DC__.+?)__([0-9]{4}-[0-9]{2}-[0-9]{2}__[0-9]{4}-[0-9]{2}-[0-9]{2})"
    m = re.match(pattern, fname)
    if not m:
        raise ValueError(f"Cannot parse: {fname}")
    return m.group(1), m.group(2)


def merge_cubes(config: Dict, input_dirs: Dict[str, str], output_dir: str, skip_existing: bool, force_locations: set = None) -> None:
    ensure_dir(output_dir)

    files_by_prefix = {}
    for key, d in input_dirs.items():
        files_by_prefix.setdefault(key, list_zarr_files(d))

    groups: Dict[str, Dict[str, List[Tuple[str, str]]]] = {}
    for source_name, paths in files_by_prefix.items():
        for path in paths:
            prefix, date_range = parse_prefix_and_date(path)
            if prefix not in groups:
                groups[prefix] = {"S2L2A": [], "S1RTC": [], "COPDEM": [], "ESALC": []}
            groups[prefix][source_name].append((path, date_range))

    merge_groups = {}
    final_prefix_name = {}
    merge_meta = {}

    for prefix, items in groups.items():
        expected_sources = ["S2L2A", "S1RTC", "COPDEM", "ESALC"]
        source_maps = {
            source_name: {d: p for p, d in items.get(source_name, [])}
            for source_name in expected_sources
        }

        s2_dates = set(source_maps["S2L2A"].keys())
        s1_dates = set(source_maps["S1RTC"].keys())
        common_dynamic_dates = sorted(s2_dates & s1_dates)

        if common_dynamic_dates:
            # Preferred path: use a matching S2/S1 dynamic range.
            date_range = common_dynamic_dates[-1]
        else:
            # Fallback for incomplete data: use latest available dynamic range.
            dynamic_candidates = sorted(s2_dates | s1_dates)
            if not dynamic_candidates:
                print(f"[MERGE] No S2/S1 dynamic cubes available for {prefix}; skipping")
                continue
            date_range = dynamic_candidates[-1]

        final_files = []
        available_sources = []

        for dynamic_source in ["S2L2A", "S1RTC"]:
            src_map = source_maps[dynamic_source]
            if date_range in src_map:
                final_files.append(src_map[date_range])
                available_sources.append(dynamic_source)
            elif src_map:
                # Use most recent dynamic cube when exact date_range is unavailable.
                fallback_date = sorted(src_map.keys())[-1]
                final_files.append(src_map[fallback_date])
                available_sources.append(dynamic_source)

        for aux_name in ["COPDEM", "ESALC"]:
            aux_items = items.get(aux_name, [])
            if not aux_items:
                continue
            aux_items_sorted = sorted(aux_items, key=lambda x: x[1])
            if config["merge"]["prefer_latest_aux"]:
                final_files.append(aux_items_sorted[-1][0])
            else:
                final_files.append(aux_items_sorted[0][0])
            available_sources.append(aux_name)

        missing_sources = [s for s in expected_sources if s not in available_sources]
        if missing_sources:
            print(f"[MERGE] Incomplete inputs for {prefix}; missing: {', '.join(missing_sources)}")

        final_prefix = f"{prefix}__{date_range}"
        merge_groups[prefix] = final_files
        final_prefix_name[prefix] = final_prefix
        merge_meta[prefix] = {
            "available_sources": available_sources,
            "missing_sources": missing_sources,
        }

    for prefix, paths in merge_groups.items():
        final_prefix = final_prefix_name[prefix]
        output_path = os.path.join(output_dir, f"{final_prefix}.zarr")
        is_forced = force_locations and prefix in force_locations
        if skip_existing and os.path.exists(output_path) and not is_forced:
            print(f"[SKIP] merged exists: {output_path}")
            continue

        print(f"[MERGE] {final_prefix} - cubes: {len(paths)}")
        cubes = [xr.open_zarr(p, consolidated=True) for p in paths]
        merged = xr.merge(cubes, compat="override", join="outer")

        for var in config["merge"]["vars_to_uint16"]:
            if var in merged:
                merged[var] = merged[var].astype("uint16")

        chunk_dict = {}
        for d in merged.dims:
            if d.lower().startswith("time"):
                chunk_dict[d] = config["merge"]["chunk_time"]
            elif d in ["x", "longitude"]:
                chunk_dict[d] = config["merge"]["chunk_x"]
            elif d in ["y", "latitude"]:
                chunk_dict[d] = config["merge"]["chunk_y"]

        merged = merged.chunk(chunk_dict)
        merged.attrs.update(config["merge"]["attrs"])

        # Keep only a single compact availability marker in metadata.
        cube_meta = merge_meta.get(prefix, {"available_sources": [], "missing_sources": []})
        missing_sources = cube_meta["missing_sources"]
        merged.attrs["missing_datasets"] = ", ".join(missing_sources) if missing_sources else "none"

        encoding = {}
        compressor = zarr.Blosc(cname="zstd", clevel=3, shuffle=1)

        def flatten_chunks(chunks):
            if chunks is None:
                return None
            return tuple(int(c) for dim in chunks for c in dim)

        # Set optimal _FillValue for all variables
        UNIVERSAL_NODATA = 32767
        
        for var in merged.data_vars:
            dtype = merged[var].dtype
            
            # Determine appropriate fill value based on dtype
            if np.issubdtype(dtype, np.floating):
                fill_value = np.nan
            else:
                fill_value = UNIVERSAL_NODATA
            
            encoding[var] = {
                "compressor": compressor, 
                "chunks": flatten_chunks(merged[var].chunks),
                "_FillValue": fill_value
            }

        for coord in merged.coords:
            if coord not in encoding:
                coord_encoding = {
                    "compressor": None,
                    "chunks": flatten_chunks(merged[coord].chunks),
                }

                # Keep S1 acquisition time precision in whole seconds for easier delta analysis.
                if coord == "time_sentinel_1_rtc" and np.issubdtype(merged[coord].dtype, np.datetime64):
                    coord_encoding.update(
                        {
                            "dtype": "int64",
                            "units": "seconds since 1970-01-01 00:00:00",
                            "calendar": "proleptic_gregorian",
                        }
                    )

                encoding[coord] = coord_encoding

        merged.to_zarr(output_path, mode="w", encoding=encoding, consolidated=True)
        print(f"[MERGE] Saved: {output_path}")


def main(config_path: str = None) -> None:
    cfg = load_config(config_path)
    cfg = resolve_output_dirs(cfg)

    for key in DEFAULT_OUTPUT_SUBDIRS:
        ensure_dir(cfg["output_dirs"][key])

    table = pd.read_csv(cfg["locations_csv"])
    nrow = table.shape[0]

    processed = {
        "s2": get_processed_locations(cfg["output_dirs"]["s2"]) if cfg["skip_existing"] else set(),
        "s1": get_processed_locations(cfg["output_dirs"]["s1"]) if cfg["skip_existing"] else set(),
        "copdem": get_processed_locations(cfg["output_dirs"]["copdem"]) if cfg["skip_existing"] else set(),
        "esalc": get_processed_locations(cfg["output_dirs"]["esalc"]) if cfg["skip_existing"] else set(),
    }

    for i in range(nrow):
        location, lon, lat, event_date = get_location_data(table, i)
        print(f"[START] {location} lon={lon} lat={lat} date={event_date}")

        start_date, end_date = build_date_range(
            event_date,
            cfg["temporal"]["increment_months"],
            cfg["temporal"]["decrement_months"],
        )

        create_cube_for_location(
            location=location,
            lon=lon,
            lat=lat,
            start_date=start_date,
            end_date=end_date,
            collections=cfg["collections"]["s2"],
            source=cfg["sources"]["s2"],
            output_dir=cfg["output_dirs"]["s2"],
            edge_size=cfg["spatial"]["edge_size"],
            units=cfg["spatial"]["units"],
            resolution=cfg["spatial"]["resolution"],
            skip_existing=cfg["skip_existing"],
            processed_locations=processed["s2"],
            s2_filter_contains_bbox=cfg["s2_filter_contains_bbox"],
        )

        create_cube_for_location(
            location=location,
            lon=lon,
            lat=lat,
            start_date=start_date,
            end_date=end_date,
            collections=cfg["collections"]["s1"],
            source=cfg["sources"]["s1"],
            output_dir=cfg["output_dirs"]["s1"],
            edge_size=cfg["spatial"]["edge_size"],
            units=cfg["spatial"]["units"],
            resolution=cfg["spatial"]["resolution"],
            skip_existing=cfg["skip_existing"],
            processed_locations=processed["s1"],
        )

        copdem_range = cfg["static_dates"]["copdem"]
        create_cube_for_location(
            location=location,
            lon=lon,
            lat=lat,
            start_date=copdem_range["start"],
            end_date=copdem_range["end"],
            collections=cfg["collections"]["copdem"],
            source=cfg["sources"]["copdem"],
            output_dir=cfg["output_dirs"]["copdem"],
            edge_size=cfg["spatial"]["edge_size"],
            units=cfg["spatial"]["units"],
            resolution=cfg["spatial"]["resolution"],
            skip_existing=cfg["skip_existing"],
            processed_locations=processed["copdem"],
        )

        esalc_range = cfg["static_dates"]["esalc"]
        create_cube_for_location(
            location=location,
            lon=lon,
            lat=lat,
            start_date=esalc_range["start"],
            end_date=esalc_range["end"],
            collections=cfg["collections"]["esalc"],
            source=cfg["sources"]["esalc"],
            output_dir=cfg["output_dirs"]["esalc"],
            edge_size=cfg["spatial"]["edge_size"],
            units=cfg["spatial"]["units"],
            resolution=cfg["spatial"]["resolution"],
            skip_existing=cfg["skip_existing"],
            processed_locations=processed["esalc"],
        )

    if cfg["cloud_mask"]["enabled"]:
        run_cloud_mask(cfg["output_dirs"]["s2"], cfg["output_dirs"]["s2_cloudmask"], cfg["skip_existing"])

    if cfg["merge"]["enabled"]:
        input_dirs = {
            "S2L2A": cfg["output_dirs"]["s2_cloudmask"] if cfg["cloud_mask"]["enabled"] else cfg["output_dirs"]["s2"],
            "S1RTC": cfg["output_dirs"]["s1"],
            "COPDEM": cfg["output_dirs"]["copdem"],
            "ESALC": cfg["output_dirs"]["esalc"],
        }
        force_locations = set(cfg["merge"].get("force_locations") or [])
        merge_cubes(cfg, input_dirs, cfg["output_dirs"]["merged"], cfg["skip_existing"], force_locations)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARCEME Data Cube Pipeline")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML (default: pipeline_config.yaml)")
    args = parser.parse_args()
    
    main(config_path=args.config)
