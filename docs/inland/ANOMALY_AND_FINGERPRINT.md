# Anomaly Detection & Fingerprinting — Shawka Dam

**Status:** built and run against both acquired EnMAP scenes, within the
validated `persistent_wet_core()` mask (see `docs/WATER_MASK.md` section
12). This document exists for the same reason `WATER_MASK.md` does: to
show the derivation, say what is genuinely tuned for this AOI versus still
a placeholder, and report the real statistical limitation this module runs
into rather than smooth over it.

**Read this before using anything from `pipeline/anomaly.py` or
`pipeline/fingerprint.py`: the background population here is tens of
pixels, not thousands.** Every score below should be read as a relative
ranking of which wet-core pixels look more or less unusual against this
AOI's own tiny observed water population — not a calibrated detector with
a known false-alarm rate. Section 1 explains why, in full.

---

## 1. Why this isn't DesalGuard-main's anomaly/fingerprint modules, copied over

`pipeline/anomaly.py` and `pipeline/fingerprint.py` mirror the INTERFACE
SHAPE of DesalGuard-main's modules of the same name (dataclasses, function
names, the RX/Mahalanobis method, the weighted-hypothesis fingerprint
pattern, the mandatory non-diagnostic disclaimer) — same reason
`pipeline/provenance.py` was carried over unmodified. Two things were
deliberately NOT carried over as working values:

1. **Coastal thresholds and endmembers.** DesalGuard's parameters
   (`n_components=12`, `alpha=0.01`, `min_pixels=25` at 30 m, named-class
   thresholds tuned to Gulf of Annaba conditions) assume a background
   water population of presumably thousands of pixels. This AOI's entire
   validated wet core is ~10-17 pixels. Every default in both modules was
   either re-derived from this AOI's own sample-size arithmetic or marked
   an explicit placeholder — see section 4.
2. **Marine-specific class definitions.** DesalGuard's `CLASSES` registry
   is built around coastal/marine optical water types. This module's
   registry (`pipeline/fingerprint.py`) keeps the classes that are general
   limnology/ocean-colour principles, not marine-specific ones (sediment,
   algal/red-edge, CDOM, surface film), and explicitly declines the one
   class that is genuinely blocked by a separate, structural problem —
   see section 3.

## 2. The RX/Mahalanobis anomaly layer (`pipeline/anomaly.py`)

### 2.1 Test and background population

`test_mask` = `persistent_wet_core(darkness_max=0.10)` — the validated
10-pixel core (`docs/WATER_MASK.md` section 12).

`background_mask` = `persistent_wet_core(darkness_max=0.13)` — the wider,
still zero-leakage, still-single-connected-component population from the
same section's threshold sweep (17 pixels). The 0.10 mask is a strict
subset of the 0.13 mask by construction (the underlying joint-darkness
criterion is monotonic in the threshold — raising it can only add pixels),
so this is "the validated core" scored against "the validated core plus
its immediate less-strict surroundings," not two arbitrarily chosen,
independently justified populations.

Both dates' spectra at every background-mask location are pooled into one
background population (`pipeline/anomaly.py` module docstring explains
why): **17 background pixels x 2 dates = 34 pooled background
pixel-spectra**, of which 28 survive the robust iterative trim.

### 2.2 The small-sample problem, stated plainly

DesalGuard's own `robust_background()` requires the background sample size
to be at least 3x the feature dimensionality to avoid a degenerate
covariance estimate. At 34 pooled samples, that caps a stable feature
space at roughly 11 dimensions — nowhere near the ~218-band raw hyperspace
DesalGuard's coastal case can afford (with, presumably, thousands of
background pixels there). Two adaptations follow directly, both stated in
`pipeline/anomaly.py`'s module docstring, not applied silently:

- Bands are reduced to **6 wavelength-ordered group means**
  (`DEFAULT_N_GROUPS=6`, finer than `water_mask.py`'s 3-group split, chosen
  from the sample-size arithmetic so the pooled background clears
  DesalGuard's own minimum with headroom) before PCA, rather than PCA over
  the full band space.
- A **covariance shrinkage term** (`shrinkage=0.15`, blended into the
  background covariance) is added on top of DesalGuard's iterative
  trimming, because even a 6x6 covariance from ~28 samples is thin.

Both are marked PLACEHOLDER where their exact value is concerned (see
section 4) — the STRUCTURE (reduce dimensionality, regularize the
covariance) is the genuinely-motivated part; the specific numbers are
reasoned, round choices, not fit against labeled data (none exists for
this AOI).

**The reported empirical threshold (`alpha=0.10`, vs. DesalGuard's 0.01)
is itself only a rough marker at this sample size** — asking 28-34 points
to resolve even a 90th-percentile tail is already stretched thin; a 99th
percentile (DesalGuard's default) would be asking the data a question it
cannot answer. This is analogous to `docs/WATER_MASK.md` section 9's
finding for `short_long_index`: a real, structural limitation of trying to
run a coastal-scale method at an AOI two to three orders of magnitude
smaller, reported here rather than presented as solved.

### 2.3 Result

`scripts/derive_anomaly_and_fingerprint.py` runs both dates against the
pooled background:

| Date | Background pixels (pooled, post-trim) | Test pixels | Empirical threshold | Max RX score among test pixels | Any pixel above threshold? |
|---|---|---|---|---|---|
| 2022-09-08 | 28 | 10 | 6.13 | 2.42 | No |
| 2024-04-24 | 28 | 10 | 6.13 | 3.21 | No |

**No test pixel in either date exceeds the RX threshold, in either date —
and this is expected, not a null result to be surprised by.** The test
population (the 10-pixel core) is a subset of the background population
(the 17-pixel wider set) by construction, so the core is, definitionally,
close to "typical" of the population it is being compared against — there
is no independent "elsewhere in the water body" population at this AOI's
scale to contrast the core against, unlike DesalGuard's coastal case where
offshore background and a facility-adjacent test area are genuinely
different places. `extract_events()` correspondingly returns 0 events for
both dates. **This does not mean "no anomalies are present" — it means
this AOI is too small to give the RX/background-threshold design a
meaningful contrast to test against**, stated plainly per the same
reporting standard used throughout this project.

## 3. The fingerprint layer (`pipeline/fingerprint.py`)

### 3.1 The wavelength-table blocker, and how it was handled (UPDATE 2026-09-19: CYANO_LIKE now built — see section 3.2a)

`fingerprint.py`'s evidence extraction is band-GROUP-based (the same 6
groups as the anomaly layer), not named-wavelength-based like
DesalGuard's. This is a direct, structural consequence of the gap
documented in `docs/WATER_MASK.md` section 2 and
`config/project.yaml` → `enmap.spec.band_characterisation_table`: neither
EnMAP GeoTIFF carries per-band wavelength metadata, so there is no way to
say "this is the reflectance at 620 nm" for any band in either scene.

Rather than guess a wavelength-to-band mapping (which would manufacture
false precision — see `pipeline/fingerprint.py`'s module docstring for why
even an evenly-spaced guess is not safe for this specific instrument), the
module computes only the classes whose optical definition is expressible
at group-level resolution, and explicitly REFUSES the one that
structurally is not:

| Class | Computable here? | Why |
|---|---|---|
| BACKGROUND_WATER | Yes | Default/baseline, no wavelength dependency |
| SEDIMENT_LIKE | Yes | Broadband elevation is a group-level signal |
| BLOOM_LIKE | Yes (coarse) | Red-edge-REGION elevation proxy, not a chlorophyll-a retrieval |
| CDOM_LIKE | Yes (coarse) | Blue-REGION depression proxy |
| SURFACE_FILM_LIKE | Yes (heuristic) | Broadband brightening + low SAM shape-similarity |
| **CYANO_LIKE** (phycocyanin) | **Yes, as of 2026-09-19** | Needs a band at a KNOWN, narrow ~620 nm wavelength — now identified via the real per-band table (`docs/WATER_MASK.md` section 14.1). Computable, gated on this AOI's own background statistics — see section 3.2a. |
| BOTTOM_INFLUENCED | **No** | Needs both a distance-from-shore raster (not built — the wet core is a single ~10-30 px blob, not a coastline) and a more precisely placed NIR band than the group-mean proxy gives |

This is the "genuine judgment call" territory flagged during this batch's
planning: rather than stop and ask whether to proceed, the reduced-scope
path was taken because it is fully defensible on its own (the excluded
classes are named and explained, not silently dropped) and the
alternative — guessing a wavelength grid to force the full class set — was
the kind of fabricated precision this project has avoided everywhere else
(same reasoning as the Satellite 813 decision, `docs/SATELLITE_813_DECISION.md`).

### 3.2 Result

Fingerprint hypotheses for the 10 test-core pixels, per date (using the
pooled 34-sample background's own group mean/std as the reference — z-scores
are relative to THIS AOI's own observed water, not a borrowed absolute
threshold):

| Date | Top-class counts (10 pixels) |
|---|---|
| 2022-09-08 | BACKGROUND_WATER: 10 |
| 2024-04-24 | CDOM_LIKE: 7, BACKGROUND_WATER: 2, BLOOM_LIKE: 1 |

**This lines up with, and gives a spectral-shape explanation for, a
finding already on record.** `docs/WATER_MASK.md` section 9 found that the
2024-04-24 core's `short_long_index` was strongly NEGATIVE relative to
2022-09-08 (short-wavelength-proxy group darker relative to the
long-wavelength-proxy group than the background) — which is structurally
the same signal `CDOM_LIKE`'s evidence rule looks for (short-group
depression without broadband brightening). The two modules were built and
run independently but agree on the direction of the seasonal difference
between the two dates, which is a modest but real internal-consistency
check, not assumed or forced.

**This is an optical hypothesis, not a water-quality diagnosis.** Every
`Fingerprint.to_dict()` output carries the same non-diagnostic disclaimer
DesalGuard's own module uses (reworded to also flag the group-level, not
named-wavelength, evidence basis): field sampling and laboratory analysis
would be required before treating "CDOM_LIKE" as an actual dissolved-
organic-matter finding rather than a coarse optical pattern match.

