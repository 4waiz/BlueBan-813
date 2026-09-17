"""Severity, confidence and operational priority.

The central design rule of this module:

    SEVERITY and CONFIDENCE are never multiplied together.

Collapsing them into one number destroys the only information an operator
actually needs. "Severity 0.8, confidence 0.3" and "severity 0.3, confidence
0.8" would both become 0.24, yet they call for completely different responses:
the first means investigate urgently because it could be serious and we are not
sure; the second means a minor, well-characterised event.

So BLUEBAN 813 reports three separate quantities:

    SEVERITY    how big and how unusual the event is
    CONFIDENCE  how much the measurement and the method can be trusted
    PRIORITY    the operational recommendation, derived from both plus exposure

Priority is produced by an explicit rule table, not a weighted sum, so an
operator can read exactly which rule fired and disagree with it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Component:
    name: str
    value: float
    weight: float
    description: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": None if not np.isfinite(self.value) else round(float(self.value), 4),
            "weight": round(float(self.weight), 3),
            "description": self.description,
        }


@dataclass
class Assessment:
    severity: float
    confidence: float
    priority: str
    priority_reason: str
    severity_components: list = field(default_factory=list)
    confidence_components: list = field(default_factory=list)
    rules_fired: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "severity": round(float(self.severity), 4),
            "confidence": round(float(self.confidence), 4),
            "priority": self.priority,
            "priority_reason": self.priority_reason,
            "severity_components": [c.to_dict() for c in self.severity_components],
            "confidence_components": [c.to_dict() for c in self.confidence_components],
            "rules_fired": self.rules_fired,
            "note": ("Severity and confidence are reported separately and are "
                     "never combined into a single score. Priority follows an "
                     "explicit rule table, shown in rules_fired."),
        }


def _w(components) -> float:
    vals = [(c.value, c.weight) for c in components
            if c.value is not None and np.isfinite(c.value)]
    if not vals:
        return float("nan")
    tw = sum(w for _, w in vals)
    return float(sum(v * w for v, w in vals) / tw) if tw > 0 else float("nan")


def severity(area_km2: float, anomaly_percentile: float | None,
             magnitude_ratio: float | None, historical_percentile: float | None,
             growth_km2_per_h: float | None = None) -> tuple:
    """How big and how unusual, on 0-1.

    ``historical_percentile`` is the most important input: an absolute index
    threshold is meaningless across water bodies, whereas "this is the 97th
    percentile for this place at this time of year" is interpretable anywhere.
    """
    c = []
    # Area saturates around 10 km2: beyond that the operational response is the
    # same, so more area should not keep inflating the score.
    if area_km2 is not None and np.isfinite(area_km2):
        c.append(Component("area", float(np.clip(area_km2 / 10.0, 0, 1)), 0.20,
                           f"Event area {area_km2:.3f} km2, saturating at 10 km2."))
    if anomaly_percentile is not None and np.isfinite(anomaly_percentile):
        c.append(Component("spectral_anomaly", float(np.clip(anomaly_percentile / 100.0, 0, 1)),
                           0.25,
                           f"Spectral anomaly at the {anomaly_percentile:.1f}th "
                           f"percentile of the water population in this scene."))
    if magnitude_ratio is not None and np.isfinite(magnitude_ratio):
        c.append(Component("magnitude", float(np.clip((magnitude_ratio - 1.0) / 4.0, 0, 1)),
                           0.20,
                           f"Peak reflectance {magnitude_ratio:.2f}x background water."))
    if historical_percentile is not None and np.isfinite(historical_percentile):
        c.append(Component("historical_rarity", float(np.clip(historical_percentile / 100.0, 0, 1)),
                           0.30,
                           f"{historical_percentile:.1f}th percentile against the "
                           f"multi-year record for this location and season."))
    if growth_km2_per_h is not None and np.isfinite(growth_km2_per_h):
        c.append(Component("growth", float(np.clip(growth_km2_per_h / 0.5, 0, 1)), 0.15,
                           f"Area changing at {growth_km2_per_h:+.3f} km2/h."))
    return _w(c), c


def confidence(valid_pixel_fraction: float | None,
               cloud_fraction: float | None,
               n_pixels: int | None,
               spectral_snr: float | None,
               classification_margin: float | None,
               cross_sensor_agreement: float | None = None,
               days_since_observation: float | None = None,
               has_in_situ: bool = False,
               bottom_influence_risk: float | None = None) -> tuple:
    """How much the measurement and the method can be trusted, on 0-1.

    ``has_in_situ`` caps the achievable confidence. Without any field
    measurement, an optical interpretation cannot be confirmed, and the system
    should not be able to report high confidence no matter how clean the
    imagery is. That cap is applied by the caller via :func:`apply_caps`.
    """
    c = []
    if valid_pixel_fraction is not None and np.isfinite(valid_pixel_fraction):
        c.append(Component("valid_coverage", float(np.clip(valid_pixel_fraction, 0, 1)), 0.20,
                           f"{valid_pixel_fraction*100:.1f}% of the AOI passed quality screening."))
    if cloud_fraction is not None and np.isfinite(cloud_fraction):
        c.append(Component("cloud_free", float(np.clip(1.0 - cloud_fraction, 0, 1)), 0.15,
                           f"Cloud cover {cloud_fraction*100:.2f}%."))
    if n_pixels is not None:
        # Confidence in a region's mean spectrum grows with sample size but
        # saturates; 500 px at 30 m is 0.45 km2, plenty for a stable mean.
        c.append(Component("sample_size", float(np.clip(np.log10(max(n_pixels, 1)) / np.log10(500), 0, 1)),
                           0.15, f"{n_pixels} pixels contributed to the event spectrum."))
    if spectral_snr is not None and np.isfinite(spectral_snr):
        c.append(Component("spectral_snr", float(np.clip(spectral_snr / 30.0, 0, 1)), 0.20,
                           f"Median signal-to-noise {spectral_snr:.1f} over the "
                           f"water-informative bands, from the sensor's own "
                           f"uncertainty layer."))
    if classification_margin is not None and np.isfinite(classification_margin):
        c.append(Component("class_margin", float(np.clip(classification_margin, 0, 1)), 0.15,
                           f"Leading optical hypothesis leads the next by "
                           f"{classification_margin:.2f}."))
    if cross_sensor_agreement is not None and np.isfinite(cross_sensor_agreement):
        c.append(Component("cross_sensor", float(np.clip(cross_sensor_agreement, 0, 1)), 0.15,
                           "Agreement between independent sensors over the same water."))
    if days_since_observation is not None and np.isfinite(days_since_observation):
        c.append(Component("recency", float(np.clip(1.0 - days_since_observation / 7.0, 0, 1)), 0.10,
                           f"Observation is {days_since_observation:.1f} days old."))
    if bottom_influence_risk is not None and np.isfinite(bottom_influence_risk):
        c.append(Component("bottom_influence", float(np.clip(1.0 - bottom_influence_risk, 0, 1)), 0.20,
                           f"Shallow-water bottom reflectance risk {bottom_influence_risk:.2f}; "
                           f"high risk reduces confidence in a water-column "
                           f"interpretation."))
    return _w(c), c


NO_IN_SITU_CAP = 0.75


def apply_caps(conf: float, has_in_situ: bool) -> tuple:
    """Cap confidence when nothing has been confirmed in the field."""
    notes = []
    if not has_in_situ and np.isfinite(conf) and conf > NO_IN_SITU_CAP:
        notes.append(
            f"Confidence capped at {NO_IN_SITU_CAP:.2f}: no in-situ or "
            f"laboratory measurement has confirmed this interpretation. "
            f"Satellite optics alone cannot exceed this.")
        conf = NO_IN_SITU_CAP
    return conf, notes


# --------------------------------------------------------------------------- #
# Priority: an explicit rule table
# --------------------------------------------------------------------------- #
PRIORITY_LEVELS = ["NORMAL", "WATCH", "INVESTIGATE", "HIGH_PRIORITY"]


TEMPORAL_VETO_PERCENTILE = 50.0


def priority(sev: float, conf: float, max_exposure: float,
             eta_hours: float | None, asset_type: str | None = None,
             historical_percentile: float | None = None) -> tuple:
    """Derive an operational priority from severity, confidence and exposure.

    Rules are evaluated in order and the highest level that fires wins. Every
    fired rule is returned so the recommendation can be audited.

    Two deliberate asymmetries:

    1. Low confidence RAISES priority when severity and exposure are high.
       Uncertainty about a potentially serious event is a reason to go and look,
       not a reason to stand down.

    2. A TEMPORAL VETO caps priority when the observation is not unusual for
       this place and season. A spatial anomaly detector compares a pixel to its
       neighbours, so it will happily flag a permanently turbid harbour or a
       bright shallow bank on every single clear day. Those are features of the
       coastline, not events. If the multi-year record says today is at or below
       the median for this location, the spatial contrast is a persistent
       feature and must not be escalated, however strong it looks in one scene.
    """
    fired = []
    level = "NORMAL"

    def raise_to(lvl, why):
        nonlocal level
        fired.append({"rule": why, "level": lvl})
        if PRIORITY_LEVELS.index(lvl) > PRIORITY_LEVELS.index(level):
            level = lvl

    s = sev if np.isfinite(sev) else 0.0
    c = conf if np.isfinite(conf) else 0.0
    e = max_exposure if np.isfinite(max_exposure) else 0.0

    if s >= 0.35:
        raise_to("WATCH", f"Severity {s:.2f} exceeds the 0.35 watch threshold.")
    if s >= 0.55:
        raise_to("INVESTIGATE", f"Severity {s:.2f} exceeds the 0.55 investigate threshold.")
    if e >= 0.30:
        raise_to("WATCH", f"An asset has exposure {e:.2f}, above 0.30.")
    if e >= 0.50 and s >= 0.30:
        raise_to("INVESTIGATE",
                 f"Moderate event (severity {s:.2f}) with elevated asset "
                 f"exposure {e:.2f}.")
    if eta_hours is not None and eta_hours <= 24 and e >= 0.40:
        raise_to("HIGH_PRIORITY",
                 f"Drift track reaches an exposed asset within {eta_hours:.0f} h.")
    if s >= 0.70 and e >= 0.40:
        raise_to("HIGH_PRIORITY",
                 f"High severity {s:.2f} with asset exposure {e:.2f}.")
    if s >= 0.50 and c < 0.45:
        raise_to("INVESTIGATE",
                 f"Severity {s:.2f} with low confidence {c:.2f}: uncertainty "
                 f"about a potentially significant event is a reason to sample, "
                 f"not to wait.")
    if s < 0.35 and e < 0.30:
        fired.append({"rule": f"Severity {s:.2f} and exposure {e:.2f} are both "
                              f"below watch thresholds.", "level": "NORMAL"})

    # Temporal veto, applied last so it can override any escalation above.
    hp = historical_percentile
    if hp is not None and np.isfinite(hp) and hp <= TEMPORAL_VETO_PERCENTILE:
        capped_from = level
        cap = "WATCH" if e >= 0.50 else "NORMAL"
        if PRIORITY_LEVELS.index(cap) < PRIORITY_LEVELS.index(level):
            level = cap
            fired.append({
                "rule": (f"TEMPORAL VETO: this observation sits at the "
                         f"{hp:.1f}th percentile of the multi-year record for "
                         f"this location and season, at or below the median. "
                         f"The spatial anomaly is therefore a persistent "
                         f"feature of this coastline, not an event. Priority "
                         f"reduced from {capped_from} to {level}."),
                "level": level, "veto": True})

    reason = fired[-1]["rule"] if fired else "No rule fired."
    for f in reversed(fired):
        if f.get("veto"):
            reason = f["rule"]
            break
    else:
        for f in fired:
            if f["level"] == level:
                reason = f["rule"]
                break
    return level, reason, fired


def assess_event(area_km2, anomaly_percentile, magnitude_ratio,
                 historical_percentile, valid_pixel_fraction, cloud_fraction,
                 n_pixels, spectral_snr, classification_margin,
                 max_exposure=0.0, eta_hours=None, growth=None,
                 cross_sensor_agreement=None, days_since_observation=None,
                 has_in_situ=False, bottom_influence_risk=None) -> Assessment:
    sev, sev_c = severity(area_km2, anomaly_percentile, magnitude_ratio,
                          historical_percentile, growth)
    conf, conf_c = confidence(valid_pixel_fraction, cloud_fraction, n_pixels,
                              spectral_snr, classification_margin,
                              cross_sensor_agreement, days_since_observation,
                              has_in_situ, bottom_influence_risk)
    conf, cap_notes = apply_caps(conf, has_in_situ)
    lvl, reason, fired = priority(sev, conf, max_exposure, eta_hours,
                                  historical_percentile=historical_percentile)
    for n in cap_notes:
        fired.append({"rule": n, "level": "CONFIDENCE_CAP"})
    return Assessment(sev, conf, lvl, reason, sev_c, conf_c, fired)
