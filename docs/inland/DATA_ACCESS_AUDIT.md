# Data Access Audit

**Project:** 813 Inland Complement · Team Kanban
**Challenge:** Water Quality & Inland/Coastal Water Intelligence
**Audit performed:** 2026-09-18
**Auditor:** verified against live STAC endpoints, live DLR registration pages, and
actual downloaded files, not assumed. Where a claim below could not be fully
verified, it is stated as such rather than presented as confirmed.

This document records what data can *actually* be obtained for the inland AOI, how,
and under what terms — the same purpose DesalGuard-main's own audit serves for the
coastal side.

---

## 1. Headline finding: EnMAP is the primary hyperspectral source, and its licence
term is materially different from Tanager's — flagged here, not buried

Unlike the coastal side, where Satellite 813 is the unavailable sensor and Tanager
is the open, CC-BY-4.0-licensed substitute, on the inland side it is **Tanager**
that has zero usable coverage (see `AOI_SELECTION.md` section 2.1 — all 9 open-data
collections enumerated, 276 items checked, exactly one touches the UAE and it is
coastal) and **EnMAP** that is the working substitute.

EnMAP's own STAC collection record for L2A products states:

```
"license": "proprietary"
```

(queried directly: `https://geoservice.dlr.de/eoc/ogc/stac/v1/collections/ENMAP_HSI_L2A`)

This is not CC-BY. Access is governed by DLR's Acceptable Use Policy, which states
users "shall provide appropriate acknowledgement of support or citation ... as
required by the body or bodies granting you access, see respective licenses" — i.e.
it defers to a per-product license this audit has not yet located and read in full.
**Before this data appears in any public submission or repository, confirm the
exact redistribution/display terms** — this audit stops short of that confirmation
and states so plainly rather than assuming CC-BY-equivalent terms because Tanager's
were.

---

## 2. What we CAN access, verified

### 2.1 EnMAP HSI L2A — hyperspectral (PRIMARY)

| Property | Value | How verified |
|---|---|---|
| Search access | Open STAC API, no authentication | Queried directly, live |
| STAC endpoint | `geoservice.dlr.de/eoc/ogc/stac/v1` | `pystac_client`-compatible, confirmed via DLR's own tutorial notebook |
| Collection | `ENMAP_HSI_L2A` | 824 items matched a broad UAE bbox; 15 over the Shawka Dam AOI |
| Bands | 224 | Counted directly from the 2022-09-08 GeoTIFF's own file attributes (rasterio `ds.count` and the raw TIFF `SamplesPerPixel`/`BitsPerSample` tags agree). **Not Wikipedia.** Not yet re-verified against the 2024-04-24 file (see below). Note: DLR's own Product Specification (EN-PCV-ICD-2009-2) states a nominal design of 91 VNIR + 131 SWIR = 222 bands — 224 vs. 222 is a real, unreconciled discrepancy, stated plainly rather than picking whichever number is more convenient. |
| Spectral range | 420-2450 nm (VNIR 420-1000, SWIR 900-2450, overlap 900-1000) | DLR's own EnMAP HSI Instrument Specification, `enmap.org/data/doc/EnMAP_Specs.pdf` — the mission's own primary document. **Not Wikipedia.** |
| Spectral sampling (FWHM), nominal | VNIR 6.5 nm / SWIR 10 nm | Same DLR instrument spec document. This is the *instrument-level* nominal figure, not the exact per-band table (see note below). |
| Spatial resolution | 30 m | Same DLR instrument spec document ("Ground Sampling Distance: 30 m × 30 m"), AND independently confirmed from the 2022-09-08 GeoTIFF's own geotransform (`ModelPixelScaleTag` = (30.0, 30.0)) — two independent confirmations, not one. |

**On the exact per-band wavelength/FWHM table:** EnMAP's own FAQ confirms each product's METADATA.XML carries a `specific/bandCharacterisation` structure with center wavelength and FWHM per band. Neither downloaded GeoTIFF carries this (checked directly at the raw TIFF-tag level on the 2022-09-08 file — no band descriptions, no per-band tags, no embedded wavelength array), and the copy of that scene's METADATA.XML pasted into this project's history was cut off before reaching that section; the actual XML file itself was never saved to `sourced data/`. This is now flagged as an explicit open item (see `config/project.yaml` → `enmap.spec.band_characterisation_table`) rather than silently left on the Wikipedia figure — it does not block the v1 water mask (`docs/WATER_MASK.md`), which was deliberately built on broad, band-index-ordered groups instead of exact wavelengths for this reason.

**Update (2026-09-19) — this gap's downstream reach is now fully mapped, not just noted once.** Beyond the water mask, this same gap directly blocks: (1) `pipeline/fingerprint.py`'s narrow-band evidence (specifically `CYANO_LIKE`/phycocyanin at ~620 nm — see `docs/ANOMALY_AND_FINGERPRINT.md` section 3.1 for the full reasoning on why that one class, and only that one among the classes considered, was excluded rather than approximated); and (2) a faithful per-band EnMAP-to-Satellite-813 spectral simulator (`pipeline/satellite813.py` — see `docs/SATELLITE_813_DECISION.md` for why building one anyway, on an assumed EnMAP wavelength grid, was decided against rather than attempted). Both are recoverable, not permanently blocked, once this table is obtained — the retrieval steps are unchanged from `config/project.yaml`'s original note.

