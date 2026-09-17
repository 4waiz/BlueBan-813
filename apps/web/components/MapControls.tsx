"use client";

/**
 * Controls that sit on top of the ocean view.
 *
 * All three are designed as cockpit hardware rather than web widgets: chamfered
 * edges, monospaced labels, no rounded cards, and every control reports the
 * actual value it is setting.
 */

import React, { useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCcw, Layers, Eye, EyeOff } from "lucide-react";

import { ForecastStep } from "@/lib/api";
import { RasterKey } from "./OceanMap";

/* ------------------------------------------------------------------ legend */

interface Ramp { stops: string[]; note: string; }

export const RASTER_META: Record<RasterKey, {
  label: string; short: string; ramp: Ramp;
}> = {
  rgb: {
    label: "True colour · 666 / 561 / 441 nm",
    short: "TRUE COLOUR",
    ramp: {
      stops: ["#04060f", "#0b1c3a", "#16457e", "#2f7fc4", "#9fd6ea"],
      note: "Shared stretch across the three channels so the real colour "
            + "balance of the water survives. Land is darkened to a backdrop.",
    },
  },
  anomaly: {
    label: "RX spectral anomaly · log₁₀ scale",
    short: "ANOMALY",
    ramp: {
      stops: ["#000004", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"],
      note: "Mahalanobis distance of each pixel's spectrum from the offshore "
            + "water population, in PCA space. Water pixels only.",
    },
  },
  ndci: {
    label: "NDCI chlorophyll proxy · dimensionless",
    short: "NDCI",
    ramp: {
      stops: ["#ffffe5", "#d9f0a3", "#78c679", "#238443", "#004529"],
      note: "Normalised difference of 706 nm and 666 nm. A screening proxy, "
            + "not a chlorophyll-a concentration.",
    },
  },
  turbidity: {
    label: "Turbidity proxy · dimensionless",
    short: "TURBIDITY",
    ramp: {
      stops: ["#000004", "#51127c", "#b73779", "#fc8961", "#fcfdbf"],
      note: "Normalised difference of 666 nm and 561 nm. A screening proxy, "
            + "not laboratory NTU.",
    },
  },
};

/**
 * Legend for the active raster.
 *
 * The numeric limits are the ones the pipeline actually mapped the pixels onto
 * (exported in raster_bounds.json as the 2nd-99th percentile of the masked
 * population). Nothing here is a typed-in range, so the legend cannot drift out
 * of step with the image.
 */
export function MapLegend({ raster, collapsed = false, scale }: {
  raster: RasterKey; collapsed?: boolean;
  scale?: { vmin?: number; vmax?: number; log?: boolean; limits?: string } | null;
}) {
  const [open, setOpen] = useState(!collapsed);
  const m = RASTER_META[raster];
  const fmtLim = (v?: number) =>
    v === undefined || v === null || !Number.isFinite(v) ? null
      : Math.abs(v) >= 100 ? v.toFixed(0)
      : Math.abs(v) >= 1 ? v.toFixed(2) : v.toFixed(3);
  const lo = fmtLim(scale?.vmin);
  const hi = fmtLim(scale?.vmax);
  return (
    <div className="bg-void/88 backdrop-blur-sm chamfer-sm border border-edge
                    max-w-[290px] overflow-hidden">
      <button onClick={() => setOpen(!open)}
              className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 tap
                         hover:bg-white/[0.04]">
        <span className="hud-label truncate">{m.short}</span>
        {open ? <EyeOff size={11} className="text-dim shrink-0" />
              : <Eye size={11} className="text-dim shrink-0" />}
      </button>
      {open && (
        <div className="px-2.5 pb-2.5">
          <div className="h-[7px] w-full chamfer-sm"
               style={{ background: `linear-gradient(90deg, ${m.ramp.stops.join(", ")})` }} />
          <div className="flex justify-between mt-1.5">
            <span className="hud-label">{lo ?? "low"}</span>
            <span className="hud-label">
              {scale?.log ? "log10 scale" : ""}
            </span>
            <span className="hud-label">{hi ?? "high"}</span>
          </div>
          <p className="text-[9.5px] leading-[1.55] text-dim mt-2">{m.ramp.note}</p>
          {scale?.limits && (
            <p className="hud-label mt-1.5 normal-case"
               style={{ letterSpacing: "0.05em" }}>
              limits: {scale.limits}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------- layer control */

export function LayerControl({
  raster, setRaster, opacity, setOpacity,
  showEvents, setShowEvents, showWater, setShowWater,
  showFlow, setShowFlow, showParticles, setShowParticles,
}: {
  raster: RasterKey; setRaster: (k: RasterKey) => void;
  opacity: number; setOpacity: (v: number) => void;
  showEvents: boolean; setShowEvents: (v: boolean) => void;
  showWater: boolean; setShowWater: (v: boolean) => void;
  showFlow: boolean; setShowFlow: (v: boolean) => void;
  showParticles: boolean; setShowParticles: (v: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-void/88 backdrop-blur-sm chamfer-sm border border-edge">
      <div className="flex items-stretch">
        {(Object.keys(RASTER_META) as RasterKey[]).map((k) => (
          <button key={k} onClick={() => setRaster(k)}
                  className="hud-label px-2.5 py-[6px] tap border-r border-edge/60 last:border-0"
                  style={{
                    background: raster === k ? "rgba(49,134,255,0.2)" : "transparent",
                    color: raster === k ? "#4A93FF" : "#5A6490",
                  }}>
            {RASTER_META[k].short}
          </button>
        ))}
        <button onClick={() => setOpen(!open)}
                className="px-2 py-[6px] tap border-l border-edge/60 hover:bg-white/[0.05]"
                title="Layers and overlays">
          <Layers size={12} className={open ? "text-beam" : "text-dim"} />
        </button>
      </div>

      {open && (
        <div className="px-2.5 py-2.5 border-t border-edge/60 w-[228px]">
          <div className="flex items-center justify-between mb-1">
            <span className="hud-label">raster opacity</span>
            <span className="hud-value text-[10px] text-muted">
              {Math.round(opacity * 100)}%
            </span>
          </div>
          <input type="range" min={0} max={100} value={Math.round(opacity * 100)}
                 onChange={(e) => setOpacity(Number(e.target.value) / 100)}
                 className="w-full accent-beam h-[3px] cursor-pointer"
                 style={{ accentColor: "#3186FF" }} />
          <div className="mt-3 space-y-1.5">
            <Toggle on={showEvents} set={setShowEvents} label="Event contours" color="#FF7A45" />
            <Toggle on={showParticles} set={setShowParticles} label="Drift particles" color="#4A93FF" />
            <Toggle on={showFlow} set={setShowFlow} label="Drift field" color="#4A93FF" />
            <Toggle on={showWater} set={setShowWater} label="Water mask edge" color="#3186FF" />
          </div>
        </div>
      )}
    </div>
  );
}

export function Toggle({ on, set, label, color }:
  { on: boolean; set: (v: boolean) => void; label: string; color: string }) {
  return (
    <button onClick={() => set(!on)} className="flex items-center gap-2 group tap w-full">
      <span className="w-[9px] h-[9px] chamfer-sm shrink-0 transition-colors"
            style={{ background: on ? color : "transparent",
                     border: `1px solid ${on ? color : "#243056"}` }} />
      <span className="hud-label" style={{ color: on ? color : "#5A6490" }}>{label}</span>
    </button>
  );
}

/* -------------------------------------------------------------- timeline */

/**
 * Forecast scrubber. Playing advances a fractional index through the horizon
 * list so the particle cloud moves continuously rather than snapping between
 * the five modelled times.
 */
export function Timeline({
  steps, t, setT, playing, setPlaying, speed = 0.55, compact = false,
}: {
  steps: ForecastStep[]; t: number;
  // A React state setter, so the animation loop can advance from the previous
  // value without re-subscribing on every frame.
  setT: React.Dispatch<React.SetStateAction<number>>;
  playing: boolean; setPlaying: (v: boolean) => void;
  speed?: number; compact?: boolean;
}) {
  const raf = useRef<number | null>(null);
  const last = useRef<number | null>(null);
  const max = Math.max(0, steps.length - 1);

  useEffect(() => {
    if (!playing || max === 0) { last.current = null; return; }
    const tick = (now: number) => {
      if (last.current !== null) {
        const dt = (now - last.current) / 1000;
        setT((prev) => {
          const next = prev + dt * speed;
          return next >= max ? 0 : next;
        });
      }
      last.current = now;
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      last.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, max, speed]);

  if (!steps.length) return null;

  const i0 = Math.min(max, Math.floor(t));
  const i1 = Math.min(max, i0 + 1);
  const frac = t - i0;
  const hours = steps[i0].hours + (steps[i1].hours - steps[i0].hours) * frac;
  const beached = steps[i0].beached_fraction
    + (steps[i1].beached_fraction - steps[i0].beached_fraction) * frac;
  const disp = steps[i0].displacement_m
    + (steps[i1].displacement_m - steps[i0].displacement_m) * frac;

  return (
    <div className="bg-void/90 backdrop-blur-sm chamfer-sm border border-edge
                    px-2.5 py-2 flex items-center gap-3 min-w-[330px]">
      <button onClick={() => setPlaying(!playing)}
              className="tap w-[26px] h-[26px] chamfer-sm flex items-center justify-center shrink-0"
              style={{ border: "1px solid #3186FF",
                       background: playing ? "rgba(49,134,255,0.22)" : "transparent" }}
              title={playing ? "Pause drift animation" : "Play drift animation"}>
        {playing ? <Pause size={11} className="text-beam" />
                 : <Play size={11} className="text-beam" />}
      </button>
      <button onClick={() => { setPlaying(false); setT(0); }}
              className="tap text-dim hover:text-beam shrink-0" title="Return to NOW">
        <RotateCcw size={12} />
      </button>

      <div className="flex-1 min-w-0">
        <div className="relative h-[22px] flex items-center">
          <input
            type="range" min={0} max={max * 100} value={Math.round(t * 100)}
            onChange={(e) => { setPlaying(false); setT(Number(e.target.value) / 100); }}
            className="absolute inset-0 w-full opacity-0 cursor-pointer z-10"
            aria-label="Forecast horizon" />
          <div className="relative w-full h-[3px] bg-edge">
            <div className="absolute inset-y-0 left-0"
                 style={{ width: `${max ? (t / max) * 100 : 0}%`, background: "#4A93FF",
                          boxShadow: "0 0 8px -2px #4A93FF" }} />
            {steps.map((s, i) => (
              <span key={s.hours}
                    className="absolute -top-[4px] w-[1px] h-[11px]"
                    style={{ left: `${max ? (i / max) * 100 : 0}%`,
                             background: i <= t ? "#4A93FF" : "#243056" }} />
            ))}
            <span className="absolute -top-[4px] w-[9px] h-[11px] chamfer-sm -ml-[4px]
                             pointer-events-none"
                  style={{ left: `${max ? (t / max) * 100 : 0}%`, background: "#4A93FF",
                           boxShadow: "0 0 10px -1px #4A93FF" }} />
          </div>
        </div>
        {!compact && (
          <div className="flex justify-between mt-[3px]">
            {steps.map((s) => (
              <span key={s.hours} className="hud-label" style={{ fontSize: 8 }}>
                {s.hours === 0 ? "NOW" : `+${s.hours}H`}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="shrink-0 text-right leading-none">
        <div className="hud-value text-[14px] text-beam2">
          {hours === 0 ? "NOW" : `+${hours.toFixed(1)}h`}
        </div>
        <div className="hud-label mt-[3px]" style={{ fontSize: 8 }}>
          {(disp / 1000).toFixed(2)} km · {(beached * 100).toFixed(0)}% beached
        </div>
      </div>
    </div>
  );
}
