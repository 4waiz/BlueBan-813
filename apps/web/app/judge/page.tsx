"use client";
/**
 * JUDGE MODE - why it matters, the closed loop, and who it is for, in thirteen
 * steps, about three minutes.
 *
 * Every number on screen is read live from this visitor's workspace (the same
 * engine the operational screens use) or from the pipeline outputs; the only
 * typed-in facts are the two sourced context facts on the first step. The
 * review, training and promotion steps are real actions, so autoplay waits for
 * the presenter there. The workspace can be reset from Settings.
 */
import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight, BrainCircuit, CheckCircle2, ChevronLeft, ChevronRight, CircleX, FlaskConical, Pause, Play,
  RotateCcw, Satellite, ShieldCheck, Sparkles, UserCheck, Waves,
} from "lucide-react";
import { getOperator, mutate, useEngineQuery, useStatic } from "@/lib/engine";
import type { GateCheck, Incident, LabelRow, ModelRecord, TrainingJob } from "@/lib/engine/types";
import SpectrumPlot from "@/components/spectra/SpectrumPlot";
import { Chip, fmt, SimBadge, STATE_COLOR, STATE_TEXT, toast } from "@/components/ui";

const DECISION_TEXT: Record<string, string> = { CONFIRM: "Confirmed", FALSE_POSITIVE: "False alarm", NEEDS_FIELD_SAMPLE: "Water sample requested" };
/** Safety-check names in plain words (the engine keeps its own identifiers). */
const GATE_LABEL: Record<string, string> = {
  model_test_suite: "Passes all model tests", validation_dataset_unchanged: "Test set unchanged",
  validation_has_both_classes: "Test set has real and false events", primary_metric_not_worse: "Detection no worse than the live model",
  calibration_acceptable: "Confidence levels acceptable", no_subgroup_regression: "No monitored area gets worse",
};

const IncidentMap = dynamic(() => import("@/components/map/IncidentMap"), { ssr: false });
const CubeViewer = dynamic(() => import("@/components/spectra/CubeViewer"), { ssr: false });

type Stage = "why" | "coast" | "sensors" | "change" | "features" | "cube" | "quantify" | "review" | "label" | "retrain" | "gate" | "impact" | "loop";
const STEPS: { stage: Stage; say: string; secs: number; action?: boolean }[] = [
  { stage: "why", say: "The UAE drinks the sea. When the sea changes, the taps are at risk.", secs: 15 },
  { stage: "coast", say: "This is the UAE coastline BlueBan watches.", secs: 11 },
  { stage: "sensors", say: "Sentinel-2 photographs this water every few days. Sentinel-3 gives a second opinion.", secs: 12 },
  { stage: "change", say: "Something changed.", secs: 10 },
  { stage: "features", say: "One index is not enough. BlueBan checks several signals against this spot's own past.", secs: 15 },
  { stage: "cube", say: "Satellite 813 adds a detailed colour fingerprint. Here it is simulated.", secs: 15 },
  { stage: "quantify", say: "Water samples would let BlueBan estimate concentrations, with uncertainty. Without them, it shows none.", secs: 14 },
  { stage: "review", say: "A person, not the model, makes the final call.", secs: 12, action: true },
  { stage: "label", say: "Each decision becomes a verified label the model can learn from.", secs: 10 },
  { stage: "retrain", say: "With enough verified labels, we train a new model.", secs: 12, action: true },
  { stage: "gate", say: "The live model stays until the new one passes a safety check. A person signs off.", secs: 14, action: true },
  { stage: "impact", say: "Built for the people who must decide before the water reaches the intake.", secs: 16 },
  { stage: "loop", say: "BlueBan does more than detect. Satellites, analysts and field teams improve it with every incident.", secs: 16 },
];

/** The two context facts behind step 1, with their sources (not computed by BlueBan). */
const WHY_FACTS = [
  { k: "Drinking water", v: "~70 plants", sub: "Most of the UAE's drinking water comes from about 70 major desalination plants on its two coasts.", src: "UAE Government portal (u.ae), Water", url: "https://u.ae/en/information-and-services/environment-and-energy/water-and-energy/water-" },
  { k: "2008–09 red tide", v: "up to 4 months", sub: "A Cochlodinium bloom spread across the Gulf of Oman and the Gulf. Reverse-osmosis desalination plants shut for up to four months, Fujairah's among them.", src: "IOC-UNESCO (2017), Harmful Algal Blooms and Desalination, Manuals and Guides 78", url: "https://repository.oceanbestpractices.org/handle/11329/759" },
];
const CLOSING = "BlueBan turns every coastal incident into both a response and a lesson.";

