"""Multi-scene temporal detector over the reused Sentinel-2/Landsat baseline
(data/baseline_indices_s2_landsat.csv, shawka_dam rows) -- Task 5 of the
2026-09-19 batch.

Prior use of this baseline (config/project.yaml water_mask.result_2022_09_08.
validation_against_reused_baseline etc.) was a SINGLE plausibility check: "is
this EnMAP date's wet fraction inside the range the baseline's wetter/driest
months record." This module builds an actual multi-scene detector on top of
the full time series instead: for every baseline observation, how far does
that month's NDCI (chlorophyll proxy) / NDTI (turbidity proxy) / RedTideIndex
/ NDWI sit from THIS AOI's own seasonal pattern in that same index -- and
where do the two EnMAP acquisition dates land relative to that pattern.

--------------------------------------------------------------------------
METHOD, and why it is built this way
--------------------------------------------------------------------------
The baseline mixes two sensors (Sentinel-2 MSI, Landsat OLI/ETM+) whose
ABSOLUTE index values are not directly comparable at this AOI -- e.g. every
Landsat NDWI_water_check reading here is more negative than every Sentinel-2
reading for the same rough period (see the printed table this module's
derivation script produces), a sensor-band-definition offset (different
green/NIR band centres and widths), not a real water-quality difference.
Pooling both sensors' raw values into one mean/std would conflate that
sensor offset with genuine temporal deviation. So deviation is scored
PER SENSOR, against that sensor's own 14-observation population at this
AOI -- the same "this AOI's own background, not a borrowed absolute
threshold" standard every other module in this project uses (z-scores
against pipeline/anomaly.py's pooled background, pipeline/fingerprint.py's
background d620 distribution, etc.), applied here across TIME instead of
across PIXELS.

14 observations per sensor is a small population for a seasonal-cycle
model -- most calendar months have zero or one sample per sensor across the
~2 sampled years, so a true month-of-year climatology (e.g. "typical
April") cannot be fit here. What IS built is a deviation-from-this-AOI's-
own-2-year-mean detector, honestly scoped as that rather than overclaimed
as a seasonal climatology. This mirrors pipeline/anomaly.py's own stated
small-sample caveat for its RX background.

``z_threshold`` (default 1.5) is a structurally-reasonable placeholder in
the same category as pipeline/fingerprint.py's evidence weights and
pipeline/anomaly.py's alpha/shrinkage -- not fit against labeled anomalous-
month examples, because none exist for this AOI. Every z-score is reported
in full regardless of whether it clears the flag, so a reader can apply a
different cutoff without rerunning anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

INDEX_COLUMNS = ("NDCI_chl_proxy", "NDTI_turbidity_proxy", "RedTideIndex_proxy", "NDWI_water_check")


@dataclass
class TemporalDeviation:
    item_id: str
    collection: str
    datetime: str
    z_scores: dict            # {index_name: z} against this sensor's own population
    max_abs_z: float
    flagged_index: str | None  # which index (if any) exceeds z_threshold
    flagged: bool


@dataclass
class TemporalDetectorResult:
    aoi: str
    z_threshold: float
    per_sensor_n: dict          # {collection: n observations}
    per_sensor_mean: dict       # {collection: {index: mean}}
    per_sensor_std: dict        # {collection: {index: std}}
    deviations: list            # list[TemporalDeviation], chronological
    n_flagged: int


def load_aoi_baseline(csv_path: str, aoi: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = df[df["aoi"] == aoi].copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def detect_temporal_deviations(df: pd.DataFrame, z_threshold: float = 1.5) -> TemporalDetectorResult:
    """Score every baseline observation's index values against THIS AOI's
    OWN per-sensor mean/std (not a borrowed absolute threshold), and flag
    any observation where at least one index's z-score exceeds
    ``z_threshold`` in magnitude.
    """
    aoi = str(df["aoi"].iloc[0]) if len(df) else "unknown"
    per_sensor_mean: dict = {}
    per_sensor_std: dict = {}
    per_sensor_n: dict = {}

    for collection, sub in df.groupby("collection"):
        per_sensor_n[collection] = int(len(sub))
        per_sensor_mean[collection] = {c: float(sub[c].mean()) for c in INDEX_COLUMNS}
        per_sensor_std[collection] = {c: float(sub[c].std(ddof=0)) for c in INDEX_COLUMNS}

    deviations = []
    n_flagged = 0
    for _, row in df.iterrows():
        collection = row["collection"]
        mean = per_sensor_mean[collection]
        std = per_sensor_std[collection]
        z = {}
        for c in INDEX_COLUMNS:
            s = std[c]
            z[c] = float((row[c] - mean[c]) / s) if s > 1e-9 else float("nan")
        finite_z = {k: v for k, v in z.items() if np.isfinite(v)}
        max_abs_z = max((abs(v) for v in finite_z.values()), default=float("nan"))
        flagged_index = None
        if finite_z:
            worst = max(finite_z, key=lambda k: abs(finite_z[k]))
            if abs(finite_z[worst]) > z_threshold:
                flagged_index = worst
        flagged = flagged_index is not None
        if flagged:
            n_flagged += 1
        deviations.append(TemporalDeviation(
            item_id=str(row["item_id"]), collection=str(collection),
            datetime=row["datetime"].isoformat(), z_scores=z,
            max_abs_z=max_abs_z, flagged_index=flagged_index, flagged=flagged,
        ))

    return TemporalDetectorResult(
        aoi=aoi, z_threshold=z_threshold, per_sensor_n=per_sensor_n,
        per_sensor_mean=per_sensor_mean, per_sensor_std=per_sensor_std,
        deviations=deviations, n_flagged=n_flagged,
    )


def nearest_bracket(df: pd.DataFrame, target_date, collection: str | None = None):
    """The nearest baseline observation BEFORE and AFTER ``target_date``
    (optionally restricted to one sensor collection). Returns
    ``(before_row_or_None, after_row_or_None)`` -- never fabricates a
    same-date observation that does not exist; a caller wanting to place an
    EnMAP acquisition date in this series gets the real bracketing
    observations and their actual date offsets, not an interpolated value.
    """
    sub = df if collection is None else df[df["collection"] == collection]
    target_date = pd.Timestamp(target_date)
    if target_date.tzinfo is None and len(df) and df["datetime"].dt.tz is not None:
        target_date = target_date.tz_localize(df["datetime"].dt.tz)
    before = sub[sub["datetime"] <= target_date]
    after = sub[sub["datetime"] > target_date]
    before_row = before.iloc[-1] if len(before) else None
    after_row = after.iloc[0] if len(after) else None
    return before_row, after_row
