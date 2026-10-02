# Limitations

Written so a reviewer does not have to find these themselves. Each entry states
what the limitation is, what it means for the product, and what would remove it.

## UAE revamp (September 2026): what changed and what did not

* **Still true everywhere:** no public in-situ data (now checked for the UAE:
  none per-sample; EAD publishes station locations only), no real Satellite 813
  data, Sen2Cor is not a water processor, and the drift is wind-only.
* **New limitations of the UAE pipeline:**
  * *NDCI over very clear water.* When corrected red reflectance approaches zero
    NDCI becomes unstable (BB-AE-2023-001). <!--num:bloom-->Only 23 of 83 OLCI-referenced bloom-like candidates were confirmed, versus 300 of 353 sediment-like ones, and the size of the bloom-like NDCI change does not track the OLCI chlorophyll contrast (Spearman ρ -0.19).<!--/num:bloom-->
    The hue angle, MCI and the learned triage model are the mitigation; a
    water-specific atmospheric correction is the fix.
  * *The cross-sensor reference is a model product.* OLCI CHL_NN/TSM_NN are
    biased in optically shallow Gulf water, cannot see events smaller than a few
    300 m pixels, and end on 2026-02-23 on the Planetary Computer.
  * *Shallow-water agreement is weak evidence.* In the Arabian Gulf both sensors
    can respond to the same seabed or resuspension signal.
  * *Small, sediment-heavy label set.* <!--num:labels-->436 cross-sensor labels, 100 frozen for validation, dominated by sediment-like candidates in shallow Gulf water where agreement is weaker evidence. The candidate's AUPRC gain over the rule has a grouped bootstrap interval of [0.04, 0.48].<!--/num:labels--> More analyst and field labels
    are the remedy, which is what the loop is for.
  * *Screening coverage.* Arabian Gulf AOIs beyond Abu Dhabi North are still
    being screened (`docs/UAE_AOI_TOURNAMENT.md` lists them as pending).

The sections below were written for the Gulf of Annaba case and remain accurate
for it.

---

## 1. No in-situ measurement exists for this AOI

**What.** No field or laboratory water-quality data for the Gulf of Annaba was
obtainable. The Cockpit's "In-situ WQ records" card has no download mechanism
(`DATA_ACCESS_AUDIT.md` §2.5).

**Consequence.** BLUEBAN 813 reports **no** concentration anywhere: no
chlorophyll-a in mg/m³, no turbidity in NTU, no TSS in mg/L. Every index is
named as a proxy in code, in the API and in the interface. Confidence is
capped at 0.75 in `pipeline/risk.py` while no field sample exists.

**Removed by.** A handful of matched samples. The system already tells a field
team where to take them (`pipeline/sampling.py`), and a calibration hook exists
in `pipeline/indices.py` where each index declares its `input_quantity`.

---

## 2. Satellite 813 data is not used, and cannot be

**What.** 813 is incubation-only for this programme phase. The official
participant onboarding instructs teams not to design a PoC that depends on it.

**Consequence.** Every hyperspectral measurement here is Planet Tanager-1.
Everything labelled 813 is a simulation, marked as such in the UI, the API
(`/api/status` → `real_813_data_used: false`) and every provenance record.

**Also.** The published 813 specification is internally inconsistent: ~205
bands over ~400–1700 nm at ~5 nm sampling requires 261 bands, not 205. We
preserve the two hard numbers (range and count) and run the 5 nm / 261-band
interpretation as a sensitivity case. Both give the same conclusion.

**Not simulated.** 813's 20 m resolution. Tanager is 30 m, and upsampling would
manufacture detail that was never measured. Our 813 simulation is therefore
**pessimistic** about the real sensor by a factor of 2.25 in area.

---

## 3. Optical anomaly is not pollution, and a class is not a substance

**What.** `pipeline/anomaly.py` produces a spectral anomaly score.
`pipeline/fingerprint.py` produces a weighted hypothesis with its evidence.

**Consequence.** Neither identifies a chemical, a species or a toxin. Satellite
optics measure how water scatters and absorbs light. They cannot distinguish a
toxic bloom from a harmless one, and every classification output carries that
disclaimer in its payload.

