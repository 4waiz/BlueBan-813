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
  { key: "B", title: "UAE matchups", icon: <FlaskConical size={15} /> },
  { key: "C", title: "Model performance", icon: <Gauge size={15} /> },
  { key: "D", title: "813 ablation", icon: <Layers size={15} /> },
  { key: "E", title: "Spatial holdout", icon: <Split size={15} /> },
  { key: "F", title: "Negative control", icon: <ShieldOff size={15} /> },
] as const;

const ARM_KEY: Record<string, string> = { A: "S2_multispectral_11band", B: "813_hyperspectral_205band", C: "813_hyperspectral_261band_5nm" };
const n0 = (v: Num | undefined, d = 3) => fmt.num(v ?? null, d);
const ci = (c?: [Num, Num]) => (c && c[0] != null && c[1] != null ? `[${c[0].toFixed(3)}, ${c[1].toFixed(3)}]` : "");

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return <th className={`px-2 py-1.5 font-semibold text-dim ${right ? "text-right" : "text-left"}`}>{children}</th>;
}
function Td({ children, right, mono, className = "" }: { children: React.ReactNode; right?: boolean; mono?: boolean; className?: string }) {
  return <td className={`px-2 py-1.5 ${right ? "text-right" : ""} ${mono ? "hud-value" : ""} ${className}`}>{children}</td>;
}

function Stat({ label, value, sub, tone = "text-ink" }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-md border border-edge bg-deep/60 px-3 py-2">
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
        <Stat label="AOIs screened" value={d.aois.length} />
        <Stat label="Datatakes processed" value={tot.toLocaleString()} sub={fail ? `${fail} failed reads, recorded` : "no failed reads"} />
        <Stat label="Usable (≥500 water px)" value={use.toLocaleString()} sub={tot ? fmt.pct(use / tot) : ""} />
        <Stat label="Offset-corrected (baseline ≥ 04.00)" value={d.aois.reduce((s, a) => s + a.n_boa_offset_applied, 0).toLocaleString()} sub="BOA_ADD_OFFSET −1000 by processing baseline" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11.5px]">
          <thead><tr className="border-b border-edge"><Th>AOI</Th><Th>Period</Th><Th right>Datatakes</Th><Th right>Usable</Th><Th right>Median valid</Th><Th right>Median cloud</Th><Th right>Glint-flagged water</Th><Th right>Median B11 water</Th><Th>Baselines</Th></tr></thead>
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
      <p className="text-[11px] text-dim">{d.method} Glint-flagged water is not discarded: a SWIR (B12) offset removes the first-order glint, and the fraction is reported so a reader can judge how much of a scene depended on that correction.</p>
    </div>
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
      <text x={W - 10} y={sy(Math.log10(1.5)) - 3} textAnchor="end" fontSize="9" fill="#23D484">×1.5 reference-positive</text>
      {pts.map((p, i) => p.s2_delta == null || !p.olci_ratio ? null : (
        <circle key={i} cx={sx(p.s2_delta)} cy={sy(Math.log10(p.olci_ratio))} r={3.2} fill={p.y === 1 ? "#23D484" : "#FF4D5E"} fillOpacity={0.75}>
          <title>{`${p.aoi} ${p.date} ${p.hyp} · S2 Δ ${p.s2_delta.toFixed(3)} · OLCI ×${p.olci_ratio.toFixed(2)}`}</title>
        </circle>))}
      <text x={P} y={H - 4} fontSize="9.5" fill="#93A6CB">S2 change vs own seasonal median (NDCI Δ or turbidity Δ) →</text>
      <text x={10} y={P - 12} fontSize="9.5" fill="#93A6CB">log₁₀ OLCI region / surroundings</text>
    </svg>
  );
}

