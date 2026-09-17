"use client";

/**
 * SPECTRA - the hyperspectral oscilloscope.
 *
 * This is where the difference between 11 broad bands and a continuous
 * spectrum becomes visible rather than asserted. The cursor reads out the
 * exact value, uncertainty and significance at any wavelength, and the
 * Sentinel-2 band overlay shows precisely what a multispectral sensor would
 * and would not have measured.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Panel, Loading, ErrorBox, KV, Chip, Caveat, SimulatedBadge, Readout,
} from "@/components/hud";
import { api, SpectraPayload, WaterEvent, CLASS_COLOR, fmt, fmtInt } from "@/lib/api";

/**
 * Sentinel-2 MSI bands drawn on the spectrum.
 *
 * Centres and bandwidths are the ESA Sentinel-2 User Handbook / MSI spectral
 * response values, and they are the same numbers pipeline/satellite813.py uses
 * to build the multispectral arm of the ablation. B9 (945 nm water vapour) and
 * B10 (1375 nm cirrus) are omitted: they carry atmosphere, not water-leaving
 * signal. B11/B12 sit outside the water-informative range plotted here.
 */
const S2_BANDS: { name: string; nm: number; w: number }[] = [
  { name: "B1", nm: 443, w: 21 }, { name: "B2", nm: 492, w: 66 },
  { name: "B3", nm: 560, w: 36 }, { name: "B4", nm: 665, w: 31 },
  { name: "B5", nm: 704, w: 15 }, { name: "B6", nm: 740, w: 15 },
  { name: "B7", nm: 783, w: 20 }, { name: "B8A", nm: 865, w: 21 },
];

type Mode = "reflectance" | "difference" | "zscore" | "snr";

