from typing import Any, List, Optional, Union
import numpy as np
import xarray as xr
from pyproj import CRS, Transformer
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info
from typing import Union, Tuple, List, Dict, Any
import pystac_client
import planetary_computer as pc
from typing import Optional, List, Dict
import time
from datetime import datetime
import shutil
import zarr
from typing import Any
import pandas as pd
import os
import numpy as np
import xarray as xr
import stackstac
from rasterio.enums import Resampling
from typing import List, Dict, Any
import re

BANDS_BY_COLLECTION = {
    'sentinel-1-rtc': ["vv", "vh"],
    'sentinel-1-grd': ["vv", "vh"],
    'sentinel-2-l2a': ['B01_20m', 'B02_10m', 'B03_10m', 'B04_10m',
                       'B05_20m', 'B06_20m', 'B07_20m', 'B08_10m',
                       'B8A_20m', 'B09_60m', 'B11_20m', 'B12_20m',
                       'SCL_20m'],
    'sentinel-2-l1c': ['B01', 'B02', 'B03', 'B04',
                       'B05', 'B06', 'B07', 'B08',
                       'B8A', 'B09', 'B11', 'B12'],
    'esa-worldcover': ['map'],
    'cop-dem-glo-30': ['data'],
    'cop-dem-glo-30-dged-cog': ['data'],
}


def central_pixel_bbox(
    lat: Union[float, int],
    lon: Union[float, int],
    edge_size: Union[float, int],
    resolution: Union[float, int],
) -> tuple:
    """Creates a Bounding Box (BBox) given a pair of coordinates and a buffer distance.

    Parameters
    ----------
    lat : float
        Latitude.
    lon : float
        Longitude.
    edge_size : float
        Buffer distance in meters.
    resolution : int | float
        Spatial resolution to use.
    latlng : bool, default = True
        Whether to return the BBox as geographic coordinates.

    Returns
    -------
    tuple
        BBox in UTM coordinates, BBox in latlon, and EPSG.
    """
    # Get the UTM EPSG from latlon
    utm_crs_list = query_utm_crs_info(
        datum_name="WGS 84",
        area_of_interest=AreaOfInterest(lon, lat, lon, lat),
    )

    # Save the CRS
    epsg = utm_crs_list[0].code
    utm_crs = CRS.from_epsg(epsg)

    # Initialize a transformer to UTM
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    # Initialize a transformer from UTM to latlon
    inverse_transformer = Transformer.from_crs(
        f"EPSG:{epsg}", "EPSG:4326", always_xy=True
    )

    # Transform latlon to UTM
    utm_coords = transformer.transform(lon, lat)

    # Round the coordinates
    utm_coords_round = [round(coord / resolution) * resolution for coord in utm_coords]

    # Buffer size
    buffer = round(edge_size * resolution / 2)

    # Create BBox coordinates according to the edge size
    E = utm_coords_round[0] + buffer
    W = utm_coords_round[0] - buffer
    N = utm_coords_round[1] + buffer
    S = utm_coords_round[1] - buffer

    # Create polygon from BBox coordinates
    polygon = [
        [W, S],
        [E, S],
        [E, N],
        [W, N],
        [W, S],
    ]

    # Transform vertices of polygon to latlon
    polygon_latlon = [list(inverse_transformer.transform(x[0], x[1])) for x in polygon]

    # Create UTM BBox
    bbox_utm = {
        "type": "Polygon",
        "coordinates": [polygon],
    }

    # Create latlon BBox
    bbox_latlon = {
        "type": "Polygon",
        "coordinates": [polygon_latlon],
    }

    return (bbox_utm, bbox_latlon, utm_coords, int(epsg))


