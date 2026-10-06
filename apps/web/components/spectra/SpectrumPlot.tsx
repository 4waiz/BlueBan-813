"use client";
import React, { useId, useMemo, useRef, useState } from "react";
import { useElementSize } from "@/lib/useSize";

export interface Spectrum {
  wavelengths_nm: number[]; event: (number | null)[]; background: (number | null)[];
  background_p05?: (number | null)[]; background_p95?: (number | null)[]; sensor?: string; simulated?: boolean;
}

const S2_BANDS: [string, number, number][] = [["B1", 443, 21], ["B2", 492, 66], ["B3", 560, 36], ["B4", 665, 31], ["B5", 704, 15], ["B6", 740, 15], ["B7", 783, 20], ["B8", 833, 106], ["B8A", 865, 21], ["B11", 1610, 91]];
export const DIAGNOSTIC: [number, string][] = [[443, "Chlorophyll (blue)"], [620, "Blue-green algae"], [665, "Sediment"], [675, "Chlorophyll (red dip)"], [705, "Bloom peak"]];

export default function SpectrumPlot(props: {
  spec: Spectrum; height?: number; fill?: boolean; showBands?: boolean; showDiff?: boolean; range?: [number, number]; highlight?: number | null;
}) {
  const box = useElementSize<HTMLDivElement>();
  if (props.fill) {
    // The chart takes exactly the box it is given (never a minimum), so it can
    // not spill over a caption or the panel below it on short screens.
    return (
      <div ref={box.ref} className="h-full w-full overflow-hidden">
        {box.width >= 120 && box.height >= 64 && <SpectrumPlotInner {...props} W={box.width} height={box.height} />}
      </div>
    );
  }
  return <SpectrumPlotInner {...props} />;
}

function SpectrumPlotInner({ spec, height = 240, showBands = true, showDiff = false, range = [400, 900], highlight, W: Wp }: {
  spec: Spectrum; height?: number; fill?: boolean; showBands?: boolean; showDiff?: boolean; range?: [number, number]; highlight?: number | null; W?: number;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  // Small boxes drop the axis title and the band names instead of overlapping them.
  const W = Wp ?? 560, H = height, roomy = H >= 150, L = 44, R = 12, T = 18, B = roomy ? 30 : 18;
  const clipId = `spc-${useId().replace(/:/g, "")}`;
  const idx = useMemo(() => spec.wavelengths_nm.map((w, i) => i).filter((i) => spec.wavelengths_nm[i] >= range[0] && spec.wavelengths_nm[i] <= range[1]), [spec, range]);
  // The y-range covers everything drawn (both envelope edges too), and the data is
  // clipped to the plot frame, so nothing can spill onto the axis labels.
  const vals = idx.flatMap((i) => [spec.event[i], spec.background[i], spec.background_p95?.[i], spec.background_p05?.[i]]).filter((v): v is number => v != null && Number.isFinite(v));
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
  const allTicks = [400, 500, 600, 700, 800, 900].filter((t) => t >= range[0] && t <= range[1]);
  // Narrow charts label every other tick so the numbers never touch.
  const tickStep = (W - L - R) / Math.max(1, allTicks.length - 1) < 48 ? 2 : 1;
  const ticks = allTicks.filter((_, i) => i % tickStep === 0);
  return (
    <div className="relative">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="block w-full select-none" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <text x={W - R} y={12} textAnchor="end" fontSize={10}>
          <tspan fill="#FF4D5E">{W >= 280 ? "● Event pixels" : "● Event"}</tspan><tspan dx={10} fill="#27C3F3">{W >= 280 ? "● Normal water" : "● Normal"}</tspan>
        </text>
        <rect x={L} y={T} width={W - L - R} height={H - T - B} fill="#040915" stroke="#16284D" />
        {showBands && S2_BANDS.filter(([, c]) => c >= range[0] && c <= range[1]).map(([n, c, fw]) => (
          <g key={n}><rect x={x(c - fw / 2)} y={T} width={Math.max(1, x(c + fw / 2) - x(c - fw / 2))} height={H - T - B} fill="#2F7BFF" opacity={0.07} />
            {H >= 120 && <text x={x(c)} y={T + 10} textAnchor="middle" fontSize={8.5} fill="#7088B3">{n}</text>}</g>
        ))}
        {DIAGNOSTIC.filter(([c]) => c >= range[0] && c <= range[1]).map(([c, n]) => (
          <line key={n} x1={x(c)} x2={x(c)} y1={T} y2={H - B} stroke={highlight && Math.abs(highlight - c) < 4 ? "#FFC23D" : "#FFC23D55"} strokeDasharray="2 3" />
        ))}
        <clipPath id={clipId}><rect x={L} y={T} width={W - L - R} height={H - T - B} /></clipPath>
        <g clipPath={`url(#${clipId})`}>
          {env && <path d={env} fill="#27C3F3" opacity={0.12} />}
          <path d={path(spec.background)} fill="none" stroke="#27C3F3" strokeWidth={1.6} />
          <path d={path(spec.event)} fill="none" stroke="#FF4D5E" strokeWidth={1.9} />
          {showDiff && <path d={path(spec.event.map((v, i) => (v != null && spec.background[i] != null ? v - spec.background[i]! + ymin : null)))} fill="none" stroke="#FFC23D" strokeWidth={1} strokeDasharray="3 2" />}
        </g>
        {ticks.map((t, k) => {
          const unit = !roomy && k === ticks.length - 1;
          return <text key={t} x={unit ? x(t) + 4 : x(t)} y={H - B + 12} textAnchor={unit ? "end" : "middle"} fontSize={9.5} fill="#93A6CB">{unit ? `${t} nm` : t}</text>;
        })}
        {[0, 0.5, 1].map((f) => { const v = ymin + f * (ymax - ymin); return <text key={f} x={L - 5} y={y(v) + 3} textAnchor="end" fontSize={9} fill="#93A6CB">{v.toFixed(3)}</text>; })}
        {roomy && <text x={W / 2} y={H - 3} textAnchor="middle" fontSize={9} fill="#7088B3">Wavelength (nm)</text>}
        {h != null && hw != null && <line x1={x(hw)} x2={x(hw)} y1={T} y2={H - B} stroke="#EAF1FF" strokeOpacity={0.5} />}
      </svg>
      {h != null && hw != null && (
        <div className="panel pointer-events-none absolute left-14 top-6 px-3 py-2 text-[11px]">
          <div className="hud-value font-bold text-caution">{hw.toFixed(1)} nm {band ? `· Sentinel-2 ${band[0]}` : "· no Sentinel-2 band"}</div>
          <div className="text-critical">Event: {spec.event[h] != null ? spec.event[h]!.toFixed(4) : "n/a"}</div>
          <div className="text-cyan">Normal water: {spec.background[h] != null ? spec.background[h]!.toFixed(4) : "n/a"}</div>
          {spec.background_p05?.[h] != null && <div className="text-muted">Usual range (5–95 %): {spec.background_p05[h]!.toFixed(4)}–{spec.background_p95![h]!.toFixed(4)}</div>}
          {diag && <div className="text-ink">Key wavelength: {diag[1]}</div>}
        </div>
      )}
    </div>
  );
}
