# import os
# import re
# import glob
# import xarray as xr
# from collections import defaultdict

# # Katalogi źródłowe
# input_dirs = [
#     "/ARCEMECUBES/PRODUCTION_CUBES/CLOUDFERRO/S2L2A_CLOUDMASK",
#     "/ARCEMECUBES/PRODUCTION_CUBES/CLOUDFERRO/COPDEM",
#     "/ARCEMECUBES/PRODUCTION_CUBES/PLANETARY/S1RTC",
#     "/ARCEMECUBES/PRODUCTION_CUBES/PLANETARY/ESALC",
# ]

# # Katalog wynikowy
# output_dir = "/ARCEMECUBES/PRODUCTION_CUBES/COMBINED"
# os.makedirs(output_dir, exist_ok=True)

# # Funkcja do wyciągania prefiksu
# def extract_prefix(path):
#     fname = os.path.basename(path)
#     match = re.match(r"(DC__[^_]+)", fname)
#     if not match:
#         raise ValueError(f"Nie udało się znaleźć prefiksu w {fname}")
#     return match.group(1)

# vars_to_uint16 = [
#     'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08',
#     'B8A', 'B09', 'B11', 'B12', 'SCL', 'cloud_mask', 'ESA_LC'
# ]


# # Grupowanie plików po prefiksie
# groups = defaultdict(list)
# for d in input_dirs:
#     for path in glob.glob(os.path.join(d, "DC__*.zarr")):
#         prefix = extract_prefix(path)
#         groups[prefix].append(path)


# # Iteracja po grupach i scalanie
# for prefix, paths in groups.items():
#     print(f"Scalam {prefix}, liczba kostek: {len(paths)}")

#     cubes = [xr.open_zarr(p) for p in paths]
#     merged = xr.merge(cubes)

#     # Konwersja typów
#     for var in vars_to_uint16:
#         if var in merged:
#             merged[var] = merged[var].astype('uint16')


#     merged.attrs.update(
#         project="ARCEME - Adaptation and Resilience to Climate Extremes and Multi-hazard Events",
#         pixel_resolution_meters="10",
#         resampling_method="nearest neighbor",
#         size_px="height: 1000 px, width: 1000 px",
#         stac_endpoints="CDSE: https://stac.dataspace.copernicus.eu/v1/ Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1",
#         collections="CDSE: sentinel-2-l2a, copernicus-dem-30; Planetary Computer: sentinel-1-rtc, esa-worldcover-2020",
#         time_axis="time_sentinel_2_l2a, time_cop_dem_glo_30_dged_cog, time_sentinel_1_rtc, time_esa_worldcover",
#         land_cover="ESA World Cover 2020 map at 10 m resolution",
#         land_cover_legend="10 - Tree cover, 20 - Shrubland, 30 - Grassland,  40 - Cropland, 50 - Built-up, 60 - Bare /sparse vegetation, 70 - Snow and Ice, 80 - Permanent water bodies, 90 - Herbaceous wetland, 95 - Mangroves, 100 - Moss and lichen",
#         land_cover_citation="https://doi.org/10.5281/zenodo.5571936",
#         cloud_mask_description="0: Unoccluded, 1: Thick cloud, 2: Thin cloud, 3: Shadow",
#         cloud_mask_algorithm="SEnSeIv2/SegFormerB2",
#         cloud_mask_stride_size="512",
#         cloud_mask_citation="https://www.doi.org/10.1109/TGRS.2024.3391625",
#         Sentinel_2_SCL_description="0: no_data, 1: saturated_or_defective, 2: dark_area_pixels,  3: cloud_shadows, 4: vegetation, 5: not_vegetated,  6: water, 7: unclassified,  8: cloud_medium_probability, 9: cloud_high_probability, 10: thin_cirrus, 11: snow",
#         data_cubes_producer="CloudFerrro S.A."
#     )

    
#     output_path = os.path.join(output_dir, f"{prefix}.zarr")
#     merged.to_zarr(output_path, mode="w")
#     print(f"Zapisano: {output_path}")
#     break

# # import xarray as xr

# # # Paths to your Zarr data cubes"
# # zarr_S2L2A = "/ARCEMECUBES/PRODUCTION_CUBES/CLOUDFERRO/S2L2A/DC__2015-0011-MOZ__2014-01-01__2016-01-01_20250905_094334_v0100.zarr"
# # zarr_S1RTC = "/ARCEMECUBES/PRODUCTION_CUBES/PLANETARY/S1RTC/DC__2015-0011-MOZ__2014-01-01__2016-01-01_20250905_095248_v0100.zarr"
# # zarr_COPDEM = "/ARCEMECUBES/PRODUCTION_CUBES/CLOUDFERRO/COPDEM/DC__2015-0011-MOZ__2010-01-01__2024-12-31_20250905_095708_v0100.zarr"
# # zarr_ESALC = "/ARCEMECUBES/PRODUCTION_CUBES/PLANETARY/ESALC/DC__2015-0011-MOZ__2019-01-01__2020-12-31_20250905_125428_v0100.zarr"

