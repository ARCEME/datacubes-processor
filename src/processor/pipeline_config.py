# Pipeline configuration for data cube orchestration.
# Adjust paths and settings as needed.

PIPELINE_CONFIG = {
    # Input table with locations and dates.
    "locations_csv": "/home/eouser/datacubes/arceme-datacubes/arceme-datacubes/datasets/dhp_global_subselection_new_melanie.csv",
    "skip_existing": True,
    # Spatial settings.
    "edge_size": 10000,
    "units": "m",
    "resolution": 10,
    # Time settings for S2/S1 relative to event date.
    "increment_months": 12,
    "decrement_months": 12,
    # Sources and collections.
    "sources": {
        "s2": "cdse",
        "s1": "planetary",
        "copdem": "cdse",
        "esalc": "planetary",
    },
    "collections": {
        "s2": ["sentinel-2-l2a"],
        "s1": ["sentinel-1-rtc"],
        "copdem": ["cop-dem-glo-30-dged-cog"],
        "esalc": ["esa-worldcover"],
    },
    # Fixed date ranges for static layers.
    "static_date_ranges": {
        "copdem": {"start": "2010-01-01", "end": "2024-12-31"},
        "esalc": {"start": "2019-01-01", "end": "2020-12-31"},
    },
    # Output directories for each stage.
    "output_dirs": {
        "s2": "/ARCEMECUBES/NEW-CUBES-MELANIE/S2L2A/",
        "s2_cloudmask": "/ARCEME-MERGE/S2L2A_CLOUDMASK/",
        "s1": "/ARCEMECUBES/NEW-CUBES-MELANIE/S1RTC/",
        "copdem": "/ARCEMECUBES/NEW-CUBES-MELANIE/COPDEM/",
        "esalc": "/ARCEMECUBES/NEW-CUBES-MELANIE/ESALC/",
        "merged": "/ARCEME-MERGE/",
    },
    # Optional filtering of S2 items to those containing the AOI polygon.
    "s2_filter_contains_bbox": False,
    # Cloud mask settings.
    "cloud_mask": {
        "enabled": True,
        # Cloud mask uses senseiv2 model and runs in CPU by default.
        # Adjust the model or device in cloud_mask.py if needed.
    },
    # Merge settings.
    "merge": {
        "enabled": True,
        "chunk_time": 25,
        "chunk_x": 500,
        "chunk_y": 500,
        "prefer_latest_aux": True,
        "vars_to_uint16": [
            "B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08",
            "B8A", "B09", "B11", "B12", "SCL", "cloud_mask", "ESA_LC"
        ],
        "attrs": {
            "project": "ARCEME - Adaptation and Resilience to Climate Extremes and Multi-hazard Events",
            "pixel_resolution_meters": "10",
            "resampling_method": "nearest neighbor",
            "size_px": "height: 1000 px, width: 1000 px",
            "stac_endpoints": "CDSE: https://stac.dataspace.copernicus.eu/v1/ Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1",
            "collections": "CDSE: sentinel-2-l2a, copernicus-dem-30; Planetary Computer: sentinel-1-rtc, esa-worldcover-2020",
            "time_axis": "time_sentinel_2_l2a, time_cop_dem_glo_30_dged_cog, time_sentinel_1_rtc, time_esa_worldcover",
            "land_cover": "ESA World Cover 2020 map at 10 m resolution",
            "land_cover_legend": "10 - Tree cover, 20 - Shrubland, 30 - Grassland,  40 - Cropland, 50 - Built-up, 60 - Bare /sparse vegetation, 70 - Snow and Ice, 80 - Permanent water bodies, 90 - Herbaceous wetland, 95 - Mangroves, 100 - Moss and lichen",
            "land_cover_citation": "https://doi.org/10.5281/zenodo.5571936",
            "cloud_mask_description": "0: Unoccluded, 1: Thick cloud, 2: Thin cloud, 3: Shadow",
            "cloud_mask_algorithm": "SEnSeIv2/SegFormerB2",
            "cloud_mask_stride_size": "512",
            "cloud_mask_citation": "https://www.doi.org/10.1109/TGRS.2024.3391625",
            "Sentinel_2_SCL_description": "0: no_data, 1: saturated_or_defective, 2: dark_area_pixels,  3: cloud_shadows, 4: vegetation, 5: not_vegetated,  6: water, 7: unclassified,  8: cloud_medium_probability, 9: cloud_high_probability, 10: thin_cirrus, 11: snow",
            "data_cubes_producer": "CloudFerrro S.A.",
        },
    },
}
