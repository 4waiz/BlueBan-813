"use client";
/**
 * VALIDATION - impossible to miss, impossible to over-read.
 *
 * A. Data quality  B. UAE matchups  C. Model performance  D. 813 ablation
 * E. Spatial holdout  F. Negative control
 *
 * Every number comes from outputs/validation/validation_summary.json, which
 * scripts/build_validation.py recomputes from the pipeline outputs. A section
 * with no data says so; nothing is typed in.
 */
import React, { useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleSlash, Database, FlaskConical, Gauge, Layers, ShieldOff, Split } from "lucide-react";
import { useEngineQuery, useStatic } from "@/lib/engine";
import type { ModelRecord } from "@/lib/engine/types";
import { Chip, fmt, Panel, SimBadge, WhyButton } from "@/components/ui";

type Num = number | null;
type CM = { tp: number; fp: number; fn: number; tn: number };
type Metrics = { auroc: Num; auprc: Num; f1: Num; precision: Num; recall: Num; brier: Num; ece: Num; n: number; positives: number; confusion: CM };
type Boot = { diff: Num; ci: [Num, Num]; a_ci?: [Num, Num]; b_ci?: [Num, Num]; n_boot: number };
type AoiQ = {
  aoi_id: string; name?: string; resolution_m?: number; n_datatakes: number; n_ok: number; n_failed: number; n_usable: number;
  date_range: [string | null, string | null]; platforms: Record<string, number>; processing_baselines: Record<string, number>;
  n_boa_offset_applied: number; median_valid_fraction: Num; median_cloud_fraction_of_valid: Num; median_water_fraction: Num;
  median_glint_fraction: Num; median_b11_water: Num; median_negative_red_fraction: Num;
};
type Arm = { f1: Num; precision: Num; recall: Num; roc_auc: Num; average_precision: Num; confusion_matrix?: CM; n_features?: number };
type Summary = {
  generated_utc: string;
  A_data_quality: { aois: AoiQ[]; method: string };
  B_matchups: {
    in_situ: { n_matchups: number; status: string; reason: string; engine: Record<string, unknown>; quantification: { usable_for_physical_units: boolean; quantity_kind: string; reasons: string[]; thresholds: Record<string, number> } };
    cross_sensor: { n: number; per_hypothesis?: Record<string, { n: number; positive: number; negative: number; variable: string }>; agreement?: Record<string, { spearman_rho: number; p_value: number; n: number }>; points?: { aoi: string; date: string; hyp: string; s2_delta: Num; olci_ratio: Num; y: number; dt_min: number }[]; median_abs_dt_minutes?: Num; rule?: Record<string, unknown>; caveat?: string };
  };
  C_model_performance: {
    status?: string; n_train?: number; n_validation?: number; train_positive?: number; validation_positive?: number; validation_hash?: string;
    production?: { model: string; metrics: Metrics }; candidate?: { model?: string; metrics?: Metrics; status?: string; coefficients?: Record<string, number> };
    bootstrap?: { auprc: Boot; auroc: Boot };
  };
  D_813_ablation: {
    status?: string; scene?: string; arms?: Record<string, string>; simulated?: boolean; caveats?: string[];
    hard?: { arms: Record<string, Arm>; n_samples: number; n_positive: number; n_spatial_blocks: number; block_size_m: number };
    easy?: { arms: Record<string, Arm>; n_samples: number; n_positive: number };
    olci_regression?: { n_matchups: number; dt_hours: { median?: number }; targets: Record<string, Record<string, { r2: Num; rmse: Num; mae: Num; r2_ci95?: { lo: Num; hi: Num } }>> };
    simulator_validation?: { question: string; time_offset_minutes: number; land: Record<string, { r2_1to1: Num; rmse: Num; bias: Num; n: number }>; water: Record<string, { r2_1to1: Num; rmse: Num; bias: Num; n: number }>; interpretation?: Record<string, string> };
  };
  E_spatial_holdout: {
    status?: string;
    triage_leave_one_aoi_out?: { held_out_aoi: string; n_test: number; test_positive: number; n_train: number; candidate?: Metrics; production?: Metrics; status?: string }[];
    ablation_spatial_vs_random?: Record<string, { spatial_blocked_f1: Num; random_split_f1: Num }> | null;
  };
  F_negative_control: {
    annaba?: { id: string; status: string; title?: string; rx_percentile: Num; seasonal_percentile: Num; n_seasonal: Num; reading: string };
    cross_sensor_rejections?: { n: number; of: number; largest: { aoi: string; date: string; hypothesis: string; area_km2: Num; s2_z: Num; olci: { variable: string; units: string; region_median: number; background_median: number; ratio: number; dt_minutes: number } }[] };
  };
};

const SECTIONS = [
  { key: "A", title: "Data quality", icon: <Database size={15} /> },
  { key: "B", title: "Independent checks", icon: <FlaskConical size={15} /> },
  { key: "C", title: "Model performance", icon: <Gauge size={15} /> },
  { key: "D", title: "What 813 adds", icon: <Layers size={15} /> },
  { key: "E", title: "Unseen areas", icon: <Split size={15} /> },
  { key: "F", title: "False-alarm test", icon: <ShieldOff size={15} /> },
] as const;

const ARM_KEY: Record<string, string> = { A: "S2_multispectral_11band", B: "813_hyperspectral_205band", C: "813_hyperspectral_261band_5nm" };
const n0 = (v: Num | undefined, d = 3) => fmt.num(v ?? null, d);
const ci = (c?: [Num, Num]) => (c && c[0] != null && c[1] != null ? `[${c[0].toFixed(3)}, ${c[1].toFixed(3)}]` : "");

