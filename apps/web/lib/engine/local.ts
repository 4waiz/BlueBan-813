/**
 * LocalEngine: the closed loop running entirely in the browser.
 *
 * The hosted deployment is static (Cloudflare Pages), so there is no Python
 * backend to persist reviews or train models. This engine is the same system
 * as services/api/store.py + trainer.py, ported: every visitor gets their own
 * persistent WORKSPACE (localStorage), seeded from the pipeline's outputs.
 * Judges therefore each see a consistent story, nothing one visitor does can
 * corrupt another's, and every action still persists, is audited in a
 * SHA-256 hash chain, and can be exported.
 */
import type {
  Aoi, Alert, AssetRow, AuditEvent, Engine, Incident, IncidentStatus, IncidentSummary, LabelRow,
  Measurement, MeasurementInput, ModelArtifact, ModelRecord, Review, ReviewInput, Sample, SampleInput,
  TrainingJob,
} from "./types";
import {
  adminTransition, alertMessage, EVENT_TYPES, LABEL_WEIGHTS, labelFromReview, MEASUREMENT_PARAMETERS,
  recommend, reviewTransition,
} from "./rules";
import {
  canon, datasetHash, evaluateGate, fitLogistic, modelTests, nextVersion, predict, rulesScore, sha256Hex,
  toMatrix, TRIAGE_FEATURES,
} from "../learning";

const KEY = "blueban813.workspace.v1";
const GENESIS = "0".repeat(64);
const SYSTEM_ACTORS = new Set(["", "system", "pipeline", "trainer", "gate", "auto"]);

export interface Seed {
  seed_version: string;
  generated_utc: string;
  incidents: Incident[];
  models: ModelRecord[];
  labels: LabelRow[];
  aois: Aoi[];
  assets: AssetRow[];
  meta?: Record<string, unknown>;
}

interface State {
  seed_version: string;
  created_at: string;
  incidents: Record<string, Incident>;
  reviews: Review[];
  samples: Sample[];
  measurements: Measurement[];
  predictions: { id: number; incident_id: string; model_id: string; created_at: string; output: Record<string, unknown> }[];
  labels: LabelRow[];
  models: ModelRecord[];
  jobs: TrainingJob[];
  aois: Aoi[];
  assets: AssetRow[];
  alerts: Alert[];
  audit: AuditEvent[];
  meta: Record<string, unknown>;
}

const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
const rid = (p: string) => `${p}-${Math.random().toString(16).slice(2, 12)}`;
const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v));

export class LocalEngine implements Engine {
  readonly mode = "workspace" as const;
  private state: State | null = null;
  private loading: Promise<State> | null = null;
  private lock: Promise<unknown> = Promise.resolve();

  constructor(private seedUrl: string) {}

  // ------------------------------------------------------------ persistence
  private async load(): Promise<State> {
    if (this.state) return this.state;
    if (this.loading) return this.loading;
    this.loading = (async () => {
      const seed: Seed = await fetch(this.seedUrl, { cache: "no-store" }).then((r) => {
        if (!r.ok) throw new Error(`workspace seed missing (${r.status})`);
        return r.json();
      });
      let saved: State | null = null;
      try {
        const raw = localStorage.getItem(KEY);
        if (raw) saved = JSON.parse(raw);
      } catch { saved = null; }
      if (saved && saved.seed_version === seed.seed_version) {
        this.state = saved;
      } else {
        this.state = await this.fromSeed(seed);
        this.persist();
      }
      return this.state!;
    })();
    return this.loading;
  }

