import config
import os
from const import INCREMENT_MONTHS, DECREMENT_MONTHS, EDGE_SIZE, UNITS, RESOLUTION
from utils import central_pixel_bbox, compute_distance_to_center, harmonize_to_pixels, process_bounding_box, get_stac_client, search_stac_items, save_cube_with_retries, get_location_data, build_cubedataset_from_items
from typing import Any, List, Optional, Union
import numpy as np
import pandas as pd
import pystac_client
import rasterio.features
import rasterio
from rasterio.enums import Resampling
import stackstac
import xarray as xr
from scipy import constants
import geopandas as gpd
from shapely.geometry import Polygon
from pyproj import CRS, Transformer
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info
import zarr
from datetime import datetime
from dateutil.relativedelta import relativedelta
import gc
import shutil
import time
import planetary_computer as pc

# dc_locations_table_path = '/home/eouser/datacubes/ARCEMECUBES/clean_code/sample_locations_marcin.csv'
dc_locations_table_path = '/home/eouser/datacubes/arceme-datacubes/arceme-datacubes/datasets/dhp_global_subselection_new_melanie.csv'  #'/home/eouser/datacubes/arceme-datacubes/arceme-datacubes/datasets/1_max_precipitation_grid_cells.csv' #'/home/eouser/datacubes/DATA_ARCEME/dhp_global_subselection_mod_MK.csv' # '/home/eouser/datacubes/DATA_ARCEME/dhp_global_subselection_mod_MK.csv' #'/home/eouser/datacubes/DATA_ARCEME/1_max_precipitation_grid_cells.csv'
table = pd.read_csv(dc_locations_table_path)
nrow = table.shape[0]
base_output_dir = '/ARCEMECUBES/NEW-CUBES-MELANIE/S1RTC/' #/ARCEMECUBES/PRODUCTION_CUBES/PLANETARY/S1RTC/'
log_file = os.path.join(base_output_dir, "processing_times.txt")
max_retries = 5

no_data_log = os.path.join(base_output_dir, "no_items_datacubes.txt")

data_collections = [
                    'sentinel-1-rtc'
                    # 'sentinel-1-grd', #planetary
                    # 'sentinel-2-l2a', 
                    # 'sentinel-2-l1c', 
                    # 'cop-dem-glo-30', #planetary
                    # 'esa-worldcover', #planetary
                    # 'cop-dem-glo-30-dged-cog'
                    ] 


source="planetary" # 'cdse' or 'planetary'

if source == "cdse":
    stac_url = "https://stac.dataspace.copernicus.eu/v1/"
elif source == "planetary":
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
else:
    raise ValueError(f"Unknown source: {source}")
print(f'Selected endpoint:  {source}')


for i in range(nrow):

    start_time = time.time()
    location, lon, lat, event_date = get_location_data(table, i)
    print(f'Started processing {location}')
    print(f'Coordinates: lon={lon}, lat={lat}, event_date={event_date}')

    event_date = datetime.strptime(event_date, '%Y-%m-%d').date()
    start_date = (event_date - relativedelta(months=INCREMENT_MONTHS)).strftime('%Y-%m-%d')
    end_date = (event_date + relativedelta(months=DECREMENT_MONTHS)).strftime('%Y-%m-%d')

    print(start_date, end_date)
    try:
        bbox_utm, bbox_latlon, epsg =  process_bounding_box(
            EDGE_SIZE, UNITS, RESOLUTION, lat, lon, location, constants
        )
    except ValueError as e:
        print(f"Skipping {location}: {e}")



    items = search_stac_items(
        source=source,
        bbox_latlon=bbox_latlon,
        start_date=start_date,
        end_date=end_date,
        collections=data_collections,
        location=location,
        verbose=True
        # query = {"eo:cloud_cover":{"lte":80}},
    )

    if items is None or len(items) == 0:
        with open(no_data_log, "a", encoding="utf-8") as f:
            f.write(
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                f"Location: {location} | "
                f"Lon: {lon} | Lat: {lat} | "
                f"Period: {start_date} – {end_date} | "
                f"Collections: {data_collections}\n"
            )
        print(f"No items for {location}: logged to TXT.")
        continue

    # query = {"eo:cloud_cover":{"lte":50}},
    # sortby=["+properties.eo:cloud_cover"],)
    # "grid:code":{"eq":"MGRS-32TQP"}
    # items = items + items_special

    cubedataset = build_cubedataset_from_items(
        items=items,
        data_collections=data_collections,
        bbox_utm=bbox_utm,
        epsg=epsg,
        resolution=RESOLUTION,
        stac_url=stac_url,
        start_date=start_date,
        end_date=end_date,
        location=location,
    )

    success = save_cube_with_retries(cubedataset, location, start_date, end_date, max_retries, base_output_dir)
    if not success:
        continue  



    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Processing time for {location}: {elapsed_time:.2f} seconds")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Location: {location} | "
            f"Items: {len(items)} | "
            f"Time: {elapsed_time:.2f} s\n"
        )

    gc.collect()  
    # break
