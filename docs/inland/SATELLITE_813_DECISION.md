# Satellite 813 — Inland Decision

**Status: REVISED (2026-09-19).** The original decision (`inland_simulator_built = false`,
below in section 1 for the record) has been reversed: a per-band, per-pixel
EnMAP-to-813 Gaussian-SRF simulator IS now built
(`pipeline/satellite813.py:simulate_813_enmap()`), because the specific
condition this document itself named for reversing that decision (section 3,
original text) is now met. This document records both the original
reasoning and why it changed, per the same standard `docs/WATER_MASK.md`
and `docs/ANOMALY_AND_FINGERPRINT.md` use: say plainly what was decided,
why, and — when a decision changes — why it changed, not just what is
built now.

The coarse coverage/configuration comparison (section 2 below) is NOT
withdrawn — it remains built, saved, and useful as a whole-range-average
companion view. The per-band simulator (section 3, new) is additional,
finer-grained capability, not a replacement.

---

## 1. The original decision (2026-09-19, superseded same day — kept for the record)

**`inland_simulator_built = false`, by design, not by omission — at the time.**

DesalGuard-main's `simulate_813()` resamples real Tanager reflectance onto
813's published band configuration with a Gaussian spectral-response
function (`gaussian_srf_matrix()` / `resample_spectra()`). That machinery
needs a real SOURCE wavelength array — DesalGuard's `TanagerScene` reads
Tanager's directly from the HDF5 file's own calibration attributes. 813's
OWN configuration is already an explicit, documented assumption in
DesalGuard's own code (`spec_813()`: "Absent a public band table we lay
205 bands evenly across the stated range... an explicit, documented
assumption") — but that one assumption sits on top of a REAL, measured
source axis.

At the time this was first decided, this project had no equivalent real
source axis. Neither acquired EnMAP GeoTIFF carried per-band wavelength
metadata. Building a faithful simulator would have required laying
EnMAP's 224 bands out evenly across its published 420-2450 nm range TOO —
a second, independent assumption, for an instrument where non-uniform
per-band spacing is a real possibility. Stacking two independently assumed
wavelength grids and running a Gaussian resampling convolution over them
would have produced output indistinguishable in form from DesalGuard's
real simulation while actually being built from two guesses — "fabricated
or upsampled detail presented as real," which this project's honesty
standard rules out. So it was not built then.

## 2. What was built instead, and remains built

`pipeline/satellite813.py`'s `enmap_813_coverage_comparison()` — a coarse
comparison using only values already independently verified elsewhere in
this project (EnMAP's total band count, published overall spectral range,
spatial resolution; all cited in `config/project.yaml` /
`docs/DATA_ACCESS_AUDIT.md`), reporting SCENE-AVERAGE figures rather than
any per-band correspondence:

| Metric | 2022-09-08 scene | 2024-04-24 scene |
|---|---|---|
| EnMAP spectral range | 420-2450 nm | 420-2450 nm |
| 813 published spectral range | 400-1700 nm | 400-1700 nm |
| Overlap | 420-1700 nm (1280 nm) | 420-1700 nm (1280 nm) |
| EnMAP valid bands this AOI | 218 (224 - 6 nodata) | 219 (224 - 5 nodata) |
| EnMAP whole-range average spacing | ~9.4 nm/band | ~9.3 nm/band |
| 813 published whole-range average spacing | ~6.4 nm/band | ~6.4 nm/band |
| Spatial resolution ratio (EnMAP / 813) | 1.5x (30 m vs 20 m) | 1.5x |

This table says EnMAP's spectral range fully contains 813's published
range, and that on a whole-range average basis 813's published
configuration is the more densely sampled one. It does NOT say anything
about what a specific EnMAP pixel would read on a specific 813 band — that
question is what section 3 below now answers, with real data.

Reproducing this comparison alone (no scene files needed):
```
python3 scripts/derive_813_coverage_comparison.py
```

## 3. The revised decision: a real per-band simulator is now built

### 3.1 Why the condition for reversal is met

This document's own original section 3 stated the reversal condition
plainly: "If `config/project.yaml`'s `enmap.spec.band_characterisation_table`
item is resolved..., a faithful Gaussian-SRF simulator becomes buildable
here with the SAME one-assumption standard as DesalGuard's own (813's grid
assumed, EnMAP's grid real, exactly DesalGuard's own situation with
Tanager)."

