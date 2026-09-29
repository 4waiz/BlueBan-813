"use client";
/**
 * SATELLITE VIEW: what each sensor contributes to the selected incident.
 * No invented spacecraft: without a permitted official 813 reference, the
 * visual is an abstract orbit + band-layout diagram drawn from the published
 * band configurations.
 */
import React, { useState } from "react";
import type { Incident } from "@/lib/engine/types";
import { fmt, SimBadge } from "@/components/ui";

type Key = "813" | "S2" | "S3" | "S1" | "LS";
const SENSORS: Record<Key, { name: string; kind: string; range: string; res: string; bands: [number, number][]; note: string; status: (i: Incident | null) => string }> = {
  "813": { name: "Satellite 813", kind: "Aquatic hyperspectral", range: "400 – 1700 nm", res: "20 m (spec) · ~205 bands", note: "No 813 product is accessible to the team (authenticated audit, 30 Sep 2026). Every 813 value shown is SIMULATED from real Planet Tanager-1 data.",
    bands: Array.from({ length: 64 }, (_, i) => [400 + i * 20, 6] as [number, number]), status: () => "SIMULATED" },
  S2: { name: "Sentinel-2 L2A", kind: "Multispectral, BOA reflectance", range: "443 – 2190 nm, 12 bands", res: "10 / 20 / 60 m · 2-5 day revisit", note: "Primary high-resolution detection sensor (mentor point 1-2). Sen2Cor L2A, glint-corrected by SWIR offset.",
    bands: [[443, 21], [492, 66], [560, 36], [665, 31], [704, 15], [740, 15], [783, 20], [833, 106], [865, 21], [1610, 91]], status: (i) => (i?.provenance?.sources || []).some((s) => (s.sensor || "").includes("Sentinel-2") || (s.satellite || "").includes("Sentinel-2")) ? "IN EVIDENCE" : "BASELINE" },
  S3: { name: "Sentinel-3 OLCI", kind: "Ocean colour, WFR L2", range: "400 – 1020 nm, 21 bands", res: "300 m · daily", note: "Wide-area context and cross-sensor reference (CHL_NN, TSM_NN), never ground truth. Planetary Computer archive ends 2026-02-23.",
    bands: [[400, 15], [412, 10], [443, 10], [490, 10], [510, 10], [560, 10], [620, 10], [665, 10], [674, 7], [681, 7], [709, 10], [754, 7], [779, 15], [865, 20], [885, 10], [900, 10], [940, 20], [1020, 40]], status: (i) => (i?.sensor_agreement && Object.keys(i.sensor_agreement).some((k) => k.includes("OLCI") || k.includes("S3"))) ? "CROSS-CHECK" : "CONTEXT" },
  S1: { name: "Sentinel-1 SAR", kind: "C-band SAR, VV/VH", range: "5.405 GHz", res: "10 m GRD · 6-12 day", note: "Optional surface-dark-anomaly mode. A dark patch is an oil-spill LOOKALIKE set (low wind, biogenic film, rain cell), never 'oil' on its own.",
    bands: [], status: (i) => (i?.sensor_agreement && Object.keys(i.sensor_agreement).some((k) => k.includes("SAR") || k.includes("S1"))) ? "IN EVIDENCE" : "OPTIONAL" },
  LS: { name: "Landsat 8/9", kind: "OLI + TIRS", range: "443 – 2200 nm + 10.9 µm thermal", res: "30 m / 100 m thermal · 8 day", note: "Thermal context (surface temperature). Not used in any reported number unless listed in the incident's provenance.",
    bands: [[443, 16], [482, 60], [561, 57], [655, 37], [865, 28], [1609, 85], [2201, 187]], status: () => "CONTEXT" },
};

export default function SensorCard({ incident }: { incident: Incident | null }) {
  const [k, setK] = useState<Key>("813");
  const s = SENSORS[k];
  const W = 300, H = 120;
  const x = (nm: number) => 12 + ((nm - 400) / 1300) * (W - 24);
  return (
    <div className="flex h-full flex-col">
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border border-edge bg-[radial-gradient(ellipse_at_70%_120%,#0b3a8a_0%,#061126_45%,#040915_70%)]">
        <svg viewBox="0 0 400 220" className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid slice" aria-hidden>
          <defs><radialGradient id="earth" cx="0.5" cy="1.4" r="1.2"><stop offset="0.55" stopColor="#1a5fd1" stopOpacity="0.9" /><stop offset="0.62" stopColor="#0b2a57" stopOpacity="0.8" /><stop offset="0.7" stopColor="#040915" stopOpacity="0" /></radialGradient></defs>
          <ellipse cx="200" cy="330" rx="330" ry="170" fill="url(#earth)" />
          <path d="M-20 150 Q200 40 420 120" stroke="#27C3F3" strokeWidth="1" fill="none" strokeDasharray="4 4" opacity="0.7" />
          <g transform="translate(250 78)">
            <rect x="-10" y="-6" width="20" height="12" rx="2" fill="#0D1C3B" stroke="#4D93FF" />
            <rect x="-42" y="-4" width="28" height="8" fill="#16284D" stroke="#2F7BFF" /><rect x="14" y="-4" width="28" height="8" fill="#16284D" stroke="#2F7BFF" />
            <path d="M0 6 L-26 110 L26 110 Z" fill="#27C3F3" opacity="0.08" />
          </g>
          <text x="14" y="206" fill="#5D7299" fontSize="9">abstract sensor diagram · not the spacecraft's design</text>
        </svg>
        <div className="absolute left-3 top-3">
          <div className="font-display text-[17px] font-bold text-ink">{s.name} {k === "813" && <SimBadge />}</div>
          <div className="text-[12px] text-cyan">{s.kind}</div>
          <div className="mt-2 text-[12px] text-ink">{s.range}</div>
          <div className="text-[12px] text-muted">{s.res}</div>
          <div className="mt-1 text-[10.5px] font-bold tracking-wider text-caution">{s.status(incident)}</div>
        </div>
        {s.bands.length > 0 && (
          <svg viewBox={`0 0 ${W} ${H}`} className="absolute bottom-1 right-1 h-[54px] w-[62%]" aria-label="band layout">
            {s.bands.map(([c, fw], i) => <rect key={i} x={x(c - fw / 2)} y={40} width={Math.max(1.2, x(c + fw / 2) - x(c - fw / 2))} height={46} fill={c < 700 ? "#27C3F3" : c < 1000 ? "#4D93FF" : "#8B7BFF"} opacity={0.75} />)}
            {[400, 700, 1000, 1300, 1700].map((t) => <text key={t} x={x(t)} y={104} fill="#5D7299" fontSize="10" textAnchor="middle">{t}</text>)}
          </svg>
        )}
      </div>
      <p className="mt-2 line-clamp-2 text-[10.5px] leading-snug text-muted short:hidden" title={s.note}>{s.note}</p>
      <div className="mt-2 grid grid-cols-5 gap-1">
        {(Object.keys(SENSORS) as Key[]).map((key) => (
          <button key={key} onClick={() => setK(key)} className={`rounded-md border px-1 py-1.5 text-[11px] font-semibold ${k === key ? "border-beam bg-beam/20 text-ink shadow-beam" : "border-edge text-muted hover:text-ink"}`}>
            {key === "LS" ? "Landsat" : key === "813" ? "813" : SENSORS[key].name.split(" ")[0].replace("Sentinel-", "S-")}
          </button>
        ))}
      </div>
      {incident && <div className="mt-1 text-[10px] text-dim short:hidden">Incident observed {fmt.utc(incident.observation_time)}</div>}
    </div>
  );
}