Specifically: a chlorophyll-related index does not identify harmful algae, and
a phycocyanin-like feature at 620 nm is a **pigment** indicator, not a
confirmation of cyanobacteria — and phycocyanin-bearing cyanobacteria are
predominantly a freshwater and brackish phenomenon, which makes that class less
plausible in open Mediterranean water. The system reports it with low
confidence when the evidence is weak, and returns `UNKNOWN_ANOMALY` rather than
asserting a class below a 45 % score margin.

---

## 4. Bottom reflectance cannot be excluded nearshore from one scene

**What.** Anomaly rate falls monotonically with distance from shore: 20.3 % in
0–120 m, 11.0 % in 120–300 m, 5.3 % in 300–600 m, 0.5 % in 600–1200 m, 0.0 %
beyond. That is the signature of a nearshore process, and a bright shallow
bottom seen through clear water produces the same pattern as suspended matter.

**Consequence.** `pipeline/fingerprint.py` carries a `BOTTOM_INFLUENCED` class
and a per-event `bottom_influence_risk` that reduces confidence. For the primary
event (median 90 m from shore) the risk is high.

**What resolves it.** The temporal baseline, because bottom reflectance is
permanent and an event is episodic. That test was run and it pointed at a
persistent feature (`VALIDATION_REPORT.md` §5). A depth reading at the
`UNCERTAINTY_POINT` sample location would settle it directly.

---

## 5. The drift forecast is not a hydrodynamic model

**What.** `pipeline/forecast.py` advects particles with a wind-driven surface
current (3 % of the 10 m wind, deflected 15°) plus random-walk diffusion.

**Not included.** Tidal currents, geostrophic and density-driven circulation,
river discharge momentum, bathymetric steering, coastline-induced eddies,
Stokes drift, and any particle settling, resuspension or biological decay. In a
semi-enclosed gulf those terms can dominate.

**Consequence.** It is labelled a scenario estimate everywhere, including in the
API payload (`is_hydrodynamic_model: false`). It has **not** been validated
against observed plume motion: no repeat hyperspectral pass and no drifter data
were available, so no centroid-error statistic is reported.

**Also.** ERA5 is a ~25 km grid. Sampling the wind at the plume centroid, 90 m
from shore, resolves to a land cell 10 km inland reporting wind from 36° where
the marine cell reports 87°. We sample offshore and record why in the
provenance; but a coastal-resolution wind product would be better.

**Animation caveat.** The drift streamlines on the map move at a fixed screen
speed, because the true surface drift of a few centimetres per second is a
fraction of a pixel per second and would look frozen. Direction and coherence
are real; the speed shown by the motion is exaggerated and labelled as such,
with the true value printed numerically.

<!-- BEGIN ADDED:s5 -->
### Added 2026-10-02: a bounded drift estimate from 2019–2025 ERA5 winds

The scenario above used ERA5 wind for the event window only. To bound what the
same model implies, the full hourly ERA5 record at the same offshore sample
point (ERA5 cell 36.94 N, 7.71 E; 61,368 hours) was pushed through the same drift physics
(3 % of the 10 m wind, 15° deflection) from 10,220 start times, six hours apart.
Generated by `scripts/limitations_evidence.py` → `outputs/validation/limitations_evidence.json`.

| Horizon | Parcel displacement, median / P95 (km), all year | Same, ±45 days of 1 June | Wind-persistence error, median / P95 (km) | Diffusion σ (km) |
|---|---|---|---|---|
| +6 h | 1.3 / 3.8 | 1.2 / 3.4 | 0.6 / 1.5 | 0.46 |
| +12 h | 2.5 / 7.3 | 2.3 / 6.3 | 1.9 / 4.2 | 0.66 |
| +24 h | 4.4 / 13.7 | 3.9 / 11.2 | 4.3 / 9.9 | 0.93 |
| +48 h | 8.2 / 25.0 | 6.9 / 20.3 | 10.0 / 23.3 | 1.31 |

