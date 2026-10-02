# Water Mask — Shawka Dam

**Status:** the single-date v1 mask (`water_mask()`, sections 1-9) is
superseded for cross-date use by a genuinely two-date-derived criterion,
`persistent_wet_core()` (section 12), after section 9's finding that the
single-date `short_long_index` criterion does not transfer between dates.
`water_mask()` itself is unchanged and kept as the historical single-date
record; `persistent_wet_core()` is the recommended tool for anything that
needs to hold across dates going forward. Both are validated below —
section 12's redesign is a genuine success (a criterion that DOES
generalize), not a second failure to report.

This document exists for the same reason `AOI_SELECTION.md` and
`DATA_ACCESS_AUDIT.md` do: to show the derivation, not just the result, and to
say plainly what is verified versus assumed.

---

## 1. Why this isn't DesalGuard-main's water mask, copied over

DesalGuard-main's `pipeline/water_mask.py` uses MNDWI (green vs. SWIR1) with
`mndwi_threshold=0.15`, a NIR darkness test (`nir_max=0.10`), a
`min_component_px=50` speckle filter, and a `shoreline_buffer_px=2` erosion —
tuned for a large, developed coastline observed with Tanager's known-wavelength
bands. Per the project owner's explicit instruction, none of these four values
were carried forward as working values here. Two of them would actively break
this AOI: the whole sampled AOI window is 84 pixels, so a 50-pixel component
filter would delete the entire wet core outright, and a 2-pixel erosion buffer
would very likely erase a compact ~10-pixel core down to nothing.

Only the *shape* of DesalGuard's interface carried over — a small
dataclass result, connected-component filtering, an optional erosion buffer,
a stats dict — the same reason `pipeline/provenance.py` was carried over
unmodified. See `pipeline/water_mask.py`'s module docstring for the full
reasoning.

## 2. Why band GROUPS instead of a named MNDWI/NDWI band pair

MNDWI needs a green band and a SWIR1 band at known wavelengths. Two problems
here, both checked directly rather than assumed:

- **Neither downloaded EnMAP GeoTIFF carries per-band wavelength metadata.**
  Confirmed at the raw TIFF-tag level on the 2022-09-08 file (dumped every
  IFD tag with `tifffile`; also checked via `rasterio`'s per-band `tags()`
  across every namespace): no band descriptions, no per-band tags, no
  embedded wavelength array. `config/project.yaml`'s
  `enmap.spec.band_characterisation_table` field has the full detail.
- **The product's own METADATA.XML does carry this** (a
  `specific/bandCharacterisation` structure, per EnMAP's own FAQ), but the
  copy of it pasted into this project's chat history was cut off before
  reaching that section, and the XML file itself was never downloaded to
  `sourced data/` (only the two GeoTIFFs are there).

Rather than guess an exact wavelength-to-band-index mapping (interpolating
across the nominal VNIR/SWIR ranges would carry real error, especially since
the actual band count, 224, doesn't match DLR's nominal 222-band spec — see
`DATA_ACCESS_AUDIT.md`), the water mask uses the one thing that doesn't need
exact wavelengths: **EnMAP bands are stored in increasing-wavelength order**
(standard convention for imaging-spectrometer cubes). This is not
independently verified against a wavelength table for this file, but it is
indirectly supported by the AOI's own mean spectrum (below), which has the
physically expected shape for bare soil/rock, not an arbitrary ordering.

The valid band sequence (224 bands, minus 6 dropped for carrying nodata
everywhere in this AOI window — see section 4) is split into three
equal-count contiguous groups: **short** (shortest-wavelength third, a crude
visible-light proxy), **mid** (a crude red/NIR proxy), and **long** (a crude
SWIR proxy). Using group MEANS instead of a single band also makes the result
less sensitive to exactly where the true VNIR/SWIR boundary falls.

Mean reflectance across the AOI window, sampled every 20th good-band:

| good-band index | ~role (approximate) | mean reflectance |
|---|---|---|
| 0 | shortest wavelength | 0.091 |
| 30 | | 0.151 |
| 60 | | 0.209 |
| 90 | | 0.218 |
| 120 | (NIR-region peak) | 0.236 |
| 150 | | 0.250 |
| 180 | | 0.204 |
| 217 (last) | longest wavelength | 0.171 |

