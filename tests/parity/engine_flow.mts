// End-to-end check of the hosted workspace engine on the real seed:
// review -> verified label -> retrain -> gate -> human promotion -> rollback.
// Run (from apps/web): npx tsx ../../tests/parity/engine_flow.mts
import { readFileSync } from "node:fs";
import { LocalEngine } from "../../apps/web/lib/engine/local";

const store = new Map<string, string>();
(globalThis as unknown as { localStorage: Storage }).localStorage = {
  getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); },
  removeItem: (k: string) => { store.delete(k); }, clear: () => store.clear(), key: () => null, length: 0,
} as Storage;
const seedPath = new URL("../../outputs/workspace/seed.json", import.meta.url);
(globalThis as unknown as { fetch: unknown }).fetch = async () => ({ ok: true, json: async () => JSON.parse(readFileSync(seedPath, "utf8")) });

const fail = (m: string) => { console.error("FLOW FAILED:", m); process.exit(1); };
const e = new LocalEngine("seed.json");
const list = await e.listIncidents();
const hero = list.find((i) => i.status === "UNDER_REVIEW" && i.aoi_id.startsWith("AE"));
if (!hero) fail("no UAE incident under review in the seed");
const r = await e.review(hero!.id, { reviewer: "Test Analyst", decision: "CONFIRM", note: "flow test" });
if (r.status_after !== "CONFIRMED" || !r.label_id) fail(`review: ${JSON.stringify(r).slice(0, 200)}`);
const labels = await e.labels("triage");
console.log(`review ok -> ${r.status_after}, label ${r.label_id}; ${labels.length} labels`);
const job = await e.retrain("triage", "Test Analyst");
if (job.status !== "SUCCEEDED") fail(`retrain: ${job.error}`);
const cand = await e.model(job.candidate_model_id!);
const gate = cand!.gate!;
console.log("gate", gate.passed ? "PASSED" : "REFUSED", gate.checks.map((c) => `${c.name}:${c.passed ? "ok" : "X"}`).join(" "));
const m = (k: string) => cand!.metrics.find((x) => x.metric === k)?.value;
console.log(`candidate AUPRC ${m("auprc")?.toFixed(3)} AUROC ${m("auroc")?.toFixed(3)} ECE ${m("ece")?.toFixed(3)}`);
let refused = false;
try { await e.promote(cand!.id, "system"); } catch { refused = true; }
if (!refused) fail("promotion by a system actor must be refused");
if (gate.passed) {
  const p = await e.promote(cand!.id, "Test Analyst", "flow test");
  if (p.status !== "PRODUCTION") fail("promotion did not reach PRODUCTION");
  const prev = (await e.models("triage")).find((x) => x.id === "triage-1.0.0");
  if (prev?.status !== "RETIRED") fail("previous production model not retired");
  const rb = await e.rollback("triage-1.0.0", "Test Analyst", "flow test");
  const after = (await e.models("triage")).find((x) => x.id === cand!.id);
  if (rb.status !== "PRODUCTION" || after?.status === "PRODUCTION") fail("rollback did not restore the previous model");
  console.log(`promoted ${p.id}; rolled back to ${rb.id} (${rb.status}); candidate now ${after?.status}`);
}
const v = await e.verifyAudit();
if (!v.ok) fail(`audit chain broken at ${v.first_bad_seq}`);
console.log(`audit chain intact (${v.n} events)`);
console.log("engine flow OK");
