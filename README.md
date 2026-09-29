# BlueBan 813

**Detect. Fingerprint. Forecast. Trace. Protect.**

BlueBan 813 turns satellite observations into operational water intelligence. Sentinel sensors watch large coastal areas continuously. When an anomaly appears, Arab Satellite 813 hyperspectral data fingerprints the event, AI estimates its severity and confidence, ocean conditions forecast where it will move, and BluePulse identifies which critical assets may be affected and where field teams should collect samples for confirmation. Instead of giving water operators another satellite image, BluePulse tells them where to look, what may be happening, where it is going, and what to do next.

> Built for the **Arab Youth Space Hackathon 2026 – 813 Challenge** (Water Quality & Inland/Coastal Water Intelligence) by team **Kanban**. Demo area: the Gulf of Annaba, Algeria.

---

## The questions BlueBan answers

| # | Operator question | Module | Status |
|---|---|---|---|
| 1 | **Is something wrong?** | Spectral anomaly detection (RX / Mahalanobis) | Built |
| 2 | **What is it?** | Optical fingerprinting (a weighted hypothesis, not a lab ID) | Built |
| 3 | **How bad is it?** | Severity and confidence, reported separately, never multiplied | Built |
| 4 | **Where is it going?** | Wind-driven surface drift forecast, 0–48 h | Built |
| 5 | **What will it hit?** | Critical asset exposure and ETA | Built |
| 6 | **Where did it come from?** | **Source tracing**: backward drift, archive look-back, source matching | **New** |
| 7 | **Where do I send the field team?** | **Information-gain sampling**: where one sample tells you the most | **Upgraded** |

Questions 1–5 describe the present and the future of an event. Question 6 adds its past. Knowing where an anomaly came from also changes the answer to question 7: the most useful sample is often not at the strongest signal but at the point that tells competing explanations apart.

---

## How it works

```
Sentinel-3 OLCI (daily, 300 m)   ─►  WATCH        wide-area screening, multi-year baseline
Sentinel-2 MSI (10–20 m)         ─►  MAP          boundaries, seasonal percentile check
Tanager-1 → 813 simulator        ─►  FINGERPRINT  what kind of anomaly (weighted hypothesis)
Risk engine                      ─►  ASSESS       severity + confidence → priority (rule table)
ERA5 wind drift, forward         ─►  FORECAST     where it is going
ERA5 wind drift, backward        ─►  TRACE        where it came from                  ◄ NEW
Operator asset register          ─►  PROTECT      which assets are exposed, and when
Information-gain planner         ─►  SAMPLE       where one sample resolves the most  ◄ UPGRADED
```

| Stage | Sensor / source | Role | Resolution |
|---|---|---|---|
| A. Regional watch | Sentinel-3 OLCI | Ocean-colour screening, baseline climatology | 300 m |
| B. Spatial detail | Sentinel-2 MSI | Boundary mapping, same-hour cross-check | 10/20/60 m |
| C. Spectral forensics | Planet Tanager-1 (426 bands) → **simulated 813** | Spectral fingerprint | 30 m |
| D. Thermal context | Landsat 8/9 OLI-TIRS | Surface water temperature | 30 m |
| E. Validation | Sentinel-3 OLCI L2 products | Independent chlorophyll / TSM reference | 300 m |
| Drift | ERA5 10 m wind (Open-Meteo archive) | Forecast and backtrack | Hourly |

### A note on Satellite 813 data

This PoC holds **no real Satellite 813 pixels**. The programme says 813 data is incubation-only and tells teams not to build a PoC that depends on it. Everything labelled "813" is a **simulation** built from real Planet Tanager-1 data: Gaussian spectral-response convolution onto the published 813 band set (205 bands, 400–1700 nm), at Tanager's native 30 m rather than an invented 20 m. See [`docs/813_PRODUCT_NOTES.md`](docs/813_PRODUCT_NOTES.md).

---

## NEW: Where did it come from? (source tracing)

The forecast tells an operator where an anomaly is going. Operators also need to know **where it started**:

