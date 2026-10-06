"use client";
/**
 * The persistent mission-control frame (docs/design/dashboard-target.png):
 * top telemetry bar, WATCH -> LEARN mission rail, content, status footer.
 * Every number here is read from the engine or the pipeline bundle.
 *
 * Below the lg breakpoint the rail becomes a slide-in drawer (menu button in
 * the top bar), so phones and tablets get the full width for the content.
 */
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import React, { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity, Binoculars, BrainCircuit, CalendarClock, Code2, Database, Factory, Gauge, LayoutDashboard, Menu, Radar,
  Satellite, Settings, ShieldCheck, Siren, Sparkles, UserRound, Waves, Presentation, Droplets, X,
} from "lucide-react";
import { BASE_PATH, getOperator, setOperator, useEngineQuery } from "@/lib/engine";
import type { Aoi, IncidentSummary, LabelRow, ModelRecord } from "@/lib/engine/types";
import { Dot, fmt, Modal, toast, Toaster } from "@/components/ui";
import { nextPass } from "@/lib/passes";
import IntroSequence from "@/components/shell/IntroSequence";

const TEAM_URL = "https://kanbanstudios.ae/team-kanban";

function useClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => { setNow(new Date()); const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  return now;
}

/** Route match that ignores a trailing slash and never lets /incident match /incidents. */
function useIsActive() {
  const raw = usePathname() || "/";
  const path = raw.length > 1 ? raw.replace(/\/+$/, "") : raw;
  return (href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`));
}

function UaeFlag({ size = 18 }: { size?: number }) {
  return (
    <svg width={size * 1.6} height={size} viewBox="0 0 12 6" aria-label="UAE flag" className="shrink-0 rounded-[2px]">
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
  return {
    incidents: inc.data || [], aois: aois.data || [], models: models.data || [], labels: labels.data || [],
    loading: inc.loading || aois.loading || models.loading || labels.loading,
  };
}

function TopBar({ aois, models, onMenu }: { aois: Aoi[]; models: ModelRecord[]; onMenu: () => void }) {
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
    <header className="flex h-[74px] shrink-0 items-center gap-3 border-b border-edge/80 bg-void/70 px-3 backdrop-blur sm:px-4 short:h-[60px] xl:gap-4">
      <button onClick={onMenu} className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-line bg-panel2 text-ink hover:border-beam2 lg:hidden" aria-label="Open navigation">
        <Menu size={19} />
      </button>
      <Link href="/" className="flex min-w-0 shrink-0 items-center gap-3 xl:pr-2">
        <Image src={`${BASE_PATH}/brand/mark-96.png`} alt="BLUEBAN 813" width={46} height={46} priority className="h-9 w-9 sm:h-[46px] sm:w-[46px] short:h-9 short:w-9" />
        <div className="whitespace-nowrap leading-tight">
          <div className="font-display text-[18px] font-extrabold tracking-[0.12em] text-ink sm:text-[22px] short:text-[19px]">BLUEBAN <span className="text-cyan">813</span></div>
          <div className="hidden text-[10.5px] font-semibold tracking-[0.3em] text-muted sm:block">UAE COASTAL INTELLIGENCE</div>
        </div>
      </Link>
      <div className="hidden h-11 w-px shrink-0 bg-edge xl:block" />
      <div className="hidden min-w-0 flex-1 items-center gap-2 xl:flex">
        <TopStat className="hidden wide:flex" icon={<Dot color={fresh != null && fresh < 6 ? "#23D484" : "#FFC23D"} pulse />} k="Satellite monitoring" v="UAE coastline" sub={`${uae.length} areas`} />
        <TopStat icon={<BrainCircuit size={20} className="text-nominal" />} k="Active model"
          v={prod ? <span>v{prod.version} <span className="text-nominal">· Live</span></span> : "loading"} sub={prod?.model_type === "rules" ? "rule-based triage" : prod ? "learned triage" : ""} />
        <TopStat icon={<CalendarClock size={20} className="text-beam2" />} k="Last image" v={fmt.utc(last, false)}
          sub={last ? `${new Date(last).toISOString().slice(11, 16)} UTC · Sentinel-2` : ""} title="Latest usable image over the monitored areas. Sentinel-2 detects; Sentinel-3 cross-checks; 813 is simulated." />
        <TopStat icon={<Satellite size={20} className="text-cyan" />} k="Next pass" title="Expected next Sentinel-2 pass: the last pass plus whole 10-day repeat cycles. A schedule, not a promise."
          v={np ? `in ${np.inText}` : "n/a"} sub={np ? `${np.platform} · orbit ${np.orbit}` : "no schedule"} />
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
        <Link href="/judge" className="btn btn-primary whitespace-nowrap px-3 sm:px-[14px]" title="A guided three-minute tour of the whole loop, with real actions"><Presentation size={15} /><span className="hidden sm:inline">Judge Mode</span><span className="sm:hidden">Tour</span></Link>
        <div className="hidden whitespace-nowrap text-right lg:block">
          <div className="hud-value text-[20px] font-semibold text-ink">{now ? now.toISOString().slice(11, 19) : "--:--:--"} <span className="text-[11px] text-muted">UTC</span></div>
          <div className="text-[10.5px] text-muted">{now ? now.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }) : ""}</div>
        </div>
        <button onClick={() => { setDraft(op); setEdit(true); }} className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-line bg-panel2 text-[12px] font-bold text-ink hover:border-beam2" title={op ? `Operator: ${op}` : "Set your name"} aria-label={op ? `Operator: ${op}` : "Set your name"}>
          {op ? op.slice(0, 2).toUpperCase() : <UserRound size={18} />}
        </button>
      </div>
      <Modal open={edit} onClose={() => setEdit(false)} title="Your name" width={420}>
        <p className="mb-3 text-[12.5px] text-muted">Your reviews, samples and model approvals are saved under this name in the audit log.</p>
        <input className="mb-3 w-full rounded-md border border-line bg-deep px-3 py-2 text-[13px] outline-none focus:border-beam2" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. analyst.awaiz" maxLength={60} />
        <div className="flex justify-end gap-2">
          <button className="btn" onClick={() => setEdit(false)}>Cancel</button>
          <button className="btn btn-primary" disabled={!draft.trim()} onClick={() => { setOperator(draft); setEdit(false); toast(`Operator set: ${draft.trim()}`); }}>Save</button>
        </div>
      </Modal>
    </header>
  );
}

function TopStat({ icon, k, v, sub, title, className = "flex" }: { icon: React.ReactNode; k: string; v: React.ReactNode; sub?: React.ReactNode; title?: string; className?: string }) {
  return (
    <div className={`${className} min-w-0 flex-1 basis-0 items-center gap-3 rounded-lg border border-edge/70 bg-panel/60 px-3 py-2 short:py-1`} title={title}>
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-edge bg-deep short:h-8 short:w-8">{icon}</div>
      <div className="min-w-0 leading-tight">
        <div className="hud-kicker truncate">{k}</div>
        <div className="truncate text-[13.5px] font-semibold text-ink">{v}</div>
        {sub && <div className="truncate text-[10.5px] text-muted tiny:hidden">{sub}</div>}
      </div>
    </div>
  );
}

type RailState = "ok" | "attention" | "blocked" | "idle";
const RAIL_COLOR: Record<RailState, string> = { ok: "#23D484", attention: "#FFC23D", blocked: "#FF4D5E", idle: "#7088B3" };

function MissionRail({ incidents, aois, models, labels, className = "" }: { incidents: IncidentSummary[]; aois: Aoi[]; models: ModelRecord[]; labels: LabelRow[]; className?: string }) {
  const isActive = useIsActive();
  const open = incidents.filter((i) => ["DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED", "MONITORING"].includes(i.status) && i.role !== "negative_control");
  const review = incidents.filter((i) => ["DETECTED", "UNDER_REVIEW"].includes(i.status));
  const field = incidents.filter((i) => i.status === "FIELD_VALIDATION_REQUIRED");
  const prod = models.find((m) => m.status === "PRODUCTION");
  const cand = models.find((m) => m.status === "CANDIDATE");
  const newLabels = labels.filter((l) => l.source !== "cross_sensor_reference" && (!prod?.promoted_at || l.created_at > prod.promoted_at));
  const uae = aois.filter((a) => a.id.startsWith("AE-"));
  const items: { href: string; label: string; sub: string; icon: React.ReactNode; state: RailState; note: string; badge?: number }[] = [
    { href: "/watch", label: "WATCH", sub: "Monitoring", icon: <Binoculars size={22} />, state: uae.length ? "ok" : "idle", note: `${uae.length} areas` },
    { href: "/incidents", label: "DETECT", sub: "Incident queue", icon: <Radar size={22} />, state: review.length ? "attention" : "ok", note: `${open.length} open`, badge: open.length },
    { href: "/spectra", label: "DIAGNOSE", sub: "Colour fingerprint", icon: <Waves size={22} />, state: "ok", note: "S2 + 813 sim" },
    { href: "/field", label: "VERIFY", sub: "Field samples", icon: <ShieldCheck size={22} />, state: field.length ? "attention" : review.length ? "attention" : "ok", note: `${review.length} to review` },
    { href: "/incident", label: "ACT", sub: "Investigation", icon: <Siren size={22} />, state: open.length ? "attention" : "idle", note: open.length ? "actions due" : "none" },
    { href: "/learn", label: "LEARN", sub: "Model improvement", icon: <Sparkles size={22} />, state: cand ? "attention" : "ok", note: cand ? "new model ready" : `${newLabels.length} new labels` },
  ];
  const groups: { title: string; links: { href: string; label: string; icon: React.ReactNode }[] }[] = [
    { title: "Operations", links: [
      { href: "/intakes", label: "INTAKE WATCH", icon: <Factory size={16} /> },
      { href: "/assets", label: "ASSETS", icon: <Activity size={16} /> },
    ] },
    { title: "Evidence", links: [
      { href: "/validation", label: "VALIDATION", icon: <Gauge size={16} /> },
      { href: "/satellite", label: "SATELLITE VIEW", icon: <Satellite size={16} /> },
      { href: "/inland", label: "INLAND · SHAWKA", icon: <Droplets size={16} /> },
    ] },
    { title: "System", links: [
      { href: "/data", label: "DATA & SOURCES", icon: <Database size={16} /> },
      { href: "/api", label: "API", icon: <Code2 size={16} /> },
      { href: "/settings", label: "SETTINGS", icon: <Settings size={16} /> },
    ] },
  ];
  return (
    <nav aria-label="Main" className={`scroll-quiet shrink-0 flex-col gap-2 overflow-y-auto p-3 short:gap-1.5 short:p-2 mini:gap-1 ${className}`}>
      <Link href="/" aria-current={isActive("/") ? "page" : undefined} className={`flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-[11.5px] font-bold tracking-[0.14em] mini:py-1.5 ${isActive("/") ? "bg-beam/15 text-ink" : "text-muted hover:text-ink"}`}>
        <LayoutDashboard size={16} className="shrink-0" /> INCIDENT CONTROL
      </Link>
      {items.map((it) => {
        const active = isActive(it.href);
        return (
          <Link key={it.label} href={it.href} aria-current={active ? "page" : undefined}
            className={`group relative flex items-center gap-3 rounded-lg border px-3 py-3 transition short:py-2 mini:py-1.5 ${active ? "border-beam/70 bg-beam/10 shadow-beam" : "border-edge/70 bg-panel/50 hover:border-line"}`}>
            <span className="absolute bottom-2 left-0 top-2 w-[3px] rounded-r" style={{ background: RAIL_COLOR[it.state] }} />
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-edge bg-deep short:h-8 short:w-8 mini:h-7 mini:w-7" style={{ color: it.state === "idle" ? "#93A6CB" : RAIL_COLOR[it.state] }}>{it.icon}</span>
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block whitespace-nowrap font-display text-[14px] font-bold tracking-[0.1em] text-ink">{it.label}</span>
              <span className="block truncate text-[11px] text-muted">{it.sub}</span>
              <span className="block truncate text-[10px] tiny:hidden" style={{ color: RAIL_COLOR[it.state] }}>{it.note}</span>
            </span>
            {it.badge ? <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-critical-fill px-1.5 text-[11px] font-bold text-white" aria-label={`${it.badge} open incidents`}>{it.badge}</span> : null}
          </Link>
        );
      })}
      {groups.map((g) => (
        <div key={g.title} className="mt-1">
          <div className="rule-h mb-2 mini:mb-1" />
          <div className="hud-kicker mb-1 px-3">{g.title}</div>
          {g.links.map((n) => (
            <Link key={n.label} href={n.href} aria-current={isActive(n.href) ? "page" : undefined}
              className={`flex items-center gap-3 whitespace-nowrap rounded-md px-3 py-2 text-[11.5px] font-bold tracking-[0.12em] short:py-1.5 mini:py-1 ${isActive(n.href) ? "bg-beam/15 text-ink" : "text-muted hover:text-ink"}`}>
              <span className="shrink-0">{n.icon}</span><span className="min-w-0 truncate">{n.label}</span>
            </Link>
          ))}
        </div>
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
  // [value, label, colour, which widths show it]
  const stats: [string | number, string, string, string][] = [
    [open, "Active incidents", "#FF4D5E", "flex"], [uae.length, "Areas monitored", "#FFC23D", "flex"],
    [scenes7, "Images (7 days)", "#EAF1FF", "hidden lg:flex"], [queued, "New labels", "#27C3F3", "hidden xl:flex"],
  ];
  return (
    <footer className="flex h-[44px] shrink-0 items-center gap-4 overflow-hidden whitespace-nowrap border-t border-edge/70 bg-void/80 px-3 text-[11px] sm:px-4 short:h-[38px]">
      <div className="hidden items-center gap-2 font-bold tracking-[0.16em] text-muted sm:flex"><UaeFlag size={12} /> UAE COASTAL MONITORING</div>
      <div className="flex min-w-0 items-center gap-4 xl:gap-6">
        {stats.map(([v, k, c, show]) => (
          <div key={k} className={`${show} items-baseline gap-1.5`}><span className="hud-value text-[15px] font-bold" style={{ color: c }}>{v}</span><span className="text-muted">{k}</span></div>
        ))}
      </div>
      <div className="ml-auto flex min-w-0 items-center gap-4">
        <span className="hidden min-w-0 truncate text-muted 2xl:inline" title="Copernicus Sentinel-2/3 · Landsat · Planet Tanager (CC BY 4.0) · EnMAP · © OpenStreetMap contributors">Open data: Copernicus Sentinel-2/3 · Landsat · Planet Tanager (CC BY 4.0) · © OpenStreetMap</span>
        <a href={TEAM_URL} target="_blank" rel="noopener noreferrer" className="shrink-0 font-semibold text-ink hover:text-cyan">Built by <span className="text-cyan">Team Kanban</span></a>
      </div>
    </footer>
  );
}

/** The rail as a slide-in drawer below the lg breakpoint. */
function NavDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[65] bg-black/60 lg:hidden" onClick={onClose}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: reduce ? 0 : 0.18 }}>
          <motion.div role="dialog" aria-modal="true" aria-label="Navigation" className="relative flex h-full w-[272px] max-w-[86vw] flex-col border-r border-line bg-void"
            initial={{ x: reduce ? 0 : -280 }} animate={{ x: 0 }} exit={{ x: reduce ? 0 : -280 }} transition={{ duration: reduce ? 0 : 0.22, ease: "easeOut" }}
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-edge px-4 py-3">
              <span className="font-display text-[15px] font-bold tracking-[0.12em]">BLUEBAN <span className="text-cyan">813</span></span>
              <button onClick={onClose} className="grid h-9 w-9 place-items-center rounded-md border border-line text-muted hover:text-ink" aria-label="Close navigation"><X size={17} /></button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const d = useShellData();
  const path = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => { setNavOpen(false); }, [path]);
  return (
    // fixed + inset-0 (not 100vh) so the frame fills the window under the 90 % CSS zoom in globals.css
    <div className="fixed inset-0 flex flex-col overflow-hidden">
      <TopBar aois={d.aois} models={d.models} onMenu={() => setNavOpen(true)} />
      {/* thin progress line while the workspace loads, so empty panels never read as "no data" */}
      <div className="relative h-0.5 shrink-0 overflow-hidden" aria-hidden>
        {d.loading && <div className="sweep absolute inset-0 bg-gradient-to-r from-transparent via-cyan to-transparent" />}
      </div>
      <div className="flex min-h-0 flex-1">
        <MissionRail {...d} className="hidden w-[236px] border-r border-edge/70 bg-void/40 lg:flex" />
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
      <Footer {...d} />
      <NavDrawer open={navOpen} onClose={() => setNavOpen(false)}><MissionRail {...d} className="flex min-h-0 w-full flex-1" /></NavDrawer>
      <Toaster />
      <IntroSequence />
    </div>
  );
}
