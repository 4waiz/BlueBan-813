# Validation Report

**BLUEBAN 813** · Team Kanban · Gulf of Annaba, Algeria
Primary observation: Tanager-1 `20250601_104901_58_4001`, 2025-06-01 10:49:01 Z

This report leads with what we could NOT establish, then what we could. That
ordering is deliberate: a reviewer should be able to see the boundary of the
evidence before seeing the claims.

---

## 0. The single most important limitation

**No in-situ or laboratory measurement was available for this AOI.**

The Cockpit lists "In-situ WQ records · CSV · variable · Ground-truth for select
MENA water bodies" as a static card with no download mechanism (see
`DATA_ACCESS_AUDIT.md` §2.5). No field data for the Gulf of Annaba was
obtainable.

Everything that follows is therefore constrained:

| We do NOT report | Because |
|---|---|
| Chlorophyll-a in mg/m³ | No calibration samples exist for this water body |
| Turbidity in NTU or FNU | Same |
| Total suspended solids in mg/L | Same |
| "Validated against ground truth" | There is no ground truth here |
| A confirmed substance or species | Optics cannot identify chemistry |

Confidence is **capped at 0.75** in `pipeline/risk.py` while no field sample
exists, so the system cannot report high confidence however clean the imagery
is.

---

## 1. Experiment 1 — Is the 813 simulator trustworthy?

`experiments/validate_simulator.py`

### Design

The 813 product is simulated, so the convolution machinery has to be shown
correct. The AOI provides the means: Tanager-1 and Sentinel-2C imaged the same
water **38 minutes apart**, both effectively cloud-free.

We ran the exact `gaussian_srf_matrix` / `resample_spectra` used by
`simulate_813`, but targeting Sentinel-2's published band set, and compared
against what Sentinel-2 actually measured. Comparison on a common 100 m grid,
minimum 4 contributing pixels per cell.

### Why land and water are reported separately

The comparison conflates two things: whether our convolution is correct, and
whether Tanager's and Sentinel-2's independent atmospheric corrections agree.
Bright land separates them. Over vegetation and bare/built surfaces the surface
signal is an order of magnitude larger than the atmospheric path term and both
correctors are operating on their design targets. Over dark water the
atmospheric path term is comparable to or larger than the water-leaving signal.

### Results over land (n = 18 123 cells)

| Band | nm | Pearson r | Regression slope | Bias | RMSE |
|---|---|---|---|---|---|
| B01 | 443 | **0.969** | 0.944 | +0.0166 | 0.0188 |
| B02 | 492 | **0.959** | 0.977 | +0.0100 | 0.0155 |
| B03 | 560 | **0.953** | 0.961 | −0.0018 | 0.0139 |
| B04 | 665 | **0.967** | 1.040 | −0.0073 | 0.0179 |
| B05 | 704 | **0.936** | 0.913 | −0.0305 | 0.0353 |
| B06 | 740 | 0.679 | 0.711 | −0.0311 | 0.0433 |
| B07 | 783 | 0.745 | 0.765 | −0.0220 | 0.0396 |
| B08 | 833 | 0.733 | 0.798 | −0.0353 | 0.0502 |
| B8A | 865 | 0.750 | 0.759 | −0.0252 | 0.0428 |
| B11 | 1610 | **0.934** | 0.916 | −0.0287 | 0.0372 |

**Reading.** In the visible (443–704 nm) and the SWIR, r = 0.93–0.97 with slopes
of 0.91–1.04. That is a validated convolution. The NIR (740–865 nm) drops to
r ≈ 0.68–0.75, which is expected: vegetation NIR reflectance is strongly
view-angle dependent and Tanager was 19.9° off-nadir against Sentinel-2's near
nadir, so BRDF differences dominate there.

### Results over water (n = 18 962 cells)

| Band | nm | Pearson r | Regression slope |
|---|---|---|---|
| B01 | 443 | 0.507 | 0.731 |
| B03 | 560 | 0.780 | 0.861 |
| B04 | 665 | 0.536 | 1.152 |
| B8A | 865 | 0.721 | **3.508** |
| B11 | 1610 | 0.833 | **3.671** |

**Reading — and this is NOT a simulator failure.** Sentinel-2 Level-2A is
produced by Sen2Cor, which ESA documents as a **land** surface-reflectance
processor. It is not designed for water and is known to perform poorly over
dark targets. Water-specific processors (ACOLITE, C2RCC, POLYMER) exist
precisely because of this. Slopes rising to 3.5–3.7 in the NIR/SWIR, where the
true water signal is near zero, is the signature of that domain mismatch.

The divergence is itself evidence for the value of a purpose-built aquatic
sensor and aquatic processing chain — which is what Satellite 813's aquatic
product is intended to be.

**Conclusion:** the convolution is validated where it can be validated. The 813
simulation is built on machinery that demonstrably reproduces an independent
real sensor.

---

## 2. Experiment 2 — Hyperspectral lift against an operational product

`experiments/hyperspectral_ablation.py`

### Design

