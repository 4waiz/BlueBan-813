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
import { Chip, Drawer, Panel, SimBadge, Tabs, Tween } from "@/components/ui";
import Markdown from "@/components/ui/Markdown";
import { FP_COLOR, MASK_KEYS, SEVERITY_COLOR, type InlandSummary, type MaskKey } from "@/components/inland/types";
import type { PixelHover } from "@/components/inland/WetCoreScene";
import type { RibbonHover } from "@/components/inland/DeviationRibbon";
import type { BandHover } from "@/components/inland/BandLadder";

function Loading3d() { return <div className="grid h-full place-items-center text-[12px] text-dim">Building 3D scene…</div>; }
const WetCoreScene = dynamic(() => import("@/components/inland/WetCoreScene"), { ssr: false, loading: Loading3d });
const DeviationRibbon = dynamic(() => import("@/components/inland/DeviationRibbon"), { ssr: false, loading: Loading3d });
const BandLadder = dynamic(() => import("@/components/inland/BandLadder"), { ssr: false, loading: Loading3d });

type View = "pool" | "dates" | "notes";

const LAYER_LABEL: Record<MaskKey, string> = {
  "2022-09-08": "Sep 2022", "2024-04-24": "Apr 2024", persistent_core: "Wet on both dates", mndwi_core: "Water-index check",
};
/** One plain line per layer; the exact test stays in the tooltip. */
const LAYER_PLAIN: Record<MaskKey, string> = {
  "2022-09-08": "Pixels dark enough to be water on 8 Sep 2022.",
  "2024-04-24": "The same test on 24 Apr 2024 finds a different spot.",
  persistent_core: "Pixels that look like water on both dates: the pool.",
  mndwi_core: "A standard water index finds no water pixels. A caution sign.",
};
const DOC_TITLES: Record<string, string> = {
  "inland-review-flags": "Review notes", "inland-aoi-selection": "AOI selection", "inland-data-access-audit": "Data access audit",
  "inland-water-mask": "Water mask", "inland-anomaly-and-fingerprint": "Anomaly and fingerprint",
  "inland-temporal-baseline-detector": "Temporal baseline detector", "inland-satellite-813-decision": "Satellite 813 decision",
  "inland-water-check-log": "Water-presence log",
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
      <div className="mt-1 text-[11px] leading-snug text-muted mini:hidden">{sub}</div>
    </motion.div>
  );
}

function WaterPresence({ s }: { s: InlandSummary }) {
  const reduce = useReducedMotion();
  const max = Math.max(...s.water_presence_periods.map((p) => p.ndwi_gt0_pct[1]), 1) * 1.08;
  return (
    <div className="space-y-2 tiny:space-y-1.5">
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
      <p className="text-[10.5px] leading-snug text-dim mini:hidden">How much of the area shows water in monthly Sentinel-2 images. Blue: any water. White: clear open water.</p>
    </div>
  );
}

