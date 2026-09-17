# Satellite 813: product notes and the sensor simulator

This document states exactly what we know about Satellite 813, what we do not,
what we built instead, and why that is a stronger contribution than pretending
otherwise.

---

## 1. What 813 data we hold: none

Stated plainly so there is no ambiguity anywhere in this submission:

> **BLUEBAN 813 contains zero Satellite 813 pixels.** No 813 scene was
> available to us. Every hyperspectral measurement in this PoC is real Planet
> Tanager-1 data. Everything labelled "813" in this repository is a clearly
> marked **simulation** derived from that Tanager data.

This is not a shortcoming we are conceding; it is the programme's own
instruction. From the authenticated participant onboarding guide, section 07:

> **Satellite 813 & MBZ-SAT — INCUBATION ONLY, UPON AVAILABILITY.** May be
> provided to selected teams during incubation if available. *Do not assume
> coverage of a specific AOI, date, or product level, and do not design a PoC
> that depends on this data.*

And section 04, for the phase we are in:

> **PHASE 2 — Proof of Concept development:** … *No guaranteed Satellite 813 or
> MBZ-SAT data.*

The Cockpit card "813 Aquatic Hyperspectral · GeoTIFF · on-demand · Optimized
bands for water-leaving radiance" carries no download control, no request form
and no endpoint; DOM inspection returns three static text nodes. See
`DATA_ACCESS_AUDIT.md` §1.

---

## 2. On "water-leaving radiance"

The Cockpit describes the 813 aquatic product as *"Optimized bands for
water-leaving radiance"*. We take that seriously rather than assuming it is a
reflectance product, because the distinction changes the mathematics.

| Quantity | Symbol | Units | Notes |
|---|---|---|---|
| Water-leaving radiance | `Lw` | W · m⁻² · sr⁻¹ · µm⁻¹ | Directional, illumination-dependent |
| Remote-sensing reflectance | `Rrs = Lw / Ed` | sr⁻¹ | Normalised by downwelling irradiance |
| Surface reflectance | `ρ = π · Lu / Ed` | unitless | What Tanager ships |

The conversion `Rrs = Lw / Ed(0⁺)` requires the downwelling irradiance at the
surface, which depends on solar geometry, atmospheric transmittance, aerosol
loading and water vapour. **You cannot convert Lw to Rrs without Ed**, and
applying an Rrs-derived index directly to an Lw product produces a number that
varies with the sun angle rather than with the water.

Since we hold no 813 product, no conversion is performed and none is assumed.
Our pipeline operates on Tanager **surface reflectance**, confirmed from the
file's own `Unit` attribute (`"Unitless"`) and consistent with the asset key
`ortho_sr_hdf5`. When real 813 data arrives, `pipeline/satellite813.py` has a
single documented entry point where the input quantity is declared, and the
index layer already carries an `input_quantity` field per index
(`pipeline/indices.py`) so a mismatch fails loudly rather than silently.

---

## 3. Published 813 specification

The only official specification available to participants, from the public data
page (`spaceacademy-hackathons.space.gov.ae/data`):

| Property | Published value |
|---|---|
| Bands | ~205 |
| Spectral range | ~400–1700 nm |
| Spectral sampling | ~5 nm |
| Spatial resolution | **20 m** |
| Revisit | listed as *not available* |

### A note on internal consistency

These three numbers cannot all hold simultaneously. 400–1700 nm at 5 nm spacing
requires **261** contiguous bands, not 205. The real instrument therefore either
does not sample the full range contiguously, samples part of it more coarsely,
or the figures are rounded from a design that differs in detail.

We resolve this transparently rather than silently picking one:

* **Primary configuration** keeps the two hard published numbers — the range
  (400–1700 nm) and the band count (205) — giving an implied 6.37 nm spacing.
* **Sensitivity configuration** keeps the published *sampling* (5 nm) across the
  published range, giving 261 bands.

Both are run in the ablation (`experiments/hyperspectral_ablation.py`). If the
conclusion changed between them, the conclusion would be an artefact of our
assumption rather than a property of the sensor. Reporting both is the only
honest way to use an inconsistent specification.

---

## 4. The simulator

`pipeline/satellite813.py:simulate_813`

### What it does

Takes the real Tanager cube (368 product-good bands, 376–2499 nm, 5 nm sampling,
median FWHM 6.05 nm) and convolves it onto the 813 band set using Gaussian
spectral response functions:

