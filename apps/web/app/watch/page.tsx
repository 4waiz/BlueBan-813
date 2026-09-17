"use client";

/**
 * WATCH - the regional monitoring record.
 *
 * This screen holds the argument that separates BLUEBAN 813 from a map viewer:
 * an absolute index threshold is meaningless across water bodies, so every
 * observation is judged against the local multi-year distribution for that
 * place and that season.
 */

import React, { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer, ComposedChart, Scatter, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, ReferenceArea, Area,
} from "recharts";

import { Panel, Loading, ErrorBox, KV, Chip, Caveat, Readout } from "@/components/hud";
import { api, fmt, fmtInt } from "@/lib/api";

const ZONES = [
  { key: "hotspot_inner_gulf", label: "Hotspot · inner gulf", color: "#FF7A45" },
  { key: "reference_offshore", label: "Reference · offshore", color: "#4A93FF" },
];

const VARS = [
  { key: "TURBIDITY_PROXY_p95", label: "Turbidity proxy (zone P95)" },
  { key: "TURBIDITY_PROXY", label: "Turbidity proxy (zone median)" },
  { key: "NDCI_p95", label: "NDCI proxy (zone P95)" },
  { key: "NDCI", label: "NDCI proxy (zone median)" },
  { key: "R665", label: "Reflectance 665 nm" },
  { key: "R560", label: "Reflectance 560 nm" },
];

const TARGET = "2025-06-01";

