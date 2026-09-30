"use client";
/**
 * DATA - where every number comes from, under what licence, and who changed what.
 *
 * Data policy, the source register, pipeline lineage (counts read from the
 * outputs), the tamper-evident audit log of this workspace, and the project
 * documentation. Nothing here is typed in by hand except the source register,
 * which lives in one place (scripts/build_static_site.py).
 */
import React, { useMemo, useState } from "react";
import { ArrowRight, CheckCircle2, CircleX, Database, ExternalLink, FileText, Fingerprint, ShieldCheck } from "lucide-react";
import { pipelineUrl, useEngineQuery, useStatic } from "@/lib/engine";
import type { AuditEvent } from "@/lib/engine/types";
import Markdown from "@/components/ui/Markdown";
import { Chip, fmt, Panel } from "@/components/ui";

type Source = { name: string; provider: string; licence: string; role: string; status: string; url: string | null };
type Status = {
  generated_utc: string;
  data_policy: { real_813_data_used: boolean; "813_status": string; in_situ_available: boolean; quantification: string; olci_archive_end: string };
  sources?: Source[];
  lineage?: { watch: { aois: number; datatakes: number; ok: number }; detect: { aois: number; acquisitions: number; pixel_level: number; candidates: number }; olci_extracts: number; labels: { n: number; validation: number }; incidents: string[] };
};

const statusColor = (s: string) => (s.startsWith("USED") ? "#23D484" : s.startsWith("NOT") || s.startsWith("NOTHING") ? "#FF4D5E" : s.startsWith("DISPLAY") ? "#93A6CB" : "#FFC23D");

function Policy({ p }: { p: Status["data_policy"] }) {
  const items: [string, string, string][] = [
    ["Real Satellite 813 data used", p.real_813_data_used ? "YES" : "NO", p["813_status"]],
    ["Public UAE in-situ measurements", p.in_situ_available ? "AVAILABLE" : "NONE", "No per-sample chlorophyll / turbidity / TSS found; EAD station LOCATIONS only"],
    ["Physical concentrations", "NOT REPORTED", p.quantification],
    ["OLCI cross-sensor archive", p.olci_archive_end.split(" ")[0], "Sentinel-3 OLCI WFR on the Planetary Computer ends here; later incidents have no OLCI check"],
  ];
  return (
    <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
      {items.map(([k, v, note]) => (
        <div key={k} className="rounded-md border border-edge bg-deep/60 p-3">
          <div className="hud-kicker">{k}</div>
          <div className={`hud-value mt-1 text-[20px] font-bold ${v === "NO" || v === "NONE" || v === "NOT REPORTED" ? "text-caution" : "text-ink"}`}>{v}</div>
          <div className="mt-1 text-[11px] text-muted">{note}</div>
        </div>))}
    </div>
  );
}

function Lineage({ l }: { l: NonNullable<Status["lineage"]> }) {
  const steps: [string, string, string][] = [
    ["WATCH", l.watch.datatakes.toLocaleString(), `Sentinel-2 datatakes over ${l.watch.aois} AOIs (${l.watch.ok.toLocaleString()} read)`],
    ["DETECT", l.detect.candidates.toLocaleString(), `candidates from ${l.detect.pixel_level.toLocaleString()} pixel-level dates of ${l.detect.acquisitions.toLocaleString()}`],
    ["OLCI", l.olci_extracts.toLocaleString(), "same-morning Sentinel-3 extracts (windowed reads)"],
    ["LABELS", l.labels.n.toLocaleString(), `cross-sensor references, ${l.labels.validation} frozen for validation`],
    ["INCIDENTS", String(l.incidents.length), l.incidents.join(", ")],
  ];
  return (
    <div className="flex flex-wrap items-stretch gap-2">
      {steps.map(([k, v, note], i) => (
        <React.Fragment key={k}>
          <div className="min-w-[150px] flex-1 rounded-md border border-edge bg-deep/60 p-3">
            <div className="hud-kicker">{k}</div>
            <div className="hud-value text-[22px] font-bold text-cyan">{v}</div>
            <div className="text-[11px] text-muted">{note}</div>
          </div>
          {i < steps.length - 1 && <ArrowRight className="self-center text-dim" size={18} />}
        </React.Fragment>))}
    </div>
  );
}

