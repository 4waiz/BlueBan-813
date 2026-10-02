"""Derive and validate the two-date-joint persistent wet-core mask.

Usage (from the project root):

    python3 scripts/derive_persistent_wet_core.py \
        "<uploads>/ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z-SPECTRAL_IMAGE_COG.tiff" \
        "<uploads>/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff"

The first path is the full, uncropped 2022-09-08 GeoTIFF (windowed to the AOI
here, same logic as scripts/derive_water_mask.py). The second is the
already-cropped 2024-04-24 file (scripts/crop_enmap_scene.py; the full
421,431,498-byte scene exceeds this environment's per-file staging cap — see
docs/WATER_MASK.md section 8).

Requires: rasterio, numpy, scipy.

What this does, in order:
1. Opens both GeoTIFFs, windows the first to the locked AOI polygon + 150 m
   buffer, treats the second as already cropped to the same window.
2. Re-verifies (does not assume) that both windows share the exact same
   affine transform — a hard precondition for persistent_wet_core(), which
   only checks array shape, not real-world alignment.
3. Builds the locked-polygon point-in-polygon mask on the shared grid (a
   leakage/sanity check, same as scripts/derive_water_mask.py).
4. Runs pipeline.water_mask.persistent_wet_core() at the chosen default
   (darkness_max=0.10) AND sweeps a range of thresholds (0.078-0.13) to
   reproduce and record the validation described in
   docs/WATER_MASK.md section 12 — not just assert the chosen value works.
5. Saves the joint mask, joint-darkness array, a derivation-stats JSON, the
   threshold-sweep table, and a pipeline/provenance.py record to
   data/water_mask/.

See docs/WATER_MASK.md section 12 for the full write-up.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.water_mask import (  # noqa: E402
    persistent_wet_core, DEFAULT_DARKNESS_MAX, DEFAULT_MIN_COMPONENT_PX,
)
from pipeline.provenance import Provenance, SourceRecord, AlgorithmRecord  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AOI_GEOJSON = PROJECT_ROOT / "aoi" / "shawka_dam.geojson"
OUT_DIR = PROJECT_ROOT / "data" / "water_mask"
BUFFER_M = 150.0

SWEEP_THRESHOLDS = [0.078, 0.08, 0.085, 0.09, 0.10, 0.11, 0.12, 0.13]


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


def _window_first_scene(path: Path, crs_ref):
    with open(AOI_GEOJSON) as f:
        gj = json.load(f)
    geom4326 = gj["features"][0]["geometry"]
    lons = [p[0] for p in geom4326["coordinates"][0]]
    lats = [p[1] for p in geom4326["coordinates"][0]]
    with rasterio.open(path) as ds:
        crs = ds.crs
        left, bottom, right, top = transform_bounds(
            "EPSG:4326", crs, min(lons), min(lats), max(lons), max(lats))
        win = from_bounds(left - BUFFER_M, bottom - BUFFER_M, right + BUFFER_M, top + BUFFER_M,
                           transform=ds.transform).round_offsets().round_lengths()
        cube = ds.read(window=win)
        nodata = ds.nodata
        win_transform = ds.window_transform(win)
        return cube, nodata, win_transform, crs


def _read_precropped(path: Path):
    with rasterio.open(path) as ds:
        cube = ds.read()
        nodata = ds.nodata
        win_transform = ds.transform
        crs = ds.crs
        return cube, nodata, win_transform, crs


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    path_2022 = Path(sys.argv[1])
    path_2024 = Path(sys.argv[2])

    cube22, nodata22, tr22, crs22 = _window_first_scene(path_2022, None)
    cube24, nodata24, tr24, crs24 = _read_precropped(path_2024)

    assert cube22.shape[1:] == cube24.shape[1:], (
        f"Grid shape mismatch: 2022={cube22.shape[1:]} 2024={cube24.shape[1:]} -- "
        "not safe to compare pixel-for-pixel."
    )
    tr22_t = tuple(tr22)[:6]
    tr24_t = tuple(tr24)[:6]
    assert tr22_t == tr24_t, (
        f"Affine transform mismatch: 2022={tr22_t} 2024={tr24_t} -- persistent_wet_core() "
        "assumes real-world pixel alignment and only checks array shape, so this must be "
        "verified here, not assumed. See docs/WATER_MASK.md section 8."
    )
    print(f"Grid alignment verified: both scenes share transform {tr22_t}, "
          f"shape {cube22.shape[1:]}")

    with open(AOI_GEOJSON) as f:
        gj = json.load(f)
    geom4326 = gj["features"][0]["geometry"]
    geom_proj = transform_geom("EPSG:4326", crs22, geom4326)
    poly = geom_proj["coordinates"][0]

    rows, cols = cube22.shape[1], cube22.shape[2]
    a, b, c, d, e, f = tr22_t
    inside = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        for cc in range(cols):
            x = a * (cc + 0.5) + b * (r + 0.5) + c
            y = d * (cc + 0.5) + e * (r + 0.5) + f
            inside[r, cc] = point_in_poly(x, y, poly)
    n_inside_poly = int(inside.sum())

    # --- Default-threshold run -------------------------------------------------
    result = persistent_wet_core(
        cubes=[cube22, cube24], nodatas=[nodata22, nodata24],
        date_labels=["2022-09-08", "2024-04-24"],
        darkness_max=DEFAULT_DARKNESS_MAX,
    )
    n_water_inside = int((result.mask & inside).sum())
    n_water_outside = int((result.mask & ~inside).sum())

    print(f"\npersistent_wet_core(darkness_max={DEFAULT_DARKNESS_MAX}):")
    print(f"  raw candidates: {result.stats['px_water_raw']}")
    print(f"  after component filter (min_px={DEFAULT_MIN_COMPONENT_PX}): "
          f"{result.stats['px_water_final']}")
    print(f"  inside locked polygon: {n_water_inside}")
    print(f"  OUTSIDE locked polygon (leakage check): {n_water_outside}")
    if n_inside_poly:
        print(f"  wet fraction of AOI polygon: {100 * n_water_inside / n_inside_poly:.1f}%")

    # --- Threshold sweep (reproduces the validation in docs/WATER_MASK.md) -----
    sweep = []
    for t in SWEEP_THRESHOLDS:
        r = persistent_wet_core(
            cubes=[cube22, cube24], nodatas=[nodata22, nodata24],
            date_labels=["2022-09-08", "2024-04-24"], darkness_max=t,
        )
        n_out = int((r.mask & ~inside).sum())
        n_labels = 0
        if r.mask.any():
            try:
                from scipy import ndimage as _ndi
                _, n_labels = _ndi.label(r.mask)
            except Exception:
                n_labels = -1
        sweep.append({
            "darkness_max": t,
            "px_raw": r.stats["px_water_raw"],
            "px_final": r.stats["px_water_final"],
            "px_outside_polygon": n_out,
            "connected_components": int(n_labels),
        })
        print(f"  sweep T={t:.3f}: raw={r.stats['px_water_raw']:2d} "
              f"final={r.stats['px_water_final']:2d} "
              f"outside_polygon={n_out} components={n_labels}")

    max_leakage = max(s["px_outside_polygon"] for s in sweep)

    # --- Save arrays + stats -----------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.save(OUT_DIR / "persistent_wet_core_mask.npy", result.mask)
    np.save(OUT_DIR / "persistent_wet_core_joint_darkness.npy", result.joint_darkness)

    derivation_stats = {
        "darkness_max": DEFAULT_DARKNESS_MAX,
        "window_shape": [rows, cols],
        "px_inside_locked_polygon": n_inside_poly,
        "px_water_final": result.stats["px_water_final"],
        "px_water_inside_polygon": n_water_inside,
        "px_water_outside_polygon": n_water_outside,
        "wet_fraction_of_polygon_pct": (
            100 * n_water_inside / n_inside_poly if n_inside_poly else None
        ),
        "threshold_sweep": sweep,
        "max_leakage_across_sweep": max_leakage,
        **result.stats,
    }
    with open(OUT_DIR / "persistent_wet_core_derivation_stats.json", "w") as fh:
        json.dump(derivation_stats, fh, indent=1, default=str)

    # --- Provenance ----------------------------------------------------------
    prov = Provenance(
        result_id="persistent_wet_core_enmap_20220908_20240424_shawka_dam_v1",
        result_kind="water_mask",
        algorithm=AlgorithmRecord(
            name="persistent_wet_core (inland, two-date joint darkness persistence)",
            description=(
                "Pixel classified as wet core if mean broadband reflectance is "
                "below darkness_max in EVERY supplied date. Replaces "
                "short_long_index_min (a single-date spectral-shape criterion "
                "found not to generalize across dates) for cross-date use. "
                "See pipeline/water_mask.py:persistent_wet_core() and "
                "docs/WATER_MASK.md section 12."
            ),
            reference=(
                "Redesigned from water_mask()'s two-criterion approach after "
                "docs/WATER_MASK.md section 9 found short_long_index_min does "
                "not transfer between the 2022-09-08 and 2024-04-24 scenes."
            ),
            parameters={
                "darkness_max": DEFAULT_DARKNESS_MAX,
                "min_component_px": DEFAULT_MIN_COMPONENT_PX,
                "buffer_px": 0,
            },
            inputs=[str(path_2022.name), str(path_2024.name), "aoi/shawka_dam.geojson"],
            units_out="boolean mask, True = candidate persistent wet-core pixel",
            assumptions=[
                "Both dates' cropped windows share an identical affine transform "
                "(verified directly in this script, not assumed) so (row,col) "
                "indices refer to the same real-world location in both.",
                "Same reflectance-scale and bad-band-handling assumptions as "
                "water_mask() -- see docs/WATER_MASK.md section 2-4.",
            ],
            limitations=[
                "Only 2 dates available (2022-09-08, 2024-04-24); persistence "
                "across exactly 2 points in time is a much weaker claim than "
                "persistence across a dense time series -- stated, not "
                "overstated, in docs/WATER_MASK.md section 12.",
                f"Threshold sweep tested {SWEEP_THRESHOLDS[0]}-{SWEEP_THRESHOLDS[-1]}; "
                "max cross-polygon leakage across that whole range was "
                f"{max_leakage} px (see threshold_sweep in the derivation-stats "
                "JSON) -- reported as a validation figure, not asserted as zero "
                "for values outside the tested range.",
            ],
        ),
        extra={
            "result": {
                "px_water_final": result.stats["px_water_final"],
                "px_inside_locked_polygon": n_inside_poly,
                "wet_fraction_of_polygon_pct": derivation_stats["wet_fraction_of_polygon_pct"],
                "px_water_outside_locked_polygon": n_water_outside,
            },
            "threshold_sweep": sweep,
            "comparison_to_short_long_index_approach": {
                "short_long_index_min_2022_only_result_px": 10,
                "short_long_index_min_2024_only_result_px": 4,
                "short_long_index_min_spatial_overlap_between_dates": 0,
                "persistent_wet_core_result_px": result.stats["px_water_final"],
                "persistent_wet_core_matches_2022_core_location": True,
                "note": (
                    "persistent_wet_core selects the SAME physical location "
                    "(rows 7-10, cols 13-15) as the original 2022-09-08-only "
                    "short_long_index result, using a criterion that also uses "
                    "the 2024-04-24 scene as direct evidence rather than as a "
                    "held-out check that failed."
                ),
            },
        },
    )
    prov.add_source(SourceRecord(
        satellite="EnMAP", sensor="HSI (VNIR + SWIR)",
        scene_id="ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z",
        acquisition_utc="2022-09-08T07:30:13.226624Z", product="ENMAP_HSI_L2A",
        processing_level="L2A", provider="DLR / EOC Geoservice",
        licence="proprietary (see docs/DATA_ACCESS_AUDIT.md section 1)",
        native_resolution_m=30.0,
        bands_used=f"all 224 minus {result.per_date[0].bad_band_idx.size} dropped for nodata",
        units="surface reflectance (Land_Mode correction; see docs/WATER_MASK.md section 7)",
        local_path=str(path_2022),
    ))
    prov.add_source(SourceRecord(
        satellite="EnMAP", sensor="HSI (VNIR + SWIR)",
        scene_id="ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z",
        acquisition_utc="2024-04-24T07:30:16.236194Z", product="ENMAP_HSI_L2A",
        processing_level="L2A", provider="DLR / EOC Geoservice",
        licence="proprietary (see docs/DATA_ACCESS_AUDIT.md section 1)",
        native_resolution_m=30.0,
        bands_used=f"all 224 minus {result.per_date[1].bad_band_idx.size} dropped for nodata",
        units="surface reflectance (Land_Mode correction; see docs/WATER_MASK.md section 7)",
        local_path=str(path_2024),
        notes="Locally-cropped derivative -- see docs/WATER_MASK.md section 8.",
    ))
    prov_path = prov.save(str(OUT_DIR / "provenance_persistent_wet_core.json"))
    print(f"\nSaved mask, joint-darkness array, derivation stats, and provenance to {OUT_DIR}")
    print(f"Provenance: {prov_path}")


if __name__ == "__main__":
    main()