function Flags({ s }: { s: InlandSummary }) {
  const [open, setOpen] = useState<string | null>(null);
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
            <span className="min-w-0 flex-1"><span className="block text-[12.5px] font-semibold text-ink">{f.title}</span>
              {f.plain && <span className="block text-[11.5px] leading-snug text-muted">{f.plain}</span>}</span>
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: SEVERITY_COLOR[f.severity] }}>{f.severity}</span>
          </button>
          {open === f.id && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="px-3 pb-2.5 pl-12 text-[11.5px] leading-relaxed text-dim">
              {f.detail}
              <div className="mt-1 text-[10.5px] text-dim">Source: <span className="hud-value">{f.evidence}</span></div>
            </motion.div>
          )}
        </div>
      ))}
      {flags.length > 6 && <button className="btn mt-1 px-3 py-1 text-[11px]" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${flags.length} notes`}</button>}
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
  const [view, setView] = useState<View>("pool");
  const [doc, setDoc] = useState<{ key: string; text: string } | null>(null);
  const inlandDocs = useMemo(() => (docsIdx?.docs || []).filter((d) => d.key.startsWith("inland-")), [docsIdx]);
  const openDoc = async (key: string) => {
    setDoc({ key, text: "Loading…" });
    try { const r = await fetch(pipelineUrl(`docs/${key}.md`)); setDoc({ key, text: r.ok ? await r.text() : `Could not load ${key}` }); }
    catch { setDoc({ key, text: `Could not load ${key}` }); }
  };

  if (!s) return <div className="grid h-full place-items-center text-muted">{error ? `Inland results are missing (${error}).` : "Loading inland results…"}</div>;

  const m = s.masks, t = s.temporal, an = s.anomaly, sup = s.satellite813.simulation_support?.["2024-04-24"];
  const overlap = m["2022-09-08"].px.filter(([r, c]) => m["2024-04-24"].px.some(([r2, c2]) => r2 === r && c2 === c)).length;
  const fpDate = layer === "2022-09-08" || layer === "2024-04-24" ? layer : null;
  const classCounts = fpDate ? an.per_date?.[fpDate]?.fingerprint_top_class_counts : an.per_date?.["2024-04-24"]?.fingerprint_top_class_counts;
  const pxArea = s.window.resolution_m ** 2;

  // Desktop: one screen. Header and caveats on top, the three sections behind
  // tabs that fill the remaining height. Smaller screens stack and scroll.
  return (
    <div className="space-y-3 p-3 short:space-y-2 short:p-2 xl:flex xl:h-full xl:flex-col xl:gap-3 xl:space-y-0 short:xl:gap-2">
      {/* ---------------------------------------------------------------- header */}
      <div className="relative shrink-0 overflow-hidden rounded-panel border border-edge/80 bg-gradient-to-br from-panel2/90 via-panel/70 to-void px-5 py-4 short:py-2.5">
        {!reduce && <motion.div aria-hidden className="pointer-events-none absolute inset-y-0 w-40 bg-gradient-to-r from-transparent via-cyan/10 to-transparent"
          initial={{ x: "-20%" }} animate={{ x: "120vw" }} transition={{ duration: 5.5, repeat: Infinity, ease: "linear", repeatDelay: 2 }} />}
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="hud-kicker flex items-center gap-2"><Droplets size={13} className="text-cyan" /> Inland water · {s.site.emirate} · EnMAP hyperspectral satellite</div>
            <h1 className="font-display text-[30px] font-extrabold tracking-wide short:text-[22px]">
              <span className="bg-gradient-to-r from-ink via-cyan to-beam2 bg-clip-text text-transparent">{s.site.name}</span>
              <span className="ml-3 align-middle text-[13px] font-semibold tracking-[0.2em] text-muted">{s.site.id}</span>
            </h1>
            <p className="mt-1 max-w-[760px] text-[12.5px] leading-relaxed text-muted">
              A small dam reservoir, {s.window.polygon_size_m[0]} × {s.window.polygon_size_m[1]} m. Seen by EnMAP on two cloud-free days and in {t.n_observations} Sentinel-2
              and Landsat images from 2023 to 2025. These are fixed results, not a live feed.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Chip label="FIXED RESULTS · 2 DATES" color="#27C3F3" />
            <Chip label={`EnMAP LICENCE: ${s.licence.enmap.toUpperCase()}`} color="#FF8A3D" />
            <SimBadge />
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------------- caveats, verbatim */}
      <div className="flex shrink-0 gap-3 rounded-panel border border-caution/50 bg-caution/[0.06] px-4 py-3 short:py-2">
        <ShieldAlert size={18} className="mt-0.5 shrink-0 text-caution" />
        <div className="text-[12.5px] leading-relaxed">
          <div className="mb-0.5 font-bold tracking-wide text-caution">Please note</div>
          <div><span className="text-muted">Licence: </span><span className="text-ink">{s.caveats[0]}.</span></div>
          <div><span className="text-muted">Detector: </span><span className="text-ink">{s.caveats[1]}.</span></div>
          <div className="mt-1 text-[11px] text-dim">So this page shows results only (masks, scores and counts), not raw EnMAP pixels. {s.licence.attribution}.</div>
        </div>
      </div>

      <Tabs className="shrink-0" value={view} onChange={setView} tabs={[
        { key: "pool", label: "Where the water is" },
        { key: "dates", label: "Unusual dates · 813 bands" },
        { key: "notes", label: `Review notes (${s.flags.length}) · documents` },
      ]} />

      {/* ---------------------------------------------------------------- wet core + stats */}
      {view === "pool" && <div className="grid gap-3 xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)] xl:grid-rows-[auto_minmax(0,1fr)]">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:col-span-2 xl:grid-cols-6">
            <Stat k="Water pool" v={m.persistent_core.n} suffix=" px" color="#27C3F3" delay={0}
              sub={<>about {((m.persistent_core.n * pxArea) / 1e4).toFixed(1)} ha · wet on both dates</>} />
            <Stat k="April 2024 alone" v={m["2024-04-24"].n} suffix=" px" color="#FFC23D" delay={0.08}
              sub={<>{overlap === 0 ? "none of them overlap" : `${overlap} overlap`} with 2022 (note F11)</>} />
            <Stat k="Water-index check" v={m.mndwi_core.n} suffix=" px" color="#FF8A3D" delay={0.16}
              sub={<>a standard index does not confirm the pool</>} />
            <Stat k="Anomaly alerts" v={(an.per_date?.["2022-09-08"]?.n_events || 0) + (an.per_date?.["2024-04-24"]?.n_events || 0)} color="#93A6CB" delay={0.24}
              sub={<>expected by design, so not proof of clean water (F5)</>} />
            <Stat k="Unusual dates" v={t.n_flagged} suffix={` / ${t.n_observations}`} color="#FF4D5E" delay={0.32}
              sub={<>chance alone gives {t.chance_level.expected_flags_if_indices_perfectly_correlated}–{t.chance_level.expected_flags_if_indices_independent} (F4)</>} />
            <Stat k="813 bands we can simulate" v={sup?.n_with_real_support || 0} suffix={` / ${s.satellite813.spec813.n_bands}`} color="#23D484" delay={0.4}
              sub={<>{sup ? `${sup.unsupported_ranges_nm.length} gaps left empty, not invented` : "n/a"}</>} />
          </div>
        <Panel kicker="Each tile is one 30 m pixel · drag to rotate" title="Where the water is"
          right={<div className="flex flex-wrap gap-1">{MASK_KEYS.map((k) => (
            <button key={k} onClick={() => setLayer(k)} className={`btn px-2.5 py-1 text-[11px] ${layer === k ? "border-beam bg-beam/20 text-ink" : ""}`}>
              {LAYER_LABEL[k]} <span className="hud-value text-dim">{m[k].n}</span></button>))}</div>}
          bodyClass="relative h-[440px] overflow-hidden xl:h-auto">
          <WetCoreScene s={s} layer={layer} onHover={setPx} height="100%" />
          <div className="pointer-events-none absolute left-3 top-3 max-w-[330px] rounded-md border border-edge/70 bg-void/80 px-3 py-2 text-[11px] leading-snug backdrop-blur">
            <div className="font-bold text-ink" title={m[layer].method}>{LAYER_LABEL[layer]}</div>
            <div className="text-muted">{LAYER_PLAIN[layer]}</div>
            <div className="mt-1 text-cyan">{m[layer].n} water pixels{m[layer].wet_fraction_of_polygon_pct != null ? ` · ${m[layer].wet_fraction_of_polygon_pct.toFixed(1)} % of the dam area` : ""}</div>
          </div>
          <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-md bg-void/75 px-3 py-1.5 text-[10.5px] text-muted backdrop-blur">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#2A5C9E]" />dam area ({s.window.n_inside_reconstructed} pixels)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#27C3F3]" />water</span>
            {fpDate && Object.keys(classCounts || {}).map((c) => <span key={c} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rotate-45" style={{ background: FP_COLOR[c] }} />{c.replace(/_/g, " ").toLowerCase()}</span>)}
          </div>
          {px && (
            <div className="pointer-events-none absolute right-3 top-3 w-[230px] rounded-md border border-caution/50 bg-void/90 px-3 py-2 text-[11px] backdrop-blur">
              <div className="hud-value font-bold text-caution">pixel row {px.row} · col {px.col}</div>
              <div className="text-muted">{px.inside ? "inside" : "outside"} the dam area</div>
              <div className="mt-1 grid grid-cols-2 gap-x-2">{MASK_KEYS.map((k) => <React.Fragment key={k}><span className="text-dim">{LAYER_LABEL[k]}</span><span className={px.wet[k] ? "text-cyan" : "text-dim"}>{px.wet[k] ? "water" : "-"}</span></React.Fragment>)}</div>
              {px.fp && <div className="mt-1 border-t border-edge pt-1"><span style={{ color: FP_COLOR[px.fp.top_class || ""] }}>{px.fp.top_class}</span>
                <div className="text-dim">anomaly score {px.fp.rx_score.toFixed(2)} (alert above {px.fp.rx_threshold.toFixed(2)})</div></div>}
            </div>
          )}
        </Panel>

        {/* the six numbers sit in a strip above; this column holds two panels that fit */}
        <div className="scroll-quiet flex flex-col gap-3 xl:grid xl:min-h-0 xl:grid-cols-2 xl:content-start xl:overflow-y-auto [&>*]:shrink-0">
          <Panel kicker={`Pool pixels by type · ${fpDate || "2024-04-24"}`} title="What the water looks like" bodyClass="px-4 pb-3">
            <div className="flex h-3 overflow-hidden rounded-full bg-deep">
              {Object.entries(classCounts || {}).map(([c, n]) => (
                <motion.div key={c} title={`${c}: ${n}`} style={{ background: FP_COLOR[c] }} initial={reduce ? false : { width: 0 }} animate={{ width: `${(n / 10) * 100}%` }} transition={{ duration: 0.7 }} />))}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px]">{Object.entries(classCounts || {}).map(([c, n]) => (
              <span key={c} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: FP_COLOR[c] }} /><span className="text-ink">{n}</span><span className="text-muted">{c.replace(/_/g, " ").toLowerCase()}</span></span>))}</div>
            <p className="mt-2 text-[10.5px] leading-snug text-dim">Simple colour rules. A rough guide, not a lab result.</p>
          </Panel>
          <Panel kicker="Sentinel-2 · Sep 2023 to Oct 2025" title="The pool is drying up" right={<Waves size={16} className="text-cyan" />} bodyClass="px-4 pb-3">
            <WaterPresence s={s} />
          </Panel>
        </div>
      </div>}

      {/* ---------------------------------------------------------------- ribbon + ladder */}
      {view === "dates" && <div className="grid gap-3 xl:min-h-0 xl:flex-1 xl:grid-cols-2">
        <Panel kicker="How unusual each image is · drag to rotate" title="Unusual dates · Sentinel-2 and Landsat" right={<ScanLine size={16} className="text-cyan" />} bodyClass="relative h-[360px] overflow-hidden xl:h-auto">
          <DeviationRibbon s={s} height="100%" onHover={setRh} />
          <div className="pointer-events-none absolute bottom-2 left-3 flex gap-3 text-[10.5px] text-muted">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#27C3F3]" />Sentinel-2 ({t.per_sensor_n["sentinel-2-l2a"]})</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#FFC23D]" />Landsat ({t.per_sensor_n["landsat-c2-l2"]})</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#FF4D5E]" />flagged as unusual</span>
          </div>
          {rh && <div className="pointer-events-none absolute right-3 top-3 rounded-md border border-edge bg-void/90 px-3 py-2 text-[11px]">
            <div className="hud-value font-bold text-ink">{rh.date} · {rh.sensor}</div><div className="text-muted">{rh.index}</div>
            <div className={rh.flagged ? "text-critical" : "text-cyan"}>{rh.flagged ? "unusual" : "normal"} (score {rh.z.toFixed(1)})</div></div>}
        </Panel>
        <Panel kicker="Every colour band each sensor sees · drag to rotate" title="EnMAP vs Satellite 813 bands" bodyClass="relative h-[360px] overflow-hidden xl:h-auto"
          right={<button onClick={() => setF2(!f2)} className={`btn px-2.5 py-1 text-[11px] ${f2 ? "border-caution bg-caution/15 text-ink" : ""}`}><Layers size={13} />{f2 ? "Hide" : "Show"} note F2</button>}>
          <BandLadder s={s} showF2={f2} height="100%" onHover={setBh} />
          {bh && <div className="pointer-events-none absolute right-3 top-3 max-w-[260px] rounded-md border border-edge bg-void/90 px-3 py-2 text-[11px]">
            <div className="font-bold text-ink">{bh.sensor} · {bh.band}</div>
            <div className="hud-value text-cyan">{bh.nm.toFixed(1)} nm · width {bh.fwhm.toFixed(1)} nm</div><div className="text-muted">{bh.note}</div></div>}
          {f2 && <div className="pointer-events-none absolute bottom-2 left-3 max-w-[70%] text-[10.5px] text-caution">The real Sep 2022 band positions: amber bands sit 11–12 nm off, red ones jumped a gap.</div>}
        </Panel>
      </div>}

      {/* ---------------------------------------------------------------- flags + docs */}
      {view === "notes" && <div className="grid gap-3 xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Panel kicker="Review notes · flagged, not changed" title={<span className="flex items-center gap-2"><AlertTriangle size={15} className="text-caution" />Things to double-check</span>} bodyClass="px-4 pb-3 scroll-quiet xl:overflow-y-auto">
          <Flags s={s} />
        </Panel>
        <Panel kicker="Full write-ups" title="Documents" bodyClass="px-4 pb-3 scroll-quiet xl:overflow-y-auto">
          <div className="space-y-1">
            {inlandDocs.map((d) => (
              <button key={d.key} onClick={() => openDoc(d.key)} className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-[12px] text-muted hover:bg-white/5 hover:text-ink">
                <span className="flex items-center gap-2"><FileText size={13} />{DOC_TITLES[d.key] || d.file}</span><span className="text-[10px] text-dim">{(d.bytes / 1024).toFixed(0)} KB</span>
              </button>))}
            {!inlandDocs.length && <p className="text-[12px] text-dim">Documents load from the static bundle.</p>}
          </div>
          <div className="rule-h my-3" />
          <div className="text-[11px] leading-relaxed text-dim">
            Data: <span className="hud-value">data/inland/</span> · API: <span className="hud-value">/api/inland/summary</span>
          </div>
        </Panel>
      </div>}

      <Drawer open={!!doc} onClose={() => setDoc(null)} title={doc ? DOC_TITLES[doc.key] || doc.key : ""} width={760}>
        {doc && <Markdown text={doc.text} />}
      </Drawer>
    </div>
  );
}