function Th({ children, right, title }: { children: React.ReactNode; right?: boolean; title?: string }) {
  return <th className={`px-2 py-1.5 font-semibold text-dim ${right ? "text-right" : "text-left"}`} title={title}>{children}</th>;
}
function Td({ children, right, mono, className = "" }: { children: React.ReactNode; right?: boolean; mono?: boolean; className?: string }) {
  return <td className={`px-2 py-1.5 ${right ? "text-right" : ""} ${mono ? "hud-value" : ""} ${className}`}>{children}</td>;
}

function Stat({ label, value, sub, tone = "text-ink", hint }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: string; hint?: string }) {
  return (
    <div className="rounded-md border border-edge bg-deep/60 px-3 py-2" title={hint}>
      <div className="hud-kicker">{label}</div>
      <div className={`hud-value mt-0.5 text-[20px] font-bold ${tone}`}>{value}</div>
      {sub && <div className="text-[11px] text-muted">{sub}</div>}
    </div>
  );
}

// --------------------------------------------------------------------------- A
function DataQuality({ d }: { d: Summary["A_data_quality"] }) {
  const tot = d.aois.reduce((s, a) => s + a.n_ok, 0), use = d.aois.reduce((s, a) => s + a.n_usable, 0);
  const fail = d.aois.reduce((s, a) => s + a.n_failed, 0);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Areas monitored" value={d.aois.length} />
        <Stat label="Images processed" value={tot.toLocaleString()} sub={fail ? `${fail} failed to read (logged)` : "none failed to read"} hint="Sentinel-2 datatakes" />
        <Stat label="Usable images" value={use.toLocaleString()} sub={tot ? fmt.pct(use / tot) : ""} hint="Usable: at least 500 water pixels after masking" />
        <Stat label="Offset-corrected" value={d.aois.reduce((s, a) => s + a.n_boa_offset_applied, 0).toLocaleString()} sub="ESA processing 04.00 or later" hint="BOA_ADD_OFFSET −1000, applied by processing baseline (≥ 04.00)" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11.5px]">
          <thead><tr className="border-b border-edge"><Th>Area</Th><Th>Period</Th><Th right title="Sentinel-2 datatakes. Failed reads in red.">Images</Th><Th right title="At least 500 water pixels">Usable</Th><Th right>Median valid</Th><Th right>Median cloud</Th><Th right title="Median share of water flagged for sun glint. Corrected, not discarded.">Sun glint</Th><Th right title="Median shortwave-infrared (B11) value over water. Near zero means little glint.">SWIR (B11)</Th><Th title="Sentinel-2 processing baselines in this period">ESA versions</Th></tr></thead>
          <tbody>
            {d.aois.map((a) => (
              <tr key={a.aoi_id} className="border-b border-edge/50">
                <Td><span className="font-semibold">{a.aoi_id}</span>{a.name && <span className="ml-1 text-dim">{a.name}</span>}</Td>
                <Td mono>{a.date_range[0]} → {a.date_range[1]}</Td>
                <Td right mono>{a.n_ok}{a.n_failed ? <span className="text-critical"> (+{a.n_failed})</span> : ""}</Td>
                <Td right mono>{a.n_usable}</Td>
                <Td right mono>{fmt.pct(a.median_valid_fraction)}</Td>
                <Td right mono>{fmt.pct(a.median_cloud_fraction_of_valid)}</Td>
                <Td right mono className={(a.median_glint_fraction ?? 0) > 0.5 ? "text-caution" : ""}>{fmt.pct(a.median_glint_fraction)}</Td>
                <Td right mono>{n0(a.median_b11_water, 4)}</Td>
                <Td className="text-dim">{Object.keys(a.processing_baselines).join(", ")}</Td>
              </tr>))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-dim">Sun glint is corrected, not thrown away. The glint column shows how much each area relied on that fix.</p>
    </div>
  );
}

function DataQualityWhy({ d }: { d: Summary["A_data_quality"] }) {
  return (
    <WhyButton title="How the images are checked">
      <div className="space-y-2 text-[12.5px] text-muted">
        <p>{d.method}</p>
        <p>An image counts as usable with at least 500 water pixels after masking. Failed reads are counted, not hidden (red in the table).</p>
        <p>Images from ESA processing baseline 04.00 or later get the −1000 reflectance offset (BOA_ADD_OFFSET) applied.</p>
        <p>Glint-flagged water is not discarded. A SWIR (B12) offset removes the first-order glint. The glint share is reported so you can judge how much a scene depended on that correction.</p>
        <p>B11 is a shortwave-infrared band. Over clear water it is close to zero, so higher values point to sun glint.</p>
      </div>
    </WhyButton>
  );
}

// --------------------------------------------------------------------------- B
function Scatter({ pts }: { pts: NonNullable<Summary["B_matchups"]["cross_sensor"]["points"]> }) {
  const W = 360, H = 190, P = 30;
  const xs = pts.map((p) => p.s2_delta).filter((v): v is number => v != null);
  const ys = pts.map((p) => (p.olci_ratio && p.olci_ratio > 0 ? Math.log10(p.olci_ratio) : null)).filter((v): v is number => v != null);
  if (xs.length < 2) return null;
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(-0.3, ...ys), y1 = Math.max(0.6, ...ys);
  const sx = (v: number) => P + ((v - x0) / (x1 - x0 || 1)) * (W - P - 8), sy = (v: number) => H - P + 6 - ((v - y0) / (y1 - y0 || 1)) * (H - P - 6);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[190px] w-full">
      <line x1={P} x2={W - 8} y1={sy(0)} y2={sy(0)} stroke="#2A3B5C" strokeDasharray="3 3" />
      <line x1={P} x2={W - 8} y1={sy(Math.log10(1.5))} y2={sy(Math.log10(1.5))} stroke="#23D48455" strokeDasharray="2 4" />
      <text x={W - 10} y={sy(Math.log10(1.5)) - 3} textAnchor="end" fontSize="9" fill="#23D484">×1.5 confirm threshold</text>
      {pts.map((p, i) => p.s2_delta == null || !p.olci_ratio ? null : (
        <circle key={i} cx={sx(p.s2_delta)} cy={sy(Math.log10(p.olci_ratio))} r={3.2} fill={p.y === 1 ? "#23D484" : "#FF4D5E"} fillOpacity={0.75}>
          <title>{`${p.aoi} ${p.date} ${p.hyp} · Sentinel-2 change ${p.s2_delta.toFixed(3)} · Sentinel-3 ×${p.olci_ratio.toFixed(2)}`}</title>
        </circle>))}
      <text x={P} y={H - 4} fontSize="9.5" fill="#93A6CB">Sentinel-2 change vs seasonal normal (NDCI or turbidity) →</text>
      <text x={10} y={P - 12} fontSize="9.5" fill="#93A6CB">Sentinel-3: patch vs surroundings (log₁₀)</text>
    </svg>
  );
}