- **Stop it.** A spill, an outfall or a discharge keeps going until someone finds it and shuts it off. Cleaning up downstream does nothing about the cause.
- **Predict the next one.** A chronic source such as a river mouth or a sewage outfall will produce the same event again. A one-off such as a ship discharge will not.
- **Protect the intake.** An anomaly moving away from a desalination intake can still matter if its source sits up-current of it.

Source tracing produces a **ranked list of candidate origins, each with the evidence behind it**. It is a lead for investigation, not an accusation. Like the asset register, the list of candidate sources (outfalls, river mouths, ports, industrial discharges) is **supplied by the operator** or taken from open data such as OpenStreetMap. BlueBan never guesses who is responsible.

### Four independent lines of evidence

**1. Backward drift: run the forecast in reverse.**
The existing Lagrangian particle model (`pipeline/forecast.py`) is run backwards in time. Particles are seeded over the detected event, the ERA5 wind-drift vector is reversed, and the particles are integrated back 6, 12, 24 and 48 hours. The random-walk diffusion term still applies, so the cloud of possible earlier positions **widens** the further back it goes. The result is a source-probability map for each look-back horizon.

A useful side effect: when a particle "beaches" in backward time, the material could have **entered the sea at that stretch of coast**. Those shoreline entry points are where land-based sources (river mouths, outfalls, drains) would sit.

**2. Archive look-back: find the first sighting.**
The pipeline already reads the Sentinel-2 and Sentinel-3 archives for the temporal baseline. Source tracing walks backwards through those scenes (Sentinel-3 daily, Sentinel-2 every ~5 days) until the anomaly disappears. **The place it first appeared** is strong evidence of origin, and it does not depend on the drift model at all.

**3. Fingerprint matching: is the spectral signature consistent with the source type?**
The fingerprint module already outputs weighted class scores. Each candidate source type has an expected signature:

| Candidate source type | Expected optical signature |
|---|---|
| River / wadi discharge | Sediment-like, high CDOM, often cooler or warmer than the sea |
| Sewage / wastewater outfall | Chlorophyll-like or organic-rich; nutrient-driven bloom downstream |
| Thermal outfall (power station, desalination brine) | Landsat thermal anomaly; weak optical signal |
| Port / shipping | Surface film / hydrocarbon-like (FAI, sheen) |
| Dredging / resuspension (no external source) | Sediment-like, no salinity or thermal contrast |
| Bottom reflectance (nothing in the water) | Persistent, shallow, sits mid-distribution in the temporal baseline |

**4. Concentration gradient: which way is "upstream"?**
Signal strength usually falls off with distance from a point source. The direction of increasing anomaly score inside the event is a local pointer back toward the source. On its own it is weak evidence, so it is used as a tie-breaker.

### Putting it together

Each candidate source `s` gets a posterior:

```
P(s | evidence)  ∝  P(s) · L_backtrack(s) · L_archive(s) · L_fingerprint(s) · L_gradient(s)
```

Two extra hypotheses are always in the set, so the model can say "none of the above":

- **`UNREGISTERED`**: a source not in the register. It gets a floor prior so an incomplete register cannot force a wrong answer.
- **`IN_SITU`**: no external source at all (resuspension or bottom reflectance). Its likelihood comes from the existing temporal module: persistent features sit mid-distribution, real events sit in the upper tail.

Each likelihood term is reported separately, the same way the risk engine keeps severity and confidence apart. An operator can see which evidence pointed where, and disagree with it.

**Illustrative output** (shows the schema, not real results):

```json
{
  "event_id": "BB-2026-001",
  "method": "Bayesian source attribution over operator-supplied candidates",
  "backtrack_horizons_h": [6, 12, 24, 48],
  "candidates": [
    {
      "id": "SRC-03",
      "type": "RIVER_MOUTH",
      "posterior": 0.46,
      "evidence": {
        "backtrack_overlap": 0.71,
        "first_seen_distance_m": 420,
        "fingerprint_consistency": 0.80,
        "gradient_alignment_deg": 22
      }
    },
    { "id": "IN_SITU",      "type": "RESUSPENSION_OR_BOTTOM", "posterior": 0.31 },
    { "id": "SRC-01",       "type": "PORT",                   "posterior": 0.15 },
    { "id": "UNREGISTERED", "type": "UNKNOWN",                "posterior": 0.08 }
  ],
  "entropy_bits": 1.74,
  "disclaimer": "Hypothesis ranking for investigation. Not an attribution of responsibility. Requires field confirmation."
}
```

