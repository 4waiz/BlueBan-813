"use client";
import React, { useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, FlaskConical, RefreshCcw, ShieldAlert, X } from "lucide-react";
import type { Decision, EventType, Incident } from "@/lib/engine/types";
import { EVENT_TYPES } from "@/lib/engine/rules";
import { getOperator, mutate, pipelineUrl } from "@/lib/engine";
import { Chip, fmt, Kind, Meter, Modal, SimBadge, Tabs, toast, WhyButton } from "@/components/ui";
import SpectrumPlot from "@/components/spectra/SpectrumPlot";

type Tab = "overview" | "spectral" | "temporal" | "assets" | "actions";

export function Provenance({ inc }: { inc: Incident }) {
  return (
    <div className="space-y-3 text-[12.5px]">
      <p className="text-muted">Every value on this incident traces to these inputs and this model. Nothing is typed into the interface.</p>
      <div className="panel-flat p-3">
        <div className="hud-kicker">Model</div>
        <div>{inc.model_id} · raised {fmt.utc(inc.detected_at)}</div>
      </div>
      {(inc.provenance?.sources || []).map((s, i) => (
        <div key={i} className="panel-flat p-3">
          <div className="font-semibold">{s.sensor || s.satellite} <span className="text-muted">· {s.product}</span></div>
          <div className="text-muted">Scene {s.scene_id}</div>
          <div className="text-muted">Acquired {fmt.utc(s.acquisition_utc)} · {s.processing_level}</div>
          <div className="text-muted">Provider {s.provider} · Licence {s.licence}</div>
          {s.quality_mask && <div className="text-muted">Quality mask: {s.quality_mask}</div>}
          {s.notes && <div className="mt-1 text-dim">{s.notes}</div>}
        </div>
      ))}
      {inc.provenance?.algorithm && <pre className="panel-flat overflow-x-auto p-3 text-[10.5px] text-muted">{JSON.stringify(inc.provenance.algorithm, null, 1)}</pre>}
    </div>
  );
}