def compute_distance_to_center(da: xr.DataArray) -> np.ndarray:
    """Computes the distance from each pixel to the specified center of the data cube.

    Parameters
    ----------
    da : xr.DataArray
        Data cube to compute the distance from.

    Returns
    -------
    np.ndarray
        Distance from each pixel to the specified center.
    """
    # Create meshgrid of coordinates
    coordinates = np.meshgrid(da.x, da.y)

    # Create meshgrid using just the value of the center coordinates
    x = (coordinates[0] ** 0) * da.attrs["central_x"]
    y = (coordinates[1] ** 0) * da.attrs["central_y"]

    # Compute the distance, transposed, so y is first
    distance_to_center = np.linalg.norm((coordinates) - np.array([x, y]), axis=0).T

    return distance_to_center


def harmonize_to_pixels(edge_size, units="m", resolution=10, constants=None):
    if units != "px":
        if units == "m":
            edge_size = edge_size / resolution
        else:
            if constants is None:
                raise ValueError("constants must be provided for unit conversion.")
            edge_size = (edge_size * getattr(constants, units)) / resolution
    return edge_size


def process_bounding_box(
    edge_size: Union[float, int],
    units: str,
    resolution: Union[float, int],
    lat: float,
    lon: float,
    location: str,
    constants=None,
) -> Tuple[List[float], Dict[str, Any], int]:
    """
    Processing edge_size and returns:
    - bbox_utm: [min_x, min_y, max_x, max_y] in UTM,
    - bbox_latlon: GeoJSON),
    - epsg: EPSG code for UTM.
    """

    edge_size_harmonized = harmonize_to_pixels(edge_size, units, resolution, constants)
    # print(f"Harmonized edge_size: {edge_size_harmonized}")

    if edge_size_harmonized <= 0:
        raise ValueError(f"Invalid edge_size {edge_size_harmonized} for {location}.")

    try:
        bbox_utm_geojson, bbox_latlon, utm_coords, epsg = central_pixel_bbox(
            lat, lon, edge_size_harmonized, resolution
        )
        # print(f"central_pixel_bbox output: utm_coords={utm_coords}, epsg={epsg}")
    except ValueError as e:
        raise ValueError(f"Error in central_pixel_bbox for {location}: {e}")

    coords = bbox_utm_geojson['coordinates'][0]
    x_coords, y_coords = zip(*coords)
    min_x, max_x = min(x_coords), max(x_coords)
    min_y, max_y = min(y_coords), max(y_coords)

    if min_x >= max_x or min_y >= max_y:
        raise ValueError(
            f"Invalid bounding box for {location}: {bbox_utm_geojson}. "
            f"Latitude: {lat}, Longitude: {lon}"
        )

    bbox_utm = [min_x, min_y, max_x, max_y]
    # print("Bounding box (UTM):", bbox_utm)

    return bbox_utm, bbox_latlon, epsg


def get_stac_client(source: str) -> pystac_client.Client:
    """
    Returns STAC client for the specified source.

    Parameters
    ---------
    source : str
        Example: 'planetary', 'dataspace', 'cf', ...

    Returns
    -------
    pystac_client.Client
    """

    source = source.lower()

    if source == "planetary":
        stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        client = pystac_client.Client.open(stac_url, modifier=pc.sign_inplace)

    elif source in {"dataspace", "copernicus", "cdse"}:
        stac_url = "https://stac.dataspace.copernicus.eu/v1/"
        client = pystac_client.Client.open(stac_url)

    else:
        raise ValueError(f"Unknown STAC source: {source}")

    return client


def search_stac_items(
    source: str,
    bbox_latlon: Dict,
    start_date: str,
    end_date: str,
    collections: List[str],
    location: str,
    limit: int = 1000,
    query: Optional[Dict] = None,
    verbose: bool = False,
) -> Optional[List]:
    """
    Searching items in STAC API

    Parameters
    ---------
    source : str
        'planetary', 'dataspace', 'cf', ...
    bbox_latlon : dict
        GeoJSON Polygon (bounding box).
    start_date : str
        Starting date (ISO8601, np. '2020-01-01').
    end_date : str
        End date (ISO8601).
    collections : list of str
        Name of collection (eg. ['sentinel-1-grd']).
    location : str
        Location name — only for logs.
    limit : int
        Max no of. STAC items in one query.

    Returns
    -------
    list lub None
        Lista of STAC items or None if there is no results.
    """

    # Pobierz klienta STAC
    client = get_stac_client(source)
    client.add_conforms_to("ITEM_SEARCH")

    # Wyszukiwanie
    search = client.search(
        intersects=bbox_latlon,
        datetime=f"{start_date}/{end_date}",
        collections=collections,
        limit=limit,
        query=query,
    )
    # print(search)
    items = search.item_collection()

    # Podpisywanie dla Planetary
    if source.lower() == "planetary":
        items = pc.sign(items)

    count = len(items)
    if verbose:
        print(f"Found: {count} items")

    if count == 0:
        if verbose:
            print(f"No items for {location}: Skipping.")
        return None

    return items