### 3.2a `CYANO_LIKE` built (2026-09-19), using the real per-band table

`docs/WATER_MASK.md` section 14.1 records how the real 224-band EnMAP
wavelength/FWHM table was obtained and cross-validated. With it,
`pipeline/fingerprint.py` gained `local_band_depth()` and the
600/620/650 nm phycocyanin shoulder windows — the SAME formula and
literature shoulder wavelengths DesalGuard-main's own `CYANO_LIKE` rule
uses (Clark & Roush 1984 local-band-depth; Simis et al. 2005's 600/620/
650 nm phycocyanin absorption window — general science, reused verbatim,
not coastal-tuned business logic). What is NOT reused is DesalGuard's
absolute `d620 > 0.03` cutoff: this AOI's own background population's d620
distribution is computed instead (pooled over the same 17-pixel/2-date
background `pipeline/anomaly.py` already uses — n=34 pixel-spectra, mean
d620=0.02147, std=0.01672), and a pixel's CYANO_LIKE evidence is scored as
a z-score of its own d620 against THAT distribution — the same
this-AOI's-own-background standard every other class and module here uses,
not DesalGuard's coastal absolute value.

CYANO_LIKE evidence is additionally gated on some co-occurring red-edge
(BLOOM_LIKE-style) support (`d620_z > 1.0 AND red_edge_excess > 0.0`),
mirroring DesalGuard's own co-requirement that BLOOM_LIKE support fire
first — phycocyanin is a bloom pigment, so an isolated 620 nm dip with no
broader bloom-like signal is treated as weaker evidence on its own.

**Result across all 20 test-core pixels (10/date x 2 dates):**

- **2022-09-08: 0/10 pixels clear the gate.** Every pixel's
  `red_edge_excess` is negative on this date (no red-edge/bloom-like
  co-signal at all), so CYANO_LIKE scores 0 for all 10 regardless of their
  individual d620_z values (which range -2.46 to +2.27 — some individually
  above the z>1.0 mark, but the AND-gate with red-edge support is what
  actually decides it, and none clear both).
- **2024-04-24: 1/10 pixels clear the gate** — pixel (row 7, col 15):
  `d620_z=1.32` (raw d620 excess +0.0221 over background), `red_edge_excess
  =0.99`, contributing a CYANO_LIKE score of 1.323. It does NOT become that
  pixel's top class — `CDOM_LIKE` scores higher there (1.954, driven by
  that same pixel's blue-region depression evidence) — so this pixel's top
  hypothesis stays CDOM_LIKE, with CYANO_LIKE recorded as real, non-zero,
  SECONDARY evidence (visible in that pixel's `evidence` list, not
  discarded because it lost).
- **CYANO_LIKE is never the top class for any of the 20 test-core pixels
  across either date.** Stated plainly rather than reading the one
  non-zero score as a detection: one pixel produced real supporting
  evidence for it, and it is reported as such (not hidden), but it never
  wins against the pixel's other evidence.

