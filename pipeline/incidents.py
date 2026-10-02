"""The COASTAL INCIDENT: the central entity of BLUEBAN 813.

BlueBan is not a map; it manages water incidents. An incident is created when
DETECT finds a region that is unusual both spatially and for its place and
season, and it then moves through human review, field validation and a final
disposition. Every step is recorded; nothing about a past prediction is ever
edited.

State machine
-------------
::

    MONITORING ──detect──▶ DETECTED ──open──▶ UNDER_REVIEW
         ▲                    │                 │  │  │  │
         │                    └──── review ─────┘  │  │  │
         │ INSUFFICIENT_EVIDENCE                   │  │  │
         └─────────────────────────────────────────┘  │  │
                         NEEDS_FIELD_SAMPLE           │  │
          FIELD_VALIDATION_REQUIRED ◀─────────────────┘  │
                │ results received ──▶ UNDER_REVIEW      │
          CONFIRM / FALSE_POSITIVE ─────────────────────▶ CONFIRMED | FALSE_POSITIVE
                                                           │
                                                   close ──▶ RESOLVED ──reopen──▶ UNDER_REVIEW

What CONFIRM means
------------------
An analyst CONFIRM confirms that a real optical water event occurred. It does
NOT confirm a species, a toxin or a substance: "harmful algal bloom" needs a
phytoplankton identification, "oil" needs a chemical sample. The confirmation
basis is recorded (``analyst`` or ``field``) and the event type stays a
hypothesis until field evidence of the right kind exists.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

STATES = ("MONITORING", "DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED",
          "CONFIRMED", "FALSE_POSITIVE", "RESOLVED")
OPEN_STATES = ("MONITORING", "DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED")

DECISIONS = ("CONFIRM", "FALSE_POSITIVE", "RECLASSIFY", "NEEDS_FIELD_SAMPLE",
             "INSUFFICIENT_EVIDENCE")

#: Event-type vocabulary. Optical hypotheses, deliberately not substance names.
EVENT_TYPES = {
    "BLOOM_LIKE": "Possible algae bloom (high chlorophyll)",
    "SEDIMENT_LIKE": "Muddy water (suspended sediment)",
    "SURFACE_FILM_LIKE": "Floating material or surface film",
    "SURFACE_DARK_ANOMALY": "Dark patch on radar (often an oil lookalike)",
    "CDOM_LIKE": "Stained water (dissolved organic matter)",
    "BOTTOM_INFLUENCED": "Seabed showing through (not a water event)",
    "PERSISTENT_FEATURE": "Permanent coastal feature (not a new event)",
    "UNKNOWN_ANOMALY": "Unusual water, type unclear",
}

# Allowed (from_state, decision) -> to_state for analyst reviews.
_REVIEW_TRANSITIONS = {
    "CONFIRM": {"DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "MONITORING"},
    "FALSE_POSITIVE": {"DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "MONITORING"},
    "RECLASSIFY": {"DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "MONITORING",
                   "CONFIRMED"},
    "NEEDS_FIELD_SAMPLE": {"DETECTED", "UNDER_REVIEW", "MONITORING"},
    "INSUFFICIENT_EVIDENCE": {"DETECTED", "UNDER_REVIEW"},
}
_DECISION_TARGET = {
    "CONFIRM": "CONFIRMED",
    "FALSE_POSITIVE": "FALSE_POSITIVE",
    "NEEDS_FIELD_SAMPLE": "FIELD_VALIDATION_REQUIRED",
    "INSUFFICIENT_EVIDENCE": "MONITORING",
}
_ADMIN_TRANSITIONS = {
    ("MONITORING", "DETECTED"), ("DETECTED", "UNDER_REVIEW"),
    ("FIELD_VALIDATION_REQUIRED", "UNDER_REVIEW"),       # results received
    ("CONFIRMED", "RESOLVED"), ("FALSE_POSITIVE", "RESOLVED"),
    ("RESOLVED", "UNDER_REVIEW"),                        # reopen
}


class TransitionError(ValueError):
    pass


def review_transition(status: str, decision: str) -> str:
    """Status after an analyst decision, or raise :class:`TransitionError`."""
    if status not in STATES:
        raise TransitionError(f"unknown status {status!r}")
    if decision not in DECISIONS:
        raise TransitionError(f"unknown decision {decision!r}")
    if status not in _REVIEW_TRANSITIONS[decision]:
        raise TransitionError(f"{decision} is not allowed from {status}")
    if decision == "RECLASSIFY":
        return "UNDER_REVIEW" if status != "CONFIRMED" else "CONFIRMED"
    return _DECISION_TARGET[decision]


def admin_transition(status: str, to: str) -> str:
    if (status, to) not in _ADMIN_TRANSITIONS:
        raise TransitionError(f"{status} -> {to} is not an allowed transition")
    return to


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def incident_id(country: str, year: int, seq: int) -> str:
    return f"BB-{country.upper()}-{int(year)}-{int(seq):03d}"


# --------------------------------------------------------------------------- #
# Labels derived from reviews: how an operator click becomes training data
# --------------------------------------------------------------------------- #
def label_from_review(decision: str, previous_hypothesis: str,
                      new_hypothesis: str | None, confirmation_basis: str) -> dict | None:
    """The triage label an analyst decision implies, or ``None`` if it implies none.

    * CONFIRM          -> y = 1, class = the (possibly reclassified) hypothesis
    * FALSE_POSITIVE   -> y = 0
    * RECLASSIFY       -> no binary label yet, but a class correction
    * NEEDS_FIELD_SAMPLE / INSUFFICIENT_EVIDENCE -> no label: uncertainty is not
      evidence, and training on it would teach the model the analyst's doubt.
    """
    if decision == "CONFIRM":
        return {"y": 1, "class": new_hypothesis or previous_hypothesis,
                "basis": confirmation_basis}
    if decision == "FALSE_POSITIVE":
        return {"y": 0, "class": new_hypothesis or "FALSE_POSITIVE",
                "basis": confirmation_basis}
    if decision == "RECLASSIFY" and new_hypothesis:
        return {"y": None, "class": new_hypothesis, "basis": confirmation_basis,
                "class_correction_from": previous_hypothesis}
    return None


#: Label weights by source. Field evidence outranks an analyst's view, which
#: outranks an automatic cross-sensor reference.
LABEL_WEIGHTS = {"field_measurement": 2.0, "in_situ_archive": 2.0,
                 "analyst_review": 1.0, "cross_sensor_reference": 0.5}


# --------------------------------------------------------------------------- #
# ACT: turn evidence into an operator task
# --------------------------------------------------------------------------- #
@dataclass
class Recommendation:
    action: str
    priority: str
    reasons: list = field(default_factory=list)
    required_evidence: list = field(default_factory=list)
    decision_deadline_utc: str | None = None
    next_pass: dict | None = None
    not_recommended: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"action": self.action, "priority": self.priority,
                "reasons": self.reasons, "required_evidence": self.required_evidence,
                "decision_deadline_utc": self.decision_deadline_utc,
                "next_pass": self.next_pass,
                "not_recommended": self.not_recommended}


def _fmt_pct(p):
    return f"{p:.0f}th" if p is not None and math.isfinite(p) else "unknown"


def recommend(inc: dict, next_pass: dict | None = None) -> Recommendation:
    """Recommended operator action for an incident payload.

    Rules are explicit and every reason is returned, like the risk engine.
    It never recommends a plant shutdown: that decision belongs to the operator
    with field data in hand.
    """
    status = inc.get("status")
    t = inc.get("temporal", {}) or {}
    pct = t.get("seasonal_percentile")
    conf = inc.get("confidence")
    sev = inc.get("severity")
    agree = inc.get("sensor_agreement", {}) or {}
    n_agree = sum(1 for v in agree.values() if isinstance(v, dict) and v.get("agrees"))
    has_field = bool((inc.get("field_validation") or {}).get("measurements"))
    exposure = inc.get("exposure") or []
    top_exp = max((e.get("exposure_score", 0) for e in exposure), default=0.0)
    nearest = min(exposure, key=lambda e: e.get("distance_m", 1e12), default=None)

    reasons = []
    if pct is not None:
        reasons.append(f"Main indicator at the {_fmt_pct(pct)} percentile "
                       f"for this place and season.")
    if inc.get("spatial", {}).get("rx_percentile") is not None:
        reasons.append(f"Stands out from the surrounding water "
                       f"({_fmt_pct(inc['spatial']['rx_percentile'])} percentile).")
    if n_agree:
        reasons.append(f"{n_agree} satellite source(s) agree: "
                       + ", ".join(k for k, v in agree.items()
                                   if isinstance(v, dict) and v.get("agrees")) + ".")
    if conf is not None:
        reasons.append(f"Model confidence {conf:.2f}.")
    if not has_field:
        reasons.append("No water sample yet.")
    if nearest:
        reasons.append(f"Nearest asset: {nearest['asset']['name']}, "
                       f"{nearest['distance_m'] / 1000:.1f} km away.")

    not_rec = ["Automatic plant shutdown: not advised on satellite evidence alone.",
               "Public health warning: needs a lab result first."]
    obs = inc.get("observation_time")
    deadline = None
    if obs:
        try:
            t0 = dt.datetime.fromisoformat(obs.replace("Z", "+00:00"))
            hours = 24 if (sev or 0) >= 0.6 or top_exp >= 0.5 else 72
            deadline = (t0 + dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            deadline = None

    if status in ("FALSE_POSITIVE", "RESOLVED"):
        return Recommendation("NO_ACTION", "NONE", ["Incident closed."], [], None,
                              next_pass, not_rec)
    if inc.get("role") == "negative_control" or (pct is not None and pct <= 50):
        return Recommendation(
            "STAND_DOWN_CONTINUE_MONITORING", "LOW",
            reasons + ["Normal for this place and season. The contrast is a "
                       "permanent feature, not a new event."],
            ["Next clear satellite image"], deadline, next_pass, not_rec)
    if status == "CONFIRMED" and has_field:
        return Recommendation("MANAGE_CONFIRMED_EVENT", "HIGH", reasons,
                              ["Follow-up samples to track the decline",
                               "Tell the asset operator (their own procedure)"],
                              deadline, next_pass, not_rec)
    if not has_field and ((pct or 0) >= 90 or (sev or 0) >= 0.5):
        return Recommendation(
            "FIELD_VERIFICATION", "HIGH" if top_exp >= 0.5 or (pct or 0) >= 97 else "MEDIUM",
            reasons,
            ["Water sample at the event centre, plus one from normal water the same day",
             "Lab tests: chlorophyll-a, turbidity, suspended sediment, temperature, salinity",
             "Algae species ID if a bloom is suspected"],
            deadline, next_pass, not_rec)
    return Recommendation("ANALYST_REVIEW", "MEDIUM", reasons,
                          ["Analyst review of the colour and history evidence"],
                          deadline, next_pass, not_rec)


def alert_message(inc: dict) -> str:
    """Operational alert text: factual, no alarmism."""
    pct = (inc.get("temporal") or {}).get("seasonal_percentile")
    aoi = inc.get("aoi_name") or inc.get("aoi_id")
    etype = EVENT_TYPES.get(inc.get("event_type_hypothesis"), "Water anomaly")
    agree = [k for k, v in (inc.get("sensor_agreement") or {}).items()
             if isinstance(v, dict) and v.get("agrees")]
    parts = [f"Unusual water spotted near {aoi}.",
             f"Suspected: {etype}."]
    if pct is not None:
        parts.append(f"{_fmt_pct(pct)} percentile for this season.")
    parts.append("A second satellite source agrees." if len(agree) > 1
                 else "One satellite source only.")
    parts.append("Needs an analyst's review.")
    return " ".join(parts)


REQUIRED_KEYS = ("id", "status", "aoi_id", "detected_at", "observation_time",
                 "event_type_hypothesis", "severity", "confidence", "model_id",
                 "geometry", "water_quality", "temporal", "sensor_agreement",
                 "quality_flags", "exposure", "field_validation", "provenance")


def validate_payload(inc: dict) -> list:
    """Missing or invalid fields in an incident payload (empty list = valid)."""
    problems = [f"missing {k}" for k in REQUIRED_KEYS if k not in inc]
    if inc.get("status") not in STATES:
        problems.append(f"invalid status {inc.get('status')!r}")
    if inc.get("event_type_hypothesis") not in EVENT_TYPES:
        problems.append(f"invalid event type {inc.get('event_type_hypothesis')!r}")
    for k in ("severity", "confidence"):
        v = inc.get(k)
        if v is not None and not (0.0 <= float(v) <= 1.0):
            problems.append(f"{k} out of [0, 1]")
    g = inc.get("geometry")
    if g is not None and (not isinstance(g, dict) or g.get("type") not in
                          ("Polygon", "MultiPolygon", "Point")):
        problems.append("geometry must be a GeoJSON Polygon/MultiPolygon/Point")
    wq = inc.get("water_quality") or {}
    for name, v in (wq.get("estimates") or {}).items():
        if v.get("quantity_kind") != "CALIBRATED" and v.get("units") in (
                "mg m-3", "mg/m3", "NTU", "mg/L", "g m-3"):
            if v.get("quantity_kind") != "GENERIC_CALIBRATION":
                problems.append(f"{name}: physical units on an uncalibrated proxy")
    return problems
