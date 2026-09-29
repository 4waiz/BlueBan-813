# Mentor Revamp Audit

**BLUEBAN 813** · Team Kanban · audit performed 2026-09-30 on branch `feat/mentor-revamp`
(base: `main` @ `ebeb426`).

This is the inventory we took **before changing anything**. Every major module in
the repository is classified as one of:

| Verdict | Meaning |
|---|---|
| **KEEP** | Scientifically sound and still useful as is. Only renames or tests added. |
| **REWORK** | The idea is right, the implementation has to change for the mentor brief. |
| **REMOVE** | Stale, misleading or off-brief. Deleted or rewritten from scratch. |
| **DEFER** | Good, but not before the core result is validated (after 11 Oct). |
| **NEW** | Does not exist yet and is required by the brief. |

The mentor feedback that drives every verdict is summarised in §1. What was
actually run during the audit is in §2.

---

## 1. What the mentor asked for, and what it changes

| # | Mentor point | Consequence for the codebase |
|---|---|---|
| 1 | Use Sentinel-2 | Sentinel-2 moves from "baseline helper" to the **primary high-resolution detection sensor**. |
| 2 | Use Level-2A | Read L2A with the per-product BOA offset instead of re-deriving reflectance; never start from L1C. |
| 3 | Meaningful water-quality features | Replace the four-index set with a documented feature set (NDCI, MCI, FAI, red-edge ratio, turbidity and TSS semi-analytical proxies, CDOM ratio, water mask), each with formula, bands, resolution, source and limitations. |
| 4 | An index is not a concentration | Every output carries a `quantity_kind`: `PROXY`, `GENERIC_CALIBRATION` (published coefficients, not validated here) or `CALIBRATED` (validated against local matchups, with an interval). The UI can only print mg/m³ / NTU for `CALIBRATED`. |
| 5 | Use in-situ / reference data | New matchup engine and a regression model zoo (linear, PLSR, RF, GBM, SVR) with grouped/spatial validation. |
| 6 | UAE is the main AOI | Annaba is demoted to **negative control**; a UAE AOI is chosen by tournament on real data availability. |
| 7 | Real results over more features | Source attribution and information-gain sampling are moved to the roadmap. |
| 8 | Operator feedback loop | New incident entity, review workflow, label store, training jobs, model registry and a human-approved promotion gate. |

---

## 2. What was run during the audit

| Check | Result |
|---|---|
| `git status` | Clean on `main` apart from the untracked design reference (`dashboard.png`, now `docs/design/dashboard-target.png`). |
| `pytest tests/` | **75 passed** in 5.5 s. |
| `uvicorn services.api.main:app` | Starts; serves the Annaba event from `outputs/`. |
| `npm run dev` (apps/web) | Starts; all ten routes render against the API. The map has **no basemap**: the Tanager footprint floats on black. |
| `npx wrangler whoami` / `pages project list` | Logged in; Pages project `blueban813` exists (last deployed a week ago, `blueban813.pages.dev`). |
| Raw data on disk | **None.** `data/raw/` is absent (correctly gitignored); the 0.9 GB Tanager cube would have to be re-fetched to rebuild the Annaba event. All derived outputs are committed. |
| Authenticated platform re-audit | Blocked at sign-in in the automation browser; see `AUTHENTICATED_DATA_AUDIT.md`. |

---

## 3. Stale conclusions found

The 2026-09-15 audit concluded that gIQ was unavailable, that Satellite 813 was
not practically available and that the in-situ records could not be downloaded.
The team now has an authenticated gIQ account and Cockpit dataset cards for 813,
OLCI, Landsat and in-situ records. **Those conclusions are therefore treated as
unverified until re-audited**, and the documents that depend on them are marked
historical rather than deleted:

