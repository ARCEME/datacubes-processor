import argparse
import importlib.util
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd
import requests
import xarray as xr
import zarr
from dateutil.relativedelta import relativedelta
from pystac_client.exceptions import APIError
from shapely.geometry import shape

from utils import (
    build_cubedataset_from_items,
    get_location_data,
    get_processed_locations,
    process_bounding_box,
    save_cube_with_retries,
    search_stac_items,
)


def load_config(config_path: str) -> Dict:
    spec = importlib.util.spec_from_file_location("pipeline_config", config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load config from {config_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "PIPELINE_CONFIG"):
        raise RuntimeError("Config file must define PIPELINE_CONFIG")
    return module.PIPELINE_CONFIG


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

    return save_cube_with_retries(cubedataset, location, start_date, end_date, base_output_dir=output_dir)


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


def merge_cubes(config: Dict, input_dirs: Dict[str, str], output_dir: str, skip_existing: bool) -> None:
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

    for prefix, items in groups.items():
        s2 = items.get("S2L2A", [])
        s1 = items.get("S1RTC", [])

        s2_map = {d: p for p, d in s2}
        s1_map = {d: p for p, d in s1}

        common_dates = sorted(set(s2_map.keys()) & set(s1_map.keys()))
        if not common_dates:
            print(f"[MERGE] Missing common S2/S1 date for {prefix}")
            continue

        date_range = common_dates[-1]
        final_files = [s2_map[date_range], s1_map[date_range]]

        for aux_name in ["COPDEM", "ESALC"]:
            aux_items = items.get(aux_name, [])
            if not aux_items:
                continue
            aux_items_sorted = sorted(aux_items, key=lambda x: x[1])
            if config["merge"]["prefer_latest_aux"]:
                final_files.append(aux_items_sorted[-1][0])
            else:
                final_files.append(aux_items_sorted[0][0])

        final_prefix = f"{prefix}__{date_range}"
        merge_groups[prefix] = final_files
        final_prefix_name[prefix] = final_prefix

    for prefix, paths in merge_groups.items():
        final_prefix = final_prefix_name[prefix]
        output_path = os.path.join(output_dir, f"{final_prefix}.zarr")
        if skip_existing and os.path.exists(output_path):
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

        encoding = {}
        compressor = zarr.Blosc(cname="zstd", clevel=3, shuffle=1)

        def flatten_chunks(chunks):
            if chunks is None:
                return None
            return tuple(int(c) for dim in chunks for c in dim)

        for var in merged.data_vars:
            encoding[var] = {"compressor": compressor, "chunks": flatten_chunks(merged[var].chunks)}

        for coord in merged.coords:
            if coord not in encoding:
                encoding[coord] = {"compressor": None, "chunks": flatten_chunks(merged[coord].chunks)}

        merged.to_zarr(output_path, mode="w", encoding=encoding, consolidated=True)
        print(f"[MERGE] Saved: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Data cube pipeline orchestrator")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "pipeline_config.py"),
        help="Path to pipeline_config.py",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    for key in ["s2", "s2_cloudmask", "s1", "copdem", "esalc", "merged"]:
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
            cfg["increment_months"],
            cfg["decrement_months"],
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
            edge_size=cfg["edge_size"],
            units=cfg["units"],
            resolution=cfg["resolution"],
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
            edge_size=cfg["edge_size"],
            units=cfg["units"],
            resolution=cfg["resolution"],
            skip_existing=cfg["skip_existing"],
            processed_locations=processed["s1"],
        )

        copdem_range = cfg["static_date_ranges"]["copdem"]
        create_cube_for_location(
            location=location,
            lon=lon,
            lat=lat,
            start_date=copdem_range["start"],
            end_date=copdem_range["end"],
            collections=cfg["collections"]["copdem"],
            source=cfg["sources"]["copdem"],
            output_dir=cfg["output_dirs"]["copdem"],
            edge_size=cfg["edge_size"],
            units=cfg["units"],
            resolution=cfg["resolution"],
            skip_existing=cfg["skip_existing"],
            processed_locations=processed["copdem"],
        )

        esalc_range = cfg["static_date_ranges"]["esalc"]
        create_cube_for_location(
            location=location,
            lon=lon,
            lat=lat,
            start_date=esalc_range["start"],
            end_date=esalc_range["end"],
            collections=cfg["collections"]["esalc"],
            source=cfg["sources"]["esalc"],
            output_dir=cfg["output_dirs"]["esalc"],
            edge_size=cfg["edge_size"],
            units=cfg["units"],
            resolution=cfg["resolution"],
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
        merge_cubes(cfg, input_dirs, cfg["output_dirs"]["merged"], cfg["skip_existing"])


if __name__ == "__main__":
    main()
