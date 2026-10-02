"""Optical class hypotheses over the inland wet core — REDUCED SCOPE.

Mirrors the shape of DesalGuard-main's `pipeline/fingerprint.py` (a
CLASSES registry, an Evidence/Fingerprint dataclass pair, a weighted-
hypothesis scorer, a mandatory non-diagnostic disclaimer) but is NOT a
full port, for one concrete, structural reason stated plainly rather than
worked around silently:

--------------------------------------------------------------------------
WHY THIS IS REDUCED SCOPE, NOT A FULL PORT — THE WAVELENGTH-TABLE BLOCKER
--------------------------------------------------------------------------
DesalGuard's `fingerprint_spectrum()` extracts evidence by looking up
reflectance at NAMED wavelengths (443, 490, 560, 620, 665, 675, 685, 705,
740, 865 nm) via `_at(wl, spec, nm)` — nearest-band lookup against a real
per-band wavelength array. Neither EnMAP GeoTIFF in this project carries
per-band wavelength metadata (verified at the raw TIFF-tag level; see
docs/WATER_MASK.md section 2 and config/project.yaml
`enmap.spec.band_characterisation_table`), and the product's own
METADATA.XML section that would supply it was never fully captured. There
is, right now, no way to say "this is the reflectance at 620 nm" for
either scene with any precision.

This is a real, structural blocker for anything that needs an EXACT named
wavelength — not a data-quality nuisance that a workaround papers over. So
rather than fake a wavelength assignment (which would silently manufacture
false precision — e.g. guessing which of 224 bands is "620 nm" by linear
interpolation across a range whose own band count, 224, doesn't match
DLR's nominal 222-band spec; see docs/DATA_ACCESS_AUDIT.md section 2.1)
this module works ONLY from the wavelength-ORDER-based band GROUPS already
established and validated in `pipeline/water_mask.py` /
`pipeline/anomaly.py` (short/mid/long or the finer N-group split), and
explicitly REFUSES to compute any class whose optical definition
structurally requires a narrow, precisely-located band. That is not a
softer version of the same evidence — it is a smaller set of classes,
honestly labeled as smaller, with the excluded ones named and explained
rather than silently dropped.

UPDATE (2026-09-19): the wavelength-table blocker above is RESOLVED — a
real per-band table was obtained (see
`data/metadata/enmap_band_characterisation.json` and
`docs/WATER_MASK.md` section 13) and CYANO_LIKE is now computable. It is
the one class in this registry that genuinely needed exact wavelengths (a
narrow phycocyanin absorption feature at ~620 nm against two shoulders);
the others (SEDIMENT_LIKE, BLOOM_LIKE, CDOM_LIKE, SURFACE_FILM_LIKE)
remain group-based by choice, not by remaining necessity — their optical
definitions were already expressible at group-level resolution and
changing them now would just be re-deriving evidence that already works,
not fixing a gap. `local_band_depth()` below reuses DesalGuard-main's own
continuum-removal formula from `pipeline/spectral.py`
(Clark & Roush 1984 -- a general, non-coastal-specific method, copied for
the same reason `spec_813()` was in `pipeline/satellite813.py`) with the
SAME 600/620/650 nm phycocyanin shoulder windows DesalGuard cites to
Simis et al. (2005) -- those are literature/physical constants, not
coastal-tuned business logic, so they are reused as-is. What is NOT reused
is DesalGuard's absolute threshold (`d620 > 0.03`) -- that was presumably
fit to his coastal case. Here, CYANO_LIKE support is judged the same way
every other class in this module is: relative to THIS AOI's own observed
background population (a z-score against the background's own d620
distribution), not a borrowed absolute cutoff. See `fingerprint_pixel()`'s
docstring and `docs/ANOMALY_AND_FINGERPRINT.md` section 3 (updated) for
the full result.

--------------------------------------------------------------------------
Classes carried over (computable from band-GROUP evidence only)
--------------------------------------------------------------------------
BACKGROUND_WATER, SEDIMENT_LIKE, BLOOM_LIKE (red-edge-REGION elevation, not
a chlorophyll-a 675 nm retrieval), CDOM_LIKE (blue-REGION depression),
SURFACE_FILM_LIKE (broadband brightening without a matching shape change),
UNKNOWN_ANOMALY.

Classes using real named bands (now possible, see UPDATE above)
--------------------------------------------------------------------------
CYANO_LIKE (phycocyanin, ~620 nm) -- computed only when a caller supplies
the optional real-spectrum arguments to `fingerprint_pixel()`; falls back
to not-computed (scored 0) if they are omitted, so existing group-only
call sites keep working unchanged.

Classes still explicitly NOT computed here
--------------------------------------------------------------------------
BOTTOM_INFLUENCED (DesalGuard's version needs a shallow-water caveat keyed
to a specific NIR band + a distance-from-shore raster; the distance metric
itself is not built for this AOI's ~10-30 px blob, which has no clear
onshore/offshore gradient to measure against -- a real band alone doesn't
fix this one). Appears in `CLASSES` below, marked `computable: False`,
with a `reason` field, so a caller iterating the registry sees it named
rather than silently missing.

Every classification carries DesalGuard's own disclaimer, unchanged: this
is a weighted OPTICAL hypothesis from broadband reflectance, never a
confirmed chemical, biological, or toxicological identification. Field
sampling and laboratory analysis are required for any of that.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


CLASSES = {
    "BACKGROUND_WATER": {
        "label": "Background water",
        "optical_definition": (
            "Broadband-dark, spectrally unremarkable relative to this AOI's "
            "own observed water population (low RX score) -- the default "
            "hypothesis, not a positive detection of anything."
        ),
        "reference": "n/a -- baseline class",
        "computable": True,
    },
    "SEDIMENT_LIKE": {
        "label": "Sediment / turbidity-like",
        "optical_definition": (
            "Elevated broadband reflectance across ALL band groups relative "
            "to the AOI's own background water population, without a "
            "pronounced red-edge-region-specific peak -- suspended mineral "
            "sediment scatters broadly across the visible-NIR range rather "
            "than absorbing/re-emitting at a specific spectral feature. "
            "General limnology/ocean-colour principle (broadband brightening "
            "from suspended particulates), not a coastal-specific one."
        ),
        "reference": (
            "General turbidity/TSS remote-sensing principle (e.g. Nechad et "
            "al. 2010, broadband reflectance increases with suspended "
            "sediment concentration); not fit to this AOI's own pixels -- "
            "see 'Genuinely tuned vs. placeholder' below."
        ),
        "computable": True,
    },
    "BLOOM_LIKE": {
        "label": "Algal-bloom-like (broad red-edge-region elevation)",
        "optical_definition": (
            "Elevated reflectance in the longer-wavelength visible / red-edge "
            "-REGION band group(s) relative to the shorter-wavelength group, "
            "beyond what the AOI's background water shows -- a coarse proxy "
            "for the chlorophyll-driven red-edge reflectance shoulder that "
            "underlies most optical bloom detection. NOT a chlorophyll-a "
            "concentration retrieval (that needs a narrow 665/705 nm ratio, "
            "unavailable here -- see module docstring)."
        ),
        "reference": (
            "General red-edge chlorophyll-reflectance principle (e.g. Gitelson "
            "et al., red-edge NIR reflectance peak in chlorophyll-rich water); "
            "coarse group-level proxy, not the cited papers' exact band ratio."
        ),
        "computable": True,
    },
    "CDOM_LIKE": {
        "label": "CDOM / dissolved-organic-matter-like",
        "optical_definition": (
            "Depressed reflectance in the shortest-wavelength band group "
            "relative to the AOI's background water, without the broadband "
            "brightening SEDIMENT_LIKE shows -- coloured dissolved organic "
            "matter absorbs strongly toward blue wavelengths. Coarse "
            "group-level proxy for the standard blue-depression CDOM signal."
        ),
        "reference": (
            "General CDOM blue-absorption principle (e.g. Kirk, Light and "
            "Photosynthesis in Aquatic Ecosystems); group-level proxy only."
        ),
        "computable": True,
    },
    "SURFACE_FILM_LIKE": {
        "label": "Surface film-like",
        "optical_definition": (
            "Broadband reflectance elevated relative to background water "
            "(similar magnitude change to SEDIMENT_LIKE) but with a LOW "
            "spectral angle (SAM) to the background mean spectrum -- i.e. "
            "brighter but a similar SHAPE, consistent with a thin film "
            "increasing overall reflectance without adding the "
            "spectrally-structured signal sediment or algae would."
        ),
        "reference": (
            "General principle that thin surface films (oil sheen, scum) "
            "tend to brighten broadband reflectance with comparatively "
            "little shape change vs. a suspended-particulate signal; "
            "heuristic, not fit to a labeled film example (none exists for "
            "this AOI)."
        ),
        "computable": True,
    },
    "CYANO_LIKE": {
        "label": "Cyanobacteria-like (phycocyanin)",
        "optical_definition": (
            "Local absorption-feature depth at the real EnMAP band nearest "
            "620 nm, against a continuum drawn between the real bands "
            "nearest 600 nm and 650 nm (Clark & Roush 1984 local band-depth "
            "formulation, same as DesalGuard-main's local_band_depth()), "
            "compared to this AOI's OWN background population's depth at "
            "the same feature -- excess depth beyond the background is the "
            "evidence, not an absolute depth cutoff."
        ),
        "reference": "Simis et al. 2005 (phycocyanin retrieval, inland waters) -- per DesalGuard-main's own citation; shoulder wavelengths (600/620/650 nm) reused as literature/physical constants, not DesalGuard's absolute threshold.",
        "computable": True,
        "note": (
            "Newly computable as of 2026-09-19 -- the wavelength-table "
            "blocker that excluded this class is resolved. See module "
            "docstring UPDATE and fingerprint_pixel()'s docstring for how "
            "to pass the real-spectrum arguments this class needs (it is "
            "the only class in this registry that does)."
        ),
    },
    "BOTTOM_INFLUENCED": {
        "label": "Bottom-influenced (shallow water)",
        "optical_definition": (
            "DesalGuard-main's version flags elevated NIR reflectance near "
            "shore as possible bottom/substrate influence rather than a "
            "water-column signal, caveated by distance-from-shore."
        ),
        "reference": "n/a -- structural note, not a specific citation.",
        "computable": False,
        "reason": (
            "Needs both a distance-from-shore raster (not built for this "
            "AOI -- the wet core here is a single ~10-30 px blob, not a "
            "coastline with a clear onshore/offshore gradient to measure "
            "distance against) and a NIR-region band placed with more "
            "precision than the group-mean proxy gives. Neither "
            "precondition is met; not attempted here rather than "
            "approximated past the point of being meaningful."
        ),
    },
    "UNKNOWN_ANOMALY": {
        "label": "Unknown anomaly",
        "optical_definition": (
            "High RX anomaly score without a clear match to any computable "
            "class above -- the honest fallback for 'spectrally unusual, "
            "cause not determined from broadband group evidence.'"
        ),
        "reference": "n/a -- fallback class",
        "computable": True,
    },
}

_DISCLAIMER = (
    "Optical hypothesis. Most classes here score off satellite broadband "
    "reflectance GROUPS, not individual wavelengths; CYANO_LIKE is the one "
    "exception, using this AOI's real per-band EnMAP wavelength table when "
    "it is supplied (see module docstring and the per-pixel caveats list for "
    "which applies to this result). NOT a chemical, biological, or "
    "toxicological identification, and coarser than DesalGuard-main's "
    "named-wavelength version even where the same class name is used. Field "
    "sampling and laboratory analysis are required for any compositional "
    "claim."
)


@dataclass
class Evidence:
    name: str
    value: float
    supports: str
    weight: float
    description: str


@dataclass
class Fingerprint:
    top_class: str
    label: str
    scores: dict
    confidence: float
    evidence: list = field(default_factory=list)
    caveats: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "top_class": self.top_class,
            "label": self.label,
            "scores": {k: round(float(v), 4) for k, v in self.scores.items()},
            "confidence": round(float(self.confidence), 4),
            "evidence": [
                {"name": e.name, "value": round(float(e.value), 4), "supports": e.supports,
                 "weight": e.weight, "description": e.description}
                for e in self.evidence
            ],
            "caveats": self.caveats,
            "disclaimer": _DISCLAIMER,
        }


# --------------------------------------------------------------------------- #
# Evidence weights -- PLACEHOLDER, structurally reasonable, NOT empirically
# tuned. There is no labeled sediment/bloom/CDOM/film example for this AOI
# to fit against (a single ~10-30 px wet core with no field data). These
# weights encode a qualitative ordering (a class's defining evidence should
# outweigh secondary/contradicting evidence) copied in STRUCTURE from
# DesalGuard-main's own weighting pattern, not copied in VALUE -- his values
# were presumably tuned against his own coastal cases, which does not
# transfer here any more than his water-mask thresholds did.
# --------------------------------------------------------------------------- #
_W_PRIMARY = 1.0
_W_SECONDARY = 0.4
_W_CONTRADICT = -0.5

# Phycocyanin shoulder windows -- literature/physical constants (Simis et
# al. 2005, same as DesalGuard-main cites), NOT coastal-tuned business
# logic, so reused as-is rather than re-derived for this AOI.
CYANO_LEFT_NM = 600.0
CYANO_CENTRE_NM = 620.0
CYANO_RIGHT_NM = 650.0


def _mean_around(wl_nm: np.ndarray, spec: np.ndarray, nm: float, halfwidth_nm: float = 5.0) -> float:
    """Mean reflectance of real bands within +/- halfwidth_nm of `nm`. Same
    formulation as DesalGuard-main's pipeline/spectral.py:_mean_around()."""
    w = (wl_nm >= nm - halfwidth_nm) & (wl_nm <= nm + halfwidth_nm)
    v = spec[w]
    v = v[np.isfinite(v)]
    return float(v.mean()) if v.size else float("nan")


