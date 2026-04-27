import argparse
from pathlib import Path

import imageio.v2 as imageio
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


def robust_percentile_stretch(arr: np.ndarray, pmin=2, pmax=98):
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return np.zeros_like(arr, dtype=np.float32)
    lo, hi = np.percentile(valid, [pmin, pmax])
    if hi <= lo:
        return np.zeros_like(arr, dtype=np.float32)
    out = (arr - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0)


def to_uint8_rgb(rgb_float: np.ndarray) -> np.ndarray:
    rgb = np.clip(rgb_float, 0.0, 1.0)
    return (rgb * 255).astype(np.uint8)


def get_time_dim(da: xr.DataArray):
    for dim in da.dims:
        if dim.lower().startswith("time"):
            return dim
    return None


def save_array_png(image: np.ndarray, out_png: Path, cmap=None):
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.imsave(out_png, image, cmap=cmap)


def get_dem_var(ds: xr.Dataset):
    for candidate in ["COP_DEM", "COP-DEM_GLO-30-DGED__data"]:
        if candidate in ds.data_vars:
            return candidate
    return None


def collect_time_indices(n: int, step: int, max_frames: int):
    idx = list(range(0, n, max(step, 1)))
    if max_frames > 0:
        idx = idx[:max_frames]
    return idx


def create_s2_gif(ds: xr.Dataset, out_path: Path, fps: float, step: int, max_frames: int):
    if not {"B04", "B03", "B02"}.issubset(ds.data_vars):
        return False

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
        frames = [to_uint8_rgb(rgb)]
    else:
        n = ds.sizes[time_dim]
        frames = []
        for i in collect_time_indices(n, step, max_frames):
            r = ds["B04"].isel({time_dim: i}).values.astype(np.float32)
            g = ds["B03"].isel({time_dim: i}).values.astype(np.float32)
            b = ds["B02"].isel({time_dim: i}).values.astype(np.float32)
            rgb = np.dstack([
                robust_percentile_stretch(r),
                robust_percentile_stretch(g),
                robust_percentile_stretch(b),
            ])
            frames.append(to_uint8_rgb(rgb))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(out_path, frames, duration=max(1.0 / max(fps, 0.1), 0.05), loop=0)
    return True


def create_s1_gif(ds: xr.Dataset, out_path: Path, fps: float, step: int, max_frames: int):
    if not {"vv", "vh"}.issubset(ds.data_vars):
        return False

    time_dim = get_time_dim(ds["vv"])
    if time_dim is None:
        vv = ds["vv"].values.astype(np.float32)
        vh = ds["vh"].values.astype(np.float32)
        ratio = np.divide(vv, vh + 1e-6)
        rgb = np.dstack([
            robust_percentile_stretch(vv),
            robust_percentile_stretch(vh),
            robust_percentile_stretch(ratio),
        ])
        frames = [to_uint8_rgb(rgb)]
    else:
        n = ds.sizes[time_dim]
        frames = []
        for i in collect_time_indices(n, step, max_frames):
            vv = ds["vv"].isel({time_dim: i}).values.astype(np.float32)
            vh = ds["vh"].isel({time_dim: i}).values.astype(np.float32)
            ratio = np.divide(vv, vh + 1e-6)
            rgb = np.dstack([
                robust_percentile_stretch(vv),
                robust_percentile_stretch(vh),
                robust_percentile_stretch(ratio),
            ])
            frames.append(to_uint8_rgb(rgb))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(out_path, frames, duration=max(1.0 / max(fps, 0.1), 0.05), loop=0)
    return True


def create_static_pngs(ds: xr.Dataset, cube_out_dir: Path):
    dem_var = get_dem_var(ds)
    if dem_var is not None:
        dem = ds[dem_var]
        time_dim = get_time_dim(dem)
        dem_arr = dem.isel({time_dim: 0}).values.astype(np.float32) if time_dim else dem.values.astype(np.float32)
        save_array_png(dem_arr, cube_out_dir / "COPDEM" / "cop_dem.png", cmap="terrain")

    if "ESA_LC" in ds.data_vars:
        lc = ds["ESA_LC"]
        time_dim = get_time_dim(lc)
        lc_arr = lc.isel({time_dim: 0}).values.astype(np.float32) if time_dim else lc.values.astype(np.float32)
        save_array_png(lc_arr, cube_out_dir / "ESALC" / "land_cover.png", cmap="tab20")


def process_merged_cube(zarr_path: Path, out_root: Path, fps: float, step: int, max_frames: int):
    cube_out_dir = out_root / zarr_path.stem
    cube_out_dir.mkdir(parents=True, exist_ok=True)

    ds = xr.open_zarr(zarr_path, consolidated=True)
    try:
        s2_ok = create_s2_gif(ds, cube_out_dir / "S2L2A" / "s2l2a.gif", fps=fps, step=step, max_frames=max_frames)
        s1_ok = create_s1_gif(ds, cube_out_dir / "S1RTC" / "s1rtc.gif", fps=fps, step=step, max_frames=max_frames)
        create_static_pngs(ds, cube_out_dir)

        status = []
        status.append("S2L2A:gif" if s2_ok else "S2L2A:missing")
        status.append("S1RTC:gif" if s1_ok else "S1RTC:missing")
        status.append("COPDEM:png")
        status.append("ESALC:png")
        print(f"Saved {zarr_path.name} -> {cube_out_dir} ({', '.join(status)})")
    finally:
        ds.close()


def main():
    parser = argparse.ArgumentParser(description="Create GIF previews from merged datacubes")
    parser.add_argument(
        "--merged-dir",
        required=True,
        help="Directory with merged .zarr cubes",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output root directory for previews",
    )
    parser.add_argument("--fps", type=float, default=4.0, help="Frames per second for GIFs")
    parser.add_argument("--step", type=int, default=1, help="Use every Nth frame")
    parser.add_argument("--max-frames", type=int, default=0, help="Limit number of frames (0 = all)")
    args = parser.parse_args()

    merged_dir = Path(args.merged_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not merged_dir.exists():
        raise FileNotFoundError(f"Merged directory not found: {merged_dir}")

    merged_zarrs = sorted(merged_dir.glob("*.zarr"))
    if not merged_zarrs:
        print(f"No merged cubes found in {merged_dir}")
        return

    for zarr_path in merged_zarrs:
        try:
            process_merged_cube(
                zarr_path=zarr_path,
                out_root=out_dir,
                fps=args.fps,
                step=args.step,
                max_frames=args.max_frames,
            )
        except Exception as exc:
            print(f"Failed {zarr_path.name}: {exc}")


if __name__ == "__main__":
    main()
