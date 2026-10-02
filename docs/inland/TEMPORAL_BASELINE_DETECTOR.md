# Temporal Baseline Detector — Shawka Dam

**Status: BUILT (2026-09-19).** The reused 14-month-per-sensor Sentinel-2/
Landsat baseline (`data/baseline_indices_s2_landsat.csv`, `shawka_dam` rows,
28 observations total: 14 Sentinel-2 + 14 Landsat, Sep 2023-Oct 2025) had
so far only been used as a single plausibility check per EnMAP date (`does
this date's wet fraction sit inside the baseline's min/max range`, see
`docs/WATER_MASK.md` sections 6/9 and `config/project.yaml`
`water_mask.result_*.validation_against_reused_baseline`). This document
covers Task 5 of the 2026-09-19 batch: an actual multi-scene detector built
on the full time series, not a single-date check.

---

## 1. Method

`pipeline/temporal.py:detect_temporal_deviations()` scores every baseline
observation's `NDCI_chl_proxy` (chlorophyll proxy), `NDTI_turbidity_proxy`
(turbidity proxy), `RedTideIndex_proxy`, and `NDWI_water_check` as a
z-score against THIS AOI's own population mean/std in that index — the
same "this AOI's own background, not a borrowed absolute threshold"
standard every other module in this project uses (pixel background in
`pipeline/anomaly.py`/`pipeline/fingerprint.py`; here, across TIME instead
of across pixels.

**Scored PER SENSOR, not pooled.** Sentinel-2 and Landsat read
systematically different absolute values here — e.g. every Landsat
`NDWI_water_check` reading at this AOI (mean -0.203) is more negative than
every Sentinel-2 reading (mean -0.114) for the same rough period, a
sensor-band-definition offset (different green/NIR band centres and
widths — Landsat OLI's own coarser NIR/Red proxy is already flagged
elsewhere in this project, `config/project.yaml`
`sensors.stage_b...caveat`), not a real water-quality difference. Pooling
both sensors into one mean/std would conflate that offset with genuine
temporal deviation, so each sensor's 14 shawka_dam observations are scored
against their own separate mean/std.

An observation is flagged if at least one index's z-score exceeds
`z_threshold=1.5` in magnitude. This is a structurally-reasonable
placeholder (same category as `pipeline/fingerprint.py`'s evidence
weights and `pipeline/anomaly.py`'s `alpha`/`shrinkage`), not fit against
labeled anomalous-month examples — none exist for this AOI. Every z-score
is saved in full regardless of whether it clears the flag
(`data/temporal/temporal_deviations.json`), so a different cutoff can be
applied without rerunning anything.

**What this is not.** 14 observations per sensor across ~2 unevenly-sampled
years is too small to fit a true month-of-year seasonal climatology — most
calendar months have 0-1 samples per sensor. This is a deviation-from-
this-AOI's-own-2-year-mean detector, not a seasonal-climatology detector,
and is described as such rather than overclaimed — the same small-sample
honesty standard `pipeline/anomaly.py`'s own background-size caveat uses.

## 2. Per-sensor baseline statistics (this AOI's own population)

| Index | Landsat mean ± std (n=14) | Sentinel-2 mean ± std (n=14) |
|---|---|---|
| NDCI_chl_proxy | +0.1246 ± 0.0169 | +0.0353 ± 0.0048 |
| NDTI_turbidity_proxy | +0.0805 ± 0.0059 | +0.0469 ± 0.0082 |
| RedTideIndex_proxy | +1.2855 ± 0.0435 | +1.0732 ± 0.0103 |
| NDWI_water_check | -0.2030 ± 0.0136 | -0.1139 ± 0.0128 |

## 3. Result — 7 of 28 observations flagged (|z| > 1.5)

| Date | Sensor | Flagged index | z |
|---|---|---|---|
| 2023-09-30 | Sentinel-2 | RedTideIndex_proxy | +2.39 |
| 2023-11-19 | Sentinel-2 | NDWI_water_check | +2.65 |
| 2024-09-04 | Sentinel-2 | RedTideIndex_proxy | +1.52 |
| 2025-09-01 | Sentinel-2 | NDTI_turbidity_proxy | +2.28 |
| 2025-09-05 | Landsat | NDCI_chl_proxy | -2.35 |
| 2025-10-04 | Sentinel-2 | NDTI_turbidity_proxy | +1.54 |
| 2025-10-31 | Landsat | NDTI_turbidity_proxy | +2.58 |

**The clearest pattern is late 2025.** Four of the seven flags cluster in
Sep-Oct 2025 (2025-09-01, 2025-09-05, 2025-10-04, 2025-10-31), on BOTH
sensors independently, on turbidity (`NDTI`) and chlorophyll (`NDCI`)
proxies. This is the same window `docs/AOI_SELECTION.md` already flags as
the driest in the whole reused series (0.2-1.0% wet fraction, near-zero
max NDWI) — this detector adds that it is also the most spectrally unusual
window on the turbidity/chlorophyll proxies specifically, not only on wet
fraction. **Stated as a real, cross-sensor-corroborated pattern, not
interpreted further here**: a shrinking water body concentrating
turbidity/chlorophyll signal as it dries is a plausible physical
mechanism, but this detector does not establish cause, only that the
deviation is real and appears on both independent sensors in the same
window.

The other three flags (2023-09-30, 2023-11-19, 2024-09-04) do not share
an obvious pattern with each other or with the water-mask findings and are
reported as isolated single-sensor deviations, not over-interpreted.

## 4. Cross-referencing the two EnMAP acquisition dates

Neither EnMAP date has a same-day or same-week baseline observation.
Rather than fabricate or interpolate one, the REAL nearest bracketing
baseline observations (per sensor) and their actual date offsets are
reported:

**2022-09-08** predates the ENTIRE reused baseline series — its first
observation is 2023-09-25 (Landsat) / 2023-09-30 (Sentinel-2), 382/387
days AFTER this EnMAP date. **There is no way to place 2022-09-08 in this
series at all** — stated plainly rather than reaching for the nearest
available point and implying it says something about September 2022.

**2024-04-24** falls inside the baseline's own already-documented coverage
gap (`config/project.yaml` `water_mask.result_2024_04_24.
validation_against_reused_baseline`: "no scene between 2024-02-23 and
2024-09-04"):

| Sensor | Nearest BEFORE | Nearest AFTER |
|---|---|---|
| Landsat | 2024-02-23 (60 days before), NOT flagged | 2024-09-19 (148 days after), NOT flagged |
| Sentinel-2 | 2024-02-22 (61 days before), NOT flagged | 2024-09-04 (133 days after), **FLAGGED** (RedTideIndex z=+1.52) |

The closest real temporal context for the 2024-04-24 EnMAP scene is: ~2
months prior, conditions were unremarkable on both sensors; ~4.5 months
later, a mild RedTideIndex deviation appears on Sentinel-2 (Landsat's
nearest-after observation, ~5 months later, does not flag). This is
reported as bracketing context only — a ~2-4.5-month gap either side is
not evidence about the EnMAP acquisition date itself, and is not treated
as such.

## 5. Reproducing this

```
python3 scripts/derive_temporal_baseline_detector.py
```

No scene files needed — reads `data/baseline_indices_s2_landsat.csv`
only. Saves the full per-observation z-score table and the EnMAP-date
cross-reference to `data/temporal/temporal_deviations.json`, plus a
provenance record.
