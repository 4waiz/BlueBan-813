"use client";
/**
 * INCIDENT CONTROL - the main screen (docs/design/dashboard-target.png).
 * Hero map + incident telemetry + satellite / spectral cube / drift panels.
 */
import React, { Suspense, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Box, LineChart, Maximize2, Minimize2, Presentation, Sigma, X } from "lucide-react";
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

const WELCOME_KEY = "blueban813.welcome.dismissed";

/** First visit only: one sentence on what this is, and the way into the guided tour. ?intro=0 skips it (demos, screenshots). */
function StartHere() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("intro") === "0") return;
    try { setShow(localStorage.getItem(WELCOME_KEY) !== "1"); } catch { setShow(true); }
  }, []);
  const close = () => { setShow(false); try { localStorage.setItem(WELCOME_KEY, "1"); } catch { /* storage blocked */ } };
  if (!show) return null;
  return (
    <div data-map-ui role="region" aria-label="Start here" className="panel absolute bottom-14 left-3 z-20 w-[min(380px,calc(100%-1.5rem))] p-4">
      <button onClick={close} className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-md text-muted hover:text-ink" aria-label="Dismiss"><X size={15} /></button>
      <div className="hud-kicker">Start here</div>
      <p className="mt-1 pr-6 text-[13px] leading-snug text-ink">BLUEBAN 813 spots unusual coastal water from satellites, sends it to a person and a field team, and learns from every answer.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link href="/judge" onClick={close} className="btn btn-primary px-3 py-1.5 text-[12px]"><Presentation size={14} /> 3-minute guided tour</Link>
        <button onClick={close} className="btn px-3 py-1.5 text-[12px]">Explore the Fujairah case</button>
      </div>
    </div>
  );
}

