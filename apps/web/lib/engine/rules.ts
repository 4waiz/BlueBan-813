/**
 * Incident rules shared by both engines' clients: state machine, label
 * derivation, recommendations and alert text. A line-for-line port of
 * pipeline/incidents.py so the hosted workspace behaves exactly like the
 * Python backend.
 */
import type { Decision, EventType, Incident, IncidentStatus, Recommendation } from "./types";

export const STATES: IncidentStatus[] = ["MONITORING", "DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "CONFIRMED", "FALSE_POSITIVE", "RESOLVED"];
export const OPEN_STATES: IncidentStatus[] = ["MONITORING", "DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED"];
export const DECISIONS: Decision[] = ["CONFIRM", "FALSE_POSITIVE", "RECLASSIFY", "NEEDS_FIELD_SAMPLE", "INSUFFICIENT_EVIDENCE"];

export const EVENT_TYPES: Record<EventType, string> = {
  BLOOM_LIKE: "High chlorophyll / bloom-like anomaly",
  SEDIMENT_LIKE: "Turbidity / suspended-sediment anomaly",
  SURFACE_FILM_LIKE: "Surface film / floating material anomaly",
  SURFACE_DARK_ANOMALY: "SAR surface dark anomaly (oil-spill lookalike set)",
  CDOM_LIKE: "Dissolved organic matter anomaly",
  BOTTOM_INFLUENCED: "Shallow bottom / benthic signal (not a water event)",
  PERSISTENT_FEATURE: "Persistent coastal feature (not a new event)",
  UNKNOWN_ANOMALY: "Unclassified water anomaly",
};

const REVIEW_FROM: Record<Decision, IncidentStatus[]> = {
  CONFIRM: ["DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "MONITORING"],
  FALSE_POSITIVE: ["DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "MONITORING"],
  RECLASSIFY: ["DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "MONITORING", "CONFIRMED"],
  NEEDS_FIELD_SAMPLE: ["DETECTED", "UNDER_REVIEW", "MONITORING"],
  INSUFFICIENT_EVIDENCE: ["DETECTED", "UNDER_REVIEW"],
};
const TARGET: Partial<Record<Decision, IncidentStatus>> = {
  CONFIRM: "CONFIRMED", FALSE_POSITIVE: "FALSE_POSITIVE",
  NEEDS_FIELD_SAMPLE: "FIELD_VALIDATION_REQUIRED", INSUFFICIENT_EVIDENCE: "MONITORING",
};
const ADMIN: [IncidentStatus, IncidentStatus][] = [
  ["MONITORING", "DETECTED"], ["DETECTED", "UNDER_REVIEW"], ["FIELD_VALIDATION_REQUIRED", "UNDER_REVIEW"],
  ["CONFIRMED", "RESOLVED"], ["FALSE_POSITIVE", "RESOLVED"], ["RESOLVED", "UNDER_REVIEW"],
];

export class TransitionError extends Error {}

export function reviewTransition(status: IncidentStatus, decision: Decision): IncidentStatus {
  if (!STATES.includes(status)) throw new TransitionError(`unknown status ${status}`);
  if (!DECISIONS.includes(decision)) throw new TransitionError(`unknown decision ${decision}`);
  if (!REVIEW_FROM[decision].includes(status)) throw new TransitionError(`${decision} is not allowed from ${status}`);
  if (decision === "RECLASSIFY") return status === "CONFIRMED" ? "CONFIRMED" : "UNDER_REVIEW";
  return TARGET[decision]!;
}

export function adminTransition(status: IncidentStatus, to: IncidentStatus): IncidentStatus {
  if (!ADMIN.some(([a, b]) => a === status && b === to)) throw new TransitionError(`${status} -> ${to} is not an allowed transition`);
  return to;
}

/** What training label an analyst decision implies (null = none). */
export function labelFromReview(decision: Decision, previous: string, next: string | null | undefined, basis: "analyst" | "field") {
  if (decision === "CONFIRM") return { y: 1, class: next || previous, basis };
  if (decision === "FALSE_POSITIVE") return { y: 0, class: next || "FALSE_POSITIVE", basis };
  if (decision === "RECLASSIFY" && next) return { y: null, class: next, basis, class_correction_from: previous };
  return null;
}

export const LABEL_WEIGHTS: Record<string, number> = {
  field_measurement: 2.0, in_situ_archive: 2.0, analyst_review: 1.0, cross_sensor_reference: 0.5,
};

const fmtPct = (p?: number | null) => (p != null && Number.isFinite(p) ? `${Math.round(p)}th` : "unknown");

export function recommend(inc: Incident): Recommendation {
  const pct = inc.temporal?.seasonal_percentile ?? null;
  const conf = inc.confidence, sev = inc.severity;
  const agree = inc.sensor_agreement || {};
  const agreeing = Object.entries(agree).filter(([, v]) => v && v.agrees).map(([k]) => k);
  const hasField = (inc.field_validation?.measurements?.length ?? inc.measurements?.length ?? 0) > 0;
  const exposure = inc.exposure || [];
  const topExp = exposure.reduce((m, e) => Math.max(m, e.exposure_score ?? 0), 0);
  const nearest = [...exposure].sort((a, b) => a.distance_m - b.distance_m)[0];
  const reasons: string[] = [];
  if (pct != null) reasons.push(`Primary indicator at the ${fmtPct(pct)} seasonal percentile for this location.`);
  if (inc.spatial?.rx_percentile != null) reasons.push(`Spatial anomaly at the ${fmtPct(inc.spatial.rx_percentile)} percentile of the scene's water population.`);
  if (agreeing.length) reasons.push(`${agreeing.length} independent sensor(s) agree: ${agreeing.join(", ")}.`);
  if (conf != null) reasons.push(`Model confidence ${conf.toFixed(2)}.`);
  if (!hasField) reasons.push("No field measurement yet.");
  if (nearest) reasons.push(`Nearest registered asset: ${nearest.asset.name} at ${(nearest.distance_m / 1000).toFixed(1)} km.`);
  const notRec = ["Automatic plant shutdown: not recommended on satellite evidence alone.",
                  "Public health advisory: requires laboratory confirmation."];
  let deadline: string | null = null;
  if (inc.observation_time) {
    const t0 = new Date(inc.observation_time);
    if (!Number.isNaN(t0.getTime())) {
      const hours = (sev ?? 0) >= 0.6 || topExp >= 0.5 ? 24 : 72;
      deadline = new Date(t0.getTime() + hours * 3600e3).toISOString().replace(/\.\d{3}Z$/, "Z");
    }
  }
  if (inc.status === "FALSE_POSITIVE" || inc.status === "RESOLVED")
    return { action: "NO_ACTION", priority: "NONE", reasons: ["Incident closed."], required_evidence: [], decision_deadline_utc: null, not_recommended: notRec };
  if (inc.role === "negative_control" || (pct != null && pct <= 50))
    return { action: "STAND_DOWN_CONTINUE_MONITORING", priority: "LOW",
             reasons: [...reasons, "Observation is not unusual for this place and season: the spatial contrast is a persistent feature, not a new event."],
             required_evidence: ["Next clear overpass"], decision_deadline_utc: deadline, not_recommended: notRec };
  if (inc.status === "CONFIRMED" && hasField)
    return { action: "MANAGE_CONFIRMED_EVENT", priority: "HIGH", reasons,
             required_evidence: ["Follow-up sampling to track decline", "Asset operator notification per their own protocol"],
             decision_deadline_utc: deadline, not_recommended: notRec };
  if (!hasField && ((pct ?? 0) >= 90 || (sev ?? 0) >= 0.5))
    return { action: "FIELD_VERIFICATION", priority: topExp >= 0.5 || (pct ?? 0) >= 97 ? "HIGH" : "MEDIUM", reasons,
             required_evidence: ["Field sample at event core with same-day background control",
                                 "Chlorophyll-a (extracted), turbidity (NTU), TSS, temperature, salinity",
                                 "Phytoplankton identification if a bloom is suspected"],
             decision_deadline_utc: deadline, not_recommended: notRec };
  return { action: "ANALYST_REVIEW", priority: "MEDIUM", reasons, required_evidence: ["Analyst review of spectral and temporal evidence"],
           decision_deadline_utc: deadline, not_recommended: notRec };
}

export function alertMessage(inc: Incident): string {
  const pct = inc.temporal?.seasonal_percentile;
  const etype = EVENT_TYPES[inc.event_type_hypothesis] || "Water anomaly";
  const agreeing = Object.values(inc.sensor_agreement || {}).filter((v) => v && v.agrees).length;
  const parts = [`New coastal anomaly detected near ${inc.aoi_name || inc.aoi_id}.`, `${etype} (hypothesis).`];
  if (pct != null) parts.push(`${fmtPct(pct)} seasonal percentile.`);
  parts.push(agreeing > 1 ? "Cross-sensor evidence available." : "Single-sensor evidence.");
  parts.push("Analyst review required.");
  return parts.join(" ");
}

export const MEASUREMENT_PARAMETERS: Record<string, string[]> = {
  chlorophyll_a: ["mg m-3", "ug/L", "mg/m3"], turbidity: ["NTU", "FNU"], tss: ["mg/L", "g m-3"],
  temperature: ["degC"], salinity: ["PSU", "g/kg"], conductivity: ["mS/cm"], ph: ["pH"],
  dissolved_oxygen: ["mg/L"], nitrate: ["umol/L", "mg/L"], phosphate: ["umol/L", "mg/L"],
  secchi_depth: ["m"], water_depth: ["m"], hydrocarbon_indicator: ["qualitative"], phytoplankton_id: ["qualitative"],
};

export const PARAMETER_LABEL: Record<string, string> = {
  chlorophyll_a: "Chlorophyll-a", turbidity: "Turbidity", tss: "Total suspended solids", temperature: "Temperature",
  salinity: "Salinity", conductivity: "Conductivity", ph: "pH", dissolved_oxygen: "Dissolved oxygen",
  nitrate: "Nitrate", phosphate: "Phosphate", secchi_depth: "Secchi depth", water_depth: "Water depth",
  hydrocarbon_indicator: "Hydrocarbon indicator", phytoplankton_id: "Phytoplankton ID",
};