# # output_path = "/ARCEMECUBES/PRODUCTION_CUBES/COMBINED/merged_cube.zarr"

# # # Load both cubes
# # cube_S2L2A = xr.open_zarr(zarr_S2L2A)
# # cube_S1RTC = xr.open_zarr(zarr_S1RTC)
# # cube_COPDEM = xr.open_zarr(zarr_COPDEM)
# # cube_ESALC = xr.open_zarr(zarr_ESALC)

# # # Merge along a shared set of variables/coordinates
# # # merged_cube = xr.merge([cube1, cube2])
# # merged_cube = xr.merge([cube_S2L2A, cube_S1RTC, cube_COPDEM, cube_ESALC])

# # # Save as a new Zarr
# # merged_cube.to_zarr(output_path, mode="w")
# # print(f"Merged cube saved to: {output_path}")



# import os
# import re
# import glob
# import xarray as xr
# from collections import defaultdict

# # Katalogi źródłowe
# input_dirs = {
#     "S2L2A": "/ARCEMECUBES/PRODUCTION_CUBES/CLOUDFERRO/S2L2A_CLOUDMASK",
#     "COPDEM": "/ARCEMECUBES/PRODUCTION_CUBES/CLOUDFERRO/COPDEM",
#     "S1RTC": "/ARCEMECUBES/PRODUCTION_CUBES/PLANETARY/S1RTC",
#     "ESALC": "/ARCEMECUBES/PRODUCTION_CUBES/PLANETARY/ESALC",
# }

# # Katalog wynikowy
# output_dir = "/ARCEMECUBES/PRODUCTION_CUBES/COMBINED"
# os.makedirs(output_dir, exist_ok=True)

# # Funkcja do wyciągania prefiksu
# def extract_prefix(path):
#     fname = os.path.basename(path)
#     match = re.match(r"(DC__[^_]+)", fname)
#     if not match:
#         raise ValueError(f"Nie udało się znaleźć prefiksu w {fname}")
#     return match.group(1)

# vars_to_uint16 = [
#     'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08',
#     'B8A', 'B09', 'B11', 'B12', 'SCL', 'cloud_mask', 'ESA_LC'
# ]

# # Grupowanie plików po prefiksie i źródle
# groups = defaultdict(lambda: defaultdict(list))
# for name, d in input_dirs.items():
#     for path in glob.glob(os.path.join(d, "DC__*.zarr")):
#         prefix = extract_prefix(path)
#         groups[prefix][name].append(path)

# # Iteracja po grupach i scalanie
# for prefix, sources in groups.items():
#     print(f"Scalam {prefix}")

#     log_lines = []
#     cubes = []

#     for src_name, paths in sources.items():
#         if paths:
#             log_lines.append(f"[OK] {src_name}: {', '.join(os.path.basename(p) for p in paths)}")
#             cubes.extend([xr.open_zarr(p) for p in paths])
#         else:
#             log_lines.append(f"[BRAK] {src_name}")

#     if not cubes:
#         print(f"Brak kostek do scalania dla {prefix}, pomijam...")
#         continue

#     merged = xr.merge(cubes)

#     # Konwersja typów
#     for var in vars_to_uint16:
#         if var in merged:
#             merged[var] = merged[var].astype('uint16')

#     # Aktualizacja atrybutów
#     merged.attrs.update(
#         project="ARCEME - Adaptation and Resilience to Climate Extremes and Multi-hazard Events",
#         pixel_resolution_meters="10",
#         resampling_method="nearest neighbor",
#         size_px="height: 1000 px, width: 1000 px",
#         stac_endpoints="CDSE: https://stac.dataspace.copernicus.eu/v1/ Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1",
#         collections="CDSE: sentinel-2-l2a, copernicus-dem-30; Planetary Computer: sentinel-1-rtc, esa-worldcover-2020",
#         time_axis="time_sentinel_2_l2a, time_cop_dem_glo_30_dged_cog, time_sentinel_1_rtc, time_esa_worldcover",
#         land_cover="ESA World Cover 2020 map at 10 m resolution",
#         land_cover_legend="10 - Tree cover, 20 - Shrubland, 30 - Grassland,  40 - Cropland, 50 - Built-up, 60 - Bare /sparse vegetation, 70 - Snow and Ice, 80 - Permanent water bodies, 90 - Herbaceous wetland, 95 - Mangroves, 100 - Moss and lichen",
#         land_cover_citation="https://doi.org/10.5281/zenodo.5571936",
#         cloud_mask_description="0: Unoccluded, 1: Thick cloud, 2: Thin cloud, 3: Shadow",
#         cloud_mask_algorithm="SEnSeIv2/SegFormerB2",
#         cloud_mask_stride_size="512",
#         cloud_mask_citation="https://www.doi.org/10.1109/TGRS.2024.3391625",
#         Sentinel_2_SCL_description="0: no_data, 1: saturated_or_defective, 2: dark_area_pixels,  3: cloud_shadows, 4: vegetation, 5: not_vegetated,  6: water, 7: unclassified,  8: cloud_medium_probability, 9: cloud_high_probability, 10: thin_cirrus, 11: snow",
#         data_cubes_producer="CloudFerrro S.A."
#     )

