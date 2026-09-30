# Judging Matrix

**BLUEBAN 813** · Team Kanban · updated 30 September 2026 (UAE revamp)

The official criteria are the five in the challenge README: **Impact, Creativity,
Validity, Relevance, Presentation**. Each row maps a criterion to what addresses
it, the evidence a judge can check, the number, and where it appears. Every
figure is produced by the pipeline (`outputs/`) and shown by the app; none is
typed into the interface.

---

## 1. Impact

| | |
|---|---|
| **What** | Incidents that reach a decision: verification queue, field plan, alerts, exposure to desalination and power plants, and a model that improves from every decision |
| **Evidence** | BB-AE-2024-001 off Fujairah: 2.39 km² of discoloured water, ~11–22 km from the Port of Fujairah, Kalba power plant and Fujairah F2 desalination plant; five-point sampling plan with a mandatory background control |
| **Number** | On the frozen validation set the learned triage candidate reaches AUPRC 0.86 vs 0.51 for the rule it would replace (grouped bootstrap interval reported, promotion gated) |
| **Demo** | Judge Mode steps 3, 7–10; Incident Control; Field Ops |

The UAE draws most of its drinking water from desalination on two very different
seas; a false alarm costs a boat dispatch and a missed bloom can shut an intake.
The loop targets exactly that trade-off.

## 2. Creativity

| | |
|---|---|
| **What** | (i) Every pixel judged against its **own** same-season history, not its neighbours. (ii) An independent satellite as a same-morning cross-check and weak teacher. (iii) A governed learning loop where production is untouched until a candidate passes a frozen-validation gate and a named human approves. (iv) A measured, not assumed, answer to "what does 813 add?" |
| **Evidence** | `pipeline/detect.py`, `scripts/build_labels.py`, `pipeline/learning.py` + `apps/web/lib/learning.ts` (parity 1e-7), the 813 ablation |
| **Demo** | Judge Mode steps 4, 5, 9, 10; Satellite View (real orbits, real sun, UAE passes) |

## 3. Validity

| | |
|---|---|
| **What** | Honest data policy (no concentration from an uncalibrated index; OLCI is a reference, not truth; 813 is simulated), grouped/spatial validation, negative controls |
| **Evidence** | Validation screen A–F; `docs/VALIDATION_REPORT.md` (generated); `docs/LIMITATIONS.md`; 139 OLCI references, Spearman ρ 0.38 (sediment, p = 2e-4) and 0.29 (bloom, p = 0.04) between the S2 change and the OLCI contrast |
| **Negative controls** | Annaba (RX 99.7th percentile but 6.6th seasonal percentile → stood down) and BB-AE-2023-001 (NDCI spike over unchanged blue water; OLCI ×1.1 → rejectable) |
| **What we do not claim** | "HAB confirmed", species, toxins, concentrations, oil from SAR darkness, pollution sources from trajectories |

## 4. Relevance

| | |
|---|---|
| **What** | Built for the 813 Challenge's water-quality track and the UAE coast; Satellite 813's aquatic band set drives the ablation and the spectral lab |
| **Evidence** | 10 UAE AOIs on both coasts; UAE AOI tournament generated from data (`docs/UAE_AOI_TOURNAMENT.md`); 813 simulated from real Tanager hyperspectral pixels, labelled SIMULATED everywhere; at the decision boundary the 813 band set cut false alarms 159 → 84 (−47 %) at matched recall |
| **Demo** | Spectral Lab ("What did 813 add?"), Judge Mode step 5 |

## 5. Presentation

| | |
|---|---|
| **What** | One-click Judge Mode (11 steps, 2–3 min, real actions), mission-control UI, full-screen 3D Satellite View, provenance on every result ("WHY AM I SEEING THIS?") |
| **Evidence** | Live at BlueBan813.kanbanstudios.ae (blueban813.pages.dev); research paper at 4waiz.github.io/BlueBan-813 |

---

## Where a sceptical reviewer should look, in order

1. **Validation → C and E**: the rule has no skill against the cross-sensor reference; the candidate does, across held-out AOIs.
2. **Validation → F** and **BB-AE-2023-001**: the system shows its own false positive.
3. **Data → Source register**: every input, its licence and whether it is used.
4. **Spectral Lab → What did 813 add?**: gains where measured, "no gain" and "not demonstrated" where not.
5. **`docs/LIMITATIONS.md`**: what would change the conclusions.
