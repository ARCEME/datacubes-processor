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


def normalize_filename_part(value: str) -> str:
    return value.replace(":", "-").replace("/", "_").replace(" ", "_")


def get_time_dim(da: xr.DataArray) -> str | None:
    for dim in da.dims:
        if dim.lower().startswith("time"):
            return dim
    return None


def is_categorical_band(var_name: str, arr: np.ndarray) -> bool:
    if var_name in {"SCL", "cloud_mask", "ESA_LC"}:
        return True

    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return False

    unique_count = np.unique(valid).size
    return unique_count <= 30


def save_band_slice(
    image: np.ndarray,
    out_path: Path,
    title: str,
    cmap: str,
    categorical: bool,
) -> None:
    _ = title
    _ = categorical
    plt.imsave(out_path, image, cmap=cmap)


def save_all_visualizations_for_zarr(zarr_path: Path, output_dir: Path) -> tuple[int, int]:
    ds = xr.open_zarr(zarr_path, consolidated=True)
    zarr_out_dir = output_dir / zarr_path.stem
    zarr_out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    failed = 0

    for var_name in sorted(ds.data_vars):
        da = ds[var_name]
        time_dim = get_time_dim(da)
        var_dir = zarr_out_dir / var_name
        var_dir.mkdir(parents=True, exist_ok=True)

        if time_dim is None:
            arr = da.values.astype(np.float32)
            if arr.ndim != 2:
                print(f"Skip {zarr_path.stem}/{var_name}: expected 2D without time, got shape {arr.shape}")
                continue

            categorical = is_categorical_band(var_name, arr)
            cmap = "tab20" if categorical else "viridis"
            out_path = var_dir / f"{var_name}__single.jpg"

            try:
                render_arr = arr if categorical else robust_percentile_stretch(arr)
                save_band_slice(
                    render_arr,
                    out_path,
                    f"{zarr_path.stem}\n{var_name} (single)",
                    cmap,
                    categorical,
                )
                saved += 1
            except Exception as exc:
                failed += 1
                print(f"Failed: {out_path.name} -> {exc}")
            continue

        time_size = int(da.sizes[time_dim])
        for idx in range(time_size):
            try:
                sliced = da.isel({time_dim: idx}).values.astype(np.float32)
                if sliced.ndim != 2:
                    print(
                        f"Skip {zarr_path.stem}/{var_name}[{idx}]: "
                        f"expected 2D after time slice, got shape {sliced.shape}"
                    )
                    continue

                categorical = is_categorical_band(var_name, sliced)
                cmap = "tab20" if categorical else "viridis"

                if time_dim in da.coords:
                    time_value = str(da.coords[time_dim].values[idx])
                else:
                    time_value = f"idx{idx:04d}"
                time_value_clean = normalize_filename_part(time_value)

                out_path = var_dir / f"{var_name}__{idx:04d}__{time_value_clean}.jpg"
                render_arr = sliced if categorical else robust_percentile_stretch(sliced)

                save_band_slice(
                    render_arr,
                    out_path,
                    f"{zarr_path.stem}\n{var_name} | {time_value}",
                    cmap,
                    categorical,
                )
                saved += 1
            except Exception as exc:
                failed += 1
                print(f"Failed: {zarr_path.stem}/{var_name}[{idx}] -> {exc}")

    return saved, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render all-band and all-date JPG visualizations for merged Zarr cubes"
    )
    parser.add_argument(
        "--merged-dir",
        default="/ARCEME-MERGE/NEW_LOCATIONS_MELANIE/MERGED",
        help="Directory containing merged .zarr cubes",
    )
    parser.add_argument(
        "--jpg-dir",
        default="/ARCEME-MERGE/NEW_LOCATIONS_MELANIE/JPG",
        help="Output root directory for JPG previews (one subfolder per zarr)",
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
    total_saved = 0
    total_failed = 0

    for zarr_path in zarr_paths:
        try:
            print(f"Processing: {zarr_path.name}")
            saved, failed = save_all_visualizations_for_zarr(zarr_path, jpg_dir)
            total_saved += saved
            total_failed += failed
            print(f"Completed: {zarr_path.name} | saved={saved} failed={failed}")
        except Exception as exc:
            total_failed += 1
            print(f"Failed zarr: {zarr_path.name} -> {exc}")

    print(f"Done. Saved JPGs: {total_saved}, Failed renders: {total_failed}")


if __name__ == "__main__":
    main()
