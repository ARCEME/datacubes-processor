import argparse
import random
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


PRODUCT_DIRS = {
    "s2": "S2L2A",
    "s1": "S1RTC",
    "esalc": "ESALC",
    "dem": "COPDEM",
}


def pick_random_zarr(product_dir: Path):
    zarrs = list(product_dir.glob("*.zarr"))
    if not zarrs:
        return None
    return random.choice(zarrs)


def pick_latest_zarr(product_dir: Path):
    zarrs = list(product_dir.glob("*.zarr"))
    if not zarrs:
        return None
    return max(zarrs, key=lambda path: path.stat().st_mtime)


def robust_percentile_stretch(arr: np.ndarray, pmin=2, pmax=98):
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return np.zeros_like(arr, dtype=np.float32)
    lo, hi = np.percentile(valid, [pmin, pmax])
    if hi <= lo:
        return np.zeros_like(arr, dtype=np.float32)
    out = (arr - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0)


def first_time_slice(da: xr.DataArray) -> xr.DataArray:
    time_dims = [dim for dim in da.dims if dim.lower().startswith("time")]
    if time_dims:
        return da.isel({time_dims[0]: 0})
    return da


def render_s2(ds: xr.Dataset):
    # Natural color RGB
    r = first_time_slice(ds["B04"]).values.astype(np.float32)
    g = first_time_slice(ds["B03"]).values.astype(np.float32)
    b = first_time_slice(ds["B02"]).values.astype(np.float32)
    rgb = np.dstack([
        robust_percentile_stretch(r),
        robust_percentile_stretch(g),
        robust_percentile_stretch(b),
    ])
    return rgb, "S2L2A RGB (B04/B03/B02)"


def render_s1(ds: xr.Dataset):
    vv = first_time_slice(ds["vv"]).values.astype(np.float32)
    vh = first_time_slice(ds["vh"]).values.astype(np.float32)
    ratio = np.divide(vv, vh + 1e-6)
    rgb = np.dstack([
        robust_percentile_stretch(vv),
        robust_percentile_stretch(vh),
        robust_percentile_stretch(ratio),
    ])
    return rgb, "S1RTC pseudo-RGB (VV/VH/VV:VH)"


def render_esalc(ds: xr.Dataset):
    lc = ds["ESA_LC"].values.astype(np.float32)
    if lc.ndim == 3:
        lc = lc[0]
    return lc, "ESALC classes"


def render_dem(ds: xr.Dataset):
    var = "COP-DEM_GLO-30-DGED__data" if "COP-DEM_GLO-30-DGED__data" in ds.data_vars else list(ds.data_vars)[0]
    dem = ds[var].values.astype(np.float32)
    if dem.ndim == 3:
        dem = dem[0]
    return dem, f"DEM ({var})"


def save_preview(product: str, zarr_path: Path, png_dir: Path):
    ds = xr.open_zarr(zarr_path, consolidated=True)

    if product == "s2":
        image, title = render_s2(ds)
        cmap = None
    elif product == "s1":
        image, title = render_s1(ds)
        cmap = None
    elif product == "esalc":
        image, title = render_esalc(ds)
        cmap = "tab20"
    elif product == "dem":
        image, title = render_dem(ds)
        cmap = "terrain"
    else:
        raise ValueError(f"Unsupported product: {product}")

    plt.figure(figsize=(8, 8))
    if image.ndim == 3:
        plt.imshow(image)
    else:
        plt.imshow(image, cmap=cmap)
        plt.colorbar(fraction=0.046, pad=0.04)

    plt.title(f"{title}\n{zarr_path.name}")
    plt.axis("off")

    out_png = png_dir / f"{product}_{zarr_path.stem}.png"
    plt.tight_layout()
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"Saved PNG: {out_png}")


def save_array_png(image: np.ndarray, out_png: Path, cmap=None):
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.imsave(out_png, image, cmap=cmap)


