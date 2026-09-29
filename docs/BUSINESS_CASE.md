# Business Case

**BLUEBAN 813** - Water Threat Intelligence for the Arab region
Team Kanban · Arab Youth Space Hackathon 2026, 813 Challenge

---

## 1. The problem, as a buyer experiences it

A coastal water authority is responsible for bathing-water compliance, for the
source water feeding intakes, and for answering a minister within hours when a
discolouration appears on a public beach.

The tools available today are:

| Tool | What it gives | What it costs |
|---|---|---|
| Scheduled boat sampling | A laboratory-grade number, at one point, on a fixed date | A crewed vessel per run, and the answer arrives days later |
| Public complaints | A location, after the fact | Reputational damage already done |
| Free satellite viewers | A picture | No decision: no baseline, no trajectory, no exposure, no sampling guidance |

The gap is not imagery. Sentinel-2 and Sentinel-3 imagery is already free. The
gap is that nobody converts it into **"send the boat here, today, because this
is unusual for this place and it is moving toward that intake."**

---

## 2. What BLUEBAN 813 sells

Not a map. A decision, with its reasoning attached:

1. This region of water is spectrally anomalous, at a calibrated false-alarm
   rate.
2. Its optical signature is most consistent with *X*, and here is the evidence.
3. Against 5 years of history for this exact place and season, it sits at the
   *n*-th percentile — so it either is or is not an event.
4. Under the observed wind it moves this way, and reaches these assets in *n*
   hours.
5. Sample at these four to six points, for these analytes, and here is what each
   one resolves.
6. Every number above traces to a scene id, a licence and an algorithm version.

Step 3 is the differentiator, and the one that saves money. A spatial detector
will flag a permanently turbid harbour every clear day. Without a local
baseline, an operator either ignores the system or wastes vessel time on
features of their own coastline.

---

## 3. Who pays, and for what

### Primary customer: national or regional water / environmental authority

**Algeria (the demonstration AOI).** The Agence Nationale des Ressources
Hydrauliques and the Commissariat National du Littoral hold coastal
water-quality and bathing-water mandates. Algeria has also commissioned large
seawater desalination capacity, which makes source-water screening a supply
issue and not only an environmental one.

**UAE and the wider Gulf.** Environment agencies at emirate and federal level
hold coastal monitoring mandates over water bodies that are hypersaline,
shallow and desalination-dependent, where a harmful bloom is a potable-supply
risk rather than an amenity problem.

### The budget line it comes from

Monitoring programmes already pay for scheduled sampling campaigns. BLUEBAN 813
does not replace the laboratory; it **re-targets** the same sampling budget and
adds a screening layer between campaigns. The pitch to a programme manager is:
same number of samples, taken where they resolve something.

### Secondary customers

| Segment | Why they buy | Entry point |
|---|---|---|
| Industrial water users (thermal power, refining) | Suspended load and biofouling drive intake screen and heat-exchanger maintenance. The demonstration AOI contains a real 72 MW plant 0.93 km from the detected region. | Single-asset monitoring |
| Desalination operators | Source-water quality drives pre-treatment load, membrane fouling and, at the extreme, a shutdown | Single-asset monitoring |
| Ports and dredging contractors | Turbidity compliance during and after works | Project-duration subscription |
| Aquaculture | Bloom and oxygen risk to immovable stock | Per-farm subscription |
| Tourism authorities and municipalities | Bathing-water compliance and beach-season reputation | Seasonal AOI subscription |
| Marine protected area managers | Sedimentation and eutrophication pressure | Annual AOI subscription |

---

## 4. Commercial model

| Line | Unit | What it includes |
|---|---|---|
| **AOI monitoring subscription** | per AOI, per year | Continuous Sentinel-3 and Sentinel-2 screening, the local baseline maintained, event detection, the operator interface |
| **Critical-asset monitoring** | per asset, per year | Exposure scoring, ETA, threshold alerting to email/SMS/webhook |
| **Hyperspectral forensics** | per tasking | Deep spectral characterisation of a specific event, 813 or another hyperspectral source |
| **API access** | per seat or per call | Integration into an existing SCADA, GIS or alerting stack |
| **Event response report** | per event | A signed, provenance-complete document suitable for a regulator or an insurer |
| **Deployment and integration** | one-off | Historical baseline build, asset onboarding, operator training |

The subscription carries the fixed cost, because the multi-year baseline is the
asset that takes time to build and is what makes a new AOI hard to copy.

### Why the unit economics work

