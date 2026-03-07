import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


def robust_percentile_stretch(arr: np.ndarray, pmin: int = 2, pmax: int = 98) -> np.ndarray:
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return np.zeros_like(arr, dtype=np.float32)

    lo, hi = np.percentile(valid, [pmin, pmax])
    if hi <= lo:
        return np.zeros_like(arr, dtype=np.float32)

    out = (arr - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def get_time_dim(da: xr.DataArray) -> str | None:
    for dim in da.dims:
        if dim.lower().startswith("time"):
            return dim
    return None


def pick_best_time_index(ds: xr.Dataset) -> int:
    if "cloud_mask" not in ds:
        return 0

    cm = ds["cloud_mask"]
    time_dim = get_time_dim(cm)
    if time_dim is None:
        return 0

    data = cm.values
    if data.ndim != 3:
        return 0

    best_idx = 0
    best_score = -1.0
    for idx in range(data.shape[0]):
        mask = data[idx]
        valid = np.isfinite(mask) & (mask <= 3)
        valid_count = int(valid.sum())
        if valid_count == 0:
            score = -1.0
        else:
            clear_count = int((mask == 0).sum())
            score = clear_count / valid_count

        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx


def build_rgb_preview(ds: xr.Dataset) -> np.ndarray:
    for band in ["B04", "B03", "B02"]:
        if band not in ds:
            raise ValueError(f"Missing required band '{band}' in merged cube")

    idx = pick_best_time_index(ds)

    r_da = ds["B04"]
    g_da = ds["B03"]
    b_da = ds["B02"]

    time_dim = get_time_dim(r_da)
    if time_dim is not None:
        r = r_da.isel({time_dim: idx}).values.astype(np.float32)
        g = g_da.isel({time_dim: idx}).values.astype(np.float32)
        b = b_da.isel({time_dim: idx}).values.astype(np.float32)
    else:
        r = r_da.values.astype(np.float32)
        g = g_da.values.astype(np.float32)
        b = b_da.values.astype(np.float32)

    rgb = np.dstack(
        [
            robust_percentile_stretch(r),
            robust_percentile_stretch(g),
            robust_percentile_stretch(b),
        ]
    )
    return rgb


def save_jpg(zarr_path: Path, output_dir: Path) -> None:
    ds = xr.open_zarr(zarr_path, consolidated=True)
    rgb = build_rgb_preview(ds)

    out_path = output_dir / f"{zarr_path.stem}.jpg"
    plt.figure(figsize=(8, 8))
    plt.imshow(rgb)
    plt.title(zarr_path.stem)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"Saved: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render JPG previews for all merged Zarr cubes")
    parser.add_argument(
        "--merged-dir",
        default="/ARCEME-MERGE/NEW_LOCATIONS_MELANIE/MERGED",
        help="Directory containing merged .zarr cubes",
    )
    parser.add_argument(
        "--jpg-dir",
        default="/ARCEME-MERGE/NEW_LOCATIONS_MELANIE/JPG",
        help="Output directory for JPG previews",
    )
    args = parser.parse_args()

    merged_dir = Path(args.merged_dir)
    jpg_dir = Path(args.jpg_dir)
    jpg_dir.mkdir(parents=True, exist_ok=True)

    zarr_paths = sorted(merged_dir.glob("*.zarr"))
    if not zarr_paths:
        print(f"No .zarr files found in {merged_dir}")
        return

    print(f"Found {len(zarr_paths)} merged cubes")
    ok = 0
    failed = 0

    for zarr_path in zarr_paths:
        try:
            save_jpg(zarr_path, jpg_dir)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"Failed: {zarr_path.name} -> {exc}")

    print(f"Done. Success: {ok}, Failed: {failed}")


if __name__ == "__main__":
    main()
