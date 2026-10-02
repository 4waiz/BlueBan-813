# Area of Interest Selection

**Selected AOI: Shawka Dam, Ras Al Khaimah, United Arab Emirates**
Locked polygon: `aoi/shawka_dam.geojson` (bbox `[56.040957, 25.103107, 56.047007, 25.10721]`,
EPSG:4326) — an irregular ~660 m x 460 m trace of the dam/wadi channel, not a bbox
approximation.

This document exists for the same reason DesalGuard-main's does: the AOI was not
picked first and justified after. It was picked *because* a hard data-availability
gate was run first, and the polygon was locked before any scene search, not fitted
to whichever scene turned up.

---

## 1. Why an inland AOI at all

The challenge is titled "Water Quality & Inland/Coastal Water Intelligence," and its
dataset description lists rivers and reservoirs alongside coastal zones as target
water bodies. DesalGuard-main's coastal PoC (Gulf of Annaba, Algeria) has no inland
component. That is the gap this project closes — nothing else. This is not a
redo of the coastal work, not a merge into DesalGuard-main, and not a unilateral
decision that inland coverage is strictly required; it is making sure a real,
working answer exists on the inland side either way.

---

## 2. The go/no-go gate, run before any AOI was locked

**Target:** Shawka Dam, RAK (owner-supplied, locked polygon; not chosen by search).

**Method:** check whether Planet Tanager's open STAC catalog (every collection, not
just `coastal-water-bodies`) or EnMAP's open archive has any hyperspectral scene
over this AOI or, failing that, any UAE dam.

### 2.1 Tanager — checked exhaustively, confirmed negative

DesalGuard-main's own audit enumerated Tanager's `coastal-water-bodies` collection
(43 items) and found 4 in the MENA region, none over an inland UAE water body. That
audit did not check Tanager's other 8 collections, so this project did. Tanager's
open-data catalog root (`planet.com/data/stac/tanager-core-imagery/catalog.json`)
lists 9 collections: GHG-plumes, energy-mining, natural-lands, agriculture,
coastal-water-bodies, urban, snow-ice, fire, ROCX2025.

Every collection's `collection.json` was fetched directly and every item's footprint
(each collection's `extent.spatial.bbox` array carries one entry per item, verified
against known scenes — e.g. the Gulf of Annaba entry matches DesalGuard-main's
primary scene bbox exactly) was checked against a UAE-wide bounding box
`[51.0, 22.0, 57.0, 26.6]`.

**276 items total** across all 9 collections as of the check date (2026-09-18) — up
from the 236 DesalGuard-main's own audit counted three days earlier; the archive is
growing fast. **Exactly one** touches the UAE at all: the same Tarif/Abu Dhabi
coastal scene (`20250511_074311_00_4001`, 51% cloud) DesalGuard-main's own audit
already found and rejected. **Zero Tanager coverage anywhere inland in the UAE, in
any collection.** Confirmed negative — not assumed, checked.

### 2.2 EnMAP — checked, confirmed positive, with one caught pitfall

Queried the open EnMAP STAC API directly (`geoservice.dlr.de/eoc/ogc/stac/v1`, no
authentication needed for search) against a generous box around the AOI. 15 L2A
items overlap.

**A pitfall worth documenting rather than silently avoiding:** 3 of those 15 looked
like the obvious best picks at first glance — `eo:cloud_cover: 0` and
`enmap:overallQuality: 2`. Checking `sun_elevation` on those three returned exactly
`0.0`, and cross-referencing the EnMAP FAQ confirmed why:
`enmap:overallQuality=2` specifically means **LOW QUALITY**, assigned when
*"sun elevation angle is less than or equal to 0"* — i.e. these are nighttime
ascending-node passes, not usable daytime imagery, despite reporting 0% cloud. They
are excluded and listed in `config/project.yaml` under `enmap.excluded_scenes` so
nobody re-adds them by re-running the same search without the same check. The
genuine daytime candidates are all `sat:orbit_state: DESCENDING` with
`enmap:overallQuality: 0` — which the DLR tutorial notebook confirms is their
*nominal* (good) code, the inverse of what the "2" figure suggests at a glance.

**Footprint verification, not point proximity.** The 25.10°N/56.0333°E coordinate
used for the initial search was a general "Wadi Shawka" Wikipedia geotag, not
confirmed to be the dam pool itself. Once the project owner supplied the locked
polygon, every candidate scene's *actual STAC footprint geometry* (a rotated
quadrilateral per scene, not its bbox) was tested against all 50 vertices of the
locked polygon by point-in-polygon:

| Date | Cloud | Footprint contains full locked polygon | Tile (matters — two tiles share a datatake ID) |
|---|---|---|---|
| 2022-09-08 | 0% | Yes (50/50 vertices) | `_006_`, not `_007_` (`_007_` misses the AOI) |
| 2024-04-24 | 0% | Yes (50/50 vertices) | `_006_`, not `_005_` (`_005_` misses the AOI) |
| 2024-04-20 | 4% | Yes (50/50 vertices) | single tile |
| 2023-12-30 | 7% | Yes (50/50 vertices) | `_014_` |
| 2024-11-22 | 7% | Yes (50/50 vertices) | `_006_` |

Both 0%-cloud dates hold up under the real footprint check. **Confirmed positive,
not assumed** — and the tile-selection error is recorded here precisely so it isn't
repeated.

### 2.3 Data in hand

