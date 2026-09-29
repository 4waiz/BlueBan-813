"use client";
/**
 * LEARN - why BlueBan gets better, and why it cannot get worse by accident.
 *
 * MODEL PREDICTION -> OPERATOR REVIEW -> VERIFIED LABEL -> LABEL STORE ->
 * RETRAIN CANDIDATE -> EVALUATION -> MODEL GATE -> HUMAN PROMOTION.
 */
import React, { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, BrainCircuit, CheckCircle2, CircleX, GitBranch, History, Play, ShieldCheck, Undo2 } from "lucide-react";
import { getOperator, mutate, useEngineQuery } from "@/lib/engine";
import type { GateCheck, LabelRow, ModelRecord } from "@/lib/engine/types";
import { Chip, fmt, Panel, toast } from "@/components/ui";

const METRICS: [string, string, boolean][] = [["auprc", "AUPRC", true], ["auroc", "AUROC", true], ["f1", "F1", true], ["precision", "Precision", true], ["recall", "Recall", true], ["brier", "Brier", false], ["ece", "ECE (calibration)", false]];

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
      {role === "candidate" ? "No candidate yet. Train one from the verified labels." : "No production model"}
    </div>
  );
  const gateProd = (m.gate?.summary?.production || {}) as Record<string, number>;
  return (
    <motion.div layout layoutId={`model-${m.id}`} className={`panel-flat h-full p-4 ${role === "production" ? "border-nominal/50" : "border-caution/50"}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2"><BrainCircuit size={18} className={role === "production" ? "text-nominal" : "text-caution"} /><span className="font-display text-[18px] font-bold">{m.id}</span></div>
        <Chip label={m.status} />
      </div>
      <div className="mt-1 text-[11.5px] text-muted">{m.model_type === "rules" ? "Rule-based triage (transparent baseline)" : "L2 logistic regression · class-balanced · portable JSON artifact"}</div>
      <div className="mt-2 grid grid-cols-2 gap-x-4 text-[11.5px]">
        <div className="kv"><span>Created</span><span>{fmt.utc(m.created_at, false)}</span></div>
        <div className="kv"><span>Parent</span><span className="hud-value">{m.parent_model || "none"}</span></div>
        <div className="kv"><span>Training set</span><span className="hud-value">{m.training_dataset_version || "n/a"}</span></div>
        <div className="kv"><span>Validation hash</span><span className="hud-value">{m.validation_dataset_hash || m.gate?.validation_hash || "n/a"}</span></div>
        {m.promoted_by && <div className="kv col-span-2"><span>Promoted by</span><span>{m.promoted_by} · {fmt.utc(m.promoted_at)}</span></div>}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {METRICS.map(([k, label, higher]) => {
          const v = metric(m, k);
          const base = role === "candidate" ? (gateProd[k] ?? metric(prodForDelta, k)) : null;
          const d = v != null && base != null ? v - base : null;
          const good = d != null && (higher ? d > 0 : d < 0);
          return (
            <div key={k} className="rounded-md border border-edge bg-deep/70 px-3 py-2">
              <div className="hud-kicker">{label}</div>
              <div className="flex items-baseline gap-2"><span className="hud-value text-[18px] font-semibold">{fmt.num(v, 3)}</span>
                {d != null && Math.abs(d) > 1e-9 && <span className={`hud-value text-[11px] ${good ? "text-nominal" : "text-critical"}`}>{d > 0 ? "+" : ""}{d.toFixed(3)}</span>}</div>
            </div>
          );
        })}
      </div>
      {m.notes && <p className="mt-3 text-[11px] leading-snug text-dim">{m.notes}</p>}
    </motion.div>
  );
}

function GateView({ checks }: { checks: GateCheck[] }) {
  const label: Record<string, string> = {
    model_test_suite: "Required model test suite passes", validation_dataset_unchanged: "Validation dataset unchanged (frozen hash)",
    validation_has_both_classes: "Validation set contains both classes", primary_metric_not_worse: "Primary metric (AUPRC) not worse than production",
    calibration_acceptable: "Calibration acceptable (ECE ≤ 0.15 or Brier not worse)", no_subgroup_regression: "No AOI subgroup regression > 0.05",
  };
  return (
    <div className="space-y-1.5">
      {checks.map((c) => (
        <div key={c.name} className="flex items-start gap-2 rounded-md border border-edge bg-deep/60 px-3 py-2 text-[12px]">
          {c.passed ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-nominal" /> : <CircleX size={16} className="mt-0.5 shrink-0 text-critical" />}
          <div className="min-w-0">
            <div className="font-semibold">{label[c.name] || c.name}</div>
            {c.name === "primary_metric_not_worse" && c.detail != null && (() => { const d = c.detail as { candidate: number; production: number; diff_ci95: number[] }; return <div className="hud-value text-[11px] text-muted">candidate {fmt.num(d.candidate, 3)} vs production {fmt.num(d.production, 3)} · paired grouped bootstrap 95% CI of Δ [{fmt.num(d.diff_ci95?.[0], 3)}, {fmt.num(d.diff_ci95?.[1], 3)}]</div>; })()}
            {c.name === "validation_dataset_unchanged" && c.detail != null && <div className="hud-value text-[11px] text-muted">{(c.detail as { frozen: string }).frozen}</div>}
            {c.name === "model_test_suite" && Array.isArray(c.detail) && <div className="text-[11px] text-muted">{(c.detail as GateCheck[]).map((t) => `${t.passed ? "✓" : "✗"} ${t.name.replace(/_/g, " ")}`).join(" · ")}</div>}
          </div>
        </div>
      ))}
      <div className="flex items-center gap-2 rounded-md border border-beam/50 bg-beam/10 px-3 py-2 text-[12px]"><ShieldCheck size={16} className="text-beam2" /><span><b>Human approval</b> required: the gate never promotes a model on its own.</span></div>
    </div>
  );
}

export default function LearnPage() {
  const models = useEngineQuery((e) => e.models("triage"));
  const labels = useEngineQuery((e) => e.labels("triage"));
  const jobs = useEngineQuery((e) => e.jobs());
  const audit = useEngineQuery((e) => e.audit("model", undefined, 60));
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
  const train = () => { const o = who(); if (o) run("train", async () => { const j = await mutate((e) => e.retrain("triage", o)); if (j.status === "FAILED") throw new Error(`Training job failed: ${j.error}`); }, "Candidate trained and gated"); };
  const promote = () => { const o = who(); if (o && cand) run("promote", () => mutate((e) => e.promote(cand.id, o, "Promoted from the Learning screen after reviewing the gate")), `${cand.id} promoted to production`); };
  const reject = () => { const o = who(); if (o && cand) run("reject", () => mutate((e) => e.reject(cand.id, o, "Rejected after review")), `${cand.id} rejected`); };
  const rollback = (id: string) => { const o = who(); if (o) run("rollback", () => mutate((e) => e.rollback(id, o, "Rollback from Learning screen")), `Rolled back to ${id}`); };

  return (
    <div className="space-y-3 p-3">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <h1 className="font-display text-[22px] font-extrabold tracking-wide">LEARN · governed model improvement</h1>
        <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted">
          {["Prediction", "Operator review", "Verified label", "Label store", "Candidate", "Evaluation", "Gate", "Human promotion"].map((s, i, a) => (
            <React.Fragment key={s}><span className="rounded border border-edge bg-panel px-2 py-1">{s}</span>{i < a.length - 1 && <ArrowRight size={12} />}</React.Fragment>))}
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[1fr_300px_1fr]">
        <Panel title="Current production model" kicker="PRODUCTION" bodyClass="p-3"><AnimatePresence mode="popLayout"><ModelCard key={prod?.id || "none"} m={prod} role="production" /></AnimatePresence></Panel>
        <Panel title="Verified labels" kicker="LABEL STORE" bodyClass="p-3 space-y-2">
          {[["New since production", counts.fresh, "#27C3F3"], ["Analyst-confirmed events", counts.confirmed, "#23D484"], ["Analyst false positives", counts.falsepos, "#FF4D5E"],
            ["Field-validated", counts.field, "#FFC23D"], ["Cross-sensor references", counts.reference, "#93A6CB"]].map(([k, v, c]) => (
            <div key={k as string} className="flex items-center justify-between rounded-md border border-edge bg-deep/70 px-3 py-2 text-[12px]">
              <span className="text-muted">{k}</span><span className="hud-value text-[16px] font-bold" style={{ color: c as string }}>{v as number}</span></div>))}
          <div className="text-[11px] text-dim">{counts.train} train · {counts.validation} frozen validation. New labels always go to TRAIN; the validation set only changes by an explicit, audited re-freeze.</div>
          <button disabled={!!busy} onClick={train} className="btn btn-primary mt-1 w-full"><Play size={15} /> {busy === "train" ? "Training…" : "Train candidate"}</button>
          {(jobs.data || [])[0] && <div className="rounded-md border border-edge bg-deep/60 p-2 text-[11px]">
            <div className="flex justify-between"><span className="hud-value">{jobs.data![0].id}</span><Chip label={jobs.data![0].status} /></div>
            {jobs.data![0].log.slice(-4).map((l, i) => <div key={i} className="text-muted">· {l.msg}{typeof l.n_train === "number" ? ` (${l.n_train} train / ${l.n_validation} val)` : ""}</div>)}
            {jobs.data![0].error && <div className="text-critical">{jobs.data![0].error}</div>}
          </div>}
        </Panel>
        <Panel title="Candidate model" kicker="CANDIDATE" bodyClass="p-3"><AnimatePresence mode="popLayout"><ModelCard key={cand?.id || "none"} m={cand} role="candidate" prodForDelta={prod} /></AnimatePresence></Panel>
      </div>

      <div className="grid gap-3 xl:grid-cols-[1.2fr_1fr]">
        <Panel title="Promotion gate: old production vs candidate on the frozen validation set" bodyClass="p-3">
          {cand?.gate ? <>
            <GateView checks={cand.gate.checks} />
            <div className="mt-3 flex gap-2">
              <button disabled={!!busy || !cand.gate.passed} onClick={promote} className="btn btn-good flex-1" title={cand.gate.passed ? "Promote to production" : "Gate not passed"}><GitBranch size={15} /> Promote to production</button>
              <button disabled={!!busy} onClick={reject} className="btn btn-bad flex-1"><CircleX size={15} /> Reject candidate</button>
            </div>
            {!cand.gate.passed && <p className="mt-2 text-[11.5px] text-critical">The gate failed, so promotion is disabled. Fix the data or reject the candidate.</p>}
          </> : <p className="text-[12.5px] text-muted">Train a candidate to see its gate report. The candidate is compared with the current production model on the same frozen validation labels, with a paired grouped bootstrap.</p>}
        </Panel>
        <Panel title="Model history & audit" bodyClass="p-3 space-y-2">
          {history.map((m) => (
            <div key={m.id} className="flex items-center justify-between rounded-md border border-edge bg-deep/60 px-3 py-2 text-[12px]">
              <span className="hud-value">{m.id}</span><span className="text-muted">{m.model_type}</span><Chip label={m.status} />
              {m.status === "RETIRED" && <button disabled={!!busy} onClick={() => rollback(m.id)} className="btn px-2 py-1 text-[11px]"><Undo2 size={13} /> Roll back</button>}
            </div>
          ))}
          <div className="rule-h my-2" />
          <div className="max-h-[220px] space-y-1 overflow-y-auto">
            {(audit.data || []).map((a) => (
              <div key={a.seq} className="flex gap-2 text-[11px]"><span className="hud-value text-dim">#{a.seq}</span><span className="text-muted">{fmt.utc(a.at)}</span><span className="text-ink">{a.actor}</span><span className="text-cyan">{a.action}</span><span className="hud-value">{a.entity_id}</span></div>
            ))}
          </div>
          <button className="btn w-full" onClick={async () => setVerify(await (await import("@/lib/engine")).getEngine().verifyAudit())}><History size={14} /> Verify audit hash chain</button>
          {verify && <div className={`text-[11.5px] ${verify.ok ? "text-nominal" : "text-critical"}`}>{verify.ok ? `Chain intact: ${verify.n} events, head ${verify.head?.slice(0, 16)}…` : "Chain broken: an audit row was altered"}</div>}
        </Panel>
      </div>
    </div>
  );
}