How to read it. **Displacement** is how far a surface parcel plausibly travels under
the observed range of winds, so it bounds the search radius a field team should
expect. **Wind-persistence error** is the distance between holding the start wind
constant and following the real hourly wind: an upper-end estimate of the
position error a wind forecast no better than persistence would add (an
operational forecast should do better). **This is a bounded estimate, not a
validated accuracy figure.** It covers wind variability only; tidal and
density-driven currents, waves and coastline effects are outside it and can be
larger in a semi-enclosed gulf. A drifter release or a repeat pass is still what
would turn it into a validated error statistic.

For context, the same computation at the Fujairah hero's offshore sample point
(ERA5 cell 25.13 N, 56.50 E), where winds are stronger (median 2.9 m/s against
2.2 m/s), gives a 24 h displacement of 4.4 / 14.8 km and a 24 h
wind-persistence error of 5.7 / 14.8 km (median / P95), under the same caveats.
<!-- END ADDED:s5 -->

---

## 6. Cross-sensor validation is not ground truth

**What.** The OLCI-target ablation compares against ESA's operational `CHL_NN`
and `TSM_NN`, which are model retrievals from a different instrument.

**Consequence.** Agreement with an operational product is not accuracy. And the
matchups carry a median **−25.5 h** offset, the closest usable OLCI acquisition;
coastal water changes materially in a day. This depresses all arms equally, so
it does not bias the comparison between them, but it caps the achievable R².

The detectability experiment's reference labels come from the full-spectrum RX
detector, which is a **full-spectrum instrument's judgment**, not a measurement.
It quantifies information loss at reduced spectral resolution; it does not
establish what the anomaly is.

---

## 7. Sen2Cor is not a water processor

**What.** Over water, simulated and real Sentinel-2 diverge sharply
(r = 0.51–0.83, NIR/SWIR slopes 3.5–3.7) while agreeing closely over land
(r = 0.93–0.97, slopes 0.91–1.04).

**Consequence.** Sentinel-2 Level-2A surface reflectance should not be treated
as a water product. Our multi-year baseline uses it for **relative** comparison
of the same zone against its own history, where a consistent bias cancels; it is
not used to state an absolute water-leaving reflectance.

**Removed by.** ACOLITE, C2RCC or POLYMER processing of the Sentinel-2 archive.

---

## 8. A single hyperspectral date

**What.** The Tanager open archive has 43 coastal-water scenes globally and four
in the MENA region, with no repeat pass over this AOI.

**Consequence.** No same-pixel hyperspectral change detection, no growth rate
measured from hyperspectral data, and no hyperspectral validation of the drift
forecast. Temporal work rests on Sentinel-2 and Sentinel-3.

<!-- BEGIN ADDED:s8 -->
### Added 2026-10-02: what a second date would take, and a proxy bound on day-to-day change

**Operational path to a second hyperspectral date.**
* *Tanager open archive.* The open STAC grew from 236 to 276 items in three days
  in September 2026; re-running the existing footprint check periodically costs
  nothing and may surface a repeat pass.
* *Tanager tasking.* A targeted repeat requires a commercial tasking request to
  Planet (paid; not placed by this project). The request would name the AOI,
  a revisit window and a cloud ceiling.
* *Other open or science-access hyperspectral missions.* EnMAP (DLR; free for
  registered science users, tasking by proposal), PRISMA (ASI; registered
  users) and EMIT (NASA; open, ISS orbit, opportunistic coverage) could supply a
  second date at 30–60 m. Each would need the simulator re-run on that sensor's
  band set.

**Proxy bound from the multi-year Sentinel-2 record (not hyperspectral validation).**
Across 352 usable Sentinel-2 acquisitions of the event zone (2020–2025), 221 pairs were at most
5 days apart. The zone's P95 turbidity proxy changed between them by a median of
0.078 (P90 0.297, P95 0.354), against a P5–P95 spread
over the whole record of 0.501. A few days can therefore move this proxy by
roughly 15 % (median) to 71 % (P95) of its full
multi-year range. That is the scale a second hyperspectral date would have to
beat before a difference could be read as change rather than ordinary variability.
Part of the upper tail is residual cloud, haze and glint that survive masking,
which a hyperspectral comparison would also have to control for. It is a
multispectral (Sentinel-2 only) proxy for the signal's variability, labelled as
such, not a hyperspectral measurement.
<!-- END ADDED:s8 -->

