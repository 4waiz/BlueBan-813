# Limitations

Written so a reviewer does not have to find these themselves. Each entry states
what the limitation is, what it means for the product, and what would remove it.

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
