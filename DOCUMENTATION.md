# ARCEME Data Cubes — Technical Documentation

**Project:** ARCEME — Adaptation and Resilience to Climate Extremes and Multi-hazard Events
**Code repository:** https://github.com/ARCEME/datacubes-processor
**ESA Open Science Catalogue:** https://opensciencedata.esa.int/stac-browser/#/projects/arceme/collection.json

---

## 1. Introduction

Data-cube technology enables the systematic integration of Earth-observation (EO)
datasets into multidimensional, analysis-ready structures that facilitate
spatio-temporal analysis. The ARCEME pipeline generates multi-source satellite
**minicubes** centred on locations of extreme environmental events, integrating
**Sentinel-1** (SAR), **Sentinel-2** (optical), **Copernicus DEM GLO-30** and
**ESA WorldCover** into a single, self-describing [Zarr](https://zarr.dev/) archive
per location.

Each cube covers a **10 × 10 km** area at **10 m** resolution (1000 × 1000 pixels)
over a **two-year** temporal window (±12 months around the event date). The workflow
relies entirely on open-source, Python-based tools for data access, preprocessing and
cube construction, ensuring reproducibility, scalability and adaptability to different
event types and study areas.

The cubes are built from an **extreme-events database** that provides, for each event,
an identifier, a country/location code, central coordinates (WGS84) and an event date.
Three location collections are produced:

| Collection | Source of locations |
|---|---|
| `ARCEME-DC-DHP-WOCAT` | WOCAT / DHP disaster sites |
| `ARCEME-DC-DHP-EMDAT` | EM-DAT International Disaster Database |
| `ARCEME-DC-DHP-GLOBAL` | Globally distributed DHP event sites |

---

## 2. Data sources

All satellite and auxiliary data are retrieved from **STAC** (SpatioTemporal Asset
Catalog) compliant catalogs, providing a standardized, interoperable interface for
discovering and retrieving multi-sensor EO data.

| Source | Product | Provider / Endpoint | Native res. |
|---|---|---|---|
| Sentinel-2 L2A | 13 bands + SCL | CDSE — `https://stac.dataspace.copernicus.eu/v1/` | 10 / 20 / 60 m |
| Sentinel-1 RTC | VV, VH backscatter | Microsoft Planetary Computer — `https://planetarycomputer.microsoft.com/api/stac/v1` | 10 m |
| Copernicus DEM GLO-30 | Elevation | CDSE | 30 m |
| ESA WorldCover 2020 | Land cover | Planetary Computer | 10 m |

**Why Planetary Computer for S1 RTC.** Sentinel-1 **RTC** (Radiometrically Terrain
Corrected) products are not available via CDSE, which only distributes GRD and SLC.
RTC applies geometric corrections based on a DEM, ensuring pixel-level alignment with
topography — without it, GRD-only products showed geometric offsets of up to ~100 m in
mountainous regions, making fusion with Sentinel-2 infeasible. ESA WorldCover is
likewise retrieved from Planetary Computer, as it is not yet fully cataloged in CDSE.

The retrieval workflow is **modular**: once Sentinel-1 RTC and ESA WorldCover become
available in the CDSE STAC, the pipeline can switch endpoints by changing a single
configuration line, with no changes to the processing code.

---

## 3. Spatial and temporal definition

### 3.1 Spatial extent
For each event, a spatial footprint is derived from the event centroid, with a
**10 × 10 km bounding box**. Cubes are produced at **10 m** resolution, i.e. a
**1000 × 1000** pixel grid. Footprint generation adapts core functions from the
[**Cubo**](https://github.com/ESDS-Leipzig/cubo) library (Montero et al., 2024):

- `central_pixel_bbox` — defines a UTM bounding box around the centroid for a given
  buffer distance;
- `compute_distance_to_center` — distance of each pixel from the cube centre;
- `harmonize_to_pixels` / `process_bounding_box` — align and enforce pixel consistency
  across datasets with different native resolutions.

The CRS is the **UTM zone derived from the centroid longitude** (WGS84 datum). UTM
bounding boxes are transformed back to geographic coordinates to build the polygons
used for STAC queries.

### 3.2 Temporal extent
The temporal window spans **one year before** to **one year after** the event, i.e. a
**two-year** series, enabling analysis of pre-/post-event dynamics, anomaly detection
and recovery assessment. Static layers use fixed date ranges independent of the event:

- **Copernicus DEM:** 2010-01-01 – 2024-12-31
- **ESA WorldCover:** 2019-01-01 – 2020-12-31 (WorldCover 2020 product)

---

## 4. Processing pipeline

Processing is orchestrated by a single script (`src/processor/pipeline_orchestrator.py`)
driven by a YAML configuration file. The stages run sequentially and can each be
enabled or disabled independently.

| # | Stage | Description |
|---|---|---|
| 1 | **Sentinel-2 L2A** | Multispectral time-series cube within `event_date ± window` |
| 2 | **Cloud mask** (optional) | SEnSeIv2 deep-learning model applied to the S2 cube (~30 min/location) |
| 3 | **Sentinel-1 RTC** | SAR backscatter cube, same spatial/temporal extent as S2 |
| 4 | **Copernicus DEM** | Elevation cube (static layer, fixed date range) |
| 5 | **ESA WorldCover** | Land-cover cube (static layer, 2020 product) |
| 6 | **Merge** (optional) | Combines all source cubes, rechunks, encodes bands to uint16, adds metadata |

### 4.1 Ingestion and harmonization
STAC items are queried with **`pystac-client`** by bounding box and temporal window,
filtered by collection and spatial extent, and signed when required (Planetary
Computer). Items are read with **`stackstac`**, which converts raster assets into
`xarray.DataArray`s. Each collection is stacked independently along its native time
dimension, and multiple acquisitions on the same date are combined with
`stackstac.mosaic`. Spatial resampling uses **nearest-neighbor** interpolation to
harmonize all datasets to the common 10 m grid.

Per-collection datasets are then converted to `xarray.Dataset`s, with time dimensions
renamed to keep them unique (`time_sentinel_2_l2a`, `time_sentinel_1_rtc`, …), and
conflicting coordinates dropped. The collections are merged into a single cube with
`xarray.merge(..., compat="override")`, preserving separate time axes per collection
while sharing consistent spatial coordinates (`x`, `y`) and standardized attributes.

### 4.2 Cloud masking (SEnSeIv2)
Cloud masking uses the **SEnSeIv2** model (Francis, 2024), implementing the
**SegFormer-B2** architecture (Xie et al., 2021), released under GPL-3.0
([GitHub](https://github.com/aliFrancis/SEnSeIv2)). SEnSeIv2 is **sensor-independent**,
producing consistent masks across optical sensors, and distinguishes four classes:

| Value | Class |
|---|---|
| 0 | Unoccluded (clear) |
| 1 | Thick cloud |
| 2 | Thin cloud |
| 3 | Shadow |

Inference uses a **stride of 512 px** and 4 output classes. Model weights and
configuration ship in the repository under `SEnSeIv2_config/`
(`config.yaml`, `weights.pt`, `senseiv2-medium.yaml`). Masking can run on CPU or CUDA
and adds ~30 min per location.

### 4.3 Skip-existing logic
A `skip_existing` mechanism checks each output directory before processing and skips
locations whose outputs already exist. This enables resuming interrupted runs, adding
new locations without reprocessing, and selective reprocessing by deleting specific
stage outputs.

### 4.4 Compute environment
Processing runs on the **CREODIAS** OpenStack cloud, co-located with the CDSE EO
endpoints for low-latency access. Cubes were generated on an `eo2a.4xlarge` VM
(32 vCPU, 128 GB RAM, 512 GB SSD) with an additional 2 TB SSD workspace.
**Dask** provides parallel computation across locations and long temporal windows;
temporary objects are periodically garbage-collected to manage memory.

---

## 5. Software and libraries

| Library | Role |
|---|---|
| [`stackstac`](https://stackstac.readthedocs.io/) | Turn STAC items into `xarray` arrays; mosaicking |
| [`cubo`](https://github.com/ESDS-Leipzig/cubo) | Footprint / bounding-box and pixel-grid harmonization |
| [`pystac-client`](https://pystac-client.readthedocs.io/) | STAC querying |
| [`xarray`](https://xarray.dev/) | N-D labelled arrays; cube assembly and I/O |
| [`dask`](https://www.dask.org/) | Parallel, out-of-core computation |
| [`zarr`](https://zarr.dev/) | Chunked, compressed cloud-native storage |
| [`senseiv2`](https://github.com/aliFrancis/SEnSeIv2) | Cloud masking (SegFormer-B2) |
| [`lexcube`](https://github.com/msoechting/lexcube) | Interactive 3D cube visualization |
| [`fsspec`](https://filesystem-spec.readthedocs.io/) | Transparent access to cloud (S3) Zarr stores |

Dependencies are pinned and managed with **`uv`** (`pyproject.toml` / `uv.lock`); a
`Dockerfile` is provided for fully containerized, reproducible runs.

---

## 6. Cube contents

### 6.1 Data variables
Each merged cube contains the following variables. The **dtype below is the actual
on-disk (Zarr) encoding**. Most layers are stored as **`uint16`** (integers); only the
SAR backscatter and the DEM are floating point.

| Name | Dtype (stored) | Dimensions | Description |
|---|---|---|---|
| `B01` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Aerosol (443 nm) |
| `B02` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Blue (490 nm) |
| `B03` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Green (560 nm) |
| `B04` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Red (665 nm) |
| `B05` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Red edge (705 nm) |
| `B06` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Red edge (740 nm) |
| `B07` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Red edge (783 nm) |
| `B08` | uint16 | (time_sentinel_2_l2a, y, x) | S2 NIR (842 nm) |
| `B8A` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Narrow NIR (865 nm) |
| `B09` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Water vapour (945 nm) |
| `B11` | uint16 | (time_sentinel_2_l2a, y, x) | S2 SWIR 1 (1610 nm) |
| `B12` | uint16 | (time_sentinel_2_l2a, y, x) | S2 SWIR 2 (2190 nm) |
| `SCL` | uint16 | (time_sentinel_2_l2a, y, x) | S2 Scene Classification Layer (12 classes) |
| `cloud_mask` | uint16 | (time_sentinel_2_l2a, y, x) | SEnSeIv2 cloud mask (4 classes) |
| `ESA_LC` | uint16 | (time_esa_worldcover, y, x) | ESA WorldCover 2020 land-cover class |
| `vv` | float64 | (time_sentinel_1_rtc, y, x) | S1 RTC backscatter, VV polarization |
| `vh` | float64 | (time_sentinel_1_rtc, y, x) | S1 RTC backscatter, VH polarization |
| `COP_DEM` | float64 | (time_cop_dem_glo_30_dged_cog, y, x) | Copernicus DEM GLO-30 elevation (m a.s.l.) |

> **Dtypes.** All Sentinel-2 bands and the discrete layers (`SCL`, `cloud_mask`,
> `ESA_LC`) are stored as **`uint16`** with a fill value of `32767`; only `vv`, `vh`
> (SAR) and `COP_DEM` (elevation) are **`float64`** (fill `NaN`).
>
> **Reading nuance.** By default `xarray.open_zarr` applies CF masking
> (`_FillValue → NaN`), which promotes the `uint16` layers to **`float32`** on read (so
> `ds.B04.dtype` shows `float32`). To get the raw integer values, open with
> `xr.open_zarr(store, mask_and_scale=False)`.
>
> **Naming.** The stored elevation/land-cover variables are `COP_DEM` and `ESA_LC`.
> Sentinel-2 native resolutions are 10 m (B02–B04, B08), 20 m (B01, B05–B07, B8A, B11,
> B12, SCL) and 60 m (B09), all resampled to 10 m in the cube.

### 6.2 Coordinates

| Coordinate | Dtype | Description |
|---|---|---|
| `time_sentinel_2_l2a` | datetime64[ns] | S2 acquisition times |
| `time_sentinel_1_rtc` | datetime64[ns] | S1 RTC acquisition times |
| `time_cop_dem_glo_30_dged_cog` | datetime64[ns] | DEM reference time (static) |
| `time_esa_worldcover` | datetime64[ns] | WorldCover reference time (static) |
| `x`, `y` | float64 | Projected coordinates (metres, cube EPSG) |
| `orbit_state` | str | Sentinel-1 orbit direction (ascending / descending) |

### 6.3 Class legends

**Cloud mask** (`cloud_mask`): `0` Unoccluded · `1` Thick cloud · `2` Thin cloud · `3` Shadow.

**Sentinel-2 SCL:** `0` No-data · `1` Saturated/defective · `2` Dark area · `3` Cloud
shadow · `4` Vegetation · `5` Not vegetated · `6` Water · `7` Unclassified ·
`8` Cloud (medium prob.) · `9` Cloud (high prob.) · `10` Thin cirrus · `11` Snow.

**ESA WorldCover** (`ESA_LC`): `10` Tree cover · `20` Shrubland · `30` Grassland ·
`40` Cropland · `50` Built-up · `60` Bare/sparse vegetation · `70` Snow/Ice ·
`80` Water · `90` Wetland · `95` Mangroves · `100` Moss/Lichen.

### 6.4 Metadata attributes
Each cube is self-describing, storing a rich attribute set aligned with FAIR, Zarr and
STAC conventions. Representative attributes (example values from one cube):

| Attribute | Description | Example |
|---|---|---|
| `project` | Research project | ARCEME – Adaptation and Resilience to Climate Extremes and Multi-hazard Events |
| `data_cubes_producer` | Producer | CloudFerro S.A. |
| `collections` | Integrated collections | CDSE: sentinel-2-l2a, cop-dem-glo-30-dged-cog; Planetary Computer: sentinel-1-rtc, esa-worldcover |
| `stac_endpoints` | STAC endpoints used | CDSE + Planetary Computer URLs |
| `epsg` | Cube CRS (UTM/WGS84) | 32737 |
| `central_x`, `central_y` | Centroid (projected, m) | 456960.0, 8363760.0 |
| `edge_size_m` / `edge_size_px` | Tile size | 10000 / 1000 |
| `pixel_resolution_meters` / `resolution` | Pixel size | 10 |
| `tile_size_px` | Grid dimensions | 1000x1000 |
| `resampling_method` | Resampling | nearest neighbor |
| `dtype_conversion` | On-disk encoding | uint16 for S2 bands, SCL, cloud_mask, ESA_LC |
| `fill_value_policy` | Fill values | float=NaN, int=32767 |
| `merge_chunking` | Zarr chunking | time=25, x=500, y=500 |
| `cloud_mask_algorithm` | Cloud-mask model | SEnSeIv2/SegFormerB2 |
| `cloud_mask_description` | Cloud-mask legend | 0 Unoccluded, 1 Thick cloud, 2 Thin cloud, 3 Shadow |
| `cloud_mask_stride_size` | Inference stride | 512 |
| `cloud_mask_citation` | Reference | https://doi.org/10.1109/TGRS.2024.3391625 |
| `land_cover` | Land-cover product | ESA WorldCover 2020 at 10 m |
| `land_cover_citation` | Reference | https://doi.org/10.5281/zenodo.5571936 |
| `land_cover_legend` | Class codes | 10 Tree cover … 100 Moss/Lichen |
| `Sentinel_2_SCL_description` | SCL legend | 0 no_data … 11 snow |
| `temporal_window` | Time window | event_date −12 months to +12 months |
| `static_dates_copdem` | DEM date range | 2010-01-01 to 2024-12-31 |
| `static_dates_esalc` | WorldCover date range | 2019-01-01 to 2020-12-31 |
| `time_coverage_start` / `time_coverage_end` | Series coverage | 2014-01-01 / 2016-01-01 |
| `time_axis` | Temporal dimensions | the four `time_*` axes |
| `location_source` | Source collection | ARCEME-DC-DHP-EMDAT |
| `missing_datasets` | Sources missing for this location | none |

---

## 7. Storage structure and compression

Cubes are stored in **Zarr format (version 2)** — cloud-optimized storage for
multidimensional arrays. Each variable is a separate array with its own metadata
(`.zattrs`) and layout (`.zarray`); all arrays share the `(y, x)` spatial coordinates
and their respective time axis. Data are stored row-major (NumPy/Dask compatible) and
compressed with **Blosc** (LZ4), balancing size against high-throughput reads. Default
merge chunking is **25 time steps × 500 × 500 px**. This structure supports lazy
loading, partial reads and parallelized access without loading whole datasets into
memory.

---

## 8. Technical validation

Every cube passes an automated validation workflow:

1. **Metadata integrity** — presence/correctness of essential attributes (EPSG,
   temporal coverage, coordinate dimensions, variable names); consistency of
   `.zattrs` / `.zmetadata` across cubes, compliant with FAIR and STAC.
2. **Completeness** — the number of time steps matches available EO acquisitions in
   the window; no missing tiles or corrupted temporal slices.
3. **Zarr structure** — hierarchical layout, `_ARRAY_DIMENSIONS`, dtype and compressor
   inspected with `xarray`/`zarr`; chunking/compression validated for parallel I/O.
4. **Parallel read** — Dask confirms cubes open, read and process without corruption.
5. **Visual cross-check** — random tiles/time slices rendered with `matplotlib`,
   `lexcube` and `xarray.plot` to confirm spatial alignment and radiometric coherence
   across all four sources.

---

## 9. Dataset availability and access

The data cubes are publicly hosted on CloudFerro / CREODIAS S3-compatible object
storage, organized as three collections:

| Collection | S3 endpoint |
|---|---|
| `ARCEME-DC-DHP-WOCAT` | https://s3.waw4-1.cloudferro.com/swift/v1/ARCEME-DC-DHP-WOCAT/ |
| `ARCEME-DC-DHP-EMDAT` | https://s3.waw4-1.cloudferro.com/swift/v1/ARCEME-DC-DHP-EMDAT/ |
| `ARCEME-DC-DHP-GLOBAL` | https://s3.waw4-1.cloudferro.com/swift/v1/ARCEME-DC-DHP-GLOBAL/ |

**Naming convention.** Each merged cube is a named Zarr archive:
`DC__<location>__<start_date>__<end_date>.zarr`, e.g.

- EMDAT: `DC__2015-0011-MOZ__2014-01-01__2016-01-01.zarr`
- WOCAT: `DC__wocat_1007_dhp_28028__2017-10-27__2019-10-27.zarr`
- GLOBAL: `DC__10051_dhp__2015-01-11__2017-01-11.zarr`

### 9.1 Coverage

The dataset comprises **601 cubes** across the three collections. Each cube covers a
10 × 10 km footprint and holds a two-year time series; the extents below are the union
of per-cube footprints and the range of event windows.

| Collection | Cubes | Longitude | Latitude | Temporal span |
|---|---|---|---|---|
| WOCAT | 21 | −20.5° … 33.5° | 37.6° … 63.9° | 2017-08 … 2024-11 |
| GLOBAL | 226 | −114.0° … 149.6° | −38.6° … 55.0° | 2015-01 … 2024-11 |
| EMDAT | 354 | −112.5° … 150.7° | −42.4° … 53.8° | 2014-01 … 2024-12 |
| **Total** | **601** | near-global | near-global | 2014 … 2024 |

WOCAT is focused on Europe and North Africa; GLOBAL and EMDAT are near-global.

### 9.2 Reading a cube

```python
import xarray as xr

# Directly from the public S3 bucket (read-only)
url = ("https://s3.waw4-1.cloudferro.com/swift/v1/"
       "ARCEME-DC-DHP-EMDAT/DC__2015-0011-MOZ__2014-01-01__2016-01-01.zarr")
ds = xr.open_zarr(url, consolidated=True)

# ...or a local copy
# ds = xr.open_zarr("DC__2015-0011-MOZ__2014-01-01__2016-01-01.zarr", consolidated=True)

print(ds)
```

### 9.3 Example analyses

```python
# True-colour band and SAR polarization
ds.B04.isel(time_sentinel_2_l2a=0).plot()   # Red
ds.vv.isel(time_sentinel_1_rtc=0).plot()     # S1 VV

# NDVI
ndvi = (ds.B08 - ds.B04) / (ds.B08 + ds.B04)
ndvi.isel(time_sentinel_2_l2a=0).plot()

# Keep only clear pixels using the SEnSeIv2 cloud mask (0 = clear)
clear = ds.B04.where(ds.cloud_mask.isel(time_sentinel_2_l2a=0) == 0)
```

Interactive 3D exploration is available via `lexcube` (see the `lexcube/previews/`
tooling for static space-time-cube renders).

### 9.4 STAC discovery

The dataset is registered in the **ESA Open Science Data Catalogue** — the ARCEME STAC
collection is browsable at
https://opensciencedata.esa.int/stac-browser/#/projects/arceme/collection.json .

STAC **collections and items** for each cube collection are also generated in this
repository under `stac-generation/` (one self-contained catalog per collection:
`stac-wocat/`, `stac-global/`, `stac-emdat/`, each with a `collection.json` and one
item per cube). Items carry the [Datacube extension](https://github.com/stac-extensions/datacube)
(`cube:dimensions`, `cube:variables`), a WGS84 geometry/bbox, the temporal window and a
`data` asset pointing at the cube's Zarr URL — so cubes can be discovered and filtered
by space, time and variable before download. Regenerate them with:

```bash
cd stac-generation
python generate_stac.py --config stac_config_wocat.yaml  --output ./stac-wocat
python generate_stac.py --config stac_config_global.yaml --output ./stac-global
python generate_stac.py --config stac_config_emdat.yaml  --output ./stac-emdat
```

---

## 10. Code repository

**https://github.com/ARCEME/datacubes-processor** (mirror of the internal GitLab).

| Path | Description |
|---|---|
| `src/processor/pipeline_orchestrator.py` | Main entry point |
| `src/processor/pipeline_config.yaml` | Master configuration |
| `src/processor/cloud_mask.py` | Cloud-masking module (SEnSeIv2) |
| `src/processor/utils.py` | Shared utilities |
| `SEnSeIv2_config/` | Cloud-mask model config + weights |
| `data/` | Input CSV location records |
| `stac-generation/` | STAC collection/item generators |
| `tutorials/` | Jupyter notebook tutorials |
| `Dockerfile`, `pyproject.toml`, `uv.lock` | Reproducible environment |

### 10.1 Environment and run

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd data-cubes-arceme
uv sync
uv run python src/processor/pipeline_orchestrator.py \
    --config src/processor/pipeline_config.yaml
```

### 10.2 Docker

```bash
docker build -t arceme-pipeline:latest .
docker run --rm -it \
  --env-file .env \
  -e PIPELINE_CONFIG=src/processor/pipeline_config.yaml \
  -v /ARCEME-MERGE:/ARCEME-MERGE \
  arceme-pipeline:latest
```

### 10.3 Credentials (`.env`)
The pipeline reads imagery from S3 and needs **S3 credentials** (not a website login).
Create a `.env` in the repo root with `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
(CDSE **S3** keys from
https://eodata-s3keysmanager.dataspace.copernicus.eu/panel/s3-credentials) and
`AWS_S3_ENDPOINT=eodata.dataspace.copernicus.eu` (CDSE) or `eodata.cloudferro.com`
(CREODIAS). See the *Environment Variables* section of the main `README.md` for the
full template.

### 10.4 Tutorials
- `tutorials/01_extracting_new_datacubes.ipynb` — prepare a locations CSV, configure and
  run the pipeline, monitor outputs.
- `tutorials/02_accessing_cubes_footprint_analysis.ipynb` — open a merged cube, visualize
  S2 RGB over time, apply the cloud mask, compute NDVI anomalies, overlay S1 SAR.

---

## 11. Known limitations and caveats

- **Sentinel-1 single-polarisation acquisitions.** Some early S1 acquisitions (notably
  2014–2016) are single-polarisation (VV only). For those dates the `vh` layer is
  absent and stored as `NaN`, while `vv` is present. Check for all-NaN `vh` slices
  before dual-pol analysis.
- **Variable number of time steps.** The count of Sentinel-2 and Sentinel-1 time steps
  differs per cube (a function of revisit, latitude and data availability in the event
  window). Never assume a fixed length along `time_sentinel_2_l2a` /
  `time_sentinel_1_rtc`; read the coordinate.
- **Occasionally missing sources.** If a source could not be retrieved for a location,
  it is recorded in the cube's `missing_datasets` attribute (`none` when complete).
  Inspect it before assuming a layer is present.
- **Cloud-mask limitations.** The SEnSeIv2 mask is a deep-learning product and is not
  perfect: thin cirrus, bright surfaces (snow, sand, salt pans) and cloud edges can be
  mis-classified. Combine with the Sentinel-2 `SCL` layer where reliability is critical.
- **Static layers as single-step "time" axes.** `COP_DEM` and `ESA_LC` are static, but
  are stored along their own length-1 time dimensions
  (`time_cop_dem_glo_30_dged_cog`, `time_esa_worldcover`) for schema uniformity — index
  position `0`.
- **Decoded dtype.** Integer layers (`uint16`) are promoted to `float32` (with `NaN`)
  by `xarray`'s default CF masking on read; use `mask_and_scale=False` for raw integers
  (see §6.1).
- **Per-cube CRS.** Each cube uses the UTM zone of its own centroid, so the `epsg`,
  `x` and `y` values differ between cubes; reproject before combining cubes from
  different zones.

---

## 12. Contact and support

- **Producer:** CloudFerro S.A. — https://cloudferro.com
- **Technical contact:** Marcin Kluczek — `mkluczek@cloudferro.com`
- **Issues / questions about the pipeline or cubes:** open an issue at
  https://github.com/ARCEME/datacubes-processor/issues

---

## 13. References

- Francis, A. (2024). *SEnSeIv2: Sensor-independent cloud masking.* IEEE TGRS.
  https://doi.org/10.1109/TGRS.2024.3391625 · https://github.com/aliFrancis/SEnSeIv2
- Xie, E. et al. (2021). *SegFormer: Simple and Efficient Design for Semantic
  Segmentation with Transformers.* NeurIPS.
- Montero, D. et al. (2024). *Cubo: On-demand EO minicubes.* https://github.com/ESDS-Leipzig/cubo
- ESA WorldCover 2020. https://doi.org/10.5281/zenodo.5571936
- STAC — SpatioTemporal Asset Catalog specification. https://stacspec.org/

---

