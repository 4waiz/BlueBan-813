"use client";
/**
 * INCIDENT INVESTIGATION: timeline | imagery comparison | evidence stack.
 * Every button persists through the engine and lands in the audit trail.
 */
import React, { Suspense, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Archive, Download, FileText, RotateCcw } from "lucide-react";
import { getOperator, mutate, useEngineQuery, useStatic } from "@/lib/engine";
import type { Decision, EventType, Incident } from "@/lib/engine/types";
import { EVENT_TYPES } from "@/lib/engine/rules";
import IncidentPanel, { Provenance } from "@/components/incident/IncidentPanel";
import SpectrumPlot from "@/components/spectra/SpectrumPlot";
import { Chip, fmt, Kind, Panel, toast, WhyButton } from "@/components/ui";
import { download, incidentReportMd } from "@/lib/report";

const IncidentMap = dynamic(() => import("@/components/map/IncidentMap"), { ssr: false });

type Ev = { at: string; kind: string; title: string; detail?: string; color: string };

/** Plain-language captions for the timeline (display only; the stored codes are unchanged). */
const DECISION_PAST: Record<Decision, string> = {
  CONFIRM: "marked as a real event", FALSE_POSITIVE: "marked as a false alarm", RECLASSIFY: "changed the suspected type",
  NEEDS_FIELD_SAMPLE: "requested a water sample", INSUFFICIENT_EVIDENCE: "marked as inconclusive",
};
const spaced = (s: unknown) => String(s).replace(/_/g, " ");

function timeline(inc: Incident): Ev[] {
  const out: Ev[] = [{ at: inc.observation_time, kind: "OBSERVED", title: `Image taken (${inc.provenance?.sources?.[0]?.satellite || "satellite"})`, detail: inc.provenance?.sources?.[0]?.scene_id, color: "#27C3F3" }];
  out.push({ at: inc.detected_at, kind: "DETECTED", title: `Flagged by ${inc.model_id}`, detail: `Suspected: ${EVENT_TYPES[inc.event_type_hypothesis]} · severity ${fmt.num(inc.severity)} · confidence ${fmt.pct(inc.confidence)}`, color: "#FFC23D" });
  (inc.reviews || []).forEach((r) => out.push({ at: r.created_at, kind: "REVIEW", title: `${r.reviewer}: ${DECISION_PAST[r.decision] || spaced(r.decision)}${r.new_hypothesis ? ` → ${EVENT_TYPES[r.new_hypothesis as EventType]?.split(" /")[0] || r.new_hypothesis}` : ""}`, detail: `${spaced(r.status_before)} → ${spaced(r.status_after)}${r.note ? ` · “${r.note}”` : ""}`, color: r.decision === "CONFIRM" ? "#23D484" : r.decision === "FALSE_POSITIVE" ? "#FF4D5E" : "#4D93FF" }));
  (inc.samples || []).filter((s) => s.collected_at).forEach((s) => out.push({ at: s.collected_at!, kind: "SAMPLE", title: `${s.code} collected by ${s.collected_by}`, detail: s.role, color: "#27C3F3" }));
  (inc.measurements || []).forEach((m) => out.push({ at: m.entered_at, kind: "LAB", title: `${m.parameter} = ${m.value} ${m.unit}`, detail: `${m.sample_id || "no sample"} · ${m.source} · ${m.entered_by}`, color: "#23D484" }));
  (inc.audit_trail || []).filter((a) => a.action === "incident.transition").forEach((a) => out.push({ at: a.at, kind: "STATUS", title: `${spaced(a.detail.from)} → ${spaced(a.detail.to)}`, detail: `${a.actor}${a.detail.reason ? ` · ${String(a.detail.reason)}` : ""}`, color: "#8B7BFF" }));
  return out.sort((a, b) => (a.at < b.at ? -1 : 1));
}

