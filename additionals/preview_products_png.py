import argparse
import random
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
    args = parser.parse_args()

    random.seed(args.seed)

    base_dir = Path(args.base_dir)
    png_dir = Path(args.png_dir)
    png_dir.mkdir(parents=True, exist_ok=True)

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