  private async fromSeed(seed: Seed): Promise<State> {
    const st: State = {
      seed_version: seed.seed_version, created_at: now(), incidents: {}, reviews: [], samples: [],
      measurements: [], predictions: [], labels: clone(seed.labels), models: clone(seed.models), jobs: [],
      aois: clone(seed.aois), assets: clone(seed.assets), alerts: [], audit: [], meta: { ...(seed.meta || {}) },
    };
    this.state = st;
    await this.appendAudit("pipeline", "workspace.init", "workspace", seed.seed_version,
      { incidents: seed.incidents.length, labels: seed.labels.length, models: seed.models.length });
    let pid = 1;
    for (const inc of seed.incidents) {
      const p = clone(inc);
      const samples = (p.samples || []) as Sample[];
      delete p.samples; delete p.reviews; delete p.measurements; delete p.predictions; delete p.audit_trail;
      st.incidents[p.id] = p;
      st.predictions.push({ id: pid++, incident_id: p.id, model_id: p.model_id || "unknown", created_at: p.detected_at,
        output: { event_type_hypothesis: p.event_type_hypothesis, severity: p.severity, confidence: p.confidence, priority: p.priority } });
      st.samples.push(...samples.map((s) => ({ ...s, incident_id: p.id })));
      await this.appendAudit("pipeline", "incident.create", "incident", p.id, { status: p.status, model_id: p.model_id });
      if (p.role !== "negative_control" && ["DETECTED", "UNDER_REVIEW"].includes(p.status)) {
        st.alerts.push({ id: rid("AL"), incident_id: p.id, aoi_id: p.aoi_id, level: "REVIEW_REQUIRED",
          message: alertMessage(p), created_at: p.detected_at, acknowledged_by: null, acknowledged_at: null });
      }
    }
    return st;
  }

  private persist() {
    try { localStorage.setItem(KEY, JSON.stringify(this.state)); } catch { /* storage full or blocked: keep in memory */ }
  }

  /** Serialise writes so the hash chain stays linear. */
  private async write<T>(fn: (st: State) => Promise<T>): Promise<T> {
    const run = this.lock.then(async () => {
      const st = await this.load();
      const out = await fn(st);
      this.persist();
      return out;
    });
    this.lock = run.catch(() => undefined);
    return run;
  }

  async reset() {
    try { localStorage.removeItem(KEY); } catch { /* ignore */ }
    this.state = null; this.loading = null;
    await this.load();
  }

  /** Download the whole workspace (reviews, labels, models, audit) as JSON. */
  async exportWorkspace(): Promise<string> {
    return JSON.stringify(await this.load(), null, 1);
  }

  // -------------------------------------------------------------- incidents
  async listIncidents(): Promise<IncidentSummary[]> {
    const st = await this.load();
    return Object.values(st.incidents).map((p) => ({
      id: p.id, aoi_id: p.aoi_id, status: p.status, detected_at: p.detected_at, observation_time: p.observation_time,
      event_type_hypothesis: p.event_type_hypothesis, severity: p.severity, confidence: p.confidence,
      priority: p.priority, model_id: p.model_id, centroid_lon: p.centroid?.[0], centroid_lat: p.centroid?.[1],
      area_km2: p.area_km2, role: p.role, disposition: p.disposition, updated_at: p.updated_at, title: p.title,
    })).sort((a, b) => (a.observation_time < b.observation_time ? 1 : -1));
  }

  async getIncident(id: string): Promise<Incident | null> {
    const st = await this.load();
    const base = st.incidents[id];
    if (!base) return null;
    const p: Incident = clone(base);
    p.reviews = st.reviews.filter((r) => r.incident_id === id);
    p.samples = st.samples.filter((s) => s.incident_id === id && s.status !== "REMOVED").sort((a, b) => (a.code < b.code ? -1 : 1));
    p.measurements = st.measurements.filter((m) => m.incident_id === id);
    p.predictions = st.predictions.filter((x) => x.incident_id === id);
    p.field_validation = { ...(p.field_validation || {}), measurements: p.measurements };
    p.recommendation = recommend(p);
    p.audit_trail = st.audit.filter((a) => a.entity_id === id || (a.detail as Record<string, unknown>)?.incident_id === id);
    return p;
  }

