/**
 * LEARN in the browser: a faithful port of pipeline/learning.py.
 *
 * The hosted deployment has no Python, so the workspace engine trains and
 * gates candidates here. The objective is exactly scikit-learn's L2 logistic
 * regression (0.5 * ||w||^2 + C * sum_i s_i * logloss_i, intercept not
 * penalised), solved by Newton-IRLS, so a candidate trained here matches one
 * trained by the Python backend on the same labels to numerical precision.
 * The artifact format (scaler + coefficients as JSON) is shared.
 */
import type { GateCheck, GateReport, LabelRow, ModelArtifact } from "./engine/types";

export const TRIAGE_FEATURES = [
  "seasonal_pct_primary", "robust_z_primary", "rx_pct", "log10_area_km2",
  "persistence_frac", "dist_shore_km", "ndci_delta", "mci_delta", "tur_delta",
  "fai_mean", "hue_delta_deg", "cloud_adjacent_frac", "valid_frac_aoi",
];

export type Matrix = number[][];

export function toMatrix(labels: LabelRow[], features: string[]) {
  const X: Matrix = labels.map((l) => features.map((f) => num(l.features?.[f])));
  const y = labels.map((l) => num(l.target?.y));
  const w = labels.map((l) => (Number.isFinite(l.weight) ? l.weight : 1));
  const groups = labels.map((l) => l.group_key || l.id);
  const subgroups = labels.map((l) => l.aoi_id || "unknown");
  return { X, y, w, groups, subgroups };
}

function num(v: unknown): number {
  const n = typeof v === "number" ? v : v == null ? NaN : Number(v);
  return Number.isFinite(n) ? n : NaN;
}