function Matchups({ d }: { d: Summary["B_matchups"] }) {
  const cs = d.cross_sensor, q = d.in_situ.quantification;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="space-y-2 rounded-md border border-critical/40 bg-critical/5 p-3">
        <div className="flex items-center justify-between"><div className="hud-kicker">Water samples matched to satellite images</div><Chip label={d.in_situ.status} color="#FF4D5E" /></div>
        <div className={`hud-value text-[30px] font-bold ${d.in_situ.n_matchups ? "text-nominal" : "text-critical"}`}>{d.in_situ.n_matchups}</div>
        <p className="text-[12px] text-muted">{d.in_situ.n_matchups ? "Water samples matched to satellite images." : "We found no public UAE water-sample data to check against."}</p>
        <div className="grid grid-cols-2 gap-x-4 text-[11.5px]">
          <div className="kv" title="Max |Δt|: longest gap allowed between sample and image"><span>Time window</span><span className="hud-value">±{String(d.in_situ.engine.max_dt_hours)} h</span></div>
          <div className="kv" title="Pixels averaged around each sample"><span>Pixel box</span><span className="hud-value">{String(d.in_situ.engine.window_px)}×{String(d.in_situ.engine.window_px)} px</span></div>
          <div className="kv" title="Min valid: share of the box that must be clear"><span>Min. clear pixels</span><span className="hud-value">{fmt.pct(Number(d.in_situ.engine.min_valid_frac))}</span></div>
          <div className="kv" title="Max CV: largest coefficient of variation allowed in the box"><span>Max. variation</span><span className="hud-value">{String(d.in_situ.engine.max_cv)}</span></div>
        </div>
        <div className="rounded border border-edge bg-deep/60 p-2 text-[11.5px]">
          <b className="text-ink">Real units allowed?</b> <span className={q.usable_for_physical_units ? "text-nominal" : "text-critical"}>{q.usable_for_physical_units ? "yes" : "NO"}</span>. Values are shown as <b>{q.quantity_kind}</b>.
          <ul className="mt-1 list-disc pl-5 text-muted">{q.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          Matching and calibration code is built and tested (tests/test_matchup.py). It runs as soon as real samples arrive in Verify or by lab CSV.
        </div>
      </div>
      <div className="space-y-2 rounded-md border border-edge bg-deep/40 p-3">
        <div className="flex items-center justify-between"><div className="hud-kicker">Sentinel-3 check (second satellite)</div><Chip label="NOT GROUND TRUTH" color="#FFC23D" /></div>
        {cs.n ? <>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(cs.per_hypothesis || {}).map(([h, v]) => (
              <Stat key={h} label={`${h.replace(/_/g, " ")} · confirmed`} value={`${v.positive}/${v.n}`} sub={`${v.negative} not confirmed`} hint={`Sentinel-3 product used: ${v.variable}`} />))}
            <Stat label="Time apart (median)" value={`${n0(cs.median_abs_dt_minutes, 0)} min`} sub="same morning" />
          </div>
          {cs.points && <Scatter pts={cs.points} />}
          <div className="text-[11.5px] text-muted">
            {Object.entries(cs.agreement || {}).map(([h, a]) => <div key={h} title={`Spearman ρ = ${a.spearman_rho.toFixed(2)}, p = ${a.p_value < 0.001 ? a.p_value.toExponential(1) : a.p_value.toFixed(3)}, n = ${a.n}`}>{h.replace(/_/g, " ")}: agreement score <b className="text-ink">{a.spearman_rho.toFixed(2)}</b> (−1 to 1, n = {a.n})</div>)}
            <p className="mt-1 text-dim">Sentinel-3 values are ESA model estimates, not samples. This is a cross-check, not proof.</p>
          </div>
        </> : <p className="text-[12px] text-muted">No Sentinel-3 checks built yet (scripts/build_labels.py).</p>}
      </div>
    </div>
  );
}

function MatchupsWhy({ d }: { d: Summary["B_matchups"] }) {
  const cs = d.cross_sensor, q = d.in_situ.quantification;
  return (
    <WhyButton title="What counts as an independent check">
      <div className="space-y-2 text-[12.5px] text-muted">
        <p><b className="text-ink">Water samples.</b> {d.in_situ.reason}</p>
        <p>A sample matches an image if it was taken within ±{String(d.in_situ.engine.max_dt_hours)} h. The pixel box around it must be mostly clear and even.</p>
        <p>Real units need at least {q.thresholds.min_matchups} matches from {q.thresholds.min_groups} independent groups (a station or a sampling day). Grouped cross-validation must also reach R² ≥ {q.thresholds.min_r2_log10} on log values. Until then, values are indices, not lab concentrations.</p>
        <p><b className="text-ink">Sentinel-3 check.</b> {cs.caveat}</p>
        <p>In the chart, each dot is one alert. Across: the Sentinel-2 change vs its seasonal normal (NDCI chlorophyll index, or turbidity). Up: the Sentinel-3 patch vs its surroundings, on a log scale. Green means Sentinel-3 confirms, red means it does not. The dashed line marks the 1.5× contrast rule.</p>
        {Object.entries(cs.agreement || {}).map(([h, a]) => <p key={h}>{h.replace(/_/g, " ")}: Spearman ρ = {a.spearman_rho.toFixed(2)} (p = {a.p_value < 0.001 ? a.p_value.toExponential(1) : a.p_value.toFixed(3)}, n = {a.n}) between the Sentinel-2 change and the Sentinel-3 contrast.</p>)}
      </div>
    </WhyButton>
  );
}

