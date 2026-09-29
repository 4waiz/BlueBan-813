// Parity check: the browser trainer (apps/web/lib/learning.ts) must reproduce
// scikit-learn's L2 logistic regression and the Python metrics on a fixture.
// Run: npx tsx tests/parity/learning_parity.ts
import { readFileSync } from "node:fs";
import { fitLogistic, predict, classificationMetrics, rulesScore, TRIAGE_FEATURES } from "../../apps/web/lib/learning";

const f = JSON.parse(readFileSync(new URL("./logistic_fixture.json", import.meta.url), "utf8"));
const X = f.X.map((r: (number | null)[]) => r.map((v) => (v === null ? NaN : v)));
const art = fitLogistic(X, f.y, f.w, TRIAGE_FEATURES, 1.0);
const p = predict(art, X);
const m = classificationMetrics(f.y, p);
const rs = rulesScore(X);
const maxCoef = Math.max(...art.coef.map((c, i) => Math.abs(c - f.coef[i])), Math.abs(art.intercept - f.intercept));
const checks = {
  coefficients: maxCoef,
  auroc: Math.abs(m.auroc - f.auroc),
  auprc: Math.abs(m.auprc - f.auprc),
  ece: Math.abs(m.ece - f.ece),
  brier: Math.abs(m.brier - f.brier),
  rules: Math.max(...rs.map((v, i) => Math.abs(v - f.rules[i]))),
};
console.log(JSON.stringify(checks));
const tol = { coefficients: 1e-4, auroc: 1e-9, auprc: 1e-9, ece: 1e-6, brier: 1e-6, rules: 1e-12 } as Record<string, number>;
const bad = Object.entries(checks).filter(([k, v]) => !(v <= tol[k]));
if (bad.length) { console.error("PARITY FAILED", bad); process.exit(1); }
console.log("parity OK");
