# Data Access Audit

**Project:** BLUEBAN 813 · Team Kanban
**Challenge:** Water Quality & Inland/Coastal Water Intelligence
**Audit performed:** 2026-09-15
**Auditor:** verified against the live participant platform and live data endpoints, not assumed.

This document records what data we can *actually* obtain, how, and under what
licence. It exists because designing a pipeline around a dataset you cannot
access is the fastest way to lose a PoC.

---

## 1. Headline finding: Satellite 813 is not available for this phase

The single most important fact discovered in this audit, quoted verbatim from
the authenticated participant onboarding guide
(`spaceacademy-hackathons.space.gov.ae/onboarding`, section 04 "Phases and what
you can access"):

| Resource | Preparatory | **PoC (current phase)** | Incubation |
|---|---|---|---|
| Open multispectral data | Yes | **Yes** | Yes |
| Open hyperspectral data | Yes | **Yes** | Yes |
| Planet Tanager open-archive data | Yes | **Yes** | Yes |
| Commercial Planet data | No | **No** | May be provided to selected teams |
| gIQ | No | **No** | May be provided to selected teams |
| **Satellite 813** | No guaranteed access | **No guaranteed access** | Upon availability |
| MBZ-SAT | No guaranteed access | **No guaranteed access** | Upon availability |

And, in section 07 of the same guide:

> **Satellite 813 & MBZ-SAT — INCUBATION ONLY, UPON AVAILABILITY.** May be
> provided to selected teams during incubation if available. *Do not assume
> coverage of a specific AOI, date, or product level, and do not design a PoC
> that depends on this data.*

### What the Cockpit dataset cards actually are

The team Cockpit (`/team`) lists four challenge datasets:

| Card | Stated format | Interactive? |
|---|---|---|
| 813 Aquatic Hyperspectral | GeoTIFF · on-demand | **No** — static text, no link, no download control |
| Sentinel-3 OLCI | NetCDF · on-demand | **No** |
| Landsat-8/9 OLI-TIRS | GeoTIFF · on-demand | **No** |
| In-situ WQ records | CSV · variable | **No** |

Inspection of the rendered DOM for the 813 card returns three text nodes and no
interactive element:

```
listitem
 generic "813 Aquatic Hyperspectral"
 generic "GeoTIFF · on-demand"
 generic "Optimized bands for water-leaving radiance"
```

There is no download endpoint, no request form and no API. "On-demand" means a
request routed through the organiser chat, and the onboarding guide states the
answer for 813 in this phase is no guaranteed access.

**Conclusion.** BLUEBAN 813 does not use, and does not claim to use, Satellite
813 data. It uses a documented Satellite 813 **sensor simulator** built from
real Tanager hyperspectral measurements. See `813_PRODUCT_NOTES.md`.

### Published Satellite 813 specification

From the public data page (`/data`), the only official 813 specification we have:

| Property | Value |
|---|---|
| Bands | ~205 |
| Spectral range | ~400–1700 nm |
| Spectral sampling | ~5 nm |
| Spatial resolution | 20 m |
| Revisit | *listed as not available* |

The "revisit: not available" entry is itself informative: it is consistent with
a mission without a public operational archive at the time of writing.

---

## 2. What we CAN access, verified

### 2.1 Planet Tanager-1 — hyperspectral (PRIMARY)

| Property | Value | How verified |
|---|---|---|
| Access | Open STAC, **no authentication** | Downloaded successfully |
| Catalog | `planet.com/data/stac/tanager-core-imagery` | 236 items enumerated across 6 collections |
| Collection used | `coastal-water-bodies` (43 items) | Full inventory in `data/metadata/` |
| Product | `ortho_sr_hdf5` — orthorectified surface reflectance | |
| Bands | **426**, 376.44 – 2499.00 nm | Read from file attribute `wavelengths` |
| Spectral sampling | 5.00 nm median | Computed from the wavelength array |
| FWHM | 5.20 – 6.81 nm (median 6.05) | File attribute `fwhm` |
| Units | Unitless surface reflectance (0–1) | File attribute `Unit` |
| No-data | `-9999.0` | File attribute `_FillValue` |
| Spatial resolution | **exactly 30.0 m** | Derived from StructMetadata.0 corner coordinates |
| Projection | **EPSG:32632** (UTM 32N / WGS84) | Group attribute `epsg_code` |
| Licence | **CC-BY-4.0** | STAC property `license` |
| File size | 0.906 GB for the primary scene | HTTP Content-Length, verified on disk |

**Attribution required for any use:**
> Tanager STAC Data, available at www.planet.com/data/stac © 2025 Planet Labs
> PBC. All Rights Reserved.

#### Product contents beyond what the tutorial notebooks use

The official challenge notebooks use only `surface_reflectance` and the three
binary masks. The product contains considerably more, and we use it:

| Dataset | Shape | What it gives us |
|---|---|---|
| `surface_reflectance` | (426, 697, 871) | The cube |
| **`surface_reflectance_uncertainty`** | (426, 697, 871) | **Per-pixel, per-band 1σ.** Drives our significance tests and the confidence model. |
| `beta_cloud_mask` | (697, 871) | Cloud |
| `beta_cirrus_mask` | (697, 871) | Cirrus |
| `nodata_pixels` | (697, 871) | Valid footprint |
| `aerosol_optical_depth` | (697, 871) | Atmospheric state |
| `column_water_vapour` | (697, 871) | g/cm², atmospheric state |
| `sun_zenith`, `sensor_zenith`, `sensor_azimuth`, `sun_azimuth` | (697, 871) | Observation geometry (glint risk) |
| `sensor_to_ground_path_length` | (697, 871) | Metres |
| `time` | (697, 871) | Per-pixel UTC |

Attributes on `surface_reflectance`:

| Attribute | Value |
|---|---|
| `wavelengths` / `wavelengths_units` | 426 centres, nm |
| `fwhm` / `fwhm_units` | 426 widths, nm |
| **`good_wavelengths`** | **Planet's own per-band quality flag: 368 good, 58 bad** |

> **This matters.** The tutorial notebooks hardcode bad bands as
> 1350–1450 nm and 1800–1950 nm. The product's own flags for our scene are
> **1342.41–1437.55 nm (20 bands)** and **1782.58–1967.21 nm (38 bands)** — both
> windows differ from the hardcoded rule at both edges. We use the product flags.

### 2.2 Sentinel-3 OLCI — ocean colour (Stage A)

| Property | Value |
|---|---|
| Access | Microsoft Planetary Computer STAC, anonymous |
| Collection | `sentinel-3-olci-wfr-l2-netcdf` (Water Full Resolution, Level-2) |
| Assets confirmed | `chl-nn`, `chl-oc4me`, `iop-nn`, `iwv`, `oa01`–`oa21` reflectance, `geo-coordinates`, `browse-jpg`, `instrument-data`, `eop-metadata` |
| Resolution | 300 m |
| Availability over AOI | **993 scenes 2022–2025**, 116 in 2025 |
| Licence | Copernicus open (free, full, open) |

This is an *operational, ESA-calibrated* chlorophyll product — our independent
reference, not something we re-derive.

### 2.3 Sentinel-2 MSI — spatial detail and temporal baseline (Stage B)

| Property | Value |
|---|---|
| Access | Planetary Computer, anonymous |
| Collection | `sentinel-2-l2a` |
| Availability over AOI | **413 scenes in 2025 alone**, 143 with <10% cloud |
| Resolution | 10 / 20 / 60 m by band |
| Licence | Copernicus open |

**Processing-baseline trap handled:** from ESA baseline 04.00 (2022-01-25) L2A
values carry a −1000 DN radiometric offset. Planetary Computer serves raw
values. A multi-year baseline that ignores this silently mixes two radiometric
scales; `pipeline/sentinel2.py:harmonize` applies the correction by acquisition
date.

### 2.4 Landsat 8/9 OLI-TIRS — thermal context (Stage D)

| Property | Value |
|---|---|
| Access | Planetary Computer, anonymous |
| Collection | `landsat-c2-l2` (Collection 2 Level-2) |
| Availability over AOI | 86 scenes in 2025, 40 with <20% cloud |
| Thermal | `lwir11` surface temperature, 100 m resampled to 30 m |
| Licence | USGS public domain |

### 2.5 In-situ water-quality records — NOT AVAILABLE

The Cockpit card "In-situ WQ records · CSV · variable · Ground-truth for select
MENA water bodies" is a static card with no download mechanism, same as the
other three. No in-situ dataset for the Gulf of Annaba was obtainable through
the platform during this audit.

**Consequence, stated plainly:** BLUEBAN 813 has **no in-situ ground truth** for
its AOI. This has hard implications that we do not paper over:

* We report **no** chlorophyll-a concentration in mg/m³.
* We report **no** turbidity in NTU/FNU.
* Our indices are named as proxies everywhere they appear, in code and in UI.
* Validation is **cross-sensor** against ESA operational products and
  **internal** (spatial hold-out), never "validated against ground truth".

See `VALIDATION_REPORT.md` for exactly what we can and cannot claim, and
`LIMITATIONS.md` for the consequences.

---

## 3. Permission to use external open data — confirmed

Cockpit FAQ, verbatim:

* *"Can we use external public datasets?"* → **"Yes — any open dataset is allowed"**
* *"Are pretrained models allowed?"* → "Yes, provided you disclose them and respect their licences."
* *"What output formats are expected?"* → "Will be disclosed during submission phase."

Every external source used here is open, and each is listed with its licence in
`DATA_LINEAGE.md`.

---

## 4. Programme facts captured during the audit

| Item | Value | Source |
|---|---|---|
| Team | Kanban, **APPROVED** | Cockpit |
| Country | United Arab Emirates | Cockpit |
| Challenge | Water Quality & Inland/Coastal Water Intelligence | Cockpit |
| Members | 4 | Cockpit |
| Current phase | Hackathon Solution Development | Dashboard |
| **PoC deadline** | **31 d 7 h from 2026-09-15 ≈ 2026-10-16** | Cockpit countdown |
| Programme scale | 369 applicants · 124 teams · 23 countries | Dashboard |
| Official judging criteria | Impact · Creativity · Validity · Relevance · Presentation | Repository README |
| Hyperspectral use | "given bonus consideration during selection" | Repository README |

---

## 5. Reproducing this audit

```bash
python scripts/discover_data.py          # re-enumerates every source below
python scripts/fetch_tanager.py 20250601_104901_58_4001
```

`scripts/fetch_tanager.py` writes a SHA-256 and the full STAC item alongside
every download, into `data/metadata/`. The primary scene:

```
sha256 = 4242bf42f5da5673bd3a381714f20f87538423287cd3962bbfd5b564fc2a81ce
bytes  = 906164921
```