| Document | Status after this audit |
|---|---|
| `DATA_ACCESS_AUDIT.md` | Moved to `docs/archive/DATA_ACCESS_AUDIT_2026-09-15.md` with a "historical, superseded" banner. Replaced by `AUTHENTICATED_DATA_AUDIT.md`. |
| `OFFICIAL_RESOURCE_AUDIT.md` | Moved to `docs/archive/` with the same banner; its repository and notebook findings remain valid and are cited from the new audit. |
| `AOI_SELECTION.md` | Moved to `docs/archive/AOI_SELECTION_TANAGER_2026-09-15.md`. Its reasoning was correct for a Tanager-constrained search; the new selection is `UAE_AOI_TOURNAMENT.md`. |
| README "BluePulse" wording | Leftover from an earlier name. Removed everywhere; the product is **BLUEBAN 813**. |
| `.env.example` `BLUEPULSE_API_*` | Renamed `BLUEBAN_API_*`. |
| `scripts/deploy_cloudflare.sh` target `blue.kanbanstudios.ae` | Target is now `blueban813.kanbanstudios.ae`. |

---

## 4. Module-by-module verdicts

### 4.1 Pipeline

| Module | Verdict | Reasoning | Action |
|---|---|---|---|
| `anomaly.py` (RX / Mahalanobis) | **KEEP** | Robust trimmed background, PCA whitening, empirically calibrated threshold instead of the violated χ² null. This is the correct detector and the mentor did not ask to replace it. | Cap `n_components` at `n_bands − 1` so it runs on Sentinel-2 feature stacks as well as hyperspectral cubes; add tests on an 8-band input. |
| `fingerprint.py` | **KEEP → REWORK** | The weighted-hypothesis design, class citations and the 45 % "UNKNOWN" floor are exactly the honesty the brief wants. It assumes a continuous spectrum, so on Sentinel-2 several evidence terms are silently unavailable. | Keep for hyperspectral. Add an explicit multispectral mode that reports which evidence could not be formed (e.g. no 620 nm band). Map class names to the incident `event_type_hypothesis` vocabulary. |
| `risk.py` | **KEEP** | Severity and confidence never multiplied; rule-table priority; temporal veto. The strongest part of the repo. | Confidence cap now lifts only when a field measurement is attached through the VERIFY workflow. Sensor agreement becomes a real input. |
| `temporal.py` | **KEEP** | Local seasonal percentiles are the false-alarm suppressor that makes Annaba a negative control. | Reuse unchanged for the UAE baseline. |
| `indices.py` | **REWORK** | Specs and uncertainty-propagated guards are good. The set is too thin for the mentor brief (no MCI, no S2-specific band mapping, no native resolution per index, no semi-analytical turbidity/TSS). | Add S2 band table and `quantity_kind`; add MCI, AFAI/FAI for S2, red-edge ratio, Nechad TSS and Dogliotti turbidity (as `GENERIC_CALIBRATION`), CDOM ratio; tests for every formula. |
| `quality.py` | **KEEP** | Mask reports are auditable. | Add Sentinel-2 SCL and OLCI WQSF reports in the same format. |
| `water_mask.py` | **KEEP** | MNDWI + NIR darkness + component filter + shoreline erosion. | Tests on S2 20 m grid (buffer in metres, not pixels). |
| `spectral.py` | **KEEP** | Correct local band depth, SAM, difference spectra with significance. | Used by the Spectral Lab and the 813 path unchanged. |
| `sentinel2.py` | **REWORK** | Offset handled by a **date rule**; ESA has reprocessed older data, so the correct switch is the product's own processing baseline. Reads only 6 bands. | Read `s2:processing_baseline` / `BOA_ADD_OFFSET` per item; read B01-B12 at a common 20 m grid; SCL masks; scene-level QC summary; feature extraction entry point. |
| `sentinel3.py` | **KEEP** | Correct: uses ESA's operational CHL_NN / TSM_NN in native log10 and never re-derives them. | Used for WATCH and as cross-sensor **reference**, never called ground truth. |
| `satellite813.py` | **KEEP (as simulator)** | Gaussian SRF convolution with a min-support rule is sound. | Relabelled **SIMULATOR / FALLBACK / TEST HARNESS**. If real 813 data is obtained, `satellite813_real.py` becomes the primary path. |
| `forecast.py` | **KEEP, DEMOTED** | Honest about being wind-only; beaching handled; offshore wind sampling documented. | Output relabelled **SCENARIO TRAJECTORY ESTIMATE** everywhere. Copernicus Marine currents upgrade **DEFERRED** unless the core is finished. |
| `exposure.py` | **KEEP** | Operator-owned assets, basis prose. | New UAE register from OpenStreetMap element ids, same policy. |
| `sampling.py` | **REWORK** | Role-based plan is good but is a one-shot export. | Becomes a workflow: editable points, statuses (PLANNED → COLLECTED → LAB_PENDING → RESULT_RECEIVED), CSV/GeoJSON export, measurement entry and lab CSV upload. |
| `provenance.py` | **KEEP → strengthen** | Completeness scoring is good. | Add model id/version and the "why am I seeing this" evidence chain for every displayed number. |
| `export.py` | **KEEP** | | |

