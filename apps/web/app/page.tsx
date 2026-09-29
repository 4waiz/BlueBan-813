"use client";
/**
 * INCIDENT CONTROL - the main screen (docs/design/dashboard-target.png).
 * Hero map + incident telemetry + satellite / spectral cube / drift panels.
 */
import React, { Suspense, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { Box, LineChart, Maximize2, Minimize2, Sigma } from "lucide-react";
import { getEngine, getOperator, mutate, useEngineQuery, useStatic } from "@/lib/engine";
import type { Incident, Sample } from "@/lib/engine/types";
import IncidentPanel from "@/components/incident/IncidentPanel";
import SensorCard from "@/components/satellite/SensorCard";
import SpectrumPlot from "@/components/spectra/SpectrumPlot";
import { fmt, Modal, Panel, SimBadge, toast } from "@/components/ui";
import type { PixelValues } from "@/components/map/IncidentMap";

const IncidentMap = dynamic(() => import("@/components/map/IncidentMap"), { ssr: false, loading: () => <div className="grid h-full place-items-center text-muted">Loading map…</div> });
const CubeViewer = dynamic(() => import("@/components/spectra/CubeViewer"), { ssr: false });
const TimeCorridor = dynamic(() => import("@/components/forecast/TimeCorridor"), { ssr: false });

async function stacRecent(bbox: [number, number, number, number]) {
  const end = new Date(), start = new Date(end.getTime() - 30 * 86400e3);
  const r = await fetch("https://planetarycomputer.microsoft.com/api/stac/v1/search", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ collections: ["sentinel-2-l2a"], bbox, datetime: `${start.toISOString()}/${end.toISOString()}`, limit: 100 }),
  });
  if (!r.ok) throw new Error(`STAC ${r.status}`);
  const j = await r.json();
  const items = (j.features || []) as { properties: { datetime: string; "eo:cloud_cover": number; platform: string } }[];
  const dates = [...new Set(items.map((i) => i.properties.datetime.slice(0, 10)))].sort();
  const clear = items.filter((i) => i.properties["eo:cloud_cover"] <= 10);
  return { n_items: items.length, n_dates: dates.length, last: dates[dates.length - 1] || null, n_clear: clear.length };
}

