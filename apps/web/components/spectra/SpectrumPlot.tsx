"use client";
import React, { useMemo, useRef, useState } from "react";

export interface Spectrum {
  wavelengths_nm: number[]; event: (number | null)[]; background: (number | null)[];
  background_p05?: (number | null)[]; background_p95?: (number | null)[]; sensor?: string; simulated?: boolean;
}

const S2_BANDS: [string, number, number][] = [["B1", 443, 21], ["B2", 492, 66], ["B3", 560, 36], ["B4", 665, 31], ["B5", 704, 15], ["B6", 740, 15], ["B7", 783, 20], ["B8", 833, 106], ["B8A", 865, 21], ["B11", 1610, 91]];
export const DIAGNOSTIC: [number, string][] = [[443, "Chl-a Soret"], [620, "Phycocyanin"], [665, "Sediment / red"], [675, "Chl-a red absorption"], [705, "Red-edge peak"]];

export default function SpectrumPlot({ spec, height = 240, showBands = true, showDiff = false, range = [400, 900], highlight }: {
  spec: Spectrum; height?: number; showBands?: boolean; showDiff?: boolean; range?: [number, number]; highlight?: number | null;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const W = 560, H = height, L = 44, R = 12, T = 12, B = 26;
  const idx = useMemo(() => spec.wavelengths_nm.map((w, i) => i).filter((i) => spec.wavelengths_nm[i] >= range[0] && spec.wavelengths_nm[i] <= range[1]), [spec, range]);
  const vals = idx.flatMap((i) => [spec.event[i], spec.background[i], spec.background_p95?.[i]]).filter((v): v is number => v != null && Number.isFinite(v));
  const ymax = Math.max(0.01, ...vals) * 1.08, ymin = Math.min(0, ...vals);
  const x = (w: number) => L + ((w - range[0]) / (range[1] - range[0])) * (W - L - R);
  const y = (v: number) => T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B);
  const path = (arr: (number | null)[]) => {
    let d = "", pen = false;
    for (const i of idx) { const v = arr[i]; if (v == null || !Number.isFinite(v)) { pen = false; continue; } d += `${pen ? "L" : "M"}${x(spec.wavelengths_nm[i]).toFixed(1)},${y(v).toFixed(1)}`; pen = true; }
    return d;
  };
  const env = spec.background_p05 && spec.background_p95 ? (() => {
    const up = idx.filter((i) => spec.background_p95![i] != null).map((i) => `${x(spec.wavelengths_nm[i])},${y(spec.background_p95![i]!)}`);
    const dn = idx.filter((i) => spec.background_p05![i] != null).reverse().map((i) => `${x(spec.wavelengths_nm[i])},${y(spec.background_p05![i]!)}`);
    return `M${up.join("L")}L${dn.join("L")}Z`;
  })() : null;
  const onMove = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const w = range[0] + ((px - L) / (W - L - R)) * (range[1] - range[0]);
    let best = idx[0], bd = Infinity;
    for (const i of idx) { const d = Math.abs(spec.wavelengths_nm[i] - w); if (d < bd) { bd = d; best = i; } }
    setHover(best);
  };
  const h = hover;
  const hw = h != null ? spec.wavelengths_nm[h] : null;
  const band = hw != null ? S2_BANDS.find(([, c, fw]) => Math.abs(hw - c) <= fw / 2) : null;
  const diag = hw != null ? DIAGNOSTIC.find(([c]) => Math.abs(hw - c) <= 6) : null;
  const ticks = [400, 500, 600, 700, 800, 900].filter((t) => t >= range[0] && t <= range[1]);
  return (
    <div className="relative">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full select-none" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <rect x={L} y={T} width={W - L - R} height={H - T - B} fill="#040915" stroke="#16284D" />
        {showBands && S2_BANDS.filter(([, c]) => c >= range[0] && c <= range[1]).map(([n, c, fw]) => (
          <g key={n}><rect x={x(c - fw / 2)} y={T} width={Math.max(1, x(c + fw / 2) - x(c - fw / 2))} height={H - T - B} fill="#2F7BFF" opacity={0.07} />
            <text x={x(c)} y={T + 10} textAnchor="middle" fontSize={8.5} fill="#5D7299">{n}</text></g>
        ))}
        {DIAGNOSTIC.filter(([c]) => c >= range[0] && c <= range[1]).map(([c, n]) => (
          <line key={n} x1={x(c)} x2={x(c)} y1={T} y2={H - B} stroke={highlight && Math.abs(highlight - c) < 4 ? "#FFC23D" : "#FFC23D55"} strokeDasharray="2 3" />
        ))}
        {env && <path d={env} fill="#27C3F3" opacity={0.12} />}
        <path d={path(spec.background)} fill="none" stroke="#27C3F3" strokeWidth={1.6} />
        <path d={path(spec.event)} fill="none" stroke="#FF4D5E" strokeWidth={1.9} />
        {showDiff && <path d={path(spec.event.map((v, i) => (v != null && spec.background[i] != null ? v - spec.background[i]! + ymin : null)))} fill="none" stroke="#FFC23D" strokeWidth={1} strokeDasharray="3 2" />}
        {ticks.map((t) => <text key={t} x={x(t)} y={H - 8} textAnchor="middle" fontSize={9.5} fill="#93A6CB">{t}</text>)}
        {[0, 0.5, 1].map((f) => { const v = ymin + f * (ymax - ymin); return <text key={f} x={L - 5} y={y(v) + 3} textAnchor="end" fontSize={9} fill="#93A6CB">{v.toFixed(3)}</text>; })}
        <text x={W / 2} y={H - 0.5} textAnchor="middle" fontSize={9} fill="#5D7299">Wavelength (nm)</text>
        {h != null && hw != null && <line x1={x(hw)} x2={x(hw)} y1={T} y2={H - B} stroke="#EAF1FF" strokeOpacity={0.5} />}
      </svg>
      <div className="pointer-events-none absolute right-2 top-2 flex gap-3 text-[10.5px]">
        <span className="text-critical">● Incident pixel(s)</span><span className="text-cyan">● Background water</span>
      </div>
      {h != null && hw != null && (
        <div className="panel pointer-events-none absolute left-14 top-6 px-3 py-2 text-[11px]">
          <div className="hud-value font-bold text-caution">{hw.toFixed(1)} nm {band ? `· S2 ${band[0]}` : "· no S2 band"}</div>
          <div className="text-critical">Incident: {spec.event[h] != null ? spec.event[h]!.toFixed(4) : "n/a"}</div>
          <div className="text-cyan">Background: {spec.background[h] != null ? spec.background[h]!.toFixed(4) : "n/a"}</div>
          {spec.background_p05?.[h] != null && <div className="text-muted">Background 5-95 %: {spec.background_p05[h]!.toFixed(4)}–{spec.background_p95![h]!.toFixed(4)}</div>}
          {diag && <div className="text-ink">Diagnostic: {diag[1]}</div>}
        </div>
      )}
    </div>
  );
}
