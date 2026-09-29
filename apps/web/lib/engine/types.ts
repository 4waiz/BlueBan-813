/**
 * Shared types for the BLUEBAN 813 closed loop.
 *
 * These mirror the Python store (services/api/store.py) and incident payload
 * (pipeline/incidents.py) field for field, so the interface works identically
 * against the FastAPI backend (HttpEngine) and the in-browser workspace used
 * by the static deployment (LocalEngine).
 */

export type IncidentStatus =
  | "MONITORING" | "DETECTED" | "UNDER_REVIEW" | "FIELD_VALIDATION_REQUIRED"
  | "CONFIRMED" | "FALSE_POSITIVE" | "RESOLVED";

export type Decision =
  | "CONFIRM" | "FALSE_POSITIVE" | "RECLASSIFY" | "NEEDS_FIELD_SAMPLE" | "INSUFFICIENT_EVIDENCE";

export type EventType =
  | "BLOOM_LIKE" | "SEDIMENT_LIKE" | "SURFACE_FILM_LIKE" | "SURFACE_DARK_ANOMALY"
  | "CDOM_LIKE" | "BOTTOM_INFLUENCED" | "PERSISTENT_FEATURE" | "UNKNOWN_ANOMALY";

export type QuantityKind = "PROXY" | "GENERIC_CALIBRATION" | "CALIBRATED" | "COLORIMETRIC";

export interface Estimate {
  value: number | null;
  units: string;
  quantity_kind: QuantityKind;
  label?: string;
  interval?: [number, number] | null;
  seasonal_percentile?: number | null;
  z?: number | null;
  baseline_median?: number | null;
  note?: string;
}

export interface SourceRecord {
  satellite?: string; sensor?: string; scene_id?: string; acquisition_utc?: string;
  product?: string; processing_level?: string; provider?: string; licence?: string;
  bands_used?: string[]; units?: string; quality_mask?: string; access_url?: string;
  notes?: string;
}

export interface SensorAgreement { agrees: boolean | null; note?: string; value?: number | null }

export interface ExposureRecord {
  asset: { id: string; name: string; type: string; type_label?: string; lon: number; lat: number; source?: string };
  distance_m: number; direction?: string; exposure_score?: number; basis?: string[];
}

export interface Review {
  id: string; incident_id: string; reviewer: string; created_at: string; model_id: string | null;
  previous_hypothesis: string; decision: Decision; new_hypothesis: string | null; note: string;
  evidence_viewed: string[]; status_before: IncidentStatus; status_after: IncidentStatus;
}

export type SampleStatus = "PLANNED" | "COLLECTED" | "LAB_PENDING" | "RESULT_RECEIVED" | "REMOVED";

export interface Sample {
  id: string; incident_id: string; code: string; role: string; lon: number; lat: number;
  status: SampleStatus; question?: string | null; analytes?: string[]; rationale?: string | null;
  planned_by?: string | null; planned_at?: string | null; collected_by?: string | null;
  collected_at?: string | null; updated_at: string;
}

export interface Measurement {
  id: string; incident_id: string; sample_id: string | null; parameter: string; value: number;
  unit: string; method?: string | null; measured_at?: string | null; lab?: string | null;
  qc_flag: string; source: "manual" | "lab_csv"; entered_by: string; entered_at: string;
}

export interface Prediction { id: number; incident_id: string; model_id: string; created_at: string; output: Record<string, unknown> }

export interface AuditEvent {
  seq: number; at: string; actor: string; action: string; entity_type: string; entity_id: string;
  detail: Record<string, unknown>; prev_hash: string; hash: string;
}

export interface Recommendation {
  action: string; priority: string; reasons: string[]; required_evidence: string[];
  decision_deadline_utc: string | null; next_pass?: Record<string, unknown> | null; not_recommended: string[];
}