#     # Zapis do Zarr
#     output_path = os.path.join(output_dir, f"{prefix}.zarr")
#     merged.to_zarr(output_path, mode="w")
#     print(f"Zapisano: {output_path}")

#     # Zapis logu
#     log_path = os.path.join(output_dir, f"{prefix}_log.txt")
#     with open(log_path, "w") as f:
#         f.write("\n".join(log_lines))
#     print(f"Zapisano log: {log_path}")

### check


# import os
# import re
# import glob
# import xarray as xr
# from collections import defaultdict
# import traceback
# import zarr
# import s3fs
# import gc

# # Konfiguracja S3
# fs = s3fs.S3FileSystem(
#     anon=False,
#     skip_instance_cache=True,
#     key='07f864fc10134645b69c5546108580ef',
#     secret='16b2235d5f47467d92272eb830440752',
#     client_kwargs={'endpoint_url': "https://s3.waw3-2.cloudferro.com"}
# )

# # Katalogi źródłowe
# input_dirs = {
#     "S2L2A": "/ARCEMECUBES/MELANIE_DC/S2L2A_CLOUDMASK/",
#     "COPDEM": "/ARCEMECUBES/MELANIE_DC/COPDEM/",
#     "S1RTC": "/ARCEMECUBES/MELANIE_DC/S1RTC/",
#     "ESALC": "/ARCEMECUBES/MELANIE_DC/ESALC/",
# }

# # Katalog wynikowy
# output_dir = "/ARCEMECUBES/MELANIE_DC/COMBINED/"
# os.makedirs(output_dir, exist_ok=True)

# # Ścieżka do wspólnego logu
# log_path = os.path.join(output_dir, "processing_log.txt")

# # Funkcja do wyciągania prefiksu
# def extract_prefix(path):
#     fname = os.path.basename(path)
#     # match = re.match(r"(DC__[^_]+)", fname)
#     # match = re.match(r"(DC__\d+(?:_dhp|_d)?)(?=__)", fname)
#     match = re.match(r"^(DC__\d+(?:_dhp|_d)?__[0-9]{4}-[0-9]{2}-[0-9]{2}__[0-9]{4}-[0-9]{2}-[0-9]{2})", fname)
#     if not match:
#         raise ValueError(f"Nie udało się znaleźć prefiksu w {fname}")
#     return match.group(1)

# vars_to_uint16 = [
#     'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08',
#     'B8A', 'B09', 'B11', 'B12', 'SCL', 'cloud_mask', 'ESA_LC'
# ]

# # Grupowanie plików po prefiksie i źródle
# groups = defaultdict(lambda: defaultdict(list))
# for name, d in input_dirs.items():
#     for path in glob.glob(os.path.join(d, "DC__*.zarr")):
#         prefix = extract_prefix(path)
#         groups[prefix][name].append(path)

# # Otwórz log do dopisywania
# with open(log_path, "w") as log_file:

#     for prefix, sources in groups.items():
#         log_file.write(f"\n=== Przetwarzanie {prefix} ===\n")
#         print(f"Scalam {prefix}")
#         print(f"Źródła: { {k: len(v) for k, v in sources.items()} }")

#         cubes = []
#         try:
#             for src_name, paths in sources.items():
#                 if paths:
#                     log_file.write(f"[OK] {src_name}: {', '.join(os.path.basename(p) for p in paths)}\n")
#                     cubes.extend([xr.open_zarr(p, chunks={"x": 1000, "y": 1000}) for p in paths])
#                 else:
#                     log_file.write(f"[BRAK] {src_name}\n")

#             if not cubes:
#                 log_file.write(f"[INFO] Brak kostek do scalania dla {prefix}, pomijam...\n")
#                 continue

#             merged = xr.merge(cubes)

#             # Konwersja typów
#             for var in vars_to_uint16:
#                 if var in merged:
#                     merged[var] = merged[var].astype('uint16')

#             for var in merged.variables:
#                 if "_FillValue" in merged[var].attrs:
#                     del merged[var].attrs["_FillValue"]

