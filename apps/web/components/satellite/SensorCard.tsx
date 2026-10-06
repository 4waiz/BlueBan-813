"use client";
/**
 * SATELLITE VIEW: what each sensor contributes to the selected incident.
 * No invented spacecraft: without a permitted official 813 reference, the
 * visual is an abstract orbit + band-layout diagram drawn from the published
 * band configurations.
 */
import React, { useState } from "react";
import Link from "next/link";
import { Maximize2 } from "lucide-react";
import type { Incident } from "@/lib/engine/types";
import { bandColor, SENSORS } from "@/lib/sensors";
import { fmt, SimBadge } from "@/components/ui";

type Key = "813" | "S2" | "S3" | "S1" | "LS";
const CARD_KEYS: Key[] = ["813", "S2", "S3", "S1", "LS"];

export default function SensorCard({ incident }: { incident: Incident | null }) {
  const [k, setK] = useState<Key>("813");
  const s = SENSORS[k];
  const W = 300, H = 46;
  const x = (nm: number) => 12 + ((nm - 400) / 1300) * (W - 24);
  return (
    <div className="flex h-full flex-col">
      {/* Everything sits in normal flow on top of the decorative background, so
          nothing can overlap: on a short card the band strip is clipped instead. */}
      <div className="relative flex min-h-0 flex-1 flex-col gap-1 overflow-hidden rounded-md border border-edge bg-[radial-gradient(ellipse_at_70%_120%,#0b3a8a_0%,#061126_45%,#040915_70%)] p-3"
        title="Illustration, not the real spacecraft">
        <svg viewBox="0 0 400 220" className="pointer-events-none absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid slice" aria-hidden>
          <defs><radialGradient id="earth" cx="0.5" cy="1.4" r="1.2"><stop offset="0.55" stopColor="#1a5fd1" stopOpacity="0.9" /><stop offset="0.62" stopColor="#0b2a57" stopOpacity="0.8" /><stop offset="0.7" stopColor="#040915" stopOpacity="0" /></radialGradient></defs>
          <ellipse cx="200" cy="330" rx="330" ry="170" fill="url(#earth)" />
          <path d="M-20 150 Q200 40 420 120" stroke="#27C3F3" strokeWidth="1" fill="none" strokeDasharray="4 4" opacity="0.7" />
          <g transform="translate(330 70)" opacity="0.55">
            <rect x="-10" y="-6" width="20" height="12" rx="2" fill="#0D1C3B" stroke="#4D93FF" />
            <rect x="-42" y="-4" width="28" height="8" fill="#16284D" stroke="#2F7BFF" /><rect x="14" y="-4" width="28" height="8" fill="#16284D" stroke="#2F7BFF" />
            <path d="M0 6 L-26 110 L26 110 Z" fill="#27C3F3" opacity="0.08" />
          </g>
        </svg>
        <div className="relative flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-display text-[17px] font-bold leading-tight text-ink tiny:text-[15px]">
              <span className="whitespace-nowrap">{s.name}</span>{k === "813" && <SimBadge text="SIMULATED" />}
            </div>
            <div className="line-clamp-2 text-[12px] leading-snug text-cyan tiny:line-clamp-1" title={s.kind}>{s.kind}</div>
          </div>
          <Link href={`/satellite?sensor=${k}`} className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-edge bg-void/70 px-2 py-1 text-[10.5px] font-semibold text-muted backdrop-blur hover:border-beam hover:text-ink" title="Open the full-screen 3D view: real orbits, coverage and UAE passes">
            <Maximize2 size={12} /> 3D orbits
          </Link>
        </div>
        <div className="relative min-w-0 leading-snug">
          <div className="truncate text-[12px] text-ink">{s.range}<span className="hidden text-muted mini:inline"> · {s.res}</span></div>
          <div className="truncate text-[12px] text-muted mini:hidden">{s.res}</div>
          {k !== "813" && <div className="mt-0.5 truncate text-[10.5px] font-bold tracking-wider text-caution">{s.status(incident)}</div>}
        </div>
        {s.bands.length > 0 && (
          <svg viewBox={`0 0 ${W} ${H}`} className="relative mt-auto h-[40px] w-full shrink-0 tiny:hidden" aria-label="spectral bands">
            {s.bands.map(([c, fw], i) => <rect key={i} x={x(c - fw / 2)} y={2} width={Math.max(1.2, x(c + fw / 2) - x(c - fw / 2))} height={28} fill={bandColor(c)} opacity={0.75} />)}
            {[400, 700, 1000, 1300, 1700].map((t) => <text key={t} x={x(t)} y={44} fill="#7088B3" fontSize="12" textAnchor="middle">{t}</text>)}
          </svg>
        )}
      </div>
      <p className="mt-2 line-clamp-2 text-[10.5px] leading-snug text-muted short:hidden" title={s.note}>{s.note}</p>
      <div className="mt-2 grid grid-cols-5 gap-1">
        {CARD_KEYS.map((key) => (
          <button key={key} onClick={() => setK(key)} className={`rounded-md border px-1 py-1.5 text-[11px] font-semibold ${k === key ? "border-beam bg-beam/20 text-ink shadow-beam" : "border-edge text-muted hover:text-ink"}`}>
            {key === "LS" ? "Landsat" : key === "813" ? "813" : SENSORS[key].name.split(" ")[0].replace("Sentinel-", "S-")}
          </button>
        ))}
      </div>
      {incident && <div className="mt-1 text-[10px] text-dim short:hidden">Incident observed {fmt.utc(incident.observation_time)}</div>}
    </div>
  );
}
