# Official Resource Audit

Everything the programme publishes, inspected rather than assumed. Audited
2026-09-15, re-checked 2026-09-17.

---

## 1. Official repository

`https://github.com/Tnecniv-Teikram/813-hyperspectral-hackathon`
Cloned to `reference/813-hyperspectral-hackathon` and **never modified**.
21 MB, 7 notebooks, MIT licence for code.

| File | Read | What it gave us |
|---|---|---|
| `README.md` (883 lines) | Yes | The official judging criteria; the Tanager data guide; the spectral-index reference; the bad-band convention |
| `00_EO_data_quickstart_notebook.ipynb` | Yes | STAC access patterns, HDF5 structure, the `eo:center_wavelength` pitfall |
| `06_ecosystem_health_water_qualityy.ipynb` | Yes | The water-quality baseline workflow; the three Tanager coastal scene ids; the turbidity-proxy definition we cite |
| `05_ecosystem_health_blue_carbon.ipynb` | Yes | Coastal index set, water-vs-vegetation spectral comparison |
| `requirements.txt` | Yes | The dependency set the programme expects |

### The official judging criteria (repository README)

| # | Criterion | What judges look for |
|---|---|---|
| 1 | Impact | Scale of problem, breadth of benefit, policy relevance |
| 2 | Creativity | Originality, or a meaningful advance on existing approaches |
| 3 | Validity | Scientific and technical rigor, real-world applicability |
| 4 | Relevance | Fit to theme, completeness, feasibility, usability |
| 5 | Presentation | Clarity of storytelling, quality of visual delivery |

> **Bonus:** *"Teams using hyperspectral data (Tanager / EnMAP) receive
> additional consideration during selection."*

Mapped to features in `JUDGING_MATRIX.md`.

### What the notebooks establish about the data

* The accessible hyperspectral sensor is **Planet Tanager-1**: 426 bands,
  380-2500 nm, 30 m, **CC-BY-4.0**, open STAC, no authentication.
* HDF5 root is `HDFEOS/GRIDS/HYP/Data Fields`.
* Wavelengths live in STAC under `bands[].eo:center_wavelength` in micrometres.
  The README flags the `eo:` prefix as a common error.
* The notebooks hardcode bad bands as 1350-1450 and 1800-1950 nm. **The product
  ships its own `good_wavelengths` flags**, which for our scene give
  1342.41-1437.55 and 1782.58-1967.21 nm. We use the product's.
* The UAE example scene `20250511_074311_00_4001` reports **38.6 % valid
  pixels** in the notebook's own printed output. This is the figure that
  disqualified the UAE AOI.

### What the notebooks do NOT do, and we do

| Notebook | BLUEBAN 813 |
|---|---|
| `surface_reflectance` and three binary masks only | Also `surface_reflectance_uncertainty`, `aerosol_optical_depth`, `column_water_vapour`, observation geometry, `StructMetadata.0` |
| Hardcoded bad-band windows | The product's own per-band flags |
| Indices with a bare `+ eps` guard | Uncertainty-propagated significance test at k = 3σ |
| Single scene, single date | 1 265-acquisition multi-year baseline |
| No validation | Three experiments with spatially blocked cross-validation and bootstrap intervals |

The notebooks' own closing guidance asks for exactly this:

> *"How good is your model, really? Include concrete validation statistics -
> accuracy, precision/recall, RMSE, IoU, or a comparison against ground
> truth/known events - not just 'it looks right on the map.'"*

---

## 2. Authenticated participant platform

`https://spaceacademy-hackathons.space.gov.ae/` - inspected through the team
leader's own signed-in browser session. No authentication was bypassed and no
credential was extracted or printed.

| Page | Status |
|---|---|
| `/dashboard` | Inspected |
| `/team` (the Cockpit) | Inspected |
| `/onboarding` | Inspected - **the decisive document** |
| `/tasks` | Inspected (empty board) |
| `/prep-training` | Inspected - no material published |
| `/data` | Inspected (public page) |

### Programme facts captured

| Item | Value |
|---|---|
| Team | **Kanban**, status **APPROVED** |
| Country | United Arab Emirates |
| Challenge | Water Quality & Inland/Coastal Water Intelligence |
| Members | 4 |
| Current phase | Hackathon Solution Development |
| **PoC deadline** | 31 d 7 h from 2026-09-15 ≈ **2026-10-16** |
| Programme scale | 369 applicants · 124 teams · 23 countries |
| Learning track | 4/4 complete |

### Cockpit FAQ, verbatim

| Question | Answer |
|---|---|
| Can we use external public datasets? | **"Yes - any open dataset is allowed"** |
| Are pretrained models allowed? | "Yes, provided you disclose them and respect their licences." |
| What output formats are expected? | "Will be disclosed during submission phase." |

Every external source we use is open and listed with its licence in
`DATA_LINEAGE.md`.

---

## 3. The four Cockpit datasets: what they actually are

The Cockpit lists four challenge datasets. DOM inspection shows each is a
**static informational card** with no link, no form, no download control and no
endpoint. For the 813 card the accessibility tree returns three text nodes:

```
listitem
 generic "813 Aquatic Hyperspectral"
 generic "GeoTIFF · on-demand"
 generic "Optimized bands for water-leaving radiance"
```

| Card | Stated | Obtainable |
|---|---|---|
| 813 Aquatic Hyperspectral | GeoTIFF · on-demand | **No** |
| Sentinel-3 OLCI | NetCDF · on-demand | Yes, independently via Planetary Computer |
| Landsat-8/9 OLI-TIRS | GeoTIFF · on-demand | Yes, independently via Planetary Computer |
| In-situ WQ records | CSV · variable | **No** |

"On-demand" means a request through the organiser chat. For 813 the onboarding
guide already answers that request.