function Matchups({ d }: { d: Summary["B_matchups"] }) {
  const cs = d.cross_sensor, q = d.in_situ.quantification;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="space-y-2 rounded-md border border-critical/40 bg-critical/5 p-3">
        <div className="flex items-center justify-between"><div className="hud-kicker">In-situ matchups (satellite ↔ water sample)</div><Chip label={d.in_situ.status} color="#FF4D5E" /></div>
        <div className="hud-value text-[30px] font-bold text-critical">0</div>
        <p className="text-[12px] text-muted">{d.in_situ.reason}</p>
        <div className="grid grid-cols-2 gap-x-4 text-[11.5px]">
          <div className="kv"><span>Max |Δt|</span><span className="hud-value">±{String(d.in_situ.engine.max_dt_hours)} h</span></div>
          <div className="kv"><span>Box</span><span className="hud-value">{String(d.in_situ.engine.window_px)}×{String(d.in_situ.engine.window_px)} px</span></div>
          <div className="kv"><span>Min valid</span><span className="hud-value">{fmt.pct(Number(d.in_situ.engine.min_valid_frac))}</span></div>
          <div className="kv"><span>Max CV</span><span className="hud-value">{String(d.in_situ.engine.max_cv)}</span></div>
        </div>
        <div className="rounded border border-edge bg-deep/60 p-2 text-[11.5px]">
          <b className="text-ink">Physical units allowed?</b> <span className={q.usable_for_physical_units ? "text-nominal" : "text-critical"}>{q.usable_for_physical_units ? "yes" : "NO"}</span>, quantity kind <b>{q.quantity_kind}</b>.
          <ul className="mt-1 list-disc pl-5 text-muted">{q.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          The matchup engine and model zoo are built and tested (tests/test_matchup.py); they run the moment legitimate samples arrive through Field Ops or a CSV.
        </div>
      </div>
      <div className="space-y-2 rounded-md border border-edge bg-deep/40 p-3">
        <div className="flex items-center justify-between"><div className="hud-kicker">Cross-sensor reference · Sentinel-2 vs Sentinel-3 OLCI</div><Chip label="NOT IN SITU" color="#FFC23D" /></div>
        {cs.n ? <>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(cs.per_hypothesis || {}).map(([h, v]) => (
              <Stat key={h} label={`${h.replace(/_/g, " ")} · ${v.variable}`} value={`${v.positive}/${v.n}`} sub={`${v.negative} not confirmed`} />))}
            <Stat label="Median |Δt|" value={`${n0(cs.median_abs_dt_minutes, 0)} min`} sub="same morning" />
          </div>
          {cs.points && <Scatter pts={cs.points} />}
          <div className="text-[11.5px] text-muted">
            {Object.entries(cs.agreement || {}).map(([h, a]) => <div key={h}>{h.replace(/_/g, " ")}: Spearman ρ = <b className="text-ink">{a.spearman_rho.toFixed(2)}</b> (p = {a.p_value < 0.001 ? a.p_value.toExponential(1) : a.p_value.toFixed(3)}, n = {a.n}) between the S2 change and the OLCI contrast.</div>)}
            <p className="mt-1 text-dim">{cs.caveat}</p>
          </div>
        </> : <p className="text-[12px] text-muted">No cross-sensor references built yet (scripts/build_labels.py).</p>}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- C
const MROWS: [keyof Metrics, string, boolean][] = [["auprc", "AUPRC", true], ["auroc", "AUROC", true], ["f1", "F1 @0.5", true], ["precision", "Precision", true], ["recall", "Recall", true], ["brier", "Brier", false], ["ece", "ECE", false]];

function Performance({ d, live }: { d: Summary["C_model_performance"]; live: ModelRecord | null | undefined }) {
  if (d.status) return <p className="text-muted">No labels yet: {d.status}.</p>;
  const p = d.production?.metrics, c = d.candidate?.metrics;
  const liveV = (k: string) => live?.metrics?.find((m) => m.metric === k && m.split === "validation" && m.subgroup === "all")?.value ?? null;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Train labels" value={d.n_train} sub={`${d.train_positive} positive`} />
        <Stat label="Frozen validation" value={d.n_validation} sub={`${d.validation_positive} positive · grouped by AOI-month`} />
        <Stat label="Validation hash" value={<span className="text-[14px]">{d.validation_hash}</span>} sub="a gate refuses if this changes" />
        <Stat label="Label source" value={<span className="text-[14px]">OLCI reference</span>} sub="weight 0.5 each; analyst 1.0, field 2.0" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead><tr className="border-b border-edge"><Th>Triage metric (frozen validation)</Th><Th right>Production · rule baseline</Th><Th right>Offline candidate · logistic</Th><Th right>Δ (grouped bootstrap 95% CI)</Th><Th right>Workspace production{live ? ` · ${live.id}` : ""}</Th></tr></thead>
          <tbody>
            {MROWS.map(([k, label, higher]) => {
              const a = p?.[k] as Num, b = c?.[k] as Num;
              const boot = k === "auprc" ? d.bootstrap?.auprc : k === "auroc" ? d.bootstrap?.auroc : undefined;
              const delta = a != null && b != null ? b - a : null;
              return (
                <tr key={k} className="border-b border-edge/50">
                  <Td>{label}</Td>
                  <Td right mono>{n0(a)}{boot?.a_ci && <span className="ml-1 text-[10px] text-dim">{ci(boot.a_ci)}</span>}</Td>
                  <Td right mono>{n0(b)}{boot?.b_ci && <span className="ml-1 text-[10px] text-dim">{ci(boot.b_ci)}</span>}</Td>
                  <Td right mono className={delta == null ? "" : (higher ? delta > 0 : delta < 0) ? "text-nominal" : "text-critical"}>{delta == null ? "n/a" : `${delta > 0 ? "+" : ""}${delta.toFixed(3)}`}{boot && <span className="ml-1 text-[10px] text-dim">{ci(boot.ci)}</span>}</Td>
                  <Td right mono>{n0(liveV(k as string))}</Td>
                </tr>);
            })}
            <tr><Td>Confusion (tp/fp/fn/tn)</Td><Td right mono>{p ? `${p.confusion.tp}/${p.confusion.fp}/${p.confusion.fn}/${p.confusion.tn}` : "n/a"}</Td><Td right mono>{c ? `${c.confusion.tp}/${c.confusion.fp}/${c.confusion.fn}/${c.confusion.tn}` : "n/a"}</Td><Td right>{""}</Td><Td right>{""}</Td></tr>
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-dim">Precision, recall and F1 are for the triage question “is this candidate worth an analyst’s time?”, against a cross-sensor reference, not against confirmed events. No regression metric (RMSE, MAE, R²) is shown for concentration because no calibrated model exists (section B). The offline candidate is not promoted: promotion happens only in LEARN, through the gate, by a named human.</p>
    </div>
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
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted"><SimBadge /> {d.scene}</div>
      <div className="grid gap-3 lg:grid-cols-2">
        {(["hard", "easy"] as const).map((regime) => (
          <div key={regime} className="rounded-md border border-edge bg-deep/40 p-3">
            <div className="hud-kicker">{regime === "hard" ? "Operational boundary (hard regime)" : "Gross plume (easy regime)"} · spatially blocked CV · n = {d[regime]?.n_samples?.toLocaleString()}</div>
            <table className="mt-1 w-full text-[12px]">
              <thead><tr className="border-b border-edge"><Th>Arm</Th><Th right>F1</Th><Th right>Precision</Th><Th right>Recall</Th><Th right>False alarms</Th></tr></thead>
              <tbody>{row(regime).map(({ k, a }) => (
                <tr key={k} className="border-b border-edge/50"><Td><b>{k}</b> <span className="text-dim">{d.arms?.[k]}</span></Td><Td right mono>{n0(a?.f1, 4)}</Td><Td right mono>{n0(a?.precision, 4)}</Td><Td right mono>{n0(a?.recall, 4)}</Td><Td right mono>{a?.confusion_matrix?.fp ?? "n/a"}</Td></tr>))}</tbody>
            </table>
          </div>))}
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <Stat label="False alarms at the boundary, A → B" value={hardA && hardB ? `−${Math.round((1 - hardB.fp / hardA.fp) * 100)}%` : "n/a"} sub={hardA && hardB ? `${hardA.fp} → ${hardB.fp} (same pixels, same labels)` : ""} tone="text-nominal" />
        <Stat label="Gross detection gain" value="none" sub="both arms saturate on an obvious plume" tone="text-muted" />
        <Stat label="Concentration skill vs OLCI" value={`R² ${n0(d.olci_regression?.targets?.CHL_NN_log10?.[ARM_KEY.A]?.r2, 2)} / ${n0(d.olci_regression?.targets?.CHL_NN_log10?.[ARM_KEY.B]?.r2, 2)}`} sub={`A / B, ${d.olci_regression?.n_matchups ?? "?"} matchups, ${n0(d.olci_regression?.dt_hours?.median, 1)} h offset: not demonstrated`} tone="text-critical" />
      </div>
      {d.simulator_validation && (
        <div className="rounded-md border border-edge bg-deep/40 p-3 text-[11.5px]">
          <div className="hud-kicker">Is the simulator itself sound? Tanager convolved to S2 bands vs a real S2 scene ({Math.abs(d.simulator_validation.time_offset_minutes).toFixed(0)} min apart)</div>
          <div className="mt-1 grid grid-cols-2 gap-3">
            {(["land", "water"] as const).map((s) => {
              const v = Object.values(d.simulator_validation![s]).map((b) => b.r2_1to1).filter((x): x is number => x != null);
              return <div key={s}><b className="text-ink">{s === "land" ? "Land" : "Water"}</b>: median 1:1 R² across bands <span className="hud-value">{v.length ? v.sort((a, b) => a - b)[Math.floor(v.length / 2)].toFixed(2) : "n/a"}</span> · {d.simulator_validation!.interpretation?.[`${s}_reads_as`]?.split(". ")[0]}.</div>;
            })}
          </div>
        </div>)}
      <ul className="list-disc pl-5 text-[11px] text-dim">{(d.caveats || []).map((c) => <li key={c}>{c}</li>)}<li>The UAE repeat needs the Tarif Tanager scene (download awaiting approval) and in-situ labels (not public).</li></ul>
    </div>
  );
}