#             # Aktualizacja atrybutów
#             merged.attrs.update(
#                 project="ARCEME - Adaptation and Resilience to Climate Extremes and Multi-hazard Events",
#                 pixel_resolution_meters="10",
#                 resampling_method="nearest neighbor",
#                 size_px="height: 1000 px, width: 1000 px",
#                 stac_endpoints="CDSE: https://stac.dataspace.copernicus.eu/v1/ Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1",
#                 collections="CDSE: sentinel-2-l2a, copernicus-dem-30; Planetary Computer: sentinel-1-rtc, esa-worldcover-2020",
#                 time_axis="time_sentinel_2_l2a, time_cop_dem_glo_30_dged_cog, time_sentinel_1_rtc, time_esa_worldcover",
#                 land_cover="ESA World Cover 2020 map at 10 m resolution",
#                 land_cover_legend="10 - Tree cover, 20 - Shrubland, 30 - Grassland,  40 - Cropland, 50 - Built-up, 60 - Bare /sparse vegetation, 70 - Snow and Ice, 80 - Permanent water bodies, 90 - Herbaceous wetland, 95 - Mangroves, 100 - Moss and lichen",
#                 land_cover_citation="https://doi.org/10.5281/zenodo.5571936",
#                 cloud_mask_description="0: Unoccluded, 1: Thick cloud, 2: Thin cloud, 3: Shadow",
#                 cloud_mask_algorithm="SEnSeIv2/SegFormerB2",
#                 cloud_mask_stride_size="512",
#                 cloud_mask_citation="https://www.doi.org/10.1109/TGRS.2024.3391625",
#                 Sentinel_2_SCL_description="0: no_data, 1: saturated_or_defective, 2: dark_area_pixels,  3: cloud_shadows, 4: vegetation, 5: not_vegetated,  6: water, 7: unclassified,  8: cloud_medium_probability, 9: cloud_high_probability, 10: thin_cirrus, 11: snow",
#                 data_cubes_producer="CloudFerrro S.A."
#             )

#             # Zapis do Zarr
#             output_path = os.path.join(output_dir, f"{prefix}.zarr")
#             merged.to_zarr(output_path, mode="w")
#             # log_file.write(f"[ZAPISANO] {output_path}\n")
#             print(f"Zapisano: {output_path}")


#             # Mapper do lokalizacji w S3
#             # s3_path = f's3://ARCEME-DATACUBES/SECONDBATCH/{prefix}.zarr'  # prefix z grupowania
#             # mapper = fs.get_mapper(s3_path)

#             # Zapis merged Dataset do S3
#             # merged.to_zarr(mapper, mode='w')
#             # log_file.write(f"[ZAPISANO S3] {s3_path}\n")
#             # print(f"Zapisano na S3: {s3_path}")

#         except Exception as e:
#             log_file.write(f"[ERROR] Wystąpił błąd przy {prefix}:\n")
#             log_file.write(traceback.format_exc() + "\n")
#             print(f"Wystąpił błąd przy {prefix}, patrz log.")

#         gc.collect()
#         # break

### new check

import os
import re
import glob
import xarray as xr
from collections import defaultdict
import traceback
import zarr
import s3fs
import gc

# Konfiguracja S3
fs = s3fs.S3FileSystem(
    anon=False,
    skip_instance_cache=True,
    key='07f864fc10134645b69c5546108580ef',
    secret='16b2235d5f47467d92272eb830440752',
    client_kwargs={'endpoint_url': "https://s3.waw3-2.cloudferro.com"}
)

# Katalogi źródłowe
input_dirs = {
    "S2L2A": "/ARCEMECUBES/MELANIE_DC/S2L2A_CLOUDMASK/",
    "COPDEM": "/ARCEMECUBES/MELANIE_DC/COPDEM/",
    "S1RTC": "/ARCEMECUBES/MELANIE_DC/S1RTC/",
    "ESALC": "/ARCEMECUBES/MELANIE_DC/ESALC_NEW/",
}

# Katalog wynikowy
output_dir = "/ARCEMECUBES/MELANIE_DC/COMBINED/"
os.makedirs(output_dir, exist_ok=True)

# Ścieżka do wspólnego logu
log_path = os.path.join(output_dir, "processing_log.txt")

# Wzorce prefiksów
LONG_RE = re.compile(r"^(DC__\d+(?:_dhp|_d)?__[0-9]{4}-[0-9]{2}-[0-9]{2}__[0-9]{4}-[0-9]{2}-[0-9]{2})")
SHORT_RE = re.compile(r"^(DC__\d+(?:_dhp|_d)?)")

# Lista zmiennych do konwersji
vars_to_uint16 = [
    'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08',
    'B8A', 'B09', 'B11', 'B12', 'SCL', 'cloud_mask', 'ESA_LC'
]

# Pomocnicza funkcja listująca katalogi Zarr
def list_dir_files(dirpath):
    return sorted(glob.glob(os.path.join(dirpath, "DC__*.zarr")))

# ========================
# Grupowanie wg zasad:
#   - S2L2A → główny długi prefiks (master)
#   - S1RTC → dopasowanie po tym samym długim prefiksie
#   - COPDEM, ESALC → dopasowanie po krótkim prefiksie
# ========================
groups = defaultdict(lambda: defaultdict(list))

# 1️⃣ Pobranie master-prefiksów z S2L2A
s2_files = list_dir_files(input_dirs["S2L2A"])
long_prefixes = []
for p in s2_files:
    fname = os.path.basename(p)
    m = LONG_RE.match(fname)
    if m:
        long_prefixes.append(m.group(1))
long_prefixes = sorted(set(long_prefixes))