export default function Watch() {
  const [ts, setTs] = useState<any>(null);
  const [rep, setRep] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [zone, setZone] = useState(ZONES[0].key);
  const [vr, setVr] = useState(VARS[0].key);

  useEffect(() => {
    (async () => {
      try {
        const [a, v] = await Promise.all([
          api.timeseries(),
          api.validation().catch(() => null),
        ]);
        setTs(a);
        setRep(v?.temporal_baseline ?? null);
      } catch (e: any) { setErr(e.message ?? String(e)); }
    })();
  }, []);

  const series = useMemo(() => {
    if (!ts?.[zone]) return [];
    return ts[zone]
      .map((o: any) => ({
        t: new Date(o.datetime).getTime(),
        date: o.datetime.slice(0, 10),
        v: o[vr],
        cloud: o.cloud_cover,
        n: o.n_water_px,
      }))
      .filter((d: any) => d.v !== null && d.v !== undefined && Number.isFinite(d.v))
      .sort((a: any, b: any) => a.t - b.t);
  }, [ts, zone, vr]);

  const stats = useMemo(() => {
    const b = rep?.zones?.[zone]?.baselines?.[vr];
    if (!b) return null;
    return {
      median: b.median, p90: b.percentiles?.["90"], p95: b.percentiles?.["95"],
      p99: b.percentiles?.["99"], p05: b.percentiles?.["5"],
      n: b.n_observations, range: b.date_range,
      target: b.target_assessment, trend: b.trend, seasonal: b.seasonal,
    };
  }, [rep, zone, vr]);

  const targetPoint = series.find((d: any) => d.date === TARGET);

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!ts) return <Loading what="monitoring record" />;

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3">
      <Panel title="Local baseline - why absolute thresholds do not work" accent="#3FD1A0">
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {ZONES.map((z) => (
            <button key={z.key} onClick={() => setZone(z.key)}
                    className="chamfer-sm hud-label px-2.5 py-[5px] tap border"
                    style={{
                      borderColor: zone === z.key ? z.color : "#1B2444",
                      color: zone === z.key ? z.color : "#5A6490",
                      background: zone === z.key ? `${z.color}1A` : "transparent",
                    }}>
              {z.label} · {fmtInt(ts[z.key]?.length)} obs
            </button>
          ))}
          <span className="flex-1" />
          {VARS.map((v) => (
            <button key={v.key} onClick={() => setVr(v.key)}
                    className="chamfer-sm hud-label px-2 py-[5px] tap border"
                    style={{
                      borderColor: vr === v.key ? "#3186FF" : "#1B2444",
                      color: vr === v.key ? "#4A93FF" : "#5A6490",
                      background: vr === v.key ? "rgba(49,134,255,0.14)" : "transparent",
                    }}>
              {v.label}
            </button>
          ))}
        </div>

        <div style={{ width: "100%", height: 350 }}>
          <ResponsiveContainer>
            <ComposedChart data={series} margin={{ top: 8, right: 14, bottom: 4, left: 4 }}>
              <CartesianGrid stroke="#1B2444" strokeDasharray="2 5" />
              {stats && (
                <>
                  <ReferenceArea y1={stats.p05} y2={stats.p95}
                                 fill="#3186FF" fillOpacity={0.07} stroke="none" />
                  <ReferenceLine y={stats.median} stroke="#3FD1A0" strokeDasharray="4 4"
                                 label={{ value: "median", position: "insideTopLeft",
                                          fill: "#3FD1A0", fontSize: 9,
                                          fontFamily: "var(--font-mono)" }} />
                  <ReferenceLine y={stats.p95} stroke="#F5C451" strokeDasharray="3 4"
                                 label={{ value: "P95", position: "insideTopLeft",
                                          fill: "#F5C451", fontSize: 9,
                                          fontFamily: "var(--font-mono)" }} />
                  <ReferenceLine y={stats.p99} stroke="#FF7A45" strokeDasharray="3 4"
                                 label={{ value: "P99", position: "insideTopLeft",
                                          fill: "#FF7A45", fontSize: 9,
                                          fontFamily: "var(--font-mono)" }} />
                </>
              )}
              <XAxis dataKey="t" type="number" scale="time"
                     domain={["dataMin", "dataMax"]}
                     tickFormatter={(v) => new Date(v).toISOString().slice(0, 7)}
                     tick={{ fill: "#5A6490", fontSize: 9, fontFamily: "var(--font-mono)" }}
                     stroke="#243056" />
              <YAxis tick={{ fill: "#5A6490", fontSize: 9, fontFamily: "var(--font-mono)" }}
                     stroke="#243056" width={56}
                     tickFormatter={(v) => Number(v).toFixed(3)} />
              <Tooltip
                contentStyle={{ background: "#0A0F22", border: "1px solid #243056",
                                borderRadius: 0, fontFamily: "var(--font-mono)",
                                fontSize: 11 }}
                labelStyle={{ color: "#5A6490" }}
                labelFormatter={(v) => new Date(Number(v)).toISOString().slice(0, 10)}
                formatter={(v: any, n: any) => [Number(v).toFixed(5), n]} />
              <Scatter dataKey="v" name="observation"
                       fill={ZONES.find((z) => z.key === zone)?.color ?? "#4A93FF"}
                       fillOpacity={0.6} />
              {targetPoint && (
                <ReferenceLine x={targetPoint.t} stroke="#F4F6FF" strokeWidth={1.2}
                               label={{ value: "2025-06-01 observation",
                                        position: "insideTopRight", fill: "#F4F6FF",
                                        fontSize: 9, fontFamily: "var(--font-mono)" }} />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <p className="text-[11px] leading-[1.7] text-muted mt-2">
          Each dot is one cloud-screened Sentinel-2 acquisition. The shaded band
          is the P5-P95 envelope for this zone. A detection is only an event if it
          sits in the upper tail of this distribution for its season; otherwise it
          is a permanent feature of the coastline.
        </p>
      </Panel>

      <div className="grid lg:grid-cols-3 gap-3">
        <Panel title="This observation" accent="#3FD1A0" delay={60}>
          {stats?.target ? (
            <>
              <Readout label="Seasonal percentile"
                       animate={stats.target.seasonal_percentile} digits={1}
                       value={fmt(stats.target.seasonal_percentile, 1)} unit="pctile"
                       size="xl"
                       color={stats.target.seasonal_percentile >= 90 ? "#FF7A45" : "#3FD1A0"} />
              <div className="mt-3">
                <KV k="Value" v={fmt(stats.target.value, 5)} />
                <KV k="All-time pctile" v={fmt(stats.target.all_time_percentile, 1)} />
                <KV k="Same-season n" v={fmtInt(stats.target.n_seasonal)} />
                <KV k="Window" v={`±${stats.target.window_days} days of day-of-year`} />
                <KV k="Matched date"
                    v={`${stats.target.matched_date} (${stats.target.days_from_target} d off)`} />
                <KV k="State" v={stats.target.state}
                    color={stats.target.state === "NORMAL" ? "#3FD1A0" : "#F5C451"} />
              </div>
              <Caveat>
                Comparing a June observation against a full-year record would
                confuse a seasonal cycle with an event, so the comparison is
                restricted to observations within {stats.target.window_days} days
                of the same day-of-year.
              </Caveat>
            </>
          ) : (
            <p className="text-[11px] text-dim leading-relaxed">
              No matched observation within the tolerance for this variable.
            </p>
          )}
        </Panel>

        <Panel title="Distribution" delay={120}>
          {stats ? (
            <>
              <KV k="Observations" v={fmtInt(stats.n)} />
              <KV k="Record span" v={`${stats.range?.[0]} → ${stats.range?.[1]}`} />
              <KV k="P5" v={fmt(stats.p05, 5)} />
              <KV k="Median" v={fmt(stats.median, 5)} color="#3FD1A0" />
              <KV k="P90" v={fmt(stats.p90, 5)} />
              <KV k="P95" v={fmt(stats.p95, 5)} color="#F5C451" />
              <KV k="P99" v={fmt(stats.p99, 5)} color="#FF7A45" />
            </>
          ) : <p className="text-[11px] text-dim">Baseline report not loaded.</p>}
        </Panel>

        <Panel title="Long-term trend" delay={180}>
          {stats?.trend?.slope_per_year !== null && stats?.trend ? (
            <>
              <Readout label="Slope" value={`${fmt(stats.trend.slope_per_year, 6)} /yr`}
                       size="md" />
              <div className="mt-3">
                <KV k="R²" v={fmt(stats.trend.r_squared, 4)} />
                <KV k="n" v={fmtInt(stats.trend.n)} />
                <KV k="Span" v={`${fmt(stats.trend.span_years, 1)} years`} />
              </div>
              <Caveat>
                With an R² this low the slope is not a meaningful trend. It is
                reported so a reviewer can see that we checked, rather than
                omitted because it was inconvenient.
              </Caveat>
            </>
          ) : <p className="text-[11px] text-dim">Insufficient observations for a trend.</p>}
        </Panel>
      </div>

      <Panel title="Seasonal structure" delay={240}>
        {stats?.seasonal && Object.keys(stats.seasonal).length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="hud-label border-b border-edge">
                  <th className="text-left py-2 font-normal">Month</th>
                  {Object.keys(stats.seasonal).map((mo) => (
                    <th key={mo} className="text-right py-2 font-normal px-2">{mo}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="hud-value">
                {(["n", "median", "p90", "p95"] as const).map((row) => (
                  <tr key={row} className="border-b border-edge/35">
                    <td className="py-2 text-muted hud-label">{row}</td>
                    {Object.values(stats.seasonal).map((s: any, i) => (
                      <td key={i} className="text-right px-2 text-ink">
                        {row === "n" ? fmtInt(s[row]) : fmt(s[row], 4)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="text-[11px] text-dim">No seasonal breakdown available.</p>}
      </Panel>
    </div>
  );
}
