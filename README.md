# BLUEBAN 813

**Water Threat Intelligence for the Arab region**
Detect. Fingerprint. Forecast. Protect.

Team **Kanban** · Arab Youth Space Hackathon 2026, **813 Challenge**
Challenge: *Water Quality & Inland/Coastal Water Intelligence*
Live: **https://blueban813.pages.dev**

---

## What this is

BLUEBAN 813 turns Earth observation into one operational decision: **should a
field team sample this water, and where.**

It is not a satellite image viewer. Given a coastal AOI it detects spectrally
anomalous water at a calibrated false-alarm rate, characterises the anomaly's
optical signature with its evidence, checks it against a multi-year local
baseline, projects its drift, scores the exposure of operator-configured assets,
plans a field-sampling mission, and records complete provenance for every number
it shows.

It is also built to **withhold an alarm**. On the demonstration scene it found a
1.13 km² anomaly with a coherent sediment signature, then reduced the priority
because 5.4 years of local history say the water was cleaner than usual that
day. A product that cannot say *nothing is happening here* is not an operational
product.

---

## Honesty statement, up front

**This repository contains zero Satellite 813 pixels.**

813 is incubation-only for this programme phase, and the official participant
guide instructs teams not to design a PoC that depends on it. Every
hyperspectral measurement here is real Planet Tanager-1 data (426 bands,
CC-BY-4.0). Everything labelled 813 is a clearly marked **simulation**, produced
by convolving that cube onto 813's published band configuration.

**No in-situ data was available for this AOI.** Consequently no chlorophyll-a in
mg/m³, no turbidity in NTU and no TSS in mg/L is reported anywhere. Every index
is named as a proxy, and confidence is capped at 0.75 while no field sample
exists.

See `docs/DATA_ACCESS_AUDIT.md`, `docs/813_PRODUCT_NOTES.md` and
`docs/LIMITATIONS.md`.

---

## The headline result

Both arms convolved from the **same Tanager pixels**, so acquisition time,
atmosphere, illumination and water state are identical between them. Spatially
blocked cross-validation throughout.

| | Multispectral (Sentinel-2, 11 bands) | + 813 (simulated, 205 bands) |
|---|---|---|
| **F1 at the operational detection boundary** | 0.9853 | **0.9918** |
| False positives (of 25 513 samples) | 159 | **84** |
| False-alarm share | 2.806 % | **1.503 %** |

**ΔF1 = +0.0065, 95 % CI [0.0050, 0.0080]** (paired bootstrap) -
a **46.4 % relative reduction in false alarms at matched recall.**

And the results that did *not* favour hyperspectral, reported because they were
measured:

* **Gross plume detection:** both arms reach F1 ≈ 1.000. An obvious plume does
  not need hyperspectral data.
* **Sentinel-3 OLCI CHL/TSM retrieval:** no detectable advantage (ΔR² = −0.068
  and +0.007, neither significant).
* **Methodological finding:** a random train/test split inflates the
  hyperspectral R² from 0.01 to **0.63** through spatial autocorrelation
  leakage - three times the inflation the multispectral arm gets.

---

## AOI: Gulf of Annaba, Algeria

Chosen on data quality, not geography. We wanted a UAE scene; the only Tanager
coastal-water scene over the UAE is **51 % cloud with 38.6 % valid pixels**, a
figure printed in the official challenge notebook's own output.

| | |
|---|---|
| Extent | 26.13 × 20.91 km · EPSG:32632 |
| Primary scene | Tanager-1 `20250601_104901_58_4001`, 2025-06-01 10:49 Z, **0 % cloud** |
| Sentinel-2 coincidence | **38 minutes**, both effectively cloud-free |
| Analysable water | 209 077 pixels · 188.17 km² |
| Baseline record | 1 265 Sentinel-2 acquisitions over 5.4 years |

That 38-minute coincidence is what turns the multispectral-versus-hyperspectral
comparison from an argument into a controlled measurement. Full reasoning in
`docs/AOI_SELECTION.md`.

---

## Quick start

```bash
# 1. Python dependencies
pip install -r requirements.txt

# 2. Hyperspectral scene (0.9 GB, CC-BY-4.0, no authentication required)
python scripts/fetch_tanager.py 20250601_104901_58_4001

# 3. Multi-year Sentinel-2 baseline (~13 min, parallel COG reads)
python scripts/build_baseline.py --years 6 --max-cloud 15

# 4. Tanager <-> Sentinel-3 OLCI matchups for the ablation
python scripts/build_matchup.py

# 5. Experiments
python experiments/validate_simulator.py
python experiments/hyperspectral_ablation.py
BLUEBAN_REGIME=hard python experiments/detectability_ablation.py
BLUEBAN_REGIME=easy python experiments/detectability_ablation.py

# 6. The event object and every map layer (~32 s)
python scripts/build_demo_event.py

# 7. Serve
uvicorn services.api.main:app --port 8813        # terminal 1
cd apps/web && npm install && npm run dev        # terminal 2
```

Then open `http://localhost:3000`. Start with **Judge Mode** (top right).

All randomised procedures are seeded (`np.random.default_rng(813)`), so the
numbers above reproduce exactly.

### Static build and deploy

The API is read-only, so the whole product ships as files with no server:

```bash
CLOUDFLARE_ACCOUNT_ID=<id> bash scripts/deploy_cloudflare.sh
```

---

## The sensor cascade

Each sensor has one job. None was added because it existed.

