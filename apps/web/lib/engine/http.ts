/**
 * HttpEngine: the closed loop against the FastAPI + SQLite backend
 * (services/api). Used when the app runs next to the Python service.
 */
import type {
  Aoi, Alert, AssetRow, AuditEvent, Engine, Incident, IncidentStatus, IncidentSummary, LabelRow,
  Measurement, MeasurementInput, ModelRecord, ReviewInput, Sample, SampleInput, TrainingJob,
} from "./types";

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { ...init, headers: { "content-type": "application/json", ...(init?.headers || {}) } });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { const b = await r.json(); msg = b.detail ? (typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail)) : msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}
const post = <T>(url: string, body: unknown) => j<T>(url, { method: "POST", body: JSON.stringify(body) });

export class HttpEngine implements Engine {
  readonly mode = "live" as const;
  constructor(private base = "/api") {}
  listIncidents = async () => (await j<{ incidents: IncidentSummary[] }>(`${this.base}/incidents`)).incidents;
  getIncident = async (id: string) => { try { return await j<Incident>(`${this.base}/incidents/${encodeURIComponent(id)}`); } catch { return null; } };
  review = (id: string, b: ReviewInput) => post<{ review_id: string; status_before: IncidentStatus; status_after: IncidentStatus; label_id: string | null; incident: Incident }>(`${this.base}/incidents/${encodeURIComponent(id)}/review`, b);
  planSamples = async (id: string, actor: string, points: SampleInput[]) => (await j<{ samples: Sample[] }>(`${this.base}/incidents/${encodeURIComponent(id)}/samples`, { method: "PUT", body: JSON.stringify({ actor, points }) })).samples;
  patchSample = (sid: string, actor: string, patch: Partial<Pick<Sample, "lon" | "lat" | "status" | "role">>) => j<Sample>(`${this.base}/samples/${encodeURIComponent(sid)}`, { method: "PATCH", body: JSON.stringify({ actor, ...patch }) });
  addMeasurement = (id: string, b: MeasurementInput) => post<Measurement>(`${this.base}/incidents/${encodeURIComponent(id)}/measurements`, b);
  importLabCsv = (id: string, actor: string, csv: string) => post<{ imported: number; rejected: { line: number; error: string }[] }>(`${this.base}/incidents/${encodeURIComponent(id)}/measurements/csv`, { actor, csv });
  retrain = (task: string, requested_by: string) => post<TrainingJob>(`${this.base}/training/retrain`, { task, requested_by });
  jobs = async () => (await j<{ jobs: TrainingJob[] }>(`${this.base}/training/jobs`)).jobs;
  models = async (task?: string) => (await j<{ models: ModelRecord[] }>(`${this.base}/models${task ? `?task=${encodeURIComponent(task)}` : ""}`)).models;
  model = async (id: string) => { try { return await j<ModelRecord>(`${this.base}/models/${encodeURIComponent(id)}`); } catch { return null; } };
  promote = (id: string, approved_by: string, note = "") => post<ModelRecord>(`${this.base}/models/${encodeURIComponent(id)}/promote`, { approved_by, note });
  reject = (id: string, actor: string, note = "") => post<ModelRecord>(`${this.base}/models/${encodeURIComponent(id)}/reject`, { actor, note });
  rollback = (id: string, actor: string, note = "") => post<ModelRecord>(`${this.base}/models/${encodeURIComponent(id)}/rollback`, { actor, note });
  labels = async (task = "triage") => (await j<{ labels: LabelRow[] }>(`${this.base}/labels?task=${encodeURIComponent(task)}`)).labels;
  audit = async (entityType?: string, entityId?: string, limit = 200) => {
    const q = new URLSearchParams();
    if (entityType) q.set("entity_type", entityType);
    if (entityId) q.set("entity_id", entityId);
    q.set("limit", String(limit));
    return (await j<{ events: AuditEvent[] }>(`${this.base}/audit?${q}`)).events;
  };
  verifyAudit = () => j<{ ok: boolean; n: number; head?: string; first_bad_seq?: number }>(`${this.base}/audit/verify`);
  alerts = async () => (await j<{ alerts: Alert[] }>(`${this.base}/alerts`)).alerts;
  ackAlert = async (id: string, actor: string) => { await post(`${this.base}/alerts/${encodeURIComponent(id)}/ack`, { actor }); };
  aois = async () => (await j<{ aois: Aoi[] }>(`${this.base}/aois`)).aois;
  addAoi = (aoi: Omit<Aoi, "id"> & { id?: string }, actor: string) => post<Aoi>(`${this.base}/aois`, { ...aoi, actor });
  assets = async () => (await j<{ assets: AssetRow[] }>(`${this.base}/assets`)).assets;
  addAsset = (a: Omit<AssetRow, "id" | "source"> & { id?: string }, actor: string) => post<AssetRow>(`${this.base}/assets`, { ...a, actor });
}