### 4.2 Scripts and experiments

| Item | Verdict | Action |
|---|---|---|
| `scripts/build_demo_event.py` | **KEEP (negative control)** | Still builds the Annaba case. Its event becomes incident `BB-DZ-2025-001` (alias `BB-2026-001`) with disposition *stand down: persistent feature*. |
| `scripts/build_baseline.py` | **REWORK** | Parametrise by AOI so the same code builds the UAE baseline. |
| `scripts/build_matchup.py` | **KEEP (cross-sensor experiment)** | Tanager↔OLCI matchups stay as a historical experiment. In-situ matchups get a new engine, `pipeline/matchup.py`. |
| `scripts/build_static_site.py` | **REWORK** | Bake incidents, models and the UAE layers as well. |
| `scripts/fetch_tanager.py` | **KEEP** | |
| `scripts/deploy_cloudflare.sh` | **REWORK** | New domain; Pages Functions + D1 for the persistent write path. |
| `experiments/validate_simulator.py` | **KEEP** | Simulator validation against a real S2 acquisition 38 min apart is still the best evidence the simulator is trustworthy. |
| `experiments/detectability_ablation.py` | **KEEP** | The −46 % false-alarm result stays, labelled as a *simulated-813 on Tanager* result for Annaba. |
| `experiments/hyperspectral_ablation.py` | **KEEP (historical)** | OLCI-target ablation (no advantage) stays reported. The **new** A/B/C ablation uses in-situ labels over the UAE AOI. |

### 4.3 Backend

| Item | Verdict | Action |
|---|---|---|
| `services/api/main.py` read endpoints | **KEEP** | Existing contracts preserved. |
| No persistence, one `assets.json` write | **REWORK** | SQLite by default (`DATABASE_URL` for PostgreSQL later): incidents, observations, reviews, samples, measurements, labels, training jobs, models, model metrics, assets, audit events. Large rasters stay on disk. |
| Write endpoints | **NEW** | `POST /api/incidents/{id}/review`, `POST /api/incidents/{id}/measurements`, `POST /api/training/retrain`, `GET /api/training/jobs`, `GET /api/models`, `GET /api/models/{id}`, `POST /api/models/{id}/promote`, `POST /api/models/{id}/rollback`. |

### 4.4 Frontend