Target: ESA Sentinel-3 OLCI Level-2 `CHL_NN` and `TSM_NN` (log₁₀), an
operational product from a different instrument through a different processing
chain. 658 matchups within ±30 h, each aggregating ≥ 25 Tanager water pixels
onto an OLCI footprint. Features: the same Tanager pixels convolved onto
Sentinel-2's 11 bands versus 813's 205 bands. Model: PLSR with component count
chosen by **spatially blocked** inner cross-validation. 29 spatial blocks of
3 km, 5 outer folds.

### Results (spatially blocked)

| Target | Arm | R² | RMSE | MAE | components |
|---|---|---|---|---|---|
| CHL_NN | S2, 11 bands | **+0.078** | 0.305 | 0.201 | 2.0 |
| CHL_NN | 813, 205 bands | +0.010 | 0.316 | 0.203 | 4.2 |
| CHL_NN | 813, 261 bands @ 5 nm | +0.016 | 0.315 | 0.212 | 2.4 |
| TSM_NN | S2, 11 bands | +0.123 | 0.395 | 0.194 | 2.6 |
| TSM_NN | 813, 205 bands | **+0.129** | 0.393 | 0.197 | 2.6 |
| TSM_NN | 813, 261 bands @ 5 nm | −0.158 | 0.453 | 0.226 | 3.0 |

### Verdict: NO detectable hyperspectral advantage for this target

ΔR² is −0.068 for chlorophyll and +0.007 for suspended matter; neither survives
a paired bootstrap. **Both arms explain very little variance**, so this
experiment is underpowered rather than decisive, and we say which:

* The nearest usable OLCI acquisition is **−25.5 h** from the Tanager overpass.
  Coastal water changes materially in a day.
* OLCI is 300 m; Tanager spectra had to be averaged over that footprint.
* `CHL_NN` and `TSM_NN` are model retrievals, not measurements.

We report this rather than hunting for a target that flatters the hyperspectral
arm.

---

## 3. Experiment 3 — Would a multispectral sensor have seen this event?

`experiments/detectability_ablation.py`

### Design and what the reference is

Reference labels come from the RX detector run on all 368 product-good Tanager
bands. **This is not ground truth and we never call it that.** It is the
judgment of a full-spectrum instrument, and the experiment measures how much of
that judgment survives at each sensor's spectral resolution. Both arms are
strict information-reductions of the same source, so neither is advantaged by
construction; 813 is simply closer to it. The informative quantity is the size
of the gap.

Two regimes, because they answer different questions. Logistic regression with
balanced class weights, 173 spatial blocks of 1.2 km, 5 folds, 25 513 samples
(5 513 positive).

### Regime A — gross events (confident anomaly vs confident background)

| Arm | F1 | ROC-AUC | Precision | Recall |
|---|---|---|---|---|
| S2, 11 bands | 0.9998 | 0.9998 | 1.0000 | 0.9996 |
| 813, 205 bands | 0.9999 | 1.0000 | 1.0000 | 0.9998 |

ΔF1 = +0.0001, not significant.

**Conclusion: an obvious plume does not require hyperspectral data.** Both
configurations saturate. We report this because it bounds the claim.

### Regime B — the operational boundary (whole water population, ambiguous included)

| Arm | F1 | Precision | Recall | TP | FP | FN | TN |
|---|---|---|---|---|---|---|---|
| S2, 11 bands | 0.9853 | 0.9719 | 0.9991 | 5 508 | **159** | 5 | 19 841 |
| 813, 205 bands | **0.9918** | **0.9850** | 0.9987 | 5 506 | **84** | 7 | 19 916 |
| 813, 261 bands @ 5 nm | 0.9919 | 0.9853 | 0.9985 | 5 505 | 82 | 8 | 19 918 |

| Quantity | Value |
|---|---|
| ΔF1 | **+0.0065** |
| 95 % CI on ΔF1 (paired bootstrap, 1 000 resamples) | **[0.0050, 0.0080]** |
| Significant | **Yes — the interval excludes zero** |
| False-alarm share | 2.806 % → 1.503 % |
| **Relative reduction in false alarms** | **−46.4 %** |
| False positives | 159 → 84 (75 fewer) |

**Conclusion.** At matched recall, 813's spectral resolution cuts false alarms
by roughly half. For an operator dispatching a crewed vessel per alert, that is
the operationally meaningful number.

**Robustness.** The 261-band 5 nm interpretation of the published 813
specification gives F1 = 0.9919 against 0.9918, so the conclusion does not
depend on how we resolve the specification's internal inconsistency (see
`813_PRODUCT_NOTES.md` §3).

---

## 4. Methodological finding — random splits fabricate hyperspectral advantage

Both ablations were run with a random split as well as a spatial one:

| Target / arm | R² random | R² spatially blocked | Inflation |
|---|---|---|---|
| CHL_NN · S2 11 band | 0.2928 | 0.0782 | +0.215 |
| CHL_NN · 813 205 band | **0.6304** | **0.0097** | **+0.621** |
| CHL_NN · 813 261 band | 0.6564 | 0.0164 | +0.640 |
| TSM_NN · S2 11 band | 0.4712 | 0.1227 | +0.349 |
| TSM_NN · 813 205 band | 0.4898 | 0.1292 | +0.361 |