def save_cube_with_retries(
    cubedataset: Any,
    location: str,
    start_date: str,
    end_date: str,
    max_retries: int = 3,
    base_output_dir: str = '/ARCEMECUBES/STAGING_CUBES/'
) -> bool:
    """
    Save data cube to Zarr format with retries if there is any errors.

    Parameters
    ----------
    cubedataset : xarray.Dataset
        Data cube to save.
    location : str
        Name of location.
    start_date : str
        Start date in format 'YYYY-MM-DD'.
    end_date : str
        End date in format 'YYYY-MM-DD'.
    max_retries : int, optional (default 3)
        Maximum number of save retries.
    base_output_dir : str, optional
        catalog, where to sacve the data cubes.

    Returns
    -------
    bool
        True, if save was sucessful, False if save was not sucessful.
    """

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    cube_name = f"DC__{location}__{start_date}__{end_date}_{timestamp}_v0100"
    output_path = f"{base_output_dir}/{cube_name}.zarr"

    retry_count = 0
    success = False

    while retry_count < max_retries and not success:
        retry_count += 1
        print(f"Saving cube: {cube_name} (Attempt {retry_count}/{max_retries}) ...")
        try:
            cubedataset.to_zarr(output_path, mode='w', compute=True)

            with zarr.open(output_path, mode='r') as store:
                if store.attrs and any(store.keys()):
                    print(f"Successfully saved cube")
                    success = True
                else:
                    print(f"Empty Zarr store created for {location} on attempt {retry_count}. Retrying.")
                    shutil.rmtree(output_path, ignore_errors=True)
        except Exception as e:
            print(f"Error writing Zarr for {location} on attempt {retry_count}: {e}")
            shutil.rmtree(output_path, ignore_errors=True)
            if retry_count < max_retries:
                time.sleep(2)

    if not success:
        print(f"Failed to save cube for {location} after {max_retries} attempts. Skipping.")

    return success

def get_location_data(table, idx):
    """
    Get information from data frame based on index.
    
    Parameters
    ----------
    table : pd.DataFrame
    idx : int
    
    Returns
    -------
    tuple
        (location, lon, lat, event_date)
    """
    location = table.loc[idx, 'DisNo.']
    lon = table.loc[idx, 'longitude']
    lat = table.loc[idx, 'latitude']
    # event_date = table.loc[idx, 'start_date'] 

    if 'start_date' in table.columns and not pd.isna(table.loc[idx, 'start_date']):
        event_date = table.loc[idx, 'start_date']
    else:
        event_date = table.loc[idx, 'date']

    return location, lon, lat, event_date


