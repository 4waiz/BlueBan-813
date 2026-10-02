"use client";
/**
 * FIELD OPS: turn an incident into a sampling mission and bring the results back.
 * Sample points come from pipeline/sampling.py (role + question per point);
 * operators move, add or remove them, record collection, enter measurements or
 * upload a lab CSV. Every step is persisted and audited.
 */
import React, { Suspense, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { Download, FlaskConical, MapPinned, Plus, Trash2, Upload } from "lucide-react";
import { getOperator, mutate, useEngineQuery, useStatic } from "@/lib/engine";
import type { Sample } from "@/lib/engine/types";
import { MEASUREMENT_PARAMETERS, PARAMETER_LABEL } from "@/lib/engine/rules";
import { Chip, fmt, Modal, Panel, statusText, toast } from "@/components/ui";
import { download } from "@/lib/report";

const IncidentMap = dynamic(() => import("@/components/map/IncidentMap"), { ssr: false });
const ROLE_COLOR: Record<string, string> = { CORE: "#FF4D5E", EDGE: "#FFC23D", BACKGROUND: "#23D484", UNCERTAINTY: "#8B7BFF", ASSET_BOUNDARY: "#27C3F3" };
const ROLE_HINT: Record<string, string> = {
  CORE: "Strongest signal: what is in the water?",
  EDGE: "Edge of the patch: is it spreading?",
  BACKGROUND: "Clean water to compare against. Always kept.",
  UNCERTAINTY: "Where the satellite reading is least certain",
  ASSET_BOUNDARY: "Next to an asset at risk: has it reached it?",
};

function Field() {
  const router = useRouter();
  const id = useSearchParams().get("id");
  const list = useEngineQuery((e) => e.listIncidents());
  const operational = (list.data || []).filter((i) => i.role !== "negative_control");
  const iid = id || operational[0]?.id || list.data?.[0]?.id || null;
  const q = useEngineQuery((e) => (iid ? e.getIncident(iid) : Promise.resolve(null)), [iid]);
  const aois = useEngineQuery((e) => e.aois());
  const assets = useEngineQuery((e) => e.assets());
  const stations = useStatic<GeoJSON.FeatureCollection>("registers/stations_ead.geojson");
  const inc = q.data;
  const [entry, setEntry] = useState<Sample | null>(null);
  const [form, setForm] = useState({ parameter: "chlorophyll_a", value: "", unit: "mg m-3", method: "", measured_at: "" });
  const fileRef = useRef<HTMLInputElement>(null);
  const samples = inc?.samples || [];
  const meas = inc?.measurements || [];

  const op = () => { const o = getOperator(); if (!o) toast("Set your operator name first (top-right avatar)", "err"); return o; };
  const patch = async (s: Sample, p: Partial<Pick<Sample, "lon" | "lat" | "status" | "role">>, msg: string) => {
    const o = op(); if (!o) return;
    try { await mutate((e) => e.patchSample(s.id, o, p)); toast(msg); } catch (e) { toast((e as Error).message, "err"); }
  };
  const addPoint = async (lon: number, lat: number) => {
    const o = op(); if (!o || !inc) return;
    const keep = samples.map((s) => ({ code: s.code, role: s.role, lon: s.lon, lat: s.lat, question: s.question || undefined, analytes: s.analytes, rationale: s.rationale || undefined }));
    const n = Math.max(0, ...samples.map((s) => Number(s.code.slice(1)) || 0)) + 1;
    keep.push({ code: `S${String(n).padStart(2, "0")}`, role: "UNCERTAINTY", lon, lat, question: "Operator-added point", analytes: ["Chlorophyll-a", "Turbidity (NTU)"], rationale: `Added by ${o}` });
    try { await mutate((e) => e.planSamples(inc.id, o, keep)); toast("Sample point added"); } catch (e) { toast((e as Error).message, "err"); }
  };
  const saveMeasurement = async () => {
    const o = op(); if (!o || !inc || !entry) return;
    try {
      await mutate((e) => e.addMeasurement(inc.id, { actor: o, parameter: form.parameter, value: Number(form.value), unit: form.unit, sample_id: entry.id, method: form.method || null, measured_at: form.measured_at || null }));
      toast(`${PARAMETER_LABEL[form.parameter]} saved for ${entry.code}`); setEntry(null); setForm({ ...form, value: "" });
    } catch (e) { toast((e as Error).message, "err"); }
  };
  const uploadCsv = async (f: File) => {
    const o = op(); if (!o || !inc) return;
    const text = await f.text();
    try { const r = await mutate((e) => e.importLabCsv(inc.id, o, text)); toast(`${r.imported} lab rows imported${r.rejected.length ? `, ${r.rejected.length} rejected (check line ${r.rejected.map((x) => x.line).join(", ")})` : ""}`, r.rejected.length ? "err" : "ok"); }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const csv = () => {
    if (!inc) return;
    const rows = [["incident_id", "sample_id", "code", "role", "lat", "lon", "status", "question", "analytes"],
      ...samples.map((s) => [inc.id, s.id, s.code, s.role, s.lat.toFixed(6), s.lon.toFixed(6), s.status, (s.question || "").replace(/,/g, ";"), (s.analytes || []).join("; ")])];
    download(`${inc.id}_samples.csv`, rows.map((r) => r.join(",")).join("\n"), "text/csv");
  };
  const geojson = () => {
    if (!inc) return;
    download(`${inc.id}_samples.geojson`, JSON.stringify({ type: "FeatureCollection", properties: { incident_id: inc.id }, features: samples.map((s) => ({ type: "Feature", geometry: { type: "Point", coordinates: [s.lon, s.lat] }, properties: { id: s.id, code: s.code, role: s.role, status: s.status, question: s.question } })) }, null, 1), "application/geo+json");
  };
  const chl = meas.filter((m) => m.parameter === "chlorophyll_a").length;
  const tur = meas.filter((m) => m.parameter === "turbidity").length;

  return (
    <div className="grid h-full min-h-0 gap-3 p-3 short:gap-2 short:p-2 xl:grid-cols-[minmax(0,1fr)_470px]">
      <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-3">
        <div className="panel flex flex-wrap items-center gap-3 px-4 py-3">
          <MapPinned size={18} className="text-cyan" />
          <select value={iid || ""} onChange={(e) => router.replace(`/field?id=${e.target.value}`)} className="rounded-md border border-line bg-deep px-3 py-1.5 text-[12.5px]">
            {(list.data || []).map((i) => <option key={i.id} value={i.id}>{i.id} · {statusText(i.status)}</option>)}
          </select>
          {inc && <Chip label={inc.status} />}
          <div className="ml-auto flex gap-2">
            <button onClick={csv} className="btn px-3 py-1.5" title="Download the sample plan as a spreadsheet (CSV)"><Download size={14} /> CSV</button>
            <button onClick={geojson} className="btn px-3 py-1.5" title="Download the sample plan for map software (GeoJSON)"><Download size={14} /> GeoJSON</button>
            <button onClick={() => fileRef.current?.click()} className="btn btn-primary px-3 py-1.5" title="Upload a CSV file of lab results"><Upload size={14} /> Upload lab results</button>
            <input ref={fileRef} name="lab-csv" type="file" accept=".csv,text/csv" hidden onChange={(e) => e.target.files?.[0] && uploadCsv(e.target.files[0])} />
          </div>
        </div>
        <div className="panel relative min-h-[360px] overflow-hidden p-0">
          <IncidentMap incident={inc || null} incidents={list.data || []} aois={aois.data || []} assets={assets.data || []} stations={stations.data} samples={samples}
            onMoveSample={(s, lon, lat) => patch(s, { lon, lat }, `${s.code} moved`)} onPlaceAsset={addPoint} placeLabel="Add a sample point" initialMode="2d" showTimeline={false} />
          <div className="map-pill absolute bottom-3 left-14 z-10">Drag a point to move it. Add one with the pin tool (map toolbar).</div>
        </div>
      </div>
      <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-3">
        <Panel title="Sample plan" kicker={`${samples.length} points · always includes a clean-water reference`} bodyClass="overflow-y-auto p-3 space-y-2">
          {samples.map((s) => (
            <div key={s.id} className="rounded-lg border border-edge bg-deep/60 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2"><span className="hud-value text-[15px] font-bold">{s.code}</span><span className="rounded px-1.5 py-0.5 text-[10px] font-bold" title={ROLE_HINT[s.role]} style={{ color: ROLE_COLOR[s.role] || "#EAF1FF", border: `1px solid ${ROLE_COLOR[s.role] || "#EAF1FF"}55` }}>{s.role.replace(/_/g, " ")}</span></div>
                <Chip label={s.status} />
              </div>
              <div className="mt-1 text-[12px]">{s.question}</div>
              <div className="hud-value text-[10.5px] text-dim">{s.lat.toFixed(5)}, {s.lon.toFixed(5)}</div>
              {s.analytes && s.analytes.length > 0 && <div className="mt-1 text-[11px] text-muted">Tests: {s.analytes.join(" · ")}</div>}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {s.status === "PLANNED" && <button className="btn px-2 py-1 text-[11px]" onClick={() => patch(s, { status: "COLLECTED" }, `${s.code} marked collected`)}>Mark collected</button>}
                {s.status === "COLLECTED" && <button className="btn px-2 py-1 text-[11px]" onClick={() => patch(s, { status: "LAB_PENDING" }, `${s.code} sent to lab`)}>Mark sent to lab</button>}
                <button className="btn btn-primary px-2 py-1 text-[11px]" onClick={() => setEntry(s)}><FlaskConical size={12} /> Enter result</button>
                {s.role !== "BACKGROUND" && s.status === "PLANNED" && <button className="btn btn-bad px-2 py-1 text-[11px]" title="Remove this point" aria-label="Remove this point" onClick={() => patch(s, { status: "REMOVED" }, `${s.code} removed`)}><Trash2 size={12} /></button>}
              </div>
            </div>
          ))}
          {!samples.length && <p className="text-[12.5px] text-muted">No sample points yet. Add one with the pin tool on the map.</p>}
          <button className="btn w-full" onClick={() => toast("Pick the pin tool in the map toolbar, then click the map", "info")}><Plus size={14} /> Add a point on the map</button>
        </Panel>
        <Panel title="Results & calibration" bodyClass="p-3 space-y-2 text-[12px]">
          <div className="max-h-[150px] overflow-y-auto">
            {meas.map((m) => <div key={m.id} className="kv py-1"><span>{PARAMETER_LABEL[m.parameter] || m.parameter} · {m.sample_id?.split("-").pop() || "no point"}</span><span className="hud-value">{m.value} {m.unit} <span className="text-dim">({m.source}, {m.entered_by})</span></span></div>)}
            {!meas.length && <div className="text-muted">No results yet.</div>}
          </div>
          <div className="rounded-md border border-edge bg-deep/60 p-2 text-[11.5px] text-muted" title="Real units also need proven skill: grouped cross-validation R² ≥ 0.4, with the confidence interval above zero (pipeline/quantify.py).">
            Until samples calibrate it, BlueBan shows an <b>index</b>, not a lab value. Real units (mg m⁻³, NTU) need <b>20+ matched results from 5+ separate days or stations</b>. This incident so far: {chl} chlorophyll-a, {tur} turbidity. Each result also becomes a training case for LEARN.
          </div>
        </Panel>
      </div>
      <Modal open={!!entry} onClose={() => setEntry(null)} title={`Enter result · ${entry?.code || ""}`} width={440}>
        <div className="space-y-2 text-[12.5px]">
          <select name="parameter" value={form.parameter} onChange={(e) => setForm({ ...form, parameter: e.target.value, unit: MEASUREMENT_PARAMETERS[e.target.value][0] })} className="w-full rounded-md border border-line bg-deep px-3 py-2">
            {Object.keys(MEASUREMENT_PARAMETERS).map((p) => <option key={p} value={p}>{PARAMETER_LABEL[p]}</option>)}
          </select>
          <div className="grid grid-cols-[1fr_140px] gap-2">
            <input name="value" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} placeholder="Value" inputMode="decimal" className="rounded-md border border-line bg-deep px-3 py-2 outline-none focus:border-beam2" />
            <select name="unit" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} className="rounded-md border border-line bg-deep px-3 py-2">{MEASUREMENT_PARAMETERS[form.parameter].map((u) => <option key={u}>{u}</option>)}</select>
          </div>
          <input name="method" value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })} placeholder="Method, optional (e.g. HPLC, fluorometer)" className="w-full rounded-md border border-line bg-deep px-3 py-2 outline-none focus:border-beam2" />
          <input name="measured_at" type="datetime-local" title="When it was measured (optional)" aria-label="When it was measured (optional)" value={form.measured_at} onChange={(e) => setForm({ ...form, measured_at: e.target.value })} className="w-full rounded-md border border-line bg-deep px-3 py-2" />
          <p className="text-[11px] text-dim">We check the unit fits and refuse negative concentrations. The incident goes back to review when results arrive.</p>
          <div className="flex justify-end gap-2"><button className="btn" onClick={() => setEntry(null)}>Cancel</button><button className="btn btn-primary" disabled={!form.value} onClick={saveMeasurement}>Save result</button></div>
        </div>
      </Modal>
    </div>
  );
}

export default function Page() { return <Suspense><Field /></Suspense>; }