  async review(id: string, body: ReviewInput) {
    return this.write(async (st) => {
      const reviewer = (body.reviewer || "").trim();
      if (!reviewer) throw new Error("reviewer is required");
      const inc = st.incidents[id];
      if (!inc) throw new Error(`not found: ${id}`);
      if (body.new_hypothesis && !(body.new_hypothesis in EVENT_TYPES)) throw new Error(`unknown event type ${body.new_hypothesis}`);
      if (body.decision === "RECLASSIFY" && !body.new_hypothesis) throw new Error("RECLASSIFY requires a new hypothesis");
      const before = inc.status;
      const after = reviewTransition(before, body.decision);
      const hasField = st.measurements.some((m) => m.incident_id === id);
      const basis = hasField ? "field" : "analyst";
      const review: Review = {
        id: rid("RV"), incident_id: id, reviewer, created_at: now(), model_id: inc.model_id,
        previous_hypothesis: inc.event_type_hypothesis, decision: body.decision,
        new_hypothesis: body.new_hypothesis || null, note: body.note || "",
        evidence_viewed: body.evidence_viewed || [], status_before: before, status_after: after,
      };
      st.reviews.push(review);
      inc.status = after;
      inc.updated_at = review.created_at;
      if (body.new_hypothesis) inc.event_type_hypothesis = body.new_hypothesis as Incident["event_type_hypothesis"];
      if (after === "CONFIRMED")
        inc.disposition = `Confirmed by ${basis === "field" ? "field evidence" : "an analyst"}: the unusual water is real. The substance or species is not confirmed${basis === "field" ? "" : " without a water sample"}.`;
      else if (after === "FALSE_POSITIVE") inc.disposition = `False alarm (${basis} review)`;
      await this.appendAudit(reviewer, `review.${body.decision.toLowerCase()}`, "incident", id,
        { review_id: review.id, from: before, to: after, model_id: inc.model_id, new_hypothesis: body.new_hypothesis || null, basis });
      const lab = labelFromReview(body.decision, review.previous_hypothesis, body.new_hypothesis, basis);
      let label_id: string | null = null;
      if (lab && lab.y != null) {
        label_id = await this.insertLabel(st, {
          task: "triage", incident_id: id, aoi_id: inc.aoi_id, target: lab,
          features: inc.model_features || {}, source: basis === "field" ? "field_measurement" : "analyst_review",
          source_ref: review.id, group_key: `${inc.aoi_id}|${inc.observation_time.slice(0, 7)}`, actor: reviewer,
        });
      }
      st.alerts.filter((a) => a.incident_id === id && !a.acknowledged_at).forEach((a) => { a.acknowledged_by = reviewer; a.acknowledged_at = review.created_at; });
      return { review_id: review.id, status_before: before, status_after: after, label_id, incident: (await this.getIncidentFrom(st, id))! };
    });
  }

  private async getIncidentFrom(st: State, id: string) { this.state = st; return this.getIncident(id); }

  private async insertLabel(st: State, a: { task: string; incident_id: string | null; aoi_id: string | null; target: Record<string, unknown>; features: Record<string, number | null>; source: string; source_ref: string | null; group_key: string | null; actor: string; split?: "train" | "validation" }) {
    const id = rid("LB");
    const row: LabelRow = {
      id, task: a.task, incident_id: a.incident_id, aoi_id: a.aoi_id, target: a.target as LabelRow["target"],
      features: a.features, source: a.source, source_ref: a.source_ref, weight: LABEL_WEIGHTS[a.source] ?? 1,
      split: a.split || "train", group_key: a.group_key, created_at: now(), created_by: a.actor, superseded_by: null,
    };
    if (a.incident_id)
      st.labels.filter((l) => l.task === a.task && l.incident_id === a.incident_id && !l.superseded_by).forEach((l) => { l.superseded_by = id; });
    st.labels.push(row);
    await this.appendAudit(a.actor, "label.create", "label", id, { task: a.task, incident_id: a.incident_id, source: a.source, target: a.target, split: row.split });
    return id;
  }

