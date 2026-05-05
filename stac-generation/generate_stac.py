#!/usr/bin/env python3
"""
Generate STAC collection and items for ARCEME data cubes.

Reads zarr files from a public HTTP endpoint (CloudFerro Swift object storage).
No credentials required — the bucket is publicly accessible.

Supported filename patterns (auto-detected):
  WOCAT  DC__wocat_{wocat_id}_dhp_{dhp_id}__{start}__{end}.zarr
  GLOBAL DC__{event_id}_{d|dhp}__{start}__{end}.zarr

Requirements:
    pip install pystac xarray zarr shapely pyproj pyyaml numpy requests
    Optional (richer cube:dimensions): pip install xstac

Usage:
    python generate_stac.py --config stac_config_wocat.yaml  --output ./stac-wocat
    python generate_stac.py --config stac_config_global.yaml --output ./stac-global
    python generate_stac.py --dry-run
    python generate_stac.py --zarr DC__wocat_1007_dhp_28028__2017-10-27__2019-10-27.zarr
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
import shapely
import xarray as xr
import yaml
from pyproj import Transformer
from pystac import (
    Asset,
    CatalogType,
    Collection,
    Extent,
    Item,
    Link,
    SpatialExtent,
    TemporalExtent,
)

try:
    from xstac import xarray_to_stac
    from xstac._xstac import build_temporal_dimension
    HAS_XSTAC = True
except ImportError:
    HAS_XSTAC = False

# ---------------------------------------------------------------------------
# Filename patterns
# ---------------------------------------------------------------------------

# WOCAT bucket:  DC__wocat_1007_dhp_28028__2017-10-27__2019-10-27.zarr
_PATTERN_WOCAT = re.compile(
    r"DC__wocat_(\d+)_dhp_(\d+)__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})\.zarr$"
)

# GLOBAL bucket: DC__10051_dhp__2015-01-11__2017-01-11.zarr
#                DC__10051_d__2015-01-11__2017-01-11.zarr
_PATTERN_GLOBAL = re.compile(
    r"DC__(\d+)_(d|dhp)__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})\.zarr$"
)

ARCEME_TIME_DIMS = [
    "time_sentinel_2_l2a",
    "time_sentinel_1_rtc",
    "time_cop_dem_glo_30_dged_cog",
    "time_esa_worldcover",
]

DATACUBE_EXT = "https://stac-extensions.github.io/datacube/v2.2.0/schema.json"

# ---------------------------------------------------------------------------
# Filename parsing — returns a normalised dict
# ---------------------------------------------------------------------------

def parse_zarr_filename(name: str) -> dict | None:
    """
    Auto-detect filename pattern and return a normalised metadata dict:
      start_date, end_date, item_suffix, title_extra, pattern
    Returns None if the name does not match any known pattern.
    """
    m = _PATTERN_WOCAT.search(name)
    if m:
        wocat_id, dhp_id, start, end = m.groups()
        return {
            "start_date":  start,
            "end_date":    end,
            "item_suffix": f"wocat-{wocat_id}-dhp-{dhp_id}",
            "title_extra": f"WOCAT {wocat_id} / DHP {dhp_id}",
            "pattern":     "wocat",
        }

    m = _PATTERN_GLOBAL.search(name)
    if m:
        event_id, suffix, start, end = m.groups()
        return {
            "start_date":  start,
            "end_date":    end,
            "item_suffix": f"{event_id}-{suffix}",
            "title_extra": f"event {event_id} ({suffix.upper()})",
            "pattern":     "global",
        }

    return None

# ---------------------------------------------------------------------------
# S3 / HTTP helpers
# ---------------------------------------------------------------------------

def list_zarr_names(base_url: str) -> list[str]:
    """Return sorted list of zarr directory names from Swift container listing."""
    url = base_url.rstrip("/") + "/?delimiter=/&format=json"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return sorted(
        e["subdir"].rstrip("/")
        for e in resp.json()
        if "subdir" in e and e["subdir"].endswith(".zarr/")
    )


def open_zarr_http(base_url: str, zarr_name: str) -> xr.Dataset:
    url = f"{base_url.rstrip('/')}/{zarr_name}"
    try:
        return xr.open_zarr(url, consolidated=True)
    except Exception:
        return xr.open_zarr(url, consolidated=False)

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def get_wgs84_bbox(ds: xr.Dataset) -> tuple[float, float, float, float]:
    epsg = int(ds.attrs.get("epsg", 32632))
    tfm  = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lon_min, lat_min = tfm.transform(float(ds.x.min()), float(ds.y.min()))
    lon_max, lat_max = tfm.transform(float(ds.x.max()), float(ds.y.max()))
    return (lon_min, lat_min, lon_max, lat_max)


def _safe(v):
    if isinstance(v, np.integer):  return int(v)
    if isinstance(v, np.floating): return float(v)
    if isinstance(v, np.ndarray):  return v.tolist()
    return v

# ---------------------------------------------------------------------------
# cube:dimensions / cube:variables
# ---------------------------------------------------------------------------

def build_cube_dimensions(ds: xr.Dataset) -> dict:
    epsg = int(ds.attrs.get("epsg", 32632))
    dims: dict = {
        "x": {
            "type": "spatial", "axis": "x",
            "extent": [float(ds.x.min()), float(ds.x.max())],
            "reference_system": f"EPSG:{epsg}",
        },
        "y": {
            "type": "spatial", "axis": "y",
            "extent": [float(ds.y.min()), float(ds.y.max())],
            "reference_system": f"EPSG:{epsg}",
        },
    }
    for tdim in ARCEME_TIME_DIMS:
        if tdim not in ds.dims or ds.sizes[tdim] == 0:
            continue
        times = ds[tdim].values
        t0 = str(np.datetime_as_string(times.min(), unit="s")) + "Z"
        t1 = str(np.datetime_as_string(times.max(), unit="s")) + "Z"
        entry: dict = {
            "type":        "temporal",
            "extent":      [t0, t1],
            "description": tdim.replace("time_", "").replace("_", "-"),
        }
        if len(times) > 1:
            days = int(np.median(np.diff(times.astype("datetime64[D]").astype(int))))
            if days > 0:
                entry["step"] = f"P{days}D"
        dims[tdim] = entry
    return dims


def build_cube_variables(ds: xr.Dataset) -> dict:
    variables: dict = {}
    for var in ds.data_vars:
        da = ds[var]
        entry: dict = {"type": "data", "dimensions": list(da.dims)}
        if da.attrs.get("units"):
            entry["unit"] = da.attrs["units"]
        if da.attrs.get("long_name"):
            entry["description"] = da.attrs["long_name"]
        variables[str(var)] = entry
    return variables

# ---------------------------------------------------------------------------
# STAC item
# ---------------------------------------------------------------------------

def build_stac_item(
    ds: xr.Dataset,
    zarr_name: str,
    config: dict,
    file_meta: dict,
) -> Item:
    collection_id = config["collection_id"]
    base_url      = config["base_url"].rstrip("/")
    epsg          = int(ds.attrs.get("epsg", 32632))

    bbox     = get_wgs84_bbox(ds)
    geometry = json.loads(json.dumps(shapely.box(*bbox).__geo_interface__))
    item_id  = f"{collection_id}-{file_meta['item_suffix']}"

    _internal = {
        "epsg", "central_x", "central_y", "edge_size_px", "edge_size_m",
        "stac", "config_file", "source_locations_csv", "output_base_dir",
        "contact",
    }
    extra_props = {
        k: _safe(v)
        for k, v in ds.attrs.items()
        if k not in _internal
        and isinstance(v, (str, int, float, bool, np.integer, np.floating))
    }

    properties = {
        "title":           f"ARCEME Datacube – {file_meta['title_extra']}",
        "description":     ds.attrs.get("project", config["collection_title"]),
        "datetime":        None,
        "start_datetime":  file_meta["start_date"] + "T00:00:00Z",
        "end_datetime":    file_meta["end_date"]   + "T00:00:00Z",
        "license":         config.get("license", "proprietary"),
        "platform":        "sentinel-1, sentinel-2",
        "instruments":     ["c-sar", "msi"],
        "created":         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "epsg":            epsg,
        **extra_props,
    }

    zarr_href = f"{base_url}/{zarr_name}"

    if HAS_XSTAC:
        template = {
            "id": item_id, "type": "Feature", "stac_version": "1.1.0",
            "stac_extensions": [DATACUBE_EXT],
            "properties": properties,
            "geometry": geometry, "bbox": list(bbox),
            "assets": {"data": {
                "href": zarr_href, "type": "application/vnd+zarr",
                "roles": ["data"], "title": zarr_name,
            }},
        }
        item = xarray_to_stac(ds, template,
                              temporal_dimension=False,
                              x_dimension="x", y_dimension="y",
                              reference_system=False)
        cube_dims = item.properties.get("cube:dimensions", {})
        for tdim in ARCEME_TIME_DIMS:
            if tdim not in ds.dims:
                continue
            td = build_temporal_dimension(ds, tdim, None, None, None).to_dict()
            cube_dims[tdim] = {k: v for k, v in td.items() if v is not None}
        for ax in ("x", "y"):
            if ax in cube_dims:
                cube_dims[ax]["reference_system"] = f"EPSG:{epsg}"
    else:
        properties["cube:dimensions"] = build_cube_dimensions(ds)
        properties["cube:variables"]  = build_cube_variables(ds)

        item = Item(
            id=item_id, geometry=geometry, bbox=list(bbox),
            datetime=None, properties=properties,
            stac_extensions=[DATACUBE_EXT],
            assets={"data": Asset(
                href=zarr_href, media_type="application/vnd+zarr",
                roles=["data"], title=zarr_name,
            )},
        )

    item.add_link(Link(
        rel="collection",
        target=f"../{collection_id}.json",
        media_type="application/json",
        title=config["collection_title"],
    ))
    return item

# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def build_collection(config: dict, items: list[Item]) -> Collection:
    bboxes = [item.bbox for item in items if item.bbox]
    spatial_extent = SpatialExtent([[
        min(b[0] for b in bboxes), min(b[1] for b in bboxes),
        max(b[2] for b in bboxes), max(b[3] for b in bboxes),
    ]]) if bboxes else SpatialExtent([config.get("fallback_bbox", [-180, -90, 180, 90])])

    starts, ends = [], []
    for item in items:
        p = item.properties
        if p.get("start_datetime"):
            starts.append(datetime.fromisoformat(p["start_datetime"].replace("Z", "+00:00")))
        if p.get("end_datetime"):
            ends.append(datetime.fromisoformat(p["end_datetime"].replace("Z", "+00:00")))

    temporal_extent = TemporalExtent([[
        min(starts) if starts else None,
        max(ends)   if ends   else None,
    ]])

    return Collection(
        id=config["collection_id"],
        title=config["collection_title"],
        description=config["collection_description"],
        extent=Extent(spatial_extent, temporal_extent),
        license=config.get("license", "proprietary"),
        extra_fields={
            "stac_version": "1.1.0",
            "keywords":     config.get("keywords", []),
            "providers":    config.get("providers", []),
            # datacube extension lives on items, not on the collection
        },
    )

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate STAC collection + items for ARCEME zarr cubes"
    )
    parser.add_argument("--config",  default="stac_config.yaml")
    parser.add_argument("--output",  default="./stac-output")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--zarr",    metavar="NAME")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path) as f:
        config = yaml.safe_load(f)

    base_url = config["base_url"].rstrip("/")
    print(f"Source : {base_url}")
    print(f"Output : {args.output}")

    if args.zarr:
        zarr_names = [args.zarr]
    else:
        print("Listing zarr files ...")
        zarr_names = list_zarr_names(base_url)
    print(f"Found {len(zarr_names)} zarr file(s)")

    if args.dry_run:
        for name in zarr_names:
            meta = parse_zarr_filename(name)
            tag = f"[{meta['pattern']}] {meta['item_suffix']}  {meta['start_date']}…{meta['end_date']}" if meta else "??"
            print(f"  {name}\n    {tag}")
        return

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    items:  list[Item] = []
    failed: list[tuple[str, str]] = []

    for zarr_name in zarr_names:
        file_meta = parse_zarr_filename(zarr_name)
        if file_meta is None:
            print(f"  SKIP (unknown filename format): {zarr_name}")
            continue

        print(f"  {zarr_name} ...", end=" ", flush=True)
        try:
            ds   = open_zarr_http(base_url, zarr_name)
            item = build_stac_item(ds, zarr_name, config, file_meta)
            items.append(item)
            print(f"OK ({item.id})")
        except Exception as exc:
            print(f"ERROR: {exc}")
            failed.append((zarr_name, str(exc)))

    print(f"\n{len(items)} item(s) generated, {len(failed)} failed.")

    if not items:
        print("Nothing to save.")
        return

    collection = build_collection(config, items)
    collection.add_items(items)
    collection.normalize_and_save(
        root_href=str(output_dir),
        catalog_type=CatalogType.SELF_CONTAINED,
    )

    # pystac propagates item extensions to the collection during save,
    # but the datacube extension schema is item-only and makes collection
    # validation fail with a false positive — remove it from collection.json.
    import json as _json
    col_path = output_dir / "collection.json"
    with open(col_path) as f:
        col_json = _json.load(f)
    col_json.pop("stac_extensions", None)
    with open(col_path, "w") as f:
        _json.dump(col_json, f, indent=2)

    print(f"STAC saved to: {output_dir}/")

    if failed:
        print("\nFailed:")
        for name, err in failed:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    main()
