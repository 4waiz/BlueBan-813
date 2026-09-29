# Data Lineage

Every dataset in BLUEBAN 813, where it came from, under what licence, and what
it was used for. Nothing in the product depends on a source not listed here.

---

## Summary

| Source | Access | Licence | Authentication |
|---|---|---|---|
| Planet Tanager-1 | Planet open STAC | **CC-BY-4.0** | None |
| Sentinel-2 MSI L2A | Microsoft Planetary Computer | Copernicus open | None (anonymous) |
| Sentinel-3 OLCI WFR L2 | Microsoft Planetary Computer | Copernicus open | None (anonymous) |
| Landsat 8/9 C2 L2 | Microsoft Planetary Computer | USGS public domain | None (anonymous) |
| ERA5 10 m wind | Open-Meteo historical archive API | Copernicus / open | None |
| OpenStreetMap | Overpass + Nominatim | **ODbL** | None |
| Satellite 813 | **not obtained** | — | incubation only |
| In-situ water quality | **not obtained** | — | no mechanism |

Permission confirmed: the Cockpit FAQ states *"Can we use external public
datasets? Yes - any open dataset is allowed."*

---

## 1. Planet Tanager-1 — primary hyperspectral

| Field | Value |
|---|---|
| Scene | `20250601_104901_58_4001` |
| Collection | `tanager-core-imagery/coastal-water-bodies` |
| Asset | `ortho_sr_hdf5` |
| Acquisition | 2025-06-01 10:49:01.582 Z |
| Processing level | Level-2 surface reflectance |
| Bands | 426, 376.44 – 2499.00 nm, 5.00 nm median sampling |
| FWHM | 5.20 – 6.81 nm (median 6.05) |
| Units | unitless surface reflectance |
| No-data | −9999.0 |
| Resolution | exactly 30.0 m |
| Projection | EPSG:32632 (UTM 32N / WGS 84) |
| Cloud | 0 % (scene metadata); 0.080 % by product mask |
| Off-nadir | 19.9° · sun elevation 73.0° |
| Bytes | 906 164 921 |
| **SHA-256** | `4242bf42f5da5673bd3a381714f20f87538423287cd3962bbfd5b564fc2a81ce` |

**Source URL**
`https://storage.googleapis.com/open-cogs/planet-stac/tanager1-release2-core-imagery/ortho_sr_hdf5/20250601_104901_58_4001_ortho_sr_hdf5.h5`

**STAC item**
`https://www.planet.com/data/stac/tanager-core-imagery/coastal-water-bodies/20250601_104901_58_4001/20250601_104901_58_4001.json`

**Required attribution**
> Tanager STAC Data, available at www.planet.com/data/stac © 2025 Planet Labs
> PBC. All Rights Reserved.

**Used for:** water masking, all indices, per-band SNR, spectral populations, RX
anomaly detection, optical fingerprinting, and as the source cube for the 813
simulator and both arms of the ablation.

**Datasets read inside the product:** `surface_reflectance`,
`surface_reflectance_uncertainty`, `nodata_pixels`, `beta_cloud_mask`,
`beta_cirrus_mask`, `aerosol_optical_depth`, `column_water_vapour`,
`sun_zenith`, `sensor_zenith`, `StructMetadata.0`.

**Retrieval:** `scripts/fetch_tanager.py`, which writes the STAC item and a
download provenance record with the checksum into `data/metadata/`.

---

## 2. Satellite 813 — SIMULATED, not obtained

| Field | Value |
|---|---|
| Status | **No 813 pixels exist in this repository** |
| Reason | Incubation-only for this programme phase |
| Official instruction | *"Do not assume coverage of a specific AOI, date, or product level, and do not design a PoC that depends on this data."* |
| Specification source | `spaceacademy-hackathons.space.gov.ae/data` |
| Published spec | ~205 bands · ~400–1700 nm · ~5 nm sampling · 20 m |
| Our simulation | 205 bands linearly spaced 400–1700 nm, 5 nm FWHM, at Tanager's native 30 m |
| Derived from | the Tanager scene above |
| Method | Gaussian spectral-response convolution |
| Labelled in API | `/api/status` → `real_813_data_used: false` |