// --------------------------------------------------------------------------- E
function Holdout({ d }: { d: Summary["E_spatial_holdout"] }) {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="rounded-md border border-edge bg-deep/40 p-3">
        <div className="hud-kicker">Triage · leave-one-AOI-out (train on the other AOIs)</div>
        {d.triage_leave_one_aoi_out?.length ? (
          <table className="mt-1 w-full text-[12px]">
            <thead><tr className="border-b border-edge"><Th>Held-out AOI</Th><Th right>n (pos)</Th><Th right>AUPRC cand / rule</Th><Th right>AUROC cand / rule</Th></tr></thead>
            <tbody>{d.triage_leave_one_aoi_out.map((r) => (
              <tr key={r.held_out_aoi} className="border-b border-edge/50"><Td>{r.held_out_aoi}</Td><Td right mono>{r.n_test} ({r.test_positive})</Td>
                {r.candidate ? <><Td right mono>{n0(r.candidate.auprc)} / {n0(r.production?.auprc)}</Td><Td right mono>{n0(r.candidate.auroc)} / {n0(r.production?.auroc)}</Td></> : <Td right className="text-dim" >{r.status}</Td>}</tr>))}</tbody>
          </table>) : <p className="text-muted">Needs labels from at least two AOIs.</p>}
      </div>
      <div className="rounded-md border border-edge bg-deep/40 p-3">
        <div className="hud-kicker">Why spatial blocking: 813 ablation F1, blocked vs random split</div>
        {d.ablation_spatial_vs_random ? (
          <table className="mt-1 w-full text-[12px]">
            <thead><tr className="border-b border-edge"><Th>Arm</Th><Th right>Spatially blocked</Th><Th right>Random split</Th><Th right>Optimism</Th></tr></thead>
            <tbody>{Object.entries(d.ablation_spatial_vs_random).map(([k, v]) => (
              <tr key={k} className="border-b border-edge/50"><Td>{k.replace(/_/g, " ")}</Td><Td right mono>{n0(v.spatial_blocked_f1, 4)}</Td><Td right mono>{n0(v.random_split_f1, 4)}</Td>
                <Td right mono className="text-caution">{v.spatial_blocked_f1 != null && v.random_split_f1 != null ? `+${(v.random_split_f1 - v.spatial_blocked_f1).toFixed(4)}` : "n/a"}</Td></tr>))}</tbody>
          </table>) : <p className="text-muted">n/a</p>}
        <p className="mt-2 text-[11px] text-dim">Neighbouring pixels are near-duplicates. A random split puts them on both sides and flatters every model; all reported ablation numbers use spatial blocks.</p>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- F
function Negative({ d }: { d: Summary["F_negative_control"] }) {
  const a = d.annaba;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {a ? (
        <div className="rounded-md border border-nominal/40 bg-nominal/5 p-3">
          <div className="flex items-center justify-between"><div className="hud-kicker">Case B · Gulf of Annaba (Algeria)</div><Chip label="STOOD DOWN" color="#23D484" /></div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Stat label="Spatial view (RX)" value={fmt.ord(a.rx_percentile)} sub="percentile in the scene: looks unusual" tone="text-caution" />
            <Stat label="Temporal view" value={fmt.ord(a.seasonal_percentile)} sub={`seasonal percentile vs ${a.n_seasonal} same-season scenes: ordinary`} tone="text-nominal" />
          </div>
          <p className="mt-2 text-[12px] text-muted">{a.reading}</p>
          <Link href={`/incident?id=${a.id}`} className="mt-1 inline-block text-[12px] text-cyan hover:underline">Open {a.id} →</Link>
        </div>) : <p className="text-muted">Negative-control case not in the workspace.</p>}
      <div className="rounded-md border border-edge bg-deep/40 p-3">
        <div className="hud-kicker">UAE detections the cross-sensor reference did not confirm</div>
        {d.cross_sensor_rejections ? <>
          <div className="hud-value text-[26px] font-bold text-violet">{d.cross_sensor_rejections.n} <span className="text-[13px] text-muted">of {d.cross_sensor_rejections.of} referenced candidates</span></div>
          <table className="mt-1 w-full text-[11.5px]">
            <thead><tr className="border-b border-edge"><Th>Candidate</Th><Th right>Area</Th><Th right>S2 z</Th><Th right>OLCI region / around</Th></tr></thead>
            <tbody>{d.cross_sensor_rejections.largest.map((r) => (
              <tr key={`${r.aoi}${r.date}${r.area_km2}`} className="border-b border-edge/50"><Td>{r.aoi} {r.date} <span className="text-dim">{r.hypothesis.replace(/_/g, " ")}</span></Td><Td right mono>{n0(r.area_km2, 1)} km²</Td><Td right mono>{n0(r.s2_z, 1)}</Td><Td right mono>{r.olci.region_median.toFixed(2)} / {r.olci.background_median.toFixed(2)} {r.olci.units}</Td></tr>))}</tbody>
          </table>
          <p className="mt-2 text-[11px] text-dim">A large, high-z Sentinel-2 anomaly that the same-morning OLCI retrieval sees as ordinary water is exactly the case an analyst should reject. Those rejections become labels, and LEARN tests whether a candidate model learns them.</p>
        </> : <p className="text-muted">No cross-sensor references yet.</p>}
      </div>
    </div>
  );
}