def build_cubedataset_from_items(
    items: List[Any],
    data_collections: List[str],
    bbox_utm: List[float],
    epsg: int,
    resolution: float,
    stac_url: str,
    start_date: str,
    end_date: str,
    location: str,
) -> xr.Dataset:
    """
    Builds data cubes for many STAC collection, keeping separate time dimensions.

    Parameters
    ---------
    items : list
        List of STAC Items.
    data_collections : list
        List collections, eg. ['sentinel-1-grd', 'sentinel-2-l2a']
    bbox_utm : list
        Bounding box w UTM: [minx, miny, maxx, maxy]
    epsg : int
        EPSG in UTM.
    resolution : float
        Resoltion in meters.
    stac_url : str
        Source URL for STAC catalog.
    start_date : str
        Start date (ISO format).
    end_date : str 
        End date (ISO format).
    location : str
        Name of location (for metadata).

    Returns
    -------
    xr.Dataset
        Merged datacubes with separate time dimensions.
    """

    problematic_coords = ['raster:offset', 'raster:scale', 'proj:shape', 'proj:code', 'auth:refs']
    dataset_list = []

    # kolekcje z wymuszonym zakresem dat 2010–2020
    # fixed_range_collections = ['esa-worldcover', 'cop-dem-glo-30', 'cop-dem-glo-30-dged-cog']
    # fixed_start, fixed_end = "2010-01-01", "2020-12-31"

    #newly added 07.10
    if items is None:
        print(f"No items provided for location {location}, skipping all collections.")
        return None
    

    for collection in data_collections:
        bands = BANDS_BY_COLLECTION.get(collection)
        if not bands:
            print(f"Warning: No bands defined for {collection}, skipping.")
            continue

        ### added       
        # if collection in fixed_range_collections:
        #     filtered_items = [
        #         item for item in items
        #         if item.collection_id == collection
        #         and fixed_start <= item.datetime.isoformat()[:10] <= fixed_end
        #         print(fixed_start)
        #     ]
        # else:
        #     filtered_items = [
        #         item for item in items
        #         if item.collection_id == collection
        #         and start_date <= item.datetime.isoformat()[:10] <= end_date
        #     ]


        filtered_items = [item for item in items if item.collection_id == collection] ### old

        if not filtered_items:
            print(f"No items found for collection {collection}, skipping.")
            continue

        print(f"Stacking collection: {collection}, {len(filtered_items)} items, bands: {bands}")

        cube = stackstac.stack(
            filtered_items,
            assets=bands,
            resolution=resolution,
            resampling=Resampling.nearest,
            bounds=bbox_utm,
            epsg=int(epsg),
            dtype=np.float64,
            fill_value=np.nan,
            # chunksize="64MB"
            # chunksize={"time": 8, "y": 1000, "x": 1000}
        )

        # newly added

        static_mosaic_dates = {
            "esa-worldcover": np.datetime64("2020-01-01"),
            "cop-dem-glo-30": np.datetime64("2020-01-01"),
            "cop-dem-glo-30-dged-cog": np.datetime64("2020-01-01"),
        }

        # For static products force one common date -> guaranteed spatial mosaic
        if collection in static_mosaic_dates:
            fixed_time = static_mosaic_dates[collection]
            cube = cube.assign_coords(time=("time", np.full(cube.sizes["time"], fixed_time)))

        # Always mosaic items from the same day into a single image
        cube = cube.assign_coords(time=cube["time"].dt.floor("D"))
        cube_mosaicked = []
        for date, group in cube.groupby("time", squeeze=False):
            mosaic = stackstac.mosaic(group, dim="time", nodata=np.nan)

            # Ensure exactly one time slice per date after mosaicking
            if "time" in mosaic.dims:
                mosaic = mosaic.isel(time=0, drop=True)

            mosaic = mosaic.expand_dims(time=[np.datetime64(date)])
            cube_mosaicked.append(mosaic)

        # newly added - drop 'id' variable if exists to avoid conflicts during concatenation
        # cube_mosaicked = [g.drop_vars('id', errors='ignore') for g in cube_mosaicked]
        # for i in range(len(cube_mosaicked)):
        #     print(cube_mosaicked[i].coords)

        # stac_coords_to_drop = [
        #     'id', 'start_datetime', 'end_datetime', 'created', 'updated', 'eopf:origin_datetime', 'statistics',
        #     'datetime', 'platform', 'constellation', 'instruments', 'sat:absolute_orbit', 'processing:datetime'
        #     'gsd', 'proj:epsg', 'proj:shape', 'proj:transform', 'grid:code', 'view:sun_elevation', 'view:azimuth',
        #     'processing:datetime', 'view:incidence_angle', 'published', 'eopf:datatake_id', 'eo:cloud_cover',
        #     'view:sun_azimuth', 'eopf:datastrip_id'
        # ]

        # for i in range(len(cube_mosaicked)):
        #     drop_vars = [v for v in stac_coords_to_drop if v in cube_mosaicked[i].coords]
        #     cube_mosaicked[i] = cube_mosaicked[i].drop_vars(drop_vars, errors='ignore')

        for i in range(len(cube_mosaicked)):
            keep_coords = {'band', 'x', 'y', 'time'}
            drop_coords = [c for c in cube_mosaicked[i].coords if c not in keep_coords]
            if drop_coords:
                cube_mosaicked[i] = cube_mosaicked[i].drop_vars(drop_coords, errors='ignore')


        cube = xr.concat(cube_mosaicked, dim='time').sortby('time')
        cube = cube.drop_duplicates(dim='time')
        # end newly added

        for attr in ["spec", "crs", "transform", "resolution"]:
            cube.attrs.pop(attr, None)

        cube.attrs.update(
            collection=collection,
            stac=stac_url,
            epsg=epsg,
            resolution=resolution,
            edge_size_px=cube.x.shape[0],
            edge_size_m=cube.x.shape[0] * resolution,
            central_x=(bbox_utm[0] + bbox_utm[2]) / 2,
            central_y=(bbox_utm[1] + bbox_utm[3]) / 2,
            time_coverage_start=start_date,
            time_coverage_end=end_date,
        )

        ds = cube.to_dataset(dim="band")

        # Name time dimension uniquely per collection
        time_dim = f"time_{collection.replace('-', '_')}"
        ds = ds.rename({"time": time_dim})

        # Drop problematic coordinates if they exist
        ds = ds.drop_vars(problematic_coords, errors='ignore')

        # Keep only the bands of interest and coordinates
        ds = ds.drop_vars(
            [v for v in ds.variables if v not in bands + [time_dim, 'x', 'y']],
            errors='ignore'
        )

        if collection == "esa-worldcover":
            time_dim = f"time_{collection.replace('-', '_')}"
            if time_dim in ds:
                n_items = ds.dims[time_dim]
                fixed_time = np.datetime64("2020-01-01T00:00:00")
                fixed_times = np.full(n_items, fixed_time, dtype="datetime64[ns]")
                ds = ds.assign_coords({time_dim: fixed_times})

        # Standardize time encoding # new feature
        if time_dim in ds:
            reference_time = ds[time_dim].isel({time_dim: 0}).values
            reference_time_str = np.datetime_as_string(reference_time, unit="ms")
            ds[time_dim].encoding.update(
                units=f"milliseconds since {reference_time_str}",
                calendar="proleptic_gregorian",
                dtype="float64"
            )

        if collection == 'sentinel-2-l2a':
            old_bands = BANDS_BY_COLLECTION['sentinel-2-l2a']
            new_bands = ['B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08', 'B8A', 'B09', 'B11', 'B12', 'SCL']
            rename_dict = dict(zip(old_bands, new_bands))
            ds = ds.rename(rename_dict)

        if collection == 'esa-worldcover':
            old_bands = BANDS_BY_COLLECTION['esa-worldcover']
            new_bands = ['ESA_LC']
            rename_dict = dict(zip(old_bands, new_bands))
            ds = ds.rename(rename_dict)

        if collection == 'cop-dem-glo-30':
            old_bands = BANDS_BY_COLLECTION['cop-dem-glo-30']
            new_bands = ['COP_DEM']
            rename_dict = dict(zip(old_bands, new_bands))
            ds = ds.rename(rename_dict)

        if collection == 'cop-dem-glo-30-dged-cog':
                old_bands = BANDS_BY_COLLECTION['cop-dem-glo-30-dged-cog']
                new_bands = ['COP_DEM']
                rename_dict = dict(zip(old_bands, new_bands))
                ds = ds.rename(rename_dict)


        # Remove duplicate timestamps if any
        ds = ds.drop_duplicates(dim=time_dim)

        dataset_list.append(ds)

    if not dataset_list:
        raise ValueError(f"No valid datasets were built for {location}")

    merged = xr.merge(dataset_list, compat='override')
    print(f"Merged dataset for {location} with {len(dataset_list)} sub-datasets.")
    return merged