# 2️⃣ Grupowanie plików według zasad
for long_pref in long_prefixes:
    short_match = SHORT_RE.match(long_pref)
    short_pref = short_match.group(1) if short_match else None

    # S2L2A (pełny prefiks)
    s2_matches = [p for p in list_dir_files(input_dirs["S2L2A"]) if os.path.basename(p).startswith(long_pref)]
    if s2_matches:
        groups[long_pref]["S2L2A"].extend(s2_matches)

    # S1RTC (pełny prefiks)
    s1_matches = [p for p in list_dir_files(input_dirs["S1RTC"]) if os.path.basename(p).startswith(long_pref)]
    if s1_matches:
        groups[long_pref]["S1RTC"].extend(s1_matches)

    # COPDEM i ESALC (krótki prefiks)
    if short_pref:
        for src in ("COPDEM", "ESALC"):
            matches = [p for p in list_dir_files(input_dirs[src]) if os.path.basename(p).startswith(short_pref)]
            if matches:
                groups[long_pref][src].extend(matches)

# ========================
# Przetwarzanie i zapis
# ========================
with open(log_path, "w") as log_file:
    for prefix, sources in groups.items():
        log_file.write(f"\n=== Przetwarzanie {prefix} ===\n")
        print(f"Scalam {prefix}")
        print(f"Źródła: { {k: len(v) for k, v in sources.items()} }")

        cubes = []
        try:
            # Otwarcie wszystkich powiązanych kostek
            for src_name, paths in sources.items():
                if paths:
                    log_file.write(f"[OK] {src_name}: {', '.join(os.path.basename(p) for p in paths)}\n")
                    cubes.extend([xr.open_zarr(p, chunks={"x": 1000, "y": 1000}) for p in paths])
                else:
                    log_file.write(f"[BRAK] {src_name}\n")

            if not cubes:
                log_file.write(f"[INFO] Brak kostek do scalania dla {prefix}, pomijam...\n")
                continue

            # Scalanie
            merged = xr.merge(cubes)

            # Konwersja typów
            for var in vars_to_uint16:
                if var in merged:
                    merged[var] = merged[var].astype('uint16')

            # Usuwanie atrybutów _FillValue
            for var in merged.variables:
                if "_FillValue" in merged[var].attrs:
                    del merged[var].attrs["_FillValue"]

            # Aktualizacja metadanych
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

            # Zapis do Zarr
            output_path = os.path.join(output_dir, f"{prefix}.zarr")
            merged.to_zarr(output_path, mode="w")
            print(f"Zapisano: {output_path}")
            log_file.write(f"[ZAPISANO] {output_path}\n")

        except Exception:
            log_file.write(f"[ERROR] Wystąpił błąd przy {prefix}:\n")
            log_file.write(traceback.format_exc() + "\n")
            print(f"Wystąpił błąd przy {prefix}, patrz log.")

        gc.collect()















# import os
# import re
# import glob
# import xarray as xr
# from collections import defaultdict
# import traceback
# import zarr
# import s3fs
# import gc
# import dask
# import psutil  # For memory logging

# # Optimize Dask for lower memory
# dask.config.set({"array.chunk-size": "128MB", "scheduler": "threads", "num-workers": 4})

# # Konfiguracja S3 (consider env vars for keys in prod)
# fs = s3fs.S3FileSystem(
#     anon=False,
#     skip_instance_cache=True,
#     key='07f864fc10134645b69c5546108580ef',
#     secret='16b2235d5f47467d92272eb830440752',
#     client_kwargs={'endpoint_url': "https://s3.waw3-2.cloudferro.com"}
# )

# # Katalogi źródłowe
# input_dirs = {
#     "S2L2A": "/ARCEMECUBES/MELANIE_DC/S2L2A_CLOUDMASK/",
#     "COPDEM": "/ARCEMECUBES/MELANIE_DC/COPDEM/",
#     "S1RTC": "/ARCEMECUBES/MELANIE_DC/S1RTC/",
#     "ESALC": "/ARCEMECUBES/MELANIE_DC/ESALC/",
# }

# # Katalog wynikowy
# output_dir = "/ARCEMECUBES/MELANIE_DC/COMBINED/"
# os.makedirs(output_dir, exist_ok=True)

# # Ścieżka do wspólnego logu
# log_path = os.path.join(output_dir, "processing_log.txt")

# # Funkcja do wyciągania prefiksu
# def extract_prefix(path):
#     fname = os.path.basename(path)
#     match = re.match(r"(DC__[^_]+)", fname)
#     if not match:
#         raise ValueError(f"Nie udało się znaleźć prefiksu w {fname}")
#     return match.group(1)

# vars_to_uint16 = [
#     'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08',
#     'B8A', 'B09', 'B11', 'B12', 'SCL', 'cloud_mask', 'ESA_LC'
# ]

# # Funkcja do logowania pamięci
# def log_memory(log_file, prefix):
#     memory = psutil.virtual_memory()
#     log_file.write(f"[MEM] {prefix}: Used {memory.percent:.1f}% ({memory.used / 1024**3:.1f} GB / {memory.total / 1024**3:.1f} GB)\n")
#     log_file.flush()

