"use client";
/**
 * LEARN - why BlueBan gets better, and why it cannot get worse by accident.
 *
 * MODEL PREDICTION -> OPERATOR REVIEW -> VERIFIED LABEL -> LABEL STORE ->
 * RETRAIN CANDIDATE -> EVALUATION -> MODEL GATE -> HUMAN PROMOTION.
 */
import React, { useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, BrainCircuit, CheckCircle2, CircleX, GitBranch, History, Play, ShieldCheck, Undo2 } from "lucide-react";
import { getOperator, mutate, useEngineQuery } from "@/lib/engine";
import type { GateCheck, LabelRow, ModelRecord } from "@/lib/engine/types";
import { Chip, fmt, Pager, Panel, toast, useFitPage } from "@/components/ui";

/** Plain names for the model's built-in tests (the engine keeps its identifiers). */
const MODEL_TEST_LABEL: Record<string, string> = {
  predictions_finite: "no broken outputs", probabilities_in_unit_interval: "scores between 0 and 1",
  concentrations_positive: "no negative values", deterministic: "same answer every time",
  artifact_roundtrip_identical: "saves and reloads exactly", missing_features_imputed_not_nan: "copes with missing data",
  feature_schema_declared: "inputs documented",
};

const METRICS: [string, string, boolean][] = [["auprc", "Detection score", true], ["auroc", "Ranking score", true], ["f1", "Overall (F1)", true], ["precision", "Correct alerts", true], ["recall", "Events caught", true], ["brier", "Probability error", false], ["ece", "Calibration error", false]];
const METRIC_HINT: Record<string, string> = {
  auprc: "AUPRC: area under the precision-recall curve. 0 to 1, higher is better.",
  auroc: "AUROC: area under the ROC curve. 0.5 is a coin flip, 1 is perfect.",
  f1: "F1: balance of correct alerts and events caught. Higher is better.",
  precision: "Precision: share of alerts that were positive cases. Higher is better.",
  recall: "Recall: share of positive cases that were caught. Higher is better.",
  brier: "Brier score: error in the predicted probabilities. Lower is better.",
  ece: "ECE: gap between stated confidence and real hit rate. Lower is better.",
};

function metric(m: ModelRecord | null | undefined, k: string): number | null {
  if (!m) return null;
  const row = m.metrics?.find((x) => x.metric === k && x.split === "validation" && x.subgroup === "all");
  if (row?.value != null) return row.value;
  const s = (m.gate?.summary?.candidate as Record<string, number> | undefined)?.[k];
  return s ?? null;
}