async function stacRecent(bbox: [number, number, number, number]) {
  const end = new Date(), start = new Date(end.getTime() - 30 * 86400e3);
  const r = await fetch("https://planetarycomputer.microsoft.com/api/stac/v1/search", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ collections: ["sentinel-2-l2a"], bbox, datetime: `${start.toISOString()}/${end.toISOString()}`, limit: 100 }),
  });
  if (!r.ok) throw new Error(`error ${r.status}`);
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
    const op = getOperator(); if (!op) { toast("Set your operator name first (top-right)", "err"); return; }
    try { const a = await mutate((e) => e.addAoi({ name: aoiDraft.name || "New area", bbox: aoiDraft.bbox, coast: "user-defined", optical_regime: "unknown" }, op)); toast(`Area ${a.id} added to WATCH`); setAoiDraft(null); }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const saveAsset = async () => {
    if (!assetDraft) return;
    const op = getOperator(); if (!op) { toast("Set your operator name first (top-right)", "err"); return; }
    try { const a = await mutate((e) => e.addAsset({ name: assetDraft.name, type: assetDraft.type, lon: assetDraft.lon, lat: assetDraft.lat }, op)); toast(`Asset added: ${a.name}`); setAssetDraft(null); }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const moveSample = async (s: Sample, lon: number, lat: number) => {
    const op = getOperator(); if (!op) { toast("Set your operator name first (top-right)", "err"); return; }
    try { await mutate((e) => e.patchSample(s.id, op, { lon, lat })); toast(`${s.code} moved to ${lat.toFixed(4)}, ${lon.toFixed(4)}`); }
    catch (e) { toast((e as Error).message, "err"); }
  };

  const spectrumFromPick = pick && incident?.spectral ? { ...incident.spectral, wavelengths_nm: pick.wavelengths_nm, event: pick.values, background: incident.spectral.background.length === pick.values.length ? incident.spectral.background : pick.values.map(() => null), background_p05: undefined, background_p95: undefined } : null;

  // Desktop: one screen, nothing scrolls. The incident panel runs the full height
  // on the right; the map sits over three panels on the left; every panel fits
  // its own box. Phones and portrait tablets: the panels stack and the page scrolls.
  return (
    <div className={`flex flex-col gap-3 p-3 short:gap-2 short:p-2 lg:grid lg:h-full ${big ? "lg:grid-cols-[1fr] lg:grid-rows-[minmax(0,1fr)]" : "lg:grid-cols-[minmax(0,1fr)_clamp(340px,26vw,440px)] lg:grid-rows-[minmax(0,1fr)_clamp(190px,30vh,330px)]"}`}>
      <div className="flex min-h-0 flex-col gap-3 short:gap-2 lg:contents">
        <div className={`panel relative min-h-0 overflow-hidden p-0 lg:col-start-1 lg:row-start-1 lg:h-auto ${big ? "h-[78vh]" : "h-[56vh] min-h-[320px]"}`}>
          <IncidentMap incident={incident} incidents={incidents} aois={aois.data || []} assets={assets.data || []} stations={stations.data}
            samples={incident?.samples || []} onSelectIncident={(id) => router.replace(`/?id=${id}`, { scroll: false })}
            onMoveSample={moveSample} onDrawAoi={onDrawAoi} onPlaceAsset={(lon, lat) => setAssetDraft({ lon, lat, name: "", type: "DESALINATION_PLANT" })} onPixel={setPixel} />
          <StartHere />
          <button data-map-ui onClick={() => setBig((b) => !b)} className="panel-flat absolute bottom-3 left-3 z-10 grid h-8 w-8 place-items-center text-muted hover:text-ink" title={big ? "Restore layout" : "Expand map"} aria-label={big ? "Restore layout" : "Expand map"}>{big ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</button>
          {pixel && (
            <div data-map-ui className="panel absolute bottom-3 left-14 z-10 w-[270px] max-w-[calc(100%-4.5rem)] p-3 text-[11.5px]">
              <div className="mb-1 flex justify-between"><span className="hud-kicker">Pixel values</span><button onClick={() => setPixel(null)} className="text-muted">×</button></div>
              <div className="hud-value text-muted">{pixel.lat.toFixed(5)}, {pixel.lon.toFixed(5)} {pixel.date ? `· ${pixel.date}` : ""}</div>
              {Object.entries(pixel.values).map(([k, v]) => <div key={k} className="kv py-0.5"><span>{k}</span><span className="hud-value">{fmt.num(v, Math.abs(v ?? 0) < 1 ? 4 : 2)}</span></div>)}
            </div>
          )}
        </div>
        {!big && <div className="h-[640px] min-h-0 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:h-auto"><IncidentPanel inc={incident} loading={inc.loading || list.loading} index={idx} total={ordered.length} onPrev={() => go(-1)} onNext={() => go(1)} onOpenTimeline={() => current && router.push(`/incident?id=${current.id}`)} /></div>}
      </div>
      {!big && (
        <div className="grid gap-3 short:gap-2 md:grid-cols-2 lg:col-start-1 lg:row-start-2 lg:min-h-0 lg:grid-cols-[clamp(220px,17vw,300px)_minmax(0,1.3fr)_minmax(0,1fr)]">
          <Panel className="h-[320px] lg:h-auto" title="Satellite view" bodyClass="px-3 pb-3 min-h-0 overflow-hidden"><SensorCard incident={incident} /></Panel>
          <Panel className="h-[480px] sm:h-[320px] md:col-span-2 md:row-start-2 lg:col-span-1 lg:row-start-auto lg:h-auto"
            title={<span className="flex items-center gap-2" title="Hyperspectral cube: each pixel holds a full light spectrum, not just red, green and blue">Spectral cube {incident?.cube?.includes("813") && <SimBadge />}</span>} bodyClass="px-3 pb-3 overflow-hidden"
            right={<div className="flex gap-1 whitespace-nowrap">
              <button onClick={() => setCubeMode("2d")} aria-pressed={cubeMode === "2d"} title="Spectrum as a 2D line plot" className={`btn px-2 py-1 text-[11px] ${cubeMode === "2d" ? "border-beam" : ""}`}><LineChart size={13} /> 2D</button>
              <button onClick={() => setCubeMode("3d")} aria-pressed={cubeMode === "3d"} title="Spectral cube in 3D" className={`btn px-2 py-1 text-[11px] ${cubeMode === "3d" ? "border-beam" : ""}`}><Box size={13} /> 3D</button>
              <a href={current ? `/spectra?id=${current.id}` : "/spectra"} className="btn px-2 py-1 text-[11px]" title="Open the Spectral Lab"><Sigma size={13} /><span className="hidden xl:inline">Spectral Lab</span><span className="xl:hidden">Lab</span></a></div>}>
            <div className="grid h-full min-h-0 grid-rows-2 gap-3 sm:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] sm:grid-rows-1">
              <div className="min-h-0 overflow-hidden rounded-md border border-edge">
                {cubeMode === "3d" && incident?.cube ? <CubeViewer name={incident.cube} height="100%" compact onSpectrum={setPick} />
                  : incident?.spectral ? <SpectrumPlot spec={incident.spectral} fill range={[400, 900]} />
                  : <div className="grid h-full place-items-center text-[12px] text-dim">No spectrum for this incident</div>}
              </div>
              <div className="flex min-h-0 flex-col">
                {spectrumFromPick ? <><div className="hud-kicker mb-1">Pixel · row {pick!.row}, col {pick!.col}</div><div className="min-h-0 flex-1"><SpectrumPlot spec={spectrumFromPick} fill range={[400, 900]} /></div></>
                  : incident?.spectral ? <><div className="hud-kicker mb-1 truncate">Event minus normal water</div><div className="min-h-0 flex-1"><SpectrumPlot spec={{ ...incident.spectral, event: incident.spectral.event.map((v, i) => (v != null && incident.spectral!.background[i] != null ? v - incident.spectral!.background[i]! : null)), background: incident.spectral.background.map(() => 0), background_p05: undefined, background_p95: undefined }} fill range={[400, 900]} showBands={false} /></div></>
                  : <div className="text-[12px] text-dim">Select an incident</div>}
                {incident?.spectral && <div className="mt-1 truncate text-[10.5px] text-muted">{incident.spectral.sensor}</div>}
              </div>
            </div>
          </Panel>
          <Panel className="h-[320px] lg:h-auto" title="Drift forecast" bodyClass="px-3 pb-3 overflow-hidden" right={<span className="whitespace-nowrap text-[10.5px] text-caution" title="Wind-only scenario, not a validated ocean forecast">not validated</span>}>
            <TimeCorridor steps={incident?.forecast?.steps || null} height="100%" wind={incident?.forecast?.wind || null} />
          </Panel>
        </div>
      )}

      <Modal open={!!aoiDraft} onClose={() => setAoiDraft(null)} title="Monitor a new area" width={480}>
        {aoiDraft && (<div className="space-y-3 text-[12.5px]">
          <div className="hud-value text-muted">Bounds {aoiDraft.bbox.map((v) => v.toFixed(3)).join(", ")}</div>
          <input autoFocus value={aoiDraft.name} onChange={(e) => setAoiDraft({ ...aoiDraft, name: e.target.value })} placeholder="Area name, e.g. Mirfa intake waters" className="w-full rounded-md border border-line bg-deep px-3 py-2 outline-none focus:border-beam2" />
          <div className="panel-flat p-3">
            <div className="hud-kicker mb-1" title="Live search of the Sentinel-2 L2A catalogue on Microsoft Planetary Computer">Sentinel-2 images here, last 30 days (live)</div>
            {aoiDraft.err ? <div className="text-critical">Could not check recent images ({aoiDraft.err}).</div> : !aoiDraft.stac ? <div className="text-muted">Checking recent images…</div> :
              <div>{aoiDraft.stac.n_dates} image dates ({aoiDraft.stac.n_items} tiles). {aoiDraft.stac.n_clear} tiles with ≤10 % cloud. Latest: {aoiDraft.stac.last || "none"}.</div>}
          </div>
          <p className="text-muted">Saving adds this area to WATCH in this workspace. The pipeline builds its past-years baseline (scripts/build_watch.py).</p>
          <div className="flex justify-end gap-2"><button className="btn" onClick={() => setAoiDraft(null)}>Cancel</button><button className="btn btn-primary" onClick={saveAoi}>Monitor area</button></div>
        </div>)}
      </Modal>
      <Modal open={!!assetDraft} onClose={() => setAssetDraft(null)} title="Add an asset" width={440}>
        {assetDraft && (<div className="space-y-3 text-[12.5px]">
          <div className="hud-value text-muted">{assetDraft.lat.toFixed(5)}, {assetDraft.lon.toFixed(5)}</div>
          <input autoFocus value={assetDraft.name} onChange={(e) => setAssetDraft({ ...assetDraft, name: e.target.value })} placeholder="Asset name" className="w-full rounded-md border border-line bg-deep px-3 py-2 outline-none focus:border-beam2" />
          <select value={assetDraft.type} onChange={(e) => setAssetDraft({ ...assetDraft, type: e.target.value })} className="w-full rounded-md border border-line bg-deep px-3 py-2">
            {["DESALINATION_PLANT", "POWER_PLANT", "AQUACULTURE", "PUBLIC_BEACH", "PORT", "OIL_TERMINAL", "MARINE_PROTECTED_AREA", "CUSTOM"].map((t) => <option key={t} value={t}>{(t.charAt(0) + t.slice(1).toLowerCase()).replace(/_/g, " ")}</option>)}
          </select>
          <p className="text-muted">Assets you add stay in your workspace. BlueBan never guesses intake locations.</p>
          <div className="flex justify-end gap-2"><button className="btn" onClick={() => setAssetDraft(null)}>Cancel</button><button className="btn btn-primary" disabled={!assetDraft.name.trim()} onClick={saveAsset}>Add asset</button></div>
        </div>)}
      </Modal>
    </div>
  );
}

export default function Page() { return <Suspense><Home /></Suspense>; }