function Home() {
  const router = useRouter();
  const sp = useSearchParams();
  const list = useEngineQuery((e) => e.listIncidents());
  const aois = useEngineQuery((e) => e.aois());
  const assets = useEngineQuery((e) => e.assets());
  const stations = useStatic<GeoJSON.FeatureCollection>("registers/stations_ead.geojson");
  const incidents = list.data || [];
  const ordered = useMemo(() => [...incidents.filter((i) => i.role !== "negative_control"), ...incidents.filter((i) => i.role === "negative_control")], [incidents]);
  const wanted = sp.get("id");
  const idx = Math.max(0, ordered.findIndex((i) => i.id === wanted));
  const current = ordered[idx];
  const inc = useEngineQuery((e) => (current ? e.getIncident(current.id) : Promise.resolve(null)), [current?.id]);
  const incident = inc.data as Incident | null;
  const [pixel, setPixel] = useState<PixelValues | null>(null);
  const [aoiDraft, setAoiDraft] = useState<{ bbox: [number, number, number, number]; name: string; stac?: Awaited<ReturnType<typeof stacRecent>> | null; err?: string } | null>(null);
  const [assetDraft, setAssetDraft] = useState<{ lon: number; lat: number; name: string; type: string } | null>(null);
  const [pick, setPick] = useState<{ wavelengths_nm: number[]; values: (number | null)[]; row: number; col: number } | null>(null);
  const [cubeMode, setCubeMode] = useState<"3d" | "2d">("3d");
  const [big, setBig] = useState(false);

  useEffect(() => { setPixel(null); setPick(null); }, [current?.id]);
  const go = (d: number) => { if (!ordered.length) return; const n = ordered[(idx + d + ordered.length) % ordered.length]; router.replace(`/?id=${n.id}`, { scroll: false }); };

  const onDrawAoi = async (bbox: [number, number, number, number]) => {
    setAoiDraft({ bbox, name: "", stac: null });
    try { const s = await stacRecent(bbox); setAoiDraft((d) => (d ? { ...d, stac: s } : d)); }
    catch (e) { setAoiDraft((d) => (d ? { ...d, err: (e as Error).message } : d)); }
  };
  const saveAoi = async () => {
    if (!aoiDraft) return;
    const op = getOperator(); if (!op) { toast("Set your operator name first", "err"); return; }
    try { const a = await mutate((e) => e.addAoi({ name: aoiDraft.name || "New AOI", bbox: aoiDraft.bbox, coast: "user-defined", optical_regime: "unknown" }, op)); toast(`AOI ${a.id} added to WATCH`); setAoiDraft(null); }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const saveAsset = async () => {
    if (!assetDraft) return;
    const op = getOperator(); if (!op) { toast("Set your operator name first", "err"); return; }
    try { const a = await mutate((e) => e.addAsset({ name: assetDraft.name, type: assetDraft.type, lon: assetDraft.lon, lat: assetDraft.lat }, op)); toast(`Asset ${a.name} registered`); setAssetDraft(null); }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const moveSample = async (s: Sample, lon: number, lat: number) => {
    const op = getOperator(); if (!op) { toast("Set your operator name first", "err"); return; }
    try { await mutate((e) => e.patchSample(s.id, op, { lon, lat })); toast(`${s.code} moved to ${lat.toFixed(4)}, ${lon.toFixed(4)}`); }
    catch (e) { toast((e as Error).message, "err"); }
  };

  const spectrumFromPick = pick && incident?.spectral ? { ...incident.spectral, wavelengths_nm: pick.wavelengths_nm, event: pick.values, background: incident.spectral.background.length === pick.values.length ? incident.spectral.background : pick.values.map(() => null), background_p05: undefined, background_p95: undefined } : null;

  return (
    <div className={`grid h-full gap-3 p-3 short:gap-2 short:p-2 ${big ? "grid-rows-[minmax(0,1fr)]" : "grid-rows-[minmax(0,1fr)_clamp(220px,31vh,330px)]"}`}>
      <div className={`grid min-h-0 gap-3 short:gap-2 ${big ? "grid-cols-[1fr]" : "grid-cols-[minmax(0,1fr)_clamp(360px,24vw,430px)]"}`}>
        <div className="panel relative min-h-0 overflow-hidden p-0">
          <IncidentMap incident={incident} incidents={incidents} aois={aois.data || []} assets={assets.data || []} stations={stations.data}
            samples={incident?.samples || []} onSelectIncident={(id) => router.replace(`/?id=${id}`, { scroll: false })}
            onMoveSample={moveSample} onDrawAoi={onDrawAoi} onPlaceAsset={(lon, lat) => setAssetDraft({ lon, lat, name: "", type: "DESALINATION_PLANT" })} onPixel={setPixel} />
          <button onClick={() => setBig((b) => !b)} className="panel-flat absolute bottom-3 left-3 z-10 grid h-8 w-8 place-items-center text-muted hover:text-ink" title={big ? "Restore layout" : "Expand map"}>{big ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</button>
          {pixel && (
            <div className="panel absolute bottom-3 left-14 z-10 w-[270px] p-3 text-[11.5px]">
              <div className="mb-1 flex justify-between"><span className="hud-kicker">Pixel inspector</span><button onClick={() => setPixel(null)} className="text-muted">×</button></div>
              <div className="hud-value text-muted">{pixel.lat.toFixed(5)}, {pixel.lon.toFixed(5)} {pixel.date ? `· ${pixel.date}` : ""}</div>
              {Object.entries(pixel.values).map(([k, v]) => <div key={k} className="kv py-0.5"><span>{k}</span><span className="hud-value">{fmt.num(v, Math.abs(v ?? 0) < 1 ? 4 : 2)}</span></div>)}
            </div>
          )}
        </div>
        {!big && <IncidentPanel inc={incident} index={idx} total={ordered.length} onPrev={() => go(-1)} onNext={() => go(1)} onOpenTimeline={() => current && router.push(`/incident?id=${current.id}`)} />}
      </div>
      {!big && (
        <div className="grid min-h-0 grid-cols-[clamp(250px,18vw,330px)_minmax(0,1.35fr)_minmax(0,1fr)] gap-3 short:gap-2">
          <Panel title="Satellite view" bodyClass="px-3 pb-3 min-h-0"><SensorCard incident={incident} /></Panel>
          <Panel title={<span className="flex items-center gap-2">Hyperspectral data cube {incident?.cube?.includes("813") && <SimBadge />}</span>} bodyClass="px-3 pb-3"
            right={<div className="flex gap-1">
              <button onClick={() => setCubeMode("2d")} className={`btn px-2 py-1 text-[11px] ${cubeMode === "2d" ? "border-beam" : ""}`}><LineChart size={13} /> 2D Plot</button>
              <button onClick={() => setCubeMode("3d")} className={`btn px-2 py-1 text-[11px] ${cubeMode === "3d" ? "border-beam" : ""}`}><Box size={13} /> 3D Cube</button>
              <a href={current ? `/spectra?id=${current.id}` : "/spectra"} className="btn px-2 py-1 text-[11px]"><Sigma size={13} /> Spectral Lab</a></div>}>
            <div className="grid h-full min-h-0 grid-cols-[1.1fr_1fr] gap-3">
              <div className="min-h-0 overflow-hidden rounded-md border border-edge">
                {cubeMode === "3d" && incident?.cube ? <CubeViewer name={incident.cube} height="100%" compact onSpectrum={setPick} />
                  : incident?.spectral ? <SpectrumPlot spec={incident.spectral} fill range={[400, 900]} />
                  : <div className="grid h-full place-items-center text-[12px] text-dim">No spectral evidence</div>}
              </div>
              <div className="flex min-h-0 flex-col">
                {spectrumFromPick ? <><div className="hud-kicker mb-1">Pixel r{pick!.row} c{pick!.col}</div><div className="min-h-0 flex-1"><SpectrumPlot spec={spectrumFromPick} fill range={[400, 900]} /></div></>
                  : incident?.spectral ? <><div className="hud-kicker mb-1 truncate">Difference (event − background)</div><div className="min-h-0 flex-1"><SpectrumPlot spec={{ ...incident.spectral, event: incident.spectral.event.map((v, i) => (v != null && incident.spectral!.background[i] != null ? v - incident.spectral!.background[i]! : null)), background: incident.spectral.background.map(() => 0), background_p05: undefined, background_p95: undefined }} fill range={[400, 900]} showBands={false} /></div></>
                  : <div className="text-[12px] text-dim">Select an incident</div>}
                {incident?.spectral && <div className="mt-1 truncate text-[10.5px] text-muted">{incident.spectral.sensor}</div>}
              </div>
            </div>
          </Panel>
          <Panel title="Forecast & drift" bodyClass="px-3 pb-3" right={<span className="text-[10.5px] text-caution">scenario, not validated</span>}>
            <TimeCorridor steps={incident?.forecast?.steps || null} height="100%" wind={incident?.forecast?.wind || null} />
          </Panel>
        </div>
      )}

      <Modal open={!!aoiDraft} onClose={() => setAoiDraft(null)} title="Create monitoring AOI" width={480}>
        {aoiDraft && (<div className="space-y-3 text-[12.5px]">
          <div className="hud-value text-muted">bbox {aoiDraft.bbox.map((v) => v.toFixed(3)).join(", ")}</div>
          <input autoFocus value={aoiDraft.name} onChange={(e) => setAoiDraft({ ...aoiDraft, name: e.target.value })} placeholder="AOI name, e.g. Mirfa intake waters" className="w-full rounded-md border border-line bg-deep px-3 py-2 outline-none focus:border-beam2" />
          <div className="panel-flat p-3">
            <div className="hud-kicker mb-1">Sentinel-2 L2A over this box, last 30 days (live STAC query)</div>
            {aoiDraft.err ? <div className="text-critical">STAC unavailable: {aoiDraft.err}</div> : !aoiDraft.stac ? <div className="text-muted">Querying Planetary Computer…</div> :
              <div>{aoiDraft.stac.n_dates} acquisition dates ({aoiDraft.stac.n_items} tiles), {aoiDraft.stac.n_clear} tiles ≤10 % cloud, latest {aoiDraft.stac.last || "none"}.</div>}
          </div>
          <p className="text-muted">Saving adds the AOI to WATCH in this workspace. Building its multi-year baseline runs in the pipeline (scripts/build_watch.py).</p>
          <div className="flex justify-end gap-2"><button className="btn" onClick={() => setAoiDraft(null)}>Cancel</button><button className="btn btn-primary" onClick={saveAoi}>Monitor AOI</button></div>
        </div>)}
      </Modal>
      <Modal open={!!assetDraft} onClose={() => setAssetDraft(null)} title="Register operator asset" width={440}>
        {assetDraft && (<div className="space-y-3 text-[12.5px]">
          <div className="hud-value text-muted">{assetDraft.lat.toFixed(5)}, {assetDraft.lon.toFixed(5)}</div>
          <input autoFocus value={assetDraft.name} onChange={(e) => setAssetDraft({ ...assetDraft, name: e.target.value })} placeholder="Asset name" className="w-full rounded-md border border-line bg-deep px-3 py-2 outline-none focus:border-beam2" />
          <select value={assetDraft.type} onChange={(e) => setAssetDraft({ ...assetDraft, type: e.target.value })} className="w-full rounded-md border border-line bg-deep px-3 py-2">
            {["DESALINATION_PLANT", "POWER_PLANT", "AQUACULTURE", "PUBLIC_BEACH", "PORT", "OIL_TERMINAL", "MARINE_PROTECTED_AREA", "CUSTOM"].map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
          </select>
          <p className="text-muted">Operator-owned: assets you add stay in your workspace. BlueBan never guesses intake locations.</p>
          <div className="flex justify-end gap-2"><button className="btn" onClick={() => setAssetDraft(null)}>Cancel</button><button className="btn btn-primary" disabled={!assetDraft.name.trim()} onClick={saveAsset}>Register asset</button></div>
        </div>)}
      </Modal>
    </div>
  );
}

export default function Page() { return <Suspense><Home /></Suspense>; }
