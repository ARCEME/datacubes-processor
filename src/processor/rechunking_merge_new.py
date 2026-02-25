import os
import re
import glob
import xarray as xr
from collections import defaultdict
import zarr

# ─────────────────────────────────────────────────────────────
# 1. Katalogi źródłowe
# ─────────────────────────────────────────────────────────────

input_dirs = [
    '/ARCEME-MERGE/S2L2A_CLOUDMASK/',
    '/ARCEMECUBES/NEW-CUBES-MELANIE/COPDEM/',
    '/ARCEMECUBES/NEW-CUBES-MELANIE/S1RTC/',
    '/ARCEMECUBES/NEW-CUBES-MELANIE/ESALC/',
]

output_dir = "/ARCEME-MERGE/MELANIE-CUBES-TEST/"
os.makedirs(output_dir, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 2. Funkcja ekstrakcji prefix i daty
# ─────────────────────────────────────────────────────────────

def extract_prefix_and_date(path):
    fname = os.path.basename(path)
    pattern = r"^(DC__\d+_[A-Za-z]+)__([0-9]{4}-[0-9]{2}-[0-9]{2}__[0-9]{4}-[0-9]{2}-[0-9]{2})"
    m = re.match(pattern, fname)
    if not m:
        raise ValueError(f"Cannot parse: {fname}")
    return m.group(1), m.group(2)

# ─────────────────────────────────────────────────────────────
# 3. Zebranie plików wg prefixu i źródła
# ─────────────────────────────────────────────────────────────

files_by_prefix = defaultdict(lambda: {
    "S2L2A": [],
    "S1RTC": [],
    "COPDEM": [],
    "ESALC": []
})

for d in input_dirs:
    for path in glob.glob(os.path.join(d, "DC__*.zarr")):
        prefix, date_range = extract_prefix_and_date(path)

        if "S2L2A_CLOUDMASK" in d:
            files_by_prefix[prefix]["S2L2A"].append((path, date_range))
        elif "S1RTC" in d:
            files_by_prefix[prefix]["S1RTC"].append((path, date_range))
        elif "COPDEM" in d:
            files_by_prefix[prefix]["COPDEM"].append((path, date_range))
        elif "ESALC" in d:
            files_by_prefix[prefix]["ESALC"].append((path, date_range))

# ─────────────────────────────────────────────────────────────
# 4. Przygotowanie grup do scalenia
# ─────────────────────────────────────────────────────────────

merge_groups = {}
final_prefix_name = {}

for prefix, groups in files_by_prefix.items():

    s2 = groups["S2L2A"]
    s1 = groups["S1RTC"]

    # mapy data -> plik
    s2_map = {d: p for p, d in s2}
    s1_map = {d: p for p, d in s1}

    wspolne_dat = sorted(set(s2_map.keys()) & set(s1_map.keys()))

    if not wspolne_dat:
        print(f"WARNING: brak wspólnej daty S2L2A/S1RTC dla {prefix}")
        continue

    date_range = wspolne_dat[0]  # weź pierwszą wspólną datę

    final_files = [
        s2_map[date_range],
        s1_map[date_range]
    ]

    if groups["COPDEM"]:
        final_files.append(groups["COPDEM"][0][0])
    if groups["ESALC"]:
        final_files.append(groups["ESALC"][0][0])

    merge_groups[prefix] = final_files
    final_prefix_name[prefix] = f"{prefix}__{date_range}"

# ─────────────────────────────────────────────────────────────
# 5. Zmienne do konwersji
# ─────────────────────────────────────────────────────────────

vars_to_uint16 = [
    'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08',
    'B8A', 'B09', 'B11', 'B12', 'SCL', 'cloud_mask', 'ESA_LC'
]

# ─────────────────────────────────────────────────────────────
# 6. Merge + Chunking + Encoding + Zapis
# ─────────────────────────────────────────────────────────────

for prefix, paths in merge_groups.items():

    final_prefix = final_prefix_name[prefix]

    print(f"\nScalam {final_prefix}, liczba kostek: {len(paths)}")
    cubes = [xr.open_zarr(p, consolidated=True) for p in paths]

    merged = xr.merge(cubes, compat='override', join='outer')

    # konwersja typów
    for var in vars_to_uint16:
        if var in merged:
            merged[var] = merged[var].astype("uint16")

    # ─── CHUNKING: wszystkie osie czasu -> 25, przestrzenne -> 500 ───
    chunk_dict = {}
    for d in merged.dims:
        if d.lower().startswith("time"):
            chunk_dict[d] = 25
        elif d in ["x", "longitude"]:
            chunk_dict[d] = 500
        elif d in ["y", "latitude"]:
            chunk_dict[d] = 500

    print(f"Rechunking: {chunk_dict}")
    merged = merged.chunk(chunk_dict)

    # ─── Atrybuty minimalne
    merged.attrs.update(
        project="ARCEME - Adaptation and Resilience to Climate Extremes and Multi-hazard Events",
        pixel_resolution_meters="10",
        resampling_method="nearest neighbor",
        size_px="height: 1000 px, width: 1000 px",
        stac_endpoints="CDSE: https://stac.dataspace.copernicus.eu/v1/ Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1",
        collections="CDSE: sentinel-2-l2a, copernicus-dem-30; Planetary Computer: sentinel-1-rtc, esa-worldcover-2020",
        time_axis="time_sentinel_2_l2a, time_cop_dem_glo_30_dged_cog, time_sentinel_1_rtc, time_esa_worldcover",
        land_cover="ESA World Cover 2020 map at 10 m resolution",
        land_cover_legend="10 - Tree cover, 20 - Shrubland, 30 - Grassland,  40 - Cropland, 50 - Built-up, 60 - Bare /sparse vegetation, 70 - Snow and Ice, 80 - Permanent water bodies, 90 - Herbaceous wetland, 95 - Mangroves, 100 - Moss and lichen",
        land_cover_citation="https://doi.org/10.5281/zenodo.5571936",
        cloud_mask_description="0: Unoccluded, 1: Thick cloud, 2: Thin cloud, 3: Shadow",
        cloud_mask_algorithm="SEnSeIv2/SegFormerB2",
        cloud_mask_stride_size="512",
        cloud_mask_citation="https://www.doi.org/10.1109/TGRS.2024.3391625",
        Sentinel_2_SCL_description="0: no_data, 1: saturated_or_defective, 2: dark_area_pixels,  3: cloud_shadows, 4: vegetation, 5: not_vegetated,  6: water, 7: unclassified,  8: cloud_medium_probability, 9: cloud_high_probability, 10: thin_cirrus, 11: snow",
        data_cubes_producer="CloudFerrro S.A."
    )

    # ─── Encoding dla Zarr
    encoding = {}
    compressor = zarr.Blosc(cname='zstd', clevel=3, shuffle=1)

    def flatten_chunks(chunks):
        if chunks is None:
            return None
        return tuple(int(c) for dim in chunks for c in dim)

    for var in merged.data_vars:
        encoding[var] = {
            'compressor': compressor,
            'chunks': flatten_chunks(merged[var].chunks)
        }

    for coord in merged.coords:
        if coord not in encoding:
            encoding[coord] = {
                'compressor': None,
                'chunks': flatten_chunks(merged[coord].chunks)
            }

    output_path = os.path.join(output_dir, f"{final_prefix}.zarr")
    print(f"Zapisuję do {output_path}...")

    merged.to_zarr(
        output_path,
        mode='w',
        encoding=encoding,
        consolidated=True
    )

    print(f"Zapisano {output_path}")
    print(f"Dimensions: {dict(merged.dims)}")
    print(f"Chunks: {dict((d, merged[d].chunks) for d in merged.dims)}")
    print("-" * 60)