# # Grupowanie plików po prefiksie i źródle
# groups = defaultdict(lambda: defaultdict(list))
# for name, d in input_dirs.items():
#     for path in glob.glob(os.path.join(d, "DC__*.zarr")):
#         prefix = extract_prefix(path)
#         groups[prefix][name].append(path)

# # Otwórz log do dopisywania
# with open(log_path, "w") as log_file:

#     for prefix, sources in groups.items():
#         log_file.write(f"\n=== Przetwarzanie {prefix} ===\n")
#         log_memory(log_file, f"Start {prefix}")
#         print(f"Scalam {prefix}")

#         cubes = []
#         try:
#             for src_name, paths in sources.items():
#                 if paths:
#                     log_file.write(f"[OK] {src_name}: {', '.join(os.path.basename(p) for p in paths)}\n")
#                     # Open with smaller chunks and only needed vars
#                     for p in paths:
#                         ds = xr.open_zarr(p, chunks={"x": 500, "y": 500}, decode_cf=False)
#                         if 'drop_vars' in locals():  # Avoid loading extras
#                             ds = ds.drop_vars([v for v in ds.variables if v not in vars_to_uint16 + list(ds.coords)])
#                         cubes.append(ds)
#                 else:
#                     log_file.write(f"[BRAK] {src_name}\n")

#             if not cubes:
#                 log_file.write(f"[INFO] Brak kostek do scalania dla {prefix}, pomijam...\n")
#                 continue

#             # Lazy merge
#             merged = xr.merge(cubes, compat='override', join='override')

#             # Lazy type conversion for uint16 vars
#             for var in vars_to_uint16:
#                 if var in merged and merged[var].dtype != 'uint16':
#                     merged = merged.assign({var: merged[var].astype('uint16')})

#             # Drop any extra vars post-merge to save mem
#             extra_vars = [v for v in merged.variables if v not in vars_to_uint16 + list(merged.coords)]
#             if extra_vars:
#                 merged = merged.drop_vars(extra_vars)

#             log_memory(log_file, f"Post-merge {prefix}")

#             # Aktualizacja atrybutów
#             merged.attrs.update(
#                 project="ARCEME - Adaptation and Resilience to Climate Extremes and Multi-hazard Events",
#                 pixel_resolution_meters="10",
#                 resampling_method="nearest neighbor",
#                 size_px="height: 1000 px, width: 1000 px",
#                 stac_endpoints="CDSE: https://stac.dataspace.copernicus.eu/v1/ Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1",
#                 collections="CDSE: sentinel-2-l2a, copernicus-dem-30; Planetary Computer: sentinel-1-rtc, esa-worldcover-2020",
#                 time_axis="time_sentinel_2_l2a, time_cop_dem_glo_30_dged_cog, time_sentinel_1_rtc, time_esa_worldcover",
#                 land_cover="ESA World Cover 2020 map at 10 m resolution",
#                 land_cover_legend="10 - Tree cover, 20 - Shrubland, 30 - Grassland,  40 - Cropland, 50 - Built-up, 60 - Bare /sparse vegetation, 70 - Snow and Ice, 80 - Permanent water bodies, 90 - Herbaceous wetland, 95 - Mangroves, 100 - Moss and lichen",
#                 land_cover_citation="https://doi.org/10.5281/zenodo.5571936",
#                 cloud_mask_description="0: Unoccluded, 1: Thick cloud, 2: Thin cloud, 3: Shadow",
#                 cloud_mask_algorithm="SEnSeIv2/SegFormerB2",
#                 cloud_mask_stride_size="512",
#                 cloud_mask_citation="https://www.doi.org/10.1109/TGRS.2024.3391625",
#                 Sentinel_2_SCL_description="0: no_data, 1: saturated_or_defective, 2: dark_area_pixels,  3: cloud_shadows, 4: vegetation, 5: not_vegetated,  6: water, 7: unclassified,  8: cloud_medium_probability, 9: cloud_high_probability, 10: thin_cirrus, 11: snow",
#                 data_cubes_producer="CloudFerrro S.A."
#             )

#             # Mapper do lokalizacji w S3
#             s3_path = f's3://ARCEME-DATACUBES/SECONDBATCH/{prefix}.zarr'
#             mapper = fs.get_mapper(s3_path)

#             # Zapis merged Dataset do S3 (with compute=False for lazier write if possible, but to_zarr needs it)
#             # Optional: merged = merged.persist()  # Pre-cache in memory if RAM allows, else skip
#             from dask.diagnostics import ProgressBar
#             with ProgressBar():
#                 merged.to_zarr(mapper, mode='w', consolidated=True)  # Consolidated for faster future reads
#             log_memory(log_file, f"Post-write {prefix}")

#             log_file.write(f"[ZAPISANO S3] {s3_path}\n")
#             print(f"Zapisano na S3: {s3_path}")