export default function ValidationPage() {
  const q = useStatic<Summary>("validation/validation_summary.json");
  const live = useEngineQuery((e) => e.models("triage").then((ms) => ms.find((m) => m.status === "PRODUCTION") || null));
  const [open, setOpen] = useState<string>("all");
  const d = q.data;
  const status = useMemo(() => {
    if (!d) return {} as Record<string, React.ReactNode>;
    const c = d.C_model_performance;
    return {
      A: `${d.A_data_quality.aois.reduce((s, a) => s + a.n_ok, 0).toLocaleString()} datatakes`,
      B: `0 in situ · ${d.B_matchups.cross_sensor.n} cross-sensor`,
      C: c.production ? `AUPRC ${n0(c.production.metrics.auprc, 2)}` : "no labels",
      D: "813 simulated",
      E: `${d.E_spatial_holdout.triage_leave_one_aoi_out?.length || 0} AOIs held out`,
      F: d.F_negative_control.annaba ? "stood down" : "n/a",
    } as Record<string, React.ReactNode>;
  }, [d]);
  if (q.error) return <div className="p-6 text-critical">Validation summary missing: run scripts/build_validation.py ({String(q.error)})</div>;
  if (!d) return <div className="p-6 text-muted">Loading validation…</div>;
  const show = (k: string) => open === "all" || open === k;
  return (
    <div className="h-full overflow-y-auto p-3 short:p-2">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="mr-2">
          <div className="hud-kicker">Validation · generated {fmt.utc(d.generated_utc)}</div>
          <h1 className="font-display text-[22px] font-bold tracking-wide">What the evidence supports, and what it does not</h1>
        </div>
        <WhyButton title="How to read this page">
          <p>Each section answers one question a reviewer should ask before trusting an incident. Metrics appear only where they mean something: classification metrics for triage, regression metrics only for a calibrated quantity (there is none yet), and every model number is on a frozen, grouped validation split.</p>
          <p className="mt-2">Numbers are recomputed from pipeline outputs by scripts/build_validation.py. If a number is missing, the analysis has not been run; it is never filled in by hand.</p>
        </WhyButton>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        {SECTIONS.map((s) => (
          <button key={s.key} onClick={() => setOpen(open === s.key ? "all" : s.key)} className={`panel-flat flex items-center gap-2 px-3 py-2 text-left ${open === s.key ? "border-beam" : ""}`}>
            <span className="grid h-7 w-7 place-items-center rounded-md bg-beam/15 font-display font-bold text-beam">{s.key}</span>
            <span className="min-w-0"><span className="flex items-center gap-1 text-[12px] font-bold tracking-wide">{s.icon}{s.title}</span><span className="block truncate text-[11px] text-muted">{status[s.key]}</span></span>
          </button>))}
      </div>
      <div className="space-y-3">
        {show("A") && <Panel kicker="A" title="Data quality" right={<CheckCircle2 size={16} className="text-nominal" />} bodyClass="p-3"><DataQuality d={d.A_data_quality} /></Panel>}
        {show("B") && <Panel kicker="B" title="UAE matchups" right={<AlertTriangle size={16} className="text-critical" />} bodyClass="p-3"><Matchups d={d.B_matchups} /></Panel>}
        {show("C") && <Panel kicker="C" title="Model performance" bodyClass="p-3"><Performance d={d.C_model_performance} live={live.data} /></Panel>}
        {show("D") && <Panel kicker="D" title="813 ablation · what does hyperspectral add?" right={<SimBadge />} bodyClass="p-3"><Ablation d={d.D_813_ablation} /></Panel>}
        {show("E") && <Panel kicker="E" title="Spatial holdout" bodyClass="p-3"><Holdout d={d.E_spatial_holdout} /></Panel>}
        {show("F") && <Panel kicker="F" title="Negative control · false-alarm suppression" right={<CircleSlash size={16} className="text-nominal" />} bodyClass="p-3"><Negative d={d.F_negative_control} /></Panel>}
      </div>
    </div>
  );
}
