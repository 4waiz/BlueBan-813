"use client";
/**
 * INLAND · Shawka Dam (Ras Al Khaimah): the inland complement.
 *
 * Built separately on two fixed EnMAP L2A dates and a 28-observation
 * Sentinel-2/Landsat baseline, integrated as an add-on. Every number on this
 * screen is read from outputs/inland/summary.json (scripts/inland/
 * build_inland_bundle.py), which holds derived masks, scores, counts and sensor
 * metadata only: per-pixel EnMAP reflectance stays out of the browser while the
 * licence is unconfirmed. The two caveats are shown verbatim.
 */
import React, { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, Droplets, FileText, Layers, ScanLine, ShieldAlert, Waves } from "lucide-react";
import { pipelineUrl, useStatic } from "@/lib/engine";
import { Chip, Drawer, Panel, SimBadge, Tween } from "@/components/ui";
import Markdown from "@/components/ui/Markdown";
import { FP_COLOR, MASK_KEYS, SEVERITY_COLOR, type InlandSummary, type MaskKey } from "@/components/inland/types";
import type { PixelHover } from "@/components/inland/WetCoreScene";
import type { RibbonHover } from "@/components/inland/DeviationRibbon";
import type { BandHover } from "@/components/inland/BandLadder";

const loading3d = (h: number) => function Loading() { return <div className="grid place-items-center text-[12px] text-dim" style={{ height: h }}>Building 3D scene…</div>; };
const WetCoreScene = dynamic(() => import("@/components/inland/WetCoreScene"), { ssr: false, loading: loading3d(440) });
const DeviationRibbon = dynamic(() => import("@/components/inland/DeviationRibbon"), { ssr: false, loading: loading3d(360) });
const BandLadder = dynamic(() => import("@/components/inland/BandLadder"), { ssr: false, loading: loading3d(360) });

const LAYER_LABEL: Record<MaskKey, string> = {
  "2022-09-08": "EnMAP 2022-09-08", "2024-04-24": "EnMAP 2024-04-24", persistent_core: "Persistent core", mndwi_core: "MNDWI check",
};
const DOC_TITLES: Record<string, string> = {
  "inland-review-flags": "Integration review flags", "inland-aoi-selection": "AOI selection", "inland-data-access-audit": "Data access audit",
  "inland-water-mask": "Water mask", "inland-anomaly-and-fingerprint": "Anomaly and fingerprint",
  "inland-temporal-baseline-detector": "Temporal baseline detector", "inland-satellite-813-decision": "Satellite 813 decision",
  "inland-water-check-log": "Water-presence check (log)",
};

function Stat({ k, v, digits = 0, suffix = "", sub, color = "#EAF1FF", delay = 0 }: { k: string; v: number; digits?: number; suffix?: string; sub: React.ReactNode; color?: string; delay?: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState<number | null>(reduce ? v : 0);
  React.useEffect(() => { const t = setTimeout(() => setShown(v), reduce ? 0 : 250 + delay * 1000); return () => clearTimeout(t); }, [v, delay, reduce]);
  return (
    <motion.div initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.4 }}
      className="rounded-lg border border-edge/80 bg-panel/60 px-3 py-2.5">
      <div className="hud-kicker">{k}</div>
      <div className="mt-0.5 text-[24px] font-bold leading-none" style={{ color }}><Tween value={shown} digits={digits} suffix={suffix} /></div>
      <div className="mt-1 text-[11px] leading-snug text-muted">{sub}</div>
    </motion.div>
  );
}

