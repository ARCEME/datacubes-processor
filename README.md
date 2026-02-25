# ARCEME Data Cube Pipeline - Usage Guide

## Overview

The pipeline orchestrator creates multi-source satellite datacubes for ARCEME project locations. It processes:
- **Sentinel-2 L2A** (CDSE or Planetary Computer)
- **Sentinel-1 RTC** (Planetary Computer)
- **Copernicus DEM** (CDSE)
- **ESA WorldCover** (Planetary Computer)
- **Cloud Mask** (optional, using SEnSeIv2 model)
- **Merged datacubes** with all sources combined

## Quick Start

1. **Edit configuration**: Open `pipeline_config.yaml` and adjust paths, dates, and settings

2. **Run pipeline**:
```bash
cd /home/eouser/datacubes/data-cubes-arceme/src/processor
python pipeline_orchestrator.py
```

3. **Use custom config** (optional):
```bash
python pipeline_orchestrator.py --config /path/to/custom_config.yaml
```

## Configuration File

The `pipeline_config.yaml` contains all pipeline settings:

### Key Settings

```yaml
# Input CSV with columns: location, lon, lat, event_date
locations_csv: /path/to/locations.csv

# Skip locations that already exist in output directories
skip_existing: true

# Spatial parameters
spatial:
  edge_size: 10000  # meters (creates 10km x 10km tiles)
  resolution: 10    # pixel size in meters

# Time range relative to event date
temporal:
  increment_months: 12  # months before event
  decrement_months: 12  # months after event

# Data sources: 'cdse' or 'planetary'
sources:
  s2: cdse         # Sentinel-2 from CDSE
  s1: planetary    # Sentinel-1 from Planetary Computer
  copdem: cdse     # DEM from CDSE
  esalc: planetary # Land cover from Planetary Computer

# Enable cloud masking (adds ~30 min per location)
cloud_mask:
  enabled: true
  device: cpu      # or 'cuda' if GPU available

# Output directories for each stage
output_dirs:
  s2: /ARCEMECUBES/NEW-CUBES-MELANIE/S2L2A/
  s2_cloudmask: /ARCEME-MERGE/S2L2A_CLOUDMASK/
  s1: /ARCEMECUBES/NEW-CUBES-MELANIE/S1RTC/
  copdem: /ARCEMECUBES/NEW-CUBES-MELANIE/COPDEM/
  esalc: /ARCEMECUBES/NEW-CUBES-MELANIE/ESALC/
  merged: /ARCEME-MERGE/
```

### Static Layers

COPDEM and ESA WorldCover use fixed date ranges (not event-based):

```yaml
static_dates:
  copdem:
    start: "2010-01-01"
    end: "2024-12-31"
  esalc:
    start: "2019-01-01"  # WorldCover 2020 product
    end: "2020-12-31"
```

### Merge Settings

```yaml
merge:
  enabled: true
  chunk_time: 25   # temporal chunk size
  chunk_x: 500     # spatial chunks (500px = 5km at 10m resolution)
  chunk_y: 500
  vars_to_uint16:  # convert these variables to uint16 for compression
    - B01
    - B02
    # ... (all S2 bands, cloud_mask, SCL, ESA_LC)
```

## Pipeline Workflow

For each location in the CSV:

1. **Sentinel-2 L2A**: Creates cube from event_date ± temporal window
2. **Cloud Mask** (if enabled): Applies SEnSeIv2 model to S2 cube
3. **Sentinel-1 RTC**: Creates cube with same temporal window
4. **Copernicus DEM**: Creates cube with static date range
5. **ESA WorldCover**: Creates cube for 2020
6. **Merge** (if enabled): Combines all sources, rechunks, adds metadata

## Output Format

Each stage produces Zarr archives:
```
DC__<location>__S2L2A__<UTM>__<dates>.zarr
DC__<location>__S2L2A_CLOUDMASK__<UTM>__<dates>.zarr
DC__<location>__S1RTC__<UTM>__<dates>.zarr
DC__<location>__COPDEM__<UTM>__<dates>.zarr
DC__<location>__ESALC__<UTM>__<dates>.zarr
DC__<location>__<UTM>__<dates>.zarr  (merged cube)
```

## Skip Existing Logic

When `skip_existing: true`, the pipeline checks each output directory and skips locations that already have output files. This allows:
- Resuming interrupted runs
- Processing new locations without reprocessing old ones
- Selective reprocessing (delete specific outputs to reprocess only those)

## Dependencies

Requires:
- `pyyaml` (for config loading)
- `xarray`, `zarr`, `pandas`
- `rasterio`, `stackstac`, `pystac-client`
- `senseiv2` (for cloud masking)

See `requirements.txt` for full list.

## Troubleshooting

**"Config file not found"**: Make sure `pipeline_config.yaml` exists in the same directory as `pipeline_orchestrator.py`

**"Invalid YAML"**: Check YAML syntax (proper indentation, no tabs, matching quotes)

**STAC API errors**: Network issues or API changes - check URLs in config

**Cloud mask slow**: Consider setting `cloud_mask.enabled: false` or use `device: cuda` if GPU available

**Memory errors**: Reduce `chunk_time`, `chunk_x`, or `chunk_y` in merge settings
