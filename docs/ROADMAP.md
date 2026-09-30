# Roadmap

**BLUEBAN 813** · Team Kanban · 30 September 2026

What is deliberately **not** in the current product, why, and what it would take.
Everything here was designed earlier and deferred under the mentor brief, which
put the closed loop (detect → verify → act → learn) and scientific honesty
ahead of new inference features.

## 1. Data that would change the science (highest value)

| Item | Why it matters | What unlocks it |
|---|---|---|
| **UAE in-situ matchups** (chl-a, turbidity, TSS with time and position) | The only way to turn PROXY indices into calibrated concentrations with uncertainty. The matchup engine, model zoo, grouped CV and calibration gate are built and tested; they wait for ≥ 20 matchups in ≥ 5 independent groups | A data-sharing agreement with EAD / MOCCAE / a university monitoring programme (draft request in `docs/PUBLIC_UAE_DATA.md`, not sent), or the organizers' "on-demand" data (draft in `docs/AUTHENTICATED_DATA_AUDIT.md`, not sent) |
| **Real Satellite 813 products** | Replace the simulated 813 arm of every ablation with real pixels; validate the Gaussian-SRF simulator against the instrument | Access from the programme. Until then every 813 value stays labelled SIMULATED |
| **Tanager scene over the UAE (Tarif)** | Repeat the 813 ablation on UAE water instead of Annaba | The 1.1 GB scene download (awaiting approval) |
| **Water-specific atmospheric correction** (ACOLITE / C2RCC / POLYMER) | Sen2Cor is a land processor; the SWIR offset removes only first-order glint. NDCI is unstable over very clear water (BB-AE-2023-001) | Compute budget and a per-scene processing step before WATCH |

## 2. Source attribution (deferred)

*"Where did it come from?"* — ranked candidate origins with the evidence behind each, never an accusation.

* **Backward drift** — run the Lagrangian particle model backwards 6–48 h from the event; diffusion widens the cloud with look-back; beaching points mark possible land entry.
* **Archive look-back** — walk back through Sentinel-2/3 scenes to the first clear sighting.
* **Fingerprint consistency** — does the optical class match the source type (river: sediment + CDOM; outfall: organic / bloom; thermal outfall: Landsat thermal; port: surface film)?
* **Gradient** — direction of increasing anomaly inside the event (tie-breaker only).
* Combined as `P(s | evidence) ∝ P(s) · L_backtrack · L_archive · L_fingerprint · L_gradient`, with `UNREGISTERED` and `IN_SITU` always in the set so an incomplete register cannot force a wrong answer.

**Why deferred:** the drift is wind-only (no tides, currents, density flow or bathymetry). In the Gulf those can dominate, and a confident-looking source ranking on that physics would break the product's first rule. It needs a hydrodynamic model (e.g. Copernicus Marine currents) and synthetic-release validation first.

## 3. Information-gain sampling (deferred)

*"If you can take only one sample, take it here."* — choose the point where competing hypotheses disagree most about what you would measure, scored against the forecast position at the boat's arrival time and updated adaptively as on-board readings (CTD, Secchi, turbidity) come in; also rank which analytes separate the hypotheses (salinity for river water, temperature for thermal outfalls, depth + Secchi for bottom reflectance).

**Why deferred:** its value depends on hypothesis likelihoods that are only meaningful once field results exist to calibrate them. The current role-based plan (core, edge, background control, uncertainty, asset boundary) is transparent and always keeps a background control.

## 4. Product

* Sentinel-1 surface-dark-anomaly mode as a first-class detector (currently documented; always reported as an oil-spill *lookalike set*).
* Multi-user deployment of the FastAPI store on PostgreSQL (`DATABASE_URL`), SSO, role-based review permissions.
* Scheduled WATCH runs (new acquisitions within hours of publication) and push delivery through the alert webhook.
* Model families beyond logistic triage (the offline zoo already compares linear, PLSR, RF, GBM, SVR, ridge-log10 under grouped CV) once label volume justifies them.