function WaterPresence({ s }: { s: InlandSummary }) {
  const reduce = useReducedMotion();
  const max = Math.max(...s.water_presence_periods.map((p) => p.ndwi_gt0_pct[1]), 1) * 1.08;
  return (
    <div className="space-y-2.5">
      {s.water_presence_periods.map((p, i) => (
        <div key={p.period}>
          <div className="mb-1 flex justify-between text-[11px]"><span className="text-ink">{p.period}</span>
            <span className="hud-value text-muted">{p.ndwi_gt0_pct[0]}–{p.ndwi_gt0_pct[1]} % wet</span></div>
          <div className="relative h-[14px] rounded bg-deep">
            <motion.div className="absolute top-0 h-full rounded" style={{ left: `${(p.ndwi_gt0_pct[0] / max) * 100}%`, background: "linear-gradient(90deg,#1E5BB8,#27C3F3)" }}
              initial={reduce ? false : { width: 0 }} animate={{ width: `${((p.ndwi_gt0_pct[1] - p.ndwi_gt0_pct[0]) / max) * 100}%` }} transition={{ delay: 0.15 * i, duration: 0.8, ease: "easeOut" }} />
            <motion.div className="absolute top-[4px] h-[6px] rounded bg-white/80" style={{ left: `${(p.ndwi_gt01_pct[0] / max) * 100}%` }}
              initial={reduce ? false : { width: 0 }} animate={{ width: `${Math.max(0.6, ((p.ndwi_gt01_pct[1] - p.ndwi_gt01_pct[0]) / max) * 100)}%` }} transition={{ delay: 0.15 * i + 0.3, duration: 0.8, ease: "easeOut" }} />
          </div>
        </div>
      ))}
      <p className="text-[10.5px] leading-snug text-dim">Share of the AOI window with NDWI &gt; 0 (blue range) and &gt; 0.1 (white), 14 monthly Sentinel-2 scenes. The per-scene table the log cites is not in the package (flag F7); these are its period ranges.</p>
    </div>
  );
}