def export_zarr_to_band_folders(zarr_path: str, output_dir: str):
    """
    Exporting all bands of Zarr data cube for separate folders (for each band) and files (for each time step) to GeoTIFF.
    Name of folders are same as bands, and GeoTIFF files are splitted by time step.

    Parameters
    ---------
    zarr_path : str
        path to Zarr file.
    output_dir : str
        base catalog for saving results.
    """
    ds = xr.open_zarr(zarr_path)
    product_name = os.path.basename(zarr_path).replace(".zarr", "")
    product_dir = os.path.join(output_dir, product_name)
    os.makedirs(product_dir, exist_ok=True)

    # Check CRS
    if "epsg" in ds.attrs:
        crs = f"EPSG:{ds.attrs['epsg']}"
        ds.rio.write_crs(crs, inplace=True)
    else:
        raise ValueError("No attribiute 'epsg' in Zarr dataset.")

    # Get all time dimensions
    time_dims = [dim for dim in ds.dims if dim.startswith("time")]

    for band in ds.data_vars:
        band_dir = os.path.join(product_dir, band)
        os.makedirs(band_dir, exist_ok=True)

        # Get the time dimension for the band
        band_time_dim = None
        for tdim in time_dims:
            if tdim in ds[band].dims:
                band_time_dim = tdim
                break

        if band_time_dim is None:
            # No time dimension – save single file
            output_file = os.path.join(band_dir, f"{band}.tif")
            ds[band].compute().rio.to_raster(output_file, driver="GTiff")
            print(f"Saved {output_file}")
            continue

        # Iterate and save over time steps
        for t in ds[band][band_time_dim]:
            time_str = str(t.values).replace(":", "_").replace(" ", "_")
            data = ds[band].sel({band_time_dim: t}).compute()
            output_file = os.path.join(band_dir, f"{band}_{time_str}.tif")
            data.rio.to_raster(output_file, driver="GTiff")
            print(f"Saved {output_file}")
            



