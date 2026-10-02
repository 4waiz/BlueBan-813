"use client";
/**
 * WATCH: what is monitored, when it was last seen, and what changed from its
 * own seasonal baseline. Series come from scripts/build_watch.py (Sentinel-2
 * L2A zone statistics per acquisition); anomaly hits from scripts/build_detect.py.
 */
import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { pipelineUrl, useEngineQuery } from "@/lib/engine";
import { nextPass } from "@/lib/passes";
import type { Aoi } from "@/lib/engine/types";
import { Chip, fmt, Panel } from "@/components/ui";
import { useElementSize } from "@/lib/useSize";

type Row = { date: string; datetime?: string; platform?: string; n_water?: number; cloud?: number; error?: boolean; f?: Record<string, { p50: number; p95: number } | null> };
type Series = { aoi_id: string; rows: Row[]; window: string[]; n_datatakes: number; n_ok: number };
type DetectDates = { dates: { date: string; BLOOM_LIKE: { n: number; area_km2: number; max_z: number | null }; SEDIMENT_LIKE: { n: number; area_km2: number; max_z: number | null }; SURFACE_FILM_LIKE: { n: number; area_km2: number; max_z: number | null } }[] };

const FEATS: [string, string][] = [["NDCI", "Chlorophyll index (NDCI) · 95th percentile"], ["MCI", "Chlorophyll peak (MCI) · 95th percentile"], ["TUR_NECHAD2016", "Turbidity (not calibrated) · 95th percentile"], ["HUE_ANGLE", "Water colour (hue angle) · median"]];
const doy = (d: string) => { const t = new Date(d + "T00:00:00Z"); return Math.floor((t.getTime() - Date.UTC(t.getUTCFullYear(), 0, 1)) / 86400e3) + 1; };
const ddist = (a: number, b: number) => Math.min(Math.abs(a - b), 365 - Math.abs(a - b));

function seasonalPct(rows: Row[], feat: string, stat: "p95" | "p50", target: Row) {
  const v = target.f?.[feat]?.[stat];
  if (v == null) return null;
  const td = doy(target.date), ty = target.date.slice(0, 4);
  const hist = rows.filter((r) => r !== target && r.f?.[feat] && r.date.slice(0, 4) !== ty && ddist(doy(r.date), td) <= 45).map((r) => r.f![feat]![stat]);
  if (hist.length < 6) return null;
  return (100 * hist.filter((h) => h < v).length) / hist.length;
}

function SeriesChart({ s, feat, det }: { s: Series; feat: string; det: DetectDates | null }) {
  const box = useElementSize<HTMLDivElement>();
  const stat = feat === "HUE_ANGLE" ? "p50" : "p95";
  const pts = s.rows.filter((r) => !r.error && (r.n_water || 0) > 500 && r.f?.[feat]).map((r) => ({ t: new Date(r.date).getTime(), v: r.f![feat]![stat], d: r.date }));
  const W = Math.max(400, box.width), H = Math.max(200, box.height), L = 50, R = 12, T = 12, B = 26;
  if (!pts.length) return <div ref={box.ref} className="grid h-full place-items-center text-muted">No usable images yet</div>;
  const t0 = Math.min(...pts.map((p) => p.t)), t1 = Math.max(...pts.map((p) => p.t));
  const vs = pts.map((p) => p.v).sort((a, b) => a - b);
  const lo = vs[Math.floor(vs.length * 0.01)], hi = vs[Math.floor(vs.length * 0.99)];
  const x = (t: number) => L + ((t - t0) / (t1 - t0 || 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo || 1)) * (H - T - B);
  // seasonal envelope: median and 90th percentile by day-of-year bin, all years
  const bins = Array.from({ length: 37 }, (_, i) => i * 10);
  const env = bins.map((b) => { const vv = pts.filter((p) => ddist(doy(p.d), b + 5) <= 20).map((p) => p.v).sort((a, c) => a - c); return vv.length > 4 ? { b, med: vv[Math.floor(vv.length / 2)], p90: vv[Math.floor(vv.length * 0.9)] } : null; });
  const years = [...new Set(pts.map((p) => p.d.slice(0, 4)))];
  const hits = new Set((det?.dates || []).filter((d) => (d.BLOOM_LIKE?.n || 0) + (d.SEDIMENT_LIKE?.n || 0) + (d.SURFACE_FILM_LIKE?.n || 0) > 0).map((d) => d.date));
  return (
    <div ref={box.ref} className="h-full w-full">
      <svg width={W} height={H}>
        <rect x={L} y={T} width={W - L - R} height={H - T - B} fill="#040915" stroke="#16284D" />
        {years.map((yr) => { const tt = Date.UTC(Number(yr), 0, 1); return tt > t0 && tt < t1 ? <g key={yr}><line x1={x(tt)} x2={x(tt)} y1={T} y2={H - B} stroke="#16284D" /><text x={x(tt) + 3} y={H - 8} fontSize={10} fill="#93A6CB">{yr}</text></g> : null; })}
        {years.map((yr) => env.filter(Boolean).map((e) => { const tt = Date.UTC(Number(yr), 0, e!.b + 5); if (tt < t0 || tt > t1) return null; return <line key={`${yr}-${e!.b}`} x1={x(tt)} x2={x(tt) + 3} y1={y(e!.p90)} y2={y(e!.p90)} stroke="#FFC23D" strokeOpacity={0.35} />; }))}
        {pts.map((p, i) => <circle key={`${p.d}-${p.t}-${i}`} cx={x(p.t)} cy={y(p.v)} r={hits.has(p.d) ? 3.6 : 1.8} fill={hits.has(p.d) ? "#FF4D5E" : "#4D93FF"} opacity={hits.has(p.d) ? 1 : 0.8}><title>{p.d}: {p.v.toFixed(4)}{hits.has(p.d) ? " · possible event flagged" : ""}</title></circle>)}
        {[lo, (lo + hi) / 2, hi].map((v, i) => <text key={i} x={L - 6} y={y(v) + 3} textAnchor="end" fontSize={10} fill="#93A6CB">{v.toFixed(3)}</text>)}
      </svg>
    </div>
  );
}