function Flags({ s }: { s: InlandSummary }) {
  const [open, setOpen] = useState<string | null>("F2");
  const [all, setAll] = useState(false);
  const order = { high: 0, medium: 1, low: 2, info: 3 } as Record<string, number>;
  const flags = [...s.flags].sort((a, b) => order[a.severity] - order[b.severity]);
  const shown = all ? flags : flags.slice(0, 6);
  return (
    <div className="space-y-1.5">
      {shown.map((f) => (
        <div key={f.id} className="rounded-md border border-edge/70 bg-deep/40">
          <button onClick={() => setOpen(open === f.id ? null : f.id)} className="flex w-full items-center gap-2 px-3 py-2 text-left">
            <span className="hud-value w-7 text-[11px] text-dim">{f.id}</span>
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: SEVERITY_COLOR[f.severity], boxShadow: `0 0 8px ${SEVERITY_COLOR[f.severity]}` }} />
            <span className="flex-1 text-[12.5px] font-semibold text-ink">{f.title}</span>
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: SEVERITY_COLOR[f.severity] }}>{f.severity}</span>
          </button>
          {open === f.id && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="px-3 pb-2.5 text-[12px] leading-relaxed text-muted">
              {f.detail}
              <div className="mt-1 text-[10.5px] text-dim">Evidence: <span className="hud-value">{f.evidence}</span></div>
            </motion.div>
          )}
        </div>
      ))}
      {flags.length > 6 && <button className="btn mt-1 px-3 py-1 text-[11px]" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${flags.length} flags`}</button>}
    </div>
  );
}

export default function InlandPage() {
  const { data: s, error } = useStatic<InlandSummary>("inland/summary.json");
  const docsIdx = useStatic<{ docs: { key: string; file: string; bytes: number }[] }>("docs/index.json").data;
  const reduce = useReducedMotion();
  const [layer, setLayer] = useState<MaskKey>("persistent_core");
  const [px, setPx] = useState<PixelHover | null>(null);
  const [rh, setRh] = useState<RibbonHover | null>(null);
  const [bh, setBh] = useState<BandHover | null>(null);
  const [f2, setF2] = useState(false);
  const [doc, setDoc] = useState<{ key: string; text: string } | null>(null);
  const inlandDocs = useMemo(() => (docsIdx?.docs || []).filter((d) => d.key.startsWith("inland-")), [docsIdx]);
  const openDoc = async (key: string) => {
    setDoc({ key, text: "Loading…" });
    try { const r = await fetch(pipelineUrl(`docs/${key}.md`)); setDoc({ key, text: r.ok ? await r.text() : `Could not load ${key}` }); }
    catch { setDoc({ key, text: `Could not load ${key}` }); }
  };

  if (!s) return <div className="grid h-full place-items-center text-muted">{error ? `Inland summary missing (${error}). Run scripts/inland/build_inland_bundle.py and scripts/build_static_site.py.` : "Loading inland results…"}</div>;

  const m = s.masks, t = s.temporal, an = s.anomaly, sup = s.satellite813.simulation_support?.["2024-04-24"];
  const overlap = m["2022-09-08"].px.filter(([r, c]) => m["2024-04-24"].px.some(([r2, c2]) => r2 === r && c2 === c)).length;
  const fpDate = layer === "2022-09-08" || layer === "2024-04-24" ? layer : null;
  const classCounts = fpDate ? an.per_date?.[fpDate]?.fingerprint_top_class_counts : an.per_date?.["2024-04-24"]?.fingerprint_top_class_counts;
  const pxArea = s.window.resolution_m ** 2;

  return (
    <div className="space-y-3 p-3 short:space-y-2 short:p-2">
      {/* ---------------------------------------------------------------- header */}
      <div className="relative overflow-hidden rounded-panel border border-edge/80 bg-gradient-to-br from-panel2/90 via-panel/70 to-void px-5 py-4">
        {!reduce && <motion.div aria-hidden className="pointer-events-none absolute inset-y-0 w-40 bg-gradient-to-r from-transparent via-cyan/10 to-transparent"
          initial={{ x: "-20%" }} animate={{ x: "120vw" }} transition={{ duration: 5.5, repeat: Infinity, ease: "linear", repeatDelay: 2 }} />}
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="hud-kicker flex items-center gap-2"><Droplets size={13} className="text-cyan" /> Inland complement · {s.site.emirate} · EnMAP L2A hyperspectral</div>
            <h1 className="font-display text-[30px] font-extrabold tracking-wide short:text-[26px]">
              <span className="bg-gradient-to-r from-ink via-cyan to-beam2 bg-clip-text text-transparent">{s.site.name}</span>
              <span className="ml-3 align-middle text-[13px] font-semibold tracking-[0.2em] text-muted">{s.site.id}</span>
            </h1>
            <p className="mt-1 max-w-[760px] text-[12.5px] leading-relaxed text-muted">
              A wadi reservoir {s.window.polygon_size_m[0]} m × {s.window.polygon_size_m[1]} m, seen by EnMAP on {Object.keys(s.scenes).join(" and ")} (0 % cloud) and by
              {" "}{t.n_observations} Sentinel-2 / Landsat observations from September 2023 to October 2025. Static results from a separately built module, integrated as an add-on.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Chip label="STATIC · 2 FIXED DATES" color="#27C3F3" />
            <Chip label={`EnMAP LICENCE: ${s.licence.enmap.toUpperCase()}`} color="#FF8A3D" />
            <SimBadge />
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------------- caveats, verbatim */}
      <div className="flex gap-3 rounded-panel border border-caution/50 bg-caution/[0.06] px-4 py-3">
        <ShieldAlert size={18} className="mt-0.5 shrink-0 text-caution" />
        <div className="text-[12.5px] leading-relaxed">
          <div className="mb-0.5 font-bold tracking-wide text-caution">Two caveats, carried over exactly</div>
          <div><span className="text-muted">Licence: </span><span className="text-ink">{s.caveats[0]}.</span></div>
          <div><span className="text-muted">Detector: </span><span className="text-ink">{s.caveats[1]}.</span></div>
          <div className="mt-1 text-[11px] text-dim">Per-pixel EnMAP reflectance layers and spectra are therefore not published here; this screen shows derived masks, scores and counts. {s.licence.attribution}.</div>
        </div>
      </div>

      {/* ---------------------------------------------------------------- wet core + stats */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <Panel kicker="EnMAP · 25 × 30 px · 30 m · drag to orbit" title="Wet-core map"
          right={<div className="flex flex-wrap gap-1">{MASK_KEYS.map((k) => (
            <button key={k} onClick={() => setLayer(k)} className={`btn px-2.5 py-1 text-[11px] ${layer === k ? "border-beam bg-beam/20 text-ink" : ""}`}>
              {LAYER_LABEL[k]} <span className="hud-value text-dim">{m[k].n}</span></button>))}</div>}
          bodyClass="relative">
          <WetCoreScene s={s} layer={layer} onHover={setPx} height={440} />
          <div className="pointer-events-none absolute left-3 top-3 max-w-[330px] rounded-md border border-edge/70 bg-void/80 px-3 py-2 text-[11px] leading-snug backdrop-blur">
            <div className="font-bold text-ink">{m[layer].label}</div>
            <div className="text-muted">{m[layer].method}</div>
            <div className="mt-1 text-cyan">{m[layer].n} px wet{m[layer].wet_fraction_of_polygon_pct != null ? ` · ${m[layer].wet_fraction_of_polygon_pct.toFixed(1)} % of the polygon` : ""}</div>
          </div>
          <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-md bg-void/75 px-3 py-1.5 text-[10.5px] text-muted backdrop-blur">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#2A5C9E]" />inside polygon ({s.window.n_inside_reconstructed} px)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#27C3F3]" />wet</span>
            {fpDate && Object.keys(classCounts || {}).map((c) => <span key={c} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rotate-45" style={{ background: FP_COLOR[c] }} />{c.replace(/_/g, " ").toLowerCase()}</span>)}
          </div>
          {px && (
            <div className="pointer-events-none absolute right-3 top-3 w-[230px] rounded-md border border-caution/50 bg-void/90 px-3 py-2 text-[11px] backdrop-blur">
              <div className="hud-value font-bold text-caution">pixel row {px.row} · col {px.col}</div>
              <div className="text-muted">{px.inside ? "inside" : "outside"} the locked polygon</div>
              <div className="mt-1 grid grid-cols-2 gap-x-2">{MASK_KEYS.map((k) => <React.Fragment key={k}><span className="text-dim">{LAYER_LABEL[k]}</span><span className={px.wet[k] ? "text-cyan" : "text-dim"}>{px.wet[k] ? "wet" : "-"}</span></React.Fragment>)}</div>
              {px.fp && <div className="mt-1 border-t border-edge pt-1"><span style={{ color: FP_COLOR[px.fp.top_class || ""] }}>{px.fp.top_class}</span>
                <div className="text-dim">RX {px.fp.rx_score.toFixed(2)} vs threshold {px.fp.rx_threshold.toFixed(2)} ({fpDate || "2024-04-24"})</div></div>}
            </div>
          )}
        </Panel>

        <div className="grid content-start gap-3">
          <div className="grid grid-cols-2 gap-2">
            <Stat k="Persistent wet core" v={m.persistent_core.n} suffix=" px" color="#27C3F3" delay={0}
              sub={<>{((m.persistent_core.n * pxArea) / 1e4).toFixed(1)} ha · {m.persistent_core.wet_fraction_of_polygon_pct?.toFixed(1)} % of {m.px_inside_locked_polygon_reported} px · dark on both dates</>} />
            <Stat k="2024-04-24 alone" v={m["2024-04-24"].n} suffix=" px" color="#FFC23D" delay={0.08}
              sub={<>same thresholds; overlaps the 2022 mask in {overlap} px (flag F11)</>} />
            <Stat k="Real-MNDWI cross-check" v={m.mndwi_core.n} suffix=" px" color="#FF8A3D" delay={0.16}
              sub={<>a standard water index does not reproduce the core</>} />
            <Stat k="RX anomaly events" v={(an.per_date?.["2022-09-08"]?.n_events || 0) + (an.per_date?.["2024-04-24"]?.n_events || 0)} color="#93A6CB" delay={0.24}
              sub={<>structural: test pixels sit inside their own background (F5)</>} />
            <Stat k="Temporal flags" v={t.n_flagged} suffix={` / ${t.n_observations}`} color="#FF4D5E" delay={0.32}
              sub={<>chance alone: {t.chance_level.expected_flags_if_indices_perfectly_correlated}–{t.chance_level.expected_flags_if_indices_independent} (F4)</>} />
            <Stat k="813 bands with EnMAP support" v={sup?.n_with_real_support || 0} suffix={` / ${s.satellite813.spec813.n_bands}`} color="#23D484" delay={0.4}
              sub={<>{sup ? sup.unsupported_ranges_nm.map(([a, b]) => `${Math.round(a)}–${Math.round(b)} nm`).join(", ") : "n/a"} left empty</>} />
          </div>
          <Panel kicker={`Fingerprint classes on the core · ${fpDate || "2024-04-24"}`} title="What the 10 core pixels look like" bodyClass="px-4 pb-3">
            <div className="flex h-3 overflow-hidden rounded-full bg-deep">
              {Object.entries(classCounts || {}).map(([c, n]) => (
                <motion.div key={c} title={`${c}: ${n}`} style={{ background: FP_COLOR[c] }} initial={reduce ? false : { width: 0 }} animate={{ width: `${(n / 10) * 100}%` }} transition={{ duration: 0.7 }} />))}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px]">{Object.entries(classCounts || {}).map(([c, n]) => (
              <span key={c} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: FP_COLOR[c] }} /><span className="text-ink">{n}</span><span className="text-muted">{c.replace(/_/g, " ").toLowerCase()}</span></span>))}</div>
            <p className="mt-2 text-[10.5px] leading-snug text-dim">Rule-based scores on six band groups; descriptive, not a calibrated classifier (see the detector caveat).</p>
          </Panel>
          <Panel kicker="Sentinel-2 water presence · Sep 2023 – Oct 2025" title="The pool is drying" right={<Waves size={16} className="text-cyan" />} bodyClass="px-4 pb-3">
            <WaterPresence s={s} />
          </Panel>
        </div>
      </div>

      {/* ---------------------------------------------------------------- ribbon + ladder */}
      <div className="grid gap-3 xl:grid-cols-2">
        <Panel kicker="z-score against each sensor's own two-year mean · drag to orbit" title="Deviation ribbon · Sentinel-2 + Landsat" right={<ScanLine size={16} className="text-cyan" />} bodyClass="relative">
          <DeviationRibbon s={s} height={360} onHover={setRh} />
          <div className="pointer-events-none absolute bottom-2 left-3 flex gap-3 text-[10.5px] text-muted">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#27C3F3]" />Sentinel-2 ({t.per_sensor_n["sentinel-2-l2a"]})</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#FFC23D]" />Landsat ({t.per_sensor_n["landsat-c2-l2"]})</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#FF4D5E]" />|z| &gt; {t.z_threshold}</span>
          </div>
          {rh && <div className="pointer-events-none absolute right-3 top-3 rounded-md border border-edge bg-void/90 px-3 py-2 text-[11px]">
            <div className="hud-value font-bold text-ink">{rh.date} · {rh.sensor}</div><div className="text-muted">{rh.index}</div>
            <div className={rh.flagged ? "text-critical" : "text-cyan"}>z = {rh.z.toFixed(2)}{rh.flagged ? " · flagged" : ""}</div></div>}
        </Panel>
        <Panel kicker="every band on one wavelength axis · drag to orbit" title="EnMAP → 813 band ladder" bodyClass="relative"
          right={<button onClick={() => setF2(!f2)} className={`btn px-2.5 py-1 text-[11px] ${f2 ? "border-caution bg-caution/15 text-ink" : ""}`}><Layers size={13} />{f2 ? "Hide" : "Show"} flag F2</button>}>
          <BandLadder s={s} showF2={f2} height={360} onHover={setBh} />
          {bh && <div className="pointer-events-none absolute right-3 top-3 max-w-[260px] rounded-md border border-edge bg-void/90 px-3 py-2 text-[11px]">
            <div className="font-bold text-ink">{bh.sensor} · {bh.band}</div>
            <div className="hud-value text-cyan">{bh.nm.toFixed(1)} nm · FWHM {bh.fwhm.toFixed(1)} nm</div><div className="text-muted">{bh.note}</div></div>}
          {f2 && <div className="pointer-events-none absolute bottom-2 left-3 max-w-[70%] text-[10.5px] text-caution">2022-09-08 as DLR&apos;s STAC publishes it: amber bands sit 11–12 nm higher, red ones moved across the water-vapour gap.</div>}
        </Panel>
      </div>

      {/* ---------------------------------------------------------------- flags + docs */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Panel kicker="Integration review · flagged, not fixed" title={<span className="flex items-center gap-2"><AlertTriangle size={15} className="text-caution" />What looks off, with evidence</span>} bodyClass="px-4 pb-3">
          <Flags s={s} />
        </Panel>
        <Panel kicker="The module's own documents, verbatim" title="Documents" bodyClass="px-4 pb-3">
          <div className="space-y-1">
            {inlandDocs.map((d) => (
              <button key={d.key} onClick={() => openDoc(d.key)} className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-[12px] text-muted hover:bg-white/5 hover:text-ink">
                <span className="flex items-center gap-2"><FileText size={13} />{DOC_TITLES[d.key] || d.file}</span><span className="text-[10px] text-dim">{(d.bytes / 1024).toFixed(0)} KB</span>
              </button>))}
            {!inlandDocs.length && <p className="text-[12px] text-dim">Documents load from the static bundle.</p>}
          </div>
          <div className="rule-h my-3" />
          <div className="text-[11px] leading-relaxed text-dim">
            Window rebuilt from DLR&apos;s STAC grid: {s.window.n_inside_reconstructed} px inside the polygon (the package reports {m.px_inside_locked_polygon_reported}).
            API: <span className="hud-value">GET /api/inland/summary</span>. Code: <span className="hud-value">pipeline/inland/</span>, data: <span className="hud-value">data/inland/</span>.
          </div>
        </Panel>
      </div>

      <Drawer open={!!doc} onClose={() => setDoc(null)} title={doc ? DOC_TITLES[doc.key] || doc.key : ""} width={760}>
        {doc && <Markdown text={doc.text} />}
      </Drawer>
    </div>
  );
}