import logging
import os
from collections import defaultdict

class LoggerWithHttpTracking:
    def __init__(self, log_file: str = "logs/processing.log"):
        # Ensure directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        # Create logger
        self.logger = logging.getLogger("datacube_logger")
        self.logger.setLevel(logging.INFO)

        # File handler
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        fh.setFormatter(formatter)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)

        if not self.logger.hasHandlers():
            self.logger.addHandler(fh)
            self.logger.addHandler(ch)

        # Dictionary to track HTTP error counts
        self.http_error_counts = defaultdict(int)

    def info(self, msg: str):
        self.logger.info(msg)

    def warning(self, msg: str):
        # Automatically parse HTTP errors in warning messages
        import re
        match = re.search(r"HTTP error code: (\d+)", msg)
        if match:
            code = match.group(1)
            self.http_error_counts[code] += 1
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(msg)

    def log_http_summary(self):
        if self.http_error_counts:
            self.logger.info("HTTP error summary:")
            for code, count in self.http_error_counts.items():
                self.logger.info(f"HTTP {code}: {count} occurrences\n")
        else:
            self.logger.info("No HTTP errors encountered.\n")


def get_processed_locations(base_output_dir):
    processed = set()
    pattern = re.compile(r"^DC__(.+?)__\d{4}-\d{2}-\d{2}__\d{4}-\d{2}-\d{2}_.*\.zarr$")

    for fname in os.listdir(base_output_dir):
        if not fname.endswith(".zarr"):
            continue
        m = pattern.match(fname)
        if m:
            processed.add(m.group(1))
    return processed

### sentinel-1-rtc = 'S1RTC'
### sentinel-1-grd = 'S1GRD'
### sentinel-2-l2a = 'S2L2A'
### sentinel-2-l1c = 'S2L1C'
### esa-worldcover = 'LC'
### cop-dem-glo-30 = 'DEM'
