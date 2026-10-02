"""Run the multi-scene temporal deviation detector over the reused 14-month
Sentinel-2/Landsat baseline (Task 5, 2026-09-19 batch) and cross-reference
against where the two EnMAP acquisition dates (2022-09-08, 2024-04-24) land
in that series.

Usage: python3 scripts/derive_temporal_baseline_detector.py
No scene files needed -- reads data/baseline_indices_s2_landsat.csv only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.temporal import (  # noqa: E402
    load_aoi_baseline, detect_temporal_deviations, nearest_bracket, INDEX_COLUMNS,
)
from pipeline.provenance import Provenance, AlgorithmRecord  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_CSV = PROJECT_ROOT / "data" / "baseline_indices_s2_landsat.csv"
OUT_DIR = PROJECT_ROOT / "data" / "temporal"
AOI = "shawka_dam"
Z_THRESHOLD = 1.5

ENMAP_DATES = {"2022-09-08": "2022-09-08", "2024-04-24": "2024-04-24"}


def main() -> None:
    df = load_aoi_baseline(str(BASELINE_CSV), AOI)
    print(f"Loaded {len(df)} '{AOI}' baseline observations "
          f"({df['datetime'].min().date()} to {df['datetime'].max().date()})")
    print(df["collection"].value_counts().to_string())

    result = detect_temporal_deviations(df, z_threshold=Z_THRESHOLD)
    print(f"\nPer-sensor n: {result.per_sensor_n}")
    for coll in result.per_sensor_mean:
        print(f"\n{coll} own-population mean/std (this AOI, {result.per_sensor_n[coll]} obs):")
        for c in INDEX_COLUMNS:
            print(f"  {c:22s} mean={result.per_sensor_mean[coll][c]:+.5f}  "
                  f"std={result.per_sensor_std[coll][c]:.5f}")

    print(f"\nFlagged months (|z| > {Z_THRESHOLD} on at least one index, "
          f"against that sensor's OWN population): {result.n_flagged}/{len(result.deviations)}")
    for d in result.deviations:
        marker = f"  <-- FLAGGED on {d.flagged_index} (z={d.z_scores[d.flagged_index]:+.2f})" if d.flagged else ""
        print(f"  {d.datetime[:10]}  {d.collection:16s} max|z|={d.max_abs_z:.2f}{marker}")

    # --- Cross-reference against the two EnMAP acquisition dates ----------
    enmap_context = {}
    for label in ENMAP_DATES:
        target_ts = pd_ts(label)
        ctx = {}
        for coll in result.per_sensor_n:
            before, after = nearest_bracket(df, label, collection=coll)
            ctx[coll] = {
                "before": None if before is None else {
                    "item_id": before["item_id"], "datetime": before["datetime"].isoformat(),
                    "days_before_enmap": (target_ts - before["datetime"]).days,
                },
                "after": None if after is None else {
                    "item_id": after["item_id"], "datetime": after["datetime"].isoformat(),
                    "days_after_enmap": (after["datetime"] - target_ts).days,
                },
            }
        enmap_context[label] = ctx

    print("\n--- EnMAP acquisition dates in the baseline series ---")
    for label, ctx in enmap_context.items():
        print(f"\n{label}:")
        for coll, brackets in ctx.items():
            b, a = brackets["before"], brackets["after"]
            b_txt = f"{b['item_id']} ({b['days_before_enmap']}d before)" if b else "NONE (before series start)"
            a_txt = f"{a['item_id']} ({a['days_after_enmap']}d after)" if a else "NONE (after series end)"
            print(f"  {coll}: nearest before = {b_txt}")
            print(f"  {coll}: nearest after  = {a_txt}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "aoi": AOI,
        "z_threshold": Z_THRESHOLD,
        "per_sensor_n": result.per_sensor_n,
        "per_sensor_mean": result.per_sensor_mean,
        "per_sensor_std": result.per_sensor_std,
        "n_flagged": result.n_flagged,
        "deviations": [
            {
                "item_id": d.item_id, "collection": d.collection, "datetime": d.datetime,
                "z_scores": {k: (None if not (v == v) else round(v, 4)) for k, v in d.z_scores.items()},
                "max_abs_z": None if not (d.max_abs_z == d.max_abs_z) else round(d.max_abs_z, 4),
                "flagged_index": d.flagged_index, "flagged": d.flagged,
            }
            for d in result.deviations
        ],
        "enmap_date_context": enmap_context,
    }
    with open(OUT_DIR / "temporal_deviations.json", "w") as fh:
        json.dump(report, fh, indent=1, default=str)

    prov = Provenance(
        result_id="temporal_baseline_detector_shawka_dam_v1",
        result_kind="temporal_deviation_detection",
        algorithm=AlgorithmRecord(
            name="detect_temporal_deviations",
            description=(
                "Per-sensor z-score deviation detector over the reused "
                "14-month Sentinel-2/Landsat baseline (28 shawka_dam "
                "observations, 14 per sensor). Flags any observation where "
                "NDCI/NDTI/RedTideIndex/NDWI deviates more than "
                f"{Z_THRESHOLD} standard deviations from THIS AOI's own "
                "per-sensor mean -- replaces the prior single-scene "
                "plausibility check (comparing one EnMAP-date wet fraction "
                "against the baseline's min/max range) with an actual "
                "multi-scene detector using the full time series."
            ),
            reference="pipeline/temporal.py",
            parameters={"z_threshold": Z_THRESHOLD, "scoring": "per-sensor (S2, Landsat scored separately against their own population)"},
            inputs=[str(BASELINE_CSV)],
            units_out="z-scores (dimensionless, per-sensor-population-relative)",
            assumptions=[
                "Deviation is scored per-sensor against that sensor's OWN "
                "14-observation population at this AOI, not pooled across "
                "sensors -- S2 and Landsat read systematically different "
                "absolute index values here (a sensor band-definition "
                "offset, not a real difference), so pooling would conflate "
                "that offset with genuine temporal deviation.",
                "z_threshold=1.5 is a structurally-reasonable placeholder, "
                "not fit against labeled anomalous-month examples (none "
                "exist for this AOI) -- same category as pipeline/"
                "fingerprint.py's evidence weights.",
            ],
            limitations=[
                "14 observations per sensor across ~2 unevenly-sampled years "
                "is too small to fit a true month-of-year seasonal "
                "climatology (most calendar months have 0-1 samples per "
                "sensor) -- this is a deviation-from-this-AOI's-own-2-year-"
                "mean detector, not a seasonal-climatology detector, and is "
                "described as such, not overclaimed.",
                "Neither EnMAP acquisition date has a same-day or same-week "
                "baseline observation; 2022-09-08 predates the entire "
                "baseline series (first observation 2023-09-25); 2024-04-24 "
                "falls inside the baseline's own known coverage gap "
                "(no scene 2024-02-23 to 2024-09-04, already documented in "
                "config/project.yaml water_mask.result_2024_04_24). The "
                "EnMAP-date cross-reference below reports the REAL nearest "
                "bracketing observations and their actual date offsets, "
                "never an interpolated or fabricated same-date value.",
            ],
        ),
        extra={"n_flagged": result.n_flagged, "enmap_date_context": {k: str(v) for k, v in enmap_context.items()}},
    )
    prov_path = prov.save(str(OUT_DIR / "provenance_temporal_baseline_detector.json"))
    print(f"\nSaved temporal deviation report and provenance to {OUT_DIR}")
    print(f"Provenance: {prov_path}")


def pd_ts(s: str):
    return pd.Timestamp(s, tz="UTC")


if __name__ == "__main__":
    main()