export default function Spectra() {
  const [sp, setSp] = useState<SpectraPayload | null>(null);
  const [ev, setEv] = useState<WaterEvent | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("reflectance");
  const [showS2, setShowS2] = useState(true);
  const [showEnv, setShowEnv] = useState(true);
  const [showRegions, setShowRegions] = useState(false);
  const [zoom, setZoom] = useState<[number, number] | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const idx = await api.events();
        const id = idx.events[0].event_id;
        const [s, e] = await Promise.all([api.spectrum(id), api.event(id)]);
        setSp(s); setEv(e);
      } catch (e: any) { setErr(e.message ?? String(e)); }
    })();
  }, []);

  const W = 1180, H = 470, M = { l: 66, r: 24, t: 20, b: 44 };

  const view = useMemo(() => {
    if (!sp) return null;
    const wl = sp.wavelengths_nm;
    const lo = zoom?.[0] ?? wl[0];
    const hi = zoom?.[1] ?? wl[wl.length - 1];
    const idxs = wl.map((w, i) => ({ w, i })).filter((d) => d.w >= lo && d.w <= hi);

    const pick = (arr: (number | null)[]) => idxs.map((d) => arr[d.i]);
    let series: { key: string; color: string; label: string; v: (number | null)[] }[] = [];

    if (mode === "reflectance") {
      series = [
        { key: "bg", color: "#4A93FF", label: "Background water", v: pick(sp.background.mean) },
        { key: "ev", color: "#FF7A45", label: "Event", v: pick(sp.event.mean) },
      ];
      if (showRegions) {
        Object.entries(sp.regions).forEach(([k, r], i) => {
          series.push({
            key: k, color: CLASS_COLOR[r.class] ?? "#8A93B8",
            label: `${k} (${r.class.replace(/_/g, " ").toLowerCase()})`,
            v: pick(r.mean),
          });
        });
      }
    } else if (mode === "difference") {
      series = [{ key: "diff", color: "#F5C451", label: "Event - background", v: pick(sp.difference) }];
    } else if (mode === "zscore") {
      series = [{ key: "z", color: "#3FD1A0", label: "z of difference", v: pick(sp.z_score) }];
    } else {
      series = [{ key: "snr", color: "#C77DFF", label: "Signal-to-noise", v: pick(sp.snr) }];
    }

    const all = series.flatMap((s) => s.v).filter((v): v is number => v !== null && Number.isFinite(v));
    let ymin = Math.min(...all), ymax = Math.max(...all);
    if (mode === "reflectance") ymin = Math.min(0, ymin);
    if (mode === "zscore" || mode === "difference") {
      const m = Math.max(Math.abs(ymin), Math.abs(ymax));
      ymin = -m; ymax = m;
    }
    const pad = (ymax - ymin) * 0.08 || 0.01;
    ymin -= pad; ymax += pad;

    const x = (w: number) => M.l + ((w - lo) / (hi - lo)) * (W - M.l - M.r);
    const y = (v: number) => H - M.b - ((v - ymin) / (ymax - ymin)) * (H - M.t - M.b);

    const envelope = showEnv && mode === "reflectance"
      ? { lo: pick(sp.background.p05), hi: pick(sp.background.p95) }
      : null;

    return { wl: idxs.map((d) => d.w), idxs, series, x, y, lo, hi, ymin, ymax, envelope };
  }, [sp, mode, zoom, showEnv, showRegions]);

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!sp || !ev || !view) return <Loading what="spectral cube" />;

  const ci = cursor !== null
    ? view.wl.reduce((best, w, i) => Math.abs(w - cursor) < Math.abs(view.wl[best] - cursor) ? i : best, 0)
    : null;
  const cw = ci !== null ? view.wl[ci] : null;
  const gi = ci !== null ? view.idxs[ci].i : null;

  const s2Covers = (nm: number) =>
    S2_BANDS.some((b) => Math.abs(b.nm - nm) <= b.w / 2);

  function toPath(v: (number | null)[]) {
    let d = "", pen = false;
    v.forEach((val, i) => {
      if (val === null || !Number.isFinite(val)) { pen = false; return; }
      const px = view!.x(view!.wl[i]), py = view!.y(val);
      d += `${pen ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`;
      pen = true;
    });
    return d;
  }

  const yTicks = 5, xTicks = 8;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_320px] gap-3">
        {/* -------------------------------------------------- oscilloscope */}
        <div className="flex flex-col gap-3 min-w-0">
          <Panel
            title="Hyperspectral oscilloscope"
            right={
              <div className="flex items-center gap-1.5 flex-wrap justify-end">
                {(["reflectance", "difference", "zscore", "snr"] as Mode[]).map((m) => (
                  <button key={m} onClick={() => setMode(m)}
                          className="chamfer-sm hud-label px-2 py-[3px] transition-colors"
                          style={{
                            color: mode === m ? "#4A93FF" : "#5A6490",
                            border: `1px solid ${mode === m ? "#3186FF" : "#1B2444"}`,
                            background: mode === m ? "rgba(49,134,255,0.14)" : "transparent",
                          }}>
                    {m === "zscore" ? "Z-SCORE" : m.toUpperCase()}
                  </button>
                ))}
              </div>
            }>
            <div className="relative">
              <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full select-none"
                   style={{ display: "block" }}
                   onMouseMove={(e) => {
                     const r = svgRef.current!.getBoundingClientRect();
                     const px = ((e.clientX - r.left) / r.width) * W;
                     if (px < M.l || px > W - M.r) { setCursor(null); return; }
                     const frac = (px - M.l) / (W - M.l - M.r);
                     setCursor(view.lo + frac * (view.hi - view.lo));
                   }}
                   onMouseLeave={() => setCursor(null)}
                   onDoubleClick={() => setZoom(null)}>
                {/* bad-band regions from the product's own flags */}
                {sp.bad_band_ranges_nm.map(([a, b], i) => {
                  if (b < view.lo || a > view.hi) return null;
                  const xa = view.x(Math.max(a, view.lo)), xb = view.x(Math.min(b, view.hi));
                  return (
                    <g key={i}>
                      <rect x={xa} y={M.t} width={Math.max(xb - xa, 1)} height={H - M.t - M.b}
                            fill="rgba(255,77,77,0.07)" />
                      <text x={(xa + xb) / 2} y={M.t + 12} textAnchor="middle"
                            className="hud-label" style={{ fontSize: 8, fill: "#FF4D4D" }}>
                        SENSOR BAD BANDS
                      </text>
                    </g>
                  );
                })}

                {/* Sentinel-2 band footprints */}
                {showS2 && S2_BANDS.map((b) => {
                  const a = b.nm - b.w / 2, c = b.nm + b.w / 2;
                  if (c < view.lo || a > view.hi) return null;
                  const xa = view.x(Math.max(a, view.lo)), xb = view.x(Math.min(c, view.hi));
                  return (
                    <g key={b.name}>
                      <rect x={xa} y={M.t} width={Math.max(xb - xa, 1.5)} height={H - M.t - M.b}
                            fill="rgba(63,209,160,0.10)" stroke="rgba(63,209,160,0.3)"
                            strokeWidth={0.5} />
                      <text x={(xa + xb) / 2} y={H - M.b + 24} textAnchor="middle"
                            className="hud-value" style={{ fontSize: 8, fill: "#3FD1A0" }}>
                        {b.name}
                      </text>
                    </g>
                  );
                })}

                {/* grid */}
                {Array.from({ length: yTicks + 1 }).map((_, i) => {
                  const v = view.ymin + (i / yTicks) * (view.ymax - view.ymin);
                  const yy = view.y(v);
                  return (
                    <g key={i}>
                      <line x1={M.l} y1={yy} x2={W - M.r} y2={yy}
                            stroke="#1B2444" strokeWidth={0.6}
                            strokeDasharray={Math.abs(v) < 1e-9 ? "" : "2 4"} />
                      <text x={M.l - 8} y={yy + 3} textAnchor="end" className="hud-value"
                            style={{ fontSize: 9, fill: "#5A6490" }}>
                        {mode === "reflectance" ? v.toFixed(3)
                          : mode === "snr" ? v.toFixed(0) : v.toFixed(3)}
                      </text>
                    </g>
                  );
                })}
                {Array.from({ length: xTicks + 1 }).map((_, i) => {
                  const w = view.lo + (i / xTicks) * (view.hi - view.lo);
                  const xx = view.x(w);
                  return (
                    <g key={i}>
                      <line x1={xx} y1={M.t} x2={xx} y2={H - M.b}
                            stroke="#1B2444" strokeWidth={0.6} strokeDasharray="2 5" />
                      <text x={xx} y={H - M.b + 14} textAnchor="middle" className="hud-value"
                            style={{ fontSize: 9, fill: "#5A6490" }}>
                        {w.toFixed(0)}
                      </text>
                    </g>
                  );
                })}

                {/* diagnostic wavelengths */}
                {Object.entries(sp.diagnostic_features).map(([k, f]) => {
                  if (f.centre_nm < view.lo || f.centre_nm > view.hi) return null;
                  const xx = view.x(f.centre_nm);
                  const covered = s2Covers(f.centre_nm);
                  return (
                    <g key={k}>
                      <line x1={xx} y1={M.t} x2={xx} y2={H - M.b}
                            stroke={covered ? "#3A4karma" : "#C77DFF"}
                            style={{ stroke: covered ? "#2E3A63" : "#C77DFF" }}
                            strokeWidth={0.9} strokeDasharray="3 3" opacity={covered ? 0.5 : 0.8} />
                      <text x={xx + 3} y={M.t + 26} className="hud-label"
                            style={{ fontSize: 7.5, fill: covered ? "#4A5478" : "#C77DFF" }}>
                        {f.centre_nm}
                      </text>
                    </g>
                  );
                })}

                {/* background dispersion envelope */}
                {view.envelope && (
                  <path
                    d={
                      view.wl.map((w, i) => {
                        const v = view.envelope!.hi[i];
                        return v === null ? "" : `${i === 0 ? "M" : "L"}${view.x(w)},${view.y(v)}`;
                      }).join("") +
                      view.wl.slice().reverse().map((w, j) => {
                        const i = view.wl.length - 1 - j;
                        const v = view.envelope!.lo[i];
                        return v === null ? "" : `L${view.x(w)},${view.y(v)}`;
                      }).join("") + "Z"
                    }
                    fill="rgba(74,147,255,0.12)" stroke="none" />
                )}

                {/* series */}
                {view.series.map((s) => (
                  <path key={s.key} d={toPath(s.v)} fill="none" stroke={s.color}
                        strokeWidth={s.key === "ev" || s.key === "bg" ? 1.9 : 1.1}
                        strokeLinejoin="round"
                        style={{ filter: `drop-shadow(0 0 4px ${s.color}44)` }} />
                ))}

                {/* axes */}
                <line x1={M.l} y1={M.t} x2={M.l} y2={H - M.b} stroke="#243056" />
                <line x1={M.l} y1={H - M.b} x2={W - M.r} y2={H - M.b} stroke="#243056" />
                <text x={M.l} y={H - 6} className="hud-label" style={{ fontSize: 9 }}>
                  WAVELENGTH (nm)
                </text>
                <text x={-((H - M.b + M.t) / 2)} y={14} transform="rotate(-90)"
                      textAnchor="middle" className="hud-label" style={{ fontSize: 9 }}>
                  {mode === "reflectance" ? "SURFACE REFLECTANCE (unitless)"
                    : mode === "difference" ? "Δ REFLECTANCE"
                    : mode === "zscore" ? "z (difference / SE)" : "SNR"}
                </text>

                {/* cursor */}
                {cw !== null && (
                  <g>
                    <line x1={view.x(cw)} y1={M.t} x2={view.x(cw)} y2={H - M.b}
                          stroke="#F4F6FF" strokeWidth={0.9} opacity={0.75} />
                    {view.series.map((s) => {
                      const v = s.v[ci!];
                      if (v === null || !Number.isFinite(v)) return null;
                      return <circle key={s.key} cx={view.x(cw)} cy={view.y(v)} r={3.4}
                                     fill="#070A16" stroke={s.color} strokeWidth={1.6} />;
                    })}
                    <rect x={Math.min(view.x(cw) + 8, W - 120)} y={M.t + 4}
                          width={112} height={20} fill="rgba(7,10,22,0.92)" stroke="#243056" />
                    <text x={Math.min(view.x(cw) + 14, W - 114)} y={M.t + 18}
                          className="hud-value" style={{ fontSize: 10, fill: "#F4F6FF" }}>
                      {cw.toFixed(2)} nm
                    </text>
                  </g>
                )}
              </svg>
            </div>

            <div className="flex items-center gap-3 flex-wrap mt-2 pt-2 border-t border-edge/50">
              {view.series.map((s) => (
                <span key={s.key} className="flex items-center gap-1.5">
                  <span style={{ width: 14, height: 2, background: s.color, display: "inline-block" }} />
                  <span className="hud-label" style={{ letterSpacing: "0.08em" }}>{s.label}</span>
                </span>
              ))}
              <div className="flex-1" />
              <Toggle on={showS2} set={setShowS2} label="Sentinel-2 bands" color="#3FD1A0" />
              <Toggle on={showEnv} set={setShowEnv} label="P5-P95 envelope" color="#4A93FF" />
              <Toggle on={showRegions} set={setShowRegions} label="All regions" color="#C77DFF" />
              <div className="flex gap-1">
                {([["Full", null], ["VIS 400-750", [400, 750]], ["Red-edge 640-760", [640, 760]],
                   ["Blue 400-560", [400, 560]]] as [string, [number, number] | null][]).map(([l, z]) => (
                  <button key={l} onClick={() => setZoom(z)}
                          className="chamfer-sm hud-label px-2 py-[3px]"
                          style={{
                            color: JSON.stringify(zoom) === JSON.stringify(z) ? "#4A93FF" : "#5A6490",
                            border: `1px solid ${JSON.stringify(zoom) === JSON.stringify(z) ? "#3186FF" : "#1B2444"}`,
                          }}>{l}</button>
                ))}
              </div>
            </div>
          </Panel>

          <Panel title="What a multispectral sensor would have measured here">
            <p className="text-[11px] leading-[1.7] text-muted">
              The green bands above are Sentinel-2&apos;s. Between them, a multispectral
              sensor measures nothing. The violet markers are wavelengths that carry
              diagnostic water information; those drawn in violet fall in the gaps,
              and those drawn grey happen to land inside a Sentinel-2 band.
            </p>
            <div className="grid sm:grid-cols-2 gap-x-6 mt-3">
              {Object.entries(sp.diagnostic_features).map(([k, f]) => {
                const covered = s2Covers(f.centre_nm);
                return (
                  <KV key={k}
                      k={`${f.centre_nm} nm`}
                      v={<span>
                          <span style={{ color: covered ? "#8A93B8" : "#C77DFF" }}>
                            {covered ? "in an S2 band" : "NOT in any S2 band"}
                          </span>
                          <span className="text-dim"> · {f.meaning}</span>
                        </span>} />
                );
              })}
            </div>
            <Caveat>
              A wavelength being measurable is not the same as a constituent being
              identifiable. See the Validation screen for what hyperspectral
              resolution measurably bought on this scene, and what it did not.
            </Caveat>
          </Panel>
        </div>

        {/* ---------------------------------------------------- side panel */}
        <div className="flex flex-col gap-3 min-w-0">
          <Panel title="Cursor readout" right={<Chip label={cw ? `${cw.toFixed(1)} nm` : "-"} color="#3186FF" />}>
            {cw === null ? (
              <p className="text-[11px] text-dim leading-relaxed">
                Move the cursor across the spectrum to read exact values,
                per-band uncertainty and significance at any wavelength.
              </p>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3 mb-2">
                  <Readout label="Background" size="sm" color="#4A93FF"
                           value={fmt(sp.background.mean[gi!], 5)} />
                  <Readout label="Event" size="sm" color="#FF7A45"
                           value={fmt(sp.event.mean[gi!], 5)} />
                </div>
                <KV k="Difference" v={fmt(sp.difference[gi!], 5)} color="#F5C451" />
                <KV k="z of difference" v={fmt(sp.z_score[gi!], 2)}
                    color={Math.abs(sp.z_score[gi!] ?? 0) > 2 ? "#3FD1A0" : "#8A93B8"} />
                <KV k="Significant" v={Math.abs(sp.z_score[gi!] ?? 0) > 2 ? "yes (|z| > 2)" : "no"}
                    color={Math.abs(sp.z_score[gi!] ?? 0) > 2 ? "#3FD1A0" : "#F5C451"} />
                <KV k="Band SNR" v={fmt(sp.snr[gi!], 1)} />
                <KV k="Background σ" v={fmt(sp.background.std[gi!], 5)} />
                <KV k="In Sentinel-2 band" v={s2Covers(cw) ? "yes" : "NO"}
                    color={s2Covers(cw) ? "#8A93B8" : "#C77DFF"} />
              </>
            )}
          </Panel>

          <Panel title="Spectral populations">
            <KV k="Background pixels" v={fmtInt(sp.background.n_pixels)} />
            <KV k="Event pixels" v={fmtInt(sp.event.n_pixels)} />
            <KV k="Bands plotted" v={fmtInt(sp.wavelengths_nm.length)} />
            <KV k="Range"
                v={`${fmt(sp.wavelengths_nm[0], 1)}-${fmt(sp.wavelengths_nm.at(-1), 1)} nm`} />
            <KV k="Sentinel-2 bands here"
                v={String(S2_BANDS.filter(
                     (b) => b.nm >= sp.wavelengths_nm[0]
                         && b.nm <= (sp.wavelengths_nm.at(-1) ?? 0)).length)}
                color="#3FD1A0" />
            <KV k="813 bands here" v={fmtInt(sp.sensor_bands.n_813_bands_in_range)}
                color="#4A93FF" />
          </Panel>

          <Panel title="Evidence used by the classifier"
                 right={<Chip label={ev.classification.top_class.replace(/_/g, " ")}
                              color={CLASS_COLOR[ev.classification.top_class]} />}>
            <div className="space-y-2.5">
              {ev.classification.evidence.slice(0, 6).map((e) => (
                <div key={e.name} className="pb-2 border-b border-edge/40 last:border-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="hud-label truncate">{e.name.replace(/_/g, " ")}</span>
                    <span className="hud-value text-[11px] shrink-0"
                          style={{ color: e.supports === "none" ? "#5A6490"
                                          : CLASS_COLOR[e.supports] ?? "#F4F6FF" }}>
                      {fmt(e.value, 4)}
                    </span>
                  </div>
                  {e.supports !== "none" && (
                    <div className="hud-label mt-1" style={{ color: CLASS_COLOR[e.supports] }}>
                      → supports {e.supports.replace(/_/g, " ").toLowerCase()}
                    </div>
                  )}
                  <p className="text-[10px] leading-[1.55] text-dim mt-1.5">{e.description}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="813 simulation" right={<SimulatedBadge compact />}>
            <p className="text-[10.5px] leading-[1.65] text-beam2/80">
              The spectrum above is real Planet Tanager-1 data. The 813 product is
              generated from it by convolving onto the published 813 band table.
              No Satellite 813 pixels exist in this system.
            </p>
            <Caveat>
              The simulator was validated against a real Sentinel-2 acquisition
              38 minutes apart: r = 0.95-0.97 over land in the visible. See
              Validation.
            </Caveat>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Toggle({ on, set, label, color }:
  { on: boolean; set: (v: boolean) => void; label: string; color: string }) {
  return (
    <button onClick={() => set(!on)} className="flex items-center gap-1.5 group">
      <span className="w-[9px] h-[9px] chamfer-sm transition-colors"
            style={{ background: on ? color : "transparent", border: `1px solid ${on ? color : "#243056"}` }} />
      <span className="hud-label" style={{ color: on ? color : "#5A6490" }}>{label}</span>
    </button>
  );
}