export default function WatchPage() {
  const aois = useEngineQuery((e) => e.aois());
  const incidents = useEngineQuery((e) => e.listIncidents());
  const uae = useMemo(() => (aois.data || []).filter((a) => a.id.startsWith("AE-")), [aois.data]);
  const [sel, setSel] = useState<string | null>(null);
  const [feat, setFeat] = useState("NDCI");
  const [series, setSeries] = useState<Record<string, Series | null>>({});
  const [det, setDet] = useState<Record<string, DetectDates | null>>({});
  const now = useMemo(() => new Date(), []);
  useEffect(() => {
    uae.forEach((a) => {
      if (series[a.id] !== undefined) return;
      setSeries((s) => ({ ...s, [a.id]: null }));
      fetch(pipelineUrl(`watch/${a.id}.json`)).then((r) => (r.ok ? r.json() : null)).then((d) => setSeries((s) => ({ ...s, [a.id]: d }))).catch(() => undefined);
      fetch(pipelineUrl(`detect/${a.id}.json`)).then((r) => (r.ok ? r.json() : null)).then((d) => setDet((s) => ({ ...s, [a.id]: d }))).catch(() => undefined);
    });
  }, [uae]); // eslint-disable-line react-hooks/exhaustive-deps
  const rows = uae.map((a) => {
    const s = series[a.id];
    const ok = (s?.rows || []).filter((r) => !r.error && (r.n_water || 0) > 500);
    const last = ok[ok.length - 1];
    const pct = last && s ? seasonalPct(ok, "NDCI", "p95", last) : null;
    const pctT = last && s ? seasonalPct(ok, "TUR_NECHAD2016", "p95", last) : null;
    const open = (incidents.data || []).filter((i) => i.aoi_id === a.id && ["DETECTED", "UNDER_REVIEW", "FIELD_VALIDATION_REQUIRED"].includes(i.status)).length;
    const np = nextPass([a], now);
    return { a, s, ok, last, pct, pctT, open, np };
  });
  const ranked = [...rows].sort((x, y) => (y.pct ?? -1) - (x.pct ?? -1));
  const cur = rows.find((r) => r.a.id === (sel || ranked[0]?.a.id));
  return (
    <div className="grid h-full min-h-0 gap-3 p-3 short:gap-2 short:p-2 grid-rows-[auto_minmax(0,1fr)]">
      <Panel title="Monitored areas" kicker="WATCH · Sentinel-2 image history" bodyClass="overflow-x-auto p-3">
        <table className="w-full text-[12px]">
          <thead><tr className="border-b border-edge text-left text-[10.5px] uppercase tracking-wider text-dim">
            <th className="py-2 pr-3">Area</th><th className="pr-3">Coast</th><th className="pr-3" title="Latest image with enough clear water to measure">Latest image</th><th className="pr-3 text-right" title="Usable images: enough clear water to measure">Images</th>
            <th className="pr-3 text-right" title="Chlorophyll index (NDCI), 95th percentile over the area's water. The rank (e.g. 70th) compares it with the same time of year in past years.">Chlorophyll · rank</th><th className="pr-3 text-right" title="Turbidity, 95th percentile over the area's water. Generic formula, not calibrated. The rank compares it with the same time of year in past years.">Turbidity · rank</th><th className="pr-3" title="Chlorophyll compared with the same time of year in past years">Vs past years</th><th className="pr-3 text-right" title="Open incidents in this area">Open</th><th className="pr-3" title="Expected from the satellite's regular repeat orbit. Plans change, and clouds can spoil a pass.">Next pass (expected)</th></tr></thead>
          <tbody>
            {ranked.map(({ a, s, ok, last, pct, pctT, open, np }) => (
              <tr key={a.id} onClick={() => setSel(a.id)} className={`cursor-pointer border-b border-edge/60 hover:bg-panel2/50 ${cur?.a.id === a.id ? "bg-beam/10" : ""}`}>
                <td className="py-2 pr-3"><div className="font-semibold">{a.name}</div><div className="hud-value text-[10.5px] text-dim">{a.id}</div></td>
                <td className="pr-3 text-muted">{a.coast}</td>
                <td className="pr-3">{last ? <>{fmt.utc(last.datetime || last.date)}<div className="text-[10.5px] text-muted">{last.platform} · {(last.n_water || 0).toLocaleString()} water pixels</div></> : s === null ? <span className="text-dim">loading…</span> : <span className="text-dim">no data yet</span>}</td>
                <td className="hud-value pr-3 text-right">{ok.length || "–"}</td>
                <td className="hud-value pr-3 text-right">{last?.f?.NDCI ? last.f.NDCI.p95.toFixed(3) : "–"} <span className="text-caution">{pct != null ? `· ${fmt.ord(pct)}` : ""}</span></td>
                <td className="hud-value pr-3 text-right">{last?.f?.TUR_NECHAD2016 ? last.f.TUR_NECHAD2016.p95.toFixed(1) : "–"} <span className="text-caution">{pctT != null ? `· ${fmt.ord(pctT)}` : ""}</span></td>
                <td className="pr-3">{pct == null ? <span className="text-dim" title="Not enough past images from this time of year">n/a</span> : pct >= 95 ? <Chip label="UNUSUAL" color="#FF4D5E" /> : pct >= 80 ? <Chip label="ELEVATED" color="#FFC23D" /> : <Chip label="NORMAL" color="#23D484" />}</td>
                <td className="hud-value pr-3 text-right">{open ? <span className="text-critical">{open}</span> : 0}</td>
                <td className="pr-3 text-muted">{np ? `in ${np.inText} · ${np.platform}` : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title={cur ? `${cur.a.name} · ${FEATS.find((f) => f[0] === feat)?.[1]}` : "Trend"} right={
        <div className="flex gap-1">{FEATS.map(([k, l]) => <button key={k} onClick={() => setFeat(k)} className={`rounded-md px-2 py-1 text-[11px] font-semibold ${feat === k ? "bg-beam text-white" : "text-muted hover:text-ink"}`}>{l.split(" (")[0].split(" P")[0]}</button>)}</div>
      } bodyClass="flex min-h-0 flex-col p-3">
        <div className="min-h-0 flex-1">{cur?.s ? <SeriesChart s={cur.s} feat={feat} det={det[cur.a.id] || null} /> : <div className="grid h-full place-items-center text-muted">Pick an area that has image history</div>}</div>
        <div className="mt-2 flex flex-wrap items-center gap-4 text-[11px] text-muted">
          <span><span className="text-beam2">●</span> one usable image</span><span><span className="text-critical">●</span> possible event flagged that day</span><span title="Most past values for that time of year fall below this line"><span className="text-caution">—</span> usual high for the season</span>
          {cur?.s && <span>{cur.s.n_ok}/{cur.s.n_datatakes} images processed · {cur.s.window.join(" → ")}</span>}
          <Link href="/incidents" className="ml-auto text-beam2">Open verification queue →</Link>
        </div>
      </Panel>
    </div>
  );
}
