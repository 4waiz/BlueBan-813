"use client";

/**
 * FORECAST - full-screen drift operations.
 *
 * The map is the whole page here. Everything else is a thin overlay, because
 * the question this screen answers ("where is it going and what does it reach")
 * is spatial.
 */

import React, { useEffect, useMemo, useState } from "react";

import OceanMap, { RasterKey } from "@/components/OceanMap";
import { LayerControl, MapLegend, Timeline } from "@/components/MapControls";
import {
  Panel, Loading, ErrorBox, KV, Caveat, Readout, Chip, Meter,
} from "@/components/hud";
import {
  api, WaterEvent, fmt, fmtInt, pct, bearingToCompass, utc,
} from "@/lib/api";

export default function Forecast() {
  const [event, setEvent] = useState<WaterEvent | null>(null);
  const [fc, setFc] = useState<any>(null);
  const [bounds, setBounds] = useState<number[] | null>(null);
  const [scales, setScales] = useState<Record<string, any> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [raster, setRaster] = useState<RasterKey>("rgb");
  const [opacity, setOpacity] = useState(0.85);
  const [showEvents, setShowEvents] = useState(true);
  const [showWater, setShowWater] = useState(false);
  const [showFlow, setShowFlow] = useState(true);
  const [showParticles, setShowParticles] = useState(true);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const idx = await api.events();
        const id = idx.events[0].event_id;
        const [e, f, l] = await Promise.all([
          api.event(id), api.forecast(id), api.layers(),
        ]);
        setEvent(e); setFc(f); setBounds(l.bounds_lonlat); setScales(l.grid?.scales ?? null);
      } catch (e: any) { setErr(e.message ?? String(e)); }
    })();
  }, []);

  const drift = useMemo(() => {
    const w = fc?.metadata?.wind_at_t0;
    const p = fc?.metadata?.parameters;
    if (!w || !p) return null;
    const f = p.wind_drift_factor ?? 0.03;
    const th = ((p.deflection_deg ?? 15) * Math.PI) / 180;
    const ct = Math.cos(-th), st = Math.sin(-th);
    return { u: f * (w.u_ms * ct - w.v_ms * st), v: f * (w.u_ms * st + w.v_ms * ct) };
  }, [fc]);

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!event || !fc || !bounds) return <Loading what="drift forecast" />;

  const steps = fc.steps as any[];
  const max = steps.length - 1;
  const i0 = Math.min(max, Math.floor(t));
  const i1 = Math.min(max, i0 + 1);
  const frac = t - i0;
  const lerp = (a: number, b: number) => a + (b - a) * frac;
  const cur = {
    hours: lerp(steps[i0].hours, steps[i1].hours),
    displacement_m: lerp(steps[i0].displacement_m, steps[i1].displacement_m),
    bearing_deg: steps[i0].bearing_deg,
    spread_radius_m: lerp(steps[i0].spread_radius_m, steps[i1].spread_radius_m),
    beached_fraction: lerp(steps[i0].beached_fraction, steps[i1].beached_fraction),
  };
  const md = fc.metadata;

  return (
    <div className="relative h-full">
      <div className="absolute inset-0">
        <OceanMap
          bounds={bounds} raster={raster} rasterOpacity={opacity}
          showEvents={showEvents} showWater={showWater}
          showFlow={showFlow} showParticles={showParticles}
          drift={drift}
          exposures={event.exposure} samples={event.samples}
          forecast={steps} forecastT={t}
          glowAt={event.geometry.centroid_lonlat}
          glowRadiusM={event.geometry.equivalent_radius_m}
          className="w-full h-full" />
      </div>

      {/* top-left: layers */}
      <div className="absolute top-3 left-3 z-10 flex flex-col gap-2 items-start">
        <LayerControl
          raster={raster} setRaster={setRaster}
          opacity={opacity} setOpacity={setOpacity}
          showEvents={showEvents} setShowEvents={setShowEvents}
          showWater={showWater} setShowWater={setShowWater}
          showFlow={showFlow} setShowFlow={setShowFlow}
          showParticles={showParticles} setShowParticles={setShowParticles} />
        <MapLegend raster={raster} collapsed scale={scales?.[raster]} />
      </div>

      {/* right: live drift state */}
      <div className="absolute top-3 right-3 bottom-3 z-10 w-[306px] flex flex-col gap-3
                      overflow-y-auto">
        <Panel title="Drift state" accent="#4A93FF" delay={0}>
          <div className="grid grid-cols-2 gap-3">
            <Readout label="Horizon" animate={cur.hours} digits={1}
                     value={fmt(cur.hours, 1)} unit="h" size="lg" color="#4A93FF" />
            <Readout label="Displacement" animate={cur.displacement_m / 1000} digits={2}
                     value={fmt(cur.displacement_m / 1000, 2)} unit="km" size="lg" />
          </div>
          <div className="mt-3">
            <Meter label="Bearing" value={cur.bearing_deg} max={360}
                   display={`${fmt(cur.bearing_deg, 0)}° ${bearingToCompass(cur.bearing_deg)}`}
                   color="#4A93FF" />
            <Meter label="Plume spread (1σ)" value={cur.spread_radius_m} max={2000}
                   display={fmtInt(cur.spread_radius_m)} unit="m" color="#4A93FF" />
            <Meter label="Beached fraction" value={cur.beached_fraction} max={1}
                   display={pct(cur.beached_fraction, 1)} color="#F5C451"
                   hint="Particles driven onto the coastline stop drifting and are recorded as stranded." />
          </div>
        </Panel>

        <Panel title="What this model is" accent="#F5C451" delay={60}>
          <div className="flex items-center gap-2 mb-2">
            <Chip label={md.is_hydrodynamic_model ? "HYDRODYNAMIC" : "NOT HYDRODYNAMIC"}
                  color="#F5C451" />
          </div>
          <p className="text-[11px] leading-[1.7] text-muted">{md.interpretation}</p>
          <div className="mt-3">
            <KV k="Method" v={md.method} />
            <KV k="Class" v={md.model_class} />
            <KV k="Wind source" v={md.wind_source} />
            <KV k="Wind at t₀"
                v={`${fmt(md.wind_at_t0.speed_ms, 2)} m/s from ${fmt(md.wind_at_t0.direction_from_deg, 0)}°`} />
            <KV k="Drift factor" v={`${md.parameters.wind_drift_factor} × wind`} />
            <KV k="Deflection" v={`${md.parameters.deflection_deg}° clockwise`} />
            <KV k="Diffusivity" v={`${md.parameters.horizontal_diffusivity_m2_s} m²/s`} />
          </div>
          <Caveat>{md.validation_status}</Caveat>
        </Panel>

        <Panel title="Not included in this model" accent="#FF4D4D" delay={120}>
          <ul className="space-y-1.5">
            {(md.not_included ?? []).map((x: string) => (
              <li key={x} className="flex gap-2 text-[10.5px] leading-[1.55] text-muted">
                <span className="text-critical shrink-0">-</span><span>{x}</span>
              </li>
            ))}
          </ul>
          {md.coastline_handling && (
            <p className="text-[10.5px] leading-[1.6] text-beam2/80 mt-3 px-2.5 py-2 chamfer-sm"
               style={{ background: "rgba(74,147,255,0.07)",
                        border: "1px solid rgba(74,147,255,0.25)" }}>
              {md.coastline_handling}
            </p>
          )}
        </Panel>

        <Panel title="Asset exposure along the track" delay={180}>
          <div className="space-y-2.5">
            {event.exposure.map((e) => (
              <div key={e.asset.id} className="pb-2.5 border-b border-edge/40 last:border-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="hud-value text-[11px] text-ink truncate">
                    {e.asset.id} · {e.asset.name}
                  </span>
                  <span className="hud-value text-[11px] shrink-0"
                        style={{ color: e.exposure_score >= 0.4 ? "#FF7A45" : "#8A93B8" }}>
                    {fmt(e.exposure_score, 3)}
                  </span>
                </div>
                <div className="hud-label mt-1">
                  {fmt(e.distance_km, 2)} km {e.direction} ·{" "}
                  {e.eta_hours !== null
                    ? <span style={{ color: "#FF7A45" }}>contact +{e.eta_hours} h</span>
                    : "no modelled contact"}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Wind series used" delay={240}>
          <KV k="ERA5 cell"
              v={`${fmt(md.wind_sample_point?.era5_cell_lonlat?.[1], 3)}, ${fmt(md.wind_sample_point?.era5_cell_lonlat?.[0], 3)}`} />
          <KV k="Sampled at"
              v={`${fmt(md.wind_sample_point?.requested_lonlat?.[1], 3)}, ${fmt(md.wind_sample_point?.requested_lonlat?.[0], 3)}`} />
          <KV k="Hours in series" v={fmtInt(fc.wind?.times?.length)} />
          <KV k="t₀" v={utc(md.wind_at_t0.time)} />
          {md.wind_sample_point?.why && (
            <p className="text-[10px] leading-[1.6] text-dim mt-2">
              {md.wind_sample_point.why}
            </p>
          )}
        </Panel>
      </div>

      {/* bottom: timeline */}
      <div className="absolute bottom-3 left-3 z-10">
        <Timeline steps={steps as any} t={t} setT={setT}
                  playing={playing} setPlaying={setPlaying} speed={0.4} />
      </div>
    </div>
  );
}
