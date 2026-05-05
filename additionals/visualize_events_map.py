"""
Produce 3 static PNG maps — one per source CSV:
  - map_EMDAT.png
  - map_GLOBAL.png
  - map_WOCAT.png
"""

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import geopandas as gpd
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
OUT_DIR  = Path(__file__).parent

import geodatasets

# land polygons + country borders (loaded once, reused for all maps)
land     = gpd.read_file(geodatasets.get_path("naturalearth.land"))
# country borders: download 110m admin-0 shapefile from Natural Earth
_borders_url = (
    "https://naciscdn.org/naturalearth/110m/cultural/"
    "ne_110m_admin_0_countries.zip"
)
import urllib.request, zipfile, io, tempfile, os

_cache = Path.home() / ".cache" / "geodatasets" / "ne_110m_admin_0_countries"
if not _cache.exists():
    print("Downloading country borders …")
    _cache.mkdir(parents=True, exist_ok=True)
    data, _ = urllib.request.urlretrieve(_borders_url, _cache / "countries.zip")
    with zipfile.ZipFile(_cache / "countries.zip") as zf:
        zf.extractall(_cache)
countries = gpd.read_file(next(_cache.glob("*.shp")))

# ── dataset definitions ───────────────────────────────────────────────────────

DATASETS = {
    "EMDAT":  {"file": "ARCEME-DC-DHP-EMDAT.csv",  "color": "#2196F3", "title": "EMDAT extreme events"},
    "GLOBAL": {"file": "ARCEME-DC-DHP-GLOBAL.csv", "color": "#FF5722", "title": "GLOBAL extreme events"},
    "WOCAT":  {"file": "ARCEME-DC-DHP-WOCAT.csv",  "color": "#4CAF50", "title": "WOCAT extreme events"},
}

# ── plot each dataset ─────────────────────────────────────────────────────────

for name, cfg in DATASETS.items():
    df = pd.read_csv(DATA_DIR / cfg["file"])
    df = df.dropna(subset=["latitude", "longitude"])

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    land.plot(ax=ax, color="#e8e8e8", edgecolor="none")
    countries.boundary.plot(ax=ax, linewidth=0.35, color="#aaaaaa")

    ax.scatter(
        df["longitude"], df["latitude"],
        c=cfg["color"], s=22, alpha=0.75, linewidths=0.3,
        edgecolors="white", label="Event location", zorder=3,
    )

    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_xticks(range(-180, 181, 30))
    ax.set_yticks(range(-90, 91, 30))
    ax.tick_params(labelsize=7, color="#888888")
    ax.grid(True, linestyle="--", linewidth=0.3, color="#888888", alpha=0.5)

    ax.set_title(cfg["title"], fontsize=16, fontweight="bold", pad=12)
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude", fontsize=9)

    ax.legend(fontsize=9, loc="lower left", framealpha=0.9, markerscale=1.4)

    n = len(df)
    ax.text(0.99, 0.01, f"n = {n} events", transform=ax.transAxes,
            fontsize=8, ha="right", va="bottom", color="#555555")

    out = OUT_DIR / f"map_{name}.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out}  ({n} events)")

print("Done.")