// --------------------------------------------------------------------------- C
const MROWS: [keyof Metrics, string, boolean][] = [["auprc", "Detection score", true], ["auroc", "Ranking score", true], ["f1", "Overall (F1)", true], ["precision", "Correct alerts", true], ["recall", "Events caught", true], ["brier", "Probability error", false], ["ece", "Calibration error", false]];
const MHINT: Record<string, string> = {
  auprc: "AUPRC: area under the precision-recall curve. 0 to 1, higher is better.",
  auroc: "AUROC: area under the ROC curve. 0.5 is a coin flip, 1 is perfect.",
  f1: "F1 @0.5: balance of correct alerts and events caught, at a 0.5 threshold. Higher is better.",
  precision: "Precision: share of alerts that were positive. Higher is better.",
  recall: "Recall: share of positive cases that were caught. Higher is better.",
  brier: "Brier score: error in the predicted probabilities. Lower is better.",
  ece: "ECE: gap between stated confidence and real hit rate. Lower is better.",
};

function Performance({ d, live }: { d: Summary["C_model_performance"]; live: ModelRecord | null | undefined }) {
  if (d.status) return <p className="text-muted">No labelled cases yet: {d.status}.</p>;
  const p = d.production?.metrics, c = d.candidate?.metrics;
  const liveV = (k: string) => live?.metrics?.find((m) => m.metric === k && m.split === "validation" && m.subgroup === "all")?.value ?? null;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Training cases" value={d.n_train} sub={`${d.train_positive} positive`} />
        <Stat label="Held-back test set" value={d.n_validation} sub={`${d.validation_positive} positive · split by area and month`} hint="Frozen validation set, grouped by AOI-month" />
        <Stat label="Test set ID" value={<span className="text-[14px]">{d.validation_hash}</span>} sub="safety check fails if it changes" hint="Fingerprint (hash) of the frozen test set" />
        <Stat label="Labels come from" value={<span className="text-[14px]">Sentinel-3 check</span>} sub="weight 0.5 (analyst 1.0, water sample 2.0)" hint="OLCI cross-sensor reference labels" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead><tr className="border-b border-edge"><Th title="Triage metrics on the frozen validation set">Score (held-back test set)</Th><Th right title="Production rule baseline">Simple rules</Th><Th right title="Offline candidate: logistic regression">New model (offline)</Th><Th right title="Δ with a 95% confidence interval (grouped bootstrap)">Change (likely range)</Th><Th right>Live model{live ? ` · ${live.id}` : ""}</Th></tr></thead>
          <tbody>
            {MROWS.map(([k, label, higher]) => {
              const a = p?.[k] as Num, b = c?.[k] as Num;
              const boot = k === "auprc" ? d.bootstrap?.auprc : k === "auroc" ? d.bootstrap?.auroc : undefined;
              const delta = a != null && b != null ? b - a : null;
              return (
                <tr key={k} className="border-b border-edge/50">
                  <Td><span title={MHINT[k]}>{label}</span></Td>
                  <Td right mono>{n0(a)}{boot?.a_ci && <span className="ml-1 text-[10px] text-dim">{ci(boot.a_ci)}</span>}</Td>
                  <Td right mono>{n0(b)}{boot?.b_ci && <span className="ml-1 text-[10px] text-dim">{ci(boot.b_ci)}</span>}</Td>
                  <Td right mono className={delta == null ? "" : (higher ? delta > 0 : delta < 0) ? "text-nominal" : "text-critical"}>{delta == null ? "n/a" : `${delta > 0 ? "+" : ""}${delta.toFixed(3)}`}{boot && <span className="ml-1 text-[10px] text-dim">{ci(boot.ci)}</span>}</Td>
                  <Td right mono>{n0(liveV(k as string))}</Td>
                </tr>);
            })}
            <tr><Td><span title="Confusion matrix: tp / fp / fn / tn">Caught / false alarms / missed / rightly ignored</span></Td><Td right mono>{p ? `${p.confusion.tp}/${p.confusion.fp}/${p.confusion.fn}/${p.confusion.tn}` : "n/a"}</Td><Td right mono>{c ? `${c.confusion.tp}/${c.confusion.fp}/${c.confusion.fn}/${c.confusion.tn}` : "n/a"}</Td><Td right>{""}</Td><Td right>{""}</Td></tr>
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-dim">Scored against Sentinel-3 checks, not confirmed events. Only a named person can put a model live, in LEARN.</p>
    </div>
  );
}

