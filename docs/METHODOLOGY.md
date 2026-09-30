# Methodology

Every algorithmic decision in BLUEBAN 813, with its source and the reason it was
chosen over the obvious alternative.

**Part A** describes the operational UAE pipeline built in the September 2026
revamp (Sentinel-2 primary sensor, per-pixel seasonal detection, cross-sensor
reference, closed loop). **Part B**, from "The sensor cascade" onward, is the
hyperspectral characterisation developed on the Gulf of Annaba Tanager scene; it
still powers the 813 simulation, the ablation and the negative control.

---

# Part A — The operational UAE pipeline

## A1. Sentinel-2 L2A ingestion (`pipeline/watch.py`, `pipeline/s2_features.py`)

* **Source.** `sentinel-2-l2a` on the Microsoft Planetary Computer, all tiles of a
  datatake (date + relative orbit + platform) mosaicked onto a fixed UTM grid per
  AOI (UTM 39/40 handled by reprojection to the AOI's zone).
* **Offset.** `BOA_ADD_OFFSET = -1000` is applied when the tile's
  `s2:processing_baseline >= 04.00`, **per tile, before mosaicking**. Deciding by
  acquisition date is wrong for reprocessed archives.
* **Masks.** SCL classes 0, 1, 3, 8, 9, 10, 11 rejected (2/4/5 are *not*: dense
  blooms and very clear water are often mislabelled there). Water requires
  MNDWI > 0 and B11 < 0.10 (land, cloud, whitecaps, strong glint rejected).
  Pixels with B11 > 0.0215 (ACOLITE's non-water threshold) are kept but
  **flagged as glint-affected** and corrected by subtracting B12 from every band.
  A pixel whose corrected red goes below -0.002 is over-corrected and dropped.
* **Shoreline buffer.** WATCH erodes the water mask by max(40 m, one pixel). The
  20 m incident analysis buffers only against land and SCL cloud areas of >= 25
  pixels (`hole_buffer=False`), so a single noisy pixel in open water does not
  become a 60 m hole.
* **Resumable.** Each datatake writes its feature cache (`.npz`, float16) and a
  sidecar row, so an interrupted multi-year screen resumes where it stopped.

## A2. Features

| Feature | Definition | Kind | Reference |
|---|---|---|---|
| NDCI | (R705 − R665) / (R705 + R665) | PROXY | Mishra & Mishra 2012 |
| MCI | R705 − R665 − (R740 − R665)(705 − 665)/(740 − 665) | PROXY | Gower et al. 2005 |
| FAI | R865 − baseline(R665, R1610) | PROXY | Hu 2009 |
| TUR_NECHAD2016 | A·ρ/(1 − ρ/C), red band, generic coefficients (ACOLITE table) | GENERIC_CALIBRATION | Nechad et al. |
| Hue angle | CIE chromaticity angle from the visible bands | COLORIMETRIC | van der Woerd & Wernand |

No feature is ever printed with physical units unless a local calibration passes
the calibration gate (A6). NDCI is unstable over very clear water where the
corrected red reflectance approaches zero; the hue angle and MCI are the checks.

## A3. DETECT: per-pixel seasonal anomaly (`pipeline/detect.py`)

A spatial detector compares a pixel with its neighbours, so a bright bank or a
dredged channel is flagged every clear day. DETECT compares every pixel with
**itself**: its values at the same time of year in *other* years.

    clim(p) = F at pixel p on acquisitions within ±45 days of day-of-year, other years
    z(p)    = (F_t(p) − median(clim(p))) / (1.4826 · MAD(clim(p)) + floor_F)
    pct(p)  = percentile of F_t(p) within clim(p)

* Floors: NDCI 0.02, MCI 0.002, FAI 0.002, turbidity 1 FNU, hue 5°.
* Candidate: connected region >= 0.5 km², z >= 3 and pct >= 95 on the
  hypothesis' primary feature (NDCI bloom-like, turbidity sediment-like, FAI
  surface material) and a secondary feature agreeing (MCI z >= 1 for bloom-like).
* Two-stage for speed: a date reaches the pixel pass only if the AOI's P95 **or
  P99** of some feature sits at or above its own 80th seasonal percentile. The
  per-pixel median uses a sort-based NaN median (identical to `np.nanmedian`,
  ~5x faster).
* Persistence: the share of past same-season dates on which at least half the
  region already exceeded half of today's threshold. Permanent features score high.
* Each candidate carries 13 triage features (`pipeline/learning.py:TRIAGE_FEATURES`),
  including the region's water-colour change `hue_delta_deg`.

## A4. Cross-sensor reference (`scripts/build_labels.py`, `pipeline/sentinel3.py`)

OLCI WFR granules from the same morning are read **windowed** around the AOI
(the tie-point grid locates the hyperslab: ~14 s instead of the full granule).
For each bloom-/sediment-like candidate the CHL_NN / TSM_NN median inside the
region is compared with the surrounding water (25 km pad, minus a 360 m ring):

* positive: ratio >= 1.5 and region >= 2 units, or region >= 10 units;
* negative: ratio <= 1.15 and region < 5 units;
* otherwise, or with < 8 valid OLCI pixels, unlabelled.

Labels carry weight 0.5 and the OLCI values they came from. They are a model
product, **never in-situ truth**. Incidents use footprint matching: an OLCI pixel
belongs to the event when its 300 m footprint overlaps it.

## A5. Incidents, verification and field work (`pipeline/incidents.py`, `services/api`)

States: MONITORING → DETECTED → UNDER_REVIEW → FIELD_VALIDATION_REQUIRED →
CONFIRMED / FALSE_POSITIVE → RESOLVED. CONFIRM, FALSE_POSITIVE and RECLASSIFY
create labels (analyst weight 1.0; field results 2.0); NEEDS_FIELD_SAMPLE and
INSUFFICIENT_EVIDENCE do not. The sampling plan is role-based (core, edge,
background control, uncertainty, asset boundary). Alerts are factual ("New
coastal anomaly detected near … 94th seasonal percentile … Analyst review
required"). Every action is written to a SHA-256 hash-chained audit log.

## A6. Learning loop and promotion gate (`pipeline/learning.py`, `apps/web/lib/learning.ts`)

* Split: stratified by class and grouped by AOI-month (whole groups on one side),
  ~20 % validation, frozen by hash on first training.
* Candidate: L2 logistic regression (scikit-learn objective, Newton-IRLS in the
  browser; parity 1e-7), class-balanced, weighted by label source.
* Gate: model tests pass · validation hash unchanged · both classes present ·
  primary metric (AUPRC) not worse (grouped bootstrap reported) · calibration
  (ECE <= limit or Brier not worse) · no AOI regression · **named human approves**.
* Quantification (when matchups exist): a model zoo (linear, PLSR, RF, GBM, SVR,
  ridge-log10) compared under grouped CV with a parsimony rule; physical units
  only when >= 20 matchups in >= 5 groups and grouped-CV R² >= 0.4 in log space
  with a confidence interval above zero.

## A7. Scenario trajectory and satellite passes

* The drift is a **SCENARIO TRAJECTORY ESTIMATE**: particles advected by ERA5
  10 m wind with a windage factor and random walk. It is not a hydrodynamic
  model and never used to infer a source.
* The Satellite View propagates public TLEs (CelesTrak) with SGP4
  (satellite.js). Predicted Sentinel-2 passes over Fujairah were checked against
  the archive: closest approach 07:02:31 UTC, 52 km west (relative orbit 20),
  16 min after each datatake's recorded start.

---

# Part B — Hyperspectral characterisation (Tanager, 813 simulation)

## The sensor cascade

Each sensor has one job. None was added because it existed.

| Stage | Sensor | Job | Why this sensor |
|---|---|---|---|
| A | Sentinel-3 OLCI WFR L2 | Operational reference and regional context | ESA-validated ocean-colour retrievals; 300 m; near-daily |
| B | Sentinel-2 MSI L2A | Multi-year local baseline; spatial detail | 413 scenes over this AOI in 2025; 10–20 m resolves the nearshore band |
| C | Tanager-1 hyperspectral | Spectral forensics; source for the 813 simulator | 426 bands, 5 nm, 30 m; open CC-BY-4.0 |
| D | Landsat 8/9 | Thermal context | Only open source of 100 m surface temperature |
| — | ERA5 10 m wind | Drift forcing | Open, hourly, no authentication |

Stage E (in-situ validation) is **empty** and the product says so. See
`LIMITATIONS.md` §1.

---

## 1. Reading the hyperspectral product

`pipeline/satellite813.py`

Every parameter comes out of the file, not out of a tutorial:

| Property | Where it comes from |
|---|---|
| 426 band centres, nm | `surface_reflectance.attrs["wavelengths"]` |
| FWHM per band, nm | `attrs["fwhm"]` (median 6.05) |
| **Bad-band flags** | `attrs["good_wavelengths"]` — 368 good, 58 bad |
| Units | `attrs["Unit"]` = "Unitless" (surface reflectance) |
| No-data | `attrs["_FillValue"]` = −9999.0 |
| Geotransform | parsed from `StructMetadata.0` |
| Projection | `HDFEOS/GRIDS/HYP.attrs["epsg_code"]` = 32632 |
| Per-pixel uncertainty | `surface_reflectance_uncertainty` (426 × rows × cols) |

**Decision: use the product's own bad-band flags.** The official challenge
notebooks hardcode the water-vapour windows as 1350–1450 and 1800–1950 nm. This
product flags **1342.41–1437.55** and **1782.58–1967.21** nm — different at all
four edges. Copying another sensor's bad-band rule onto a different instrument
is exactly the kind of unexamined assumption that makes hyperspectral results
unreproducible.

---

## 2. Quality screening

`pipeline/quality.py`

1. **Product masks** — `nodata_pixels`, `beta_cloud_mask`, `beta_cirrus_mask`.
2. **Sun glint** — reject water pixels with NIR reflectance > 0.05. Liquid water
   absorbs strongly beyond ~750 nm, so elevated NIR over water means glint,
   whitecaps, foam or a mixed pixel.
   *Hu (2009) RSE 113:2118-2129; Wang & Shi (2007).*
3. **Uncertainty ratio** — reject pixels where the product's own reported σ
   exceeds the value. Strictly better than a blanket SNR assumption: it is the
   instrument's own statement about that measurement.

Every step returns a `MaskReport` with how much it removed, and those reports
travel into the event payload.

---

## 3. Water masking

`pipeline/water_mask.py`

**Decision: MNDWI, not NDWI.** Green vs SWIR separates water from built and bare
surfaces far more cleanly on a developed coastline than green vs NIR.
*Xu (2006) IJRS 27(14):3025-3033.*

Then three filters that matter more than the index choice:

* **NIR darkness** — water must be dark beyond 750 nm.
* **Connected-component removal** — components under 50 px (4.5 ha) are speckle.
* **Shoreline erosion, 2 px** — a 60 m fringe removed at 30 m resolution.
  A pixel straddling the shoreline mixes land and water spectra and cannot be
  interpreted as either. This removed 6 574 pixels.

`offshore_background()` further requires ≥ 240 m from any non-water pixel, which
is what makes the anomaly background clean.

**Result:** 209 077 water pixels, 188.17 km².

---

## 4. Indices, with uncertainty propagated

`pipeline/indices.py`

Every index carries its source, required wavelengths, expected input quantity,
output units, valid range and assumptions as an `IndexSpec`, and that record
travels into provenance.

| Index | Formula | Source |
|---|---|---|
| NDWI | (G₅₆₀ − NIR₈₆₀)/(…) | McFeeters (1996) IJRS 17(7):1425-1432 |
| MNDWI | (G₅₆₀ − SWIR₁₆₁₀)/(…) | Xu (2006) IJRS 27(14):3025-3033 |
| NDCI | (RE₇₀₅ − R₆₆₅)/(…) | Mishra & Mishra (2012) RSE 117:394-406 |
| Turbidity proxy | (R₆₆₅ − G₅₆₀)/(…) | Official challenge notebook 06; form consistent with Nechad et al. (2009) RSE 113:2141-2154 |
| CHL red-edge ratio | R₇₀₅/R₆₆₅ | Gitelson et al. (2008) RSE 112:3582-3593 |
| FAI | NIR − baseline(red→SWIR) | Hu (2009) RSE 113:2118-2129 |

### The problem the tutorials hide

Applying these formulas naively to water pixels on this scene gives:

```
NDCI   min = -1907.3   max = +2407.0
NDWI   max = +1.289          (physically impossible)
```

Over dark water the denominator approaches the noise floor. **0.53 % of water
pixels have R₇₀₅ + R₆₆₅ ≤ 0** after atmospheric correction. Those values are not
weak signal; they are division by noise.

### The fix, using the sensor's own uncertainty

For ND = (a − b)/(a + b), first-order propagation gives

```
σ_ND = 2 · sqrt(b²σ_a² + a²σ_b²) / (a + b)²
```

and a pixel is kept only when

```
(a + b) > k · sqrt(σ_a² + σ_b²),   k = 3
```

Measured σ at 665 nm is 0.000363 (median), so the guard is ~0.0015 in
reflectance — derived, not tuned.

**Result:** 0.8–1.1 % of pixels rejected, every index bounded to its physical
range, and **every pixel now carries a per-pixel uncertainty** that feeds the
confidence model.

| Index | Kept | Range after guard | Median σ |
|---|---|---|---|
| NDWI | 99.89 % | 0.177 … 0.998 | 0.0163 |
| MNDWI | 99.19 % | 0.162 … 1.000 | 0.0124 |
| NDCI | 99.20 % | −0.990 … 0.997 | 0.0328 |
| Turbidity | 99.34 % | −1.000 … −0.033 | 0.0225 |

The NDCI σ of 0.033 is itself useful: NDCI differences below ~0.03 on this scene
are not significant.

---

## 5. Which bands actually carry water information

`pipeline/spectral.py`

**Decision: measure it, do not assume it.** Two independent criteria:

1. **Physics.** Liquid water absorbs almost totally beyond 900 nm, so there is
   essentially no water-leaving signal in the NIR/SWIR — what remains is surface
   reflection and residual atmosphere. Range restricted to 400–900 nm for
   water-colour interpretation. Longer bands stay in the cube as glint and
   atmospheric diagnostics.
2. **Measured SNR.** A band is used only if its median |R|/σ over water, from the
   product's uncertainty layer, exceeds 3.

**Result: 100 of 368 bands, 401.3–896.4 nm.** Measured SNR at key wavelengths:

| nm | 411 | 441 | 491 | 561 | 621 | 666 | 676 | 686 | 706 | 866 | 941 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SNR | 28.8 | 33.1 | 36.7 | 31.7 | 25.6 | 20.6 | 23.4 | 21.6 | 22.5 | 26.5 | **8.8** |

941 nm correctly falls out: it is the 940 nm water-vapour absorption band.

### Band depth, done properly

**Decision: local two-shoulder continua, not a global convex hull.** Water
reflectance falls steeply and convexly from blue to NIR, so a hull fitted over
400–900 nm sits far above the spectrum in the red and reports a large apparent
"absorption depth" for every pixel, feature or not. Our first implementation did
exactly that and produced depths of ~0.79 everywhere, which is meaningless.

The standard formulation is used instead:

```
depth = 1 − R(centre) / linear_interp(R(left), R(right))
```

*Clark & Roush (1984) JGR 89(B7):6329-6340.*

| Feature | Shoulders | Centre |
|---|---|---|
| Chlorophyll-a red absorption | 650 / 715 nm | 675 nm |
| Phycocyanin | 600 / 650 nm | 620 nm |
| Chlorophyll-a Soret | 412 / 490 nm | 443 nm |

**And depths are reported as an excess over background water, not absolutely.**
Clear Mediterranean water already has a 675 nm depth of 0.059 here, so an
absolute threshold fires on normal water. What identifies an event is how much
deeper the feature is than the local norm.

---

## 6. Anomaly detection

`pipeline/anomaly.py`

**RX detector** — Mahalanobis distance of each pixel's spectrum from the
background water population, computed in a PCA-reduced space because adjacent
hyperspectral bands are almost perfectly correlated and the raw covariance is
singular. 12 components retain 94.46 % of variance.
*Reed & Yu (1990) IEEE Trans. ASSP 38(10):1760-1770.*

**Robust background.** A plain mean over all water pixels is contaminated by the
very anomaly being sought. Three iterations of trimming the most distant 5 % and
recomputing converge the background on normal water (159 967 of 186 578 offshore
pixels retained).

### The threshold, and why the textbook one is wrong here

Under the RX null hypothesis, squared Mahalanobis distance in *k* dimensions is
χ²(k). On this scene:

| Rule | Threshold | Water pixels flagged |
|---|---|---|
| χ²(12) at α = 0.01 | 26.22 | **14.57 %** |
| Empirical 99th percentile of the background | **936.19** | **2.64 %** |

Real coastal water is a mixture of offshore, nearshore and depth-influenced
populations, so it is not multivariate normal and the χ² tail is far too
optimistic. We report the χ² value for reference and **threshold on the
empirical distribution of the background population itself**, which gives a real
false-alarm rate regardless of distribution shape.

**Result:** 7 event regions, 4.94 km² total, after morphological closing and a
25-pixel (2.25 ha) minimum.

---

## 7. Fingerprinting

`pipeline/fingerprint.py`

Produces a **weighted hypothesis with its evidence**, never an identification.
Classes are defined by optical behaviour, each with a citation:

| Class | Optical definition | Source |
|---|---|---|
| SEDIMENT_LIKE | Broadband visible elevation growing from blue to red | Nechad et al. (2009); Doxaran et al. (2002) |
| BLOOM_LIKE | Red-edge peak 700–710 nm with 675 nm absorption | Gitelson et al. (2008); Mishra & Mishra (2012) |
| CYANO_LIKE | Bloom shape plus 620 nm phycocyanin feature | Simis et al. (2005) |
| CDOM_LIKE | Steep blue absorption without a red-edge peak | Bricaud et al. (1981) |
| SURFACE_FILM_LIKE | NIR above the red-to-SWIR baseline | Hu (2009) |
| BOTTOM_INFLUENCED | Green-dominant nearshore with suppressed red | Lyzenga (1978) |
| UNKNOWN_ANOMALY | Statistically anomalous, no signature match | — |

**The key discriminator** is the visible tilt, R₆₆₅/bg minus R₄₄₃/bg. Mineral
particles scatter more efficiently toward the red; dissolved organic matter
absorbs blue and does the opposite. For the primary event this is strongly
positive while the chlorophyll excess is **negative** (−0.034) — sediment
diluting the pigment feature, not algae.

If the leading class scores below 45 %, the system returns `UNKNOWN_ANOMALY`
rather than asserting. Three of seven regions did.

---

## 8. Temporal baselines

`pipeline/temporal.py`, `scripts/build_baseline.py`

**Decision: local percentiles, never absolute thresholds.** "NDCI above 0.2 is a
bloom" is meaningless across water bodies: what is alarming in the clear
Mediterranean is normal in a turbid estuary. Every observation is judged against
the distribution for **that place and that time of year** (±45 days of
day-of-year, wrapping the year boundary).

**Two statistics per zone, and the reason.** A 1.13 km² plume inside a ~30 km²
monitoring zone barely moves the zone median. We therefore track the zone
**median** and the zone **95th percentile**; the latter follows the most affected
water in the zone and is the sensitive test.

**Processing-baseline trap.** From ESA baseline 04.00 (2022-01-25) Sentinel-2
L2A carries a −1000 DN radiometric offset, and Planetary Computer serves raw
values. `pipeline/sentinel2.py:harmonize` applies it by acquisition date;
ignoring it silently mixes two radiometric scales across a multi-year baseline.

**Record built:** 1 265 acquisitions, 5.4 years, cloud ≤ 15 %.

---

## 9. Drift forecasting

`pipeline/forecast.py`

Wind-driven surface drift at **3 % of the 10 m wind**, rotated 15° clockwise,
plus random-walk diffusion at 5 m²/s.
*Ekman (1905); ASCE (1996) J. Hydraulic Eng. 122(11):594-609; Breivik et al. (2011).*

Two decisions that matter:

* **Coastline beaching.** Particles driven onto land stop at their last water
  position and are counted as stranded. Without this, an onshore wind puts a
  forecast plume on top of a town.
* **Offshore wind sampling.** ERA5 is a ~25 km grid. The plume centroid, 90 m
  from shore, resolves to a land cell 10 km inland reporting wind from 36°; the
  marine cell reports 87°. A 51° error would send the plume the wrong way. We
  sample over offshore water and record the reason in provenance.

Labelled a **scenario estimate**, not validated. See `LIMITATIONS.md` §5.

---

## 10. Severity, confidence and priority

`pipeline/risk.py`

**Severity and confidence are never multiplied.** Collapsing them destroys the
only information an operator needs: "severity 0.8, confidence 0.3" and
"severity 0.3, confidence 0.8" both become 0.24 yet call for opposite responses.

| Severity input | Weight |
|---|---|
| Historical rarity (local seasonal percentile) | 0.30 |
| Spectral anomaly percentile | 0.25 |
| Event area (saturating at 10 km²) | 0.20 |
| Magnitude vs background | 0.20 |
| Growth rate | 0.15 |

| Confidence input | Weight |
|---|---|
| Valid coverage | 0.20 |
| Measured spectral SNR | 0.20 |
| Bottom-influence risk (inverted) | 0.20 |
| Cloud-free fraction | 0.15 |
| Sample size | 0.15 |
| Classification margin | 0.15 |

Capped at **0.75** while no in-situ measurement exists.

**Priority comes from an explicit rule table**, not a weighted sum, and every
fired rule is returned so an operator can disagree with it. Two deliberate
asymmetries:

1. **Low confidence RAISES priority** when severity and exposure are high.
   Uncertainty about a potentially serious event is a reason to go and look.
2. **A temporal veto CAPS priority** when the observation sits at or below the
   median for its season. A spatial detector will flag a permanently turbid
   harbour every clear day; the multi-year record is what separates a feature
   from an event.

---

## 11. Exposure and sampling

`pipeline/exposure.py`, `pipeline/sampling.py`

Exposure = proximity (5 km decay) × trajectory (1.0 if the drift track
intersects, else 0.35) × asset sensitivity. Every component is returned in a
`basis` list as prose.

The sampling planner assigns each point a **role and the question it answers**:
event core, leading edge, asset boundary, background control, uncertainty point.
A minimum separation of 400 m prevents two samples measuring the same water.

**A background control is mandatory.** Without a same-day measurement of
unaffected water in the same body, an absolute laboratory value from the event
core cannot be interpreted at all.

---

## 12. The 813 simulator

`pipeline/satellite813.py` — full treatment in `813_PRODUCT_NOTES.md`.

Gaussian spectral-response convolution onto the published 813 band table, with a
`min_support` rule so simulated bands straddling a Tanager bad-band gap return
NaN rather than being interpolated across the region where the atmosphere
destroyed the signal. Spectral configuration only; 813's 20 m resolution is
deliberately not simulated.

---

## 13. Provenance

`pipeline/provenance.py`

Every derived result records satellite, sensor, scene id, acquisition time,
product, processing level, provider, licence, native resolution, bands and
wavelengths used, units, quality masks, access URL, local path, **SHA-256**,
plus the algorithm with its parameters, assumptions and limitations, the git
revision and the environment.

`completeness()` returns the fraction of required fields present and names the
missing ones, so the interface can show an honest badge rather than implying a
record is richer than it is. Current: **100 % across 5 source records**.

---

## Full reference list

Bricaud, Morel & Prieur (1981) *Limnol. Oceanogr.* 26:43-53 ·
Bricaud et al. (1995) *JGR Oceans* 100:13321-13332 ·
Clark & Roush (1984) *JGR* 89(B7):6329-6340 ·
Doerffer & Schiller (2007) OLCI C2RCC ATBD ·
Doxaran et al. (2002) *RSE* 81:149-161 ·
Ekman (1905) *Ark. Mat. Astr. Fys.* 2(11) ·
Gitelson et al. (2008) *RSE* 112:3582-3593 ·
Gower et al. (1999) *IJRS* 20:1771-1786 ·
Hu (2009) *RSE* 113:2118-2129 ·
Kruse et al. (1993) *RSE* 44:145-163 ·
Lyzenga (1978) *Applied Optics* 17:379-383 ·
McFeeters (1996) *IJRS* 17(7):1425-1432 ·
Mishra & Mishra (2012) *RSE* 117:394-406 ·
Morel et al. (2007) OC4Me ATBD ·
Nechad, Ruddick & Park (2009) *RSE* 113:2141-2154 ·
Reed & Yu (1990) *IEEE Trans. ASSP* 38(10):1760-1770 ·
Simis, Peters & Gons (2005) *Limnol. Oceanogr.* 50:237-245 ·
Xu (2006) *IJRS* 27(14):3025-3033 ·
ASCE (1996) *J. Hydraulic Eng.* 122(11):594-609 ·
Breivik et al. (2011) wind-induced drift of objects at sea ·
ESA Sentinel-2 User Handbook / MSI SRF ·
ESA Sentinel-3 OLCI Level-2 Water Product Data Format Specification.
