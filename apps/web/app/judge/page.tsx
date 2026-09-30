"use client";
/**
 * JUDGE MODE - the closed loop in eleven steps, two to three minutes.
 *
 * Every number on screen is read live from this visitor's workspace (the same
 * engine the operational screens use) or from the pipeline outputs; nothing is
 * scripted into the page. Steps 7, 9 and 10 are real actions - a review, a
 * training job and a gated promotion - so autoplay waits for the presenter
 * there. The workspace can be reset from Settings.
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
import { Chip, fmt, SimBadge, STATE_COLOR, toast } from "@/components/ui";

const IncidentMap = dynamic(() => import("@/components/map/IncidentMap"), { ssr: false });
const CubeViewer = dynamic(() => import("@/components/spectra/CubeViewer"), { ssr: false });

type Stage = "coast" | "sensors" | "change" | "features" | "cube" | "quantify" | "review" | "label" | "retrain" | "gate" | "loop";
const STEPS: { stage: Stage; say: string; secs: number; action?: boolean }[] = [
  { stage: "coast", say: "This is the UAE coastline BlueBan is monitoring.", secs: 11 },
  { stage: "sensors", say: "Sentinel-2 and Sentinel-3 provide continuous Earth-observation context.", secs: 12 },
  { stage: "change", say: "Something changed.", secs: 10 },
  { stage: "features", say: "BlueBan doesn't stop at an index.", secs: 15 },
  { stage: "cube", say: "813 gives us a detailed spectral fingerprint.", secs: 15 },
  { stage: "quantify", say: "If we have field reference measurements, BlueBan converts optical features into an estimated physical parameter and reports uncertainty.", secs: 14 },
  { stage: "review", say: "But a model should not make the final decision alone.", secs: 12, action: true },
  { stage: "label", say: "That decision becomes a verified label.", secs: 10 },
  { stage: "retrain", say: "When enough verified evidence exists, we retrain a candidate.", secs: 12, action: true },
  { stage: "gate", say: "The previous production model remains untouched until the candidate passes the validation gate.", secs: 14, action: true },
  { stage: "loop", say: "BlueBan does not just detect coastal incidents. It creates a closed learning loop between satellites, analysts and field teams.", secs: 16 },
];
const CLOSING = "BlueBan turns every coastal incident into both a response and a lesson.";

type VSum = { A_data_quality: { aois: { aoi_id: string; n_ok: number; n_usable: number; date_range: [string, string] }[] }; B_matchups: { cross_sensor: { n: number; median_abs_dt_minutes?: number | null } }; D_813_ablation: { hard?: { arms: Record<string, { confusion_matrix?: { fp: number } }> } } };

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
          {step.stage === "features" && hero && (
            <div className="grid h-full grid-rows-[auto_minmax(0,1fr)] gap-2 p-4">
              <div className="flex flex-wrap items-center gap-2"><Chip label={hero.status} /><span className="font-display text-[18px] font-bold">{hero.title}</span><span className="text-[12px] text-muted">{hero.aoi_name} · {fmt.utc(hero.observation_time)}</span></div>
              <div className="grid content-start gap-2 sm:grid-cols-2 xl:grid-cols-3">
                <Fact k="NDCI · robust z vs own season" v={fmt.num(f.NDCI?.z as number, 1)} sub={`${fmt.ord(f.NDCI?.seasonal_percentile as number)} seasonal percentile · PROXY`} tone="text-caution" />
                <Fact k="MCI · red-edge peak" v={fmt.num(f.MCI?.value as number, 4)} sub={`z ${fmt.num(f.MCI?.z as number, 1)} · baseline ${fmt.num(f.MCI?.baseline_median as number, 4)} · PROXY`} />
                <Fact k="Water colour (hue angle)" v={`${fmt.num(hue?.value, 0)}°`} sub={`usually ${fmt.num(hue?.baseline_median, 0)}° here: visible discolouration`} tone="text-caution" />
                <Fact k="Sentinel-3 OLCI, same morning" v={olci?.agrees ? "agrees" : olci?.agrees === false ? "disagrees" : "n/a"} sub={olci?.note} tone={olci?.agrees ? "text-nominal" : "text-muted"} />
                <Fact k="Area · distance to shore" v={`${fmt.num(hero.area_km2, 2)} km²`} sub={`${fmt.num(hero.model_features?.dist_shore_km as number, 1)} km offshore`} />
                <Fact k="Seen here before?" v={fmt.pct(hero.temporal?.persistence_frac)} sub="share of past same-season dates with a similar signal: new, not a fixture" tone="text-nominal" />
              </div>
            </div>)}
          {step.stage === "cube" && hero?.cube && (
            <div className="grid h-full min-h-0 grid-cols-[1.25fr_1fr]">
              <CubeViewer name={hero.cube} height="100%" sweep compact />
              <div className="flex min-h-0 flex-col gap-2 p-3">
                <div className="hud-kicker">Event vs background water · real Sentinel-2</div>
                <div className="min-h-0 flex-1">{hero.spectral && <SpectrumPlot spec={hero.spectral} fill range={[430, 900]} showDiff highlight={705} />}</div>
                <div className="rounded-md border border-edge bg-deep/70 p-2 text-[11.5px] text-muted"><SimBadge /> <span className="ml-1">Sentinel-2 resolves the red-edge with one 15 nm band. On the same real pixels, the simulated 813 band set cut false alarms at the decision boundary from <b className="text-ink">{fpA ?? "?"}</b> to <b className="text-ink">{fpB ?? "?"}</b> (spatially blocked CV). Gross detection gained nothing.</span></div>
              </div>
            </div>)}
          {step.stage === "quantify" && hero && (
            <div className="grid h-full content-center gap-3 p-6">
              <div className="hud-kicker">Physical estimate · real result only</div>
              <div className="font-display text-[30px] font-bold text-critical">No mg m⁻³ is shown.</div>
              <p className="max-w-[640px] text-[14px] text-muted">There are no public UAE water samples for chlorophyll, turbidity or TSS, so no local calibration exists. BlueBan reports these values as <b className="text-ink">proxies</b> and refuses to print a concentration.</p>
              <div className="grid max-w-[720px] gap-2 sm:grid-cols-3">
                <Fact k="In-situ matchups" v="0" sub="needs ≥ 20 in ≥ 5 groups" tone="text-critical" />
                <Fact k="Turbidity (generic Nechad)" v={`${fmt.num(f.TUR_NECHAD2016?.value as number, 1)} FNU`} sub="GENERIC_CALIBRATION · not locally validated" />
                <Fact k="Matchup engine" v="ready" sub="±24 h, 3×3 box, CV ≤ 0.15; grouped CV + CIs" tone="text-nominal" />
              </div>
              <p className="text-[12px] text-dim">The first field sample entered in Field Ops starts the matchup table. Twenty good ones in five independent groups unlock a calibrated estimate with its uncertainty.</p>
            </div>)}
          {step.stage === "review" && hero && (
            <div className="grid h-full content-center gap-4 p-6">
              <div className="flex items-center gap-2"><UserCheck className="text-beam" /><span className="font-display text-[22px] font-bold">Analyst review · {hero.id}</span><Chip label={reviewOut ? reviewOut.after : hero.status} /></div>
              <p className="max-w-[640px] text-[13.5px] text-muted">The triage model only ranks. A named analyst decides, having seen the spectrum, the features, the OLCI cross-check and the timeline. The decision is written to the audit log.</p>
              {!reviewOut ? (
                <div className="flex flex-wrap gap-3">
                  <button disabled={busy} onClick={() => doReview("CONFIRM")} className="btn btn-primary px-5 py-3 text-[14px]"><CheckCircle2 size={18} /> CONFIRM</button>
                  <button disabled={busy} onClick={() => doReview("FALSE_POSITIVE")} className="btn px-5 py-3 text-[14px]" style={{ borderColor: "#8B7BFF" }}><CircleX size={18} /> FALSE POSITIVE</button>
                  <button disabled={busy} onClick={() => doReview("NEEDS_FIELD_SAMPLE")} className="btn px-5 py-3 text-[14px]"><FlaskConical size={18} /> NEEDS FIELD SAMPLE</button>
                </div>) : (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-md border border-nominal/50 bg-nominal/10 p-3 text-[13px]">
                  <b>{reviewOut.decision.replace(/_/g, " ")}</b> by {getOperator()}: {reviewOut.before.replace(/_/g, " ")} → <b style={{ color: STATE_COLOR[reviewOut.after] }}>{reviewOut.after.replace(/_/g, " ")}</b>.
                  {reviewOut.label ? <> Verified label <span className="hud-value">{reviewOut.label}</span> created.</> : <> No label: this decision does not settle the question, so nothing is taught.</>}
                </motion.div>)}
              <p className="text-[11.5px] text-dim">“Confirm” means the optical anomaly is real and worth acting on. It is not a claim of a harmful bloom or a species; that needs a water sample.</p>
            </div>)}
          {step.stage === "label" && (
            <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-2 p-4">
              <div className="flex items-center gap-3"><Sparkles className="text-caution" /><span className="font-display text-[20px] font-bold">Label store · triage</span>
                <span className="text-[12px] text-muted">{labels.length} active labels · {labels.filter((l) => l.split === "validation").length} frozen for validation</span></div>
              <div className="min-h-0 overflow-y-auto rounded-md border border-edge">
                <table className="w-full text-[11.5px]">
                  <thead className="sticky top-0 bg-panel"><tr className="border-b border-edge text-dim"><th className="px-2 py-1 text-left">Label</th><th className="px-2 text-left">Source</th><th className="px-2 text-right">y</th><th className="px-2 text-right">Weight</th><th className="px-2 text-left">Split</th></tr></thead>
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
                  <div className="flex items-center gap-2"><BrainCircuit size={18} className={role === "PRODUCTION" ? "text-nominal" : "text-caution"} /><span className="hud-kicker">{role}</span></div>
                  {m ? (
                    <motion.div layoutId={`jm-${m.id}`} className="mt-1">
                      <div className="font-display text-[20px] font-bold">{m.id}</div>
                      <div className="text-[11.5px] text-muted">{m.model_type === "rules" ? "Rule baseline" : "L2 logistic, trained in this workspace"}</div>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        {[["auprc", "AUPRC"], ["auroc", "AUROC"], ["f1", "F1"], ["ece", "ECE"]].map(([k, lab]) => <Fact key={k} k={lab} v={fmt.num(metricOf(m, k), 3)} />)}
                      </div>
                    </motion.div>
                  ) : role === "CANDIDATE" ? (
                    <div className="grid flex-1 place-items-center text-center text-[12.5px] text-muted">
                      {promoted ? "Promoted. The old model is retired, not deleted, and one click rolls it back." : job?.status === "FAILED" ? <span className="text-critical">Training refused: {job.error}</span> : "No candidate yet."}
                    </div>) : <div className="text-muted">No production model.</div>}
                </motion.div>))}
            </div>)}
          {step.stage === "loop" && (
            <div className="grid h-full place-items-center p-6">
              <div className="flex flex-wrap items-center justify-center gap-2">
                {[["SATELLITE", <Satellite key="s" size={22} />], ["MODEL", <BrainCircuit key="m" size={22} />], ["OPERATOR", <UserCheck key="o" size={22} />], ["FIELD", <FlaskConical key="f" size={22} />], ["VERIFIED DATA", <ShieldCheck key="v" size={22} />], ["BETTER MODEL", <Sparkles key="b" size={22} />]].map(([t, ic], k) => (
                  <React.Fragment key={String(t)}>
                    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reduce ? 0 : k * 0.35 }} className="panel-flat flex w-[132px] flex-col items-center gap-2 px-3 py-4 text-center">
                      <span className="text-beam">{ic}</span><span className="font-display text-[13px] font-bold tracking-wider">{t}</span>
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
              <div className="mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto text-[12.5px] text-muted">
                {step.stage === "coast" && <><p>{uaeAois.length} areas of interest along both UAE coasts: the Arabian Gulf (optically shallow, bright seabed) and the Gulf of Oman (deep, bloom-prone). The Annaba scene in Algeria is kept as a negative control.</p><Link href="/watch" className="text-cyan hover:underline">Open WATCH →</Link></>}
                {step.stage === "sensors" && <div className="grid grid-cols-2 gap-2">
                  <Fact k="Sentinel-2 datatakes screened" v={nDt?.toLocaleString() ?? "…"} sub="L2A, 2017–2026, per-pixel quality masks" />
                  <Fact k="Revisit" v="2–5 days" sub="10/20/60 m · Sentinel-2A/B/C" />
                  <Fact k="OLCI cross-sensor refs" v={vs?.B_matchups.cross_sensor.n ?? "…"} sub={`same morning, median ${fmt.num(vs?.B_matchups.cross_sensor.median_abs_dt_minutes ?? null, 0)} min apart`} />
                  <Fact k="Role of Sentinel-3" v="reference" sub="context and cross-check, never ground truth" />
                </div>}
                {step.stage === "change" && hero && <div className="rounded-md border border-critical/40 bg-critical/5 p-3 text-[13px] text-ink">
                  New coastal anomaly detected near {hero.aoi_name}. {fmt.ord(hero.temporal?.seasonal_percentile)} seasonal percentile. Cross-sensor evidence {olci?.agrees ? "available and in agreement" : "available"}. Analyst review required.
                </div>}
                {step.stage === "features" && <p>Each number is measured against the same pixel’s own history at the same time of year in other years, so a bright sandbank or a dredged channel that is always there scores low and a new event scores high. An independent sensor on the same morning agrees or does not.</p>}
                {step.stage === "cube" && <p>Scrubbing the cube shows where the event separates from ordinary water: the red-edge near 705 nm. Satellite 813 samples that region in narrow bands. No 813 product was accessible to the team, so every 813 value here is <b className="text-ink">simulated</b> from real Tanager hyperspectral pixels and labelled as such.</p>}
                {step.stage === "quantify" && <p>This is the honest state of the UAE data, not a limitation of the software. The Validation page shows the matchup engine, its thresholds and the calibration verdict.</p>}
                {step.stage === "review" && <p>Every decision is kept with the reviewer’s name, the evidence they viewed and the model version that raised the incident.</p>}
                {step.stage === "label" && <p>Analyst labels weigh 1.0, field results 2.0, and cross-sensor references 0.5. Labels from the same AOI and month always land on the same side of the frozen split, so the model is never tested on near-copies of its training data.</p>}
                {step.stage === "retrain" && (!job ? <button disabled={busy} onClick={doRetrain} className="btn btn-primary"><RotateCcw size={15} /> Retrain candidate</button>
                  : <div className="space-y-1">{job.log.map((l, k) => <div key={k} className="hud-value text-[11px]"><span className="text-dim">{l.at.slice(11, 19)}</span> {l.msg}</div>)}</div>)}
                {step.stage === "gate" && (candidate?.gate ? <>
                  <ul className="space-y-1">{candidate.gate.checks.map((c: GateCheck) => <li key={c.name} className="flex items-center gap-2">{c.passed ? <CheckCircle2 size={14} className="text-nominal" /> : <CircleX size={14} className="text-critical" />}<span className={c.passed ? "text-ink" : "text-critical"}>{c.name.replace(/_/g, " ")}</span></li>)}
                    <li className="flex items-center gap-2"><UserCheck size={14} className={promoted ? "text-nominal" : "text-caution"} /><span>human approval {promoted ? `· ${getOperator()}` : "· required"}</span></li></ul>
                  {!promoted && (candidate.gate.passed
                    ? <button disabled={busy} onClick={doPromote} className="btn btn-primary mt-2"><ShieldCheck size={15} /> Promote candidate</button>
                    : <p className="mt-2 text-critical">The gate refused. Production stays on {production?.id}; the candidate is kept for the record.</p>)}
                </> : <p>{job?.status === "FAILED" ? `No candidate: ${job.error}` : "Retrain first (step 9)."}</p>)}
                {step.stage === "loop" && <p>Satellite → model → operator → field → verified data → better model. Every arrow is a screen in this product and a row in its audit log.</p>}
              </div>
            </motion.div>
          </AnimatePresence>
          <div className="mt-3 flex items-center gap-2 border-t border-edge pt-3">
            <button onClick={prev} className="btn px-2 py-1.5" aria-label="Previous"><ChevronLeft size={16} /></button>
            <button onClick={() => setPlaying((p) => !p)} className="btn px-3 py-1.5">{playing ? <><Pause size={15} /> Pause</> : <><Play size={15} /> Play</>}</button>
            <button onClick={next} className="btn px-2 py-1.5" aria-label="Next"><ChevronRight size={16} /></button>
            {step.action && !actionDone && playing && <span className="text-[11px] text-caution">waiting for you</span>}
            <span className="ml-auto text-[11px] text-dim">← → · space</span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] text-dim">
        <span><Waves size={12} className="mr-1 inline" />Live workspace data · actions are recorded in the audit log · reset in Settings</span>
        <Link href="/" className="text-cyan hover:underline">Exit to Incident Control</Link>
      </div>
    </div>
  );
}

export default function Page() { return <Suspense><Judge /></Suspense>; }