function ModelCard({ m, role, prodForDelta }: { m: ModelRecord | null | undefined; role: "production" | "candidate"; prodForDelta?: ModelRecord | null }) {
  if (!m) return (
    <div className="panel-flat grid h-full min-h-[260px] place-items-center p-6 text-center text-[12.5px] text-muted">
      {role === "candidate" ? "No new model yet. Train one from the case library." : "No live model"}
    </div>
  );
  const gateProd = (m.gate?.summary?.production || {}) as Record<string, number>;
  return (
    <motion.div layout layoutId={`model-${m.id}`} title={m.notes || undefined} className={`panel-flat h-full p-3 ${role === "production" ? "border-nominal/50" : "border-caution/50"}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2"><BrainCircuit size={18} className={role === "production" ? "text-nominal" : "text-caution"} /><span className="font-display text-[18px] font-bold">{m.id}</span></div>
        <Chip label={m.status} />
      </div>
      <div className="mt-1 text-[11.5px] text-muted mini:hidden" title={m.model_type === "rules" ? "Rule-based triage (transparent baseline)" : "L2 logistic regression · class-balanced · portable JSON artifact"}>{m.model_type === "rules" ? "Simple rules, easy to inspect (the starting point)" : "Learned model, trained on the case library"}</div>
      <div className="mt-2 grid grid-cols-2 gap-x-4 text-[11.5px]">
        <div className="kv"><span>Created</span><span>{fmt.utc(m.created_at, false)}</span></div>
        <div className="kv"><span>Based on</span><span className="hud-value">{m.parent_model || "none"}</span></div>
        <div className="kv mini:hidden"><span>Training data</span><span className="hud-value">{m.training_dataset_version || "n/a"}</span></div>
        <div className="kv mini:hidden" title="Fingerprint (hash) of the held-back test set"><span>Test set ID</span><span className="hud-value">{m.validation_dataset_hash || m.gate?.validation_hash || "n/a"}</span></div>
        {m.promoted_by && <div className="kv col-span-2"><span>Put live by</span><span>{m.promoted_by} · {fmt.utc(m.promoted_at)}</span></div>}
      </div>
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        {METRICS.map(([k, label, higher]) => {
          const v = metric(m, k);
          const base = role === "candidate" ? (gateProd[k] ?? metric(prodForDelta, k)) : null;
          const d = v != null && base != null ? v - base : null;
          const good = d != null && (higher ? d > 0 : d < 0);
          return (
            <div key={k} className="min-w-0 rounded-md border border-edge bg-deep/70 px-2.5 py-1.5 tiny:py-1" title={METRIC_HINT[k]}>
              <div className="hud-kicker truncate">{label}</div>
              <div className="flex items-baseline gap-1.5"><span className="hud-value text-[16px] font-semibold">{fmt.num(v, 3)}</span>
                {d != null && Math.abs(d) > 1e-9 && <span className={`hud-value text-[11px] ${good ? "text-nominal" : "text-critical"}`}>{d > 0 ? "+" : ""}{d.toFixed(3)}</span>}</div>
            </div>
          );
        })}
      </div>
      {m.notes && <p className="mt-2 line-clamp-2 text-[11px] leading-snug text-dim tiny:hidden">{m.notes}</p>}
    </motion.div>
  );
}

function GateView({ checks }: { checks: GateCheck[] }) {
  const label: Record<string, string> = {
    model_test_suite: "Passes all required model tests", validation_dataset_unchanged: "Test set is unchanged",
    validation_has_both_classes: "Test set has both positive and negative cases", primary_metric_not_worse: "Detection score is no worse than the live model",
    calibration_acceptable: "Confidence levels are acceptable", no_subgroup_regression: "No area's detection score drops by more than 0.05",
  };
  const tip: Record<string, string> = {
    validation_dataset_unchanged: "The held-back test set's fingerprint (hash) still matches the frozen one",
    validation_has_both_classes: "The validation set must contain both classes",
    primary_metric_not_worse: "Primary metric: AUPRC. The range is a 95% confidence interval of the difference (paired, grouped bootstrap).",
    calibration_acceptable: "ECE ≤ 0.15, or Brier score no worse than the live model",
    no_subgroup_regression: "Checked in every monitored area (AOI subgroup) with enough cases",
  };
  return (
    <div className="space-y-1.5">
      {checks.map((c) => (
        <div key={c.name} className="flex items-start gap-2 rounded-md border border-edge bg-deep/60 px-3 py-2 text-[12px]" title={tip[c.name]}>
          {c.passed ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-nominal" /> : <CircleX size={16} className="mt-0.5 shrink-0 text-critical" />}
          <div className="min-w-0">
            <div className="font-semibold">{label[c.name] || c.name}</div>
            {c.name === "primary_metric_not_worse" && c.detail != null && (() => { const d = c.detail as { candidate: number; production: number; diff_ci95: number[] }; return <div className="hud-value text-[11px] text-muted">new {fmt.num(d.candidate, 3)} vs live {fmt.num(d.production, 3)} · likely difference [{fmt.num(d.diff_ci95?.[0], 3)}, {fmt.num(d.diff_ci95?.[1], 3)}]</div>; })()}
            {c.name === "validation_dataset_unchanged" && c.detail != null && <div className="hud-value text-[11px] text-muted">{(c.detail as { frozen: string }).frozen}</div>}
            {c.name === "model_test_suite" && Array.isArray(c.detail) && <div className="text-[11px] text-muted">{(c.detail as GateCheck[]).map((t) => `${t.passed ? "✓" : "✗"} ${MODEL_TEST_LABEL[t.name] || t.name.replace(/_/g, " ")}`).join(" · ")}</div>}
          </div>
        </div>
      ))}
      <div className="flex items-center gap-2 rounded-md border border-beam/50 bg-beam/10 px-3 py-2 text-[12px]"><ShieldCheck size={16} className="text-beam2" /><span><b>A person must approve.</b> The safety check never puts a model live by itself.</span></div>
    </div>
  );
}

export default function LearnPage() {
  const models = useEngineQuery((e) => e.models("triage"));
  const labels = useEngineQuery((e) => e.labels("triage"));
  const jobs = useEngineQuery((e) => e.jobs());
  const audit = useEngineQuery((e) => e.audit("model", undefined, 60));
  const auditBox = useRef<HTMLDivElement>(null);
  const auditPg = useFitPage(audit.data || [], auditBox);
  const [busy, setBusy] = useState<string | null>(null);
  const [verify, setVerify] = useState<{ ok: boolean; n: number; head?: string } | null>(null);
  const ms = models.data || [];
  const prod = ms.find((m) => m.status === "PRODUCTION");
  const cand = ms.find((m) => m.status === "CANDIDATE");
  const history = ms.filter((m) => m.status !== "CANDIDATE");
  const L = labels.data || [];
  const sinceProd = (l: LabelRow) => !prod?.promoted_at || l.created_at > prod.promoted_at;
  const counts = useMemo(() => {
    const by = (f: (l: LabelRow) => boolean) => L.filter(f).length;
    return {
      train: by((l) => l.split === "train"), validation: by((l) => l.split === "validation"),
      confirmed: by((l) => l.target.y === 1 && l.source !== "cross_sensor_reference"),
      falsepos: by((l) => l.target.y === 0 && l.source !== "cross_sensor_reference"),
      field: by((l) => l.source === "field_measurement"), reference: by((l) => l.source === "cross_sensor_reference"),
      fresh: by((l) => sinceProd(l) && l.source !== "cross_sensor_reference"),
    };
  }, [L, prod]); // eslint-disable-line react-hooks/exhaustive-deps

  const who = () => { const o = getOperator(); if (!o) toast("Set your operator name first (top-right avatar)", "err"); return o; };
  const run = async (name: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(name);
    try { await fn(); toast(ok); } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(null); }
  };
  const train = () => { const o = who(); if (o) run("train", async () => { const j = await mutate((e) => e.retrain("triage", o)); if (j.status === "FAILED") throw new Error(`Training failed: ${j.error}`); }, "New model trained and safety-checked"); };
  const promote = () => { const o = who(); if (o && cand) run("promote", () => mutate((e) => e.promote(cand.id, o, "Promoted from the Learning screen after reviewing the gate")), `${cand.id} is now live`); };
  const reject = () => { const o = who(); if (o && cand) run("reject", () => mutate((e) => e.reject(cand.id, o, "Rejected after review")), `${cand.id} rejected`); };
  const rollback = (id: string) => { const o = who(); if (o) run("rollback", () => mutate((e) => e.rollback(id, o, "Rollback from Learning screen")), `Rolled back to ${id}`); };

  return (
    // Desktop: one screen; each panel scrolls inside itself. Smaller screens stack and scroll.
    <div className="space-y-3 p-3 short:p-2 xl:grid xl:h-full xl:grid-rows-[auto_minmax(0,1.15fr)_minmax(0,1fr)] xl:gap-3 xl:space-y-0 short:xl:gap-2">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <h1 className="font-display text-[22px] font-extrabold tracking-wide">LEARN · improve the model, safely</h1>
        <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted mini:hidden">
          {["Model flags", "Operator review", "Answer saved", "Case library", "New model", "Tested", "Safety check", "Person approves"].map((s, i, a) => (
            <React.Fragment key={s}><span className="rounded border border-edge bg-panel px-2 py-1">{s}</span>{i < a.length - 1 && <ArrowRight size={12} />}</React.Fragment>))}
        </div>
      </div>

      <div className="grid gap-3 short:gap-2 xl:min-h-0 xl:grid-cols-[1fr_300px_1fr]">
        <Panel title="Live model" kicker="IN USE NOW" bodyClass="p-3 scroll-quiet overflow-y-auto"><AnimatePresence mode="popLayout"><ModelCard key={prod?.id || "none"} m={prod} role="production" /></AnimatePresence></Panel>
        <Panel title="Case library" kicker="WHAT THE MODEL LEARNS FROM" bodyClass="p-3 space-y-2 tiny:space-y-1.5 scroll-quiet overflow-y-auto">
          {[["New since the live model", counts.fresh, "#27C3F3"], ["Confirmed by an analyst", counts.confirmed, "#23D484"], ["False alarms (analyst)", counts.falsepos, "#FF4D5E"],
            ["Checked with water samples", counts.field, "#FFC23D"], ["Sentinel-3 checks", counts.reference, "#93A6CB"]].map(([k, v, c]) => (
            <div key={k as string} className="flex items-center justify-between rounded-md border border-edge bg-deep/70 px-3 py-1.5 text-[12px] tiny:py-1">
              <span className="text-muted">{k}</span><span className="hud-value text-[16px] font-bold" style={{ color: c as string }}>{v as number}</span></div>))}
          <div className="text-[11px] text-dim mini:hidden">{counts.train} for training · {counts.validation} in the held-back test set. New cases always go to training. The test set changes only in a deliberate, logged step.</div>
          <button disabled={!!busy} onClick={train} className="btn btn-primary mt-1 w-full"><Play size={15} /> {busy === "train" ? "Training…" : "Train a new model"}</button>
          {(jobs.data || [])[0] && <div className="rounded-md border border-edge bg-deep/60 p-2 text-[11px]">
            <div className="flex justify-between"><span className="hud-value">{jobs.data![0].id}</span><Chip label={jobs.data![0].status} /></div>
            {jobs.data![0].log.slice(-4).map((l, i, all) => <div key={i} className={`text-muted ${i < all.length - 2 ? "tiny:hidden" : ""}`}>· {l.msg}{typeof l.n_train === "number" ? ` (${l.n_train} training / ${l.n_validation} test)` : ""}</div>)}
            {jobs.data![0].error && <div className="text-critical">{jobs.data![0].error}</div>}
          </div>}
        </Panel>
        <Panel title="New model" kicker="NOT LIVE YET" bodyClass="p-3 scroll-quiet overflow-y-auto"><AnimatePresence mode="popLayout"><ModelCard key={cand?.id || "none"} m={cand} role="candidate" prodForDelta={prod} /></AnimatePresence></Panel>
      </div>

      <div className="grid gap-3 short:gap-2 xl:min-h-0 xl:grid-cols-[1.2fr_1fr]">
        <Panel title="Safety check before going live" kicker="LIVE VS NEW MODEL · SAME HELD-BACK TEST SET" bodyClass="p-3 scroll-quiet overflow-y-auto">
          {cand?.gate ? <>
            <GateView checks={cand.gate.checks} />
            <div className="mt-3 flex gap-2">
              <button disabled={!!busy || !cand.gate.passed} onClick={promote} className="btn btn-good flex-1" title={cand.gate.passed ? "Put this model live" : "Safety check not passed"}><GitBranch size={15} /> Go live</button>
              <button disabled={!!busy} onClick={reject} className="btn btn-bad flex-1"><CircleX size={15} /> Reject new model</button>
            </div>
            {!cand.gate.passed && <p className="mt-2 text-[11.5px] text-critical">Safety check failed, so it cannot go live. Fix the data or reject the new model.</p>}
          </> : <p className="text-[12.5px] text-muted" title="Compared on the same frozen validation labels, with a paired, grouped bootstrap">Train a new model to see its safety check. It is scored against the live model on the same held-back test set.</p>}
        </Panel>
        <Panel title="Model history & log" right={<Pager {...auditPg} />} bodyClass="flex min-h-0 flex-col gap-2 p-3">
          {history.map((m) => (
            <div key={m.id} className="flex shrink-0 items-center justify-between rounded-md border border-edge bg-deep/60 px-3 py-1.5 text-[12px]">
              <span className="hud-value">{m.id}</span><span className="text-muted">{m.model_type}</span><Chip label={m.status} />
              {m.status === "RETIRED" && <button disabled={!!busy} onClick={() => rollback(m.id)} className="btn px-2 py-1 text-[11px]"><Undo2 size={13} /> Roll back</button>}
            </div>
          ))}
          <div className="rule-h my-1 shrink-0" />
          <div ref={auditBox} className="scroll-quiet min-h-0 flex-1 space-y-1 overflow-y-auto">
            {auditPg.rows.map((a) => (
              <div key={a.seq} data-row className="flex gap-2 whitespace-nowrap text-[11px]"><span className="hud-value text-dim">#{a.seq}</span><span className="text-muted">{fmt.utc(a.at)}</span><span className="text-ink">{a.actor}</span><span className="text-cyan">{a.action}</span><span className="hud-value">{a.entity_id}</span></div>
            ))}
          </div>
          <button className="btn w-full" title="Each log entry is hash-chained to the one before it" onClick={async () => setVerify(await (await import("@/lib/engine")).getEngine().verifyAudit())}><History size={14} /> Check the log for tampering</button>
          {verify && <div className={`text-[11.5px] ${verify.ok ? "text-nominal" : "text-critical"}`}>{verify.ok ? `Log intact: ${verify.n} entries, none altered · latest ${verify.head?.slice(0, 16)}…` : "Tampering found: a log entry was changed"}</div>}
        </Panel>
      </div>
    </div>
  );
}
