"use client";

/**
 * OVERVIEW — the mission-control composition.
 *
 * Left    : the operational sequence, showing how the conclusion was reached
 * Centre  : the hero ocean view, with the instrument cluster above it
 * Right   : narrow telemetry bars
 *
 * Nothing here is hardcoded. Every value is read from the pipeline output.
 */

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import OceanMap, { RasterKey } from "@/components/OceanMap";
import {
  Panel, Readout, Gauge, Meter, SequenceItem, SeqState, Chip, StatusDot,
  Loading, ErrorBox, Caveat, KV, SimulatedBadge,
} from "@/components/hud";
import {
  api, WaterEvent, PRIORITY_COLOR, CLASS_COLOR, fmt, fmtInt, pct, utc,
  bearingToCompass,
} from "@/lib/api";

const RASTERS: { key: RasterKey; label: string }[] = [
  { key: "rgb", label: "TRUE COLOUR" },
  { key: "anomaly", label: "ANOMALY" },
  { key: "ndci", label: "NDCI" },
  { key: "turbidity", label: "TURBIDITY" },
];

export default function Overview() {
  const [event, setEvent] = useState<WaterEvent | null>(null);
  const [bounds, setBounds] = useState<number[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [raster, setRaster] = useState<RasterKey>("rgb");
  const [fi, setFi] = useState(0);

  useEffect(() => {
    (async () => {
      try {
        const idx = await api.events();
        const first = idx.events?.[0];
        if (!first) throw new Error("No events in outputs/events/index.json");
        const [e, l] = await Promise.all([api.event(first.event_id), api.layers()]);
        setEvent(e);
        setBounds(l.bounds_lonlat);
      } catch (e: any) {
        setErr(e.message ?? String(e));
      }
    })();
  }, []);

  const seq = useMemo(() => buildSequence(event), [event]);

  if (err) {
    return (
      <div className="p-6 max-w-3xl">
        <ErrorBox error={err}
          hint="Start the API with `uvicorn services.api.main:app --port 8813`, and build outputs with `python scripts/build_demo_event.py`." />
      </div>
    );
  }
  if (!event || !bounds) return <Loading what="event telemetry" />;

  const pc = PRIORITY_COLOR[event.state] ?? "#5A6490";
  const cc = CLASS_COLOR[event.classification.top_class] ?? "#8A93B8";
  const steps = event.forecast.steps;
  const step = steps[Math.min(fi, steps.length - 1)];
  const topExp = event.exposure[0];
  const veto = event.assessment.rules_fired.find((r) => r.veto);
  const ta = event.temporal?.assessment;

  const snr = event.quality?.informative_bands?.median_snr;
  const nInf = event.quality?.informative_bands?.n;
  const turb = event.indices?.TURBIDITY_PROXY;
  const ndci = event.indices?.NDCI;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[264px_minmax(0,1fr)_282px] gap-3 p-3 h-full min-h-0">
      {/* ================================================== LEFT: sequence */}
      <div className="flex flex-col gap-3 min-w-0 overflow-y-auto pr-1">
        <Panel title="Operational sequence" tight accent={pc}>
          <div className="divide-y divide-edge/40">
            {seq.map((s) => (
              <SequenceItem key={s.name} state={s.state} name={s.name} detail={s.detail} />
            ))}
          </div>
        </Panel>

        <Panel title="Verdict" accent={pc}>
          <div className="flex items-start gap-3">
            <StatusDot color={pc} pulse={event.state === "HIGH_PRIORITY"} size={9} />
            <div className="min-w-0">
              <div className="hud-value text-[17px] tracking-wide2" style={{ color: pc }}>
                {event.state.replace("_", " ")}
              </div>
              <p className="text-[10.5px] leading-[1.6] text-muted mt-2">
                {event.assessment.priority_reason}
              </p>
            </div>
          </div>
          {veto && (
            <div className="mt-3 px-2.5 py-2 chamfer-sm"
                 style={{ background: "rgba(74,147,255,0.08)",
                          border: "1px solid rgba(74,147,255,0.3)" }}>
              <div className="hud-label mb-1" style={{ color: "#4A93FF" }}>
                temporal veto applied
              </div>
              <p className="text-[10px] leading-[1.55] text-beam2/85">
                A spatial detector flags anything that differs from its neighbours.
                The multi-year record is what separates an event from a permanent
                feature of this coastline.
              </p>
            </div>
          )}
        </Panel>

        <Panel title="Optical hypothesis" accent={cc}>
          <Readout label="Leading class" value={event.classification.label}
                   size="sm" color={cc} mono={false} />
          <div className="mt-3 space-y-[3px]">
            {Object.entries(event.classification.scores)
              .filter(([, v]) => v > 0.01)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 4)
              .map(([k, v]) => (
                <Meter key={k} label={k.replace(/_/g, " ")} value={v} max={1}
                       display={pct(v, 0)} color={CLASS_COLOR[k] ?? "#8A93B8"} />
              ))}
          </div>
          <Caveat>
            Optical hypothesis only. Not a chemical or biological identification.
            Laboratory analysis of a physical sample is required to confirm.
          </Caveat>
        </Panel>
      </div>

      {/* ================================================= CENTRE: hero */}
      <div className="flex flex-col gap-3 min-w-0 min-h-0">
        {/* instrument cluster */}
        <Panel tight>
          <div className="flex items-center justify-around gap-2 flex-wrap py-1">
            <Gauge label="Severity" value={event.severity} max={1}
                   display={fmt(event.severity, 2)} color={pc} size={104} />
            <Gauge label="Confidence" value={event.confidence} max={1}
                   display={fmt(event.confidence, 2)} color="#3186FF" size={104}
                   sub="capped: no in-situ" />
            <Gauge label="Event area" value={event.geometry.area_km2} max={5}
                   display={fmt(event.geometry.area_km2, 3)} unit="km²"
                   color="#4A93FF" size={104} />
            <Gauge label="Spectral Δ" value={event.anomaly.event_percentile_in_scene}
                   max={100} display={fmt(event.anomaly.event_percentile_in_scene, 1)}
                   unit="pctile" color="#F5C451" size={104} />
            <Gauge label="Turbidity proxy" value={turb?.event_median ?? null}
                   min={-1} max={0} display={fmt(turb?.event_median, 3)}
                   color="#F5C451" size={104}
                   sub={`bg ${fmt(turb?.background_median, 3)}`} />
            <Gauge label="NDCI proxy" value={ndci?.event_median ?? null}
                   min={-0.5} max={0.5} display={fmt(ndci?.event_median, 3)}
                   color="#3FD1A0" size={104}
                   sub={`bg ${fmt(ndci?.background_median, 3)}`} />
          </div>
        </Panel>

        {/* hero map */}
        <div className="panel chamfer relative flex-1 min-h-[300px] scanlines overflow-hidden">
          <div className="absolute inset-0">
            <OceanMap
              bounds={bounds}
              raster={raster}
              showEvents
              exposures={event.exposure}
              samples={event.samples}
              forecast={steps}
              forecastIndex={fi}
              className="w-full h-full"
            />
          </div>

          {/* raster selector */}
          <div className="absolute top-2.5 left-2.5 z-10 flex gap-[3px]">
            {RASTERS.map((r) => (
              <button key={r.key} onClick={() => setRaster(r.key)}
                      className="chamfer-sm hud-label px-2.5 py-[5px] transition-colors backdrop-blur-sm"
                      style={{
                        background: raster === r.key ? "rgba(49,134,255,0.2)" : "rgba(10,15,34,0.85)",
                        border: `1px solid ${raster === r.key ? "#3186FF" : "#1B2444"}`,
                        color: raster === r.key ? "#4A93FF" : "#5A6490",
                      }}>
                {r.label}
              </button>
            ))}
          </div>

          {/* forecast scrubber */}
          <div className="absolute bottom-2.5 left-2.5 z-10 flex items-center gap-[3px]
                          bg-void/85 backdrop-blur-sm chamfer-sm px-1 py-1 border border-edge">
            <span className="hud-label px-2">drift</span>
            {steps.map((s, i) => (
              <button key={s.hours} onClick={() => setFi(i)}
                      className="chamfer-sm hud-value text-[10px] px-2.5 py-[5px] transition-colors"
                      style={{
                        background: fi === i ? "rgba(74,147,255,0.22)" : "transparent",
                        color: fi === i ? "#4A93FF" : "#5A6490",
                        border: `1px solid ${fi === i ? "#4A93FF" : "transparent"}`,
                      }}>
                {s.hours === 0 ? "NOW" : `+${s.hours}H`}
              </button>
            ))}
          </div>

          {/* scene stamp */}
          <div className="absolute top-2.5 right-12 z-10 text-right pointer-events-none">
            <div className="hud-label">{event.observation.primary_sensor}</div>
            <div className="hud-value text-[10px] text-muted mt-[3px]">
              {event.observation.scene_id}
            </div>
            <div className="hud-value text-[10px] text-dim mt-[2px]">
              {event.observation.pixel_size_m} m · EPSG:{event.observation.epsg_native}
            </div>
          </div>
        </div>
      </div>

      {/* =============================================== RIGHT: telemetry */}
      <div className="flex flex-col gap-3 min-w-0 overflow-y-auto pr-1">
        <Panel title="Event telemetry">
          <Meter label="Drift displacement" value={step?.displacement_m ?? 0} max={5000}
                 display={fmt((step?.displacement_m ?? 0) / 1000, 2)} unit="km" />
          <Meter label="Drift bearing" value={step?.bearing_deg ?? 0} max={360}
                 display={`${fmt(step?.bearing_deg, 0)}° ${bearingToCompass(step?.bearing_deg ?? 0)}`}
                 color="#4A93FF" />
          <Meter label="Plume spread (1σ)" value={step?.spread_radius_m ?? 0} max={2000}
                 display={fmtInt(step?.spread_radius_m)} unit="m" color="#4A93FF" />
          <Meter label="Beached fraction" value={step?.beached_fraction ?? 0} max={1}
                 display={pct(step?.beached_fraction, 1)} color="#F5C451" />
          <Meter label="Wind speed"
                 value={event.forecast.metadata?.wind_at_t0?.speed_ms} max={15}
                 display={fmt(event.forecast.metadata?.wind_at_t0?.speed_ms, 2)} unit="m/s" />
          <Meter label="Nearest asset" value={topExp ? 20 - topExp.distance_km : 0} max={20}
                 display={fmt(topExp?.distance_km, 2)} unit="km" color="#FF7A45" />
          <Meter label="Max asset exposure" value={topExp?.exposure_score ?? 0} max={1}
                 display={fmt(topExp?.exposure_score, 3)} color="#FF7A45" />
          <Meter label="ETA to asset"
                 value={topExp?.eta_hours !== null && topExp?.eta_hours !== undefined
                          ? 48 - topExp.eta_hours : 0}
                 max={48}
                 display={topExp?.eta_hours !== null && topExp?.eta_hours !== undefined
                          ? `+${fmt(topExp.eta_hours, 0)}` : "none"}
                 unit="h" color="#FF4D4D" />
          <Meter label="Valid coverage" value={event.quality?.scene?.valid_fraction} max={1}
                 display={pct(event.quality?.scene?.valid_fraction, 1)} color="#3FD1A0" />
          <Meter label="Cloud" value={1 - (event.quality?.scene?.cloud_fraction ?? 0)} max={1}
                 display={pct(event.quality?.scene?.cloud_fraction, 2)} color="#3FD1A0" />
          <Meter label="Spectral SNR (median)" value={snr} max={40}
                 display={fmt(snr, 1)} color="#3FD1A0" />
        </Panel>

        <Panel title="Temporal context"
               right={ta ? <Chip label={`n=${ta.n_seasonal}`} /> : undefined}>
          {ta ? (
            <>
              <Readout label="Seasonal percentile"
                       value={fmt(ta.seasonal_percentile, 1)} unit="pctile"
                       size="lg"
                       color={ta.seasonal_percentile >= 90 ? "#FF7A45" : "#3FD1A0"}
                       sub={`vs ${ta.n_seasonal} same-season observations`} />
              <div className="mt-3">
                <KV k="All-time pctile" v={fmt(ta.all_time_percentile, 1)} />
                <KV k="Matched date" v={ta.matched_date} />
                <KV k="Offset" v={`${ta.days_from_target} d`} />
                <KV k="State" v={ta.state}
                    color={ta.state === "NORMAL" ? "#3FD1A0" : "#F5C451"} />
              </div>
            </>
          ) : (
            <p className="text-[10.5px] leading-[1.6] text-dim">
              Multi-year baseline not yet built. Run
              <span className="hud-value text-muted"> scripts/build_baseline.py</span>.
              Without it, a spatial anomaly cannot be separated from a permanent
              coastal feature.
            </p>
          )}
        </Panel>

        <Panel title="Scene integrity">
          <KV k="Bands total" v={fmtInt(event.quality?.scene?.n_bands_total)} />
          <KV k="Bands product-good" v={fmtInt(event.quality?.scene?.n_bands_good)} />
          <KV k="Bands flagged bad" v={fmtInt(event.quality?.scene?.n_bands_flagged_bad)}
              color="#F5C451" />
          <KV k="Water-informative" v={`${fmtInt(nInf)} bands`} color="#3FD1A0" />
          <KV k="Informative range"
              v={event.quality?.informative_bands?.range_nm
                  ? `${event.quality.informative_bands.range_nm[0]}–${event.quality.informative_bands.range_nm[1]} nm`
                  : "—"} />
          <KV k="Water pixels" v={fmtInt(event.quality?.water_mask?.px_water_final)} />
          <KV k="Provenance" v={pct(event.provenance_summary.completeness, 0)}
              color="#3FD1A0" />
        </Panel>

        <Panel title="813 status" right={<SimulatedBadge compact />}>
          <p className="text-[10px] leading-[1.6] text-beam2/80">
            {event.satellite_813.warning}
          </p>
          <div className="mt-2">
            <KV k="Simulated bands" v={fmtInt(event.satellite_813.n_bands)} />
            <KV k="With source support" v={fmtInt(event.satellite_813.n_bands_supported)} />
            <KV k="Spec resolution" v={`${event.satellite_813.spatial_resolution_m_specified} m`} />
            <KV k="Simulated at" v={`${event.satellite_813.spatial_resolution_m_simulated} m`}
                color="#F5C451" />
          </div>
          <Link href="/data"
                className="mt-3 flex items-center gap-1.5 hud-label hover:text-beam transition-colors"
                style={{ color: "#4A93FF" }}>
            view full provenance <ArrowUpRight size={11} />
          </Link>
        </Panel>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- sequence */

function buildSequence(e: WaterEvent | null):
  { state: SeqState; name: string; detail: string }[] {
  if (!e) {
    return [{ state: "pending", name: "Awaiting telemetry", detail: "—" }];
  }
  const ta = e.temporal?.assessment;
  const veto = e.assessment.rules_fired.find((r) => r.veto);
  const topExp = e.exposure[0];
  const q = e.quality ?? {};

  return [
    {
      state: "done",
      name: "Regional watch",
      detail: `Sentinel-3 OLCI reference · ${fmtInt(q.water_mask?.px_water_final)} water px`,
    },
    {
      state: "done",
      name: "Quality screening",
      detail: `${pct(q.scene?.valid_fraction, 1)} valid · ${pct(q.scene?.cloud_fraction, 2)} cloud`,
    },
    {
      state: "done",
      name: "Anomaly detected",
      detail: `RX ${fmt(e.anomaly.event_mean_rx, 0)} · ${fmt(e.anomaly.event_percentile_in_scene, 1)}th pctile`,
    },
    {
      state: "done",
      name: "813 fingerprint",
      detail: `${fmtInt(q.informative_bands?.n)} informative bands · SNR ${fmt(q.informative_bands?.median_snr, 1)}`,
    },
    {
      state: e.classification.top_class === "UNKNOWN_ANOMALY" ? "warn" : "done",
      name: "Classification",
      detail: `${e.classification.label} · ${pct(e.classification.confidence, 0)} margin`,
    },
    {
      state: ta ? (veto ? "vetoed" : "done") : "pending",
      name: "Temporal check",
      detail: ta
        ? `${fmt(ta.seasonal_percentile, 1)}th seasonal pctile${veto ? " · veto applied" : ""}`
        : "baseline not built",
    },
    {
      state: "done",
      name: "Trajectory",
      detail: `${fmt((e.forecast.steps.at(-1)?.displacement_m ?? 0) / 1000, 2)} km @ 48 h · wind-driven`,
    },
    {
      state: topExp && topExp.exposure_score >= 0.4 ? "warn" : "done",
      name: "Asset exposure",
      detail: topExp
        ? `${topExp.asset.id} at ${fmt(topExp.distance_km, 2)} km · ${fmt(topExp.exposure_score, 3)}`
        : "no assets configured",
    },
    {
      state: "pending",
      name: "Field validation",
      detail: `${e.samples.length} sample points planned · none collected`,
    },
  ];
}