### Limits, stated up front

- The backtrack uses the same **wind-only drift** as the forecast: no tides, no geostrophic or density-driven flow, no river momentum, no bathymetric steering. In a semi-enclosed gulf those can dominate. Backward error grows with look-back time, just as forward error does.
- Diffusion cannot be undone. The backward cloud shows where the material **could** have been, and it spreads with time. Horizons past about 48 h are shown but down-weighted.
- The archive look-back is limited by cloud cover and revisit gaps. "First seen" means first seen in a clear scene, which may be later than the true start.
- Attribution is only as good as the candidate register. That is why `UNREGISTERED` always stays in the set.

---

## UPGRADED: One sample, maximum information (where to send the field team)

> *Where can I send the field team so that one water sample gives me the maximum information?*

Satellites screen; laboratories confirm. A field team has a limited budget of boat hours and samples. The current planner (`pipeline/sampling.py`) assigns samples by **role**: event core, leading edge, asset boundary, background control, uncertainty point. That covers the event well, but it does not ask which **single** sample would change the operator's picture the most.

The upgrade adds an **expected information gain** strategy.

### The idea

Before sampling, BlueBan holds a set of competing hypotheses `H`: what the event is (fingerprint classes) × where it came from (source candidates). A sample at location `x` returns a reading `y` (salinity, turbidity, temperature, chlorophyll, …). A good sample is one whose result is expected to **shrink that uncertainty the most**:

```
IG(x) = H(hypotheses)  −  Σ_y  P(y | x) · H(hypotheses | y, x)
```

In plain terms, the best place to sample is where the hypotheses **disagree most about what you would measure**. That is often not the strongest signal. It is typically:

- the fork between two backtracked paths from different candidate sources, or
- a point near a candidate source where "it came from here" and "it came from elsewhere" predict clearly different salinity or temperature, or
- a shallow point where "suspended sediment" and "bottom reflectance" can be told apart with a depth reading and a Secchi disk.

### Choosing what to measure, not just where

The same logic ranks **which analytes to request**. Some tracers separate candidate origins in one reading, and several can be measured on the boat, instantly:

| Separates… | Tracer | How fast |
|---|---|---|
| River / wadi water vs seawater | Salinity / conductivity (low), CDOM | Instant, CTD probe |
| Thermal outfall vs everything else | Temperature anomaly | Instant, CTD / thermometer |
| Suspended matter vs bottom reflectance | TSS / turbidity, Secchi depth, water depth | Instant (turbidity, Secchi, depth); TSS in lab |
| Sewage vs other organic sources | Fecal indicator bacteria (E. coli, enterococci), ammonium | Ammonium kit on site; bacteria 24–48 h |
| Nutrient-driven bloom | Chlorophyll-a, nitrate, phosphate | Fluorometer instant; lab for nutrients |
| Ship / port discharge | Hydrocarbons (TPH, PAH), visible sheen | Lab |
| Industrial effluent | Dissolved metals (Fe, Mn, Zn), pH | pH instant; metals in lab |

### Accounting for travel time

The plume keeps moving while the boat is on its way. Candidate locations are scored against the **forecast position at the team's arrival time**, not where the event was at the satellite overpass. The planner can also rank by **information per boat-hour**, `IG(x) / travel_time(x)`, when time matters more than sample count.

### Adaptive sampling

When results come back (instant CTD readings especially), the hypothesis weights are updated and the next-best point is recomputed. Each sample then decides where the next one goes, and the field plan narrows as evidence arrives instead of being fixed at the start.

### How it fits the existing planner

The information-gain strategy **adds to** the role-based plan rather than replacing it:

| Role | Question it answers | Status |
|---|---|---|
| `EVENT_CORE` | What is present at the strongest signal? | Existing |
| `LEADING_EDGE` | Is the event advancing? | Existing |
| `ASSET_BOUNDARY` | Has it reached the asset yet? | Existing |
| `BACKGROUND_CONTROL` | What does normal water read today? | Existing (always kept) |
| `UNCERTAINTY_POINT` | Where is the model least sure? | Existing |
| **`SOURCE_DISCRIMINATOR`** | **Which candidate origin is it?** | **New** |
| **`BEST_SINGLE_SAMPLE`** | **If you can take only one sample, take it here** | **New** |

A background control stays mandatory: an absolute lab value means nothing without a same-day reference.

**Illustrative output** (shows the schema, not real results):

```json
{
  "id": "S00",
  "role": "BEST_SINGLE_SAMPLE",
  "lon": 7.7712,
  "lat": 36.8871,
  "arrive_by_utc": "2025-06-01T13:30:00Z",
  "expected_information_gain_bits": 1.21,
  "measure": ["Salinity (CTD)", "Turbidity (NTU)", "Secchi depth", "Water depth", "TSS (lab)"],
  "decision_table": [
    { "if": "salinity < 36.5 PSU and TSS high",  "then": "River discharge most likely (≈ 0.85)" },
    { "if": "salinity normal and TSS high",      "then": "Local resuspension most likely (≈ 0.75)" },
    { "if": "TSS normal and depth < 4 m",        "then": "Bottom reflectance: no water-quality event (≈ 0.90)" }
  ],
  "rationale": "The three leading hypotheses predict clearly different salinity/TSS/depth combinations here. One visit with a CTD and a Secchi disk separates all three."
}
```

---

## Demo event: BB-2026-001, Gulf of Annaba

Real outputs from the current pipeline (`outputs/events/BB-2026-001.json`):

| Field | Value |
|---|---|
| Primary scene | Tanager-1 `20250601_104901_58_4001`, 2025-06-01 10:49 UTC, 0 % cloud |
| Event area | 1.13 km², median 90 m from shore |
| Anomaly | 99.7th percentile of the scene's water population (RX) |
| Fingerprint | `SEDIMENT_LIKE`: high turbidity / suspended sediment signature |
| Severity / confidence | 0.33 / 0.69 |
| Priority | **WATCH**, reduced from HIGH_PRIORITY by the temporal veto (6.6th percentile of the multi-year record: a persistent coastal feature, not an event) |
| Bottom-influence risk | 0.85 |
| Drift | Westward, bearing ≈ 273° |

**What the new modules are built to answer here.** The current system concludes "persistent feature, not an event" but cannot say why. Source tracing turns that into a testable question with three competing explanations: a chronic land source such as a nearby river mouth, local resuspension near the port, or bottom reflectance with nothing unusual in the water. The information-gain planner would then send one team to one point with a CTD, a Secchi disk and a TSS bottle, which is the cheapest measurement that separates all three.

---

## Repository layout

```
apps/web/            Next.js 14 + MapLibre operator UI (watch, spectra, forecast, assets, samples, validation)
  app/source/        Source-tracing view: backward cloud + ranked origins            (new, planned)
services/api/        FastAPI server that reads pipeline outputs (no geo-computation at request time)
pipeline/
  anomaly.py         RX spectral anomaly detection
  fingerprint.py     Optical event classes as weighted hypotheses
  risk.py            Severity, confidence, priority rule table
  temporal.py        Multi-year baselines and percentile veto
  forecast.py        Wind-driven Lagrangian drift (forward)
  source.py          Backward drift, archive look-back, Bayesian attribution         (new, planned)
  exposure.py        Operator-supplied asset exposure and ETA
  sampling.py        Role-based field plan  + information-gain strategy               (upgrade, planned)
  satellite813.py    813 sensor simulator (spectral convolution from Tanager)
  sentinel2.py / sentinel3.py / spectral.py / indices.py / quality.py / water_mask.py / provenance.py / export.py
scripts/             Offline builders (build_demo_event.py is the single orchestrator)
experiments/         Hyperspectral and detectability ablations, simulator validation
config/
  project.yaml       AOI, sensors, algorithm parameters
  assets.geojson     Operator asset register
  sources.geojson    Operator candidate-source register                              (new, planned)
docs/                813 product notes, AOI selection, data-access audit
outputs/             Events, map layers, validation results produced by the pipeline
```