  // ------------------------------------------------------------------ field
  async planSamples(id: string, actor: string, points: SampleInput[]): Promise<Sample[]> {
    return this.write(async (st) => {
      if (!st.incidents[id]) throw new Error(`not found: ${id}`);
      const t = now();
      st.samples.filter((s) => s.incident_id === id && s.status === "PLANNED").forEach((s) => { s.status = "REMOVED"; s.updated_at = t; });
      points.forEach((pt, i) => {
        const code = pt.code || `S${String(i + 1).padStart(2, "0")}`;
        const sid = `${id}-${code}`;
        const ex = st.samples.find((s) => s.id === sid);
        if (ex) Object.assign(ex, { lon: pt.lon, lat: pt.lat, role: pt.role, status: ex.status === "REMOVED" ? "PLANNED" : ex.status, updated_at: t });
        else st.samples.push({ id: sid, incident_id: id, code, role: pt.role, lon: pt.lon, lat: pt.lat, status: "PLANNED",
          question: pt.question || null, analytes: pt.analytes || [], rationale: pt.rationale || null, planned_by: actor,
          planned_at: t, collected_by: null, collected_at: null, updated_at: t });
      });
      await this.appendAudit(actor, "samples.plan", "incident", id, { n: points.length, codes: points.map((p) => p.code) });
      return st.samples.filter((s) => s.incident_id === id && s.status !== "REMOVED");
    });
  }

  async patchSample(sampleId: string, actor: string, patch: Partial<Pick<Sample, "lon" | "lat" | "status" | "role">>): Promise<Sample> {
    return this.write(async (st) => {
      const s = st.samples.find((x) => x.id === sampleId);
      if (!s) throw new Error(`not found: ${sampleId}`);
      if (patch.status && !["PLANNED", "COLLECTED", "LAB_PENDING", "RESULT_RECEIVED", "REMOVED"].includes(patch.status)) throw new Error(`invalid sample status ${patch.status}`);
      Object.assign(s, patch, { updated_at: now() });
      if (patch.status === "COLLECTED") { s.collected_by = actor; s.collected_at = s.updated_at; }
      await this.appendAudit(actor, "sample.update", "sample", sampleId, { patch, incident_id: s.incident_id });
      return { ...s };
    });
  }

  async addMeasurement(id: string, b: MeasurementInput): Promise<Measurement> {
    return this.write(async (st) => this.addMeasurementIn(st, id, b, "manual"));
  }

  private async addMeasurementIn(st: State, id: string, b: MeasurementInput, source: "manual" | "lab_csv"): Promise<Measurement> {
    const inc = st.incidents[id];
    if (!inc) throw new Error(`not found: ${id}`);
    const units = MEASUREMENT_PARAMETERS[b.parameter];
    if (!units) throw new Error(`unsupported parameter ${b.parameter}`);
    if (!units.includes(b.unit)) throw new Error(`unit ${b.unit} not accepted for ${b.parameter} (use one of ${units.join(", ")})`);
    const v = Number(b.value);
    if (!Number.isFinite(v)) throw new Error("value is not a number");
    if (b.parameter !== "temperature" && v < 0) throw new Error(`${b.parameter} cannot be negative`);
    if (b.sample_id && !st.samples.some((s) => s.id === b.sample_id && s.incident_id === id)) throw new Error(`unknown sample ${b.sample_id}`);
    const m: Measurement = { id: rid("MS"), incident_id: id, sample_id: b.sample_id || null, parameter: b.parameter, value: v, unit: b.unit,
      method: b.method || null, measured_at: b.measured_at || null, lab: b.lab || null, qc_flag: b.qc_flag || "UNCHECKED",
      source, entered_by: b.actor, entered_at: now() };
    st.measurements.push(m);
    if (b.sample_id) { const s = st.samples.find((x) => x.id === b.sample_id)!; s.status = "RESULT_RECEIVED"; s.updated_at = m.entered_at; }
    if (inc.status === "FIELD_VALIDATION_REQUIRED") {
      inc.status = "UNDER_REVIEW";
      await this.appendAudit(b.actor, "incident.transition", "incident", id, { from: "FIELD_VALIDATION_REQUIRED", to: "UNDER_REVIEW", reason: "field result received" });
    }
    await this.appendAudit(b.actor, "measurement.create", "measurement", m.id, { incident_id: id, sample_id: m.sample_id, parameter: m.parameter, value: v, unit: m.unit, source });
    return m;
  }