def safe_time_label(da: xr.DataArray, time_dim: str, idx: int) -> str:
    if time_dim is None:
        return "nodate"

    if time_dim in da.coords:
        value = da[time_dim].values[idx]
        if np.issubdtype(np.asarray(value).dtype, np.datetime64):
            return np.datetime_as_string(value, unit="D")

        label = str(value)
    else:
        label = str(idx)

    label = label.replace(" ", "_").replace(":", "-")
    label = re.sub(r"[^0-9A-Za-z_\-]", "", label)
    return label or f"idx{idx:04d}"


def get_time_dim(da: xr.DataArray):
    for dim in da.dims:
        if dim.lower().startswith("time"):
            return dim
    return None


def get_dem_var(ds: xr.Dataset):
    for candidate in ["COP_DEM", "COP-DEM_GLO-30-DGED__data"]:
        if candidate in ds.data_vars:
            return candidate
    return None


def generate_merged_product_previews(zarr_path: Path, png_root_dir: Path):
    ds = xr.open_zarr(zarr_path, consolidated=True)
    cube_out_dir = png_root_dir / zarr_path.stem
    cube_out_dir.mkdir(parents=True, exist_ok=True)

    try:
        # S2 RGB for every S2 time step.
        if {"B04", "B03", "B02"}.issubset(ds.data_vars):
            s2_dir = cube_out_dir / "S2L2A"
            time_dim = get_time_dim(ds["B04"])
            if time_dim is None:
                r = ds["B04"].values.astype(np.float32)
                g = ds["B03"].values.astype(np.float32)
                b = ds["B02"].values.astype(np.float32)
                rgb = np.dstack([
                    robust_percentile_stretch(r),
                    robust_percentile_stretch(g),
                    robust_percentile_stretch(b),
                ])
                save_array_png(rgb, s2_dir / "s2l2a_rgb_nodate.png")
            else:
                n = ds.sizes[time_dim]
                for i in range(n):
                    r = ds["B04"].isel({time_dim: i}).values.astype(np.float32)
                    g = ds["B03"].isel({time_dim: i}).values.astype(np.float32)
                    b = ds["B02"].isel({time_dim: i}).values.astype(np.float32)
                    rgb = np.dstack([
                        robust_percentile_stretch(r),
                        robust_percentile_stretch(g),
                        robust_percentile_stretch(b),
                    ])
                    label = safe_time_label(ds["B04"], time_dim, i)
                    save_array_png(rgb, s2_dir / f"s2l2a_rgb_{label}.png")

        # S1 pseudo-RGB for every S1 time step.
        if {"vv", "vh"}.issubset(ds.data_vars):
            s1_dir = cube_out_dir / "S1RTC"
            time_dim = get_time_dim(ds["vv"])
            if time_dim is None:
                vv = ds["vv"].values.astype(np.float32)
                vh = ds["vh"].values.astype(np.float32)
                ratio = np.divide(vv, vh + 1e-6)
                s1_rgb = np.dstack([
                    robust_percentile_stretch(vv),
                    robust_percentile_stretch(vh),
                    robust_percentile_stretch(ratio),
                ])
                save_array_png(s1_rgb, s1_dir / "s1rtc_nodate.png")
            else:
                n = ds.sizes[time_dim]
                for i in range(n):
                    vv = ds["vv"].isel({time_dim: i}).values.astype(np.float32)
                    vh = ds["vh"].isel({time_dim: i}).values.astype(np.float32)
                    ratio = np.divide(vv, vh + 1e-6)
                    s1_rgb = np.dstack([
                        robust_percentile_stretch(vv),
                        robust_percentile_stretch(vh),
                        robust_percentile_stretch(ratio),
                    ])
                    label = safe_time_label(ds["vv"], time_dim, i)
                    save_array_png(s1_rgb, s1_dir / f"s1rtc_{label}.png")

        # Cloud mask for every cloud-mask time step.
        if "cloud_mask" in ds.data_vars:
            cloud_dir = cube_out_dir / "CLOUD_MASK"
            cm = ds["cloud_mask"]
            time_dim = get_time_dim(cm)
            if time_dim is None:
                arr = cm.values.astype(np.float32)
                save_array_png(arr, cloud_dir / "cloud_mask_nodate.png", cmap="tab10")
            else:
                n = ds.sizes[time_dim]
                for i in range(n):
                    arr = cm.isel({time_dim: i}).values.astype(np.float32)
                    label = safe_time_label(cm, time_dim, i)
                    save_array_png(arr, cloud_dir / f"cloud_mask_{label}.png", cmap="tab10")

        # DEM single image.
        dem_var = get_dem_var(ds)
        if dem_var is not None:
            dem_dir = cube_out_dir / "COPDEM"
            dem = ds[dem_var]
            time_dim = get_time_dim(dem)
            if time_dim is not None:
                label = safe_time_label(dem, time_dim, 0)
                dem_arr = dem.isel({time_dim: 0}).values.astype(np.float32)
            else:
                label = "nodate"
                dem_arr = dem.values.astype(np.float32)
            save_array_png(dem_arr, dem_dir / f"cop_dem_{label}.png", cmap="terrain")

        # Land cover single image.
        if "ESA_LC" in ds.data_vars:
            lc_dir = cube_out_dir / "ESALC"
            lc = ds["ESA_LC"]
            time_dim = get_time_dim(lc)
            if time_dim is not None:
                label = safe_time_label(lc, time_dim, 0)
                lc_arr = lc.isel({time_dim: 0}).values.astype(np.float32)
            else:
                label = "nodate"
                lc_arr = lc.values.astype(np.float32)
            save_array_png(lc_arr, lc_dir / f"land_cover_{label}.png", cmap="tab20")

        print(f"Saved preview set: {cube_out_dir}")
    finally:
        ds.close()


