"""Run the anomaly (RX) and fingerprint layers over the validated wet core.

Usage (from the project root):

    python3 scripts/derive_anomaly_and_fingerprint.py \
        "<uploads>/...20220908...SPECTRAL_IMAGE_COG.tiff" \
        "<uploads>/...20240424...AOI_CROP.tiff"

Same two inputs as scripts/derive_persistent_wet_core.py. This script:

1. Rebuilds the two aligned cubes and the validated persistent-wet-core
   masks at two thresholds: darkness_max=0.10 (the chosen core, TEST
   population) and darkness_max=0.13 (the wider, still-zero-leakage
   population, BACKGROUND) -- see docs/WATER_MASK.md section 12. The 0.10
   mask is a strict subset of the 0.13 mask (the underlying criterion is
   monotonic in the threshold), so this is background >= test by
   construction, not two arbitrarily chosen populations.
2. Runs pipeline.anomaly.rx_anomaly() with that test/background pair,
   pooling both dates' spectra for the background (see that module's
   docstring for why).
3. Runs pipeline.fingerprint.fingerprint_pixel() for every test pixel in
   every date, using the SAME pooled background mean/std the anomaly layer
   used, plus that pixel's own RX score, threshold, and SAM value.
4. Runs pipeline.anomaly.extract_events() per date.
5. Saves a full JSON report and a provenance record to data/anomaly/.

See docs/ANOMALY_AND_FINGERPRINT.md for the write-up this script's output
feeds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.water_mask import persistent_wet_core, load_band_characterisation  # noqa: E402
from pipeline.anomaly import rx_anomaly, band_group_features, extract_events, DEFAULT_N_GROUPS  # noqa: E402
from pipeline.fingerprint import (  # noqa: E402
    fingerprint_pixel, CLASSES, local_band_depth,
    CYANO_LEFT_NM, CYANO_CENTRE_NM, CYANO_RIGHT_NM,
)
from pipeline.provenance import Provenance, SourceRecord, AlgorithmRecord  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AOI_GEOJSON = PROJECT_ROOT / "aoi" / "shawka_dam.geojson"
BAND_TABLE = PROJECT_ROOT / "data" / "metadata" / "enmap_band_characterisation.json"
OUT_DIR = PROJECT_ROOT / "data" / "anomaly"
BUFFER_M = 150.0


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
        return cube, ds.nodata


def _read_precropped(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(), ds.nodata


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    path_2022, path_2024 = Path(sys.argv[1]), Path(sys.argv[2])

    cube22, nodata22 = _window_first_scene(path_2022)
    cube24, nodata24 = _read_precropped(path_2024)
    assert cube22.shape[1:] == cube24.shape[1:], "grid mismatch -- see derive_persistent_wet_core.py"

    cubes = [cube22, cube24]
    nodatas = [nodata22, nodata24]
    labels = ["2022-09-08", "2024-04-24"]

    core_test = persistent_wet_core(cubes, nodatas, labels, darkness_max=0.10)
    core_bg = persistent_wet_core(cubes, nodatas, labels, darkness_max=0.13)
    is_subset = bool((core_test.mask & ~core_bg.mask).sum() == 0)
    print(f"Test mask (darkness_max=0.10): {int(core_test.mask.sum())} px")
    print(f"Background mask (darkness_max=0.13): {int(core_bg.mask.sum())} px")
    print(f"Test mask is a strict subset of background mask: {is_subset}")

    # --- Anomaly (RX) ----------------------------------------------------
    results = rx_anomaly(cubes, nodatas, test_mask=core_test.mask,
                         background_mask=core_bg.mask, date_labels=labels)

    # Pooled background mean/std in GROUP space (same grouping the anomaly
    # layer used), for the fingerprint layer's z-scores.
    Xb_list = []
    for cube, nodata in zip(cubes, nodatas):
        feats, _, _ = band_group_features(cube, nodata, n_groups=DEFAULT_N_GROUPS)
        flat = np.moveaxis(feats, 0, -1).reshape(-1, DEFAULT_N_GROUPS)
        bm = core_bg.mask.ravel()
        finite = np.isfinite(flat).all(axis=1)
        Xb_list.append(flat[bm & finite])
    Xb_all = np.concatenate(Xb_list, axis=0)
    bg_mean = Xb_all.mean(axis=0)
    bg_std = Xb_all.std(axis=0)
    print(f"\nPooled background group means: {np.round(bg_mean, 4).tolist()}")
    print(f"Pooled background group stds:  {np.round(bg_std, 4).tolist()}")

    # --- Real-band data for CYANO_LIKE (newly computable) ------------------
    bands = load_band_characterisation(str(BAND_TABLE))
    wl_nm = np.array([b["center_wavelength_nm"] for b in bands])

    def _real_spectrum(cube, nodata, r, c):
        """Per-pixel spectrum with nodata bands set to NaN (not dropped
        wholesale). EnMAP has ~5-6 bands that are nodata EVERYWHERE in this
        AOI window -- the water-vapor absorption gaps at ~1390-1449nm and
        ~1780-1967nm documented in docs/WATER_MASK.md section 12 -- so
        requiring an entire 224-band spectrum to be nodata-free would skip
        every pixel, even though those gap bands are nowhere near the
        600/620/650nm CYANO_LIKE window. local_band_depth()'s _mean_around()
        already drops non-finite samples per-window via np.isfinite(), so
        converting nodata -> NaN here (rather than skipping the pixel) lets
        it use whichever of the 600/620/650nm windows are actually populated
        for THIS pixel."""
        raw = cube[:, r, c].astype(np.float64)
        raw = np.where(raw == nodata, np.nan, raw)
        return raw / 10000.0

    # Background's own d620 distribution, pooled across both dates, over the
    # SAME background mask used for the group-based background above.
    d620_bg_values = []
    for cube, nodata in zip(cubes, nodatas):
        rr_bg, cc_bg = np.where(core_bg.mask)
        for r, c in zip(rr_bg, cc_bg):
            spec = _real_spectrum(cube, nodata, r, c)
            d = local_band_depth(wl_nm, spec, CYANO_LEFT_NM, CYANO_CENTRE_NM, CYANO_RIGHT_NM)
            if np.isfinite(d):
                d620_bg_values.append(d)
    d620_bg_values = np.array(d620_bg_values)
    bg_d620_mean = float(d620_bg_values.mean()) if d620_bg_values.size else float("nan")
    bg_d620_std = float(d620_bg_values.std()) if d620_bg_values.size else float("nan")
    print(f"\nBackground d620 (phycocyanin band-depth, {CYANO_LEFT_NM}/{CYANO_CENTRE_NM}/{CYANO_RIGHT_NM} nm): "
          f"n={d620_bg_values.size}, mean={bg_d620_mean:.5f}, std={bg_d620_std:.5f}")

    report = {
        "background_d620_mean": bg_d620_mean, "background_d620_std": bg_d620_std,
        "background_d620_n": int(d620_bg_values.size),
        "test_mask_px": int(core_test.mask.sum()),
        "background_mask_px": int(core_bg.mask.sum()),
        "background_is_superset_of_test": is_subset,
        "n_groups": DEFAULT_N_GROUPS,
        "background_group_means": bg_mean.tolist(),
        "background_group_stds": bg_std.tolist(),
        "per_date": {},
    }

    for cube, nodata, lbl in zip(cubes, nodatas, labels):
        res = results[lbl]
        feats, _, _ = band_group_features(cube, nodata, n_groups=DEFAULT_N_GROUPS)
        rr, cc = np.where(core_test.mask)
        pixel_reports = []
        for r, c in zip(rr, cc):
            gv = feats[:, r, c]
            sam_val = float(res.sam[r, c]) if np.isfinite(res.sam[r, c]) else None
            rx_val = float(res.score[r, c]) if np.isfinite(res.score[r, c]) else None
            real_spec = _real_spectrum(cube, nodata, r, c)
            d620_this = local_band_depth(wl_nm, real_spec, CYANO_LEFT_NM, CYANO_CENTRE_NM, CYANO_RIGHT_NM)
            fp = fingerprint_pixel(
                gv, bg_mean, bg_std, sam_value=sam_val,
                rx_score=rx_val, rx_threshold=res.threshold_score,
                real_wl_nm=wl_nm, real_spectrum=real_spec,
                background_d620_mean=bg_d620_mean, background_d620_std=bg_d620_std,
            )
            pixel_reports.append({
                "row": int(r), "col": int(c),
                "group_values": np.round(gv, 4).tolist(),
                "rx_score": rx_val, "rx_threshold": res.threshold_score,
                "sam_rad": sam_val,
                "d620_this_pixel": round(float(d620_this), 5) if np.isfinite(d620_this) else None,
                "fingerprint": fp.to_dict(),
            })

        events_mask, events = extract_events(res.score, res.pvalue, res.threshold_score,
                                             pixel_size_m=30.0, min_pixels=1, close_iterations=0)
        print(f"\n--- {lbl} ---")
        print(f"  RX result: {res.to_dict()}")
        print(f"  Events extracted: {len(events)}")
        for e in events:
            print(f"    label={e.label} px={e.pixel_count} centroid_rc={e.centroid_rc} "
                  f"mean_score={e.mean_score:.3f} max_score={e.max_score:.3f}")
        top_classes = [p["fingerprint"]["top_class"] for p in pixel_reports]
        from collections import Counter
        print(f"  Fingerprint top-class counts: {dict(Counter(top_classes))}")

        report["per_date"][lbl] = {
            "anomaly_result": res.to_dict(),
            "events": [
                {"label": e.label, "pixel_count": e.pixel_count, "area_km2": e.area_km2,
                 "centroid_rc": e.centroid_rc, "mean_score": e.mean_score, "max_score": e.max_score,
                 "bbox_rc": e.bbox_rc}
                for e in events
            ],
            "pixel_fingerprints": pixel_reports,
            "fingerprint_top_class_counts": dict(Counter(top_classes)),
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "anomaly_fingerprint_report.json", "w") as fh:
        json.dump(report, fh, indent=1, default=str)

    prov = Provenance(
        result_id="anomaly_fingerprint_enmap_20220908_20240424_shawka_dam_v1",
        result_kind="anomaly_and_fingerprint",
        algorithm=AlgorithmRecord(
            name="rx_anomaly + fingerprint_pixel (inland adaptation)",
            description=(
                "RX/Mahalanobis anomaly score in PCA-of-band-group space, "
                "pooled background across both dates, applied within the "
                "validated persistent wet core; band-group-based fingerprint "
                "hypothesis over the same population. See pipeline/anomaly.py "
                "and pipeline/fingerprint.py module docstrings for the full "
                "derivation and stated small-sample / no-wavelength-table "
                "limitations."
            ),
            reference="Reed & Yu (1990); interface shape mirrors DesalGuard-main, values/features do not.",
            parameters={
                "test_darkness_max": 0.10, "background_darkness_max": 0.13,
                "n_groups": DEFAULT_N_GROUPS,
            },
            inputs=[str(path_2022.name), str(path_2024.name), "aoi/shawka_dam.geojson"],
            units_out="per-pixel RX score, SAM, and weighted class-hypothesis scores",
            assumptions=[
                "Background (darkness_max=0.13 persistent-wet-core mask) is a valid "
                "'normal water' population for this AOI -- itself only validated by "
                "the zero-leakage/single-component checks in docs/WATER_MASK.md "
                "section 12, not by independent ground truth.",
            ],
            limitations=[
                "Background pooled across 2 dates is still only tens of pixel-spectra "
                "-- see pipeline/anomaly.py module docstring; scores are a relative "
                "ranking, not a calibrated detection.",
                "Most fingerprint evidence is still band-GROUP-based; CYANO_LIKE now "
                "uses real named bands (600/620/650 nm phycocyanin shoulders, see "
                "data/metadata/enmap_band_characterisation.json), the one class that "
                "structurally needed them. BOTTOM_INFLUENCED remains not computed "
                "-- see pipeline/fingerprint.py module docstring and CLASSES registry.",
                "Fingerprint evidence WEIGHTS (including CYANO_LIKE's z-score gate) "
                "are structurally-reasoned placeholders, not empirically fit -- no "
                "labeled anomaly example exists for this AOI.",
                f"Background d620 distribution (phycocyanin band-depth) has n="
                f"{d620_bg_values.size} -- same small-sample caveat as the rest of "
                "this module's background statistics.",
            ],
        ),
        extra={"summary": {lbl: report["per_date"][lbl]["fingerprint_top_class_counts"] for lbl in labels}},
    )
    prov.add_source(SourceRecord(
        satellite="EnMAP", sensor="HSI (VNIR + SWIR)", scene_id=path_2022.name,
        acquisition_utc="2022-09-08T07:30:13.226624Z", product="ENMAP_HSI_L2A",
        processing_level="L2A", provider="DLR / EOC Geoservice", licence="proprietary",
        native_resolution_m=30.0, local_path=str(path_2022),
    ))
    prov.add_source(SourceRecord(
        satellite="EnMAP", sensor="HSI (VNIR + SWIR)", scene_id=path_2024.name,
        acquisition_utc="2024-04-24T07:30:16.236194Z", product="ENMAP_HSI_L2A",
        processing_level="L2A", provider="DLR / EOC Geoservice", licence="proprietary",
        native_resolution_m=30.0, local_path=str(path_2024),
    ))
    prov_path = prov.save(str(OUT_DIR / "provenance_anomaly_fingerprint.json"))
    print(f"\nSaved report and provenance to {OUT_DIR}")
    print(f"Provenance: {prov_path}")


if __name__ == "__main__":
    main()