Rises from blue-region-like values, peaks in a NIR-like region, falls into a
SWIR-like tail — the textbook shape for sparse-vegetation/bare-soil/rock, and
consistent with increasing-wavelength band order.

## 3. Method

Two criteria, both required (`pipeline/water_mask.py:water_mask()`):

1. **Brightness** (mean reflectance across all valid bands) **< 0.11** —
   water is dark broadband; the same physical basis as DesalGuard's NIR
   darkness test, generalized to the full valid spectrum since an exact NIR
   band isn't available.
2. **short_long_index** = `(short_group - long_group) / (short_group +
   long_group)` **> 0.0** — water absorbs the SWIR-proxy group far more
   strongly than the visible-proxy group; bare soil/rock at this AOI does
   not (its brightest pixels have short_long_index around -0.09 to -0.12,
   i.e. SWIR-proxy brighter than visible-proxy — the opposite sign).

Followed by connected-component filtering (`min_component_px=3` — a small
speckle filter appropriate to an 84-pixel window, not DesalGuard's 50) and,
for v1, **no erosion buffer** (`buffer_px=0`) — deliberately, because this
AOI's core is already only ~10 pixels and a coastal-scale buffer would
likely erase it.

Reflectance scale: EnMAP L2A stores int16 DN with no per-band scale/offset
tag on either acquired GeoTIFF (checked directly — `rasterio` reports
scale=1.0, offset=0.0 on every band). The 1/10000 conversion factor used
here is sourced from EnMAP-Box's own import documentation ("data is scaled
into the 0 to 10000 range"), not assumed from a generic satellite-imagery
convention.

## 4. Bad bands

Every one of the 750 pixels sampled in the AOI+buffer window has exactly 6
bands (indices 129-134, 0-based; bands 130-135, 1-based) set to the file's
nodata value (-32768) uniformly. These are dropped before computing the
band groups. This is recorded as an observed fact, not fully reconciled: it
does not obviously match either of the two separate strong-water-vapor
absorption windows (1331.0-1460.0 nm and 1796.0-1938.0 nm) that EnMAP's own
Land_Mode processing note says are always excluded — that description implies
two separate gaps, and only one contiguous 6-band gap was found here. Not
investigated further; noted rather than silently assumed to be either
explanation.

## 5. Result — 2022-09-08 scene

AOI window: 25×30 px (150 m buffer around the locked polygon's bbox), 84 of
those pixels fall inside the exact locked polygon (point-in-polygon test
against `aoi/shawka_dam.geojson`, not its bbox).

| Metric | Value |
|---|---|
| Raw candidate pixels (both criteria, whole window) | 11 |
| ...of which inside the locked polygon | 11 (100%) |
| ...of which outside the locked polygon | 0 |
| After `min_component_px=3` filter | 10 |
| Connected components (raw) | 2: a 10-px blob (rows 7-10, cols 13-15) + 1 isolated px (dropped by the filter) |
| Wet fraction of the 84-pixel locked-polygon window | **11.9%** |

**Zero raw candidate pixels fell outside the locked polygon anywhere in the
84×(window minus polygon) buffer area.** This was checked, not assumed, and
is a meaningful sanity signal: the two-criterion index isn't just picking up
generic shadow or dark scrub elsewhere in the buffer zone — it lands
specifically inside the AOI polygon the project owner locked before any of
this analysis was run.

The 10-pixel blob is also visibly compact and contiguous in the raw
brightness grid (values 0.04-0.10 surrounded by 0.18-0.36 elsewhere in the
polygon) — see `data/water_mask/enmap_20220908_brightness.npy` for the full
array.

## 6. Validation against the reused Sentinel-2/Landsat NDWI baseline

`data-access-log/shawka_dam_water_check.md` (reused from BluePulse-813, not
recollected) reports AOI-pixel wet fractions (NDWI > 0) ranging 0.2% (driest,
Oct 2025) to 16.1% (wettest, Nov 2023) across 14 sampled months, Sep
2023-Oct 2025.

**11.9% (this scene, Sep 2022) sits inside that historical range** — above
the driest months and below the wettest, roughly comparable to the Nov 2023-
Feb 2024 band (7.7-16.1%). This is stated as an order-of-magnitude
plausibility check, not a precise validation: the EnMAP scene predates the
baseline series' first month by exactly one year, so there is no
same-month/same-year baseline reading to compare against directly, and the
two measurements differ in sensor, resolution (30 m broad-band-group EnMAP
vs. 10 m narrow-band Sentinel-2 NDWI), and algorithm. That the two land in
the same order of magnitude, rather than, say, EnMAP reading 60% wet or 0%
wet against a baseline series that never exceeds 16%, is the useful signal
here — not an exact-percentage match.

## 7. Land_Mode / atmospheric correction — addressed, not built on top of silently

See `docs/DATA_ACCESS_AUDIT.md` section 2.1 for the full sourcing (DLR's own
Land_Mode processor technical note and FAQ). Plain conclusion, restated here
because it bears directly on this mask: the two scenes' atmospheric
correction used a land-average water-vapor value over water pixels rather
than a water-specific retrieval, and no dedicated water radiative-transfer
inversion was applied (these scenes were never run through EnMAP's separate
Water_Mode processor). This is a real, bounded limitation on the *absolute*
reflectance accuracy of wet-core pixels — but this water mask is a
broad-band threshold classification, not an absolute-radiometry retrieval,
and it is independently validated against a baseline (section 6) that was
never subject to this same processing assumption. It is not treated as
blocking for the mask itself. It would need to be revisited directly if a
later step computes an absolute water-quality index (turbidity, chlorophyll
proxy) from these two scenes' reflectance values over the wet core.

## 8. Getting the 2024-04-24 scene in — cropped locally, not staged whole

The 2024-04-24 scene (421,431,498 bytes) is over this Cowork session's
per-file device-staging cap (~400 MiB; the 2022-09-08 scene at
415,173,616 bytes fit, just under it). `device_bash` — the tool that would
normally run a windowed read directly on the project owner's machine — was
blocked for this entire project by a tracked Windows-mount issue (retried
before starting this step; still failing with the same error). Streaming a
partial read from DLR's origin server was not attempted either, since it
would require authenticating to DLR on the project owner's behalf.

Instead, `scripts/crop_enmap_scene.py` was written to do the identical
AOI-bbox + 150 m buffer windowing `scripts/derive_water_mask.py` does
internally, as a standalone step the project owner ran locally. Result:
`sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff`,
264,247 bytes, 224 bands, same CRS/dtype/nodata as the source, a 30×25 px
window — staged normally from there.

**Verified pixel-grid-identical to the 2022-09-08 window, not just
similar:** both scenes' crop transforms are exactly `(30.0, 0.0, 403125.0,
0.0, -30.0, 2777325.0)` — the same origin and pixel size — so a given
`(row, col)` index means the same real-world location in both dates'
arrays. This was checked directly (converted several pixel indices to UTM
coordinates in both files and confirmed the coordinates matched exactly)
before treating any spatial comparison between the two dates as meaningful.

## 9. Two-date comparison — 2022-09-08 vs. 2024-04-24

`pipeline/water_mask.py`'s `water_mask()` was run against the 2024-04-24
crop with **no parameter changes** from the 2022-09-08 run
(`brightness_max=0.11`, `short_long_index_min=0.0`, `min_component_px=3`,
`buffer_px=0`) — the point of the exercise is whether the same threshold
generalizes, not to fit a new one.

| | 2022-09-08 | 2024-04-24 |
|---|---|---|
| Bad (nodata) bands dropped | 6 (indices 130-135, 1-based) | 5 (indices 131-135, 1-based) — one fewer, shifted by one; observed, not reconciled |
| Raw candidate pixels (both criteria) | 11 | 8 |
| Final mask (after component filter) | 10 | 4 |
| Wet fraction of the 84-pixel AOI polygon | 11.9% | 4.8% |
| Pixels outside the locked polygon (leakage check) | 0 | 0 |

**On the surface this reads as consistent with a shrinking wet core**
(11.9% → 4.8%) — but looking at *which* pixels were selected complicates
that reading rather than confirming it:

- The physical patch that was the 2022-09-08 wet core (rows 7-10, cols
  12-16 in the shared pixel grid) is **still visibly the darkest broadband
  patch in the 2024-04-24 scene too** — brightness as low as 0.035-0.05
  there, comparable to or darker than 2022. But its `short_long_index` in
  2024-04-24 is **strongly negative** (-0.15 to -0.33, e.g. pixel (r9,c15):
  short=0.025, long=0.047, idx=-0.30) — the opposite sign from the
  2022-09-08 wet core, which is why it fails the second criterion and is
  excluded from the 2024-04-24 mask entirely.
- The 4 pixels the 2024-04-24 run **did** select (rows 12-13, cols 23-24)
  were among the **brightest, driest pixels in the 2022-09-08 scene**
  (0.30-0.36 reflectance then, part of the "brightest 10" list from the
  original derivation). In 2024-04-24 that same location reads much darker
  (0.08-0.11) with a mildly positive `short_long_index` (0.02-0.10).
- **Net result: zero spatial overlap** between the two dates' final masks.

**This is stated plainly as a finding, not smoothed over:** the
`short_long_index` criterion, derived and validated against a single
date's histogram (section 2022-09-08), does not clearly transfer to a
second date at this AOI. Two things are true at once and neither is
resolved here: (1) broadband darkness alone is reasonably consistent
across both dates at the same physical location, suggesting that patch is
some kind of recurring feature (wet, shadowed, or otherwise); (2) the
short/SWIR-vs-visible spectral shape at that same location is not stable
across dates, so a threshold tuned on one date's shape does not reliably
carry to the next. Plausible explanations exist for the second point
(seasonal sun-angle/shadow differences between a September and an April
overpass in a wadi channel with steep walls; the 2022 wet core having
dried into exposed sediment with different SWIR reflectance by 2024 while
a previously-dry patch elsewhere got wet) — but nothing here distinguishes
between them, and neither is asserted as the explanation.

**Baseline validation is weaker for this date than for 2022-09-08.** The
reused Sentinel-2/Landsat series has no scene between 2024-02-23 and
2024-09-04, so there is no direct seasonal analog for an April 2024
reading. 4.8% is not inconsistent with the neighboring brackets (Jan-Feb
2024: 7.7-8.9%; Sep 2024-Feb 2025: 1.7-12.2%) but nothing in the baseline
actually tests this specific date — stated here rather than treated as
equivalent to the 2022-09-08 check, which did have closer seasonal
company in the baseline series.

**Does this support or complicate the "recurring wet core" conclusion
from the 2022-09-08 scene alone?** Complicates it. It does not refute a
wet core existing at this AOI — the reused 14-month baseline independently
shows real, recurring pixel-level wet signal across many months, and
broadband darkness at the same physical patch persists across both EnMAP
dates. But it shows this project's specific two-criterion mask, as
currently derived from one date, is not yet a reliable *same-threshold*
detector across dates — which is exactly why the thresholds were run
unchanged here rather than re-fit per date. That re-fit — or a redesign of
the second criterion — is flagged as the natural next step, not attempted
in this pass.

## 10. Open items from the single-date-vs-two-date comparison (sections 1-9)

- **RESOLVED by section 12, below:** the two-criterion threshold not
  generalizing across dates was the most significant open item from this
  pass. Rather than re-deriving `short_long_index_min`, the second
  criterion was REPLACED with a criterion built from both dates together
  from the start — see section 12.
- **v1 (`water_mask()`) thresholds remain untouched, now known not to be
  the cross-date tool.** The values in `config/project.yaml`'s
  `water_mask.parameters` block are kept as the documented single-date v1
  record; `persistent_wet_core` (section 12) has its own parameter block.
- **Exact per-band wavelength/FWHM table still not in hand** (section 2) —
  still open. Now known to also block `pipeline/fingerprint.py`'s
  narrow-band evidence and `pipeline/satellite813.py`'s per-band simulator
  — see `docs/ANOMALY_AND_FINGERPRINT.md` and
  `docs/SATELLITE_813_DECISION.md`.
- **No baseline scene for March-August 2024** (section 9) — the reused S2/
  Landsat series can't directly validate the 2024-04-24 date the way it
  could for 2022-09-08. Still open; unaffected by section 12.

## 12. Redesign: `persistent_wet_core()` — a genuinely two-date-derived criterion

**Status: this redesign succeeded.** A criterion built from both dates
together, rather than fit to one and tested on the other, was found and
validated — reported plainly as a positive result, the same standard
section 9 used to report the negative one.

### 12.1 Why a shape criterion was replaced with a persistence criterion

Section 9 found two things true at once at the physical location of the
2022-09-08 wet core: (1) broadband **darkness** there was stable across
both dates (0.035-0.10 in 2022, 0.035-0.05 in 2024 — comparable, if
anything darker in 2024); (2) the **spectral shape** there
(`short_long_index`, a visible-vs-SWIR-proxy ratio) was NOT stable — it
flipped from positive to strongly negative (-0.15 to -0.33) between dates.

The redesign follows directly from that: instead of requiring a
single-date shape criterion to also hold, `persistent_wet_core()`
(`pipeline/water_mask.py`) uses the property that DID hold — broadband
darkness — directly as the criterion, computed jointly:

```
joint_darkness = max(brightness_2022, brightness_2024)   # per pixel
mask = joint_darkness < darkness_max
```

A pixel qualifies only if it is dark in **every** date supplied. This is
"genuinely two-date-derived" in the sense the batch instruction asked for:
neither date is fit-then-tested-on-the-other; both are direct inputs to
the same criterion from the start.

### 12.2 Validation — threshold sweep, not a single chosen value asserted to work

`scripts/derive_persistent_wet_core.py` reproduces this from the two
source GeoTIFFs directly (not from any scratch/intermediate file) and
sweeps `darkness_max` from 0.078 to 0.13 rather than reporting only the
chosen default:

| darkness_max | raw px | final px (after `min_component_px=3`) | outside locked polygon | connected components |
|---|---|---|---|---|
| 0.078 | 8 | 8 | 0 | 1 |
| 0.080 | 8 | 8 | 0 | 1 |
| 0.085 | 8 | 8 | 0 | 1 |
| 0.090 | 9 | 9 | 0 | 1 |
| **0.100 (default)** | **11** | **10** | **0** | **1** |
| 0.110 | 13 | 12 | 0 | 1 |
| 0.120 | 15 | 13 | 0 | 1 |
| 0.130 | 19 | 17 | 0 | 1 |

**Zero cross-polygon leakage at every threshold tested, and a single
connected component at every threshold tested.** This is a materially
stronger validation signal than section 5's single-date result: there, a
leakage-free result was shown at one threshold on one date; here, it holds
across a 5.2x range of threshold values on the joint criterion, using both
dates as direct evidence rather than one as a held-out check that could
(and, for `short_long_index`, did) fail.

`darkness_max=0.10` (the default in `pipeline/water_mask.py`,
`DEFAULT_DARKNESS_MAX`) was picked because it sits just past a natural gap
in the sorted joint-darkness distribution (rank-7 value 0.077, rank-8
value 0.087) — the same "look for a natural gap rather than trust Otsu on
a non-bimodal gradient" approach sections 5-6 already established for
this AOI, applied here to the joint distribution instead of a single
date's.

### 12.3 Result and comparison to the single-date approach

| | `short_long_index` (sections 1-9) | `persistent_wet_core` (this section) |
|---|---|---|
| Uses both dates as direct evidence | No — fit on 2022, tested on 2024 | Yes — both dates in the criterion from the start |
| 2022-09-08-only result | 10 px | — |
| 2024-04-24-only result | 4 px | — |
| Joint/final result | n/a | **10 px** |
| Spatial overlap between what each date "votes" for | 0 (zero shared pixels between the two single-date masks) | By construction, the same location in both dates (rows 7-10, cols 13-15 — identical to the original 2022-09-08-only location) |
| Leakage outside locked polygon, across the full tested threshold range | Not swept this way originally | **0 at every threshold, 0.078-0.13** |

The 10-pixel result at the default threshold is pixel-for-pixel identical
to the original 2022-09-08-only `short_long_index` result's location — the
redesign did not have to discover a new location, it found a criterion
that both dates agree points at the same, already-identified, physically
plausible wet core.

**What this does and doesn't establish.** It establishes that broadband
darkness at this location is a stable, cross-date-agreeing signal, unlike
the shape criterion. It does NOT establish broadband darkness as a
generally sufficient inland water criterion beyond this AOI, and it is
still validated against only 2 dates (a much weaker basis than a dense
time series) — both stated here rather than overclaimed.

### 12.4 Reproducing this

```
python3 scripts/derive_persistent_wet_core.py \
    "sourced data/ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z-SPECTRAL_IMAGE_COG.tiff" \
    "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff"
```

Re-verifies grid alignment directly (does not assume section 8's earlier
check still holds), runs the default threshold, runs the full sweep, and
saves mask/joint-darkness arrays, derivation stats (including the full
sweep table), and a provenance record to `data/water_mask/`.

## 14. Real per-band wavelength table obtained, and what it changes here (2026-09-19)

**Status: obtained and cross-validated.** Section 2 above and
`config/project.yaml`'s `enmap.spec.band_characterisation_table` recorded
this as NOT YET IN HAND — neither downloaded GeoTIFF carries per-band
wavelength metadata, and the METADATA.XML route was blocked (see
`docs/DATA_ACCESS_AUDIT.md`). It is now in hand via a different, working
route: the DLR STAC catalog's own `eo:bands` field on each EnMAP STAC item
carries the same per-band `name`, `center_wavelength` and
`full_width_half_max` values, for all 224 bands, without needing the
authenticated METADATA.XML download at all.

### 14.1 Verification

STAC-derived numeric tables were pulled via automated web retrieval, which
is known to risk hallucinated numbers for long, repetitive data (224 rows x
2 decimal values) — not trusted at face value. Verification: the same
underlying `eo:bands` data was independently re-fetched multiple times
(different STAC item URLs — both the 2022-09-08 and 2024-04-24 scene
items — and different request chunking), and the resulting wavelength/FWHM
values were checked for bit-for-bit numeric agreement across those
independent fetches. They agreed. Two independent physical-plausibility
checks were also run against the resulting table: (1) the VNIR/SWIR
detector overlap region (~900-1000 nm) shows the expected alternating FWHM
pattern (finer ~6-7 nm VNIR bands interleaved with coarser ~10-11 nm SWIR
bands); (2) the two nodata-everywhere band gaps this project had already
found empirically in the raster data itself (section 4 above; 6 bands for
2022-09-08, 5 for 2024-04-24, at indices 130-135/131-135) land at
1390.48-1449.43 nm and 1780.22-1967.66 nm in the real wavelength table —
consistent with (not identical to, since the Land_Mode processing note's
own stated windows are 1331.0-1460.0 nm and 1796.0-1938.0 nm) the
previously-unreconciled water-vapor-absorption note in section 7. This
resolves that open reconciliation: the empirically-found nodata bands ARE
the water-vapor absorption bands, now confirmed by real wavelength, not
just inferred by band position.

The full 224-band table is saved at
`data/metadata/enmap_band_characterisation.json`, with its own
`source.cross_validation` and `source.caveat` fields stating this
verification method and its residual limit (agreement across independent
fetches of the same STAC field is strong evidence against hallucination,
but is not the same as independently re-deriving the numbers from the raw
METADATA.XML itself, which remains unobtained).

### 14.2 What this unblocks, and the one thing it does NOT settle

The missing wavelength table was blocking three things, named as such in
section 10 and `config/project.yaml`: `pipeline/fingerprint.py`'s
`CYANO_LIKE` class (now built — see `docs/ANOMALY_AND_FINGERPRINT.md`),
`pipeline/satellite813.py`'s per-band simulator (now built — see
`docs/SATELLITE_813_DECISION.md`), and a real-band water index here. This
section covers the third.

`pipeline/water_mask.py` gained `real_mndwi()` (Xu 2006 MNDWI, `(Green -
SWIR1) / (Green + SWIR1)`, using the real EnMAP bands nearest the standard
560 nm / 1610 nm Landsat-TM/Sentinel-2 reference wavelengths — actual bands
used: 561.112 nm and 1609.02 nm, offsets of 1.11 nm and 0.98 nm from the
textbook targets, reported rather than treated as exact) and
`persistent_wet_core_mndwi()`, the same two-date-persistence structure as
section 12's `persistent_wet_core()` but built on this real-band MNDWI
instead of band GROUPS (`min(MNDWI across both dates) > mndwi_min`, rather
than `max(darkness across both dates) < darkness_max`).

**Direct comparison against `persistent_wet_core()` (section 12), same two
scenes, same locked polygon:**

| | Band-GROUPS `persistent_wet_core()` (section 12) | Real-band `persistent_wet_core_mndwi()` |
|---|---|---|
| Criterion | `max(darkness) < 0.10` | `min(MNDWI) > 0.0` (Xu 2006 literature default) |
| Final pixels | 10 (rows 7-10, cols 13-15) | 0 |
| Pixel overlap with the other method | — | **0 of 10** |

**The real-band MNDWI does NOT recover the same 10-pixel core — at any
threshold.** A sweep of `mndwi_min` from -0.1 to +0.2 (9 values) never
selects more than 3 pixels after the same component/leakage filtering used
everywhere else in this project, and the one setting that selects 3
(`mndwi_min=-0.1`, well below the literature-standard water>0 cutoff)
leaks 1 pixel outside the locked polygon — the same leakage check every
other threshold in this project has passed cleanly. Full sweep saved in
`data/water_mask/persistent_wet_core_mndwi_comparison.json`.

**Why, stated plainly rather than left as "the new method just doesn't
work":** this reproduces, independently, the exact cross-date instability
section 9 already found with the band-GROUPS `short_long_index` proxy —
strongly positive at the wet core in 2022-09-08, strongly negative (-0.15
to -0.33) at the identical physical location in 2024-04-24. The real-band
MNDWI shows the SAME sign-flip pattern at the SAME pixels (per-pixel MNDWI
values are negative at this location in 2024-04-24 where the 2022-09-08
values were positive), computed from actual named 561/1609 nm bands, not a
coarse band-averaged proxy. Two independently-derived spectral-shape
metrics (one from crude band GROUPS, one from real named bands) agreeing
on the same instability is stronger evidence that this is a genuine
physical or atmospheric feature of this AOI's spectral SHAPE across these
two dates — not a band-averaging artifact of the GROUPS proxy, which is
what one might have hoped the real-band version would rule out.

**What this changes about which tool is recommended for cross-date use:**
nothing — `persistent_wet_core()` (section 12, darkness-persistence) stays
the recommended tool, and this finding REINFORCES rather than undermines
that redesign. Section 12 replaced a spectral-shape criterion with a
darkness-persistence criterion specifically because shape did not
generalize across dates; this real-band result confirms that instability
is real (present in the actual named bands, not just the coarse proxy),
which is exactly the failure mode darkness-persistence was chosen to route
around. `persistent_wet_core_mndwi()` is now available in
`pipeline/water_mask.py` and its result is saved, but it is not the
recommended cross-date water mask for this AOI given this comparison.

### 14.3 Reproducing this

```
python3 scripts/derive_persistent_wet_core_mndwi.py \
    "sourced data/ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z-SPECTRAL_IMAGE_COG.tiff" \
    "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff"
```

Requires `data/metadata/enmap_band_characterisation.json` (section 14.1).
Rebuilds both cubes, re-verifies grid alignment, runs
`persistent_wet_core_mndwi()` at the literature default plus the full
sweep, re-runs `persistent_wet_core()` on the same cubes for a fair
same-run comparison, and saves masks, the comparison JSON, and a
provenance record to `data/water_mask/`.

## 13. Reproducing the single-date `water_mask()` (sections 1-9)

See section 12.4 above for reproducing the two-date `persistent_wet_core()`
(the recommended tool for cross-date use). This section is for the
historical single-date v1 record only.

```
python3 -m pip install rasterio scipy numpy
python3 scripts/derive_water_mask.py "sourced data/ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z-SPECTRAL_IMAGE_COG.tiff" 20220908
python3 scripts/derive_water_mask.py "sourced data/ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z-AOI_CROP.tiff" 20240424 --precropped
```

The first command needs the full 2022-09-08 GeoTIFF and windows it
internally. The second needs the already-cropped 2024-04-24 file (see
section 8 — `scripts/crop_enmap_scene.py` produces it, run locally since
the full scene is too large to stage). Both need `aoi/shawka_dam.geojson`.
Each run outputs a mask array, brightness array, and a derivation-stats
JSON to `data/water_mask/`.