export default function IncidentPanel({ inc, index, total, onPrev, onNext, onOpenTimeline }: {
  inc: Incident | null; index: number; total: number; onPrev?: () => void; onNext?: () => void; onOpenTimeline?: () => void;
}) {
  const [tab, setTab] = useState<Tab>("overview");
  const [busy, setBusy] = useState<string | null>(null);
  const [reclass, setReclass] = useState(false);
  const [note, setNote] = useState("");
  const [newType, setNewType] = useState<EventType>("SEDIMENT_LIKE");
  const [viewed, setViewed] = useState<Set<string>>(new Set(["overview"]));

  const wq = inc?.water_quality?.features || {};
  const est = inc?.water_quality?.estimates || {};
  const agree = inc?.sensor_agreement || {};
  const nearest = useMemo(() => [...(inc?.exposure || [])].sort((a, b) => a.distance_m - b.distance_m)[0], [inc]);

  if (!inc) return <div className="panel grid h-full place-items-center text-muted">No incident selected</div>;
  const color = inc.role === "negative_control" ? "#8B7BFF" : inc.status === "UNDER_REVIEW" || inc.status === "DETECTED" ? "#FF4D5E" : "#FFC23D";

  const act = async (decision: Decision, extra: { new_hypothesis?: string } = {}) => {
    const reviewer = getOperator();
    if (!reviewer) { toast("Set your operator name first (top-right avatar). Every decision is audited.", "err"); return; }
    setBusy(decision);
    try {
      const r = await mutate((e) => e.review(inc.id, { reviewer, decision, note, evidence_viewed: [...viewed], ...extra }));
      toast(`${decision.replace(/_/g, " ")} recorded · ${r.status_before} → ${r.status_after}${r.label_id ? " · verified label added to LEARN" : ""}`);
      setNote(""); setReclass(false);
    } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(null); }
  };

  const setT = (t: Tab) => { setTab(t); setViewed((v) => new Set(v).add(t)); };
  const thumb = inc.layers?.rasters.find((r) => r.key === "ndci") || inc.layers?.rasters.find((r) => r.key === "rgb");

  return (
    <section className="panel flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between px-4 pb-2 pt-3">
        <h2 className="panel-title">Incident</h2>
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <button onClick={onPrev} className="grid h-7 w-7 place-items-center rounded-md border border-edge hover:border-line" aria-label="Previous incident"><ChevronLeft size={15} /></button>
          <span className="hud-value">{index + 1} of {total}</span>
          <button onClick={onNext} className="grid h-7 w-7 place-items-center rounded-md border border-beam/60 bg-beam/15 hover:bg-beam/30" aria-label="Next incident"><ChevronRight size={15} /></button>
        </div>
      </header>
      <AnimatePresence mode="wait">
        <motion.div key={inc.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="flex min-h-0 flex-1 flex-col">
          <div className="mx-4 flex items-start gap-3 rounded-lg border p-3 short:p-2" style={{ borderColor: `${color}55`, background: `linear-gradient(90deg, ${color}22, transparent)` }}>
            <AlertTriangle size={30} style={{ color }} className="mt-0.5 shrink-0 short:hidden" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-display text-[19px] font-extrabold tracking-wide short:text-[16px]">{inc.id}</span>
                <Chip label={inc.status} />
                {inc.role === "negative_control" && <Chip label="NEGATIVE CONTROL" color="#8B7BFF" />}
              </div>
              <div className="text-[13px] font-semibold leading-snug short:text-[12px]" style={{ color }}>{inc.title || EVENT_TYPES[inc.event_type_hypothesis]}</div>
              <div className="text-[11px] text-muted">{inc.aoi_name} · {fmt.utc(inc.observation_time)}</div>
            </div>
          </div>
          <Tabs className="mx-4 mt-2" value={tab} onChange={setT} tabs={[
            { key: "overview", label: "Overview" }, { key: "spectral", label: "Spectral Evidence" }, { key: "temporal", label: "Temporal" },
            { key: "assets", label: "Assets" }, { key: "actions", label: "Actions" }]} />
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            {tab === "overview" && (
              <div className="grid grid-cols-[132px_1fr] gap-3">
                <div className="overflow-hidden rounded-md border border-edge bg-deep">
                  {thumb ? <img src={pipelineUrl(thumb.url)} alt={thumb.label} className="h-[150px] w-full object-cover" /> : <div className="grid h-[150px] place-items-center text-[11px] text-dim">no layer</div>}
                </div>
                <div>
                  <div className="kv"><span>Event type (hypothesis)</span><span className="text-right font-semibold">{EVENT_TYPES[inc.event_type_hypothesis]?.split(" /")[0]}</span></div>
                  <div className="kv"><span>Confidence</span><span className="flex items-center gap-2"><span className="hud-value text-beam2">{fmt.pct(inc.confidence)}</span><span className="w-16"><Meter value={inc.confidence} color="#4D93FF" /></span></span></div>
                  <div className="kv"><span>Severity</span><span className="flex items-center gap-2"><span className="hud-value">{fmt.num(inc.severity)}</span><span className="w-16"><Meter value={inc.severity} color="#FFC23D" /></span></span></div>
                  <div className="kv"><span>Area</span><span className="hud-value">{inc.area_km2 != null ? `${inc.area_km2.toFixed(2)} km²` : "n/a"}</span></div>
                </div>
                <div className="col-span-2">
                  {Object.entries({ ...est, ...wq }).slice(0, 6).map(([k, v]) => (
                    <div key={k} className="kv">
                      <span className="flex items-center gap-2">{v.label || k} <Kind kind={v.quantity_kind} /></span>
                      <span className="flex items-center gap-2">
                        <span className="hud-value">{fmt.num(v.value, Math.abs(v.value ?? 0) < 1 ? 3 : 1)}{v.units && v.units !== "dimensionless" ? ` ${v.units}` : ""}</span>
                        {v.seasonal_percentile != null && <span className="text-[10.5px] text-caution">{fmt.ord(v.seasonal_percentile)} pct</span>}
                      </span>
                    </div>
                  ))}
                  <div className="kv"><span>Sensor agreement</span>
                    <span className="flex flex-wrap justify-end gap-1">{Object.entries(agree).map(([k, v]) => (
                      <span key={k} title={v.note} className="rounded px-1.5 py-0.5 text-[10px] font-bold" style={{ color: v.agrees ? "#23D484" : v.agrees === false ? "#FF4D5E" : "#5D7299", background: "#0A1630", border: "1px solid #16284D" }}>
                        {v.agrees ? "✓" : v.agrees === false ? "✗" : "·"} {k.split(" (")[0]}</span>))}</span></div>
                  <div className="kv"><span>Nearest asset</span><span className="text-right">{nearest ? <>{nearest.asset.name}<div className="text-[10.5px] text-muted">{fmt.km(nearest.distance_m)}</div></> : "none registered"}</span></div>
                  <div className="kv"><span>Validation status</span><span className="text-right text-caution">{inc.recommendation?.action === "FIELD_VERIFICATION" ? "● Field sample recommended" : inc.field_validation?.status || inc.recommendation?.action?.replace(/_/g, " ")}</span></div>
                  <div className="mt-2 flex justify-end"><WhyButton title={`Why am I seeing ${inc.id}?`}><Provenance inc={inc} /></WhyButton></div>
                </div>
                {inc.summary && <p className="col-span-2 rounded-md border border-edge bg-deep/60 p-3 text-[12px] leading-relaxed text-muted">{inc.summary}</p>}
              </div>
            )}
            {tab === "spectral" && (
              <div>
                {inc.spectral ? (
                  <>
                    <div className="mb-2 flex items-center gap-2 text-[11.5px] text-muted">{inc.spectral.sensor} {inc.spectral.simulated && <SimBadge />}</div>
                    <SpectrumPlot spec={inc.spectral} height={210} />
                    <p className="mt-2 text-[11.5px] text-muted">Event vs background water with the background 5–95 % envelope. A spectrum is optical evidence, not a species or substance identification.</p>
                  </>
                ) : <p className="text-muted">No spectrum for this incident.</p>}
                <Link href={`/spectra?id=${inc.id}`} className="btn mt-3 w-full">Open in Spectral Lab (2D + 3D cube)</Link>
              </div>
            )}
            {tab === "temporal" && (
              <div className="space-y-2 text-[12.5px]">
                <div className="kv"><span>Seasonal percentile (primary indicator)</span><span className="hud-value text-caution">{fmt.ord(inc.temporal?.seasonal_percentile)}</span></div>
                <div className="kv"><span>Same-season observations</span><span className="hud-value">{inc.temporal?.n_seasonal ?? "n/a"}</span></div>
                <div className="kv"><span>Persistence at this location</span><span className="hud-value">{inc.temporal?.persistence_frac != null ? fmt.pct(inc.temporal.persistence_frac) : "n/a"}</span></div>
                {inc.temporal?.note && <p className="text-muted">{inc.temporal.note}</p>}
                {inc.temporal?.series && inc.temporal.series.length > 2 && <MiniSeries series={inc.temporal.series} mark={inc.observation_time.slice(0, 10)} />}
                <button onClick={onOpenTimeline} className="btn w-full">Open investigation timeline</button>
              </div>
            )}
            {tab === "assets" && (
              <div className="space-y-2">
                {(inc.exposure || []).length === 0 && <p className="text-muted">No registered asset within range.</p>}
                {[...(inc.exposure || [])].sort((a, b) => a.distance_m - b.distance_m).map((e) => (
                  <div key={e.asset.id} className="panel-flat p-3 text-[12px]">
                    <div className="flex justify-between"><span className="font-semibold">{e.asset.name}</span><span className="hud-value">{fmt.km(e.distance_m)}</span></div>
                    <div className="text-muted">{(e.asset.type_label || e.asset.type).replace(/_/g, " ")} · {e.direction ? `${e.direction} of event · ` : ""}{e.asset.source}</div>
                    {e.exposure_score != null && <div className="mt-1 flex items-center gap-2"><span className="text-muted">Exposure</span><span className="w-24"><Meter value={e.exposure_score} color="#FF8A3D" /></span><span className="hud-value">{fmt.num(e.exposure_score)}</span></div>}
                  </div>
                ))}
                <p className="text-[11px] text-dim">Assets are mapped facility centroids from OpenStreetMap; intake locations are not public and are never estimated.</p>
              </div>
            )}
            {tab === "actions" && inc.recommendation && (
              <div className="space-y-2 text-[12.5px]">
                <div className="flex items-center justify-between"><span className="font-display text-[15px] font-bold">{inc.recommendation.action.replace(/_/g, " ")}</span><Chip label={inc.recommendation.priority} /></div>
                <ul className="list-disc space-y-1 pl-5 text-muted">{inc.recommendation.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
                {inc.recommendation.required_evidence.length > 0 && <><div className="hud-kicker mt-2">Required evidence</div><ul className="list-disc pl-5 text-muted">{inc.recommendation.required_evidence.map((r, i) => <li key={i}>{r}</li>)}</ul></>}
                {inc.recommendation.decision_deadline_utc && <div className="kv"><span>Decision deadline</span><span className="hud-value">{fmt.utc(inc.recommendation.decision_deadline_utc)}</span></div>}
                <div className="hud-kicker mt-2">Not recommended</div>
                <ul className="list-disc pl-5 text-dim">{inc.recommendation.not_recommended.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            )}
          </div>
          <div className="border-t border-edge p-2.5">
            <input name="review-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional review note (saved with your decision)" className="mb-2 short:mb-1.5 short:py-1 w-full rounded-md border border-line bg-deep px-3 py-1.5 text-[12px] outline-none focus:border-beam2" maxLength={400} />
            <div className="grid grid-cols-3 gap-2">
              <button disabled={!!busy} onClick={() => act("CONFIRM")} className="btn btn-good whitespace-nowrap px-2"><Check size={15} /> Confirm Event</button>
              <button disabled={!!busy} onClick={() => act("FALSE_POSITIVE")} className="btn btn-bad whitespace-nowrap px-2"><X size={15} /> False Positive</button>
              <button disabled={!!busy} onClick={() => setReclass(true)} className="btn whitespace-nowrap px-2"><RefreshCcw size={14} /> Reclassify</button>
            </div>
            <div className="mt-2 grid grid-cols-[1.5fr_1fr] gap-2">
              <button disabled={!!busy} onClick={() => act("NEEDS_FIELD_SAMPLE")} className="btn btn-primary whitespace-nowrap"><FlaskConical size={15} /> Request Field Sample</button>
              <button disabled={!!busy} onClick={() => act("INSUFFICIENT_EVIDENCE")} className="btn whitespace-nowrap px-2"><ShieldAlert size={14} /> Insufficient</button>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
      <Modal open={reclass} onClose={() => setReclass(false)} title={`Reclassify ${inc.id}`} width={440}>
        <p className="mb-2 text-[12px] text-muted">Current hypothesis: <b>{EVENT_TYPES[inc.event_type_hypothesis]}</b>. The original prediction is kept; your correction is recorded next to it.</p>
        <select value={newType} onChange={(e) => setNewType(e.target.value as EventType)} className="mb-3 w-full rounded-md border border-line bg-deep px-3 py-2 text-[13px]">
          {Object.entries(EVENT_TYPES).filter(([k]) => k !== inc.event_type_hypothesis).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <div className="flex justify-end gap-2"><button className="btn" onClick={() => setReclass(false)}>Cancel</button><button className="btn btn-primary" onClick={() => act("RECLASSIFY", { new_hypothesis: newType })}>Save reclassification</button></div>
      </Modal>
    </section>
  );
}

function MiniSeries({ series, mark }: { series: { date: string; value: number | null }[]; mark: string }) {
  const pts = series.filter((s) => s.value != null) as { date: string; value: number }[];
  const W = 360, H = 110, P = 6;
  const t = pts.map((p) => new Date(p.date).getTime());
  const v = pts.map((p) => p.value);
  const tx = (x: number) => P + ((x - Math.min(...t)) / (Math.max(...t) - Math.min(...t) || 1)) * (W - 2 * P);
  const ty = (y: number) => H - P - ((y - Math.min(...v)) / (Math.max(...v) - Math.min(...v) || 1)) * (H - 2 * P);
  const mk = pts.find((p) => p.date.slice(0, 10) === mark);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-md border border-edge bg-deep">
      <polyline fill="none" stroke="#4D93FF" strokeWidth="1.2" points={pts.map((p, i) => `${tx(t[i])},${ty(p.value)}`).join(" ")} />
      {pts.map((p, i) => <circle key={i} cx={tx(t[i])} cy={ty(p.value)} r={1.4} fill="#93A6CB" />)}
      {mk && <circle cx={tx(new Date(mk.date).getTime())} cy={ty(mk.value)} r={4.5} fill="#FF4D5E" stroke="#040915" />}
    </svg>
  );
}