**Update (2026-09-19, later same day) — RESOLVED, via a different route than the one described above.** The METADATA.XML download path above remains blocked exactly as described (never obtained). The table was instead obtained from the DLR STAC catalog's own `eo:bands` field on each EnMAP STAC item, which independently carries the same per-band `name`/`center_wavelength`/`full_width_half_max` values without needing that authenticated XML download at all. Retrieved via automated web access (a method that risks hallucinated numbers for a long, repetitive 224-row table, so not trusted at face value) and cross-validated: the same field was independently re-fetched multiple times across different STAC item URLs (both the 2022-09-08 and 2024-04-24 scene items) and different request chunking, and the resulting values agreed bit-for-bit across fetches; two physical-plausibility checks also passed (the VNIR/SWIR detector-overlap FWHM alternation; the previously-unreconciled empirical nodata-band-gap positions now landing exactly on a genuine gap in the real band-centre sequence). Full method and the resulting 224-band table: `data/metadata/enmap_band_characterisation.json`; full write-up: `docs/WATER_MASK.md` section 14.1. This unblocks both items named just above — see `docs/ANOMALY_AND_FINGERPRINT.md` section 3.2a (`CYANO_LIKE`, now computable) and `docs/SATELLITE_813_DECISION.md` section 3 (per-band simulator, now built) for what each does with it. The residual limitation stated in `enmap_band_characterisation.json`'s own `source.caveat` field stands: agreement across independent STAC fetches is strong evidence against hallucination, but is not the same as independently re-deriving the numbers from the raw METADATA.XML itself, which remains unobtained.
| Product | L2A — orthorectified, atmospherically corrected | STAC item `processing:level: L2A` |
| **Atmospheric correction mode** | **`correctionType: Land_Mode`**, `waterReflectanceProduct: NA` | Read directly from both acquired scenes' own METADATA.XML |
| Licence | proprietary | STAC collection record, `license` field |
| Download access | Requires a DLR/EOC UMS account | Registration form inspected directly (see section 3) |
| File format | Cloud-optimized GeoTIFF (`SPECTRAL_IMAGE_COG.TIF`), plus per-scene quality masks (cloud, cloud-shadow, haze, cirrus, snow, defective-pixel) as separate COG assets | STAC item `assets` |

**The `Land_Mode` / `waterReflectanceProduct: NA` flag, resolved — not left open.**
DLR's own FAQ states there are three L2A processing options: land, water, and
combined mode. Water mode (and the water-pixel branch of combined mode) runs a
separate, dedicated water atmospheric-correction/retrieval path, producing
"underwater reflectance" and "normalized water-leaving reflectance" via a
different processor module (MIP, provided by EOMAP). Both of this project's
scenes were ordered/processed in pure `Land_Mode`, so `waterReflectanceProduct:
NA` is not missing data — it correctly states that branch never ran.

DLR's Land_Mode atmospheric-correction technical note (`EN-PCV-TN-6007`) is
explicit about what that means for water pixels specifically: the water-vapor
retrieval algorithm (APDA, using channels near 0.94/1.13 µm) "is not valid over
dark surfaces (water)," so "the water vapor columns over water surfaces will be
set to the average value obtained over land" rather than retrieved locally.
Land_Mode also assumes a fixed rural/continental aerosol type and a Lambertian
(non-water-specific) surface reflectance model scene-wide.

**Plain conclusion: this is a real, bounded limitation, not a non-issue.** It
can bias the *absolute* reflectance value of wet-core pixels in these two
scenes, particularly near the water-vapor-sensitive channels, because the
correction used a land-average water-vapor estimate over them instead of a
water-appropriate retrieval, and no dedicated water radiative-transfer
inversion was applied. It does not, on its own, block a threshold-based
water-mask classification validated against an independent baseline (see
`docs/WATER_MASK.md`) — but it would matter directly if this project later
computes an absolute water-quality metric (turbidity, chlorophyll proxy, etc.)
from these two scenes' reflectance values over the wet core, and that step
should address it again at that point rather than assume this note already
covers it.

#### Acquired scenes — full detail

Both files were downloaded directly by the project owner through the DLR UMS login
flow (see section 3) and are in `sourced data/`.

**2022-09-08** (`ENMAP01-____L2A-DT0000003309_20220908T073013Z_006_V010502_20251029T084333Z`)