Full per-pixel d620/z-score/evidence values are in
`data/anomaly/anomaly_fingerprint_report.json` (`d620_this_pixel` and the
`fingerprint.evidence`/`fingerprint.caveats` fields per pixel).

**A stale claim this update also corrected:** `fingerprint_pixel()`'s
per-pixel caveat and the module's `_DISCLAIMER` previously stated
unconditionally that this AOI "lacks a per-band wavelength table" — true
when written, now false for CYANO_LIKE specifically. Both are now
conditional: they still correctly describe BACKGROUND_WATER/SEDIMENT_LIKE/
BLOOM_LIKE/CDOM_LIKE/SURFACE_FILM_LIKE/UNKNOWN_ANOMALY as group-level
proxies (unchanged, still true), while stating that CYANO_LIKE alone uses
the real per-band table when one is supplied to the call.

### 3.3 `BOTTOM_INFLUENCED` — still not computable, and why that is unaffected by section 3.2a

Unlike `CYANO_LIKE`, `BOTTOM_INFLUENCED` was never blocked by the missing
wavelength table — it needs a distance-from-shore raster (not built: the
wet core is a single ~10-30 px blob, not a coastline with an inside/outside
geometry to measure distance against) and a more precisely placed NIR band
than even the real per-band table would resolve on its own without that
geometry. Obtaining the wavelength table (section 3.2a) does not unblock
this class; it remains explicitly excluded, not silently omitted.

## 4. Genuinely tuned vs. placeholder — full list

| Parameter | Value | Status |
|---|---|---|
| `n_groups=6` (anomaly + fingerprint feature space) | 6 | **Genuinely tuned** for this AOI's sample size — chosen so the pooled background clears `robust_background()`'s own `n >= n_features*3` minimum with headroom. |
| `test_mask` / `background_mask` definitions | `persistent_wet_core(0.10)` / `persistent_wet_core(0.13)` | **Genuinely derived** from this AOI's own validated threshold sweep (`docs/WATER_MASK.md` section 12), not borrowed. |
| `shrinkage=0.15` (covariance regularization) | 0.15 | **Placeholder.** Structurally motivated (background is small even after group-reduction), but the specific value is a round, conservative choice, not fit against labeled data. |
| `alpha=0.10` (RX empirical threshold false-alarm rate) | 0.10 | **Placeholder**, widened from DesalGuard's 0.01 because a 1%-tail estimate from ~28-34 samples is not resolvable — reported as a rough marker, not a calibrated rate. |
| `min_pixels=1`, `close_iterations=0` (event extraction) | 1, 0 | **Genuinely tuned** for this AOI's scale — DesalGuard's `min_pixels=25` would discard the entire possible signal outright (see `pipeline/anomaly.py` `extract_events()` docstring). |
| Fingerprint evidence WEIGHTS (`_W_PRIMARY`, `_W_SECONDARY`, `_W_CONTRADICT`) | 1.0 / 0.4 / -0.5 | **Placeholder.** Structure (primary evidence should outweigh secondary/contradicting evidence) is reasoned; the specific numbers are not fit against any labeled example — none exists for this AOI. |
| Fingerprint class registry (which classes are computable at all) | see section 3.1 table | **Genuinely derived** from this AOI's actual data gaps, not a placeholder. As of 2026-09-19, CYANO_LIKE is computable (section 3.2a, real per-band table obtained); BOTTOM_INFLUENCED remains correctly excluded (section 3.3, a geometry gap unrelated to the wavelength table). |
| CYANO_LIKE gate/z-score (`d620_z > 1.0 AND red_edge_excess > 0.0`) | z-threshold 1.0 | **Placeholder threshold, genuinely-derived population.** The z>1.0 cutoff is a structural placeholder (same category as the other evidence weights below); the population it is scored against (this AOI's own 34-pixel-spectra background d620 mean/std) is genuinely derived, not borrowed — see section 3.2a. |

## 5. Reproducing this

```
python3 scripts/derive_anomaly_and_fingerprint.py \
    "sourced data/ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z-SPECTRAL_IMAGE_COG.tiff" \
    "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff"
```

Requires `docs/WATER_MASK.md` section 12's two source files. Rebuilds both
`persistent_wet_core()` masks, runs `rx_anomaly()` and
`fingerprint_pixel()` per pixel per date, extracts events, and saves a full
JSON report plus a provenance record to `data/anomaly/`.