---

## 4. The decisive finding: phase access rules

From `/onboarding` section 04, for the phase we are in:

| Resource | Preparatory | **PoC (current)** | Incubation |
|---|---|---|---|
| Open multispectral | Yes | **Yes** | Yes |
| Open hyperspectral | Yes | **Yes** | Yes |
| Planet Tanager open archive | Yes | **Yes** | Yes |
| Commercial Planet | No | **No** | May be provided |
| gIQ platform | No | **No** | May be provided |
| **Satellite 813** | No guaranteed access | **No guaranteed access** | Upon availability |
| MBZ-SAT | No guaranteed access | **No guaranteed access** | Upon availability |

And section 07, verbatim:

> **Satellite 813 & MBZ-SAT - INCUBATION ONLY, UPON AVAILABILITY.** May be
> provided to selected teams during incubation if available. *Do not assume
> coverage of a specific AOI, date, or product level, and do not design a PoC
> that depends on this data.*

**This is the instruction BLUEBAN 813 is built to comply with.** We hold no 813
data, and the response is a documented sensor simulator that answers the
mission-utility question instead. See `813_PRODUCT_NOTES.md`.

### Published Satellite 813 specification

From the public `/data` page, the only official specification available:

| Property | Published |
|---|---|
| Bands | ~205 |
| Range | ~400-1700 nm |
| Sampling | ~5 nm |
| Resolution | **20 m** |
| Revisit | *listed as not available* |

The three spectral figures are mutually inconsistent: 400-1700 nm at 5 nm
requires 261 bands. We preserve the range and the band count, and run the 5 nm
interpretation as a sensitivity case. Both give the same conclusion.

---

## 5. Official guidance we followed, and where

The onboarding guide's section 08, *"Mistakes that sink a PoC"*, reads as a
checklist. Ours:

| Official warning | What we did |
|---|---|
| Waiting for premium data before starting | Built entirely on open data; 813 is simulated |
| Downloading the largest AOI available | One 26 × 21 km AOI |
| Using one image to answer a change question | 1 265-acquisition baseline behind a single hyperspectral date |
| Ignoring clouds, shadows and quality flags | Product masks, glint test, per-pixel uncertainty screen, all reported |
| Reporting an index as ground truth | Every index named a proxy in code, API and UI; no concentration reported |
| **Randomly splitting nearby pixels for train/test** | **Spatial blocking throughout; the random-split inflation is published** |
| Treating hyperspectral bands like RGB channels | Product bad-band flags, measured SNR selection, standardised features, compared against a simpler baseline |
| Publishing restricted imagery to a public repo | Only code, metadata, checksums and derived outputs committed |
| Starting with deep learning | PLSR and logistic regression; nothing deeper was justified |
| Reporting accuracy with no description of validation | Reference data, split method and independence stated for every figure |

Section 09's 16-item checklist is complete, including *"I explained whether
hyperspectral data adds real value"* - measured in
`experiments/detectability_ablation.py` - and *"I checked that no credentials or
restricted data are in GitHub."*

---

## 6. Public data page: the recommended stack

The `/data` page (Arabic locale) sets out a three-phase access model and a
sensor comparison. Its practical guidance, which we followed:

1. Start simple - Sentinel-2 or Landsat first.
2. Start with a small AOI.
3. Download only what you need; use cloud access.
4. Use hyperspectral **strategically**, where the problem depends on fine
   spectral or material information.

> *"A good solution does not need every dataset. It needs the right sensor for
> the right problem, with a clear explanation of why."*

That sentence is the design brief for the sensor cascade in
`METHODOLOGY.md`.

---

## 7. Provider endpoints verified live

| Provider | Endpoint | Result |
|---|---|---|
| Planet open STAC | `planet.com/data/stac/tanager-core-imagery` | **236 items** enumerated across 6 collections; 43 in `coastal-water-bodies` |
| Microsoft Planetary Computer | `planetarycomputer.microsoft.com/api/stac/v1` | **136 collections**; `sentinel-2-l2a`, `sentinel-3-olci-wfr-l2-netcdf`, `landsat-c2-l2`, `esa-worldcover`, `era5-pds` all present |
| ERA5 via Planetary Computer | `era5-pds` | Archive ends ~2020-12; **zero items for 2025**. Open-Meteo used instead |
| Open-Meteo archive | `archive-api.open-meteo.com/v1/archive` | Hourly ERA5 10 m wind for the event date, no authentication |
| OpenStreetMap Overpass | `overpass-api.de/api/interpreter` | 25 typed coastal features inside the AOI |
| EnMAP | `geoservice.dlr.de` | Listed as open self-serve; not used, because Tanager already provides a validated 426-band cube with a 38-minute Sentinel-2 coincidence over the chosen AOI |

---

## 8. What we chose not to use, and why

| Resource | Why not |
|---|---|
| EnMAP | No coincidence advantage over Tanager for this AOI; adding a second hyperspectral source would not change any conclusion |
| Space42 gIQ | Explicitly unavailable in this phase |
| Commercial Planet / PlanetScope | Explicitly unavailable in this phase |
| MBZ-SAT | Incubation only |
| ESA WorldCover | Our water mask is derived from the scene itself, which is more current than a static land-cover product |
| HyperCoast | An excellent visualisation library, but the product needs an operator interface rather than a notebook viewer |

---

## 9. Blocked items requiring a human action

| Item | Action needed |
|---|---|
| Real Satellite 813 data | Incubation selection. Not requestable now. |
| In-situ WQ records | An organiser would have to supply a file; there is no self-serve mechanism. |
| Custom domain on the hosted demo | Cloudflare Pages custom domains cannot be attached from the CLI; one dashboard action is required. |

Nothing else in the build is blocked.