type VSum = {
  A_data_quality: { aois: { aoi_id: string; n_ok: number; n_usable: number; date_range: [string, string] }[] };
  B_matchups: { cross_sensor: { n: number; median_abs_dt_minutes?: number | null } };
  C_model_performance?: { production?: { metrics?: { auprc?: number } }; candidate?: { metrics?: { auprc?: number } }; bootstrap?: { auprc?: { ci?: [number, number] } } };
  D_813_ablation: { hard?: { arms: Record<string, { confusion_matrix?: { fp: number } }> } };
};

function Fact({ k, v, sub, tone = "text-ink" }: { k: string; v: React.ReactNode; sub?: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-md border border-edge bg-deep/70 px-3 py-2">
      <div className="hud-kicker">{k}</div>
      <div className={`hud-value text-[20px] font-bold ${tone}`}>{v}</div>
      {sub && <div className="text-[11px] text-muted">{sub}</div>}
    </div>
  );
}

function metricOf(m: ModelRecord | null | undefined, k: string): number | null {
  const r = m?.metrics?.find((x) => x.metric === k && x.split === "validation" && x.subgroup === "all");
  if (r?.value != null) return r.value;
  return ((m?.gate?.summary?.candidate || {}) as Record<string, number>)[k] ?? null;
}

function Judge() {
  const reduce = useReducedMotion();
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reviewOut, setReviewOut] = useState<{ before: string; after: string; label: string | null; decision: string } | null>(null);
  const [job, setJob] = useState<TrainingJob | null>(null);
  const [promoted, setPromoted] = useState<string | null>(null);

  const list = useEngineQuery((e) => e.listIncidents());
  const heroId = useMemo(() => {
    const ops = (list.data || []).filter((x) => x.role !== "negative_control" && x.aoi_id?.startsWith("AE"));
    return (ops.find((x) => x.status === "UNDER_REVIEW") || ops[0] || list.data?.[0])?.id || null;
  }, [list.data]);
  const hero = useEngineQuery((e) => (heroId ? e.getIncident(heroId) : Promise.resolve(null)), [heroId]).data as Incident | null | undefined;
  const aois = useEngineQuery((e) => e.aois()).data || [];
  const assets = useEngineQuery((e) => e.assets()).data || [];
  const labels = useEngineQuery((e) => e.labels("triage")).data || [];
  const models = useEngineQuery((e) => e.models("triage")).data || [];
  const vs = useStatic<VSum>("validation/validation_summary.json").data;

  const step = STEPS[i];
  const next = useCallback(() => setI((p) => Math.min(STEPS.length - 1, p + 1)), []);
  const prev = useCallback(() => setI((p) => Math.max(0, p - 1)), []);

  // autoplay: timed steps advance; action steps wait until their action is done
  const actionDone = step.stage === "review" ? !!reviewOut : step.stage === "retrain" ? !!job : step.stage === "gate" ? !!promoted || (job?.status === "FAILED") : true;
  useEffect(() => {
    if (!playing || i >= STEPS.length - 1) return;
    if (step.action && !actionDone) return;
    const t = setTimeout(next, (step.action ? 4 : step.secs) * 1000);
    return () => clearTimeout(t);
  }, [playing, i, step, actionDone, next]);
  useEffect(() => {
    const h = (ev: KeyboardEvent) => {
      if ((ev.target as HTMLElement)?.tagName === "INPUT") return;
      if (ev.key === "ArrowRight") next();
      if (ev.key === "ArrowLeft") prev();
      if (ev.key === " ") { ev.preventDefault(); setPlaying((p) => !p); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [next, prev]);

  const production = models.find((m) => m.status === "PRODUCTION") || null;
  const candidate = job?.candidate_model_id ? models.find((m) => m.id === job.candidate_model_id) || null : null;
  const newLabel = reviewOut?.label ? labels.find((l) => l.id === reviewOut.label) || null : null;

  async function doReview(decision: "CONFIRM" | "FALSE_POSITIVE" | "NEEDS_FIELD_SAMPLE") {
    if (!hero) return;
    setBusy(true);
    try {
      const r = await mutate((e) => e.review(hero.id, { reviewer: getOperator(), decision, note: "Judge Mode review", evidence_viewed: ["spectrum", "features", "OLCI cross-check", "timeline"] }));
      setReviewOut({ before: r.status_before, after: r.status_after, label: r.label_id, decision });
    } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  async function doRetrain() {
    setBusy(true);
    try { setJob(await mutate((e) => e.retrain("triage", getOperator()))); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }
  async function doPromote() {
    if (!candidate) return;
    setBusy(true);
    try { await mutate((e) => e.promote(candidate.id, getOperator(), "Promoted in Judge Mode after reviewing the gate")); setPromoted(candidate.id); }
    catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  }

  const f = hero?.water_quality?.features || {};
  const olci = hero?.sensor_agreement?.["Sentinel-3 OLCI"] as (Record<string, unknown> & { agrees?: boolean | null; note?: string }) | undefined;
  const hue = f.HUE_ANGLE as unknown as { value?: number; baseline_median?: number } | undefined;
  const nDt = vs?.A_data_quality.aois.reduce((s, a) => s + a.n_ok, 0);
  const uaeAois = aois.filter((a) => a.id.startsWith("AE"));
  const fpA = vs?.D_813_ablation.hard?.arms?.S2_multispectral_11band?.confusion_matrix?.fp, fpB = vs?.D_813_ablation.hard?.arms?.["813_hyperspectral_205band"]?.confusion_matrix?.fp;
  const apRule = vs?.C_model_performance?.production?.metrics?.auprc, apCand = vs?.C_model_performance?.candidate?.metrics?.auprc, apCi = vs?.C_model_performance?.bootstrap?.auprc?.ci;
  const showMap = ["coast", "sensors", "change"].includes(step.stage);

  return (
    <div className="relative grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-2 p-3 short:p-2">
      {/* progress */}
      <div className="flex items-center gap-2">
        <span className="hud-kicker mr-1">JUDGE MODE</span>
        <div className="flex flex-1 gap-1">
          {STEPS.map((s, k) => (
            <button key={k} onClick={() => setI(k)} aria-label={`Step ${k + 1}`} className="group h-2 flex-1 overflow-hidden rounded-full bg-edge">
              <motion.span className="block h-full rounded-full" style={{ background: k < i ? "#23D484" : k === i ? "#2F7BFF" : "transparent" }}
                initial={false} animate={{ width: k <= i ? "100%" : "0%" }} transition={{ duration: reduce ? 0 : 0.4 }} />
            </button>))}
        </div>
        <span className="hud-value w-[46px] text-right text-[12px] text-muted">{i + 1}/{STEPS.length}</span>
      </div>

      {/* stage */}
      <div className="grid min-h-0 gap-3 lg:grid-cols-[minmax(0,1.35fr)_minmax(340px,1fr)]">
        <div className="panel relative min-h-0 overflow-hidden">
          {showMap && (
            <IncidentMap incident={step.stage === "change" ? hero || null : null} incidents={step.stage === "change" && hero ? [{ id: hero.id, status: hero.status, aoi_id: hero.aoi_id, centroid: hero.centroid, title: hero.title, event_type_hypothesis: hero.event_type_hypothesis, priority: hero.priority, observation_time: hero.observation_time } as never] : []}
              aois={aois} assets={step.stage === "change" ? assets : []} compact showTimeline={false} initialMode="3d" />)}
          {step.stage === "why" && (
            <div className="grid h-full content-center gap-4 scroll-quiet overflow-y-auto p-6 short:gap-3 short:p-4">
              <div className="hud-kicker">Why this matters</div>
              <div className="grid gap-3 md:grid-cols-2">
                {WHY_FACTS.map((x, k) => (
                  <motion.div key={x.k} initial={{ opacity: 0, y: reduce ? 0 : 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reduce ? 0 : 0.25 + k * 0.35 }}
                    className="rounded-lg border border-edge bg-deep/70 p-4">
                    <div className="hud-kicker">{x.k}</div>
                    <div className="hud-value mt-1 text-[30px] font-bold leading-none text-caution short:text-[24px]">{x.v}</div>
                    <p className="mt-2 text-[13px] leading-snug text-ink">{x.sub}</p>
                    <a href={x.url} target="_blank" rel="noopener noreferrer" className="mt-2 block text-[11px] text-dim hover:text-cyan">Source: {x.src} ↗</a>
                  </motion.div>))}
              </div>
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: reduce ? 0 : 1.1 }} className="rounded-lg border border-critical/40 bg-critical/5 p-4">
                <div className="hud-kicker text-critical">The gap today</div>
                <p className="mt-1 text-[13.5px] leading-snug text-ink">The warning comes from the intake filters, a boat sample on a fixed calendar, or the public. Satellite images of this water are free every few days, but nobody turns them into a decision: <b>is this unusual for this spot, and where should the boat go?</b></p>
              </motion.div>
            </div>)}
          {step.stage === "impact" && (
            <div className="grid h-full content-center gap-3 scroll-quiet overflow-y-auto p-5 short:p-4">
              <div className="hud-kicker">Who uses it · what it changes</div>
              <div className="grid gap-2 md:grid-cols-3">
                {[["Desalination & power plants", "Early warning for the water in front of the intake: distance, drift scenario, and a sampling plan."],
                  ["Environment regulators", "Send the boat where it resolves something. Every decision goes into a tamper-evident log and can be exported."],
                  ["Ports, fish farms, beaches", "An alert when unusual water appears near their site, with the evidence attached."]].map(([t, d], k) => (
                  <motion.div key={t} initial={{ opacity: 0, y: reduce ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reduce ? 0 : k * 0.2 }} className="rounded-lg border border-edge bg-deep/70 p-3">
                    <div className="font-display text-[14px] font-bold">{t}</div><p className="mt-1 text-[12px] leading-snug text-muted">{d}</p>
                  </motion.div>))}
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                <Fact k="Images screened" v={nDt?.toLocaleString() ?? "…"} sub={`${uaeAois.length} UAE areas, 2017–2026, open data`} />
                <Fact k="Learned model vs rule" v={apRule != null && apCand != null ? `${fmt.num(apRule, 2)} → ${fmt.num(apCand, 2)}` : "…"} sub={apCi ? `AUPRC on 100 held-back labels · gain CI [${fmt.num(apCi[0], 2)}, ${fmt.num(apCi[1], 2)}]` : "AUPRC on held-back labels"} tone="text-nominal" />
                <Fact k="813 on borderline cases" v={fpA != null && fpB != null ? `${fpA} → ${fpB}` : "…"} sub={<span>false alarms at the same catch rate <SimBadge text="SIMULATED" /></span>} tone="text-caution" />
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
                <span className="hud-kicker mr-1">How it is offered</span>
                {["Per-area monitoring", "Per-asset alerts", "Per-event 813 hyperspectral analysis", "Reports and API"].map((t) => <span key={t} className="rounded-full border border-line bg-panel2 px-2.5 py-1 text-ink">{t}</span>)}
                <span className="ml-auto rounded-full border border-cyan/50 px-2.5 py-1 text-cyan" title="UN Sustainable Development Goals 6 (clean water) and 14 (life below water)">SDG 6 · SDG 14</span>
              </div>
            </div>)}
          {step.stage === "features" && hero && (
            <div className="grid h-full grid-rows-[auto_minmax(0,1fr)] gap-2 p-4">
              <div className="flex flex-wrap items-center gap-2"><Chip label={hero.status} /><span className="font-display text-[18px] font-bold">{hero.title}</span><span className="text-[12px] text-muted">{hero.aoi_name} · {fmt.utc(hero.observation_time)}</span></div>
              <div className="grid content-start gap-2 sm:grid-cols-2 xl:grid-cols-3">
                <Fact k="Chlorophyll index · vs past years" v={fmt.num(f.NDCI?.z as number, 1)} sub={<span title="NDCI robust z-score against this spot's same-season history in other years">{`${fmt.ord(f.NDCI?.seasonal_percentile as number)} percentile for this season · NDCI · PROXY`}</span>} tone="text-caution" />
                <Fact k="Chlorophyll peak (MCI)" v={fmt.num(f.MCI?.value as number, 4)} sub={<span title="MCI measures the red-edge peak. The score is a robust z-score against past years.">{`score ${fmt.num(f.MCI?.z as number, 1)} vs past years · usually ${fmt.num(f.MCI?.baseline_median as number, 4)} · PROXY`}</span>} />
                <Fact k="Water colour (hue angle)" v={`${fmt.num(hue?.value, 0)}°`} sub={`usually ${fmt.num(hue?.baseline_median, 0)}° here · visibly discoloured`} tone="text-caution" />
                <Fact k="Sentinel-3 check, same morning" v={olci?.agrees ? "agrees" : olci?.agrees === false ? "disagrees" : "no data"} sub={olci?.note} tone={olci?.agrees ? "text-nominal" : "text-muted"} />
                <Fact k="Area · distance to shore" v={`${fmt.num(hero.area_km2, 2)} km²`} sub={`${fmt.num(hero.model_features?.dist_shore_km as number, 1)} km offshore`} />
                <Fact k="Seen here before?" v={fmt.pct(hero.temporal?.persistence_frac)} sub="share of past same-season dates with a similar signal. Low means new." tone="text-nominal" />
              </div>
            </div>)}
          {step.stage === "cube" && hero?.cube && (
            <div className="grid h-full min-h-0 grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
              <CubeViewer name={hero.cube} height="100%" sweep compact />
              <div className="flex min-h-0 flex-col gap-2 p-3">
                <div className="hud-kicker">Event vs normal water · real Sentinel-2</div>
                <div className="min-h-0 flex-1">{hero.spectral && <SpectrumPlot spec={hero.spectral} fill range={[430, 900]} showDiff highlight={705} />}</div>
                <div className="rounded-md border border-edge bg-deep/70 p-2 text-[11.5px] text-muted" title="Sentinel-2 covers the red edge with one 15 nm band. False alarms counted at the decision boundary, with spatially blocked cross-validation."><SimBadge /> <span className="ml-1">Sentinel-2 sees this colour region with a single band. On the same real pixels, simulated 813 bands cut false alarms on borderline cases from <b className="text-ink">{fpA ?? "?"}</b> to <b className="text-ink">{fpB ?? "?"}</b>. Overall detection did not improve.</span></div>
              </div>
            </div>)}
          {step.stage === "quantify" && hero && (
            <div className="grid h-full content-center gap-3 p-6">
              <div className="hud-kicker">Concentration estimate · real results only</div>
              <div className="font-display text-[30px] font-bold text-critical">No concentration is shown.</div>
              <p className="max-w-[640px] text-[14px] text-muted">There are no public UAE water samples for chlorophyll, turbidity or sediment. So nothing is calibrated locally. BlueBan shows these values as <b className="text-ink">proxies</b> and will not print a concentration.</p>
              <div className="grid max-w-[720px] gap-2 sm:grid-cols-3">
                <Fact k="Matched water samples" v="0" sub="needs at least 20, across 5+ groups" tone="text-critical" />
                <Fact k="Turbidity (generic formula)" v={`${fmt.num(f.TUR_NECHAD2016?.value as number, 1)} FNU`} sub={<span title="Nechad (2016) turbidity formula with generic coefficients">GENERIC CALIBRATION · not checked against UAE samples</span>} />
                <Fact k="Sample matching" v="ready" sub={<span title="±24 h window, 3×3 pixel box, CV ≤ 0.15. Grouped cross-validation with confidence intervals.">pairs each sample with an image taken within 24 h</span>} tone="text-nominal" />
              </div>
              <p className="text-[12px] text-dim">The first sample entered in Field Ops starts the matching. Twenty good samples in five separate groups unlock a calibrated estimate, with its uncertainty.</p>
            </div>)}
          {step.stage === "review" && hero && (
            <div className="grid h-full content-center gap-4 p-6">
              <div className="flex items-center gap-2"><UserCheck className="text-beam2" /><span className="font-display text-[22px] font-bold">Analyst review · {hero.id}</span><Chip label={reviewOut ? reviewOut.after : hero.status} /></div>
              <p className="max-w-[640px] text-[13.5px] text-muted">The model only ranks incidents. A named analyst decides after seeing the spectrum, the measurements, the Sentinel-3 check and the timeline. The decision goes into the audit log.</p>
              {!reviewOut ? (
                <div className="flex flex-wrap gap-3">
                  <button disabled={busy} onClick={() => doReview("CONFIRM")} className="btn btn-primary px-5 py-3 text-[14px]"><CheckCircle2 size={18} /> CONFIRM</button>
                  <button disabled={busy} onClick={() => doReview("FALSE_POSITIVE")} className="btn px-5 py-3 text-[14px]" style={{ borderColor: "#8B7BFF" }}><CircleX size={18} /> FALSE ALARM</button>
                  <button disabled={busy} onClick={() => doReview("NEEDS_FIELD_SAMPLE")} className="btn px-5 py-3 text-[14px]"><FlaskConical size={18} /> REQUEST WATER SAMPLE</button>
                </div>) : (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-md border border-nominal/50 bg-nominal/10 p-3 text-[13px]">
                  <b>{DECISION_TEXT[reviewOut.decision] || reviewOut.decision.replace(/_/g, " ")}</b> by {getOperator()}: {(STATE_TEXT[reviewOut.before] ?? reviewOut.before.replace(/_/g, " ")).toLowerCase()} → <b style={{ color: STATE_COLOR[reviewOut.after] }}>{(STATE_TEXT[reviewOut.after] ?? reviewOut.after.replace(/_/g, " ")).toLowerCase()}</b>.
                  {reviewOut.label ? <> Verified label <span className="hud-value">{reviewOut.label}</span> created.</> : <> No label yet. This decision leaves the question open, so the model learns nothing from it.</>}
                </motion.div>)}
              <p className="text-[11.5px] text-dim">“Confirm” means the unusual colour is real and worth acting on. It does not claim a harmful bloom or a species. Only a water sample can show that.</p>
            </div>)}
          {step.stage === "label" && (
            <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-2 p-4">
              <div className="flex items-center gap-3"><Sparkles className="text-caution" /><span className="font-display text-[20px] font-bold">Verified labels · triage model</span>
                <span className="text-[12px] text-muted">{labels.length} active labels · {labels.filter((l) => l.split === "validation").length} held back for testing</span></div>
              <div className="min-h-0 scroll-quiet overflow-y-auto rounded-md border border-edge">
                <table className="w-full text-[11.5px]">
                  <thead className="sticky top-0 bg-panel"><tr className="border-b border-edge text-dim"><th className="px-2 py-1 text-left">Label</th><th className="px-2 text-left">Source</th><th className="px-2 text-right" title="1 = real event, 0 = not an event">Outcome</th><th className="px-2 text-right">Weight</th><th className="px-2 text-left">Used for</th></tr></thead>
                  <tbody>
                    {[...(newLabel ? [newLabel] : []), ...labels.filter((l) => l.id !== newLabel?.id).slice(0, 14)].map((l: LabelRow) => (
                      <motion.tr key={l.id} initial={l.id === newLabel?.id ? { backgroundColor: "rgba(35,212,132,0.35)" } : false} animate={{ backgroundColor: l.id === newLabel?.id ? "rgba(35,212,132,0.12)" : "rgba(0,0,0,0)" }} transition={{ duration: 1.6 }} className="border-b border-edge/50">
                        <td className="hud-value px-2 py-1">{l.id}{l.id === newLabel?.id && <span className="ml-2 text-nominal">NEW</span>}</td><td className="px-2">{l.source.replace(/_/g, " ")}</td><td className="hud-value px-2 text-right">{String(l.target.y)}</td><td className="hud-value px-2 text-right">{l.weight}</td><td className="px-2">{l.split}</td>
                      </motion.tr>))}
                  </tbody>
                </table>
              </div>
            </div>)}
          {(step.stage === "retrain" || step.stage === "gate") && (
            <div className="grid h-full min-h-0 grid-cols-2 gap-3 p-4">
              {[{ m: promoted ? models.find((x) => x.id === promoted) : production, role: "PRODUCTION" }, { m: promoted ? null : candidate, role: "CANDIDATE" }].map(({ m, role }) => (
                <motion.div key={role} layout className={`panel-flat flex min-h-0 flex-col p-3 ${role === "PRODUCTION" ? "border-nominal/50" : "border-caution/50"}`}>
                  <div className="flex items-center gap-2"><BrainCircuit size={18} className={role === "PRODUCTION" ? "text-nominal" : "text-caution"} /><span className="hud-kicker">{role === "PRODUCTION" ? "LIVE MODEL" : "NEW MODEL"}</span></div>
                  {m ? (
                    <motion.div layoutId={`jm-${m.id}`} className="mt-1">
                      <div className="font-display text-[20px] font-bold">{m.id}</div>
                      <div className="text-[11.5px] text-muted" title={m.model_type === "rules" ? "Rule baseline" : "L2 logistic regression"}>{m.model_type === "rules" ? "Rule-based baseline" : "Learned model, trained in this workspace"}</div>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        {[["auprc", "Detection score"], ["auroc", "Ranking (AUROC)"], ["f1", "F1 score"], ["ece", "Calibration error"]].map(([k, lab]) => <Fact key={k} k={lab} v={fmt.num(metricOf(m, k), 3)} />)}
                      </div>
                    </motion.div>
                  ) : role === "CANDIDATE" ? (
                    <div className="grid flex-1 place-items-center text-center text-[12.5px] text-muted">
                      {promoted ? "Now live. The old model is retired, not deleted. One click brings it back." : job?.status === "FAILED" ? <span className="text-critical">Training refused: {job.error}</span> : "No new model yet."}
                    </div>) : <div className="text-muted">No live model.</div>}
                </motion.div>))}
            </div>)}
          {step.stage === "loop" && (
            <div className="grid h-full place-items-center p-6">
              <div className="flex flex-wrap items-center justify-center gap-2">
                {[["SATELLITE", <Satellite key="s" size={22} />], ["MODEL", <BrainCircuit key="m" size={22} />], ["OPERATOR", <UserCheck key="o" size={22} />], ["FIELD TEAM", <FlaskConical key="f" size={22} />], ["VERIFIED DATA", <ShieldCheck key="v" size={22} />], ["BETTER MODEL", <Sparkles key="b" size={22} />]].map(([t, ic], k) => (
                  <React.Fragment key={String(t)}>
                    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reduce ? 0 : k * 0.35 }} className="panel-flat flex w-[132px] flex-col items-center gap-2 px-3 py-4 text-center">
                      <span className="text-beam2">{ic}</span><span className="font-display text-[13px] font-bold tracking-wider">{t}</span>
                    </motion.div>
                    {k < 5 && <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: reduce ? 0 : k * 0.35 + 0.2 }}><ArrowRight className="text-cyan" /></motion.span>}
                  </React.Fragment>))}
              </div>
              <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: reduce ? 0 : 2.4 }} className="mt-8 max-w-[860px] text-center font-display text-[26px] font-bold leading-snug">{CLOSING}</motion.p>
            </div>)}
        </div>

        {/* narration + evidence rail */}
        <div className="panel flex min-h-0 flex-col p-4">
          <AnimatePresence mode="wait">
            <motion.div key={i} initial={{ opacity: 0, y: reduce ? 0 : 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reduce ? 0 : 0.35 }} className="flex min-h-0 flex-1 flex-col">
              <div className="hud-kicker">Step {i + 1}</div>
              <p className="mt-1 font-display text-[24px] font-bold leading-snug short:text-[20px]">“{step.say}”</p>
              <div className="mt-3 min-h-0 flex-1 space-y-2 scroll-quiet overflow-y-auto text-[12.5px] text-muted">
                {step.stage === "why" && <><p>BlueBan 813 watches the water in front of the UAE&apos;s intakes, beaches and ports from orbit. It flags water that is unusual <b className="text-ink">for that exact spot and season</b>, sends it to a person, then a boat, then a lab, and learns from every answer.</p>
                  <p>Theme: Water Quality &amp; Inland/Coastal Water Intelligence. Built on open Sentinel-2/3 data, with Satellite 813 simulated from real hyperspectral pixels.</p></>}
                {step.stage === "impact" && <><p>For an operator the question is per intake, not per incident: <Link href="/intakes" className="text-cyan hover:underline">Intake watch →</Link> shows each desalination and power-plant intake, the nearest unusual water, and the alert they would receive.</p>
                  <p>The first pilot we ask for: <b className="text-ink">one coast, one operator, one season</b>. Their sampling calendar stays; we compare our flags with their lab results and measure whether the boat went to better places.</p>
                  <p>No revenue is claimed and no concentration is printed without local water samples. <Link href="/validation" className="text-cyan hover:underline">See the evidence →</Link></p></>}
                {step.stage === "coast" && <><p>{uaeAois.length} monitored areas on both UAE coasts. The Arabian Gulf is shallow, so the bright seabed shows through. The Gulf of Oman is deep and prone to algae blooms. A known false alarm from Annaba, Algeria, is kept as a test.</p><Link href="/watch" className="text-cyan hover:underline">Open WATCH →</Link></>}
                {step.stage === "sensors" && <div className="grid grid-cols-2 gap-2">
                  <Fact k="Sentinel-2 images checked" v={nDt?.toLocaleString() ?? "…"} sub="2017–2026 · clouds and bad pixels masked" />
                  <Fact k="Revisit" v="2–5 days" sub="10/20/60 m pixels · Sentinel-2A/B/C" />
                  <Fact k="Sentinel-3 checks" v={vs?.B_matchups.cross_sensor.n ?? "…"} sub={`same morning, typically ${fmt.num(vs?.B_matchups.cross_sensor.median_abs_dt_minutes ?? null, 0)} min apart`} />
                  <Fact k="Role of Sentinel-3" v="second check" sub="context and a cross-check, not ground truth" />
                </div>}
                {step.stage === "change" && hero && <div className="rounded-md border border-critical/40 bg-critical/5 p-3 text-[13px] text-ink">
                  Unusual water near {hero.aoi_name}. {fmt.ord(hero.temporal?.seasonal_percentile)} percentile for this time of year. Sentinel-3 check: {olci?.agrees ? "agrees" : "available"}. An analyst must review it.
                </div>}
                {step.stage === "features" && <p>Each number is compared with the same spot at the same time of year in past years. A sandbank that is always there scores low. A new event scores high. Sentinel-3, on the same morning, either agrees or not.</p>}
                {step.stage === "cube" && <><p>The colour sweep shows where the event differs from normal water: near 705 nm. Satellite 813 covers that region in narrow bands. We had no access to 813 data, so every 813 value here is <b className="text-ink">simulated</b> from real Tanager pixels.</p>
                  <p>Inland, the same 813 band set is simulated on real EnMAP hyperspectral images of Shawka Dam. <Link href="/inland" className="text-cyan hover:underline">Open Inland →</Link></p></>}
                {step.stage === "quantify" && <p>This is the honest state of UAE data, not a software limit. The Validation page shows the sample-matching rules and the calibration result.</p>}
                {step.stage === "review" && <p>Each decision is saved with the reviewer’s name, the evidence they saw and the model version that raised the alert.</p>}
                {step.stage === "label" && <p>Analyst labels count 1.0, field results 2.0 and Sentinel-3 checks 0.5. Labels from the same area and month stay together, in training or in the held-back test set. So the model is never tested on near-copies of what it learned from.</p>}
                {step.stage === "retrain" && (!job ? <button disabled={busy} onClick={doRetrain} className="btn btn-primary"><RotateCcw size={15} /> Train new model</button>
                  : <div className="space-y-1">{job.log.map((l, k) => <div key={k} className="hud-value text-[11px]"><span className="text-dim">{l.at.slice(11, 19)}</span> {l.msg}</div>)}</div>)}
                {step.stage === "gate" && (candidate?.gate ? <>
                  <ul className="space-y-1">{candidate.gate.checks.map((c: GateCheck) => <li key={c.name} className="flex items-center gap-2">{c.passed ? <CheckCircle2 size={14} className="text-nominal" /> : <CircleX size={14} className="text-critical" />}<span className={c.passed ? "text-ink" : "text-critical"}>{GATE_LABEL[c.name] || c.name.replace(/_/g, " ")}</span></li>)}
                    <li className="flex items-center gap-2"><UserCheck size={14} className={promoted ? "text-nominal" : "text-caution"} /><span>Human approval {promoted ? `· ${getOperator()}` : "· required"}</span></li></ul>
                  {!promoted && (candidate.gate.passed
                    ? <button disabled={busy} onClick={doPromote} className="btn btn-primary mt-2"><ShieldCheck size={15} /> Make new model live</button>
                    : <p className="mt-2 text-critical">The safety check failed. {production?.id} stays live. The new model is kept on record.</p>)}
                </> : <p>{job?.status === "FAILED" ? `No new model: ${job.error}` : "Train a new model first (step 9)."}</p>)}
                {step.stage === "loop" && <p>Satellite → model → operator → field team → verified data → better model. Each arrow is a screen in the app and an entry in its audit log.</p>}
              </div>
            </motion.div>
          </AnimatePresence>
          <div className="mt-3 flex items-center gap-2 border-t border-edge pt-3">
            <button onClick={prev} className="btn px-2 py-1.5" aria-label="Previous"><ChevronLeft size={16} /></button>
            <button onClick={() => setPlaying((p) => !p)} className="btn px-3 py-1.5">{playing ? <><Pause size={15} /> Pause</> : <><Play size={15} /> Play</>}</button>
            <button onClick={next} className="btn px-2 py-1.5" aria-label="Next"><ChevronRight size={16} /></button>
            {step.action && !actionDone && playing && <span className="text-[11px] text-caution">Waiting for you</span>}
            <span className="ml-auto text-[11px] text-dim">← → · space</span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] text-dim">
        <span><Waves size={12} className="mr-1 inline" />Live data from your workspace · actions go into the audit log · reset in Settings</span>
        <Link href="/" className="text-cyan hover:underline">Exit to Incident Control</Link>
      </div>
    </div>
  );
}

export default function Page() { return <Suspense><Judge /></Suspense>; }