function AuditLog() {
  const [type, setType] = useState<string>("");
  const [verify, setVerify] = useState<{ ok: boolean; n: number; first_bad_seq?: number } | null>(null);
  const q = useEngineQuery((e) => e.audit(type || undefined, undefined, 300), [type]);
  const rows = q.data || [];
  const types = useMemo(() => ["", "incident", "review", "label", "sample", "measurement", "training_job", "model", "aoi", "asset", "alert"], []);
  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <select value={type} onChange={(e) => setType(e.target.value)} className="rounded-md border border-line bg-deep px-2 py-1 text-[12px]">
          {types.map((t) => <option key={t} value={t}>{t || "all entities"}</option>)}
        </select>
        <button className="btn px-2 py-1 text-[12px]" onClick={async () => { const { getEngine } = await import("@/lib/engine"); setVerify(await getEngine().verifyAudit()); }}><Fingerprint size={14} /> Verify hash chain</button>
        {verify && (verify.ok
          ? <span className="flex items-center gap-1 text-[12px] text-nominal"><CheckCircle2 size={14} /> intact · {verify.n} events</span>
          : <span className="flex items-center gap-1 text-[12px] text-critical"><CircleX size={14} /> broken at event {verify.first_bad_seq}</span>)}
        <span className="ml-auto text-[11px] text-dim">Each event stores the SHA-256 of the previous one: editing any past event breaks every hash after it.</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto rounded-md border border-edge">
        <table className="w-full text-[11.5px]">
          <thead className="sticky top-0 bg-panel"><tr className="border-b border-edge text-dim"><th className="px-2 py-1 text-left">#</th><th className="px-2 text-left">When (UTC)</th><th className="px-2 text-left">Actor</th><th className="px-2 text-left">Action</th><th className="px-2 text-left">Entity</th><th className="px-2 text-left">Hash</th></tr></thead>
          <tbody>
            {rows.map((a: AuditEvent) => (
              <tr key={a.seq} className="border-b border-edge/50" title={JSON.stringify(a.detail)}>
                <td className="hud-value px-2 py-1 text-dim">{a.seq}</td>
                <td className="px-2">{fmt.utc(a.at)}</td>
                <td className="px-2">{a.actor}</td>
                <td className="px-2 text-cyan">{a.action}</td>
                <td className="px-2">{a.entity_type} <span className="text-dim">{a.entity_id}</span></td>
                <td className="hud-value px-2 text-dim">{a.hash.slice(0, 12)}…</td>
              </tr>))}
            {!rows.length && <tr><td colSpan={6} className="p-4 text-center text-muted">No events yet. Reviews, samples, training and promotions will appear here.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Docs() {
  const idx = useStatic<{ docs: { key: string; file: string; bytes: number }[] }>("docs/index.json").data;
  const [key, setKey] = useState<string | null>(null);
  const [text, setText] = useState<string>("");
  const open = async (k: string) => {
    setKey(k); setText("Loading…");
    try { const r = await fetch(pipelineUrl(`docs/${k}.md`)); setText(r.ok ? await r.text() : `Could not load ${k}`); } catch { setText(`Could not load ${k}`); }
  };
  const docs = idx?.docs || [];
  return (
    <div className="grid h-full min-h-0 gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
      <div className="min-h-0 space-y-1 overflow-y-auto">
        {docs.map((d) => (
          <button key={d.key} onClick={() => open(d.key)} className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-[12px] ${key === d.key ? "bg-beam/20 text-ink" : "text-muted hover:bg-white/5 hover:text-ink"}`}>
            <span className="flex items-center gap-2"><FileText size={13} />{d.file.replace(/^archive\//, "archive · ").replace(/\.md$/, "").replace(/_/g, " ")}</span>
            <span className="text-[10px] text-dim">{(d.bytes / 1024).toFixed(0)} KB</span>
          </button>))}
      </div>
      <div className="min-h-0 overflow-y-auto rounded-md border border-edge bg-deep/40 px-5 py-3">
        {key ? <Markdown text={text} /> : <p className="text-[13px] text-muted">Pick a document: the audits, the event register, methodology, limitations, the validation report and the archived earlier conclusions (kept, marked historical).</p>}
      </div>
    </div>
  );
}

export default function DataPage() {
  const st = useStatic<Status>("status.json");
  const [tab, setTab] = useState<"sources" | "audit" | "docs">("sources");
  const s = st.data;
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_auto_minmax(0,1fr)] gap-3 overflow-hidden p-3 short:gap-2 short:p-2">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="hud-kicker">Data · provenance, policy and audit {s && `· bundle ${fmt.utc(s.generated_utc)}`}</div>
          <h1 className="font-display text-[22px] font-bold tracking-wide">Where every number comes from</h1>
        </div>
        <div className="flex gap-1">
          {([["sources", "Sources & lineage", <Database key="d" size={14} />], ["audit", "Audit log", <ShieldCheck key="a" size={14} />], ["docs", "Documents", <FileText key="f" size={14} />]] as const).map(([k, label, icon]) => (
            <button key={k} onClick={() => setTab(k)} className={`btn px-3 py-1.5 text-[12px] ${tab === k ? "border-beam bg-beam/15" : ""}`}>{icon}{label}</button>))}
        </div>
      </div>
      {s ? <Policy p={s.data_policy} /> : <div className="text-muted">{st.error ? `status.json missing: ${st.error}` : "Loading…"}</div>}
      {tab === "sources" && s && (
        <div className="grid min-h-0 gap-3 overflow-y-auto">
          {s.lineage && <Panel title="Pipeline lineage" kicker="Counts read from outputs/ at bundle time" bodyClass="p-3"><Lineage l={s.lineage} /></Panel>}
          <Panel title="Source register" kicker="Provider · licence · what it is used for" bodyClass="p-3">
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead><tr className="border-b border-edge text-dim"><th className="px-2 py-1.5 text-left">Source</th><th className="px-2 text-left">Provider</th><th className="px-2 text-left">Licence</th><th className="px-2 text-left">Role</th><th className="px-2 text-left">Status</th></tr></thead>
                <tbody>{(s.sources || []).map((r) => (
                  <tr key={r.name} className="border-b border-edge/50 align-top">
                    <td className="px-2 py-1.5 font-semibold">{r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-cyan">{r.name}<ExternalLink size={11} /></a> : r.name}</td>
                    <td className="px-2 py-1.5 text-muted">{r.provider}</td>
                    <td className="px-2 py-1.5 text-muted">{r.licence}</td>
                    <td className="px-2 py-1.5 text-muted">{r.role}</td>
                    <td className="px-2 py-1.5"><Chip label={r.status} color={statusColor(r.status)} /></td>
                  </tr>))}</tbody>
              </table>
            </div>
            <p className="mt-2 text-[11px] text-dim">Restricted downloads (authenticated platforms, commercial imagery) never leave data/raw/private/, which is gitignored. Nothing on this page or in the repository is restricted data.</p>
          </Panel>
        </div>)}
      {tab === "audit" && <Panel title="Audit log · this workspace" bodyClass="min-h-0 p-3" className="min-h-0"><AuditLog /></Panel>}
      {tab === "docs" && <Panel title="Documentation" bodyClass="min-h-0 p-3" className="min-h-0"><Docs /></Panel>}
    </div>
  );
}