#             # Explicit close and GC
#             for cube in cubes:
#                 cube.close()
#             merged.close()
#             del merged, cubes
#             gc.collect()

#         except Exception as e:
#             log_file.write(f"[ERROR] Wystąpił błąd przy {prefix}:\n")
#             log_file.write(traceback.format_exc() + "\n")
#             print(f"Wystąpił błąd przy {prefix}, patrz log.")
#             gc.collect()

#         log_memory(log_file, f"End {prefix}")


# import os
# import re
# import glob
# import xarray as xr
# from collections import defaultdict
# import traceback
# import zarr
# import s3fs
# import gc
# import dask
# import psutil  # For memory logging
# import numpy as np

# # Optimize Dask for lower memory
# dask.config.set({"array.chunk-size": "128MB", "scheduler": "threads", "num-workers": 4})

# # Konfiguracja S3 (consider env vars for keys in prod)
# fs = s3fs.S3FileSystem(
#     anon=False,
#     skip_instance_cache=True,
#     key='07f864fc10134645b69c5546108580ef',
#     secret='16b2235d5f47467d92272eb830440752',
#     client_kwargs={'endpoint_url': "https://s3.waw3-2.cloudferro.com"}
# )

# # Katalogi źródłowe
# input_dirs = {
#     "S2L2A": "/ARCEMECUBES/MELANIE_DC/S2L2A_CLOUDMASK/",
#     "COPDEM": "/ARCEMECUBES/MELANIE_DC/COPDEM/",
#     "S1RTC": "/ARCEMECUBES/MELANIE_DC/S1RTC/",
#     "ESALC": "/ARCEMECUBES/MELANIE_DC/ESALC/",
# }

# # Katalog wynikowy
# output_dir = "/ARCEMECUBES/MELANIE_DC/COMBINED/"
# os.makedirs(output_dir, exist_ok=True)

# # Ścieżka do wspólnego logu
# log_path = os.path.join(output_dir, "processing_log.txt")

# # Funkcja do wyciągania prefiksu
# def extract_prefix(path):
#     fname = os.path.basename(path)
#     match = re.match(r"(DC__[^_]+)", fname)
#     if not match:
#         raise ValueError(f"Nie udało się znaleźć prefiksu w {fname}")
#     return match.group(1)

# vars_to_uint16 = [
#     'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08',
#     'B8A', 'B09', 'B11', 'B12', 'SCL', 'cloud_mask', 'ESA_LC'
# ]

# # Funkcja do logowania pamięci
# def log_memory(log_file, prefix):
#     memory = psutil.virtual_memory()
#     log_file.write(f"[MEM] {prefix}: Used {memory.percent:.1f}% ({memory.used / 1024**3:.1f} GB / {memory.total / 1024**3:.1f} GB)\n")
#     log_file.flush()

# # Grupowanie plików po prefiksie i źródle
# groups = defaultdict(lambda: defaultdict(list))
# for name, d in input_dirs.items():
#     for path in glob.glob(os.path.join(d, "DC__*.zarr")):
#         prefix = extract_prefix(path)
#         groups[prefix][name].append(path)

# # Otwórz log do dopisywania
# with open(log_path, "w") as log_file:

#     for prefix, sources in groups.items():
#         log_file.write(f"\n=== Przetwarzanie {prefix} ===\n")
#         log_memory(log_file, f"Start {prefix}")
#         print(f"Scalam {prefix}")

#         source_datasets = {}  # Dict of source_name: merged_ds_for_source
#         try:
#             for src_name, paths in sources.items():
#                 if paths:
#                     log_file.write(f"[OK] {src_name}: {', '.join(os.path.basename(p) for p in paths)}\n")
#                     # Open individual datasets with smaller chunks
#                     individual_ds = []
#                     for p in paths:
#                         ds = xr.open_zarr(p, chunks={"x": 500, "y": 500})
#                         # Keep only needed vars + coords
#                         keep_vars = [v for v in vars_to_uint16 if v in ds.data_vars] + list(ds.coords)
#                         ds = ds.drop_vars([v for v in ds.data_vars if v not in keep_vars])
#                         individual_ds.append(ds)

#                     if len(individual_ds) > 1:
#                         # Find time dim (assume consistent across vars)
#                         time_dim = None
#                         if individual_ds:
#                             sample_ds = individual_ds[0]
#                             time_dim = next((dim for dim in sample_ds.dims if 'time' in dim.lower()), None)
#                         if time_dim:
#                             source_merged = xr.concat(individual_ds, dim=time_dim, coords='minimal', data_vars='minimal', compat='override')
#                             # Sort by time if needed
#                             if source_merged[time_dim].size > 1:
#                                 source_merged = source_merged.sortby(time_dim)
#                         else:
#                             # Fallback to merge if no time dim (e.g., static like COPDEM)
#                             source_merged = xr.merge(individual_ds, compat='override')
#                     else:
#                         source_merged = individual_ds[0]