function PerformanceWhy({ d }: { d: Summary["C_model_performance"] }) {
  return (
    <WhyButton title="How the model is scored">
      <div className="space-y-2 text-[12.5px] text-muted">
        <p>The question is triage: is this alert worth an analyst’s time? Scores are measured against Sentinel-3 checks, not against confirmed events.</p>
        <p>Simple rules: {d.production?.model ?? "n/a"}. New model: {d.candidate?.model ?? "n/a"}. The new model here is offline. It goes live only in LEARN, after the safety check, approved by a named person.</p>
        <p>The held-back test set is frozen and grouped by area and month, so cases from the same area and month stay together. Its fingerprint must not change, or the safety check fails.</p>
        <p>Likely range: a 95% confidence interval from a grouped bootstrap ({d.bootstrap?.auprc.n_boot ?? "n/a"} resamples). With this few labels, the ranges are wide.</p>
        <p>Detection score is AUPRC (0 to 1, higher is better). Ranking score is AUROC (0.5 is a coin flip). Overall is F1 at a 0.5 threshold. Correct alerts is precision and events caught is recall. Probability error is the Brier score and calibration error is ECE. For both, lower is better.</p>
        <p>Label weights: Sentinel-3 check 0.5, analyst 1.0, water sample 2.0.</p>
        <p>No concentration score (RMSE, MAE, R²) is shown, because no calibrated model exists yet (section B).</p>
      </div>
    </WhyButton>
  );
}

// --------------------------------------------------------------------------- D
function Ablation({ d }: { d: Summary["D_813_ablation"] }) {
  if (d.status) return <p className="text-muted">{d.status}</p>;
  const row = (regime: "hard" | "easy") => {
    const arms = d[regime]?.arms || {};
    return (["A", "B", "C"] as const).map((k) => ({ k, a: arms[ARM_KEY[k]] }));
  };
  const hardA = d.hard?.arms?.[ARM_KEY.A]?.confusion_matrix, hardB = d.hard?.arms?.[ARM_KEY.B]?.confusion_matrix;
  return (
    <div className="space-y-3">
      <div className="text-[12px] text-muted">Same real pixels, different bands: Sentinel-2 (A) vs simulated 813 (B, C).</div>
      <div className="grid gap-3 lg:grid-cols-2">
        {(["hard", "easy"] as const).map((regime) => (
          <div key={regime} className="rounded-md border border-edge bg-deep/40 p-3">
            <div className="hud-kicker" title={regime === "hard" ? "Operational boundary (hard regime) · spatially blocked CV" : "Gross plume (easy regime) · spatially blocked CV"}>{regime === "hard" ? "Plume edges (hard case)" : "Obvious plume (easy case)"} · {d[regime]?.n_samples?.toLocaleString()} test pixels</div>
            <table className="mt-1 w-full text-[12px]">
              <thead><tr className="border-b border-edge"><Th title="Test arm (band set)">Bands</Th><Th right title="F1: balance of correct alerts and pixels caught">Overall (F1)</Th><Th right title="Precision: share of flagged pixels that were anomalous">Correct alerts</Th><Th right title="Recall: share of anomalous pixels that were found">Caught</Th><Th right>False alarms</Th></tr></thead>
              <tbody>{row(regime).map(({ k, a }) => (
                <tr key={k} className="border-b border-edge/50"><Td><b>{k}</b> <span className="text-dim">{d.arms?.[k]}</span></Td><Td right mono>{n0(a?.f1, 4)}</Td><Td right mono>{n0(a?.precision, 4)}</Td><Td right mono>{n0(a?.recall, 4)}</Td><Td right mono>{a?.confusion_matrix?.fp ?? "n/a"}</Td></tr>))}</tbody>
            </table>
          </div>))}
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <Stat label="False alarms at plume edges, A → B" value={hardA && hardB ? `−${Math.round((1 - hardB.fp / hardA.fp) * 100)}%` : "n/a"} sub={hardA && hardB ? `${hardA.fp} → ${hardB.fp} (same pixels, same labels)` : ""} tone="text-nominal" />
        <Stat label="Gain on an obvious plume" value="none" sub="both band sets are already near perfect" tone="text-muted" />
        <Stat label="Concentration vs Sentinel-3" value={`R² ${n0(d.olci_regression?.targets?.CHL_NN_log10?.[ARM_KEY.A]?.r2, 2)} / ${n0(d.olci_regression?.targets?.CHL_NN_log10?.[ARM_KEY.B]?.r2, 2)}`} sub={`A / B, ${d.olci_regression?.n_matchups ?? "?"} matchups, ${n0(d.olci_regression?.dt_hours?.median, 1)} h time offset: not shown`} tone="text-critical" hint="R²: 1 is perfect, 0 is no skill. Target: Sentinel-3 chlorophyll (CHL_NN, log₁₀)." />
      </div>
      {d.simulator_validation && (
        <div className="rounded-md border border-edge bg-deep/40 p-3 text-[11.5px]">
          <div className="hud-kicker" title="Tanager convolved to Sentinel-2 bands vs a real Sentinel-2 scene">Is the simulator sound? Checked against a real Sentinel-2 image ({Math.abs(d.simulator_validation.time_offset_minutes).toFixed(0)} min apart)</div>
          <div className="mt-1 grid grid-cols-2 gap-3">
            {(["land", "water"] as const).map((s) => {
              const v = Object.values(d.simulator_validation![s]).map((b) => b.r2_1to1).filter((x): x is number => x != null);
              return <div key={s} title="Median 1:1 R² across bands"><b className="text-ink">{s === "land" ? "Land" : "Water"}</b>: agreement <span className="hud-value">{v.length ? v.sort((a, b) => a - b)[Math.floor(v.length / 2)].toFixed(2) : "n/a"}</span> (1 = perfect) · {d.simulator_validation!.interpretation?.[`${s}_reads_as`]?.split(". ")[0]}.</div>;
            })}
          </div>
        </div>)}
      <p className="text-[11px] text-dim">The answer key is a spectral anomaly score, not water samples. The scene is outside the UAE.</p>
    </div>
  );
}

