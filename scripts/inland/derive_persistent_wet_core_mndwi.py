"""Derive and validate the REAL-BAND MNDWI persistent wet-core mask, and
compare it directly against the band-GROUPS persistent_wet_core() result.

Usage (from the project root):

    python3 scripts/derive_persistent_wet_core_mndwi.py \
        "<uploads>/...20220908...SPECTRAL_IMAGE_COG.tiff" \
        "<uploads>/...20240424...AOI_CROP.tiff"

Same two inputs as scripts/derive_persistent_wet_core.py. Requires
data/metadata/enmap_band_characterisation.json (see docs/WATER_MASK.md
section 14 for how it was obtained and verified).

What this does:
1. Rebuilds the two aligned cubes (same windowing as
   scripts/derive_persistent_wet_core.py) and re-verifies grid alignment.
2. Loads the real per-band wavelength table and runs
   pipeline.water_mask.persistent_wet_core_mndwi() at the literature
   default (mndwi_min=0.0), plus a threshold sweep over this AOI's own
   MNDWI distribution.
3. Re-runs pipeline.water_mask.persistent_wet_core() (the band-GROUPS
   version) on the SAME cubes so the comparison is apples-to-apples in
   this one script run, not against a possibly-stale saved array.
4. Reports the direct comparison: same pixels, different pixels, or no
   overlap -- printed plainly, not smoothed over either way.
5. Saves both results, the sweep, and a provenance record to
   data/water_mask/.
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
    persistent_wet_core, persistent_wet_core_mndwi, load_band_characterisation,
    DEFAULT_DARKNESS_MAX,
)
from pipeline.provenance import Provenance, SourceRecord, AlgorithmRecord  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AOI_GEOJSON = PROJECT_ROOT / "aoi" / "shawka_dam.geojson"
BAND_TABLE = PROJECT_ROOT / "data" / "metadata" / "enmap_band_characterisation.json"
OUT_DIR = PROJECT_ROOT / "data" / "water_mask"
BUFFER_M = 150.0

MNDWI_SWEEP = [-0.1, -0.05, -0.02, 0.0, 0.02, 0.05, 0.1, 0.15, 0.2]


def point_in_poly(x, y, poly):
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


def _window_first_scene(path: Path):
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
        return cube, ds.nodata, ds.window_transform(win), crs


def _read_precropped(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(), ds.nodata, ds.transform, ds.crs


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    path_2022, path_2024 = Path(sys.argv[1]), Path(sys.argv[2])

    cube22, nodata22, tr22, crs22 = _window_first_scene(path_2022)
    cube24, nodata24, tr24, crs24 = _read_precropped(path_2024)
    assert cube22.shape[1:] == cube24.shape[1:], "grid mismatch"
    assert tuple(tr22)[:6] == tuple(tr24)[:6], "transform mismatch -- see docs/WATER_MASK.md section 8"
    print(f"Grid alignment verified: {tuple(tr22)[:6]}, shape {cube22.shape[1:]}")

    cubes = [cube22, cube24]
    nodatas = [nodata22, nodata24]
    labels = ["2022-09-08", "2024-04-24"]

    with open(AOI_GEOJSON) as f:
        gj = json.load(f)
    geom_proj = transform_geom("EPSG:4326", crs22, gj["features"][0]["geometry"])
    poly = geom_proj["coordinates"][0]
    rows, cols = cube22.shape[1], cube22.shape[2]
    a, b, c, d, e, f = tuple(tr22)[:6]
    inside = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        for cc in range(cols):
            x = a * (cc + 0.5) + b * (r + 0.5) + c
            y = d * (cc + 0.5) + e * (r + 0.5) + f
            inside[r, cc] = point_in_poly(x, y, poly)
    n_inside_poly = int(inside.sum())

    bands = load_band_characterisation(str(BAND_TABLE))
    print(f"Loaded {len(bands)} bands from {BAND_TABLE.name}")

    # --- Real MNDWI, default threshold (literature convention 0.0) --------
    mndwi_result = persistent_wet_core_mndwi(cubes, nodatas, bands, date_labels=labels, mndwi_min=0.0)
    n_mndwi_inside = int((mndwi_result.mask & inside).sum())
    n_mndwi_outside = int((mndwi_result.mask & ~inside).sum())
    print(f"\npersistent_wet_core_mndwi(mndwi_min=0.0):")
    print(f"  green band: {mndwi_result.stats['green_nm_actual']:.2f} nm "
          f"(offset {mndwi_result.stats['green_offset_nm']:.2f} nm from 560 nm target)")
    print(f"  swir1 band: {mndwi_result.stats['swir1_nm_actual']:.2f} nm "
          f"(offset {mndwi_result.stats['swir1_offset_nm']:.2f} nm from 1610 nm target)")
    print(f"  raw candidates: {mndwi_result.stats['px_water_raw']}")
    print(f"  final (after component filter): {mndwi_result.stats['px_water_final']}")
    print(f"  inside locked polygon: {n_mndwi_inside}")
    print(f"  OUTSIDE locked polygon (leakage check): {n_mndwi_outside}")

    # --- Threshold sweep on this AOI's own MNDWI distribution --------------
    sweep = []
    for t in MNDWI_SWEEP:
        r = persistent_wet_core_mndwi(cubes, nodatas, bands, date_labels=labels, mndwi_min=t)
        n_out = int((r.mask & ~inside).sum())
        n_comp = 0
        if r.mask.any():
            from scipy import ndimage as _ndi
            _, n_comp = _ndi.label(r.mask)
        sweep.append({"mndwi_min": t, "px_raw": r.stats["px_water_raw"],
                      "px_final": r.stats["px_water_final"], "px_outside_polygon": n_out,
                      "connected_components": int(n_comp)})
        print(f"  sweep mndwi_min={t:+.2f}: raw={r.stats['px_water_raw']:2d} "
              f"final={r.stats['px_water_final']:2d} outside_polygon={n_out} components={n_comp}")

    # --- Re-run the band-GROUPS version on the SAME cubes for a fair compare
    group_result = persistent_wet_core(cubes, nodatas, labels, darkness_max=DEFAULT_DARKNESS_MAX)
    n_group_inside = int((group_result.mask & inside).sum())

    overlap = int((mndwi_result.mask & group_result.mask).sum())
    only_mndwi = int((mndwi_result.mask & ~group_result.mask).sum())
    only_group = int((group_result.mask & ~mndwi_result.mask).sum())
    group_rr, group_cc = np.where(group_result.mask)
    mndwi_rr, mndwi_cc = np.where(mndwi_result.mask)

    print(f"\n=== Direct comparison: real-band MNDWI vs. band-GROUPS persistent_wet_core ===")
    print(f"Band-GROUPS result (darkness_max={DEFAULT_DARKNESS_MAX}): {group_result.stats['px_water_final']} px "
          f"at {list(zip(group_rr.tolist(), group_cc.tolist()))}")
    print(f"Real-MNDWI result (mndwi_min=0.0): {mndwi_result.stats['px_water_final']} px "
          f"at {list(zip(mndwi_rr.tolist(), mndwi_cc.tolist()))}")
    print(f"Pixels in both: {overlap}")
    print(f"Pixels only in MNDWI result: {only_mndwi}")
    print(f"Pixels only in GROUPS result: {only_group}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    np.save(OUT_DIR / "persistent_wet_core_mndwi_mask.npy", mndwi_result.mask)
    np.save(OUT_DIR / "persistent_wet_core_mndwi_joint_min.npy", mndwi_result.joint_mndwi_min)

    comparison = {
        "band_groups_result": {
            "px_final": group_result.stats["px_water_final"],
            "pixels_rc": list(zip(group_rr.tolist(), group_cc.tolist())),
        },
        "real_mndwi_result": {
            "px_final": mndwi_result.stats["px_water_final"],
            "pixels_rc": list(zip(mndwi_rr.tolist(), mndwi_cc.tolist())),
            "green_nm_actual": mndwi_result.stats["green_nm_actual"],
            "swir1_nm_actual": mndwi_result.stats["swir1_nm_actual"],
        },
        "overlap_px": overlap, "only_mndwi_px": only_mndwi, "only_groups_px": only_group,
        "mndwi_threshold_sweep": sweep,
        "px_inside_locked_polygon": n_inside_poly,
    }
    with open(OUT_DIR / "persistent_wet_core_mndwi_comparison.json", "w") as fh:
        json.dump(comparison, fh, indent=1, default=str)

    prov = Provenance(
        result_id="persistent_wet_core_mndwi_enmap_20220908_20240424_shawka_dam_v1",
        result_kind="water_mask",
        algorithm=AlgorithmRecord(
            name="persistent_wet_core_mndwi (real-band MNDWI, two-date persistence)",
            description=(
                "Xu (2006) MNDWI ((Green-SWIR1)/(Green+SWIR1)) using the real EnMAP "
                "bands nearest 560 nm / 1610 nm, with the same two-date persistence "
                "structure as persistent_wet_core(). Compared directly against that "
                "band-GROUPS result -- see docs/WATER_MASK.md section 14."
            ),
            reference="Xu, H. (2006). Modification of normalised difference water index (MNDWI). Int. J. Remote Sens.",
            parameters={"mndwi_min": 0.0, "green_nm_target": 560.0, "swir1_nm_target": 1610.0,
                       "green_nm_actual": mndwi_result.stats["green_nm_actual"],
                       "swir1_nm_actual": mndwi_result.stats["swir1_nm_actual"]},
            inputs=[str(path_2022.name), str(path_2024.name), "aoi/shawka_dam.geojson",
                   "data/metadata/enmap_band_characterisation.json"],
            units_out="boolean mask, True = candidate persistent wet-core pixel",
            assumptions=[
                "Band index in the GeoTIFF corresponds 1:1, in order, to the eo:bands "
                "array index from the STAC item -- standard STAC eo-extension convention, "
                "not independently re-verified against the file's own internal band "
                "descriptors (which don't exist -- see docs/WATER_MASK.md section 2).",
                "mndwi_min=0.0 is Xu (2006)'s literature-standard threshold, not fit to "
                "this AOI -- see the threshold sweep in this record's extra field for how "
                "sensitive the result is to that choice at this AOI.",
            ],
            limitations=[
                "Wavelength table itself is verified by cross-validation across two "
                "independent STAC fetches (see data/metadata/enmap_band_characterisation.json "
                "and docs/WATER_MASK.md section 14), not by an independently obtained second "
                "document (e.g. the product's own METADATA.XML, still not downloaded).",
            ],
        ),
        extra=comparison,
    )
    for path, nodata, acq, label in [
        (path_2022, nodata22, "2022-09-08T07:30:13.226624Z", "2022-09-08"),
        (path_2024, nodata24, "2024-04-24T07:30:16.236194Z", "2024-04-24"),
    ]:
        prov.add_source(SourceRecord(
            satellite="EnMAP", sensor="HSI (VNIR + SWIR)", scene_id=path.name,
            acquisition_utc=acq, product="ENMAP_HSI_L2A", processing_level="L2A",
            provider="DLR / EOC Geoservice", licence="proprietary",
            native_resolution_m=30.0, local_path=str(path),
        ))
    prov_path = prov.save(str(OUT_DIR / "provenance_persistent_wet_core_mndwi.json"))
    print(f"\nSaved MNDWI mask, comparison, and provenance to {OUT_DIR}")
    print(f"Provenance: {prov_path}")


if __name__ == "__main__":
    main()