export interface Incident {
  id: string;
  status: IncidentStatus;
  aoi_id: string;
  aoi_name?: string;
  detected_at: string;
  observation_time: string;
  event_type_hypothesis: EventType;
  severity: number | null;
  confidence: number | null;
  priority?: string | null;
  model_id: string | null;
  role?: "operational" | "negative_control" | "benchmark";
  geometry: GeoJSON.Geometry | null;
  centroid?: [number, number];
  area_km2?: number | null;
  title?: string;
  summary?: string;
  water_quality: { estimates?: Record<string, Estimate>; features?: Record<string, Estimate> };
  temporal: { seasonal_percentile?: number | null; n_seasonal?: number | null; persistence_frac?: number | null; series?: { date: string; value: number | null }[]; note?: string };
  spatial?: { rx_percentile?: number | null };
  sensor_agreement: Record<string, SensorAgreement>;
  quality_flags: string[];
  exposure: ExposureRecord[];
  field_validation: { status?: string; measurements?: Measurement[] };
  provenance: { sources?: SourceRecord[]; algorithm?: Record<string, unknown>; code_version?: string };
  model_features?: Record<string, number | null>;
  layers?: IncidentLayers;
  spectral?: { wavelengths_nm: number[]; event: (number | null)[]; background: (number | null)[]; background_p05?: (number | null)[]; background_p95?: (number | null)[]; sensor: string; simulated?: boolean; bands?: string[] };
  context?: { title: string; source: string; url?: string; note?: string }[];
  forecast?: { steps: { hours: number; centroid: [number, number]; spread_radius_m: number; particles?: [number, number][]; bearing_deg?: number; displacement_m?: number }[]; wind?: { speed_kmh?: number; from?: string } | null; label?: string; is_hydrodynamic_model?: boolean };
  cube?: string | null;
  aliases?: string[];
  disposition?: string | null;
  reviews?: Review[];
  samples?: Sample[];
  measurements?: Measurement[];
  predictions?: Prediction[];
  recommendation?: Recommendation;
  audit_trail?: AuditEvent[];
  updated_at?: string;
}

export interface IncidentSummary {
  id: string; aoi_id: string; status: IncidentStatus; detected_at: string; observation_time: string;
  event_type_hypothesis: EventType; severity: number | null; confidence: number | null;
  priority?: string | null; model_id: string | null; centroid_lon?: number; centroid_lat?: number;
  area_km2?: number | null; role?: string; disposition?: string | null; updated_at?: string; title?: string;
}

export interface LayerRef {
  key: string; label: string; url: string; bounds: [number, number, number, number];
  legend?: { min: number; max: number; units: string; cmap: string; label: string };
  date?: string; sensor?: string; kind?: "raster" | "vector";
}

export interface IncidentLayers {
  bounds: [number, number, number, number];
  rasters: LayerRef[];
  timeline?: { date: string; rgb: string; index?: string; valid?: boolean }[];
  pixels?: { url: string; meta: string };
}

export interface LabelRow {
  id: string; task: string; incident_id: string | null; aoi_id: string | null;
  target: { y?: number | null; class?: string; [k: string]: unknown };
  features: Record<string, number | null>; source: string; source_ref: string | null;
  weight: number; split: "train" | "validation"; group_key: string | null;
  created_at: string; created_by: string; superseded_by: string | null;
}

export interface MetricRow { split: string; subgroup: string; metric: string; value: number | null; ci_low?: number | null; ci_high?: number | null; n?: number | null }

export interface GateCheck { name: string; passed: boolean; detail?: unknown }
export interface GateReport {
  task: string; passed: boolean; checks: GateCheck[];
  summary: { candidate: Record<string, unknown>; production: Record<string, unknown> };
  human_approval: { required: boolean; approved_by: string | null; at?: string; note?: string };
  validation_hash: string;
  rollback?: Record<string, unknown>;
}

export type ModelStatus = "TRAINING" | "CANDIDATE" | "REJECTED" | "STAGING" | "PRODUCTION" | "RETIRED";

export interface ModelArtifact {
  kind: "logistic" | "ridge_log10"; features: string[]; medians: number[]; mean: number[];
  scale: number[]; coef: number[]; intercept: number; resid_sd?: number | null;
  conformal_q90?: number | null; extra?: Record<string, unknown>;
}