  async importLabCsv(id: string, actor: string, csv: string) {
    return this.write(async (st) => {
      const lines = csv.replace(/\r/g, "").split("\n").filter((l) => l.trim());
      const head = (lines.shift() || "").split(",").map((h) => h.trim());
      const rejected: { line: number; error: string }[] = [];
      let imported = 0;
      for (let i = 0; i < lines.length; i++) {
        const cells = lines[i].split(",");
        const row: Record<string, string> = {};
        head.forEach((h, j) => (row[h] = (cells[j] || "").trim()));
        try {
          if (!row.parameter || !row.value || !row.unit) throw new Error("parameter, value and unit are required");
          const code = row.sample_code;
          await this.addMeasurementIn(st, id, { actor, parameter: row.parameter, value: Number(row.value), unit: row.unit,
            sample_id: code ? `${id}-${code}` : null, method: row.method || null, measured_at: row.measured_at || null,
            lab: row.lab || null, qc_flag: row.qc_flag || "UNCHECKED" }, "lab_csv");
          imported++;
        } catch (e) { rejected.push({ line: i + 2, error: (e as Error).message }); }
      }
      return { imported, rejected };
    });
  }

  // ------------------------------------------------------------------ learn
  async labels(task = "triage"): Promise<LabelRow[]> {
    const st = await this.load();
    return st.labels.filter((l) => l.task === task && !l.superseded_by);
  }

  async retrain(task: string, requestedBy: string): Promise<TrainingJob> {
    return this.write(async (st) => {
      const job: TrainingJob = { id: rid("JOB"), task, requested_by: requestedBy, created_at: now(), started_at: now(),
        finished_at: null, status: "RUNNING", dataset_version: null, n_train: null, n_validation: null,
        candidate_model_id: null, log: [], error: null };
      st.jobs.unshift(job);
      const step = (msg: string, extra: Record<string, unknown> = {}) => job.log.push({ at: now(), msg, ...extra });
      await this.appendAudit(requestedBy, "training.request", "training_job", job.id, { task });
      try {
        if (task !== "triage") throw new Error("the hosted workspace trains the triage model; quantification runs in the Python backend");
        const active = st.labels.filter((l) => l.task === task && !l.superseded_by && (l.target.y === 0 || l.target.y === 1));
        const train = active.filter((l) => l.split === "train");
        const val = active.filter((l) => l.split === "validation");
        step("labels loaded", { n_train: train.length, n_validation: val.length });
        const key = `validation_hash:${task}`;
        const current = await datasetHash(val);
        let frozen = st.meta[key] as string | undefined;
        if (!frozen) { frozen = current; st.meta[key] = current; step("validation set frozen for the first time", { hash: current }); }
        if (!val.length) throw new Error("no validation labels: freeze a validation set before training");
        if (train.length < 12) throw new Error(`insufficient verified labels: ${train.length} in train, need >= 12`);
        const tr = toMatrix(train, TRIAGE_FEATURES), va = toMatrix(val, TRIAGE_FEATURES);
        const npos = tr.y.filter((v) => v === 1).length, nneg = tr.y.filter((v) => v === 0).length;
        if (npos < 3 || nneg < 3) throw new Error(`need >= 3 labels of each class (have ${npos} confirmed, ${nneg} false positive)`);
        const art = fitLogistic(tr.X, tr.y, tr.w, TRIAGE_FEATURES);
        step("candidate fitted", { model_type: "logistic_l2" });
        const prod = st.models.find((m) => m.task === task && m.status === "PRODUCTION");
        const cand = predict(art, va.X);
        const prodScores = !prod || prod.model_type === "rules" ? rulesScore(va.X) : predict(prod.artifact as ModelArtifact, va.X);
        if (!prod || prod.model_type === "rules") step("comparing against the production rule baseline");
        const gate = evaluateGate(cand, prodScores, va.y, va.groups, va.subgroups, frozen, current, modelTests(art, va.X));
        step("gate evaluated", { passed: gate.passed });
        const versions = st.models.filter((m) => m.task === task).map((m) => m.version)
          .sort((a, b) => { const pa = a.split(".").map(Number), pb = b.split(".").map(Number); return pa[0] - pb[0] || pa[1] - pb[1] || pa[2] - pb[2]; });
        const version = nextVersion(versions[versions.length - 1]);
        const mc = gate.summary.candidate as Record<string, number>;
        const model: ModelRecord = {
          id: `${task}-${version}`, task, version, model_type: "logistic_l2", created_at: now(),
          training_dataset_version: await datasetHash(train), validation_dataset_hash: current, feature_set: TRIAGE_FEATURES,
          params: art.extra || {}, artifact: art, status: "CANDIDATE", parent_model: prod?.id || null,
          notes: `Trained in this workspace by job ${job.id} on ${train.length} labels (${[...new Set(train.map((l) => l.source))].sort().join(", ")}).`,
          gate, promoted_by: null, promoted_at: null,
          metrics: ["auroc", "auprc", "f1", "precision", "recall", "brier", "ece"].map((k) => ({ split: "validation", subgroup: "all", metric: k, value: mc[k] ?? null, n: mc.n })),
        };
        st.models.unshift(model);
        await this.appendAudit("trainer", "model.register", "model", model.id, { task, status: "CANDIDATE", parent: model.parent_model });
        step("candidate registered", { model_id: model.id });
        Object.assign(job, { status: "SUCCEEDED", finished_at: now(), dataset_version: model.training_dataset_version,
          n_train: train.length, n_validation: val.length, candidate_model_id: model.id });
      } catch (e) {
        step("failed", { error: (e as Error).message });
        Object.assign(job, { status: "FAILED", finished_at: now(), error: (e as Error).message });
      }
      await this.appendAudit("trainer", "training.status", "training_job", job.id, { status: job.status, candidate: job.candidate_model_id });
      return clone(job);
    });
  }