def main():
    parser = argparse.ArgumentParser(description="Create PNG previews from datacube products")
    parser.add_argument(
        "--base-dir",
        default="/ARCEME-MERGE/TEST_OUTPUT_CLOUD",
        help="Base directory with product subfolders (S2L2A, S1RTC, ESALC, COPDEM)",
    )
    parser.add_argument(
        "--png-dir",
        default="/ARCEME-MERGE/TEST_OUTPUT_CLOUD/PNG_PREVIEWS",
        help="Output directory for PNG previews",
    )
    parser.add_argument(
        "--pick",
        choices=["latest", "random"],
        default="latest",
        help="How to pick zarr per product (default: latest)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--merged-dir",
        default=None,
        help="Optional directory with merged .zarr cubes. If provided, previews are generated in per-cube subfolders.",
    )
    args = parser.parse_args()

    random.seed(args.seed)

    base_dir = Path(args.base_dir)
    png_dir = Path(args.png_dir)
    png_dir.mkdir(parents=True, exist_ok=True)

    if args.merged_dir:
        merged_dir = Path(args.merged_dir)
        if not merged_dir.exists():
            raise FileNotFoundError(f"Merged directory not found: {merged_dir}")

        merged_zarrs = sorted(merged_dir.glob("*.zarr"))
        if not merged_zarrs:
            print(f"No merged cubes found in {merged_dir}")
            return

        for zarr_path in merged_zarrs:
            try:
                generate_merged_product_previews(zarr_path, png_dir)
            except Exception as exc:
                print(f"Failed merged ({zarr_path.name}): {exc}")
        return

    for product, subdir in PRODUCT_DIRS.items():
        product_dir = base_dir / subdir
        if not product_dir.exists():
            print(f"Skip {product}: missing dir {product_dir}")
            continue

        if args.pick == "latest":
            zarr_path = pick_latest_zarr(product_dir)
        else:
            zarr_path = pick_random_zarr(product_dir)
        if zarr_path is None:
            print(f"Skip {product}: no .zarr files in {product_dir}")
            continue

        try:
            save_preview(product, zarr_path, png_dir)
        except Exception as exc:
            print(f"Failed {product} ({zarr_path.name}): {exc}")


if __name__ == "__main__":
    main()