export interface ModelRecord {
  id: string; task: string; version: string; model_type: string; created_at: string;
  training_dataset_version: string | null; validation_dataset_hash: string | null;
  feature_set: string[]; params: Record<string, unknown> | null; artifact: ModelArtifact | Record<string, unknown> | null;
  status: ModelStatus; parent_model: string | null; notes: string | null; gate: GateReport | null;
  promoted_by: string | null; promoted_at: string | null; metrics: MetricRow[];
}

export interface TrainingJob {
  id: string; task: string; requested_by: string; created_at: string; started_at: string | null;
  finished_at: string | null; status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  dataset_version: string | null; n_train: number | null; n_validation: number | null;
  candidate_model_id: string | null; log: { at: string; msg: string; [k: string]: unknown }[]; error: string | null;
}

export interface Aoi {
  id: string; name: string; emirate?: string; coast?: string; bbox: [number, number, number, number];
  optical_regime?: string; status?: string; created_by?: string;
  last_observation?: string | null; next_pass?: string | null; n_obs_7d?: number | null;
  latest?: Record<string, number | null>; open_incidents?: number;
}

export interface AssetRow { id: string; name: string; type: string; lon: number; lat: number; source: string; aoi_id?: string | null; notes?: string | null }

export interface Alert { id: string; incident_id: string | null; aoi_id: string | null; level: string; message: string; created_at: string; acknowledged_by: string | null; acknowledged_at: string | null }

export interface ReviewInput { reviewer: string; decision: Decision; new_hypothesis?: string | null; note?: string; evidence_viewed?: string[] }
export interface MeasurementInput { actor: string; parameter: string; value: number; unit: string; sample_id?: string | null; method?: string | null; measured_at?: string | null; lab?: string | null; qc_flag?: string }
export interface SampleInput { code?: string; role: string; lon: number; lat: number; question?: string; analytes?: string[]; rationale?: string }

/** The one interface every screen talks to. */
export interface Engine {
  readonly mode: "live" | "workspace";
  listIncidents(): Promise<IncidentSummary[]>;
  getIncident(id: string): Promise<Incident | null>;
  review(id: string, body: ReviewInput): Promise<{ review_id: string; status_before: IncidentStatus; status_after: IncidentStatus; label_id: string | null; incident: Incident }>;
  planSamples(id: string, actor: string, points: SampleInput[]): Promise<Sample[]>;
  patchSample(sampleId: string, actor: string, patch: Partial<Pick<Sample, "lon" | "lat" | "status" | "role">>): Promise<Sample>;
  addMeasurement(id: string, body: MeasurementInput): Promise<Measurement>;
  importLabCsv(id: string, actor: string, csv: string): Promise<{ imported: number; rejected: { line: number; error: string }[] }>;
  retrain(task: string, requestedBy: string): Promise<TrainingJob>;
  jobs(): Promise<TrainingJob[]>;
  models(task?: string): Promise<ModelRecord[]>;
  model(id: string): Promise<ModelRecord | null>;
  promote(id: string, approvedBy: string, note?: string): Promise<ModelRecord>;
  reject(id: string, actor: string, note?: string): Promise<ModelRecord>;
  rollback(id: string, actor: string, note?: string): Promise<ModelRecord>;
  labels(task?: string): Promise<LabelRow[]>;
  audit(entityType?: string, entityId?: string, limit?: number): Promise<AuditEvent[]>;
  verifyAudit(): Promise<{ ok: boolean; n: number; head?: string; first_bad_seq?: number }>;
  alerts(): Promise<Alert[]>;
  ackAlert(id: string, actor: string): Promise<void>;
  aois(): Promise<Aoi[]>;
  addAoi(aoi: Omit<Aoi, "id"> & { id?: string }, actor: string): Promise<Aoi>;
  assets(): Promise<AssetRow[]>;
  addAsset(a: Omit<AssetRow, "id" | "source"> & { id?: string }, actor: string): Promise<AssetRow>;
  transition(id: string, to: IncidentStatus, actor: string, reason?: string): Promise<Incident>;
  reset?(): Promise<void>;
}
