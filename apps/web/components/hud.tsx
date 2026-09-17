"use client";

/**
 * HUD primitives: the instrument vocabulary the whole interface is built from.
 *
 * The design language is borrowed from aerospace flight-control displays -
 * thin instrumentation rules, chamfered panels, monospaced telemetry, colour
 * used only to carry state. None of it is decorative: if a colour appears, it
 * means something.
 */

import React, { useEffect, useRef, useState } from "react";

import { useCountUp, prefersReducedMotion } from "@/lib/motion";

/* ------------------------------------------------------------------ panels */

export function Panel({
  title, right, children, className = "", tight = false, accent,
  delay = 0, boot = false,
}: {
  title?: string; right?: React.ReactNode; children: React.ReactNode;
  className?: string; tight?: boolean; accent?: string;
  delay?: number; boot?: boolean;
}) {
  return (
    <section
      className={`panel chamfer relative panel-in ${boot ? "boot-scan" : ""} ${className}`}
      style={{ animationDelay: `${delay}ms` }}>
      {accent && (
        <span className="absolute left-0 top-0 h-full w-[2px]"
              style={{ background: accent, boxShadow: `0 0 12px -2px ${accent}` }} />
      )}
      {title && (
        <header className="flex items-center justify-between gap-3 px-3 pt-2.5 pb-1.5">
          <h2 className="hud-label truncate">{title}</h2>
          {right}
        </header>
      )}
      {title && <div className="rule-h mx-3" />}
      <div className={tight ? "p-2" : "p-3"}>{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------- status atoms */

export function StatusDot({ color, pulse = false, size = 7 }:
  { color: string; pulse?: boolean; size?: number }) {
  return (
    <span className="relative inline-flex items-center justify-center"
          style={{ width: size + 6, height: size + 6 }}>
      {pulse && (
        <span className="pulse-ring absolute rounded-full"
              style={{ width: size, height: size, background: color, opacity: 0.6 }} />
      )}
      <span className="relative rounded-full"
            style={{ width: size, height: size, background: color,
                     boxShadow: `0 0 10px -1px ${color}` }} />
    </span>
  );
}

export function Chip({ label, color = "#5A6490", filled = false }:
  { label: string; color?: string; filled?: boolean }) {
  return (
    <span
      className="chamfer-sm hud-label px-2 py-[3px] whitespace-nowrap"
      style={{
        color: filled ? "#070A16" : color,
        background: filled ? color : "transparent",
        border: `1px solid ${color}`,
        letterSpacing: "0.14em",
      }}
    >
      {label}
    </span>
  );
}

/* ----------------------------------------------------------- readouts */

export function Readout({
  label, value, unit, sub, color = "#F4F6FF", size = "md", mono = true,
  animate, digits = 2,
}: {
  label: string; value: React.ReactNode; unit?: string; sub?: string;
  color?: string; size?: "sm" | "md" | "lg" | "xl"; mono?: boolean;
  /** When given, the number counts up to this value instead of appearing. */
  animate?: number | null; digits?: number;
}) {
  const sizes = { sm: "text-[15px]", md: "text-[21px]", lg: "text-[30px]", xl: "text-[44px]" };
  const counted = useCountUp(animate ?? null, animate === undefined ? 0 : 900);
  const shown = animate !== undefined && animate !== null && Number.isFinite(counted)
    ? counted.toFixed(digits)
    : value;
  return (
    <div className="min-w-0">
      <div className="hud-label mb-1 truncate">{label}</div>
      <div className={`${mono ? "hud-value" : ""} ${sizes[size]} leading-none flex items-baseline gap-1.5`}
           style={{ color }}>
        <span className="truncate">{shown}</span>
        {unit && <span className="text-[10px] text-dim tracking-wide2 shrink-0">{unit}</span>}
      </div>
      {sub && <div className="hud-label mt-1.5 truncate" style={{ letterSpacing: "0.1em" }}>{sub}</div>}
    </div>
  );
}

/**
 * Horizontal telemetry bar: label, thin meter, value.
 *
 * Deliberately not a rounded card. Flight displays put the number on a rule,
 * not in a box.
 */
export function Meter({
  label, value, min = 0, max = 1, display, unit, color = "#3186FF",
  marker, markerLabel, hint,
}: {
  label: string; value: number | null | undefined; min?: number; max?: number;
  display?: string; unit?: string; color?: string;
  marker?: number; markerLabel?: string; hint?: string;
}) {
  const ok = value !== null && value !== undefined && Number.isFinite(value);
  const anim = useCountUp(ok ? (value as number) : null, 850);
  const shownVal = ok && Number.isFinite(anim) ? anim : (value as number);
  const frac = ok ? Math.max(0, Math.min(1, (shownVal - min) / (max - min))) : 0;
  const mfrac = marker !== undefined ? Math.max(0, Math.min(1, (marker - min) / (max - min))) : null;
  return (
    <div className="py-[7px] group" title={hint}>
      <div className="flex items-baseline justify-between gap-2 mb-[5px]">
        <span className="hud-label truncate">{label}</span>
        <span className="hud-value text-[12px] shrink-0" style={{ color: ok ? "#F4F6FF" : "#5A6490" }}>
          {display ?? (ok ? (value as number).toFixed(2) : "-")}
          {unit && <span className="text-dim text-[9px] ml-1">{unit}</span>}
        </span>
      </div>
      <div className="relative h-[3px] bg-edge/70 group-hover:h-[5px] transition-[height] duration-150">
        <div className="absolute inset-y-0 left-0"
             style={{ width: `${frac * 100}%`, background: color,
                      boxShadow: `0 0 8px -2px ${color}` }} />
        {mfrac !== null && (
          <div className="absolute -top-[3px] h-[9px] w-[1px] bg-muted/80"
               style={{ left: `${mfrac * 100}%` }} title={markerLabel} />
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- sequence */

export type SeqState = "done" | "active" | "warn" | "pending" | "vetoed";

const SEQ: Record<SeqState, { glyph: string; color: string }> = {
  done:    { glyph: "✓", color: "#3FD1A0" },
  active:  { glyph: "●", color: "#3186FF" },
  warn:    { glyph: "⚠", color: "#F5C451" },
  vetoed:  { glyph: "⊘", color: "#4A93FF" },
  pending: { glyph: "○", color: "#5A6490" },
};

export function SequenceItem({
  state, name, detail, onClick, active = false,
}: {
  state: SeqState; name: string; detail: string;
  onClick?: () => void; active?: boolean;
}) {
  const s = SEQ[state];
  return (
    <button
      onClick={onClick}
      className={`group w-full text-left flex gap-2.5 px-2.5 py-[9px] transition-colors
                  ${active ? "bg-beam/10" : "hover:bg-white/[0.035]"}`}
      style={active ? { boxShadow: "inset 2px 0 0 #3186FF" } : undefined}
    >
      <span className="hud-value text-[13px] leading-none mt-[2px] shrink-0 w-3 text-center"
            style={{ color: s.color }}>
        {state === "active" ? <span className="blink-soft">{s.glyph}</span> : s.glyph}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[10.5px] font-medium tracking-wide2 uppercase text-ink truncate">
          {name}
        </span>
        <span className="block hud-label mt-[3px] normal-case truncate"
              style={{ letterSpacing: "0.06em", color: "#6E78A0" }}>
          {detail}
        </span>
      </span>
    </button>
  );
}

/* ----------------------------------------------------------------- gauges */

/**
 * Circular instrument. Thin dotted circumference, a coloured arc for the value,
 * and a tabular-numeral centre. Modelled on a spacecraft attitude readout
 * rather than a dashboard donut chart.
 */
export function Gauge({
  label, value, min = 0, max = 1, display, unit, color = "#3186FF",
  size = 108, sub, danger, hint, digits = 2,
}: {
  label: string; value: number | null | undefined; min?: number; max?: number;
  display?: string; unit?: string; color?: string; size?: number;
  sub?: string; danger?: boolean; hint?: string; digits?: number;
}) {
  const ok = value !== null && value !== undefined && Number.isFinite(value);
  const anim = useCountUp(ok ? (value as number) : null, 1050);
  const live = ok && Number.isFinite(anim) ? anim : (value as number);
  const frac = ok ? Math.max(0, Math.min(1, (live - min) / (max - min))) : 0;
  const R = size / 2 - 11;
  const C = 2 * Math.PI * R;
  // 270 degree sweep starting at the 7-o'clock position.
  const SWEEP = 0.75;
  const arc = C * SWEEP;

  return (
    <div className="flex flex-col items-center gap-1.5 select-none group"
         title={hint}>
      <svg width={size} height={size} className="overflow-visible
                 transition-transform duration-200 group-hover:scale-[1.035]">
        <g transform={`rotate(135 ${size / 2} ${size / 2})`}>
          <circle cx={size / 2} cy={size / 2} r={R} fill="none"
                  stroke="#1B2444" strokeWidth={5}
                  strokeDasharray={`${arc} ${C}`} strokeLinecap="butt" />
          <circle cx={size / 2} cy={size / 2} r={R} fill="none"
                  stroke={color} strokeWidth={5}
                  strokeDasharray={`${arc * frac} ${C}`} strokeLinecap="butt"
                  style={{ filter: `drop-shadow(0 0 5px ${color}66)` }} />
        </g>
        {/* dotted outer ring */}
        <circle cx={size / 2} cy={size / 2} r={R + 7} fill="none"
                stroke="#243056" strokeWidth={1} strokeDasharray="1 4" opacity={0.85} />
        {/* minor ticks */}
        {Array.from({ length: 13 }).map((_, i) => {
          const a = (135 + (270 * i) / 12) * (Math.PI / 180);
          const r1 = R - 8.5, r2 = R - 5;
          return (
            <line key={i}
                  x1={size / 2 + r1 * Math.cos(a)} y1={size / 2 + r1 * Math.sin(a)}
                  x2={size / 2 + r2 * Math.cos(a)} y2={size / 2 + r2 * Math.sin(a)}
                  stroke="#243056" strokeWidth={1} />
          );
        })}
        <text x={size / 2} y={size / 2 + 2} textAnchor="middle"
              className="hud-value"
              style={{ fontSize: size > 96 ? 20 : 16, fill: ok ? "#F4F6FF" : "#5A6490" }}>
          {display ?? (ok ? live.toFixed(digits) : "-")}
        </text>
        {unit && (
          <text x={size / 2} y={size / 2 + 16} textAnchor="middle"
                className="hud-label" style={{ fontSize: 8, fill: "#5A6490" }}>
            {unit}
          </text>
        )}
        {danger && (
          <circle cx={size / 2} cy={11} r={2.5} fill="#FF4D4D" className="blink-soft" />
        )}
      </svg>
      <div className="hud-label text-center leading-tight max-w-[120px]">{label}</div>
      {sub && <div className="hud-label text-center" style={{ color: "#4A5478" }}>{sub}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ tables */

export function KV({ k, v, mono = true, color }:
  { k: string; v: React.ReactNode; mono?: boolean; color?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[5px] border-b border-edge/40 last:border-0">
      <span className="hud-label shrink-0">{k}</span>
      <span className={`${mono ? "hud-value" : ""} text-[11.5px] text-right break-words min-w-0`}
            style={{ color: color ?? "#C9D0EE" }}>
        {v}
      </span>
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center gap-2">
      <div className="hud-label" style={{ color: "#4A5478" }}>{title}</div>
      {hint && <div className="text-[11px] text-dim max-w-sm leading-relaxed">{hint}</div>}
    </div>
  );
}

export function Loading({ what = "telemetry" }: { what?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      <div className="relative w-36 h-[2px] bg-edge overflow-hidden">
        <div className="sweep absolute inset-y-0 w-1/3"
             style={{ background: "linear-gradient(90deg,transparent,#3186FF,transparent)" }} />
      </div>
      <div className="hud-label">acquiring {what}</div>
    </div>
  );
}

export function ErrorBox({ error, hint }: { error: string; hint?: string }) {
  return (
    <div className="panel-quiet chamfer p-4 border-alert/40">
      <div className="hud-label mb-1.5" style={{ color: "#FF7A45" }}>signal lost</div>
      <div className="hud-value text-[11.5px] text-ink/90 break-words">{error}</div>
      {hint && <div className="text-[11px] text-dim mt-2.5 leading-relaxed">{hint}</div>}
    </div>
  );
}

/** Small inline warning used wherever a scientific caveat must travel with a number. */
export function Caveat({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 items-start mt-2 px-2.5 py-2 chamfer-sm"
         style={{ background: "rgba(245,196,81,0.07)", border: "1px solid rgba(245,196,81,0.22)" }}>
      <span className="text-caution text-[11px] leading-none mt-[2px]">⚠</span>
      <span className="text-[10.5px] leading-[1.5] text-caution/90">{children}</span>
    </div>
  );
}

/** The label that must appear anywhere simulated 813 data is shown. */
export function SimulatedBadge({ compact = false }: { compact?: boolean }) {
  return (
    <span className="chamfer-sm hud-label px-2 py-[3px] inline-flex items-center gap-1.5"
          style={{ color: "#4A93FF", border: "1px solid rgba(74,147,255,0.45)",
                   background: "rgba(74,147,255,0.08)" }}>
      <span style={{ fontSize: 9 }}>◇</span>
      {compact ? "SIM" : "813 SIMULATED"}
    </span>
  );
}
