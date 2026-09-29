"use client";
/**
 * The persistent mission-control frame (docs/design/dashboard-target.png):
 * top telemetry bar, WATCH -> LEARN mission rail, content, status footer.
 * Every number here is read from the engine or the pipeline bundle.
 */
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import React, { useEffect, useMemo, useState } from "react";
import {
  Activity, Binoculars, BrainCircuit, CalendarClock, ClipboardCheck, Database, FlaskConical, Gauge,
  LayoutDashboard, Radar, Satellite, Settings, ShieldCheck, Siren, Sparkles, UserRound, Waves, Presentation,
} from "lucide-react";
import { BASE_PATH, getOperator, setOperator, useEngineQuery } from "@/lib/engine";
import type { Aoi, IncidentSummary, LabelRow, ModelRecord } from "@/lib/engine/types";
import { Dot, fmt, Modal, SimBadge, toast, Toaster } from "@/components/ui";
import { nextPass } from "@/lib/passes";

const TEAM_URL = "https://kanbanstudios.ae/team-kanban";

function useClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => { setNow(new Date()); const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  return now;
}

function UaeFlag({ size = 18 }: { size?: number }) {
  return (
    <svg width={size * 1.6} height={size} viewBox="0 0 12 6" aria-label="UAE flag" className="rounded-[2px]">
      <rect width="12" height="2" fill="#00732F" /><rect y="2" width="12" height="2" fill="#FFFFFF" />
      <rect y="4" width="12" height="2" fill="#000000" /><rect width="3" height="6" fill="#FF0000" />
    </svg>
  );
}

export function useShellData() {
  const inc = useEngineQuery((e) => e.listIncidents());
  const aois = useEngineQuery((e) => e.aois());
  const models = useEngineQuery((e) => e.models("triage"));
  const labels = useEngineQuery((e) => e.labels("triage"));
  return { incidents: inc.data || [], aois: aois.data || [], models: models.data || [], labels: labels.data || [] };
}

function TopBar({ aois, models }: { aois: Aoi[]; models: ModelRecord[] }) {
  const now = useClock();
  const [op, setOp] = useState("");
  const [edit, setEdit] = useState(false);
  const [draft, setDraft] = useState("");
  useEffect(() => { setOp(getOperator()); }, [edit]);
  const prod = models.find((m) => m.status === "PRODUCTION");
  const uae = aois.filter((a) => a.id.startsWith("AE-"));
  const last = uae.map((a) => a.last_observation).filter(Boolean).sort().pop() || null;
  const np = useMemo(() => (now ? nextPass(uae, now) : null), [uae, now]);
  const fresh = last && now ? (now.getTime() - new Date(last).getTime()) / 86400e3 : null;
  return (
    <header className="flex h-[74px] items-center gap-4 border-b border-edge/80 bg-void/70 px-4 backdrop-blur">
      <Link href="/" className="flex items-center gap-3 pr-4">
        <Image src={`${BASE_PATH}/brand/mark-96.png`} alt="BLUEBAN 813" width={46} height={46} priority />
        <div className="leading-tight">
          <div className="font-display text-[22px] font-extrabold tracking-[0.12em] text-ink">BLUEBAN <span className="text-cyan">813</span></div>
          <div className="text-[10.5px] font-semibold tracking-[0.34em] text-muted">UAE COASTAL INTELLIGENCE</div>
        </div>
      </Link>
      <div className="hidden h-11 w-px bg-edge xl:block" />
      <div className="hidden min-w-0 flex-1 items-center gap-2 xl:flex">
        <TopStat icon={<Dot color={fresh != null && fresh < 6 ? "#23D484" : "#FFC23D"} pulse />} k="REAL-TIME MONITORING" v="UAE Coastline" sub={`${uae.length} AOIs`} />
        <TopStat icon={<BrainCircuit size={20} className="text-nominal" />} k="ACTIVE MODEL"
          v={prod ? <span>v{prod.version} <span className="text-nominal">(Production)</span></span> : "loading"} sub={prod?.model_type === "rules" ? "rule-based triage" : "learned triage"} />
        <TopStat icon={<CalendarClock size={20} className="text-beam2" />} k="LAST OBSERVATION" v={fmt.utc(last)}
          sub={<span className="flex items-center gap-1.5">Sentinel-2 L2A · <SimBadge text="813 SIM" /> · Sentinel-3</span>} />
        <TopStat icon={<Satellite size={20} className="text-cyan" />} k="NEXT PASS (NOMINAL)"
          v={np ? `in ${np.inText}` : "n/a"} sub={np ? `${np.platform} · orbit ${np.orbit}` : "no pattern"} />
      </div>
      <div className="ml-auto flex items-center gap-3">
        <Link href="/judge" className="btn btn-primary hidden md:inline-flex"><Presentation size={15} /> Judge Mode</Link>
        <div className="hidden text-right lg:block">
          <div className="hud-value text-[20px] font-semibold text-ink">{now ? now.toISOString().slice(11, 19) : "--:--:--"} <span className="text-[11px] text-muted">UTC</span></div>
          <div className="text-[10.5px] text-muted">{now ? now.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }) : ""}</div>
        </div>
        <button onClick={() => { setDraft(op); setEdit(true); }} className="grid h-10 w-10 place-items-center rounded-full border border-line bg-panel2 text-[12px] font-bold text-ink hover:border-beam2" title={op ? `Operator: ${op}` : "Set operator name"}>
          {op ? op.slice(0, 2).toUpperCase() : <UserRound size={18} />}
        </button>
      </div>
      <Modal open={edit} onClose={() => setEdit(false)} title="Operator identity" width={420}>
        <p className="mb-3 text-[12.5px] text-muted">Every review, sample and promotion is recorded under this name in the audit log.</p>
        <input className="mb-3 w-full rounded-md border border-line bg-deep px-3 py-2 text-[13px] outline-none focus:border-beam2" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. analyst.awaiz" maxLength={60} />
        <div className="flex justify-end gap-2">
          <button className="btn" onClick={() => setEdit(false)}>Cancel</button>
          <button className="btn btn-primary" disabled={!draft.trim()} onClick={() => { setOperator(draft); setEdit(false); toast(`Operator set: ${draft.trim()}`); }}>Save</button>
        </div>
      </Modal>
    </header>
  );
}