  async jobs() { return clone((await this.load()).jobs); }
  async models(task?: string) { const st = await this.load(); return clone(st.models.filter((m) => !task || m.task === task)); }
  async model(id: string) { const st = await this.load(); const m = st.models.find((x) => x.id === id); return m ? clone(m) : null; }

  private async setStatus(st: State, m: ModelRecord, status: ModelRecord["status"], actor: string, note = "") {
    let retired: string | null = null;
    if (status === "PRODUCTION") {
      const prev = st.models.find((x) => x.task === m.task && x.status === "PRODUCTION" && x.id !== m.id);
      if (prev) { prev.status = "RETIRED"; retired = prev.id; }
      m.promoted_by = actor; m.promoted_at = now();
    }
    const from = m.status;
    m.status = status;
    await this.appendAudit(actor, `model.${status.toLowerCase()}`, "model", m.id, { from, to: status, retired, note, gate_passed: m.gate?.passed ?? null });
    return clone(m);
  }

  async promote(id: string, approvedBy: string, note = "") {
    return this.write(async (st) => {
      const m = st.models.find((x) => x.id === id);
      if (!m) throw new Error(`not found: ${id}`);
      if (SYSTEM_ACTORS.has((approvedBy || "").trim().toLowerCase())) throw new Error("promotion requires a named human approver");
      if (!["CANDIDATE", "STAGING"].includes(m.status)) throw new Error(`only CANDIDATE/STAGING models can be promoted (is ${m.status})`);
      if (!m.gate?.passed) throw new Error(`gate not passed: ${(m.gate?.checks || []).filter((c) => !c.passed).map((c) => c.name).join(", ") || "no gate report"}`);
      m.gate = { ...m.gate, human_approval: { required: true, approved_by: approvedBy.trim(), at: now(), note } };
      return this.setStatus(st, m, "PRODUCTION", approvedBy.trim(), note);
    });
  }

  async reject(id: string, actor: string, note = "") {
    return this.write(async (st) => {
      const m = st.models.find((x) => x.id === id);
      if (!m) throw new Error(`not found: ${id}`);
      if (m.status === "PRODUCTION") throw new Error("cannot reject the production model; roll back instead");
      return this.setStatus(st, m, "REJECTED", actor, note);
    });
  }