```
sigma_i   = FWHM_i / (2 * sqrt(2 * ln 2))
W[i, j]   = exp(-0.5 * ((c_i - s_j) / sigma_i)^2),  zeroed beyond 3 sigma
W[i, :]  /= sum(W[i, :])
R_813[i]  = sum_j W[i, j] * R_tanager[j]
```

Gaussian SRF convolution is the standard method for cross-sensor band synthesis
and is what ISOFIT/HyTools and ESA sensor-intercomparison workflows use.

### What it deliberately does not do

**It does not resample to 20 m.** Tanager is 30 m; 813 is specified at 20 m.
Upsampling 30 m imagery to 20 m would manufacture spatial detail that was never
measured, and would make the simulated product look better than the real
instrument could justify. The simulator therefore reproduces 813's **spectral**
configuration only, at Tanager's native 30 m, and the spatial difference is
carried as a stated limitation rather than faked.

The practical consequence is that our 813 simulation is **pessimistic** about
813's real capability: a genuine 813 at 20 m would resolve plume structure
2.25× finer in area than what we show.

### Bad-band honesty

The Tanager product flags 58 of its 426 bands as bad, in two runs:

| Run | Wavelengths | Bands |
|---|---|---|
| 1 | 1342.41 – 1437.55 nm | 20 |
| 2 | 1782.58 – 1967.21 nm | 38 |

These are atmospheric water-vapour absorption windows. Both fall inside 813's
400–1700 nm range (the first entirely, the second partially), so simulated 813
bands there have no valid source data.

`resample_spectra` enforces a `min_support` rule: a target band is returned only
if at least 50 % of its Gaussian weight lands on *finite* source bands.
Simulated 813 bands straddling a Tanager gap come back as NaN rather than being
interpolated across the gap. **Interpolating there would fabricate exactly the
region where the atmosphere destroyed the signal.**

> Note the direction of this decision. The tutorial notebooks hardcode the bad
> windows as 1350–1450 nm and 1800–1950 nm. The product's own `good_wavelengths`
> attribute gives 1342.41–1437.55 and 1782.58–1967.21 for this scene — different
> at all four edges. We use the product's flags. Copying another sensor's
> bad-band rule onto a different instrument is precisely the kind of unexamined
> assumption that makes hyperspectral results unreproducible.

---

## 5. Why simulation is the stronger answer

The question a space agency actually has about a mission it is flying is not
"can you draw a map with it". It is:

> **What will this instrument buy us that we cannot already get from Sentinel-2
> and Sentinel-3, and by how much?**

That question is answerable *before launch*, and answering it is more useful
than another map. Our ablation
(`experiments/hyperspectral_ablation.py`) sets it up as a controlled experiment:

```
            Real Tanager cube over the Gulf of Annaba
                    (same pixels, same water,
                     same atmosphere, same instant)
                              |
             +----------------+----------------+
             |                                 |
   convolve to Sentinel-2 MSI         convolve to 813 spec
        11 broad bands                  205 narrow bands
             |                                 |
             +----------------+----------------+
                              |
                  same target, same folds,
                  same spatially-separated split
                              |
                        measured lift
```

Because both feature sets come from the *same pixels*, the comparison has no
confounds: no atmospheric difference, no time difference, no geolocation error,
no illumination difference. Any measured difference is attributable to spectral
configuration alone. Comparing a real Sentinel-2 scene against a real
hyperspectral scene could never isolate the variable that cleanly.

This makes 813 technically central to the PoC — as the **subject of a mission
utility study** — without a single fabricated pixel.

---

## 6. Path to real 813 data

The code is built so that swapping the simulator for real data is a small,
contained change:

| Step | Where | Status |
|---|---|---|
| Declare input quantity and units | `pipeline/indices.py` `IndexSpec.input_quantity` | Ready |
| Read the product | new `Satellite813Scene` alongside `TanagerScene` | Interface defined |
| Band table | replace `spec_813()` synthetic centres with the real table | One function |
| Lw → Rrs conversion if required | new, needs `Ed`; raises rather than guessing | Explicitly not implemented |
| Re-run ablation | `experiments/hyperspectral_ablation.py --sensor real813` | Ready |
| Provenance | `SourceRecord(satellite="Satellite 813", ...)` | Ready |

Everything that reaches the interface is labelled **813 (SIMULATED)** and the
Evidence drawer shows the simulation's own provenance record — the source
Tanager scene, the SRF method, and the min-support rule. A judge clicking
through never has to wonder which pixels are real.
