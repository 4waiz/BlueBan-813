"use client";
/**
 * UI primitives. Colour carries state only; everything else is the neutral
 * mission-control palette defined in tailwind.config.ts.
 */
import React, { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { HelpCircle, X } from "lucide-react";
import { createPortal } from "react-dom";

export const STATE_COLOR: Record<string, string> = {
  MONITORING: "#93A6CB", DETECTED: "#FFC23D", UNDER_REVIEW: "#FF4D5E",
  FIELD_VALIDATION_REQUIRED: "#FF8A3D", CONFIRMED: "#23D484", FALSE_POSITIVE: "#8B7BFF", RESOLVED: "#5D7299",
  PRODUCTION: "#23D484", CANDIDATE: "#FFC23D", REJECTED: "#FF4D5E", RETIRED: "#5D7299", STAGING: "#27C3F3", TRAINING: "#4D93FF",
  SUCCEEDED: "#23D484", FAILED: "#FF4D5E", RUNNING: "#4D93FF", QUEUED: "#93A6CB",
  PLANNED: "#93A6CB", COLLECTED: "#27C3F3", LAB_PENDING: "#FFC23D", RESULT_RECEIVED: "#23D484",
  HIGH: "#FF4D5E", MEDIUM: "#FFC23D", LOW: "#23D484", NONE: "#5D7299",
};

export function Panel({ title, right, children, className = "", bodyClass = "", kicker }: {
  title?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string; bodyClass?: string; kicker?: string;
}) {
  return (
    <section className={`panel flex min-h-0 flex-col ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 px-4 pb-2 pt-3">
          <div className="min-w-0">
            {kicker && <div className="hud-kicker">{kicker}</div>}
            {title && <h2 className="panel-title truncate">{title}</h2>}
          </div>
          {right}
        </header>
      )}
      <div className={`min-h-0 flex-1 ${bodyClass}`}>{children}</div>
    </section>
  );
}

/** Plain words for workflow codes; the code still picks the colour. */
export const STATE_TEXT: Record<string, string> = {
  DETECTED: "New", UNDER_REVIEW: "Under review", FIELD_VALIDATION_REQUIRED: "Needs field check", FALSE_POSITIVE: "False alarm",
  PRODUCTION: "Live", CANDIDATE: "New model", LAB_PENDING: "At the lab", RESULT_RECEIVED: "Result in", INSUFFICIENT_EVIDENCE: "Inconclusive",
};

/** Sentence-case plain words for any workflow code (for selects, popups and toasts). */
export function statusText(code: string): string {
  const t = STATE_TEXT[code] ?? code.replace(/_/g, " ").toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1).toLowerCase();
}

export function Chip({ label, color, dot = true, className = "" }: { label: string; color?: string; dot?: boolean; className?: string }) {
  const c = color || STATE_COLOR[label] || "#93A6CB";
  return (
    <span className={`chip ${className}`} style={{ color: c, borderColor: `${c}66`, background: `${c}14` }}>
      {dot && <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} />}
      {STATE_TEXT[label] ?? label.replace(/_/g, " ")}
    </span>
  );
}

export function Dot({ color = "#23D484", pulse = false, size = 8 }: { color?: string; pulse?: boolean; size?: number }) {
  return (
    <span className="relative inline-flex" style={{ width: size, height: size }}>
      {pulse && <span className="pulse-ring absolute inset-0 rounded-full" style={{ background: color }} />}
      <span className="relative inline-flex rounded-full" style={{ width: size, height: size, background: color, boxShadow: `0 0 10px ${color}` }} />
    </span>
  );
}

export function Meter({ value, color = "#2F7BFF", max = 1 }: { value: number | null | undefined; color?: string; max?: number }) {
  const v = value == null || !Number.isFinite(value) ? 0 : Math.max(0, Math.min(1, value / max));
  return <div className="meter"><i style={{ width: `${v * 100}%`, background: `linear-gradient(90deg, ${color}99, ${color})` }} /></div>;
}

export function Tabs<T extends string>({ tabs, value, onChange, className = "" }: { tabs: { key: T; label: string }[]; value: T; onChange: (t: T) => void; className?: string }) {
  return (
    <div className={`flex gap-1 overflow-x-auto border-b border-edge ${className}`}>
      {tabs.map((t) => (
        <button key={t.key} className="tab" data-active={t.key === value} onClick={() => onChange(t.key)}>{t.label}</button>
      ))}
    </div>
  );
}

/** Numbers ease into new values instead of snapping (state changes read as motion). */
export function Tween({ value, digits = 2, suffix = "", className = "" }: { value: number | null | undefined; digits?: number; suffix?: string; className?: string }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState<number | null>(value ?? null);
  useEffect(() => {
    if (value == null || !Number.isFinite(value)) { setShown(null); return; }
    if (reduce || shown == null) { setShown(value); return; }
    const from = shown, to = value, t0 = performance.now(), dur = 320;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / dur);
      setShown(from + (to - from) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  return <span className={`hud-value ${className}`}>{shown == null ? "n/a" : `${shown.toFixed(digits)}${suffix}`}</span>;
}

export function Kind({ kind }: { kind?: string }) {
  if (!kind) return null;
  const map: Record<string, [string, string, string]> = {
    PROXY: ["PROXY", "#93A6CB", "An index, not a measured concentration"],
    GENERIC_CALIBRATION: ["APPROX.", "#FFC23D", "Published generic formula, not checked against UAE water samples"],
    CALIBRATED: ["CALIBRATED", "#23D484", "Calibrated against local water samples"],
    COLORIMETRIC: ["COLOUR", "#27C3F3", "A measure of water colour"],
  };
  const [l, c, tip] = map[kind] || [kind, "#93A6CB", ""];
  return <span title={tip || undefined} className="rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider" style={{ color: c, background: `${c}18`, border: `1px solid ${c}44` }}>{l}</span>;
}

export function SimBadge({ text = "813 SIMULATED" }: { text?: string }) {
  return <span className="rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-caution" style={{ background: "#FFC23D18", border: "1px solid #FFC23D55" }}>{text}</span>;
}

/** "Why am I seeing this?" - opens the evidence chain for any displayed number. */
export function WhyButton({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)} className="inline-flex items-center gap-1 text-[10.5px] font-semibold text-beam2 hover:text-cyan" title="Why am I seeing this?">
        <HelpCircle size={12} /> Why?
      </button>
      <Drawer open={open} onClose={() => setOpen(false)} title={title}>{children}</Drawer>
    </>
  );
}

/**
 * Overlays render into <body>. Any ancestor with backdrop-filter (the top bar,
 * every .panel) becomes the containing block of position: fixed, which would
 * otherwise clip a dialog to that box and let later content cover it.
 */
function BodyPortal({ children }: { children: React.ReactNode }) {
  const [el, setEl] = useState<HTMLElement | null>(null);
  useEffect(() => { setEl(document.body); }, []);
  return el ? createPortal(children, el) : null;
}

export function Drawer({ open, onClose, title, children, width = 520 }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; width?: number }) {
  return (
    <BodyPortal><AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[60] flex justify-end bg-black/50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.aside className="panel h-full overflow-y-auto rounded-none border-l border-line p-5" style={{ width }}
            initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }} transition={{ duration: 0.22, ease: "easeOut" }}
            onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="panel-title">{title}</h3>
              <button onClick={onClose} className="text-muted hover:text-ink" aria-label="Close"><X size={18} /></button>
            </div>
            {children}
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence></BodyPortal>
  );
}

export function Modal({ open, onClose, title, children, width = 560 }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; width?: number }) {
  return (
    <BodyPortal><AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[70] grid place-items-center bg-black/60 p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div className="panel max-h-[88vh] w-full overflow-y-auto p-5" style={{ maxWidth: width }}
            initial={{ y: 12, opacity: 0, scale: 0.98 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 8, opacity: 0 }} transition={{ duration: 0.2 }}
            onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="panel-title">{title}</h3>
              <button onClick={onClose} className="text-muted hover:text-ink" aria-label="Close"><X size={18} /></button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence></BodyPortal>
  );
}

// ---------------------------------------------------------------- toasts
type Toast = { id: number; text: string; tone: "ok" | "err" | "info" };
const toastListeners = new Set<(t: Toast) => void>();
let tid = 0;
export function toast(text: string, tone: Toast["tone"] = "ok") { const t = { id: ++tid, text, tone }; toastListeners.forEach((f) => f(t)); }
export function Toaster() {
  const [items, setItems] = useState<Toast[]>([]);
  useEffect(() => {
    const f = (t: Toast) => { setItems((x) => [...x, t]); setTimeout(() => setItems((x) => x.filter((y) => y.id !== t.id)), 4200); };
    toastListeners.add(f);
    return () => { toastListeners.delete(f); };
  }, []);
  return (
    <div className="pointer-events-none fixed bottom-16 right-5 z-[80] flex flex-col gap-2">
      <AnimatePresence>
        {items.map((t) => (
          <motion.div key={t.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 20 }}
            className="panel pointer-events-auto max-w-sm px-4 py-3 text-[12.5px]"
            style={{ borderColor: t.tone === "err" ? "#FF4D5E88" : t.tone === "ok" ? "#23D48488" : "#2F7BFF88" }}>
            {t.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

export const fmt = {
  num: (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? "n/a" : v.toFixed(d)),
  pct: (v: number | null | undefined, d = 0) => (v == null || !Number.isFinite(v) ? "n/a" : `${(v * 100).toFixed(d)}%`),
  ord: (v: number | null | undefined) => {
    if (v == null || !Number.isFinite(v)) return "n/a";
    const n = Math.round(v), s = ["th", "st", "nd", "rd"], m = n % 100;
    return `${n}${s[(m - 20) % 10] || s[m] || s[0]}`;
  },
  utc: (s?: string | null, withTime = true) => {
    if (!s) return "n/a";
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return s;
    const day = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
    return withTime ? `${day} · ${d.toISOString().slice(11, 16)} UTC` : day;
  },
  km: (m?: number | null) => (m == null ? "n/a" : m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`),
};
