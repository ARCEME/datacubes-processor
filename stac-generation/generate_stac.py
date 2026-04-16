#!/usr/bin/env python3
"""
Generate STAC collection and items for ARCEME data cubes stored in S3.

Each zarr file in the bucket becomes one STAC Item linked to a parent Collection.
Metadata is extracted directly from zarr attributes plus the filename.

Requirements:
    pip install pystac s3fs xarray zarr shapely pyproj pyyaml numpy
    Optional (richer cube:dimensions): pip install xstac

Usage:
    python generate_stac.py
    python generate_stac.py --config stac_config.yaml --output ./stac-output
    python generate_stac.py --dry-run       # list files only
    python generate_stac.py --zarr DC__wocat_1007_dhp_28028__2017-10-27__2019-10-27.zarr
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import s3fs
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
    SpatialExtent,
    TemporalExtent,
)

# Optional: xstac enriches cube:dimensions automatically
try:
    from xstac import xarray_to_stac
    from xstac._xstac import build_temporal_dimension
    HAS_XSTAC = True
except ImportError:
    HAS_XSTAC = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZARR_NAME_PATTERN = re.compile(
    r"DC__wocat_(\d+)_dhp_(\d+)__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})\.zarr$"
)

# Temporal dimension names used in ARCEME cubes
ARCEME_TIME_DIMS = [
    "time_sentinel_2_l2a",
    "time_sentinel_1_rtc",
    "time_cop_dem_glo_30_dged_cog",
    "time_esa_worldcover",
]

DATACUBE_EXT = "https://stac-extensions.github.io/datacube/v2.2.0/schema.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_zarr_filename(name: str) -> dict | None:
    """Return dict with wocat_id, dhp_id, start_date, end_date or None."""
    m = ZARR_NAME_PATTERN.search(name)
    if not m:
        return None
    return {
        "wocat_id": m.group(1),
        "dhp_id": m.group(2),
        "start_date": m.group(3),
        "end_date": m.group(4),
    }


def get_wgs84_bbox(ds: xr.Dataset) -> tuple[float, float, float, float]:
    """Transform UTM x/y extents to WGS84 (lon_min, lat_min, lon_max, lat_max)."""
    epsg = int(ds.attrs.get("epsg", 32632))
    tfm = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    x_min = float(ds.x.min())
    x_max = float(ds.x.max())
    y_min = float(ds.y.min())
    y_max = float(ds.y.max())
    lon_min, lat_min = tfm.transform(x_min, y_min)
    lon_max, lat_max = tfm.transform(x_max, y_max)
    return (lon_min, lat_min, lon_max, lat_max)


def _numpy_to_python(obj):
    """Recursively convert numpy scalars to plain Python types (for JSON)."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def build_cube_dimensions(ds: xr.Dataset) -> dict:
    """
    Build STAC datacube cube:dimensions dict from dataset.
    Covers x, y (spatial) and all temporal dimensions present in ds.
    """
    epsg = int(ds.attrs.get("epsg", 32632))
    dims: dict = {}

    # Spatial x
    dims["x"] = {
        "type": "spatial",
        "axis": "x",
        "extent": [float(ds.x.min()), float(ds.x.max())],
        "reference_system": f"EPSG:{epsg}",
    }

    # Spatial y
    dims["y"] = {
        "type": "spatial",
        "axis": "y",
        "extent": [float(ds.y.min()), float(ds.y.max())],
        "reference_system": f"EPSG:{epsg}",
    }

    # Temporal dimensions
    for tdim in ARCEME_TIME_DIMS:
        if tdim not in ds.dims:
            continue
        times = ds[tdim].values
        if len(times) == 0:
            continue
        t_start = str(np.datetime_as_string(times.min(), unit="s")) + "Z"
        t_end = str(np.datetime_as_string(times.max(), unit="s")) + "Z"
        dims[tdim] = {
            "type": "temporal",
            "extent": [t_start, t_end],
            "description": f"Timestamps for {tdim.replace('time_', '').replace('_', '-')}",
        }
        if len(times) > 1:
            # Compute median step in days (approximate)
            deltas = np.diff(times.astype("datetime64[D]").astype(int))
            median_days = int(np.median(deltas))
            if median_days > 0:
                dims[tdim]["step"] = f"P{median_days}D"

    return dims


def build_cube_variables(ds: xr.Dataset) -> dict:
    """Build STAC datacube cube:variables dict from dataset data_vars."""
    variables: dict = {}
    for var in ds.data_vars:
        da = ds[var]
        entry: dict = {
            "type": "data",
            "dimensions": list(da.dims),
        }
        if da.attrs.get("units"):
            entry["unit"] = da.attrs["units"]
        if da.attrs.get("long_name"):
            entry["description"] = da.attrs["long_name"]
        variables[str(var)] = entry
    return variables


