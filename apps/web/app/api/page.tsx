"use client";
/**
 * API - the contract every screen uses.
 *
 * Self-hosted, the screens talk to FastAPI (services/api, SQLite with a
 * DATABASE_URL for PostgreSQL). Hosted, the same Engine interface runs in the
 * browser against a per-visitor workspace. This page lists the HTTP contract
 * and, when connected to a server, lets you call the read endpoints.
 */
import React, { useState } from "react";
import { Check, Copy, Play } from "lucide-react";
import { DATA_MODE } from "@/lib/engine";
import { Chip, Panel } from "@/components/ui";

type Ep = { m: "GET" | "POST" | "PUT" | "PATCH"; p: string; d: string; body?: string };
const GROUPS: { tag: string; task: string; eps: Ep[] }[] = [
  { tag: "incidents", task: "Open an incident · Export a report", eps: [
    { m: "GET", p: "/api/incidents", d: "List incidents: status, area, priority, time seen" },
    { m: "GET", p: "/api/incidents/{id}", d: "One incident in full: evidence, sources, samples, reviews, next steps" },
    { m: "GET", p: "/api/incidents/{id}/report", d: "Incident report in Markdown" },
  ] },
  { tag: "verify", task: "Review · Correct · Close an incident", eps: [
    { m: "POST", p: "/api/incidents/{id}/review", d: "Record a review. CONFIRM, FALSE_POSITIVE and RECLASSIFY create a verified label", body: '{"reviewer":"A. Analyst","decision":"CONFIRM","note":"…","evidence_viewed":["spectrum"]}' },
    { m: "POST", p: "/api/incidents/{id}/transition", d: "Change the status (e.g. RESOLVED). Logged in the audit log", body: '{"to":"RESOLVED","actor":"A. Analyst","reason":"…"}' },
  ] },
  { tag: "field", task: "Plan samples · Export the plan · Enter results", eps: [
    { m: "PUT", p: "/api/incidents/{id}/samples", d: "Replace the sample plan", body: '{"actor":"…","points":[{"role":"CORE","lon":56.45,"lat":25.11}]}' },
    { m: "PATCH", p: "/api/samples/{sid}", d: "Move a sample point or update its status", body: '{"actor":"…","status":"COLLECTED"}' },
    { m: "GET", p: "/api/incidents/{id}/samples.csv", d: "Sample plan as CSV" },
    { m: "GET", p: "/api/incidents/{id}/samples.geojson", d: "Sample plan as GeoJSON" },
    { m: "GET", p: "/api/measurements/parameters", d: "Accepted measurements and units" },
    { m: "POST", p: "/api/incidents/{id}/measurements", d: "Add one field or lab measurement", body: '{"actor":"…","parameter":"chlorophyll_a","value":12.4,"unit":"mg/m3","sample_id":"…"}' },
    { m: "POST", p: "/api/incidents/{id}/measurements/csv", d: "Import lab results from CSV, checked line by line" },
  ] },
  { tag: "learn", task: "Train a new model · Compare · Make it live", eps: [
    { m: "GET", p: "/api/labels/summary", d: "Label counts by source, class and train/test set" },
    { m: "GET", p: "/api/labels", d: "Verified labels with their saved feature values" },
    { m: "POST", p: "/api/training/retrain", d: "Train a new model. The safety check uses the held-back test set", body: '{"task":"triage","requested_by":"…"}' },
    { m: "GET", p: "/api/training/jobs", d: "Training jobs and their logs" },
    { m: "GET", p: "/api/models", d: "All models by status: PRODUCTION, CANDIDATE, REJECTED, RETIRED" },
    { m: "GET", p: "/api/models/{id}/compare", d: "New model vs live model on the same held-back test set" },
    { m: "POST", p: "/api/models/{id}/promote", d: "Make a model live. Needs a passed safety check and a named approver", body: '{"approved_by":"A. Analyst","note":"…"}' },
    { m: "POST", p: "/api/models/{id}/reject", d: "Reject a new model" },
    { m: "POST", p: "/api/models/{id}/rollback", d: "Bring back the previous live model" },
  ] },
  { tag: "audit · alerts · watch", task: "Check the audit log · Watch an area", eps: [
    { m: "GET", p: "/api/audit", d: "Tamper-proof log of every action" },
    { m: "GET", p: "/api/audit/verify", d: "Check the log for tampering. Reports the first broken event" },
    { m: "GET", p: "/api/alerts", d: "Operator alerts" },
    { m: "POST", p: "/api/alerts/{id}/ack", d: "Acknowledge an alert" },
    { m: "GET", p: "/api/aois", d: "Monitored areas, with satellite pass times and status" },
    { m: "GET", p: "/api/watch/{aoi_id}", d: "One area's readings over time, by season" },
  ] },
];
const MC: Record<string, string> = { GET: "#23D484", POST: "#2F7BFF", PUT: "#FFC23D", PATCH: "#FF8A3D" };