Every input the PoC uses is open and unauthenticated: Sentinel-2, Sentinel-3,
Landsat, ERA5, Tanager's open archive. Marginal cost per AOI is compute and
storage. Heavy processing happens offline and the interface is served as static
files — the hosted demonstration runs at essentially zero infrastructure cost.

Hyperspectral tasking is the one genuinely variable cost, which is why it is
priced per event rather than folded into the subscription.

---

## 5. What replaces what

| Today | With BLUEBAN 813 |
|---|---|
| Fixed sampling calendar | The calendar stays; between campaigns, screening decides whether an extra run is justified |
| Sample where it has always been sampled | Sample where the evidence is, including a mandatory same-day control |
| "Is this normal?" answered from memory | Answered from 428 observations at that location for that season |
| Discolouration reported by the public | Detected on the next clear overpass |
| A conclusion in an email | A conclusion with a scene id, a checksum and an algorithm version |

Deliberately **not** replaced: the laboratory. The product's position is that
satellite screening decides *where to test*, and the closing line of the demo
says so.

---

## 6. Regional impact and SDG alignment

Stated narrowly, because a broad SDG list is not an argument.

**SDG 6 - Clean water and sanitation.** Targets 6.3 (water quality, reducing
pollution) and 6.5 (integrated water resources management). The product measures
coastal water quality against a local historical baseline and directs the
physical testing that regulation depends on.

**SDG 14 - Life below water.** Target 14.1 (marine pollution, including
nutrient and land-based sources). Event detection with an origin-region capacity
supports exactly this reporting obligation.

**SDG 9 - Industry, innovation and infrastructure.** Only insofar as it is
literal here: protecting operating water intakes against a measurable
source-water risk.

**Coastal resilience.** The Arab region's coastline carries its potable supply,
its industrial cooling and much of its food. Optical screening at 20-30 m makes
episodic pressure on that coastline visible between sampling campaigns, and does
so with the same method from the Maghreb to the Gulf.

---

## 7. How it scales across the region

The technical reason it ports is that **no threshold in the system is
absolute**. Severity is driven by the local seasonal percentile, the anomaly
background is the local offshore water population, and the detection threshold
is calibrated empirically per scene. A new AOI needs a baseline built, not a
model re-tuned.

| Stage | What is needed | Timeline |
|---|---|---|
| New AOI onboarded | Build the multi-year Sentinel-2 baseline | ~13 minutes of compute for 5 years |
| New asset onboarded | A pin, a GeoJSON or a CSV from the operator | Immediate |
| New country | The same open data; only the asset register is local | Days |
| Hyperspectral upgrade | Swap the simulator for a real 813 band table | One function; see `813_PRODUCT_NOTES.md` §6 |

---

## 8. Why the 813 mission strengthens the business, and vice versa

The measured result is that 813-class spectral resolution **halves the
false-alarm rate at the operational decision boundary** (159 to 84 false
positives at matched recall, 95 % CI on ΔF1 [0.0050, 0.0080]). It does **not**
help with gross plume detection, where Sentinel-2 already saturates.

That is a precise commercial statement: the hyperspectral layer is worth paying
for on the marginal, early-stage events, which are the ones worth catching, and
not on the obvious ones. It supports a two-tier product - free-data screening as
the subscription, hyperspectral forensics as a per-event upsell - and it gives
the mission owner a quantified answer to "what will operators actually use this
for", before launch.

The system is 813-ready by construction: the simulator is a single documented
function boundary, and the input quantity and units are declared per index so a
real product with different units fails loudly rather than silently.

---

## 9. What we are not claiming

* **No revenue projection.** We have no signed pilot and no price discovery, and
  a fabricated figure would be worth less than saying so.
* **No accuracy claim in physical units.** With no in-situ data for this AOI, we
  report no mg/m³ and no NTU. See `LIMITATIONS.md` §1.
* **No regulatory status.** Nothing here is validated for compliance reporting.
  The event-report line item is a deliverable format, not an accredited method.
* **No 813 data.** The commercial roadmap assumes incubation access; the PoC
  does not depend on it.

---

## 10. The first pilot we would ask for

One AOI, one operator, one season.

* One 25-50 km coastal stretch containing at least one water intake.
* The operator's own asset register.
* Their existing sampling calendar for the season, unchanged.
* Access to the laboratory results from those scheduled campaigns.

The measurable outcome is the one thing the PoC cannot self-report: whether
BLUEBAN 813's screening percentile agrees with their laboratory record, and
whether the sampling planner's suggested locations returned more informative
results than the fixed stations. That is the experiment that turns this from a
validated method into a validated product.