Full treatment in `813_PRODUCT_NOTES.md`.

---

## 3. Sentinel-2 MSI Level-2A

### 3a. Coincident pair (simulator validation)

| Field | Value |
|---|---|
| Items | `S2C_MSIL2A_20250601T101041_R022_T32SLF_20250601T142413`, `…_T32SLG_…` |
| Acquisition | 2025-06-01 10:10:41.025 Z |
| **Offset from Tanager** | **−38.3 minutes** |
| Cloud | 0.000269 % (T32SLF), 0.000921 % (T32SLG) |
| Bands used | B01–B08, B8A, B11, SCL |

### 3b. Multi-year baseline

| Field | Value |
|---|---|
| Collection | `sentinel-2-l2a` |
| Search | AOI bbox, 2020-01-01 → 2025-12-31, cloud ≤ 15 % |
| Acquisitions used | **1 265** (428 hotspot zone, 837 reference zone) |
| Span | 2020-07-17 → 2025-12-28 (5.4 years) |
| Bands | B03, B04, B05, B8A, B11, SCL at a common 20 m grid |
| Correction applied | ESA processing-baseline 04.00 offset (−1000 DN) by acquisition date |

**Licence:** Copernicus open (free, full and open access).
**Attribution:** *Contains modified Copernicus Sentinel-2 data, processed by
ESA, accessed via Microsoft Planetary Computer.*

**Used for:** validating the spectral simulator against a real sensor; the
multi-year local baseline that produced the temporal veto.

---

## 4. Sentinel-3 OLCI Water Full Resolution Level-2

| Field | Value |
|---|---|
| Collection | `sentinel-3-olci-wfr-l2-netcdf` |
| Matchup scene | `S3A_OL_2_WFR_20250531T091627_20250531T091927_0180_126_264_2340` |
| Acquisition | 2025-05-31 09:17:57 Z |
| **Offset from Tanager** | **−25.52 h** |
| Cloud | 6 % |
| Variables | `CHL_NN`, `CHL_NN_unc`, `TSM_NN`, `TSM_NN_unc` (all log₁₀) |
| Quality flags | WQSF |
| Resolution | 300 m |
| Matchups built | 658 within ±30 h (981 total across the window) |
| Archive depth over AOI | 993 scenes 2022–2025 |

**Licence:** Copernicus open.
**Attribution:** *Contains modified Copernicus Sentinel-3 data, processed by
ESA, accessed via Microsoft Planetary Computer.*

**Used for:** the operational reference target in the retrieval ablation. We do
not re-derive chlorophyll; ESA's operationally validated retrieval is used and
cited.

**Note:** no OLCI acquisition exists on 2025-06-01 itself over this AOI. The
±25.5 h offset is a reported limitation, not a hidden one.

---

## 5. Landsat 8/9 Collection 2 Level-2

| Field | Value |
|---|---|
| Collection | `landsat-c2-l2` |
| Nearest items | `LC09_L2SP_193034_20250531_02_T1`, `LC09_L2SP_193035_20250531_02_T1` |
| Acquisition | 2025-05-31 10:06:22 Z (−24.7 h) |
| Cloud | 1.09 % / 0.04 % |
| Archive over AOI | 86 scenes in 2025, 40 under 20 % cloud |

**Licence:** USGS public domain.
**Attribution:** *Landsat 8/9 courtesy of the U.S. Geological Survey.*

**Status:** availability audited and the access path implemented in
`pipeline/landsat.py`; thermal context is **not** used in any reported number
for this event. Listed here because the audit is part of the lineage, and
claiming otherwise would overstate the product.

---

## 6. ERA5 reanalysis — 10 m wind