| Field (from the product's own METADATA.XML) | Value |
|---|---|
| Acquisition (UTC) | 2022-09-08T07:30:13 – 07:30:18 |
| Orbit | DESCENDING |
| Scene sun zenith angle | 22° |
| Cloud cover | 0% |
| Haze cover | 1% |
| Cirrus / snow / water cover (scene-wide flags) | 0% / 0% / 0% |
| overallQuality | 0 (nominal, per DLR FAQ) |
| Dead pixels VNIR / SWIR | 137 / 1531 |
| Defective pixels VNIR / SWIR | 2 / 12 |
| Product screening result | OK, no failed groups |
| Reported product size | 352,981,669 bytes |
| **Downloaded file size** | **415,173,616 bytes** (COG re-encoding accounts for the difference) |
| Citation (DLR's own) | `DLR (2025): EnMAP L0 Product 0000003309_06_L0_20220908T201017_010402_20251029 doi: 10.15489/rlyibn8gjc58 Processed to level 2A (version: 010502, parameters: U0BLNNTS284G)` |

**2024-04-24** (`ENMAP01-____L2A-DT0000070441_20240424T073016Z_006_V010502_20260318T012317Z`)

| Field | Value |
|---|---|
| Acquisition (UTC) | 2024-04-24T07:30:16 – 07:30:21 |
| Orbit | DESCENDING |
| Scene sun zenith angle | 16° |
| Cloud / haze / cirrus / snow / water cover | 0% / 0% / 0% / 0% / 0% |
| overallQuality | 0 (nominal) |
| Dead pixels VNIR / SWIR | 137 / 1509 |
| Defective pixels VNIR / SWIR | 2 / 12 |
| Product screening result | OK, no failed groups |
| Reported product size | 362,650,458 bytes |
| **Downloaded file size** | **421,431,498 bytes** |
| Citation (DLR's own) | `DLR (2026): EnMAP L0 Product 0000070441_06_L0_20240424T200611_010402_20260318 doi: 10.15489/rlyibn8gjc58 Processed to level 2A (version: 010502, parameters: U0BLNNTS322G)` |

Full per-file provenance records (source, licence caveat, local path, integrity
status) are in `data/metadata/`.

### 2.2 Sentinel-2 MSI, Landsat 8/9, Sentinel-3 OLCI — reused, not recollected

Historical baseline for this exact AOI already exists from BluePulse-813 (an
earlier, separate, paused project) and was reused by copy, per the project owner's
instruction — not recollected. See `AOI_SELECTION.md` section 3 for the water-check
findings this produced, and `config/project.yaml` for the confirmed-unusable
Sentinel-3 finding. The underlying access method (Microsoft Planetary Computer,
anonymous STAC access, Copernicus open licence) matches what DesalGuard-main
documents for its own coastal use of the same sensors, and is not re-verified here
since it was not re-queried.

### 2.3 In-situ water-quality records — not separately checked for this AOI

DesalGuard-main's own audit established that the Cockpit's "In-situ WQ records"
card is a static, non-interactive listing with no download mechanism for the
programme as a whole. That finding is a property of the shared organiser platform,
not of the Gulf of Annaba AOI specifically, so it is expected to hold here too —
but this has not been independently re-checked against the Shawka Dam AOI, and is
noted as an inherited assumption rather than a separately verified fact.

---

## 3. Registration and download — what was actually required (not assumed)

The download path was traced directly: STAC item asset `href` →
`download.geoservice.dlr.de` → redirects to `sso.eoc.dlr.de` (DLR's UMS login). No
existing session. The registration form
(`sso.eoc.dlr.de/geoservice/selfservice/register`) was opened and inspected before
any account was created.

**What it requires:** first name, last name, organisation, full postal address
(street, postal code, city, country), an email address (the form explicitly
recommends institutional/academic addresses — "access may be restricted to
non-private email addresses" — disposable addresses are rejected), a username, and
a password, plus acceptance of DLR's Terms and Privacy Notice.

Creating accounts and entering passwords on someone else's behalf is outside what
this assistant does under any circumstance, so this step was handed to the project
owner rather than worked around. **Result, confirmed by the owner completing it
directly:** self-service registration was sufficient — no scientific-proposal or
manual-approval step was encountered in practice for downloading these two L2A
scenes, resolving the ambiguity DLR's own FAQ left open (it mentions EnMAP access
sometimes differentiating by "whether this is related to a scientific proposal
process or not," which this audit could not resolve from documentation alone
before the owner's direct attempt).

**Status: DATA IN HAND for 2 of 5 confirmed scenes.** Not "access pending."

---

## 4. Reproducing this audit

```
Tanager exhaustive check:
  https://www.planet.com/data/stac/tanager-core-imagery/<collection>/collection.json
  for each of: GHG-plumes, energy-mining, natural-lands, agriculture,
  coastal-water-bodies, urban, snow-ice, fire, ROCX2025

EnMAP STAC search:
  https://geoservice.dlr.de/eoc/ogc/stac/v1/search
  ?collections=ENMAP_HSI_L2A&bbox=55.90,25.00,56.15,25.25&limit=100

EnMAP collection licence field:
  https://geoservice.dlr.de/eoc/ogc/stac/v1/collections/ENMAP_HSI_L2A

EnMAP registration:
  https://sso.eoc.dlr.de/geoservice/selfservice/register?locale=en
```
