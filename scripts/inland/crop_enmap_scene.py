"""Crop a full EnMAP L2A GeoTIFF down to the Shawka Dam AOI (+ buffer), locally.

Why this script exists: the 2024-04-24 scene
(ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-
SPECTRAL_IMAGE_COG.tiff, 421,431,498 bytes) is over this Cowork session's
~400 MiB per-file device-staging cap, and the local shell this session would
normally use to crop it in place on your machine (device_bash) is currently
blocked by a tracked Windows-mount issue. This script does the same crop
`scripts/derive_water_mask.py` does internally for the 2022-09-08 scene —
window to the locked AOI polygon plus a 150 m buffer, same as the sampled
window already validated for that scene — but as a standalone step you can
run locally and then hand the small output file back.

Usage (from the project root, i.e. 813-inland-standalone-complement/):

    pip install rasterio
    python3 scripts/crop_enmap_scene.py ^
        "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-SPECTRAL_IMAGE_COG.tiff" ^
        "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff"

(use `\` instead of `^` for line continuation if running in a non-Windows
shell / WSL / git-bash)

Output: a new GeoTIFF, same CRS/georeferencing/dtype/nodata/band count as the
input, windowed down to just the AOI + buffer (the same ~25x30 px window size
the 2022-09-08 scene produced). Should be a few hundred KB to a few MB, not
hundreds of MB — well under the staging cap. Drop the result back into
`sourced data/` (or wherever's convenient) and it can be staged normally.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AOI_GEOJSON = PROJECT_ROOT / "aoi" / "shawka_dam.geojson"
BUFFER_M = 150.0   # same buffer used for the 2022-09-08 scene's sampled window


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python3 crop_enmap_scene.py <input_geotiff> <output_geotiff>")
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    with open(AOI_GEOJSON) as f:
        gj = json.load(f)
    coords = gj["features"][0]["geometry"]["coordinates"][0]
    lons = [p[0] for p in coords]
    lats = [p[1] for p in coords]

    with rasterio.open(in_path) as src:
        print(f"Input: {in_path.name}")
        print(f"  size on disk: {in_path.stat().st_size:,} bytes")
        print(f"  bands: {src.count}, shape: {src.width}x{src.height}, dtype: {src.dtypes[0]}, crs: {src.crs}")

        left, bottom, right, top = transform_bounds(
            "EPSG:4326", src.crs, min(lons), min(lats), max(lons), max(lats))
        win = from_bounds(left - BUFFER_M, bottom - BUFFER_M, right + BUFFER_M, top + BUFFER_M,
                           transform=src.transform).round_offsets().round_lengths()

        print(f"  crop window: col_off={win.col_off} row_off={win.row_off} "
              f"width={win.width} height={win.height}")

        data = src.read(window=win)
        win_transform = src.window_transform(win)

        profile = src.profile.copy()
        profile.update({
            "height": win.height,
            "width": win.width,
            "transform": win_transform,
        })

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data)

    out_bytes = out_path.stat().st_size
    print(f"\nOutput: {out_path}")
    print(f"  size on disk: {out_bytes:,} bytes ({out_bytes / (1024*1024):.2f} MiB)")
    if out_bytes < 400 * 1024 * 1024:
        print("  -> under the ~400 MiB staging cap, should transfer fine.")
    else:
        print("  -> STILL over the ~400 MiB staging cap. Report this back rather than "
              "guessing at a further workaround (e.g. smaller buffer, band subset).")


if __name__ == "__main__":
    main()
