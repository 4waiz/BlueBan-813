# Judging Matrix

The official criteria are the five in the challenge repository README: **Impact,
Creativity, Validity, Relevance, Presentation**. Each row below maps a criterion
to the feature that addresses it, the evidence a judge can check, the metric, and
where in the demo it appears.

Every figure quoted here is produced by the pipeline and served by the API. None
is written into the interface.

---

## 1. Impact

| | |
|---|---|
| **Feature** | Asset-aware exposure with an ETA, plus a sampling planner that targets a limited field budget |
| **Evidence** | A real 72 MW thermal power station 0.93 km from the detected region, exposure 0.738, modelled drift contact at +6 h. Five real, OSM-verified coastal assets in the register. |
| **Metric** | 46.4 % relative reduction in false alarms. Each false alarm is a crewed vessel dispatch, so that is the cost line the product moves. |
| **Demo moment** | Judge Mode step 6, then the Assets screen |
| **Where** | `pipeline/exposure.py`, `config/assets.geojson`, `/api/events/{id}` → `exposure` |

The regional argument is water security, not a generic SDG list. The Arab region
depends on coastal water for potable supply, industrial cooling and food, and the
same optical screening problem recurs from the Maghreb to the Gulf. The method is
percentile-based specifically so it ports without re-tuning; see
`BUSINESS_CASE.md`.

---

## 2. Creativity

| | |
|---|---|
| **Feature A** | The **813 sensor simulator**: answering the mission-utility question before the mission flies |
| **Evidence** | Gaussian SRF convolution of a real 426-band cube onto 813's published 205-band table, with the same machinery validated against a real Sentinel-2 acquisition 38 minutes apart |
| **Metric** | r = 0.95–0.97, slope 0.91–1.04 over land in the visible |
| **Demo moment** | Judge Mode step 8 |
| **Feature B** | The **temporal veto**: a product that can say "nothing is happening" |
| **Evidence** | The same spatial anomaly scores HIGH_PRIORITY with no temporal context and WATCH with a 5.4-year record |
| **Metric** | 6.6th seasonal percentile from 428 zone observations |
| **Demo moment** | Judge Mode step 4, then the Watch screen |
| **Feature C** | Uncertainty-propagated indices using the sensor's own per-pixel σ |
| **Evidence** | Naive NDCI spans −1907 to +2407 on this scene; the guard bounds it to ±1 at a cost of 0.8 % of pixels |
| **Where** | `pipeline/satellite813.py`, `pipeline/risk.py`, `pipeline/indices.py` |

The originality is not a new index. It is that the system is built to **withhold
an alarm**, and that the value of the hyperspectral mission is measured rather
than asserted.

---

## 3. Validity

This is the criterion the project is built around.

| Claim | Evidence | Where |
|---|---|---|
| Band quality comes from the product, not a tutorial | Product flags 1342.41–1437.55 and 1782.58–1967.21 nm; the notebooks hardcode 1350–1450 and 1800–1950 | `METHODOLOGY.md` §1 |
| Informative bands are measured, not assumed | 100 of 368 bands clear SNR ≥ 3 against the instrument's own uncertainty layer, inside 401–896 nm | `METHODOLOGY.md` §5 |
| Indices are physically bounded | Uncertainty-propagated significance guard at k = 3σ | `METHODOLOGY.md` §4 |
| The detection threshold is calibrated, not picked | χ²(12) flags 14.57 % of water; the empirical 1 % background FAR flags 2.64 %. Both reported. | `METHODOLOGY.md` §6 |
| Validation splits are spatial | 173 spatial blocks; the random-split figures are published alongside to show the inflation | `VALIDATION_REPORT.md` §4 |
| The lift is statistically tested | ΔF1 = +0.0065, 95 % CI [0.0050, 0.0080], paired bootstrap | `VALIDATION_REPORT.md` §3 |
| The conclusion is robust to a specification ambiguity | 261-band 5 nm variant gives F1 = 0.9919 vs 0.9918 | `VALIDATION_REPORT.md` §3 |
| Negative results are reported | Two experiments found no advantage; both are on the Validation screen above the headline | `VALIDATION_REPORT.md` §2 |
| Our own methodological error is documented | A random inner CV split drove PLSR to its cap and produced R² = −15.7; the fix is in the code | `VALIDATION_REPORT.md` §4 |
| Provenance is complete | 100 % across 5 source records, with SHA-256 on the primary scene | Data screen |
| Limitations are enumerated, not hidden | 11 sections including "what we deliberately did not do" | `LIMITATIONS.md` |

**The strongest single validity signal:** we downgraded our own headline event.
The RX detector found a 1.13 km² anomaly with a coherent sediment signature, and
the multi-year baseline said the water was cleaner than usual that day, so the
system reduced the priority and the interface explains why.

---

## 4. Relevance