# ---------------------------------------------------------------------------
# STAC item builder
# ---------------------------------------------------------------------------

def build_stac_item(
    ds: xr.Dataset,
    zarr_name: str,
    config: dict,
    file_meta: dict,
) -> Item:
    """
    Create a pystac.Item from an xarray Dataset.
    Falls back to manual cube:dimensions if xstac is not installed.
    """
    collection_id = config["collection_id"]
    s3_bucket = config["s3_bucket"]
    s3_prefix = config.get("s3_prefix", "")  # optional subfolder inside bucket
    epsg = int(ds.attrs.get("epsg", 32632))

    bbox = get_wgs84_bbox(ds)
    geometry = json.loads(json.dumps(shapely.box(*bbox).__geo_interface__))

    item_id = (
        f"{collection_id}-wocat-{file_meta['wocat_id']}"
        f"-dhp-{file_meta['dhp_id']}"
    )

    # Collect safe attrs from zarr (skip large/internal ones)
    _skip = {"epsg", "central_x", "central_y", "edge_size_px", "edge_size_m"}
    extra_props = {
        k: _numpy_to_python(v)
        for k, v in ds.attrs.items()
        if k not in _skip and isinstance(v, (str, int, float, bool, np.integer, np.floating))
    }

    properties = {
        "title": (
            f"ARCEME Datacube – WOCAT {file_meta['wocat_id']}"
            f" / DHP {file_meta['dhp_id']}"
        ),
        "description": ds.attrs.get("project", config["collection_title"]),
        "start_datetime": file_meta["start_date"] + "T00:00:00Z",
        "end_datetime": file_meta["end_date"] + "T00:00:00Z",
        "datetime": None,  # use start/end instead
        "license": config.get("license", "proprietary"),
        "platform": "sentinel-1, sentinel-2",
        "instruments": ["c-sar", "msi"],
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "epsg": epsg,
        **extra_props,
    }

    # href: s3 path or relative path inside collection
    zarr_href = f"s3://{s3_bucket}/{s3_prefix}{zarr_name}" if not s3_prefix else \
        f"s3://{s3_bucket}/{s3_prefix.rstrip('/')}/{zarr_name}"

    assets = {
        "data": Asset(
            href=zarr_href,
            media_type="application/vnd+zarr",
            roles=["data"],
            title=zarr_name,
        )
    }

    if HAS_XSTAC:
        # Let xstac fill in cube:dimensions and cube:variables
        template = {
            "id": item_id,
            "type": "Feature",
            "stac_version": "1.1.0",
            "properties": properties,
            "geometry": geometry,
            "bbox": list(bbox),
            "assets": {
                "data": {
                    "href": zarr_href,
                    "type": "application/vnd+zarr",
                    "roles": ["data"],
                    "title": zarr_name,
                }
            },
            "stac_extensions": [DATACUBE_EXT],
        }
        item = xarray_to_stac(
            ds,
            template,
            temporal_dimension=False,
            x_dimension="x",
            y_dimension="y",
            reference_system=False,
        )
        # Add multiple temporal dimensions
        cube_dims = item.properties.get("cube:dimensions", {})
        for tdim in ARCEME_TIME_DIMS:
            if tdim not in ds.dims:
                continue
            td = build_temporal_dimension(ds, tdim, None, None, None).to_dict()
            cube_dims[tdim] = {k: v for k, v in td.items() if v is not None}
        # Attach EPSG to spatial dims
        for ax in ("x", "y"):
            if ax in cube_dims:
                cube_dims[ax]["reference_system"] = f"EPSG:{epsg}"

    else:
        # Manual implementation (no xstac needed)
        cube_dims = build_cube_dimensions(ds)
        cube_vars = build_cube_variables(ds)

        properties["cube:dimensions"] = cube_dims
        properties["cube:variables"] = cube_vars

        item = Item(
            id=item_id,
            geometry=geometry,
            bbox=list(bbox),
            datetime=None,
            properties=properties,
            stac_extensions=[DATACUBE_EXT],
            assets=assets,
        )

    item.add_link(
        pystac_link(
            rel="collection",
            target=f"../{collection_id}.json",
            title=config["collection_title"],
        )
    )

    return item


def pystac_link(rel: str, target: str, title: str):
    """Create a simple pystac Link."""
    from pystac import Link
    return Link(rel=rel, target=target, title=title, media_type="application/json")


# ---------------------------------------------------------------------------
# Collection builder
# ---------------------------------------------------------------------------