| Stage | Sensor | Job |
|---|---|---|
| A | Sentinel-3 OLCI WFR L2 | Operational reference (ESA `CHL_NN`, `TSM_NN`) |
| B | Sentinel-2 MSI L2A | Multi-year local baseline; spatial detail |
| C | **Tanager-1** (426 bands) | Spectral forensics; source for the 813 simulator |
| D | Landsat 8/9 | Thermal context (access audited) |
| E | In-situ | **empty, and the product says so** |
| — | ERA5 10 m wind | Drift forcing |

---

## What is technically unusual here

| | |
|---|---|
| **Product-native band quality** | Uses Tanager's own `good_wavelengths` flags (1342.41-1437.55 and 1782.58-1967.21 nm) rather than the tutorials' hardcoded windows, which differ at all four edges |
| **Uncertainty-propagated indices** | A naive NDCI spans **−1907 to +2407** on these water pixels because 0.53 % have a non-positive denominator. A k = 3σ significance guard built from the sensor's own per-pixel uncertainty bounds every index to its physical range at a cost of 0.8 % of pixels |
| **Measured band selection** | 100 of 368 bands clear SNR ≥ 3 over water inside 401-896 nm. Measured, not assumed |
| **Empirically calibrated detection** | The textbook χ²(12) threshold flags 14.57 % of water pixels because coastal water is not multivariate normal. Both thresholds are reported; the empirical 1 % background FAR (2.64 %) is used |
| **Local band depths** | Two-shoulder continua measured as an *excess over background water*. Clear Mediterranean water already has a 0.059 chlorophyll feature at 675 nm, so absolute thresholds fire on normal water |
| **Severity ≠ confidence** | Never multiplied. Priority comes from an auditable rule table with two deliberate asymmetries: low confidence *raises* priority, and a temporal veto *caps* it |
| **Coastline beaching** | Drift particles driven ashore strand rather than continuing inland over a town |
| **Offshore wind sampling** | ERA5's ~25 km grid resolves the plume centroid to a land cell 10 km inland reporting wind from 36°; the marine cell reports 87° |

---

## Repository layout

```
pipeline/            satellite813 · sentinel2 · sentinel3 · quality · water_mask
                     indices · spectral · anomaly · fingerprint · temporal
                     forecast · exposure · risk · sampling · provenance · export
experiments/         validate_simulator · hyperspectral_ablation
                     detectability_ablation
scripts/             fetch_tanager · build_baseline · build_matchup
                     build_demo_event · build_static_site · deploy_cloudflare.sh
services/api/        FastAPI read-only service
apps/web/            Next.js mission-control interface
config/              project.yaml · assets.geojson (real, OSM-verified)
outputs/             events · layers · validation  (derived, committed)
data/                raw (gitignored) · metadata (checksums, committed)
docs/                the documents listed below
tests/               band selection · units · masking · indices · risk bounds
```

---

## Documentation

| Read this | For |
|---|---|
| `docs/LIMITATIONS.md` | **Start here.** The boundary of the evidence |
| `docs/VALIDATION_REPORT.md` | Every experiment, negatives first |
| `docs/DATA_ACCESS_AUDIT.md` | What data exists, verified against the live platform |
| `docs/AOI_SELECTION.md` | Why Annaba beat Abu Dhabi and the Red Sea |
| `docs/813_PRODUCT_NOTES.md` | The simulator, and why simulation is the stronger answer |
| `docs/METHODOLOGY.md` | Every algorithmic decision with its citation |
| `docs/DATA_LINEAGE.md` | Every dataset, licence and checksum |
| `docs/BUSINESS_CASE.md` | Who pays, for what, and what it replaces |
| `docs/JUDGING_MATRIX.md` | Criterion → feature → evidence → metric → demo moment |

---

## Interface

Nine screens plus a guided walkthrough:

**Overview** the operational sequence, the instrument cluster and the animated
ocean view · **Watch** the multi-year monitoring record with seasonal
percentiles · **Spectra** a hyperspectral oscilloscope showing exactly which
diagnostic wavelengths fall in Sentinel-2's band gaps · **Forecast** full-screen
drift operations with a scrubbable timeline · **Assets** exposure ranking and
operator asset entry · **Samples** the field mission plan with CSV and GeoJSON
export · **Validation** every experiment, negatives above the headline ·
**Data** the provenance drawer with source checksums · **API** the integration
surface with live request execution · **Judge Mode** nine steps, each with the
line to say and the evidence on screen.

Every displayed number is read from pipeline output. There are no fallback
constants: colour-scale limits, AOI extent, water area, band counts and the
event id are all served by the API.

---

## Attribution

> Tanager STAC Data, available at www.planet.com/data/stac © 2025 Planet Labs
> PBC. All Rights Reserved. (CC-BY-4.0)

Contains modified Copernicus Sentinel-2 and Sentinel-3 data, processed by ESA,
accessed via Microsoft Planetary Computer. Landsat 8/9 courtesy of the U.S.
Geological Survey. ERA5 generated by ECMWF for the Copernicus Climate Change
Service, accessed through the Open-Meteo historical archive API. Asset register
© OpenStreetMap contributors (ODbL).

No raw Earth observation imagery, restricted imagery or credential is committed
to this repository.

---

## Team Kanban

| | |
|---|---|
| **Awaiz Ahmed** | Team lead · full-stack development |
| **Mohammad Umar** | AI and research |
| **Huda Mueen** | — |
| **Bilal Feroz** | — |

Code MIT. Data under the licences listed above.