The 2022-09-08 and 2024-04-24 scenes (tile `_006_` of each) were downloaded directly
by the project owner via the DLR/EOC Geoservice UMS account (self-service
registration; see `docs/DATA_ACCESS_AUDIT.md` for exactly what that required).
Files are in `sourced data/`, 415 MB and 421 MB respectively — the right order of
magnitude for a full 230-band cube at this footprint and close to the ~353-363 MB
product size the scenes' own metadata reports (the difference is expected: COG
re-encoding on download). This is **data in hand**, not access pending.

---

## 3. Wet-core evidence — reused, not recollected, and reported honestly

This AOI's water presence was already characterized in BluePulse-813 (an earlier,
separate, paused project), reused here by copy per the project owner's instruction.
Source: `data-access-log/shawka_dam_water_check.md` and
`data/baseline_indices_s2_landsat.csv` (BluePulse-813), method: NDWI computed per
10 m Sentinel-2 pixel across the full AOI window (2,806 pixels/scene) for 14 monthly
scenes, Sep 2023-Oct 2025, lowest cloud per month.

| Period | % of AOI pixels with NDWI > 0 | % with NDWI > 0.1 (stricter open-water) |
|---|---|---|
| Sep-Oct 2023 | 6.5-6.7% | 4.9-5.2% |
| **Nov-Dec 2023 (peak)** | **8.6-16.1%** | **6.8-13.6%** |
| Jan-Feb 2024 | 7.7-8.9% | 5.9-7.6% |
| Sep 2024-Feb 2025 | 1.7-12.2% | 0.5-8.5% |
| **Sep-Oct 2025 (most recent)** | **0.2-1.0%** | **0.0%** |

Reported the same way DesalGuard-main reports the Abu Dhabi rejection: plainly,
including the part that doesn't favour the AOI.

- **AOI-mean NDWI is negative in every one of the 14 sampled months** (range -0.06
  to -0.13) — the polygon traces the wadi channel, not the wet extent, so a naive
  AOI-mean check reads "no water" every time.
- **A real, persistent wet core exists inside the polygon at the pixel level**: max
  per-pixel NDWI reaches 0.41 (Nov 2023) and stays positive (0.15-0.33) through most
  of the 14 months — a genuine standing-water patch, consistent with a small dam
  pool, trackable at the pixel level even though it is a small minority of the AOI.
- **The wet fraction is not stable, and trends down sharply in the two most recent
  scenes available**: Sep 2025 was 1.0% wet (max NDWI 0.074), Oct 2025 was 0.2% wet
  (max NDWI 0.025, zero pixels above the stricter 0.1 threshold). As of the most
  recent available imagery, the AOI was close to fully dry.

**Open risk, carried forward rather than resolved here:** if the current
fall/winter 2026 season stays as dry as the last two sampled BluePulse scenes, the
wet core to point a hyperspectral anomaly detector at may be very small or absent
on any given acquisition date. BluePulse-813's own recommendation — tightening the
AOI to the sub-polygon where NDWI > 0.1 recurs across the wettest months, and
identifying one backup UAE MOEI dam candidate in case this one stays dry — is
reused here as an open flag for Step 5, not decided in this skeleton, per the same
instruction that produced it originally. **Still open, not decided here, per
explicit instruction (2026-09-19 batch): the backup-dam question and the
"is inland coverage strictly required" question both remain for the team.**

**Update (2026-09-19):** the pixel-level wet core this section anticipated is
now built, validated across both acquired EnMAP dates, and has an
anomaly/fingerprint layer running against it — see `docs/WATER_MASK.md`
section 12 and `docs/ANOMALY_AND_FINGERPRINT.md`. The 10-pixel validated
core is small (as this section already flagged it might be), which is
exactly why `pipeline/anomaly.py`'s background population is stated
plainly as too small for a calibrated detector rather than presented as
more solid than it is — see that document section 2.2.

**Update (2026-09-19, later same day):** this section's own NDWI series
(same source CSV, `data/baseline_indices_s2_landsat.csv`) has now also
been used to build an actual multi-scene temporal deviation detector
(z-scoring every month's NDCI/NDTI/RedTideIndex/NDWI against this AOI's
own per-sensor population), going beyond the single min/max-range
plausibility check this section and `docs/WATER_MASK.md` use elsewhere —
see `docs/TEMPORAL_BASELINE_DETECTOR.md`. Notably, it flags several
Sep-Oct 2025 observations (both sensors) as the largest deviations in the
whole 2-year series — the same two months this section already flags as
the driest/most-wet-fraction-depleted, now also standing out on
turbidity/chlorophyll proxies, not just wet fraction.

**Sentinel-3 OLCI is confirmed unusable for this AOI regardless of season** — all 6
sampled scenes in the BluePulse-813 check returned 0 valid water pixels, because
WFR L2 is land-masked at 300 m and the AOI is sub-pixel at that resolution. This is
carried into `config/project.yaml` as a checked fact, not re-tested here.

---

## 4. Reproducing this selection

The STAC enumeration and footprint-containment check are recorded step-by-step
above rather than as a script, since this skeleton phase has not yet built
`scripts/` for this project. The exact STAC endpoints, collection IDs, and query
parameters used are:

```
Tanager:  https://www.planet.com/data/stac/tanager-core-imagery/<collection>/collection.json
          for <collection> in: GHG-plumes, energy-mining, natural-lands,
          agriculture, coastal-water-bodies, urban, snow-ice, fire, ROCX2025

EnMAP:    https://geoservice.dlr.de/eoc/ogc/stac/v1/search
          ?collections=ENMAP_HSI_L2A&bbox=55.90,25.00,56.15,25.25
```

Footprint verification used the `geometry` field of each returned STAC item
(a `Polygon`) tested by ray-casting point-in-polygon against every vertex of
`aoi/shawka_dam.geojson`.