#                     # Lazy type conversion for uint16 vars using direct assignment
#                     for var in vars_to_uint16:
#                         if var in source_merged.data_vars and source_merged[var].dtype != 'uint16':
#                             source_merged[var] = source_merged[var].astype('uint16')
#                             # Clean up invalid _FillValue if present
#                             if '_FillValue' in source_merged[var].attrs and np.isnan(source_merged[var].attrs['_FillValue']):
#                                 del source_merged[var].attrs['_FillValue']
#                             # Set valid _FillValue for uint16
#                             source_merged[var].attrs['_FillValue'] = 0

#                     source_datasets[src_name] = source_merged
#                 else:
#                     log_file.write(f"[BRAK] {src_name}\n")

#             if not source_datasets:
#                 log_file.write(f"[INFO] Brak kostek do scalania dla {prefix}, pomijam...\n")
#                 continue

#             # Now merge across sources (should have compatible spatial dims, different time dims ok with outer join)
#             cubes = list(source_datasets.values())
#             merged = xr.merge(cubes, compat='override', join='outer')

#             # Drop any extra vars post-merge to save mem (use data_vars)
#             keep_vars = [v for v in vars_to_uint16 if v in merged.data_vars] + list(merged.coords)
#             extra_vars = [v for v in merged.data_vars if v not in keep_vars]
#             if extra_vars:
#                 merged = merged.drop_vars(extra_vars)

#             log_memory(log_file, f"Post-merge {prefix}")

#             # Prep encoding for to_zarr: Override for uint16 vars
#             encoding = {}
#             for var in vars_to_uint16:
#                 if var in merged.data_vars:
#                     encoding[var] = {'dtype': 'uint16', '_FillValue': 0}

#             # Aktualizacja atrybutów
#             merged.attrs.update(
#                 project="ARCEME - Adaptation and Resilience to Climate Extremes and Multi-hazard Events",
#                 pixel_resolution_meters="10",
#                 resampling_method="nearest neighbor",
#                 size_px="height: 1000 px, width: 1000 px",
#                 stac_endpoints="CDSE: https://stac.dataspace.copernicus.eu/v1/ Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1",
#                 collections="CDSE: sentinel-2-l2a, copernicus-dem-30; Planetary Computer: sentinel-1-rtc, esa-worldcover-2020",
#                 time_axis="time_sentinel_2_l2a, time_cop_dem_glo_30_dged_cog, time_sentinel_1_rtc, time_esa_worldcover",
#                 land_cover="ESA World Cover 2020 map at 10 m resolution",
#                 land_cover_legend="10 - Tree cover, 20 - Shrubland, 30 - Grassland,  40 - Cropland, 50 - Built-up, 60 - Bare /sparse vegetation, 70 - Snow and Ice, 80 - Permanent water bodies, 90 - Herbaceous wetland, 95 - Mangroves, 100 - Moss and lichen",
#                 land_cover_citation="https://doi.org/10.5281/zenodo.5571936",
#                 cloud_mask_description="0: Unoccluded, 1: Thick cloud, 2: Thin cloud, 3: Shadow",
#                 cloud_mask_algorithm="SEnSeIv2/SegFormerB2",
#                 cloud_mask_stride_size="512",
#                 cloud_mask_citation="https://www.doi.org/10.1109/TGRS.2024.3391625",
#                 Sentinel_2_SCL_description="0: no_data, 1: saturated_or_defective, 2: dark_area_pixels,  3: cloud_shadows, 4: vegetation, 5: not_vegetated,  6: water, 7: unclassified,  8: cloud_medium_probability, 9: cloud_high_probability, 10: thin_cirrus, 11: snow",
#                 data_cubes_producer="CloudFerrro S.A."
#             )

#             # Mapper do lokalizacji w S3
#             s3_path = f's3://ARCEME-DATACUBES/SECONDBATCH/{prefix}.zarr'
#             mapper = fs.get_mapper(s3_path)

#             # Zapis merged Dataset do S3 with encoding
#             from dask.diagnostics import ProgressBar
#             with ProgressBar():
#                 merged.to_zarr(mapper, mode='w', consolidated=True, encoding=encoding)
#             log_memory(log_file, f"Post-write {prefix}")

#             log_file.write(f"[ZAPISANO S3] {s3_path}\n")
#             print(f"Zapisano na S3: {s3_path}")

#             # Explicit close and GC
#             for ds in source_datasets.values():
#                 ds.close()
#             merged.close()
#             del merged
#             gc.collect()

#         except Exception as e:
#             log_file.write(f"[ERROR] Wystąpił błąd przy {prefix}:\n")
#             log_file.write(traceback.format_exc() + "\n")
#             print(f"Wystąpił błąd przy {prefix}, patrz log.")
#             # Close any open ds on error
#             if 'source_datasets' in locals():
#                 for ds in source_datasets.values():
#                     try:
#                         ds.close()
#                     except:
#                         pass
#             if 'merged' in locals():
#                 try:
#                     merged.close()
#                 except:
#                     pass
#             gc.collect()

#         log_memory(log_file, f"End {prefix}")