| Field | Value |
|---|---|
| Producer | ECMWF for the Copernicus Climate Change Service |
| Access | Open-Meteo historical archive API (open, no authentication) |
| Variables | `wind_speed_10m`, `wind_direction_10m`, hourly, UTC |
| Sample point | offshore water centroid of the AOI |
| ERA5 cell returned | 36.942 N, 7.708 E |
| Value at t₀ | 2.25 m/s from 87° |
| Window | 2025-05-31 → 2025-06-04 (120 hours) |

**Attribution:** *Generated using Copernicus Climate Change Service information
(ERA5). Accessed through the Open-Meteo historical archive API.*

**Used for:** the wind-driven drift forecast.

**Why not Planetary Computer's `era5-pds`:** its archive ends around 2020-12 and
returns zero items for 2025.

**Why sampled offshore:** ERA5 is a ~25 km grid. The plume centroid, 90 m from
shore, resolves to a land cell ~10 km inland reporting wind from 36° where the
marine cell reports 87°.

---

## 7. OpenStreetMap — operator asset register

| Field | Value |
|---|---|
| Access | Overpass API and Nominatim, queried 2026-09-17 |
| Query extent | 36.8739, 7.5175, 37.0599, 7.8093 (the Tanager footprint) |
| Features adopted | 5, each with its OSM element id |
| File | `config/assets.geojson` |

| Asset | Type | OSM element | Coordinates |
|---|---|---|---|
| Annaba fishing harbour | PORT | `way/377885029` | 36.905051, 7.774241 |
| Annaba Port power station (72 MW) | INDUSTRIAL_INTAKE | `way/226955369` | 36.892052, 7.763084 |
| Plage Chapuis | PUBLIC_BEACH | `way/108063412` | 36.927583, 7.761094 |
| Plage Ain Achir | PUBLIC_BEACH | `way/296899348` | 36.957139, 7.780217 |
| Cap de Garde lighthouse | CUSTOM | `node/1408222792` | 36.967081, 7.783556 |

**Licence:** Open Database License (ODbL).
**Attribution:** *© OpenStreetMap contributors.*

**Policy.** BLUEBAN 813 ships no infrastructure database. Every coordinate above
is a real, publicly mapped feature with a verifiable element id; none was
estimated. A facility asset sits at the mapped facility centroid, not at its
water-intake structure. No marine protected area is claimed, because none could
be verified inside the AOI.

---

## 8. In-situ water quality — NOT OBTAINED

| Field | Value |
|---|---|
| Cockpit listing | "In-situ WQ records · CSV · variable · Ground-truth for select MENA water bodies" |
| Mechanism | **none** — a static card with no link, form or endpoint |
| Obtained | **no** |

Consequences are enumerated in `LIMITATIONS.md` §1 and `VALIDATION_REPORT.md`
§0. In short: no concentration is reported anywhere in this product, and
confidence is capped at 0.75.

---

## Derived outputs and how to regenerate them

| Output | Produced by | Inputs |
|---|---|---|
| `outputs/events/BB-2026-001*.json` | `scripts/build_demo_event.py` | Tanager, S2 baseline, ERA5, asset register |
| `outputs/layers/*.png` `.geojson` | same | Tanager |
| `outputs/validation/s2_timeseries.json`, `s2_baseline_report.json` | `scripts/build_baseline.py` | Sentinel-2 |
| `data/cache/matchup/*` | `scripts/build_matchup.py` | Tanager + Sentinel-3 |
| `outputs/validation/simulator_validation.json` | `experiments/validate_simulator.py` | Tanager + Sentinel-2 |
| `outputs/validation/hyperspectral_lift.json` | `experiments/hyperspectral_ablation.py` | matchups |
| `outputs/validation/detectability_lift_*.json` | `experiments/detectability_ablation.py` | Tanager |
| `apps/web/public/pipeline/**` | `scripts/build_static_site.py` | everything above |

## What is not committed to this repository

* Raw Earth observation imagery. The 0.9 GB Tanager HDF5 stays in
  `data/raw/` and is gitignored; it is reproducible from the URL and checksum
  above.
* Any credential. `.env.example` lists variable names only, and no source used
  here requires authentication.
* Any restricted or commercial imagery.

All randomised procedures are seeded (`np.random.default_rng(813)`).
