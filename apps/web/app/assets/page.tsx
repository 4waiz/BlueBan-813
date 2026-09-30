"use client";
/**
 * ASSETS - what an incident could reach.
 *
 * Desalination plants, power-plant cooling intakes, ports and public beaches
 * from OpenStreetMap, plus any asset an operator adds. Exposure for the
 * selected incident is distance and direction only: intake locations are not
 * public, so none is estimated.
 */
import React, { Suspense, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { MapPin, Plus, Search } from "lucide-react";
import { getOperator, mutate, useEngineQuery } from "@/lib/engine";
import type { AssetRow } from "@/lib/engine/types";
import { Chip, fmt, Modal, Panel, toast } from "@/components/ui";

const IncidentMap = dynamic(() => import("@/components/map/IncidentMap"), { ssr: false });

const TYPES: Record<string, { label: string; color: string }> = {
  DESALINATION_PLANT: { label: "Desalination plant", color: "#27C3F3" },
  POWER_PLANT: { label: "Power plant (cooling water)", color: "#FFC23D" },
  OIL_TERMINAL: { label: "Oil terminal", color: "#FF8A3D" },
  PORT: { label: "Port / harbour", color: "#8B7BFF" },
  PUBLIC_BEACH: { label: "Public beach", color: "#23D484" },
  AQUACULTURE: { label: "Aquaculture", color: "#FF6FB5" },
  PROTECTED_AREA: { label: "Protected area", color: "#93A6CB" },
};
const hav = (lo1: number, la1: number, lo2: number, la2: number) => {
  const R = 6371e3, r = Math.PI / 180, a = Math.sin(((la2 - la1) * r) / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin(((lo2 - lo1) * r) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
};
const bearing = (lo1: number, la1: number, lo2: number, la2: number) => {
  const r = Math.PI / 180, y = Math.sin((lo2 - lo1) * r) * Math.cos(la2 * r), x = Math.cos(la1 * r) * Math.sin(la2 * r) - Math.sin(la1 * r) * Math.cos(la2 * r) * Math.cos((lo2 - lo1) * r);
  const b = (Math.atan2(y, x) / r + 360) % 360;
  return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(b / 45) % 8];
};

function Assets() {
  const sp = useSearchParams();
  const list = useEngineQuery((e) => e.listIncidents()).data || [];
  const iid = sp.get("incident") || list.find((i) => i.aoi_id?.startsWith("AE") && i.status === "UNDER_REVIEW")?.id || list[0]?.id || null;
  const inc = useEngineQuery((e) => (iid ? e.getIncident(iid) : Promise.resolve(null)), [iid]).data || null;
  const assets = useEngineQuery((e) => e.assets()).data || [];
  const aois = useEngineQuery((e) => e.aois()).data || [];
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [draft, setDraft] = useState<{ lon: number; lat: number } | null>(null);
  const [name, setName] = useState("");
  const [dtype, setDtype] = useState("DESALINATION_PLANT");

  const rows = useMemo(() => {
    const c = inc?.centroid;
    return assets
      .filter((a) => (!type || a.type === type) && (!q || a.name.toLowerCase().includes(q.toLowerCase())))
      .map((a) => ({ a, d: c ? hav(c[0], c[1], a.lon, a.lat) : null, dir: c ? bearing(c[0], c[1], a.lon, a.lat) : null }))
      .sort((x, y) => (x.d ?? 1e12) - (y.d ?? 1e12));
  }, [assets, type, q, inc?.centroid]);
  const counts = useMemo(() => assets.reduce((m, a) => { m[a.type] = (m[a.type] || 0) + 1; return m; }, {} as Record<string, number>), [assets]);

  const add = async () => {
    if (!draft || !name.trim()) return;
    try {
      await mutate((e) => e.addAsset({ name: name.trim(), type: dtype, lon: draft.lon, lat: draft.lat, notes: "Placed by an operator on the map" } as Omit<AssetRow, "id" | "source">, getOperator() || "operator"));
      toast(`Asset added: ${name.trim()}`); setDraft(null); setName("");
    } catch (e) { toast((e as Error).message, "err"); }
  };

  return (
    <div className="grid h-full min-h-0 gap-3 p-3 short:gap-2 short:p-2 xl:grid-cols-[minmax(0,1.4fr)_minmax(380px,1fr)]">
      <Panel title="Asset map" kicker={inc ? `Exposure for ${inc.id}` : "Coastal assets"} bodyClass="relative min-h-0">
        <IncidentMap incident={inc} incidents={inc ? [{ id: inc.id, status: inc.status, aoi_id: inc.aoi_id, centroid: inc.centroid, title: inc.title, event_type_hypothesis: inc.event_type_hypothesis, priority: inc.priority, observation_time: inc.observation_time } as never] : []}
          aois={aois} assets={assets} onPlaceAsset={(lon, lat) => setDraft({ lon, lat })} compact showTimeline={false} initialMode="2d" />
        <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-void/80 px-2 py-1 text-[11px] text-muted">Use the map’s place-asset tool to add a facility.</div>
      </Panel>
      <Panel title="Asset register" kicker={`${assets.length} assets · OpenStreetMap + operator`} bodyClass="flex min-h-0 flex-col gap-2 p-3">
        <div className="flex flex-wrap gap-1">
          <button onClick={() => setType("")} className={`rounded-md border px-2 py-1 text-[11px] ${!type ? "border-beam bg-beam/15 text-ink" : "border-edge text-muted"}`}>All {assets.length}</button>
          {Object.entries(counts).map(([t, n]) => <button key={t} onClick={() => setType(t === type ? "" : t)} className={`rounded-md border px-2 py-1 text-[11px] ${type === t ? "border-beam bg-beam/15 text-ink" : "border-edge text-muted"}`}><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: TYPES[t]?.color || "#93A6CB" }} />{TYPES[t]?.label || t} {n}</button>)}
        </div>
        <div className="relative"><Search size={13} className="absolute left-2 top-2 text-dim" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search assets" className="w-full rounded-md border border-line bg-deep py-1.5 pl-7 pr-2 text-[12px]" /></div>
        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-edge">
          <table className="w-full text-[11.5px]">
            <thead className="sticky top-0 bg-panel"><tr className="border-b border-edge text-dim"><th className="px-2 py-1 text-left">Asset</th><th className="px-2 text-left">Type</th><th className="px-2 text-right">{inc ? "From incident" : "Location"}</th></tr></thead>
            <tbody>{rows.map(({ a, d, dir }) => (
              <tr key={a.id} className="border-b border-edge/50" title={a.notes || a.source}>
                <td className="px-2 py-1"><div className="font-semibold text-ink">{a.name}</div><div className="text-[10.5px] text-dim">{a.source}</div></td>
                <td className="px-2"><Chip label={TYPES[a.type]?.label || a.type} color={TYPES[a.type]?.color} /></td>
                <td className="hud-value px-2 text-right">{d != null ? `${fmt.km(d)} ${dir}` : `${a.lat.toFixed(3)}, ${a.lon.toFixed(3)}`}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <p className="text-[11px] text-dim">Distance and direction from the incident centroid only. Intake positions are not public and are never estimated; an operator can place a known intake on the map.</p>
      </Panel>
      <Modal open={!!draft} onClose={() => setDraft(null)} title="Add asset" width={420}>
        <div className="space-y-2 text-[12.5px]">
          <div className="flex items-center gap-2 text-muted"><MapPin size={14} /> {draft?.lat.toFixed(5)}, {draft?.lon.toFixed(5)}</div>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (e.g. Intake, Fujairah F2)" className="w-full rounded-md border border-line bg-deep px-3 py-1.5" />
          <select value={dtype} onChange={(e) => setDtype(e.target.value)} className="w-full rounded-md border border-line bg-deep px-3 py-1.5">
            {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <div className="flex justify-end gap-2 pt-2"><button className="btn" onClick={() => setDraft(null)}>Cancel</button><button className="btn btn-primary" disabled={!name.trim()} onClick={add}><Plus size={14} /> Add</button></div>
        </div>
      </Modal>
    </div>
  );
}

export default function Page() { return <Suspense><Assets /></Suspense>; }