| | |
|---|---|
| **Theme fit** | Water Quality & Inland/Coastal Water Intelligence: turbidity, chlorophyll proxies, pollution-plume screening, coastal zone |
| **Completeness** | Detect → fingerprint → verify temporally → forecast → assess exposure → plan sampling → record provenance. All nine cascade stages run end to end on real data. |
| **Feasibility** | Entire pipeline runs from a clean checkout with open data and no authentication. Primary scene is 0.9 GB. Event build takes ~32 s. |
| **Usability** | Nine-screen operator interface, a nine-step guided walkthrough, and a documented read-only API with live request execution |
| **Hyperspectral use** | Central, and measured rather than claimed |

**Data reality handled correctly.** The official guide states 813 is
incubation-only and instructs teams not to depend on it. We complied, and turned
the constraint into the contribution: a mission-utility study. See
`813_PRODUCT_NOTES.md`.

**AOI chosen on evidence.** We wanted a UAE scene. The only Tanager
coastal-water scene over the UAE is 51 % cloud with 38.6 % valid pixels — a
figure printed in the official notebook's own output. We chose the data and
documented the decision in `AOI_SELECTION.md`.

---

## 5. Presentation

| | |
|---|---|
| **Visual system** | Aerospace flight-control language: near-black field, thin instrumentation rules, chamfered panels, monospaced telemetry, colour used only to carry state |
| **Hero object** | An animated dark-ocean view: drift streamlines from the real ERA5-derived field, particle trails interpolated between horizons, an event glow with a reticle so a 1 km² plume is findable at AOI zoom |
| **Signature screen** | The hyperspectral oscilloscope, which shows Sentinel-2's band footprints overlaid on the continuous spectrum so the gaps are visible rather than described |
| **Judge Mode** | Nine steps with the line to say, the evidence on screen, and a jump to the page that proves it. Keyboard navigable, with an auto-advance option. |
| **Honesty in the design** | Negative results appear *above* the headline on the Validation screen; the simulated-813 badge is in the top strip; every proxy is named as a proxy |

**Every number in the interface is read from pipeline output.** There are no
fallback constants: colour-scale limits, AOI extent, water area, band counts and
the event id are all served by the API, so the interface cannot drift out of step
with the data.

---

## The user's own seven-dimension framing

| Dimension | Strongest evidence |
|---|---|
| **1. Problem definition** | A specific operator decision: should a vessel be dispatched, and to where. `BUSINESS_CASE.md` names the buyer and the workflow replaced. |
| **2. Technical robustness** | Product-native band flags; uncertainty propagation; empirically calibrated thresholds; spatially blocked validation; a documented self-correction. |
| **3. Meaningful hyperspectral use** | 100 measured-informative bands; local band depths; an RX detector in PCA space; and a controlled ablation isolating spectral configuration as the only variable. |
| **4. Product & presentation** | Nine screens, an animated hero map, a guided demo, a live API console. |
| **5. Innovation** | The 813 simulator as a pre-launch mission-utility study; the temporal veto; severity and confidence never combined. |
| **6. Impact & strategic alignment** | Real exposed industrial asset at 0.93 km; a 46 % false-alarm reduction; SDG 6 and 14 through coastal water security. |
| **7. Commercial viability** | Annual AOI subscription with named expansion paths and a stated replacement for scheduled boat sampling. `BUSINESS_CASE.md`. |

---

## The quantitative answer to "why 813"

| | Multispectral baseline | + 813 hyperspectral | Lift |
|---|---|---|---|
| **Operational detection boundary (F1)** | 0.9853 | **0.9918** | **+0.0065**, CI [0.0050, 0.0080] |
| False-alarm share | 2.806 % | **1.503 %** | **−46.4 % relative** |
| False positives (of 25 513 samples) | 159 | **84** | 75 fewer |
| Gross plume detection (F1) | 0.9998 | 0.9999 | +0.0001, **not significant** |
| OLCI CHL_NN retrieval (R²) | 0.078 | 0.010 | −0.068, **not significant** |
| OLCI TSM_NN retrieval (R²) | 0.123 | 0.129 | +0.007, **not significant** |

Read together: **hyperspectral resolution does not help you see an obvious
plume, and on this evidence it does not improve a coarse-resolution
concentration retrieval either. What it does is halve the false-alarm rate at
the operational decision boundary** — which is precisely where a monitoring
programme spends its money.

---

## Where to look, in order, for a sceptical reviewer

1. `docs/LIMITATIONS.md` — the boundary of the evidence, first.
2. `docs/VALIDATION_REPORT.md` §0 and §2 — what we could not establish.
3. The **Validation** screen — negative results appear before the headline.
4. `docs/DATA_ACCESS_AUDIT.md` §1 — why there is no 813 data here.
5. The **Data** screen — provenance with the source checksum.
6. `docs/METHODOLOGY.md` §4 and §6 — the two places we departed from the
   tutorial approach, and why.