def build_collection(config: dict, items: list[Item]) -> Collection:
    """Build the parent STAC Collection from config + derived extents."""
    bboxes = [item.bbox for item in items if item.bbox]
    if bboxes:
        spatial_extent = SpatialExtent([[
            min(b[0] for b in bboxes),
            min(b[1] for b in bboxes),
            max(b[2] for b in bboxes),
            max(b[3] for b in bboxes),
        ]])
    else:
        spatial_extent = SpatialExtent([config.get("fallback_bbox", [-180, -90, 180, 90])])

    starts, ends = [], []
    for item in items:
        p = item.properties
        if p.get("start_datetime"):
            starts.append(datetime.fromisoformat(p["start_datetime"].replace("Z", "+00:00")))
        if p.get("end_datetime"):
            ends.append(datetime.fromisoformat(p["end_datetime"].replace("Z", "+00:00")))
    temporal_extent = TemporalExtent([[
        min(starts) if starts else None,
        max(ends) if ends else None,
    ]])

    collection = Collection(
        id=config["collection_id"],
        title=config["collection_title"],
        description=config["collection_description"],
        extent=Extent(spatial_extent, temporal_extent),
        license=config.get("license", "proprietary"),
        extra_fields={
            "stac_version": "1.1.0",
            "keywords": config.get("keywords", []),
            "providers": config.get("providers", []),
            "stac_extensions": [DATACUBE_EXT],
        },
    )
    return collection


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def list_zarr_names(fs: s3fs.S3FileSystem, bucket: str) -> list[str]:
    """Return list of zarr directory names (without bucket prefix)."""
    entries = fs.ls(bucket, detail=False)
    names = []
    for e in entries:
        name = Path(e).name
        if name.endswith(".zarr"):
            names.append(name)
    return sorted(names)


def open_zarr_from_s3(fs: s3fs.S3FileSystem, bucket: str, zarr_name: str) -> xr.Dataset:
    """Open a zarr store from S3, trying consolidated=False as fallback."""
    store = s3fs.S3Map(root=f"{bucket}/{zarr_name}", s3=fs)
    try:
        return xr.open_zarr(store)
    except Exception:
        return xr.open_zarr(store, consolidated=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate STAC collection + items for ARCEME zarr cubes in S3"
    )
    parser.add_argument(
        "--config", default="stac_config.yaml",
        help="Path to YAML config (default: stac_config.yaml)",
    )
    parser.add_argument(
        "--output", default="./stac-output",
        help="Output directory for STAC files (default: ./stac-output)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only list zarr files, do not generate STAC",
    )
    parser.add_argument(
        "--zarr", metavar="NAME",
        help="Process a single zarr file by name (for testing)",
    )
    args = parser.parse_args()

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Connect to S3
    s3_kwargs = config.get("s3_kwargs", {})
    fs = s3fs.S3FileSystem(**s3_kwargs)
    bucket = config["s3_bucket"]

    # List zarr files
    print(f"Listing zarr files in s3://{bucket}/ ...")
    if args.zarr:
        zarr_names = [args.zarr]
    else:
        zarr_names = list_zarr_names(fs, bucket)
    print(f"Found {len(zarr_names)} zarr file(s)")

    if args.dry_run:
        for name in zarr_names:
            meta = parse_zarr_filename(name)
            tag = f"wocat={meta['wocat_id']} dhp={meta['dhp_id']} {meta['start_date']}…{meta['end_date']}" if meta else "??"
            print(f"  {name}  [{tag}]")
        return

    # Generate STAC items
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    items: list[Item] = []
    failed: list[tuple[str, str]] = []

    for zarr_name in zarr_names:
        file_meta = parse_zarr_filename(zarr_name)
        if file_meta is None:
            print(f"  SKIP (unexpected filename): {zarr_name}")
            continue

        print(f"Processing {zarr_name} ...", end=" ", flush=True)
        try:
            ds = open_zarr_from_s3(fs, bucket, zarr_name)
            item = build_stac_item(ds, zarr_name, config, file_meta)
            items.append(item)
            print(f"OK  →  {item.id}")
        except Exception as exc:
            print(f"ERROR: {exc}")
            failed.append((zarr_name, str(exc)))

    print(f"\n{len(items)} item(s) generated, {len(failed)} failed.")

    if not items:
        print("Nothing to save.")
        return

    # Build collection and save
    collection = build_collection(config, items)
    collection.add_items(items)
    collection.normalize_and_save(
        root_href=str(output_dir),
        catalog_type=CatalogType.SELF_CONTAINED,
    )
    print(f"STAC collection saved to: {output_dir}/")

    if failed:
        print("\nFailed files:")
        for name, err in failed:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    main()