function TopStat({ icon, k, v, sub }: { icon: React.ReactNode; k: string; v: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-lg border border-edge/70 bg-panel/60 px-3 py-2">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-edge bg-deep">{icon}</div>
      <div className="min-w-0 leading-tight">
        <div className="hud-kicker">{k}</div>
        <div className="truncate text-[13.5px] font-semibold text-ink">{v}</div>
        {sub && <div className="truncate text-[10.5px] text-muted">{sub}</div>}
      </div>
    </div>
  );
}

type RailState = "ok" | "attention" | "blocked" | "idle";
const RAIL_COLOR: Record<RailState, string> = { ok: "#23D484", attention: "#FFC23D", blocked: "#FF4D5E", idle: "#5D7299" };

function MissionRail({ incidents, aois, models, labels }: { incidents: IncidentSummary[]; aois: Aoi[]; models: ModelRecord[]; labels: LabelRow[] }) {
  const path = usePathname();
  const open = incidents.filter((i) => ["DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "MONITORING"].includes(i.status) && i.role !== "negative_control");
  const review = incidents.filter((i) => ["DETECTED", "UNDER_REVIEW"].includes(i.status));
  const field = incidents.filter((i) => i.status === "FIELD_VALIDATION_REQUIRED");
  const prod = models.find((m) => m.status === "PRODUCTION");
  const cand = models.find((m) => m.status === "CANDIDATE");
  const newLabels = labels.filter((l) => l.source !== "cross_sensor_reference" && (!prod?.promoted_at || l.created_at > prod.promoted_at));
  const uae = aois.filter((a) => a.id.startsWith("AE-"));
  const items: { href: string; label: string; sub: string; icon: React.ReactNode; state: RailState; note: string }[] = [
    { href: "/watch", label: "WATCH", sub: "Monitoring", icon: <Binoculars size={22} />, state: uae.length ? "ok" : "idle", note: `${uae.length} AOIs` },
    { href: "/incidents", label: "DETECT", sub: "Anomalies", icon: <Radar size={22} />, state: review.length ? "attention" : "ok", note: `${open.length} open` },
    { href: "/spectra", label: "DIAGNOSE", sub: "Spectral evidence", icon: <Waves size={22} />, state: "ok", note: "S2 + 813 sim" },
    { href: "/field", label: "VERIFY", sub: "Field validation", icon: <ShieldCheck size={22} />, state: field.length ? "attention" : review.length ? "attention" : "ok", note: `${review.length} to review` },
    { href: "/incident", label: "ACT", sub: "Response", icon: <Siren size={22} />, state: open.length ? "attention" : "idle", note: open.length ? "actions due" : "none" },
    { href: "/learn", label: "LEARN", sub: "Model improvement", icon: <Sparkles size={22} />, state: cand ? "attention" : "ok", note: cand ? "candidate ready" : `${newLabels.length} new labels` },
  ];
  const nav = [
    { href: "/incidents", label: "INCIDENTS", icon: <ClipboardCheck size={16} />, badge: open.length },
    { href: "/field", label: "SAMPLES", icon: <FlaskConical size={16} /> },
    { href: "/validation", label: "VALIDATION", icon: <Gauge size={16} /> },
    { href: "/data", label: "DATA", icon: <Database size={16} /> },
    { href: "/assets", label: "ASSETS", icon: <Activity size={16} /> },
    { href: "/settings", label: "SETTINGS", icon: <Settings size={16} /> },
  ];
  return (
    <nav className="flex w-[228px] shrink-0 flex-col gap-2 overflow-y-auto border-r border-edge/70 bg-void/40 p-3">
      <Link href="/" className={`flex items-center gap-2 rounded-md px-3 py-2 text-[11.5px] font-bold tracking-[0.14em] ${path === "/" ? "bg-beam/15 text-ink" : "text-muted hover:text-ink"}`}>
        <LayoutDashboard size={16} /> INCIDENT CONTROL
      </Link>
      {items.map((it) => {
        const active = path === it.href || (it.href !== "/" && path.startsWith(it.href));
        return (
          <Link key={it.label} href={it.href}
            className={`group relative flex items-center gap-3 rounded-lg border px-3 py-3 transition ${active ? "border-beam/70 bg-beam/10 shadow-beam" : "border-edge/70 bg-panel/50 hover:border-line"}`}>
            <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r" style={{ background: RAIL_COLOR[it.state] }} />
            <span className="grid h-10 w-10 place-items-center rounded-md border border-edge bg-deep" style={{ color: RAIL_COLOR[it.state] === "#5D7299" ? "#93A6CB" : RAIL_COLOR[it.state] }}>{it.icon}</span>
            <span className="min-w-0 leading-tight">
              <span className="block font-display text-[14px] font-bold tracking-[0.1em] text-ink">{it.label}</span>
              <span className="block truncate text-[11px] text-muted">{it.sub}</span>
              <span className="block truncate text-[10px]" style={{ color: RAIL_COLOR[it.state] }}>{it.note}</span>
            </span>
          </Link>
        );
      })}
      <div className="rule-h my-2" />
      {nav.map((n) => (
        <Link key={n.label} href={n.href} className={`flex items-center gap-3 rounded-md px-3 py-2 text-[11.5px] font-bold tracking-[0.12em] ${path.startsWith(n.href) ? "bg-beam/15 text-ink" : "text-muted hover:text-ink"}`}>
          {n.icon}<span className="flex-1">{n.label}</span>
          {n.badge ? <span className="grid h-5 min-w-5 place-items-center rounded-full bg-critical px-1.5 text-[10px] font-bold text-white">{n.badge}</span> : null}
        </Link>
      ))}
    </nav>
  );
}

function Footer({ incidents, aois, labels, models }: { incidents: IncidentSummary[]; aois: Aoi[]; labels: LabelRow[]; models: ModelRecord[] }) {
  const open = incidents.filter((i) => ["DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED"].includes(i.status)).length;
  const uae = aois.filter((a) => a.id.startsWith("AE-"));
  const scenes7 = uae.reduce((s, a) => s + (a.n_obs_7d || 0), 0);
  const prod = models.find((m) => m.status === "PRODUCTION");
  const queued = labels.filter((l) => l.source !== "cross_sensor_reference" && (!prod?.promoted_at || l.created_at > prod.promoted_at)).length;
  const stats: [string, string | number, string][] = [
    ["Active incidents", open, "#FF4D5E"], ["Monitoring AOIs", uae.length, "#FFC23D"],
    ["AOI observations (7d)", scenes7, "#EAF1FF"], ["Labels queued for LEARN", queued, "#27C3F3"],
  ];
  return (
    <footer className="flex h-[44px] items-center gap-5 border-t border-edge/70 bg-void/80 px-4 text-[11px]">
      <div className="flex items-center gap-2 font-bold tracking-[0.16em] text-muted"><UaeFlag size={12} /> UAE COASTAL MONITORING</div>
      <div className="hidden items-center gap-6 md:flex">
        {stats.map(([k, v, c]) => (
          <div key={k} className="flex items-baseline gap-2"><span className="hud-value text-[15px] font-bold" style={{ color: c }}>{v}</span><span className="text-muted">{k}</span></div>
        ))}
      </div>
      <div className="ml-auto flex items-center gap-4">
        <span className="hidden text-muted lg:inline">Open data: Copernicus Sentinel-2/3 · Landsat · Planet Tanager (CC-BY-4.0) · © OpenStreetMap</span>
        <a href={TEAM_URL} target="_blank" rel="noopener noreferrer" className="font-semibold text-ink hover:text-cyan">Built by <span className="text-cyan">Team Kanban</span></a>
      </div>
    </footer>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const d = useShellData();
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TopBar aois={d.aois} models={d.models} />
      <div className="flex min-h-0 flex-1">
        <MissionRail {...d} />
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
      <Footer {...d} />
      <Toaster />
    </div>
  );
}
