# Judging Matrix

**BLUEBAN 813** · Team Kanban · theme: Water Quality & Inland/Coastal Water Intelligence · updated 7 October 2026

The Proof-of-Concept stage is judged on seven published criteria, with bonus
points for effective use of hyperspectral data (Satellite 813 where available),
and the technical score breaks ties. Each row below maps a criterion to what
addresses it, the evidence a judge can check, the number, and where to see it.
Every figure is produced by the pipeline (`outputs/`) and shown by the app;
none is typed into the interface. Figures between `num` markers are rewritten
by `scripts/build_validation.py`.

---

## 1. Problem definition

| | |
|---|---|
| **What** | Most of the UAE's drinking water comes from about 70 major desalination plants on its two coasts ([UAE Government portal](https://u.ae/en/information-and-services/environment-and-energy/water-and-energy/water-)). In the 2008–09 *Cochlodinium* red tide, seawater reverse-osmosis plants shut for up to four months, Fujairah's among them ([IOC-UNESCO 2017, Manuals and Guides 78](https://repository.oceanbestpractices.org/handle/11329/759)). Today the warning comes from intake filters, a boat sample on a fixed calendar, or the public |
| **The gap** | Free Sentinel-2/3 images exist every few days, but nobody turns them into a decision: *is this unusual for this spot and season, and where should the boat go?* |
| **Evidence** | `docs/BUSINESS_CASE.md` §1; README "The problem" |
| **Demo** | Judge Mode step 1 ("Why this matters") |

## 2. Technical robustness

| | |
|---|---|
| **What** | Every pixel compared with its **own** same-season history (robust z and seasonal percentile), baseline-aware Sentinel-2 L2A reading, glint-aware water mask, same-morning Sentinel-3 OLCI cross-check, frozen grouped validation split with bootstrap intervals, negative controls, parity-tested trainer (Python and browser agree to 1e-7), CI |
| **Scale** | 5,080 Sentinel-2 datatakes screened over 10 UAE areas (2017–2026). No threshold is absolute: a new area needs its baseline built, not a model re-tuned |
| **Number** | <!--num:triage-->On the frozen validation set (100 labels) the learned triage candidate reaches AUPRC 0.94 vs 0.66 for the rule it would replace; the grouped bootstrap 95 % interval on the difference is [0.04, 0.48], excluding zero, and it beats the rule on 9 of 9 held-out AOIs (promotion still gated)<!--/num:triage--> |
| **Reproducible** | `notebooks/blueban813_poc.ipynb` runs offline from `data/sample_input/` and reproduces the Fujairah detection and the learning gate; `python -m pytest -q` |
| **Demo** | Validation screen A–F; Judge Mode steps 5, 10–11 |

## 3. Use of hyperspectral and Earth-observation data (+ hyperspectral bonus)

| | |
|---|---|
| **Multi-sensor** | Sentinel-2 L2A (detection, 20 m), Sentinel-3 OLCI (cross-sensor reference, never ground truth), Landsat 8/9 (inland baseline, thermal context), Sentinel-1 (optional dark-slick screen), ERA5 wind (drift scenario) |
| **Hyperspectral** | Satellite 813's published band set (~205 bands, 400–1700 nm, 20 m) simulated from **real** hyperspectral pixels: Planet Tanager-1 (Gulf of Annaba) and EnMAP L2A (Shawka Dam, two dates; 196 of 205 simulated 813 bands have real EnMAP support) |
| **Measured, not assumed** | On the same real pixels, at the operational decision boundary, the simulated 813 band set cut false alarms from 159 to 84 (−47 %) at the same recall; **no gain** on gross plumes; concentration vs OLCI **not demonstrated**. All 813 values are labelled SIMULATED: no 813 product was accessible to teams |
| **Evidence** | `experiments/detectability_ablation.py`, `outputs/validation/detectability_lift*.json`, `docs/inland/SATELLITE_813_DECISION.md` |
| **Demo** | Spectral Lab ("What did 813 add?"), Inland screen (EnMAP → 813 band ladder), Judge Mode step 6 |

## 4. Product and presentation

| | |
|---|---|
| **What** | A working decision-support web app (one-screen dashboards, works on phones), an HTTP API (FastAPI, `/api` screen documents every route), exportable incident reports and evidence packages, a research paper, and a reproducible notebook |
| **Deployable** | Static build served from Cloudflare Pages at near-zero cost; the same app runs against the FastAPI + SQLite/PostgreSQL backend for operations |
| **Evidence** | Live at BlueBan813.kanbanstudios.ae (blueban813.pages.dev); paper at 4waiz.github.io/BlueBan-813 |
| **Demo** | One-click Judge Mode (13 steps, about 3 minutes, real review / retrain / promote actions); full-screen 3D Satellite View with real orbits |

## 5. Innovation

| | |
|---|---|
| **What** | (i) Judged against the pixel's **own** history, so a permanently turbid harbour stops raising alarms. (ii) An independent satellite as a same-morning cross-check and weak teacher. (iii) A governed learning loop: production is untouched until a candidate passes a frozen-validation gate **and** a named person approves; one-click rollback; hash-chained audit log. (iv) A measured answer to "what does 813 add?" before 813 data exists |
| **Evidence** | `pipeline/detect.py`, `scripts/build_labels.py`, `pipeline/learning.py` + `apps/web/lib/learning.ts` |
| **Demo** | Judge Mode steps 5, 9–11; Learn screen |

## 6. Impact and strategic alignment

| | |
|---|---|
| **What** | Protects potable-water intakes and coastal users on both UAE coasts; directs scarce sampling to where it resolves something; leaves an auditable record a regulator can rely on |
| **Alignment** | Challenge theme 03 (water security and marine environments: harmful blooms, desalination protection); SDG 6 (targets 6.3, 6.5) and SDG 14 (target 14.1); the same method ports from the Gulf to the Maghreb (Annaba is the negative control) |
| **Validity** | Honest data policy: no concentration from an uncalibrated index, OLCI is a reference, 813 is simulated; <!--num:xsensor-->436 OLCI references; Spearman ρ between the S2 change and the OLCI contrast 0.46 for sediment-like candidates (n = 353) and -0.19 for bloom-like ones (n = 83)<!--/num:xsensor-->, reported as the weakness it is |
| **Negative controls** | Annaba (RX 99.7th percentile but 6.6th seasonal percentile → stood down) and BB-AE-2023-001 (NDCI spike over unchanged blue water; OLCI ×1.1 → rejectable) |
| **Demo** | Judge Mode step 12 ("Who uses it"); Validation → F |

## 7. Commercial viability

| | |
|---|---|
| **Who pays** | Desalination and power operators (intake early warning), environment regulators and municipalities (targeted sampling, bathing-water compliance), ports, aquaculture and beach operators |
| **How** | Per-area monitoring subscription; per-asset alerting; per-event hyperspectral (813) analysis; reports and API. Inputs are open data, so marginal cost per area is compute and storage |
| **Next** | One pilot: one coast, one operator, one season, compared with the operator's own lab record. Incubation: deploy on the GIQ platform and swap the simulator for real 813 data |
| **Evidence** | `docs/BUSINESS_CASE.md` (no revenue is claimed: no signed pilot yet) |

---

## Where a sceptical reviewer should look, in order

1. **Validation → C and E**: the rule has no skill against the cross-sensor reference; the candidate does, across held-out AOIs.
2. **Validation → F** and **BB-AE-2023-001**: the system shows its own false positive.
3. **Data → Source register**: every input, its licence and whether it is used.
4. **Spectral Lab → What did 813 add?**: gains where measured, "no gain" and "not demonstrated" where not.
5. **`docs/LIMITATIONS.md`**: what would change the conclusions.

---

## Inland complement: Shawka Dam (appended 2026-10-02)

| | |
|---|---|
| **What** | A second, separately built site on **inland** water (the challenge covers inland and coastal water): Shawka Dam, Ras Al Khaimah, from two EnMAP L2A hyperspectral dates and a 28-observation Sentinel-2/Landsat baseline, integrated as an add-on without changing the coastal results |
| **Relevance** | Inland reservoir monitoring in the UAE, on a real dam, with Satellite 813 simulated on a second hyperspectral sensor (EnMAP), not only on Tanager |
| **Validity** | Carried over exactly: EnMAP's license is "proprietary" with redistribution terms not yet confirmed for public submission; and the anomaly/fingerprint results are based on a ~10-17 pixel background population, not a calibrated detector. The two-date test that did not confirm the first date is reported, and an integration review lists 15 flags with evidence (`docs/inland/REVIEW_FLAGS.md`) |
| **Number** | Persistent wet core 10 px of 84 inside the polygon; 2024 fingerprint classes BLOOM_LIKE 1, CDOM_LIKE 7, BACKGROUND_WATER 2; 7/28 temporal flags against 3.7–12.2 expected by chance; 196/205 simulated 813 bands with real EnMAP support |
| **Demo** | `/inland`: 3D wet-core map per date, EnMAP→813 band ladder, 3D deviation ribbon; `GET /api/inland/summary` |