That item is now resolved. `docs/WATER_MASK.md` section 14.1 records how:
EnMAP's real per-band centre-wavelength/FWHM table was obtained from the
DLR STAC catalog's own `eo:bands` metadata (not the METADATA.XML route
that was blocked — a different, working route to the same underlying
per-band fact) and cross-validated by independently re-fetching it
multiple times and checking bit-for-bit numeric agreement, plus two
physical-plausibility checks (the VNIR/SWIR detector-overlap FWHM pattern;
the empirically-found nodata band gaps landing exactly where the real
wavelength table shows a genuine gap in EnMAP's own band-centre sequence).
It is saved at `data/metadata/enmap_band_characterisation.json`.

EnMAP's axis is now exactly as real as Tanager's was for DesalGuard's own
simulator — read from the source product's own metadata (via STAC), not
laid out evenly by this project. 813's own grid remains the ONE explicit,
documented assumption (`spec_813()`, unchanged, copied verbatim from
DesalGuard-main) — the same one-assumption situation DesalGuard's own
Tanager-to-813 simulator is in, not a weaker one. Building the resampler
now no longer requires stacking two guesses; it requires the same single,
disclosed guess DesalGuard's own code already carries.

### 3.2 What is built

`pipeline/satellite813.py:simulate_813_enmap()` — a per-band Gaussian-SRF
resample of an EnMAP reflectance cube onto 813's published configuration.
`gaussian_srf_matrix()` and `resample_spectra()` are copied UNMODIFIED from
DesalGuard-main (general cross-sensor band-synthesis machinery, the
standard method used for sensor intercomparison in ISOFIT/HyTools — not
coastal-tuned business logic, so nothing to re-derive). `min_support=0.5`
(how much of a target band's Gaussian weight must land on finite source
data before the resampled value is trusted vs. marked NaN) is likewise a
general engineering default, reused at DesalGuard's own value rather than
re-derived, in the same category as its own `truncate=3 sigma` Gaussian
window default — a structural resampling-honesty knob, not an AOI-fit
detection threshold.

No spatial resampling is attempted (EnMAP's 30 m stays 30 m, not upsampled
to 813's 20 m) — the same position DesalGuard's own simulator takes,
stating outright that upsampling "would invent spatial detail the source
never measured."

### 3.3 Result, run against both acquired EnMAP scenes' persistent-wet-core pixels

```
python3 scripts/derive_813_simulation.py \
    "sourced data/ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z-SPECTRAL_IMAGE_COG.tiff" \
    "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff"
```

Real EnMAP source: 224 bands, 418.4-2450.3 nm (from
`data/metadata/enmap_band_characterisation.json`). 813 target: 205 bands,
400.0-1700.0 nm (`spec_813()`, unchanged).

**Coverage — a real, computed answer, not a whole-range-average estimate:**
196 of 813's 205 published bands (96%) have real EnMAP source support
somewhere in their Gaussian response window, for both dates. The 9
unsupported bands are NOT one contiguous span — they split into two real,
disjoint gaps:

- **2 bands at 400.0-406.4 nm** — below EnMAP's real coverage floor
  (EnMAP's own lowest band centre is 418.4 nm, so 813's published range
  extending down to 400 nm has no EnMAP data at all in that narrow sliver).
- **7 bands at 1400.5-1438.7 nm** — landing inside EnMAP's own real
  wavelength-axis gap (the water-vapor absorption discontinuity documented
  in `docs/WATER_MASK.md` section 14.1, where EnMAP's band-centre sequence
  itself jumps from ~1390 nm to ~1449 nm with no bands in between — not
  merely nodata pixel VALUES, an actual absence of band centres in that
  window).

**Per-pixel:** at every one of the 10 persistent-wet-core test pixels, on
BOTH dates, additional 813 bands come back NaN beyond those 9
structurally-unsupported ones — 11 extra bands (2022-09-08) and 9 extra
(2024-04-24) — from real per-pixel EnMAP nodata (the same 6-band/5-band
per-scene nodata gap already documented in `docs/WATER_MASK.md` section 4,
now propagating correctly through `min_support` gating into which 813
bands the resampled spectrum can and cannot report for that specific
pixel). This is stated as a real, computed finding — it is not a fixed
number baked into the simulator, it comes out of `resample_spectra()`'s
own per-target-band support-fraction check running against each pixel's
actual data.

Full per-pixel simulated 813-band spectra (`spectrum_813`, NaN where
unsupported) for all 20 test-core pixels are saved in
`data/satellite813/enmap_to_813_simulation.json`.

### 3.4 What this does and does not establish

It establishes, with real per-band EnMAP data rather than a whole-range
average, which parts of 813's published band configuration this AOI's
EnMAP coverage can and cannot stand in for, and exactly which 813 bands
lose data at which pixels because of EnMAP's own real nodata gaps — a
finer, per-band, per-pixel answer than section 2's coverage comparison
could give. It does NOT retrieve a real 813 observation of this AOI (813
itself remains incubation-only, programme-wide, unrelated to this
project's data access); it is a simulation of what 813 would plausibly
read GIVEN 813's published (still assumed) band layout, not a real 813
measurement. It also does not resolve 813's own one remaining assumption
(its bands are laid out evenly across its published range) — that stays
exactly as uncertain as it was, and exactly as uncertain as it is in
DesalGuard-main's own Tanager-based simulation.

## 4. Reproducing this

```
python3 scripts/derive_813_coverage_comparison.py   # coarse comparison, section 2, no scene files needed
python3 scripts/derive_813_simulation.py \           # real per-band simulator, section 3
    "sourced data/ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z-SPECTRAL_IMAGE_COG.tiff" \
    "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff"
```

Both save their own report and provenance record to `data/satellite813/`.