### Planned configuration

```yaml
source_attribution:
  candidate_sources: config/sources.geojson   # operator-supplied, like assets.geojson
  backtrack_horizons_h: [6, 12, 24, 48]
  n_particles: 2000
  archive_lookback_days: 14
  unregistered_source_prior: 0.15

sampling:
  strategy: information_gain      # or "roles" for the current behaviour
  budget_samples: 1
  boat_speed_kn: 10
  always_include_background_control: true
```

---

## Running locally

There is no `requirements.txt` yet. The pipeline and API import:

```bash
pip install numpy scipy pyproj rasterio h5py shapely affine pyyaml matplotlib pillow fastapi uvicorn pydantic
```

Build the demo event (fetches real data, writes everything under `outputs/`):

```bash
python scripts/build_demo_event.py
```

Start the API on port 8813:

```bash
uvicorn services.api.main:app --reload --port 8813
```

Start the web UI on port 3000:

```bash
cd apps/web && npm install && npm run dev
```

Credentials are optional; see `.env.example`. Planetary Computer works anonymously for public collections.

---

## API

| Method | Endpoint | Returns |
|---|---|---|
| GET | `/api/health`, `/api/status`, `/api/config` | System status and configuration |
| GET | `/api/events` | Event index |
| GET | `/api/events/{id}` | Full event object |
| GET | `/api/events/{id}/spectrum` | Event spectra |
| GET | `/api/events/{id}/forecast` | Forward drift steps |
| GET | `/api/events/{id}/samples` | Field-sampling plan |
| GET | `/api/events/{id}/provenance` | Data lineage |
| GET | `/api/events/{id}/source` | **Ranked candidate origins + backward cloud** *(new, planned)* |
| GET | `/api/events/{id}/samples?strategy=information_gain&budget=1` | **Best single sample + decision table** *(new, planned)* |
| GET | `/api/layers`, `/api/layers/{name}` | Map layers |
| GET | `/api/validation`, `/api/hyperspectral-lift`, `/api/timeseries` | Validation results |
| GET / POST | `/api/assets` | Operator asset register |

---

## Roadmap: the "where from" feature

- [ ] `pipeline/source.py`: backward advection (reuse `forecast.advect` with reversed drift, beaching as shoreline entry points)
- [ ] Archive look-back over Sentinel-2 / Sentinel-3 for first-sighting location
- [ ] Source-type ↔ fingerprint-class consistency matrix
- [ ] Bayesian combination with `UNREGISTERED` and `IN_SITU` hypotheses; per-term evidence in the output
- [ ] `config/sources.geojson` operator register + POST endpoint (same policy as assets)
- [ ] `sampling.py`: expected-information-gain strategy, `SOURCE_DISCRIMINATOR` and `BEST_SINGLE_SAMPLE` roles
- [ ] Travel-time-aware scoring against the forecast position at arrival
- [ ] Adaptive re-planning when field readings are entered
- [ ] `apps/web/app/source`: backward cloud, ranked origins, "one sample" card
- [ ] Validation: synthetic releases from known points in the simulator, then check whether the true source ranks first

---

## Principles

- **Hypotheses, not verdicts.** Fingerprints, severity and now source attribution are weighted hypotheses with visible evidence. Lab analysis confirms.
- **Severity and confidence are never multiplied.** The same rule applies to the source-evidence terms.
- **No invented data.** No 813 pixels are claimed; simulated products are labelled everywhere.
- **Operators own sensitive locations.** Assets and candidate sources are operator-supplied, never guessed or published by the system.
- **State the physics that is missing.** The forecast and the backtrack both list what they leave out.