function Investigation() {
  const id = useSearchParams().get("id");
  const list = useEngineQuery((e) => e.listIncidents());
  const first = (list.data || []).find((i) => i.role !== "negative_control")?.id || list.data?.[0]?.id;
  const iid = id || first || null;
  const q = useEngineQuery((e) => (iid ? e.getIncident(iid) : Promise.resolve(null)), [iid]);
  const aois = useEngineQuery((e) => e.aois());
  const assets = useEngineQuery((e) => e.assets());
  const stations = useStatic<GeoJSON.FeatureCollection>("registers/stations_ead.geojson");
  const inc = q.data;
  const [busy, setBusy] = useState(false);
  const evs = useMemo(() => (inc ? timeline(inc) : []), [inc]);
  if (!inc) return <div className="p-6 text-muted">{q.loading ? "Loading incident…" : "Incident not found."}</div>;
  const feats = { ...(inc.water_quality?.estimates || {}), ...(inc.water_quality?.features || {}) };
  const mf = inc.model_features || {};
  const act = async (to: "RESOLVED" | "UNDER_REVIEW") => {
    const op = getOperator(); if (!op) { toast("Set your operator name first (top-right)", "err"); return; }
    setBusy(true);
    try { await mutate((e) => e.transition(inc.id, to, op, to === "RESOLVED" ? "Closed from investigation screen" : "Reopened for review")); toast(to === "RESOLVED" ? "Incident closed" : "Incident reopened"); }
    catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  };
  return (
    <div className="grid h-full min-h-0 gap-3 p-3 short:gap-2 short:p-2 xl:grid-cols-[300px_minmax(0,1fr)_400px]">
      <Panel title="Incident timeline" kicker={inc.id} bodyClass="overflow-y-auto px-4 pb-4">
        <ol className="relative ml-2 border-l border-edge">
          {evs.map((e, i) => (
            <li key={i} className="mb-4 ml-4">
              <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full" style={{ background: e.color, boxShadow: `0 0 8px ${e.color}` }} />
              <div className="hud-value text-[10.5px] text-dim">{fmt.utc(e.at)} · {e.kind}</div>
              <div className="text-[12.5px] font-semibold">{e.title}</div>
              {e.detail && <div className="break-words text-[11.5px] text-muted [overflow-wrap:anywhere]">{e.detail}</div>}
            </li>
          ))}
        </ol>
        <div className="mt-2 space-y-2">
          <button className="btn w-full" onClick={() => download(`${inc.id}_report.md`, incidentReportMd(inc))}><FileText size={14} /> Download report</button>
          <button className="btn w-full" onClick={() => download(`${inc.id}.json`, JSON.stringify(inc, null, 1), "application/json")}><Download size={14} /> Download all data (JSON)</button>
          {["CONFIRMED", "FALSE_POSITIVE"].includes(inc.status) && <button disabled={busy} className="btn w-full" onClick={() => act("RESOLVED")}><Archive size={14} /> Close incident</button>}
          {inc.status === "RESOLVED" && <button disabled={busy} className="btn w-full" onClick={() => act("UNDER_REVIEW")}><RotateCcw size={14} /> Reopen</button>}
          <Link href={`/field?id=${inc.id}`} className="btn w-full">Water sampling for this incident</Link>
        </div>
      </Panel>
      {/* one screen on desktop: the map takes the free height, the evidence scrolls inside its own panel */}
      <div className="flex min-h-0 flex-col gap-3 short:gap-2">
        <div className="panel relative h-[420px] min-h-0 shrink-0 overflow-hidden p-0 xl:h-auto xl:min-h-[200px] xl:flex-1 xl:shrink">
          <IncidentMap incident={inc} incidents={list.data || []} aois={aois.data || []} assets={assets.data || []} stations={stations.data} samples={inc.samples || []} initialMode="split" />
        </div>
        <Panel className="shrink-0 xl:max-h-[46%]" title="Evidence" bodyClass="grid content-start gap-3 overflow-y-auto p-3 md:grid-cols-2 2xl:grid-cols-3">
          <section className="panel-flat p-3 text-[12px]"><div className="hud-kicker mb-1">Detection</div>
            <div className="kv"><span title="How unusual the colour is vs all water in this image (RX detector, percentile). 100th = most unusual.">Spectral anomaly score</span><span className="hud-value">{fmt.ord(inc.spatial?.rx_percentile)}</span></div>
            <div className="kv"><span title="Robust z-score vs the same season in past years. 0 is normal. Higher is more unusual.">Score vs past years</span><span className="hud-value">{fmt.num(mf.robust_z_primary as number, 1)}</span></div>
            <div className="kv"><span>Area</span><span className="hud-value">{inc.area_km2 != null ? `${inc.area_km2.toFixed(2)} km²` : "n/a"}</span></div>
            <div className="kv"><span>Distance to shore</span><span className="hud-value">{mf.dist_shore_km != null ? `${(mf.dist_shore_km as number).toFixed(2)} km` : "n/a"}</span></div></section>
          <section className="panel-flat p-3 text-[12px]"><div className="hud-kicker mb-1">Compared with past years</div>
            <div className="kv"><span title="Main indicator vs the same season in past years. 100th = higher than all of them.">Percentile vs past years</span><span className="hud-value text-caution">{fmt.ord(inc.temporal?.seasonal_percentile)}</span></div>
            <div className="kv"><span>Past images, same season</span><span className="hud-value">{inc.temporal?.n_seasonal ?? "n/a"}</span></div>
            <div className="kv"><span title="Share of past same-season images where this spot was also unusual. High means a lasting feature, not a new event.">Also unusual in past years</span><span className="hud-value">{inc.temporal?.persistence_frac != null ? fmt.pct(inc.temporal.persistence_frac) : "n/a"}</span></div>
            <p className="mt-1 text-[11px] text-dim">{inc.temporal?.note}</p></section>
          <section className="panel-flat p-3 text-[12px]"><div className="hud-kicker mb-1">Spectrum</div>
            {inc.spectral ? <SpectrumPlot spec={inc.spectral} height={150} range={[400, 900]} /> : <span className="text-muted">None</span>}</section>
          <section className="panel-flat p-3 text-[12px]"><div className="hud-kicker mb-1" title="Sentinel-3 is a second-satellite check, not ground truth">Satellite agreement</div>
            {Object.entries(inc.sensor_agreement || {}).map(([k, a]) => (
              <div key={k} className="kv"><span>{k}</span><span style={{ color: a.agrees ? "#23D484" : a.agrees === false ? "#FF4D5E" : "#5D7299" }}>{a.agrees ? "agrees" : a.agrees === false ? "does not agree" : "n/a"}{a.note ? ` · ${a.note}` : ""}</span></div>))}</section>
          <section className="panel-flat p-3 text-[12px]"><div className="hud-kicker mb-1" title="Indices and proxies, not lab values, until water samples calibrate them">Water indicators</div>
            {Object.entries(feats).map(([k, e]) => (
              <div key={k} className="kv"><span className="flex items-center gap-1.5">{e.label || k} <Kind kind={e.quantity_kind} /></span><span className="hud-value" title="Value · percentile vs past years">{fmt.num(e.value, 3)}{e.seasonal_percentile != null ? ` · ${fmt.ord(e.seasonal_percentile)}` : ""}</span></div>))}
            <div className="mt-1"><WhyButton title="Where the numbers come from"><Provenance inc={inc} /></WhyButton></div></section>
          <section className="panel-flat p-3 text-[12px]"><div className="hud-kicker mb-1">Field results & outcome</div>
            <div className="kv"><span>Measurements</span><span className="hud-value">{inc.measurements?.length || 0}</span></div>
            <div className="kv"><span>Samples</span><span className="hud-value">{inc.samples?.length || 0} ({inc.samples?.filter((s) => s.status === "RESULT_RECEIVED").length || 0} with results)</span></div>
            <div className="kv"><span>Status</span><Chip label={inc.status} /></div>
            <p className="mt-1 text-[11.5px] text-muted">{inc.disposition || "No final outcome yet."}</p></section>
        </Panel>
      </div>
      <IncidentPanel inc={inc} index={0} total={1} />
    </div>
  );
}

export default function Page() { return <Suspense><Investigation /></Suspense>; }
