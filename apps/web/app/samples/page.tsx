"use client";

/**
 * SAMPLES - the field mission plan.
 *
 * The product claim this screen has to earn: satellite observation does not
 * replace physical water testing, it decides where testing is worth doing.
 * Each point therefore carries the question it answers, not just a coordinate.
 */

import React, { useEffect, useState } from "react";
import { Download, Crosshair, FlaskConical } from "lucide-react";

import OceanMap, { RasterKey } from "@/components/OceanMap";
import { MapLegend } from "@/components/MapControls";
import { Panel, Loading, ErrorBox, KV, Chip, Caveat, Readout } from "@/components/hud";
import { api, WaterEvent, SamplePoint, fmt, fmtInt, resolve } from "@/lib/api";

const ROLE_COLOR: Record<string, string> = {
  EVENT_CORE: "#FF4D4D",
  LEADING_EDGE: "#FF7A45",
  ASSET_BOUNDARY: "#F5C451",
  BACKGROUND_CONTROL: "#3FD1A0",
  UNCERTAINTY_POINT: "#C77DFF",
};

export default function Samples() {
  const [event, setEvent] = useState<WaterEvent | null>(null);
  const [bounds, setBounds] = useState<number[] | null>(null);
  const [scales, setScales] = useState<Record<string, any> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [focus, setFocus] = useState<[number, number] | null>(null);
  const [raster, setRaster] = useState<RasterKey>("anomaly");

  useEffect(() => {
    (async () => {
      try {
        const idx = await api.events();
        const id = idx.events[0].event_id;
        const [e, l] = await Promise.all([api.event(id), api.layers()]);
        setEvent(e); setBounds(l.bounds_lonlat); setScales(l.grid?.scales ?? null);
        setSel(e.samples[0]?.id ?? null);
      } catch (e: any) { setErr(e.message ?? String(e)); }
    })();
  }, []);

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!event || !bounds) return <Loading what="sampling plan" />;

  const points = event.samples;
  const chosen = points.find((p) => p.id === sel) ?? points[0];

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_378px] gap-3 p-3 h-full min-h-0">
      {/* map */}
      <div className="panel chamfer relative min-h-[340px] overflow-hidden scanlines
                      panel-in">
        <div className="absolute inset-0">
          <OceanMap
            bounds={bounds} raster={raster} rasterOpacity={0.9}
            showEvents showFlow={false} showParticles={false} showTrack={false}
            exposures={event.exposure} samples={points}
            glowAt={event.geometry.centroid_lonlat}
            glowRadiusM={event.geometry.equivalent_radius_m}
            focus={focus} focusZoom={13.6}
            className="w-full h-full" />
        </div>
        <div className="absolute top-2.5 left-2.5 z-10 flex flex-col gap-2 items-start">
          <div className="bg-void/88 backdrop-blur-sm chamfer-sm border border-edge flex">
            {(["anomaly", "rgb", "turbidity", "ndci"] as RasterKey[]).map((k) => (
              <button key={k} onClick={() => setRaster(k)}
                      className="hud-label px-2.5 py-[6px] tap border-r border-edge/60 last:border-0"
                      style={{ background: raster === k ? "rgba(49,134,255,0.2)" : "transparent",
                               color: raster === k ? "#4A93FF" : "#5A6490" }}>
                {k.toUpperCase()}
              </button>
            ))}
          </div>
          <MapLegend raster={raster} collapsed scale={scales?.[raster]} />
        </div>
      </div>

      {/* manifest */}
      <div className="flex flex-col gap-3 min-w-0 overflow-y-auto pr-1">
        <Panel title="Field sampling plan" accent="#3FD1A0"
               right={<Chip label={`${points.length} POINTS`} color="#3FD1A0" />}>
          <p className="text-[11px] leading-[1.7] text-muted">
            Satellite remote sensing does not replace physical water testing.
            This plan spends a limited sampling budget where a measurement
            resolves the most uncertainty.
          </p>
          <div className="flex gap-2 mt-3">
            <a href={resolve(`/api/events/${event.event_id}/samples?fmt=csv`)} download
               className="chamfer-sm hud-label px-2.5 py-1.5 tap flex items-center gap-1.5
                          border border-nominal/50 text-nominal hover:bg-nominal/10">
              <Download size={11} /> export CSV
            </a>
            <a href={resolve(`/api/events/${event.event_id}/samples`)} target="_blank" rel="noreferrer"
               className="chamfer-sm hud-label px-2.5 py-1.5 tap flex items-center gap-1.5
                          border border-beam/50 text-beam2 hover:bg-beam/10">
              <Download size={11} /> GeoJSON
            </a>
          </div>
        </Panel>

        <Panel title="Manifest" tight>
          <div className="divide-y divide-edge/40">
            {points.map((p, i) => {
              const c = ROLE_COLOR[p.role] ?? "#8A93B8";
              const on = p.id === sel;
              return (
                <button key={p.id}
                        onClick={() => { setSel(p.id); setFocus([p.lon, p.lat]); }}
                        className={`w-full text-left px-2.5 py-2.5 tap flex gap-2.5 panel-in
                                    ${on ? "bg-beam/10" : "row-hover"}`}
                        style={{
                          animationDelay: `${i * 55}ms`,
                          boxShadow: on ? "inset 2px 0 0 #3186FF" : undefined,
                        }}>
                  <span className="w-[22px] h-[22px] shrink-0 rounded-full flex items-center
                                   justify-center hud-value text-[9.5px]"
                        style={{ border: `1.4px solid ${c}`, color: c,
                                 background: `${c}22` }}>
                    {p.id.replace("S", "")}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block hud-value text-[10.5px] tracking-wide2 uppercase"
                          style={{ color: c }}>
                      {p.role.replace(/_/g, " ")}
                    </span>
                    <span className="block hud-value text-[10px] text-dim mt-[3px]">
                      {p.lat.toFixed(5)}, {p.lon.toFixed(5)}
                    </span>
                  </span>
                  <span className="hud-label shrink-0 self-start">P{p.priority}</span>
                </button>
              );
            })}
          </div>
        </Panel>

        {chosen && (
          <Panel title={`${chosen.id} detail`}
                 accent={ROLE_COLOR[chosen.role] ?? "#8A93B8"}
                 right={
                   <button onClick={() => setFocus([chosen.lon, chosen.lat])}
                           className="hud-label tap flex items-center gap-1 hover:text-beam">
                     <Crosshair size={11} /> centre
                   </button>
                 }>
            <Readout label="Question this point answers" value={chosen.role_question}
                     size="sm" mono={false} color="#C9D0EE" />
            <p className="text-[11px] leading-[1.7] text-muted mt-3">{chosen.rationale}</p>
            <div className="mt-3">
              <KV k="Latitude" v={chosen.lat.toFixed(6)} />
              <KV k="Longitude" v={chosen.lon.toFixed(6)} />
              <KV k="Priority" v={`P${chosen.priority}`} />
              <KV k="RX anomaly" v={fmt(chosen.anomaly_score, 1)} />
              <KV k="From shore" v={chosen.distance_from_shore_m !== null
                    ? `${fmtInt(chosen.distance_from_shore_m)} m` : "-"} />
              <KV k="To asset" v={chosen.distance_to_asset_m !== null
                    ? `${fmtInt(chosen.distance_to_asset_m)} m` : "-"} />
            </div>
            <div className="mt-3">
              <div className="hud-label mb-2 flex items-center gap-1.5">
                <FlaskConical size={11} /> recommended analyses
              </div>
              <ul className="space-y-1.5">
                {chosen.expected_variables.map((v) => (
                  <li key={v} className="flex gap-2 text-[10.5px] leading-[1.5] text-muted">
                    <span style={{ color: ROLE_COLOR[chosen.role] ?? "#8A93B8" }}>›</span>
                    <span>{v}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Panel>
        )}

        <Panel title="Why a background control is mandatory" accent="#3FD1A0">
          <p className="text-[11px] leading-[1.7] text-muted">
            A laboratory value from the event core cannot be interpreted on its
            own. Without a same-day measurement of unaffected water in the same
            body, there is nothing to compare it against, and a reading that is
            normal for this coastline can be mistaken for an anomaly. The planner
            always includes one, at least 800 m offshore and in the
            lowest-anomaly water available.
          </p>
          <Caveat>
            These are screening-led suggestions. Vessel access, permits, sea
            state and local knowledge take precedence; the plan exports to CSV
            and GeoJSON so a field lead can amend it.
          </Caveat>
        </Panel>
      </div>
    </div>
  );
}