| Item | Verdict | Action |
|---|---|---|
| Design language (near-black field, thin rules, chamfers, mono telemetry) | **KEEP** | It already reads as flight control. Refined toward `docs/design/dashboard-target.png`. |
| `Shell.tsx` layout | **REWORK** | Top bar with AOI / last observation / active model / next pass / UTC; left mission rail WATCH → LEARN with state and blocking warnings; bottom system dock. |
| `OceanMap.tsx` | **REWORK** | Satellite basemap, sensor layers, incident polygons, stations, samples (draggable), assets, time scrub, before/after compare, pixel click. |
| `/` Overview | **REWORK** | Becomes **Incident Control**: map hero + incident telemetry. |
| `/watch` | **REWORK** | AOI monitoring table: last observation per sensor, valid imagery, change from baseline, open incidents. |
| `/spectra` | **REWORK** | Spectral Lab: 2D scientific plot + 3D hyperspectral cube (React Three Fiber). |
| `/forecast` | **REWORK (demoted)** | Folded into the incident view as a scenario trajectory panel. |
| `/assets`, `/data`, `/api` | **KEEP** | Updated for UAE and provenance chain. |
| `/samples` | **REWORK** | Becomes **Field Ops**. |
| `/validation` | **REWORK** | Sections A-F: data quality, UAE matchups, model performance, 813 ablation, spatial holdout, negative control. |
| `/judge` | **REWORK** | Rebuilt around the mentor story (11 steps, closed loop). |
| `/incidents`, `/incidents/[id]`, `/learn` | **NEW** | Verification queue, investigation screen, learning loop. |

### 4.5 Documentation

| Item | Verdict |
|---|---|
| `METHODOLOGY.md`, `LIMITATIONS.md`, `VALIDATION_REPORT.md`, `DATA_LINEAGE.md` | **REWORK** for the UAE hero case; Annaba sections retained as negative control. |
| `813_PRODUCT_NOTES.md` | **REWORK** after the 813 re-audit. |
| `BUSINESS_CASE.md`, `JUDGING_MATRIX.md` | **REWORK** for the closed-loop positioning. |
| README source-attribution and information-gain sections | **DEFER** → `docs/ROADMAP.md` (stretch goals). |

---

## 5. REMOVE list

| What | Why |
|---|---|
| "BluePulse" name in README and env vars | Stale product name. |
| README presenting source tracing as a headline capability | It is unbuilt; presenting a roadmap item as a feature is the kind of overclaim the project otherwise avoids. |
| `forecast` as a top-level destination | A wind-only scenario tool must not dominate the product. |
| Any claim that Annaba is the primary demo | It is the negative control. |

## 6. DEFER list (not before 11 October)

| What | Condition to un-defer |
|---|---|
| Bayesian source attribution (`pipeline/source.py`) | Core UAE result, calibration, 813 experiment and closed loop all validated. |
| Information-gain sampling | Same. |
| Copernicus Marine current-driven trajectory | Same, plus an authenticated CMEMS account supplied by the team. |
| Blender assets | Only with an accurate, permitted official 813 reference; otherwise an abstract sensor visual or nothing. |

## 7. NEW list

| What | Where |
|---|---|
| Authenticated data audit | `docs/AUTHENTICATED_DATA_AUDIT.md` |
| Public UAE in-situ source search | `docs/PUBLIC_UAE_DATA.md` |
| UAE AOI tournament | `docs/UAE_AOI_TOURNAMENT.md`, `scripts/aoi_census.py` |
| Sentinel-2 L2A water-quality feature set | `pipeline/s2_features.py` |
| Sentinel-1 surface-dark-anomaly mode (optional) | `pipeline/sentinel1.py` |
| Satellite ↔ field matchup engine | `pipeline/matchup.py` |
| Quantification model zoo | `pipeline/quantify.py` |
| Incident entity and state machine | `pipeline/incidents.py` |
| Label store, training jobs, model registry, promotion gate | `pipeline/learning.py`, `services/api/db.py` |
| Real 813 reader (only if data is obtained) | `pipeline/satellite813_real.py` |
| 813 A/B/C ablation on UAE labels | `experiments/ablation_813_uae.py` |
| Research paper on GitHub Pages | `paper/`, `.github/workflows/pages.yml` |
| Reproducible Python environment | `pyproject.toml` |