Neighbouring water pixels are near-duplicates. Under a random split they land on
both sides, and the inflation is **three times larger for the high-dimensional
arm**, which has more capacity to memorise. A team reporting the random-split
numbers would announce a large hyperspectral advantage that does not exist.

**Our own error, documented.** An earlier run of the ablation used a random
split for the INNER component-selection loop as well. It drove PLSR to the
20-component cap and produced an outer R² of **−15.7**. That was a flaw in our
protocol, not a property of the data; the fix and the reasoning are in the
docstring of `fit_predict_plsr`.

---

## 5. Temporal validation — the test that changed the verdict

`scripts/build_baseline.py`, `pipeline/temporal.py`

### Why this is validation and not decoration

A spatial anomaly detector compares a pixel to its neighbours. It will flag a
permanently turbid harbour, or a bright shallow bank, on **every clear day**.
Those are features of the coastline, not events. Only a multi-year record can
tell the difference — and for the nearshore detections in this scene, bottom
reflectance in shallow water is a serious competing explanation that a single
scene cannot exclude.

### Record

| Zone | Observations | Span |
|---|---|---|
| Hotspot, inner gulf | **428** | 2020-07-20 → 2025-12-28 |
| Reference, offshore | **837** | 2020-07-17 → 2025-12-28 |

1 265 cloud-screened (≤ 15 %) Sentinel-2 acquisitions over 5.4 years. ESA
processing-baseline 04.00 radiometric offset applied by acquisition date.

### The observation date, against its own history

Zone: hotspot inner gulf. Seasonal window ±45 days of day-of-year, n = 106.

| Variable | Baseline median | 2025-06-01 | Seasonal pctile | State |
|---|---|---|---|---|
| TURBIDITY_PROXY (zone median) | −0.34505 | −0.48570 | **5.7** | NORMAL |
| TURBIDITY_PROXY (zone **P95**) | −0.20670 | −0.33750 | **6.6** | NORMAL |
| NDCI (zone median) | −0.03463 | −0.14999 | 1.9 | NORMAL |
| NDCI (zone P95) | +0.03846 | 0.00000 | 7.5 | NORMAL |
| R665 (zone median) | 0.02490 | 0.00860 | 0.9 | NORMAL |
| R560 (zone P95) | 0.08964 | 0.11480 | 64.2 | NORMAL |

**The P95 statistic matters.** A 1.13 km² plume inside a ~30 km² monitoring zone
barely moves the zone median, so the median alone could call a real event
"normal". We therefore track the 95th percentile of the zone, which follows the
most affected water in it. It agrees: **6.6th percentile**.

### Verdict

On the observation date the Gulf of Annaba nearshore was **cleaner than usual,
not dirtier**. The spatial anomaly is a persistent feature of this coastline.

`pipeline/risk.py` applies a **temporal veto**: priority is capped when the
observation sits at or below the median for its season. The same event scores:

| Temporal evidence | Severity | Priority |
|---|---|---|
| None (no baseline) | 0.723 | **HIGH_PRIORITY** |
| 6.6th percentile (measured) | 0.513 | **WATCH** (capped; an asset is exposed) |
| 97th percentile (hypothetical) | 0.801 | HIGH_PRIORITY |

A product that cannot say "nothing is happening here" is not an operational
product.

---

## 6. Data-integrity checks that passed

| Check | Result |
|---|---|
| Scene cloud fraction | 0.080 % (product mask) |
| Scene cirrus fraction | 0.0002 % |
| Valid pixels | 68.38 % of array; remainder is the 19.9° off-nadir border, not cloud |
| Aerosol optical depth | mean 0.112 — clean atmosphere |
| Column water vapour | mean 1.395 g/cm² |
| Sun zenith | 16.98° (elevation 73°) |
| Bands flagged bad by the product | 58 of 426, in two runs matching the atmospheric water-vapour windows |
| Water pixels after masking | 209 077 → 188.17 km² |
| Shoreline pixels removed | 6 574 (60 m buffer at 30 m resolution) |
| Index physical bounds after uncertainty guard | all within ±1; NDCI went from [−1907, +2407] to [−0.99, +0.997] |
| Per-band SNR over water | 100 of 368 bands clear SNR ≥ 3 in 401–896 nm |
| Provenance completeness | **100 %** across 5 source records |

---

## 7. Reproduction

```bash
python scripts/fetch_tanager.py 20250601_104901_58_4001
python scripts/build_baseline.py --years 6 --max-cloud 15
python scripts/build_matchup.py
python experiments/validate_simulator.py
python experiments/hyperspectral_ablation.py
BLUEBAN_REGIME=hard python experiments/detectability_ablation.py
BLUEBAN_REGIME=easy python experiments/detectability_ablation.py
python scripts/build_demo_event.py
```

Primary scene checksum:
`sha256 = 4242bf42f5da5673bd3a381714f20f87538423287cd3962bbfd5b564fc2a81ce`
(906 164 921 bytes)

All randomised procedures are seeded (`np.random.default_rng(813)`).