function AblationWhy({ d }: { d: Summary["D_813_ablation"] }) {
  const sv = d.simulator_validation;
  return (
    <WhyButton title="How the 813 test works">
      <div className="space-y-2 text-[12.5px] text-muted">
        {d.scene && <p>Scene: {d.scene}.</p>}
        <p>Plume edges (hard case): can each band set draw the same working boundary as the full spectrum? This is the case that matters day to day. Obvious plume (easy case): a clear plume vs clearly normal water. It is a control. If both band sets ace it, obvious events do not need hyperspectral data.</p>
        {d.hard?.n_spatial_blocks != null && <p>Pixels are tested in {d.hard.n_spatial_blocks} separate map blocks of {d.hard.block_size_m} m (spatially blocked cross-validation).</p>}
        {d.olci_regression && <p>Concentration test: each band set predicts Sentinel-3 chlorophyll (CHL_NN, log₁₀) at {d.olci_regression.n_matchups} matched points. R² near zero means no skill.</p>}
        {sv && <p>Simulator check: {sv.question} Agreement is the median 1:1 R² across bands.</p>}
        {sv?.interpretation?.why_two_surfaces && <p>{sv.interpretation.why_two_surfaces}</p>}
        {sv?.interpretation?.land_reads_as && <p><b className="text-ink">Land.</b> {sv.interpretation.land_reads_as}</p>}
        {sv?.interpretation?.water_reads_as && <p><b className="text-ink">Water.</b> {sv.interpretation.water_reads_as}</p>}
        <p className="font-semibold text-ink">Caveats</p>
        <ul className="list-disc space-y-1 pl-5">{(d.caveats || []).map((c) => <li key={c}>{c}</li>)}<li>A UAE repeat needs the Tarif Tanager scene (download awaiting approval) and water-sample labels (not public).</li></ul>
      </div>
    </WhyButton>
  );
}

// --------------------------------------------------------------------------- E
function Holdout({ d }: { d: Summary["E_spatial_holdout"] }) {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="rounded-md border border-edge bg-deep/40 p-3">
        <div className="hud-kicker" title="Triage · leave-one-AOI-out">Each area scored by a model trained on the others</div>
        {d.triage_leave_one_aoi_out?.length ? (
          <table className="mt-1 w-full text-[12px]">
            <thead><tr className="border-b border-edge"><Th title="Held-out AOI">Test area</Th><Th right title="Test cases (positive cases)">Cases (pos.)</Th><Th right title="AUPRC: new model / simple rules">Detection: new / rules</Th><Th right title="AUROC: new model / simple rules">Ranking: new / rules</Th></tr></thead>
            <tbody>{d.triage_leave_one_aoi_out.map((r) => (
              <tr key={r.held_out_aoi} className="border-b border-edge/50"><Td>{r.held_out_aoi}</Td><Td right mono>{r.n_test} ({r.test_positive})</Td>
                {r.candidate ? <><Td right mono>{n0(r.candidate.auprc)} / {n0(r.production?.auprc)}</Td><Td right mono>{n0(r.candidate.auroc)} / {n0(r.production?.auroc)}</Td></> : <Td right className="text-dim" >{r.status}</Td>}</tr>))}</tbody>
          </table>) : <p className="text-muted">Needs labelled cases from at least two areas.</p>}
      </div>
      <div className="rounded-md border border-edge bg-deep/40 p-3">
        <div className="hud-kicker" title="Why spatial blocking: 813 ablation F1, blocked vs random split">Why we split by map blocks: 813 test F1, blocks vs random</div>
        {d.ablation_spatial_vs_random ? (
          <table className="mt-1 w-full text-[12px]">
            <thead><tr className="border-b border-edge"><Th title="Test arm (band set)">Bands</Th><Th right title="Spatially blocked split">Map blocks</Th><Th right>Random split</Th><Th right title="Optimism: random-split F1 minus map-block F1">Inflated by</Th></tr></thead>
            <tbody>{Object.entries(d.ablation_spatial_vs_random).map(([k, v]) => (
              <tr key={k} className="border-b border-edge/50"><Td>{k.replace(/_/g, " ")}</Td><Td right mono>{n0(v.spatial_blocked_f1, 4)}</Td><Td right mono>{n0(v.random_split_f1, 4)}</Td>
                <Td right mono className="text-caution">{v.spatial_blocked_f1 != null && v.random_split_f1 != null ? `+${(v.random_split_f1 - v.spatial_blocked_f1).toFixed(4)}` : "n/a"}</Td></tr>))}</tbody>
          </table>) : <p className="text-muted">n/a</p>}
        <p className="mt-2 text-[11px] text-dim">Neighbouring pixels are near-copies, so a random split flatters every model. All 813 test numbers use map blocks.</p>
      </div>
    </div>
  );
}

function HoldoutWhy() {
  return (
    <WhyButton title="How unseen areas are tested">
      <div className="space-y-2 text-[12.5px] text-muted">
        <p>Leave-one-area-out: for each monitored area, the model trains on all the other areas and is tested on that one. An area is skipped when training or test lacks positive or negative cases.</p>
        <p>Detection is AUPRC and ranking is AUROC. “Rules” is the simple rule baseline. Labels are Sentinel-3 checks, not confirmed events.</p>
        <p>Map blocks: neighbouring pixels are near-duplicates. A random split puts them in both training and test, which flatters every model. “Inflated by” is the random-split F1 minus the map-block F1.</p>
      </div>
    </WhyButton>
  );
}