  async rollback(id: string, actor: string, note = "") {
    return this.write(async (st) => {
      const m = st.models.find((x) => x.id === id);
      if (!m) throw new Error(`not found: ${id}`);
      if (SYSTEM_ACTORS.has((actor || "").trim().toLowerCase())) throw new Error("rollback requires a named human");
      if (!["RETIRED", "STAGING"].includes(m.status)) throw new Error(`can only roll back to a RETIRED model (is ${m.status})`);
      return this.setStatus(st, m, "PRODUCTION", actor, `rollback: ${note}`);
    });
  }

  // ------------------------------------------------------------ audit etc.
  async audit(entityType?: string, entityId?: string, limit = 200) {
    const st = await this.load();
    return clone(st.audit.filter((a) => (!entityType || a.entity_type === entityType) && (!entityId || a.entity_id === entityId)).slice(-limit).reverse());
  }

  private async appendAudit(actor: string, action: string, entity_type: string, entity_id: string, detail: Record<string, unknown>) {
    const st = this.state!;
    const prev = st.audit.length ? st.audit[st.audit.length - 1].hash : GENESIS;
    const ev = { at: now(), actor, action, entity_type, entity_id, detail };
    const hash = await sha256Hex(prev + canon(ev));
    st.audit.push({ seq: st.audit.length + 1, ...ev, prev_hash: prev, hash });
    return hash;
  }

  async verifyAudit() {
    const st = await this.load();
    let prev = GENESIS;
    for (const a of st.audit) {
      const ev = { at: a.at, actor: a.actor, action: a.action, entity_type: a.entity_type, entity_id: a.entity_id, detail: a.detail };
      const h = await sha256Hex(prev + canon(ev));
      if (a.prev_hash !== prev || a.hash !== h) return { ok: false, n: st.audit.length, first_bad_seq: a.seq };
      prev = h;
    }
    return { ok: true, n: st.audit.length, head: prev };
  }

  async alerts() { return clone((await this.load()).alerts).sort((a, b) => (a.created_at < b.created_at ? 1 : -1)); }
  async ackAlert(id: string, actor: string) {
    await this.write(async (st) => {
      const a = st.alerts.find((x) => x.id === id);
      if (a) { a.acknowledged_by = actor; a.acknowledged_at = now(); await this.appendAudit(actor, "alert.ack", "alert", id, {}); }
    });
  }

  async aois() { return clone((await this.load()).aois); }
  async addAoi(aoi: Omit<Aoi, "id"> & { id?: string }, actor: string): Promise<Aoi> {
    return this.write(async (st) => {
      const [x0, y0, x1, y1] = aoi.bbox;
      if (!(x1 > x0 && y1 > y0) || x1 - x0 > 3 || y1 - y0 > 3) throw new Error("AOI must be a valid box no larger than 3 degrees");
      const row: Aoi = { ...aoi, id: aoi.id || `AE-USER-${Math.random().toString(36).slice(2, 7).toUpperCase()}`, status: "MONITORING", created_by: actor };
      st.aois.push(row);
      await this.appendAudit(actor, "aoi.create", "aoi", row.id, { bbox: row.bbox, name: row.name });
      return clone(row);
    });
  }

  async assets() { return clone((await this.load()).assets); }
  async addAsset(a: Omit<AssetRow, "id" | "source"> & { id?: string }, actor: string): Promise<AssetRow> {
    return this.write(async (st) => {
      if (!a.name?.trim()) throw new Error("asset name is required");
      const row: AssetRow = { ...a, id: a.id || `OP-${Math.random().toString(36).slice(2, 8).toUpperCase()}`, source: "operator" };
      st.assets.push(row);
      await this.appendAudit(actor, "asset.create", "asset", row.id, { name: row.name, type: row.type, lon: row.lon, lat: row.lat });
      return clone(row);
    });
  }

  /** Admin transition (resolve / reopen). */
  async transition(id: string, to: IncidentStatus, actor: string, reason = "") {
    return this.write(async (st) => {
      const inc = st.incidents[id];
      if (!inc) throw new Error(`not found: ${id}`);
      const from = inc.status;
      inc.status = adminTransition(from, to);
      inc.updated_at = now();
      await this.appendAudit(actor, "incident.transition", "incident", id, { from, to, reason });
      return (await this.getIncidentFrom(st, id))!;
    });
  }
}