// --------------------------------------------------------------------------
// Scaler + linear artifact
// --------------------------------------------------------------------------
function median(a: number[]): number {
  const v = a.filter(Number.isFinite).sort((x, y) => x - y);
  if (!v.length) return NaN;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

export function fitScaler(X: Matrix) {
  const d = X[0]?.length ?? 0;
  const med: number[] = [], mu: number[] = [], sd: number[] = [];
  for (let j = 0; j < d; j++) {
    const col = X.map((r) => r[j]);
    const m = median(col);
    const mm = Number.isFinite(m) ? m : 0;
    const filled = col.map((v) => (Number.isFinite(v) ? v : mm));
    const mean = filled.reduce((s, v) => s + v, 0) / Math.max(filled.length, 1);
    const varc = filled.reduce((s, v) => s + (v - mean) ** 2, 0) / Math.max(filled.length, 1);
    med.push(mm); mu.push(mean); sd.push(Math.sqrt(varc) > 1e-12 ? Math.sqrt(varc) : 1);
  }
  return { med, mu, sd };
}

function standardise(X: Matrix, med: number[], mu: number[], sd: number[]): Matrix {
  return X.map((r) => r.map((v, j) => ((Number.isFinite(v) ? v : med[j]) - mu[j]) / sd[j]));
}

export function decision(a: ModelArtifact, X: Matrix): number[] {
  const Z = standardise(X, a.medians, a.mean, a.scale);
  return Z.map((r) => r.reduce((s, v, j) => s + v * a.coef[j], a.intercept));
}

export function predict(a: ModelArtifact, X: Matrix): number[] {
  const s = decision(a, X);
  if (a.kind === "logistic") return s.map((v) => 1 / (1 + Math.exp(-v)));
  return s.map((v) => Math.pow(10, v));
}

// --------------------------------------------------------------------------
// L2 logistic regression, Newton-IRLS on scikit-learn's objective
// --------------------------------------------------------------------------
function solve(A: Matrix, b: number[]): number[] {
  const n = b.length;
  const M = A.map((r, i) => [...r, b[i]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const piv = M[c][c] || 1e-12;
    for (let r = c + 1; r < n; r++) {
      const f = M[r][c] / piv;
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  const x = new Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let s = M[r][n];
    for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k];
    x[r] = s / (M[r][r] || 1e-12);
  }
  return x;
}

export function fitLogistic(X: Matrix, y: number[], w: number[] | null, features: string[], C = 1.0): ModelArtifact {
  const { med, mu, sd } = fitScaler(X);
  const Z = standardise(X, med, mu, sd);
  const n = Z.length, d = Z[0]?.length ?? 0;
  const ww = w ?? new Array(n).fill(1);
  let pos = 0, neg = 0;
  for (let i = 0; i < n; i++) (y[i] === 1 ? (pos += ww[i]) : (neg += ww[i]));
  if (pos === 0 || neg === 0) throw new Error("need both classes to train a triage model");
  const s = ww.map((wi, i) => wi * (y[i] === 1 ? (pos + neg) / (2 * pos) : (pos + neg) / (2 * neg)));
  const beta = new Array(d + 1).fill(0); // [w..., b]
  for (let it = 0; it < 100; it++) {
    const g = new Array(d + 1).fill(0);
    const H: Matrix = Array.from({ length: d + 1 }, () => new Array(d + 1).fill(0));
    for (let j = 0; j < d; j++) { g[j] = beta[j]; H[j][j] = 1; } // L2 on weights only
    for (let i = 0; i < n; i++) {
      const xi = [...Z[i], 1];
      let t = 0;
      for (let j = 0; j <= d; j++) t += xi[j] * beta[j];
      const p = 1 / (1 + Math.exp(-t));
      const r = C * s[i] * (p - y[i]);
      const h = C * s[i] * p * (1 - p);
      for (let j = 0; j <= d; j++) {
        g[j] += r * xi[j];
        for (let k = 0; k <= d; k++) H[j][k] += h * xi[j] * xi[k];
      }
    }
    const step = solve(H, g);
    let norm = 0;
    for (let j = 0; j <= d; j++) { beta[j] -= step[j]; norm += step[j] * step[j]; }
    if (Math.sqrt(norm) < 1e-10) break;
  }
  return { kind: "logistic", features, medians: med, mean: mu, scale: sd,
           coef: beta.slice(0, d), intercept: beta[d], extra: { C, class_balanced: true, solver: "newton-irls" } };
}

// --------------------------------------------------------------------------
// Rule baseline (model v1.0): same function as pipeline/learning.rules_score
// --------------------------------------------------------------------------
export function rulesScore(X: Matrix, features = TRIAGE_FEATURES): number[] {
  const idx = (n: string) => features.indexOf(n);
  const col = (r: number[], n: string, d: number) => { const i = idx(n); const v = i >= 0 ? r[i] : NaN; return Number.isFinite(v) ? v : d; };
  return X.map((r) => {
    const pct = col(r, "seasonal_pct_primary", 50);
    const persist = Math.min(Math.max(col(r, "persistence_frac", 0), 0), 1);
    const cloud = Math.min(Math.max(col(r, "cloud_adjacent_frac", 0), 0), 1);
    let s = Math.min(Math.max((pct - 80) / 20, 0), 1);
    s = s * (1 - persist) * (1 - 0.6 * cloud);
    return Math.min(Math.max(0.05 + 0.9 * s, 0), 1);
  });
}

// --------------------------------------------------------------------------
// Metrics (scikit-learn definitions)
// --------------------------------------------------------------------------
export function auroc(y: number[], p: number[]): number {
  const pos = y.filter((v) => v === 1).length, neg = y.length - pos;
  if (!pos || !neg) return NaN;
  const order = p.map((v, i) => [v, i] as [number, number]).sort((a, b) => a[0] - b[0]);
  const rank = new Array(p.length);
  for (let i = 0; i < order.length;) {
    let j = i;
    while (j + 1 < order.length && order[j + 1][0] === order[i][0]) j++;
    const r = (i + j) / 2 + 1;
    for (let k = i; k <= j; k++) rank[order[k][1]] = r;
    i = j + 1;
  }
  let sum = 0;
  y.forEach((v, i) => { if (v === 1) sum += rank[i]; });
  return (sum - (pos * (pos + 1)) / 2) / (pos * neg);
}

export function averagePrecision(y: number[], p: number[]): number {
  const pos = y.filter((v) => v === 1).length;
  if (!pos || pos === y.length) return NaN;
  const order = p.map((v, i) => [v, y[i]] as [number, number]).sort((a, b) => b[0] - a[0]);
  let tp = 0, fp = 0, prevR = 0, ap = 0;
  for (let i = 0; i < order.length;) {
    let j = i;
    while (j < order.length && order[j][0] === order[i][0]) { order[j][1] === 1 ? tp++ : fp++; j++; }
    const R = tp / pos, P = tp / (tp + fp);
    ap += (R - prevR) * P;
    prevR = R;
    i = j;
  }
  return ap;
}

export function ece(y: number[], p: number[], bins = 10): number {
  let e = 0;
  for (let b = 0; b < bins; b++) {
    const lo = b / bins, hi = (b + 1) / bins;
    const idx = p.map((v, i) => i).filter((i) => p[i] >= lo && (b === bins - 1 ? p[i] <= hi : p[i] < hi));
    if (!idx.length) continue;
    const mp = idx.reduce((s, i) => s + p[i], 0) / idx.length;
    const my = idx.reduce((s, i) => s + y[i], 0) / idx.length;
    e += (idx.length / p.length) * Math.abs(mp - my);
  }
  return e;
}

export function classificationMetrics(y: number[], p: number[], thr = 0.5) {
  let tp = 0, fp = 0, fn = 0, tn = 0, brier = 0, ll = 0;
  y.forEach((yi, i) => {
    const yh = p[i] >= thr ? 1 : 0;
    if (yh && yi) tp++; else if (yh && !yi) fp++; else if (!yh && yi) fn++; else tn++;
    brier += (p[i] - yi) ** 2;
    const pe = Math.min(Math.max(p[i], 1e-9), 1 - 1e-9);
    ll += -(yi * Math.log(pe) + (1 - yi) * Math.log(1 - pe));
  });
  const precision = tp + fp ? tp / (tp + fp) : NaN;
  const recall = tp + fn ? tp / (tp + fn) : NaN;
  const f1 = precision + recall ? (2 * precision * recall) / (precision + recall) : NaN;
  return { auroc: auroc(y, p), auprc: averagePrecision(y, p), f1, precision, recall,
           brier: brier / y.length, log_loss: ll / y.length, ece: ece(y, p), n: y.length,
           positives: y.filter((v) => v === 1).length, confusion: { tp, fp, fn, tn } };
}

function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function groupedBootstrapDiff(y: number[], a: number[], b: number[], groups: string[],
  fn: (y: number[], p: number[]) => number, nBoot = 1000, seed = 813) {
  const rng = mulberry32(seed);
  const ug = [...new Set(groups)].sort();
  const gi = new Map<string, number[]>();
  groups.forEach((g, i) => { if (!gi.has(g)) gi.set(g, []); gi.get(g)!.push(i); });
  const diffs: number[] = [];
  for (let k = 0; k < nBoot; k++) {
    const ix: number[] = [];
    for (let t = 0; t < ug.length; t++) ix.push(...gi.get(ug[Math.floor(rng() * ug.length)])!);
    const yy = ix.map((i) => y[i]);
    const ma = fn(yy, ix.map((i) => a[i])), mb = fn(yy, ix.map((i) => b[i]));
    if (Number.isFinite(ma) && Number.isFinite(mb)) diffs.push(mb - ma);
  }
  diffs.sort((x, z) => x - z);
  const q = (f: number) => diffs.length ? diffs[Math.min(diffs.length - 1, Math.floor(f * diffs.length))] : NaN;
  return { diff: fn(y, b) - fn(y, a), ci: [q(0.025), q(0.975)] as [number, number], n_boot: diffs.length };
}

// --------------------------------------------------------------------------
// Model tests and gate (same checks as pipeline/learning.evaluate_gate)
// --------------------------------------------------------------------------
export function modelTests(a: ModelArtifact, Xv: Matrix): GateCheck[] {
  const p1 = predict(a, Xv);
  const p2 = predict(a, Xv);
  const rt = JSON.parse(JSON.stringify(a)) as ModelArtifact;
  const p3 = predict(rt, Xv);
  const Xn = Xv.map((r) => r.map(() => NaN));
  return [
    { name: "predictions_finite", passed: p1.every(Number.isFinite) },
    a.kind === "logistic"
      ? { name: "probabilities_in_unit_interval", passed: p1.every((v) => v >= 0 && v <= 1) }
      : { name: "concentrations_positive", passed: p1.every((v) => v > 0) },
    { name: "deterministic", passed: p1.every((v, i) => v === p2[i]) },
    { name: "artifact_roundtrip_identical", passed: p1.every((v, i) => Math.abs(v - p3[i]) < 1e-12) },
    { name: "missing_features_imputed_not_nan", passed: predict(a, Xn).every(Number.isFinite) },
    { name: "feature_schema_declared", passed: a.features.length === (Xv[0]?.length ?? 0) },
  ];
}

export function evaluateGate(cand: number[], prod: number[], y: number[], groups: string[], subgroups: string[],
  frozenHash: string, currentHash: string, tests: GateCheck[]): GateReport {
  const checks: GateCheck[] = [];
  checks.push({ name: "model_test_suite", passed: tests.every((t) => t.passed), detail: tests });
  checks.push({ name: "validation_dataset_unchanged", passed: frozenHash === currentHash, detail: { frozen: frozenHash, current: currentHash } });
  const both = new Set(y).size === 2;
  checks.push({ name: "validation_has_both_classes", passed: both, detail: { n: y.length, positives: y.filter((v) => v === 1).length } });
  const mc = classificationMetrics(y, cand), mp = classificationMetrics(y, prod);
  const boot = groupedBootstrapDiff(y, prod, cand, groups, averagePrecision);
  checks.push({ name: "primary_metric_not_worse", passed: mc.auprc >= mp.auprc,
                detail: { metric: "auprc", candidate: mc.auprc, production: mp.auprc, diff_ci95: boot.ci } });
  checks.push({ name: "calibration_acceptable", passed: mc.ece <= 0.15 || mc.brier <= mp.brier,
                detail: { ece: mc.ece, max_ece: 0.15, brier_candidate: mc.brier, brier_production: mp.brier } });
  const sub: Record<string, unknown>[] = [];
  for (const g of [...new Set(subgroups)].sort()) {
    const ix = subgroups.map((s, i) => (s === g ? i : -1)).filter((i) => i >= 0);
    const yy = ix.map((i) => y[i]);
    if (ix.length < 5 || new Set(yy).size < 2) { sub.push({ subgroup: g, n: ix.length, skipped: true }); continue; }
    const a = averagePrecision(yy, ix.map((i) => prod[i])), b = averagePrecision(yy, ix.map((i) => cand[i]));
    sub.push({ subgroup: g, n: ix.length, production: a, candidate: b, regressed: b < a - 0.05 });
  }
  checks.push({ name: "no_subgroup_regression", passed: !sub.some((s) => s.regressed), detail: sub });
  return { task: "triage", passed: checks.every((c) => c.passed), checks,
           summary: { candidate: mc, production: mp },
           human_approval: { required: true, approved_by: null }, validation_hash: currentHash };
}

export function nextVersion(current?: string | null, bump: "major" | "minor" | "patch" = "minor"): string {
  if (!current) return "1.0.0";
  const [ma, mi, pa] = current.split(".").map(Number);
  if (bump === "major") return `${ma + 1}.0.0`;
  if (bump === "patch") return `${ma}.${mi}.${pa + 1}`;
  return `${ma}.${mi + 1}.0`;
}

export async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function datasetHash(labels: LabelRow[]): Promise<string> {
  const rows = [...labels].sort((a, b) => (a.id < b.id ? -1 : 1)).map((l) => [l.id, l.target, l.features]);
  return (await sha256Hex(canon(rows))).slice(0, 16);
}

/** Canonical JSON: sorted keys, no whitespace. */
export function canon(v: unknown): string {
  if (v === null || typeof v !== "object") return JSON.stringify(v ?? null);
  if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
  const o = v as Record<string, unknown>;
  return "{" + Object.keys(o).sort().map((k) => JSON.stringify(k) + ":" + canon(o[k])).join(",") + "}";
}