// --------------------------------------------------------------------------- F
function Negative({ d }: { d: Summary["F_negative_control"] }) {
  const a = d.annaba;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {a ? (
        <div className="rounded-md border border-nominal/40 bg-nominal/5 p-3">
          <div className="flex items-center justify-between"><div className="hud-kicker">Case B · Gulf of Annaba (Algeria)</div><Chip label="DISMISSED" color="#23D484" /></div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Stat label="Vs the rest of the image" value={a.rx_percentile != null ? `${a.rx_percentile.toFixed(1)}th` : "n/a"} sub="percentile · looks unusual" tone="text-caution" hint="Spatial view: RX spectral anomaly score, as a percentile within the scene" />
            <Stat label="Vs past years, same season" value={fmt.ord(a.seasonal_percentile)} sub={`percentile of ${a.n_seasonal} same-season images · normal`} tone="text-nominal" hint="Temporal view: seasonal percentile" />
          </div>
          <p className="mt-2 text-[12px] text-muted">Odd in the image, but normal for this place and season. It is a lasting coastal feature, so the alert is dismissed.</p>
          <Link href={`/incident?id=${a.id}`} className="mt-1 inline-block text-[12px] text-cyan hover:underline">Open {a.id} →</Link>
        </div>) : <p className="text-muted">The known false-alarm case is not in this workspace.</p>}
      <div className="rounded-md border border-edge bg-deep/40 p-3">
        <div className="hud-kicker">UAE alerts that Sentinel-3 did not confirm</div>
        {d.cross_sensor_rejections ? <>
          <div className="hud-value text-[26px] font-bold text-violet">{d.cross_sensor_rejections.n} <span className="text-[13px] text-muted">of {d.cross_sensor_rejections.of} checked alerts</span></div>
          <table className="mt-1 w-full text-[11.5px]">
            <thead><tr className="border-b border-edge"><Th>Alert</Th><Th right>Size</Th><Th right title="S2 z: robust z-score vs the seasonal normal">Sentinel-2 score</Th><Th right title="OLCI median inside the alert / in the water around it">Sentinel-3 patch / around</Th></tr></thead>
            <tbody>{d.cross_sensor_rejections.largest.map((r) => (
              <tr key={`${r.aoi}${r.date}${r.area_km2}`} className="border-b border-edge/50"><Td>{r.aoi} {r.date} <span className="text-dim">{r.hypothesis.replace(/_/g, " ")}</span></Td><Td right mono>{n0(r.area_km2, 1)} km²</Td><Td right mono>{n0(r.s2_z, 1)}</Td><Td right mono>{r.olci.region_median.toFixed(2)} / {r.olci.background_median.toFixed(2)} {r.olci.units}</Td></tr>))}</tbody>
          </table>
          <p className="mt-2 text-[11px] text-dim">Big Sentinel-2 alerts that Sentinel-3 saw as normal water that morning should be rejected. Each becomes a label, and LEARN checks that new models learn from them.</p>
        </> : <p className="text-muted">No Sentinel-3 checks yet.</p>}
      </div>
    </div>
  );
}

function NegativeWhy({ d }: { d: Summary["F_negative_control"] }) {
  const a = d.annaba;
  return (
    <WhyButton title="How false alarms are caught">
      <div className="space-y-2 text-[12.5px] text-muted">
        {a && <p><b className="text-ink">Annaba.</b> {a.reading}</p>}
        <p>Vs the rest of the image: the RX spectral anomaly score, ranked within the scene. Vs past years: the seasonal percentile against images from the same season at the same place.</p>
        <p>Sentinel-3 rejections: alerts where Sentinel-3 saw ordinary water the same morning. The Sentinel-2 score is a robust z-score against the seasonal normal. The Sentinel-3 columns show the median inside the alert and in the water around it.</p>
        <p>A large, high-z Sentinel-2 anomaly that Sentinel-3 sees as ordinary water is exactly the case an analyst should reject. Each rejection becomes a label, and LEARN tests whether a new model learns them.</p>
      </div>
    </WhyButton>
  );
}

/** One-line takeaways that follow the data: if a result changes, the headline does too. */
function headlines(d: Summary): Record<string, string> {
  const nSamples = d.B_matchups.in_situ.n_matchups;
  const c = d.C_model_performance;
  const cand = c.candidate?.metrics?.auprc, rule = c.production?.metrics.auprc;
  const fp = (k: string) => d.D_813_ablation.hard?.arms?.[ARM_KEY[k]]?.confusion_matrix?.fp;
  const fpA = fp("A"), fpB = fp("B");
  const loao = (d.E_spatial_holdout.triage_leave_one_aoi_out || []).filter((r) => r.candidate?.auprc != null && r.production?.auprc != null);
  const wins = loao.filter((r) => (r.candidate!.auprc as number) > (r.production!.auprc as number)).length;
  const an = d.F_negative_control.annaba;
  return {
    A: "Images are cleaned and checked before use",
    B: nSamples === 0 ? "No water samples yet, so values stay indices" : `${nSamples} water samples matched to images`,
    C: cand == null || rule == null ? "Not enough labels to score a new model yet"
      : cand > rule ? "New model ranks alerts better than simple rules" : "New model does not beat the simple rules yet",
    D: fpA == null || fpB == null ? "813 test not run yet"
      : fpB < fpA ? "Simulated 813 cuts false alarms at plume edges" : "Simulated 813 shows no clear gain here",
    E: !loao.length ? "Not enough areas to test unseen areas yet"
      : wins === loao.length ? "New model beats the rules in every unseen area"
      : wins > loao.length / 2 ? "New model beats the rules in most unseen areas" : "Mixed results in unseen areas",
    F: !an ? "No false-alarm test case loaded"
      : (an.seasonal_percentile ?? 100) <= 50 ? "A known false alarm is correctly dismissed" : "Check the false-alarm test case",
  };
}

