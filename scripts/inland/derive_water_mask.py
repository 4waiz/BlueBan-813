"""Derive and validate the Shawka Dam water mask against an EnMAP scene.

Usage (from the project root):

    # 2022-09-08 scene: full, uncropped GeoTIFF -- windowed to the AOI here.
    python3 scripts/derive_water_mask.py \
        "sourced data/ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z-SPECTRAL_IMAGE_COG.tiff" \
        20220908

    # 2024-04-24 scene: already cropped to the AOI locally (scripts/crop_enmap_scene.py,
    # run on the project owner's machine -- the full 421,431,498-byte original exceeds
    # this environment's per-file staging cap and was never brought in whole). Same
    # windowing logic, just already applied, so pass --precropped to skip re-windowing.
    python3 scripts/derive_water_mask.py \
        "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff" \
        20240424 --precropped

Requires: rasterio, numpy, scipy (`pip install rasterio scipy numpy`).

What this does, in order:
1. Opens the GeoTIFF. If not already cropped, windows it to the locked AOI
   polygon (aoi/shawka_dam.geojson) plus a 150 m buffer, matching the crop
   scripts/crop_enmap_scene.py uses standalone.
2. Builds a per-pixel point-in-polygon mask against the *exact* locked
   polygon (not its bbox).
3. Runs pipeline.water_mask.water_mask() with its UNCHANGED default
   thresholds (not re-tuned per date -- the point of running the same
   function against both scenes is that they stay comparable).
4. Reports whether any candidate pixel falls outside the locked polygon
   (a leakage/sanity check, not assumed).
5. Saves the mask, brightness array, and a derivation-stats JSON to
   data/water_mask/enmap_<date>_*.

See docs/WATER_MASK.md for the full write-up, including the two-date
comparison and what it does and doesn't support.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.water_mask import water_mask, band_groups  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AOI_GEOJSON = PROJECT_ROOT / "aoi" / "shawka_dam.geojson"
OUT_DIR = PROJECT_ROOT / "data" / "water_mask"
BUFFER_M = 150.0


def point_in_poly(x: float, y: float, poly: list[list[float]]) -> bool:
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("geotiff", help="Path to the EnMAP L2A GeoTIFF (relative to project root)")
    ap.add_argument("date_label", help="e.g. 20220908 -- used to name output files")
    ap.add_argument("--precropped", action="store_true",
                     help="Skip AOI windowing; the file is already cropped to the AOI+buffer "
                          "(e.g. by scripts/crop_enmap_scene.py).")
    args = ap.parse_args()

    geotiff_path = PROJECT_ROOT / args.geotiff

    with open(AOI_GEOJSON) as f:
        gj = json.load(f)
    geom4326 = gj["features"][0]["geometry"]
    lons = [p[0] for p in geom4326["coordinates"][0]]
    lats = [p[1] for p in geom4326["coordinates"][0]]

    with rasterio.open(geotiff_path) as ds:
        crs = ds.crs
        if args.precropped:
            cube = ds.read()
            nodata = ds.nodata
            win_transform = ds.transform
        else:
            left, bottom, right, top = transform_bounds(
                "EPSG:4326", crs, min(lons), min(lats), max(lons), max(lats))
            win = from_bounds(left - BUFFER_M, bottom - BUFFER_M, right + BUFFER_M, top + BUFFER_M,
                               transform=ds.transform).round_offsets().round_lengths()
            cube = ds.read(window=win)
            nodata = ds.nodata
            win_transform = ds.window_transform(win)

    geom_proj = transform_geom("EPSG:4326", crs, geom4326)
    poly = geom_proj["coordinates"][0]

    rows, cols = cube.shape[1], cube.shape[2]
    a, b, c, d, e, f = win_transform[:6]
    inside = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        for cc in range(cols):
            x = a * (cc + 0.5) + b * (r + 0.5) + c
            y = d * (cc + 0.5) + e * (r + 0.5) + f
            inside[r, cc] = point_in_poly(x, y, poly)

    result = water_mask(cube, nodata)   # unchanged default thresholds
    groups = band_groups(cube, nodata)

    n_inside_poly = int(inside.sum())
    n_water_total = int(result.mask.sum())
    n_water_inside = int((result.mask & inside).sum())
    n_water_outside = int((result.mask & ~inside).sum())

    print(f"Scene: {args.date_label} ({'precropped' if args.precropped else 'windowed here'})")
    print(f"AOI window: {rows}x{cols} px, {n_inside_poly} inside locked polygon")
    print(f"Bad (nodata-carrying) bands dropped: {groups.bad_band_idx.tolist()} "
          f"({len(groups.bad_band_idx)} of {cube.shape[0]})")
    print(f"Water mask (raw): {result.stats['px_water_raw']} px")
    print(f"Water mask (after component filter, min_component_px="
          f"{result.min_component_px}): {n_water_total} px")
    print(f"  inside locked polygon: {n_water_inside}")
    print(f"  OUTSIDE locked polygon (leakage check): {n_water_outside}")
    if n_inside_poly:
        print(f"  wet fraction of AOI polygon: "
              f"{100 * n_water_inside / n_inside_poly:.1f}%")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.save(OUT_DIR / f"enmap_{args.date_label}_mask.npy", result.mask)
    np.save(OUT_DIR / f"enmap_{args.date_label}_brightness.npy", result.brightness)
    with open(OUT_DIR / f"enmap_{args.date_label}_derivation_stats.json", "w") as fh:
        json.dump({
            "date_label": args.date_label,
            "geotiff": str(args.geotiff),
            "precropped": args.precropped,
            "window_shape": [rows, cols],
            "px_inside_locked_polygon": n_inside_poly,
            "px_water_final": n_water_total,
            "px_water_inside_polygon": n_water_inside,
            "px_water_outside_polygon": n_water_outside,
            "wet_fraction_of_polygon_pct": (100 * n_water_inside / n_inside_poly) if n_inside_poly else None,
            **result.stats,
        }, fh, indent=1)
    print(f"\nSaved mask, brightness array, and derivation stats to {OUT_DIR}")


if __name__ == "__main__":
    main()