---

## 9. Assets are places, not intakes

**What.** `config/assets.geojson` holds five real, publicly mapped Gulf of
Annaba features with their OpenStreetMap element ids.

**Consequence.** A facility asset sits at the mapped **facility centroid**, not
at its water-intake structure, which is usually not public. Reported distances
are facility distances. No confidential infrastructure coordinate is included,
and none is estimated. No marine protected area is claimed because none could be
verified inside the AOI.

---

## 10. Scope of the geography

**What.** One 26.13 × 20.91 km AOI, one date, one water body.

**Consequence.** Nothing here demonstrates generalisation. Mediterranean coastal
water is optically different from the Arabian Gulf (hypersaline, shallow,
frequently dust-loaded) and from the Red Sea (oligotrophic, coral-influenced).
Thresholds are all local-percentile based specifically so the method ports
without re-tuning, but that is an argument, not a demonstration.

<!-- BEGIN ADDED:s10 -->
### Added 2026-10-02: a portability check on ten UAE AOIs

The September 2026 UAE build is a second geography reached with open data. Its
detector uses the same idea, a local seasonal-percentile test against the same
place's own history, with **one set of thresholds applied unchanged to every
AOI** (z ≥ 3, seasonal percentile ≥ 95, area ≥ 0.5 km²), on two very different seas:
the shallow, hypersaline Arabian Gulf and the deep Gulf of Oman. It is a related
method, not the identical Annaba pipeline (per-pixel instead of zone-level).
Without any re-tuning, Sentinel-3 OLCI confirmed the following share of the
candidates it could reference:

| AOI | Coast | Candidates | OLCI confirmed / referenced | Rate | Held-out triage AUPRC, learned vs rule |
|---|---|---|---|---|---|
| AE-AUH-LAGOON | Arabian Gulf | 282 | 10/10 | 100 % | not scorable (one class) |
| AE-AUH-NORTH | Arabian Gulf | 681 | 41/60 | 68 % | 0.98 vs 0.50 |
| AE-AUH-TAWEELAH | Arabian Gulf | 676 | 74/90 | 82 % | 1.00 vs 0.67 |
| AE-DXB-JEBELALI | Arabian Gulf | 391 | 46/58 | 79 % | 0.99 vs 0.62 |
| AE-SHJ-AJM | Arabian Gulf | 215 | 52/63 | 83 % | 0.94 vs 0.73 |
| AE-UAQ-RAK | Arabian Gulf | 370 | 61/76 | 80 % | 0.90 vs 0.83 |
| AE-FUJ | Gulf of Oman | 257 | 11/31 | 35 % | 0.56 vs 0.34 |
| AE-FUJ-DIBBA | Gulf of Oman | 57 | 12/19 | 63 % | 0.94 vs 0.86 |
| AE-SHJ-KALBA | Gulf of Oman | 57 | 11/14 | 79 % | 0.93 vs 0.76 |
| AE-SHJ-KHORFAKKAN | Gulf of Oman | 75 | 5/15 | 33 % | 1.00 vs 0.22 |

**Result, stated plainly: it ports, but unevenly.** Confirmation rates range from
33 % (AE-SHJ-KHORFAKKAN, 5 of 15) to 100 % (AE-AUH-LAGOON, 10 of 10).
Pooled by sea: 284 of 357 (80 %) on the Arabian Gulf against 39 of 79
(49 %) on the Gulf of Oman, so the clear, deep east coast, which includes the
hero AOI, carries the heavier false-alarm burden. Sediment-like candidates are mostly confirmed
(300 of 353); bloom-like candidates mostly are not
(23 of 83), because NDCI is unstable over very clear water. In the
shallow Gulf both sensors can respond to the seabed, so agreement there is weaker
evidence. The thresholds needed no re-tuning to run, but the false-alarm burden
does depend on water type, which is what the learning loop is for: trained
without the AOI it is scored on, the learned triage beats the fixed rule on
9 of 9 scorable AOIs (last column).
OLCI is a model product, not in-situ truth; a Mediterranean or Red Sea repeat
remains untested.
<!-- END ADDED:s10 -->