export default function ValidationPage() {
  const q = useStatic<Summary>("validation/validation_summary.json");
  const live = useEngineQuery((e) => e.models("triage").then((ms) => ms.find((m) => m.status === "PRODUCTION") || null));
  // One section at a time (A to F work as tabs), so the page fits the screen.
  const [open, setOpen] = useState<string>("A");
  const d = q.data;
  const status = useMemo(() => {
    if (!d) return {} as Record<string, React.ReactNode>;
    const c = d.C_model_performance;
    return {
      A: `${d.A_data_quality.aois.reduce((s, a) => s + a.n_ok, 0).toLocaleString()} images`,
      B: `${d.B_matchups.in_situ.n_matchups} samples · ${d.B_matchups.cross_sensor.n} Sentinel-3 checks`,
      C: c.production ? `Score ${n0(c.production.metrics.auprc, 2)} → ${n0(c.candidate?.metrics?.auprc, 2)}` : "no labels yet",
      D: "813 simulated",
      E: `${d.E_spatial_holdout.triage_leave_one_aoi_out?.length || 0} areas held back`,
      F: d.F_negative_control.annaba ? ((d.F_negative_control.annaba.seasonal_percentile ?? 100) <= 50 ? "false alarm dismissed" : "check this case") : "n/a",
    } as Record<string, React.ReactNode>;
  }, [d]);
  if (q.error) return <div className="p-6 text-critical">Evidence summary missing. Run scripts/build_validation.py ({String(q.error)})</div>;
  if (!d) return <div className="p-6 text-muted">Loading the evidence…</div>;
  const show = (k: string) => open === "all" || open === k;
  const H = headlines(d);
  return (
    <div className="p-3 short:p-2 lg:flex lg:h-full lg:min-h-0 lg:flex-col">
      <div className="mb-3 flex shrink-0 flex-wrap items-center gap-2 short:mb-2">
        <div className="mr-2">
          <div className="hud-kicker">Validation · updated {fmt.utc(d.generated_utc)}</div>
          <h1 className="font-display text-[22px] font-bold tracking-wide">What the evidence shows, and what it doesn’t yet</h1>
        </div>
        <WhyButton title="How to read this page">
          <div className="space-y-2 text-[12.5px] text-muted">
            <p>Each section answers one question to ask before trusting an alert. The headline is the short answer. Open Why? on a section for the method and the caveats.</p>
            <ul className="list-disc space-y-1 pl-5">
              <li><b className="text-ink">A.</b> Is the satellite data good enough to use?</li>
              <li><b className="text-ink">B.</b> Has anything independent checked it?</li>
              <li><b className="text-ink">C.</b> Does the model sort alerts well?</li>
              <li><b className="text-ink">D.</b> What would Satellite 813 add? (simulated)</li>
              <li><b className="text-ink">E.</b> Does it work on areas it never saw?</li>
              <li><b className="text-ink">F.</b> Does it dismiss a known false alarm?</li>
            </ul>
            <p>Scores appear only where they mean something. Alert scores (classification) use a frozen, grouped, held-back test set. Concentration scores (regression) need a calibrated model, and none exists yet.</p>
            <p>Every number is rebuilt from pipeline outputs by scripts/build_validation.py. A missing number means that analysis has not run. No number is filled in by hand.</p>
          </div>
        </WhyButton>
      </div>
      <div className="mb-3 grid shrink-0 grid-cols-2 gap-2 short:mb-2 md:grid-cols-3 xl:grid-cols-6" role="tablist" aria-label="Evidence sections">
        {SECTIONS.map((s) => (
          <button key={s.key} role="tab" aria-selected={open === s.key} onClick={() => setOpen(s.key)} className={`panel-flat flex items-center gap-2 px-3 py-2 text-left ${open === s.key ? "border-beam bg-beam/10" : "hover:border-line"}`}>
            <span className="grid h-7 w-7 place-items-center rounded-md bg-beam/15 font-display font-bold text-beam2">{s.key}</span>
            <span className="min-w-0"><span className="flex items-center gap-1 text-[12px] font-bold tracking-wide">{s.icon}{s.title}</span><span className="block truncate text-[11px] text-muted">{status[s.key]}</span></span>
          </button>))}
      </div>
      <div className="space-y-3 lg:min-h-0 lg:flex-1 lg:[&>section]:h-full">
        {show("A") && <Panel kicker="A · Data quality" title={H.A} right={<span className="flex shrink-0 items-center gap-3"><DataQualityWhy d={d.A_data_quality} /><CheckCircle2 size={16} className="text-nominal" /></span>} bodyClass="scroll-quiet p-3 lg:overflow-y-auto"><DataQuality d={d.A_data_quality} /></Panel>}
        {show("B") && <Panel kicker="B · Independent checks" title={H.B} right={<span className="flex shrink-0 items-center gap-3"><MatchupsWhy d={d.B_matchups} /><AlertTriangle size={16} className="text-critical" /></span>} bodyClass="scroll-quiet p-3 lg:overflow-y-auto"><Matchups d={d.B_matchups} /></Panel>}
        {show("C") && <Panel kicker="C · Model performance" title={H.C} right={<span className="flex shrink-0 items-center gap-3"><PerformanceWhy d={d.C_model_performance} /></span>} bodyClass="scroll-quiet p-3 lg:overflow-y-auto"><Performance d={d.C_model_performance} live={live.data} /></Panel>}
        {show("D") && <Panel kicker="D · What 813 adds" title={H.D} right={<span className="flex shrink-0 items-center gap-3"><AblationWhy d={d.D_813_ablation} /><SimBadge /></span>} bodyClass="scroll-quiet p-3 lg:overflow-y-auto"><Ablation d={d.D_813_ablation} /></Panel>}
        {show("E") && <Panel kicker="E · Unseen areas" title={H.E} right={<span className="flex shrink-0 items-center gap-3"><HoldoutWhy /></span>} bodyClass="scroll-quiet p-3 lg:overflow-y-auto"><Holdout d={d.E_spatial_holdout} /></Panel>}
        {show("F") && <Panel kicker="F · False-alarm test" title={H.F} right={<span className="flex shrink-0 items-center gap-3"><NegativeWhy d={d.F_negative_control} /><CircleSlash size={16} className="text-nominal" /></span>} bodyClass="scroll-quiet p-3 lg:overflow-y-auto"><Negative d={d.F_negative_control} /></Panel>}
      </div>
    </div>
  );
}
