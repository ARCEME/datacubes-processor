import xarray as xr
import numpy as np
from senseiv2.inference import CloudMask
from senseiv2.constants import SENTINEL2_DESCRIPTORS
import os
from pathlib import Path
import time

start = time.time()
# Define raw Sentinel-2 bands
S2_RAW_BANDS = ['B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08', 'B8A', 'B09', 'B11', 'B12']
BAND_TO_DESC = {band: i for i, band in enumerate(S2_RAW_BANDS)}

# Load model from local files
DEVICE = 'cpu'  # or 'cuda' if available
# For src/processor/ directory: go up 3 levels to project root
MODEL_DIR = Path(__file__).parent.parent.parent / 'SEnSeIv2_config'
config_path = MODEL_DIR / 'config.yaml'
weights_path = MODEL_DIR / 'weights.pt'
model = CloudMask(str(config_path), str(weights_path), verbose=True, categorise=True, device=DEVICE)

def process_datacube(zarr_input_path, zarr_output_path):
    """Process a single Zarr file and generate cloud mask."""
    print(f"Processing {zarr_input_path}")
    
    # Open the Zarr dataset
    try:
        ds = xr.open_zarr(zarr_input_path)
    except Exception as e:
        print(f"Error opening {zarr_input_path}: {str(e)}")
        return None
    
    # Get dimensions
    height = ds.sizes['y']
    width = ds.sizes['x']
    
    # Check for duplicate times
    time_series = ds['time_sentinel_2_l2a'].to_series()
    if time_series.duplicated().any():
        print(f"Warning: Duplicate time entries found in {zarr_input_path}")
        duplicates = time_series[time_series.duplicated(keep=False)]
        print(f"Duplicate timestamps: {duplicates.index.tolist()}")
    
    # Create output dataset
    ds_out = ds.copy(deep=True)
    
    # Process each unique date
    for time_val in ds.time_sentinel_2_l2a.values:
        # Check for Sentinel-2 data availability
        s2_available = any(
            band in ds.data_vars and not ds[band].sel(time_sentinel_2_l2a=time_val).isnull().all()
            for band in S2_RAW_BANDS
        )
        
        if not s2_available:
            print(f"No valid Sentinel-2 bands for time {time_val} in {zarr_input_path}")
            continue
            
        # Extract and normalize bands
        s2_data = []
        available_bands = []
        for band in S2_RAW_BANDS:
            if band in ds.data_vars and not ds[band].sel(time_sentinel_2_l2a=time_val).isnull().all():
                band_data = ds[band].sel(time_sentinel_2_l2a=time_val).values
                if band_data.ndim != 2:
                    print(f"Error: {band} at time {time_val} has unexpected shape {band_data.shape}")
                    continue
                band_data = np.nan_to_num(band_data, nan=0.0).astype(np.float32)
                band_data = (band_data - 1000) / 10000  # Normalize
                s2_data.append(band_data)
                available_bands.append(band)
        
        if not s2_data:
            print(f"No valid bands for time {time_val} in {zarr_input_path}")
            continue
            
        # Stack bands
        s2_array = np.stack(s2_data, axis=0)
        descriptors = [SENTINEL2_DESCRIPTORS[BAND_TO_DESC[band]] for band in available_bands]
        
        print(f"Time {time_val}: {len(available_bands)} bands, shape {s2_array.shape}")
        
        # Generate cloud mask
        try:
            cloud_mask = model(
                s2_array,
                descriptors=descriptors,
                stride=512
                # stride=min(height, width) // 3 # old
            )
            
            # Ensure cloud_mask is 2D
            if cloud_mask.ndim == 3:
                print(f"Warning: Cloud mask has shape {cloud_mask.shape}, taking first dimension")
                cloud_mask = cloud_mask[0]
            elif cloud_mask.shape != (height, width):
                print(f"Warning: Cloud mask shape {cloud_mask.shape} does not match expected ({height}, {width})")
            
            # Initialize cloud_mask variable if not exists
            if 'cloud_mask' not in ds_out:
                ds_out['cloud_mask'] = xr.DataArray(
                    np.full((ds.sizes['time_sentinel_2_l2a'], height, width), np.nan, dtype=np.float32),
                    dims=['time_sentinel_2_l2a', 'y', 'x'],
                    coords={'time_sentinel_2_l2a': ds.time_sentinel_2_l2a, 'y': ds.y, 'x': ds.x}
                )
            
            # Store cloud mask
            ds_out['cloud_mask'].loc[dict(time_sentinel_2_l2a=time_val)] = cloud_mask
            
        except Exception as e:
            print(f"Error processing time {time_val} in {zarr_input_path}: {str(e)}")
            continue
    
    # Save to Zarr
    try:
        ds_out.to_zarr(zarr_output_path, mode='w')
        print(f"Saved cloud-masked dataset to {zarr_output_path}")
        return ds_out
    except Exception as e:
        print(f"Error saving {zarr_output_path}: {str(e)}")
        return None
    

import re
import os

def get_processed_locations_cloudmask(output_dir):
    """
    Zwraca zbiór location_id w postaci:
    62878_d
    62878_dhp
    """
    processed = set()

    pattern = re.compile(
        r"^DC__(\d+_(?:d|dhp))__\d{4}-\d{2}-\d{2}__\d{4}-\d{2}-\d{2}_.+_cloudmask\.zarr$"
    )

    for fname in os.listdir(output_dir):
        m = pattern.match(fname)
        if m:
            processed.add(m.group(1))

    return processed


def extract_location_id(zarr_name):
    """
    DC__62878_d__2020-10-13__2022-10-13_....zarr → 62878_d
    """
    m = re.match(r"^DC__(\d+_(?:d|dhp))__", zarr_name)
    if not m:
        raise ValueError(f"Cannot parse location_id from {zarr_name}")
    return m.group(1)


def process_directory(input_dir, output_dir):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    processed_locations = get_processed_locations_cloudmask(output_dir)
    print(f"Already processed: {len(processed_locations)}")

    zarr_files = list(input_dir.glob("*.zarr"))
    if not zarr_files:
        print(f"No Zarr files found in {input_dir}")
        return

    for zarr_file in zarr_files:
        try:
            location_id = extract_location_id(zarr_file.name)
        except ValueError as e:
            print(e)
            continue

        if location_id in processed_locations:
            print(f"Skipping already processed {location_id}")
            continue

        output_file = output_dir / f"{zarr_file.stem}_cloudmask.zarr"

        result = process_datacube(zarr_file, output_file)
        if result is not None:
            print(f"Successfully processed {zarr_file.name}")
        else:
            print(f"Failed to process {zarr_file.name}")

# Example usage
if __name__ == "__main__":
    input_directory = '/ARCEMECUBES/NEW-CUBES-MELANIE/S2L2A/'
    output_directory = '/ARCEME-MERGE/S2L2A_CLOUDMASK'
    process_directory(input_directory, output_directory)

end = time.time()
print(f"Total processing time: {end - start} seconds")