---

## 11. Engineering limitations

| Limitation | Detail |
|---|---|
| API is unauthenticated | Read-only apart from asset registration. Needs auth, rate limiting and audit logging before exposure outside a trusted network. |
| Static deployment has no write path | The hosted demo stores a new asset in the browser only, and says so. |
| The RX background is assumed stationary | One offshore population for the whole scene. A large AOI with distinct water masses would need several. |
| The chi-squared null is violated | Documented, and the empirical threshold is used instead. |
| Cloud masking is the product's own | `beta_cloud_mask` is a beta product per its own naming. Cirrus over dark water is a known weak point for any optical sensor. |
| No orbital tasking | The system consumes archives. Operational use would need a tasking request path for 813. |

---

## What we deliberately did not do

* We did not pick the AOI that flattered the story. The UAE scene was preferred
  on strategic grounds and rejected on 51 % cloud.
* We did not report the random-split numbers, which would have shown a large
  hyperspectral advantage.
* We did not drop the two experiments that found no advantage.
* We did not suppress the temporal result that downgraded our own headline
  event from HIGH_PRIORITY.
* We did not convert an index into a concentration without calibration data.

---

## Inland complement: Shawka Dam (appended 2026-10-02)

The inland module ([`docs/inland/`](inland/README.md)) has its own limitations, stated
in its documents and summarised here in the same form: what it is, what it means,
what would remove it. Two caveats are carried over exactly:

* **Licence.** EnMAP's license is "proprietary" with redistribution terms not yet confirmed for public submission. *Means:* per-pixel EnMAP reflectance layers and spectra are
  kept out of the public repository and site (`data/inland/restricted/`,
  gitignored); only derived masks, scores and counts are published, with
  attribution. *Removed by:* written confirmation of the redistribution and display
  terms from DLR.
* **Detector size.** the anomaly/fingerprint results are based on a ~10-17 pixel background population, not a calibrated detector. *Means:* RX scores and fingerprint classes on the wet
  core are descriptive. The test pixels are also part of the background they are
  scored against, so the 0 RX events on both dates is structural, not evidence of
  normal water. *Removed by:* a larger water body or more dates, and a background
  population disjoint from the test pixels.

Further limitations:

* **Two dates, and the second does not confirm the first.** With unchanged
  thresholds the 2022-09-08 mask has 10 px and the 2024-04-24 mask 4 px, with no overlap; the
  persistent core (10 px) rests on darkness on both dates, and a real MNDWI finds
  0 px. *Removed by:* a third EnMAP date. The open archive already lists
  candidates whose footprints contain the polygon (2024-04-20 at 4 % cloud,
  2023-12-30 and 2024-11-22 at 7 %).
* **Temporal flags are within chance.** 7 of 28 observations flag at |z| > 1.5, and pure
  noise would flag 3.7–12.2 depending on how correlated the four indices are. The
  cross-sensor Sep–Oct 2025 cluster is the readable part. *Removed by:* a longer
  baseline (Sentinel-2 since 2017) and a seasonal climatology.
* **Land correction over water.** EnMAP L2A here is Land_Mode surface reflectance,
  not a water-leaving product. *Removed by:* EnMAP's water mode or an aquatic
  atmospheric correction.
* **A drying target.** The most recent imagery (Sep–Oct 2025) shows 0.2–1.0 % of
  the AOI wet; the next acquisition may have no water to analyse. Sentinel-3 OLCI
  cannot help (the pool is sub-pixel at 300 m).
* **Band table.** The per-band wavelengths used for both dates match the
  2024-04-24 item only (REVIEW_FLAGS F2). *Removed by:* re-running the 2022-09-08
  derivations with that item's own table, which needs the raw scene from the module owner.