export default function ApiPage() {
  const [path, setPath] = useState("/api/incidents");
  const [out, setOut] = useState<string>("");
  const [copied, setCopied] = useState<string | null>(null);
  const live = DATA_MODE === "live";
  const run = async () => {
    setOut("…");
    try { const r = await fetch(path); const t = await r.text(); try { setOut(`${r.status}\n${JSON.stringify(JSON.parse(t), null, 2).slice(0, 20000)}`); } catch { setOut(`${r.status}\n${t.slice(0, 20000)}`); } }
    catch (e) { setOut(String(e)); }
  };
  return (
    <div className="grid h-full min-h-0 gap-3 overflow-hidden p-3 short:p-2 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <Panel title="API endpoints" kicker="services/api (FastAPI) · interactive docs at /docs" right={<Chip label={live ? "CONNECTED TO SERVER" : "HOSTED: RUNS IN YOUR BROWSER"} color={live ? "#23D484" : "#FFC23D"} />} bodyClass="min-h-0 overflow-y-auto p-3">
        {GROUPS.map((g) => (
          <div key={g.tag} className="mb-3">
            <div className="mb-1 flex items-baseline gap-2"><span className="hud-kicker">{g.tag}</span><span className="text-[11px] text-dim">{g.task}</span></div>
            {g.eps.map((e) => (
              <div key={e.m + e.p} className="mb-1 grid grid-cols-[62px_minmax(0,1fr)_auto] items-start gap-2 rounded-md border border-edge bg-deep/50 px-2 py-1.5 text-[12px]">
                <span className="hud-value font-bold" style={{ color: MC[e.m] }}>{e.m}</span>
                <div className="min-w-0"><div className="hud-value truncate text-ink">{e.p}</div><div className="text-[11px] text-muted">{e.d}</div>{e.body && <div className="hud-value mt-0.5 truncate text-[10.5px] text-dim">{e.body}</div>}</div>
                <div className="flex gap-1">
                  {e.m === "GET" && !e.p.includes("{") && <button className="btn px-1.5 py-1" title="Try in console" onClick={() => setPath(e.p)}><Play size={12} /></button>}
                  <button className="btn px-1.5 py-1" title="Copy curl command" onClick={() => { navigator.clipboard?.writeText(`curl -X ${e.m} http://localhost:8813${e.p}${e.body ? ` -H 'content-type: application/json' -d '${e.body}'` : ""}`); setCopied(e.p); setTimeout(() => setCopied(null), 1200); }}>{copied === e.p ? <Check size={12} /> : <Copy size={12} />}</button>
                </div>
              </div>))}
          </div>))}
      </Panel>
      <Panel title="Console" kicker={live ? "Try read-only calls on this server" : "Needs the self-hosted server"} bodyClass="flex min-h-0 flex-col gap-2 p-3">
        {live ? <>
          <div className="flex gap-2"><input value={path} onChange={(e) => setPath(e.target.value)} className="hud-value flex-1 rounded-md border border-line bg-deep px-2 py-1.5 text-[12px]" /><button className="btn btn-primary" onClick={run} disabled={!path.startsWith("/api/")}><Play size={14} /> GET</button></div>
          <pre className="min-h-0 flex-1 overflow-auto rounded-md border border-edge bg-deep p-3 font-mono text-[11px] text-muted">{out || "Pick a GET endpoint or type a path."}</pre>
        </> : (
          <div className="space-y-2 text-[12.5px] text-muted">
            <p>This hosted demo has no server. Every screen runs the same engine in your browser, on a copy of the pipeline results. To use the HTTP API and a database, run the full stack locally:</p>
            <pre className="rounded-md border border-edge bg-deep p-3 font-mono text-[11.5px] text-ink">{`pip install -e .
python scripts/seed_db.py
uvicorn services.api.main:app --port 8813
cd apps/web && NEXT_PUBLIC_DATA_MODE=live npm run dev`}</pre>
            <p>API docs are then at <span className="hud-value text-ink">http://localhost:8813/docs</span>. Set DATABASE_URL to use PostgreSQL.</p>
          </div>)}
      </Panel>
    </div>
  );
}