def local_band_depth(wl_nm: np.ndarray, spec: np.ndarray, left_nm: float,
                     centre_nm: float, right_nm: float, halfwidth_nm: float = 5.0) -> float:
    """Absorption depth at `centre_nm` against a LOCAL continuum (the
    straight line between the real reflectance at `left_nm` and `right_nm`).
    Copied formula from DesalGuard-main's pipeline/spectral.py of the same
    name -- Clark & Roush (1984), a general method, not coastal-specific.

        depth = 1 - R(centre) / R_continuum(centre)

    Positive means absorption (a trough), negative means a peak.
    """
    rl = _mean_around(wl_nm, spec, left_nm, halfwidth_nm)
    rc = _mean_around(wl_nm, spec, centre_nm, halfwidth_nm)
    rr = _mean_around(wl_nm, spec, right_nm, halfwidth_nm)
    if not all(np.isfinite([rl, rc, rr])) or right_nm == left_nm:
        return float("nan")
    frac = (centre_nm - left_nm) / (right_nm - left_nm)
    cont = rl + (rr - rl) * frac
    if abs(cont) < 1e-9:
        return float("nan")
    return float(1.0 - rc / cont)


def fingerprint_pixel(group_values: np.ndarray, background_mean: np.ndarray,
                       background_std: np.ndarray, sam_value: float | None = None,
                       rx_score: float | None = None, rx_threshold: float | None = None,
                       real_wl_nm: np.ndarray | None = None, real_spectrum: np.ndarray | None = None,
                       background_d620_mean: float | None = None,
                       background_d620_std: float | None = None) -> Fingerprint:
    """Score one pixel's band-group reflectance against the AOI's own
    background statistics and produce a weighted class hypothesis.

    Parameters
    ----------
    group_values
        This pixel's band-group means, length ``n_groups`` (same grouping
        used to compute ``background_mean``/``background_std`` -- caller's
        responsibility to keep consistent, mirroring
        pipeline.anomaly.band_group_features()'s output).
    background_mean, background_std
        Per-group mean/std of the AOI's OWN background population (e.g. the
        pooled background pipeline.anomaly.rx_anomaly() builds) -- z-scores
        are computed against this AOI's own observed water, not an absolute
        reflectance threshold borrowed from elsewhere.
    sam_value
        Spectral angle (radians) vs. the background mean spectrum, if
        available (pipeline.anomaly.AnomalyResult.sam) -- used for
        SURFACE_FILM_LIKE's "brighter but similar shape" evidence.
    rx_score, rx_threshold
        This pixel's RX anomaly score and the background's empirical
        threshold, if available -- used for UNKNOWN_ANOMALY's fallback
        evidence and folded into `confidence`.
    real_wl_nm, real_spectrum
        This pixel's REAL per-band wavelength array (nm) and matching
        reflectance spectrum -- e.g. the full 224-band EnMAP spectrum and
        data/metadata/enmap_band_characterisation.json's wavelengths.
        Enables CYANO_LIKE (the one class in this module that needs exact
        wavelengths, not group means). Omit both (the default) and
        CYANO_LIKE is simply not scored, exactly as before this capability
        was added -- existing group-only call sites keep working unchanged.
    background_d620_mean, background_d620_std
        This AOI's OWN background population's mean/std of
        local_band_depth() at the 600/620/650 nm phycocyanin shoulders
        (computed once per background population, not per pixel -- see
        scripts/derive_anomaly_and_fingerprint.py for how it's built from
        the pooled background used elsewhere in this module). CYANO_LIKE
        support is an excess-over-background z-score against these, the
        same relative-to-this-AOI's-own-water approach every other class
        here uses -- not DesalGuard's absolute `d620 > 0.03` cutoff.
    """
    n = len(group_values)
    if n < 2:
        raise ValueError("fingerprint_pixel() needs at least 2 band groups "
                         "(a 'short' and a 'long' proxy) to form any evidence")

    with np.errstate(invalid="ignore", divide="ignore"):
        z = (group_values - background_mean) / np.where(background_std > 1e-9, background_std, np.nan)

    short_z, long_z = float(z[0]), float(z[-1])
    mid_idx = n // 2
    mid_z = float(z[mid_idx])
    broadband_z = float(np.nanmean(z))

    scores = {c: 0.0 for c in CLASSES}
    evidence: list[Evidence] = []
    have_real_bands = real_wl_nm is not None and real_spectrum is not None
    caveats: list[str] = [
        (
            "Group-level proxy evidence for BACKGROUND_WATER, SEDIMENT_LIKE, "
            "BLOOM_LIKE, CDOM_LIKE, SURFACE_FILM_LIKE and UNKNOWN_ANOMALY -- "
            "these still score off band GROUPS, not individual wavelengths "
            "(see module docstring). CYANO_LIKE alone uses this AOI's real "
            "per-band wavelength table (data/metadata/"
            "enmap_band_characterisation.json) when supplied to this call."
            if have_real_bands else
            "Group-level proxy evidence only -- no per-band wavelength table "
            "was supplied for this call (see module docstring)."
        ),
    ]

    # BACKGROUND_WATER: default, penalized by any large deviation in any group.
    max_abs_z = float(np.nanmax(np.abs(z)))
    scores["BACKGROUND_WATER"] = max(0.0, _W_PRIMARY * (1.5 - max_abs_z))

    # SEDIMENT_LIKE: broadband elevation across groups, roughly uniform.
    if broadband_z > 0.5:
        spread = float(np.nanstd(z))
        uniformity = max(0.0, 1.0 - spread / (abs(broadband_z) + 1e-6))
        ev = _W_PRIMARY * broadband_z * uniformity
        scores["SEDIMENT_LIKE"] += ev
        evidence.append(Evidence(
            "broadband_elevation_uniform", broadband_z, "SEDIMENT_LIKE", _W_PRIMARY,
            "Mean z-score elevation across all band groups, scaled by how "
            "uniform that elevation is across groups (sediment scatters "
            "broadly rather than peaking in one region).",
        ))

    # BLOOM_LIKE: mid/long-group elevation specifically outpacing short-group.
    red_edge_excess = mid_z - short_z
    if red_edge_excess > 0.5 and mid_z > 0.3:
        ev = _W_PRIMARY * red_edge_excess
        scores["BLOOM_LIKE"] += ev
        evidence.append(Evidence(
            "red_edge_region_excess", red_edge_excess, "BLOOM_LIKE", _W_PRIMARY,
            "Mid-group z-score minus short-group z-score -- coarse proxy for "
            "a red-edge-region reflectance shoulder relative to visible.",
        ))
        if short_z > 0.3:
            scores["BLOOM_LIKE"] += _W_CONTRADICT * short_z
            evidence.append(Evidence(
                "short_group_also_elevated", short_z, "SEDIMENT_LIKE", _W_CONTRADICT,
                "Short-group is ALSO elevated, which is more consistent with "
                "broadband sediment scattering than a bloom-specific "
                "red-edge peak -- counted against BLOOM_LIKE.",
            ))

    # CDOM_LIKE: short-group depression without broadband brightening.
    if short_z < -0.5 and broadband_z < 0.3:
        ev = _W_PRIMARY * (-short_z)
        scores["CDOM_LIKE"] += ev
        evidence.append(Evidence(
            "blue_region_depression", short_z, "CDOM_LIKE", _W_PRIMARY,
            "Short-group z-score depressed relative to background, without "
            "an accompanying broadband brightening -- coarse proxy for CDOM "
            "blue absorption.",
        ))

    # SURFACE_FILM_LIKE: broadband elevation + low SAM (shape similar to background).
    if sam_value is not None and broadband_z > 0.5:
        # low SAM = similar shape; use a soft threshold rather than a hard cut.
        shape_similarity = max(0.0, 1.0 - float(sam_value) / 0.3)  # ~0.3 rad soft scale
        if shape_similarity > 0.3:
            ev = _W_SECONDARY * broadband_z * shape_similarity
            scores["SURFACE_FILM_LIKE"] += ev
            evidence.append(Evidence(
                "broadband_bright_low_sam", shape_similarity, "SURFACE_FILM_LIKE", _W_SECONDARY,
                "Broadband elevation combined with a spectral angle close to "
                "the background mean shape -- brighter without much shape "
                "change, a coarse film-like heuristic.",
            ))
            caveats.append(
                "SAM soft-scale (0.3 rad) is an unfit placeholder, not derived "
                "from this AOI's own data -- there is no labeled film example."
            )

    # CYANO_LIKE: real-band phycocyanin absorption depth, excess over this
    # AOI's own background, gated on some BLOOM_LIKE-style red-edge support
    # (mirrors DesalGuard's own co-requirement that BLOOM_LIKE > 1.0 fire
    # first -- phycocyanin is a bloom pigment, so an isolated 620 nm dip
    # with no broader bloom-like signal at all is weaker evidence).
    if (real_wl_nm is not None and real_spectrum is not None
            and background_d620_mean is not None and background_d620_std is not None):
        d620 = local_band_depth(real_wl_nm, real_spectrum, CYANO_LEFT_NM, CYANO_CENTRE_NM, CYANO_RIGHT_NM)
        if np.isfinite(d620):
            excess = d620 - background_d620_mean
            with np.errstate(invalid="ignore", divide="ignore"):
                d620_z = excess / background_d620_std if background_d620_std > 1e-9 else float("nan")
            if np.isfinite(d620_z) and d620_z > 1.0 and red_edge_excess > 0.0:
                ev = _W_PRIMARY * min(d620_z, 3.0)
                scores["CYANO_LIKE"] += ev
                evidence.append(Evidence(
                    "phycocyanin_absorption_620_excess_z", d620_z, "CYANO_LIKE", _W_PRIMARY,
                    f"Excess local band-depth at 620 nm (real bands, "
                    f"600/620/650 nm shoulders) over this AOI's own "
                    f"background population, as a z-score against the "
                    f"background's own d620 distribution (raw excess "
                    f"{excess:+.4f}). Gated on some red-edge (BLOOM_LIKE-"
                    f"style) support, mirroring DesalGuard's own "
                    f"co-requirement.",
                ))
            else:
                caveats.append(
                    f"CYANO_LIKE evidence computed but did not clear the "
                    f"gate (d620_z={d620_z:.2f} if finite, "
                    f"red_edge_excess={red_edge_excess:.2f}) -- see evidence "
                    f"list for what WAS computed even when it stays below "
                    f"threshold."
                )
        else:
            caveats.append(
                "CYANO_LIKE: local_band_depth() returned NaN (insufficient "
                "finite real-band data within the shoulder windows) -- not "
                "scored for this pixel."
            )

    # UNKNOWN_ANOMALY: RX score exceeds background threshold but nothing above fired strongly.
    if rx_score is not None and rx_threshold is not None and np.isfinite(rx_score):
        if rx_score >= rx_threshold:
            best_named = max((v for k, v in scores.items() if k != "BACKGROUND_WATER"), default=0.0)
            if best_named < 0.3:
                scores["UNKNOWN_ANOMALY"] = _W_PRIMARY * min(3.0, rx_score / max(rx_threshold, 1e-6))
                evidence.append(Evidence(
                    "rx_score_above_threshold_unexplained", float(rx_score), "UNKNOWN_ANOMALY", _W_PRIMARY,
                    "RX anomaly score exceeds the (small-sample, see "
                    "pipeline/anomaly.py) empirical background threshold, but "
                    "no group-level evidence above explains the shape of the "
                    "deviation.",
                ))
                caveats.append(
                    "RX threshold itself is a rough marker at this AOI's "
                    "background sample size -- see pipeline/anomaly.py module "
                    "docstring."
                )

    top_class = max(scores, key=scores.get)
    top_score = scores[top_class]
    others = sorted((v for k, v in scores.items() if k != top_class), reverse=True)
    runner_up = others[0] if others else 0.0
    confidence = float(np.clip((top_score - runner_up) / (abs(top_score) + 1e-6), 0.0, 1.0)) if top_score > 0 else 0.0

    if top_class == "BACKGROUND_WATER" and max_abs_z < 1.0:
        caveats.append("No group deviates more than 1 background std -- unremarkable pixel, not a positive finding of 'clean water.'")

    return Fingerprint(top_class=top_class, label=CLASSES[top_class]["label"],
                       scores=scores, confidence=confidence, evidence=evidence, caveats=caveats)
