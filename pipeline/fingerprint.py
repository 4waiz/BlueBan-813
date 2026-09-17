"""Water event fingerprinting: what KIND of anomaly is this?

The hard rule for this module: it produces a WEIGHTED HYPOTHESIS with an
explicit basis, never a confirmed identification. Satellite optics measure how
water scatters and absorbs light. They do not measure chemistry, they do not
identify species, and they cannot distinguish a toxic bloom from a harmless one.

Every class below is defined by optical behaviour, and every score reports which
spectral evidence supported it and how strongly. An operator reading the output
should be able to see exactly why the system leaned one way, and disagree.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .spectral import local_band_depth


# --------------------------------------------------------------------------- #
# Classes, defined optically
# --------------------------------------------------------------------------- #
CLASSES = {
    "BACKGROUND_WATER": {
        "label": "Normal / background water",
        "optical_definition": "Spectrum statistically consistent with the local "
                              "background water population.",
        "colour": "nominal",
    },
    "SEDIMENT_LIKE": {
        "label": "High turbidity / suspended sediment signature",
        "optical_definition": "Broadband elevation of reflectance across the "
                              "visible with the increase growing from blue to "
                              "red, consistent with mineral particle scattering.",
        "reference": "Nechad et al. (2009) RSE 113:2141-2154; "
                     "Doxaran et al. (2002) RSE 81:149-161",
        "colour": "caution",
    },
    "BLOOM_LIKE": {
        "label": "Chlorophyll / bloom-like signature",
        "optical_definition": "Red-edge reflectance peak near 700-710 nm with "
                              "absorption near 675 nm, and depressed blue "
                              "reflectance from pigment absorption near 443 nm.",
        "reference": "Gitelson et al. (2008) RSE 112:3582-3593; "
                     "Mishra & Mishra (2012) RSE 117:394-406",
        "colour": "alert",
    },
    "CYANO_LIKE": {
        "label": "Cyanobacteria-like pigment signature",
        "optical_definition": "Bloom-like shape plus an additional absorption "
                              "feature near 620 nm attributable to phycocyanin.",
        "reference": "Simis et al. (2005) Limnol. Oceanogr. 50:237-245",
        "colour": "alert",
    },
    "CDOM_LIKE": {
        "label": "Coloured dissolved organic matter signature",
        "optical_definition": "Strong, steep absorption in the blue (412-443 nm) "
                              "without a corresponding red-edge peak, typical of "
                              "terrestrial dissolved organic input.",
        "reference": "Bricaud et al. (1981) Limnol. Oceanogr. 26:43-53",
        "colour": "caution",
    },
    "SURFACE_FILM_LIKE": {
        "label": "Surface film / floating material signature",
        "optical_definition": "Elevated NIR reflectance above the red-to-SWIR "
                              "baseline, indicating material at or above the "
                              "surface rather than in the water column.",
        "reference": "Hu (2009) RSE 113:2118-2129 (Floating Algae Index)",
        "colour": "alert",
    },
    "BOTTOM_INFLUENCED": {
        "label": "Shallow water / bottom reflectance",
        "optical_definition": "Elevated green reflectance close to shore with "
                              "the red elevation strongly suppressed relative to "
                              "green, consistent with a bright bottom seen "
                              "through an absorbing water column.",
        "reference": "Lyzenga (1978) Applied Optics 17:379-383",
        "colour": "info",
    },
    "UNKNOWN_ANOMALY": {
        "label": "Unclassified spectral anomaly",
        "optical_definition": "Statistically anomalous but not matching any "
                              "defined optical signature.",
        "colour": "caution",
    },
}


@dataclass
class Evidence:
    """One piece of spectral evidence contributing to a class score."""

    name: str
    value: float
    supports: str
    weight: float
    description: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": None if not np.isfinite(self.value) else round(float(self.value), 6),
            "supports": self.supports,
            "weight": round(float(self.weight), 4),
            "description": self.description,
        }


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
            "evidence": [e.to_dict() for e in self.evidence],
            "caveats": self.caveats,
            "disclaimer": (
                "Optical hypothesis from satellite reflectance. NOT a chemical, "
                "biological or toxicological identification. Field sampling and "
                "laboratory analysis are required to confirm any interpretation."
            ),
        }


def _at(wl, spec, nm):
    i = int(np.argmin(np.abs(wl - nm)))
    return float(spec[i]), float(wl[i])


def fingerprint_spectrum(wl: np.ndarray, spec: np.ndarray, background: np.ndarray,
                         distance_from_shore_m: float | None = None,
                         fai_value: float | None = None) -> Fingerprint:
    """Score optical classes for one spectrum against a background spectrum.

    ``wl`` in nm, ``spec`` and ``background`` are reflectance on the same grid.
    Scores are relative weights of evidence, normalised to sum to 1; they are
    not probabilities and are not presented as such.
    """
    ev: list[Evidence] = []
    scores = {k: 0.0 for k in CLASSES}

    def ratio(nm):
        v, _ = _at(wl, spec, nm)
        b, _ = _at(wl, background, nm)
        return v / b if b > 1e-9 else np.nan

    r443, r490, r560, r620, r665, r675, r685, r705, r740, r865 = (
        ratio(x) for x in (443, 490, 560, 620, 665, 675, 685, 705, 740, 865))

    # --- Spectral tilt: how the enhancement grows with wavelength ----------- #
    if np.isfinite(r443) and np.isfinite(r665):
        tilt = r665 - r443
        ev.append(Evidence(
            "visible_tilt_665_over_443", tilt,
            "SEDIMENT_LIKE" if tilt > 0.5 else "CDOM_LIKE" if tilt < -0.3 else "none",
            abs(tilt),
            "Enhancement at 665 nm minus enhancement at 443 nm. Mineral "
            "particles scatter more efficiently toward the red, so sediment "
            "raises red more than blue; dissolved organic matter absorbs blue "
            "and does the opposite."))
        if tilt > 0.5:
            scores["SEDIMENT_LIKE"] += min(tilt, 4.0)
        elif tilt < -0.3:
            scores["CDOM_LIKE"] += min(-tilt, 2.0)

    # --- Broadband green/red elevation -> sediment ------------------------- #
    if np.isfinite(r560) and np.isfinite(r665):
        broad = 0.5 * (r560 + r665)
        ev.append(Evidence(
            "broadband_vis_enhancement", broad,
            "SEDIMENT_LIKE" if broad > 1.8 else "none", max(0.0, broad - 1.0),
            "Mean enhancement at 560 and 665 nm relative to background water."))
        if broad > 1.8:
            scores["SEDIMENT_LIKE"] += min(broad - 1.0, 3.0)

    # --- Red-edge peak -> bloom ------------------------------------------- #
    # Local band depths against two-shoulder continua, not a global hull.
    #
    # These are reported as ANOMALIES relative to the background water, not as
    # absolute depths. Clear Mediterranean water already has a measurable 675 nm
    # chlorophyll feature (0.059 for the Gulf of Annaba background), so an
    # absolute threshold fires on every pixel including normal water. What
    # identifies an event is how much DEEPER the feature is than the local norm.
    d675 = local_band_depth(wl, spec, 650.0, 675.0, 715.0)
    d675_bg = local_band_depth(wl, background, 650.0, 675.0, 715.0)
    d675 = d675 - d675_bg if np.isfinite(d675) and np.isfinite(d675_bg) else np.nan
    if np.isfinite(r705) and np.isfinite(r665):
        redge = r705 / r665 if r665 > 1e-9 else np.nan
        ev.append(Evidence(
            "red_edge_ratio_705_665", redge,
            "BLOOM_LIKE" if np.isfinite(redge) and redge > 1.15 else "none",
            max(0.0, (redge - 1.0) * 3) if np.isfinite(redge) else 0.0,
            "Ratio of the 705 nm enhancement to the 665 nm enhancement. Algal "
            "biomass produces a reflectance peak near 700-710 nm that mineral "
            "sediment does not."))
        if np.isfinite(redge) and redge > 1.15:
            scores["BLOOM_LIKE"] += min((redge - 1.0) * 4, 4.0)

    if np.isfinite(d675):
        ev.append(Evidence(
            "chl_absorption_depth_675", d675,
            "BLOOM_LIKE" if d675 > 0.02 else "none", d675 * 10,
            "Excess depth of the 675 nm chlorophyll-a absorption feature over "
            "the local background water, measured against a 650/715 nm "
            "continuum. Positive means more pigment absorption than normal here."))
        if d675 > 0.02:
            scores["BLOOM_LIKE"] += min(d675 * 20, 3.0)

    # --- Phycocyanin -> cyanobacteria ------------------------------------- #
    d620 = local_band_depth(wl, spec, 600.0, 620.0, 650.0)
    d620_bg = local_band_depth(wl, background, 600.0, 620.0, 650.0)
    d620 = d620 - d620_bg if np.isfinite(d620) and np.isfinite(d620_bg) else np.nan
    if np.isfinite(d620):
        supports = ("CYANO_LIKE"
                    if (d620 > 0.03 and scores["BLOOM_LIKE"] > 1.0) else "none")
        ev.append(Evidence(
            "phycocyanin_absorption_620", d620, supports, d620 * 10,
            "Excess depth of the 620 nm feature over background water. "
            "Phycocyanin is a cyanobacterial accessory pigment. This requires "
            "narrow bands: Sentinel-2 has no band at 620 nm at all, so a "
            "multispectral sensor cannot form this evidence."))
        if supports == "CYANO_LIKE":
            scores["CYANO_LIKE"] += min(d620 * 20, 2.0)

    # --- Blue depression -> CDOM ------------------------------------------ #
    if np.isfinite(r443) and np.isfinite(r560):
        blue_dep = r560 - r443
        if blue_dep > 0.6 and scores["BLOOM_LIKE"] < 0.5:
            ev.append(Evidence(
                "blue_depression_443", blue_dep, "CDOM_LIKE", min(blue_dep, 2.0),
                "Blue reflectance suppressed relative to green without a "
                "red-edge peak, the signature of dissolved organic absorption."))
            scores["CDOM_LIKE"] += min(blue_dep, 2.0)

    # --- Floating material ------------------------------------------------ #
    if fai_value is not None and np.isfinite(fai_value):
        ev.append(Evidence(
            "floating_algae_index", fai_value,
            "SURFACE_FILM_LIKE" if fai_value > 0.005 else "none",
            max(0.0, fai_value * 200),
            "NIR reflectance above the red-to-SWIR baseline (Hu 2009). "
            "Positive values indicate material at or above the surface."))
        if fai_value > 0.005:
            scores["SURFACE_FILM_LIKE"] += min(fai_value * 300, 3.0)

    # --- Bottom reflectance, the main competing explanation nearshore ------ #
    caveats: list[str] = []
    if distance_from_shore_m is not None:
        shallow = distance_from_shore_m < 300.0
        if shallow and np.isfinite(r560) and np.isfinite(r665):
            # A bright bottom seen through water raises green far more than red,
            # because the water column absorbs red on both the down and up path.
            green_dominance = r560 - r665
            if green_dominance > 0.8:
                ev.append(Evidence(
                    "green_dominant_nearshore", green_dominance,
                    "BOTTOM_INFLUENCED", min(green_dominance, 2.5),
                    f"Green enhancement exceeds red enhancement by "
                    f"{green_dominance:.2f} at {distance_from_shore_m:.0f} m from "
                    f"shore. Water absorbs red strongly, so a bright bottom "
                    f"raises green far more than red; suspended matter in the "
                    f"water column raises both."))
                scores["BOTTOM_INFLUENCED"] += min(green_dominance, 2.5)
        if shallow:
            caveats.append(
                f"Pixel is {distance_from_shore_m:.0f} m from shore. Bottom "
                f"reflectance is a competing explanation that a single scene "
                f"cannot exclude; the temporal baseline test is required.")

    total = sum(scores.values())
    if total < 0.5:
        scores["BACKGROUND_WATER"] = 1.0
        total = sum(scores.values())

    norm = {k: (v / total if total > 0 else 0.0) for k, v in scores.items()}
    top = max(norm, key=norm.get)
    ordered = sorted(norm.values(), reverse=True)
    margin = ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)

    if top == "BACKGROUND_WATER":
        caveats.append("No distinctive optical signature; treated as background.")
    if norm[top] < 0.45:
        top_out = "UNKNOWN_ANOMALY"
        caveats.append(
            f"Leading hypothesis ({CLASSES[top]['label']}) scored only "
            f"{norm[top]:.0%}; reported as unclassified rather than asserted.")
    else:
        top_out = top

    return Fingerprint(
        top_class=top_out,
        label=CLASSES[top_out]["label"],
        scores=norm,
        confidence=float(np.clip(margin, 0.0, 1.0)),
        evidence=sorted(ev, key=lambda e: -e.weight),
        caveats=caveats,
    )
