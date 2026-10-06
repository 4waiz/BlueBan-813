"use client";
/**
 * INTAKE WATCH: the operator's question, asked per asset.
 *
 * "Is the water in front of my intake unusual, and do I need to act?" For each
 * desalination plant, power-plant cooling intake and industrial intake in the
 * register, the status comes from the open incidents in this workspace: the
 * pipeline's own distance to the asset (incident exposure records) and the
 * wind-only drift scenario's closest approach. Rules are fixed and shown on
 * screen. Intake positions are not public, so distances are to the facility
 * centre from OpenStreetMap; nothing here claims a bloom has reached an intake.
 */
import React, { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Copy, ExternalLink, FlaskConical, Siren } from "lucide-react";
import { useEngineQuery } from "@/lib/engine";
import { EVENT_TYPES, OPEN_STATES } from "@/lib/engine/rules";
import { nextPass } from "@/lib/passes";
import type { Aoi, AssetRow, Incident } from "@/lib/engine/types";
import { Chip, fmt, Loading, Pager, Panel, toast, useFitPage } from "@/components/ui";

type Level = "ALERT" | "WATCH" | "CLEAR" | "NOT_MONITORED";
const LEVEL: Record<Level, { text: string; color: string; rule: string }> = {
  ALERT: { text: "Act now", color: "#FF4D5E", rule: "An open incident within 15 km, or the drift scenario comes within 5 km" },
  WATCH: { text: "Watch", color: "#FFC23D", rule: "An open incident within 30 km" },
  CLEAR: { text: "Clear", color: "#23D484", rule: "Monitored, and no open incident within 30 km" },
  NOT_MONITORED: { text: "Not monitored", color: "#7088B3", rule: "Outside the monitored areas: add the area to WATCH" },
};
const INTAKE_TYPES: Record<string, string> = {
  DESALINATION_PLANT: "Desalination", POWER_PLANT: "Power plant (cooling water)", INDUSTRIAL_INTAKE: "Industrial intake",
};

const hav = (lo1: number, la1: number, lo2: number, la2: number) => {
  const R = 6371e3, r = Math.PI / 180, a = Math.sin(((la2 - la1) * r) / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin(((lo2 - lo1) * r) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
};
const inBox = (a: AssetRow, b: Aoi["bbox"]) => a.lon >= b[0] && a.lon <= b[2] && a.lat >= b[1] && a.lat <= b[3];
/** Compass direction from the asset to the water, i.e. where the operator should look. */
const towards = (lo1: number, la1: number, lo2: number, la2: number) => {
  const r = Math.PI / 180, y = Math.sin((lo2 - lo1) * r) * Math.cos(la2 * r), x = Math.cos(la1 * r) * Math.sin(la2 * r) - Math.sin(la1 * r) * Math.cos(la2 * r) * Math.cos((lo2 - lo1) * r);
  const b = (Math.atan2(y, x) / r + 360) % 360;
  return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"][Math.round(b / 22.5) % 16];
};

interface Row {
  asset: AssetRow; level: Level; aoi: Aoi | null; inc: Incident | null; distM: number | null; dir: string | null;
  drift: { km: number; hours: number } | null; score: number | null;
}

/** The drift scenario's closest approach, as written by pipeline/exposure.py into the exposure basis. */
function closestApproach(basis?: string[]) {
  for (const b of basis || []) {
    const m = /closest approach ([\d.]+) km at \+(\d+) h/.exec(b);
    if (m) return { km: Number(m[1]), hours: Number(m[2]) };
  }
  return null;
}

function alertText(r: Row) {
  if (!r.inc) return "";
  const t = EVENT_TYPES[r.inc.event_type_hypothesis]?.split(" /")[0] || r.inc.event_type_hypothesis;
  const olci = r.inc.sensor_agreement?.["Sentinel-3 OLCI"];
  return [
    `BLUEBAN 813 · ${LEVEL[r.level].text.toUpperCase()} · ${r.asset.name}`,
    `Unusual water ${fmt.km(r.distM)}${r.dir ? ` to the ${r.dir}` : ""} of the facility (${t.toLowerCase()}, ${fmt.num(r.inc.area_km2, 2)} km²), seen by Sentinel-2 on ${fmt.utc(r.inc.observation_time)}.`,
    `Unusual for this place and season: ${fmt.ord(r.inc.temporal?.seasonal_percentile)} percentile against ${r.inc.temporal?.n_seasonal ?? "n/a"} past same-season images.`,
    olci ? `Sentinel-3 cross-check: ${olci.agrees ? "agrees" : olci.agrees === false ? "does not agree" : "not available"}.` : "",
    r.drift ? `Wind-only drift scenario: closest approach ${r.drift.km} km at +${r.drift.hours} h (a scenario, not an ocean forecast).` : "",
    `Recommended: review the evidence and request water samples (the plan includes a clean-water control). Incident ${r.inc.id}.`,
    `Not a confirmed harmful bloom; no concentration is claimed until water samples are tested.`,
  ].filter(Boolean).join("\n");
}

export default function IntakeWatch() {
  const assetsQ = useEngineQuery((e) => e.assets());
  const aoisQ = useEngineQuery((e) => e.aois());
  const listQ = useEngineQuery((e) => e.listIncidents());
  const openIds = useMemo(() => (listQ.data || []).filter((i) => OPEN_STATES.includes(i.status) && i.role !== "negative_control" && i.aoi_id?.startsWith("AE")).map((i) => i.id), [listQ.data]);
  const openQ = useEngineQuery(async (e) => (await Promise.all(openIds.map((id) => e.getIncident(id)))).filter(Boolean) as Incident[], [openIds.join(",")]);
  const [all, setAll] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const now = useMemo(() => new Date(), []);

  const rows = useMemo<Row[]>(() => {
    const aois = (aoisQ.data || []).filter((a) => a.id.startsWith("AE-"));
    const incs = openQ.data || [];
    return (assetsQ.data || [])
      .filter((a) => all ? a.type !== "PUBLIC_BEACH" : a.type in INTAKE_TYPES)
      .map((asset) => {
        const aoi = aois.find((x) => x.id === asset.aoi_id) || aois.find((x) => inBox(asset, x.bbox)) || null;
        let best: Row | null = null;
        for (const inc of incs) {
          const ex = (inc.exposure || []).find((e) => e.asset.id === asset.id || e.asset.name === asset.name);
          const distM = ex?.distance_m ?? (inc.centroid ? hav(inc.centroid[0], inc.centroid[1], asset.lon, asset.lat) : null);
          if (distM == null) continue;
          const drift = closestApproach(ex?.basis);
          const level: Level = distM <= 15e3 || (drift && drift.km <= 5) ? "ALERT" : distM <= 30e3 ? "WATCH" : "CLEAR";
          const dir = inc.centroid ? towards(asset.lon, asset.lat, inc.centroid[0], inc.centroid[1]) : null;
          const cand: Row = { asset, aoi, inc, distM, dir, drift, score: ex?.exposure_score ?? null, level };
          if (!best || distM < (best.distM ?? Infinity)) best = cand;
        }
        if (best && best.level !== "CLEAR") return best;
        return { asset, aoi, inc: null, distM: null, dir: null, drift: null, score: null, level: aoi ? "CLEAR" : "NOT_MONITORED" } as Row;
      })
      .sort((a, b) => ["ALERT", "WATCH", "CLEAR", "NOT_MONITORED"].indexOf(a.level) - ["ALERT", "WATCH", "CLEAR", "NOT_MONITORED"].indexOf(b.level) || (a.distM ?? 1e12) - (b.distM ?? 1e12));
  }, [assetsQ.data, aoisQ.data, openQ.data, all]);

  const tableBox = useRef<HTMLDivElement>(null);
  const pg = useFitPage(rows, tableBox);
  const counts = rows.reduce((m, r) => { m[r.level] = (m[r.level] || 0) + 1; return m; }, {} as Record<Level, number>);
  const cur = rows.find((r) => r.asset.id === sel) || rows.find((r) => r.inc) || rows[0] || null;
  const loading = assetsQ.loading || aoisQ.loading || listQ.loading || openQ.loading;

  return (
    <div className="grid gap-3 p-3 short:gap-2 short:p-2 xl:h-full xl:min-h-0 xl:grid-cols-[minmax(0,1.6fr)_minmax(360px,1fr)]">
      <Panel kicker="ACT · per intake, not per incident" title="Intake watch: is the water in front of each intake unusual?"
        right={<div className="flex gap-1">
          <button onClick={() => setAll(false)} className={`rounded-md px-2.5 py-1 text-[11.5px] font-semibold ${!all ? "bg-beam-fill text-white" : "text-muted hover:text-ink"}`}>Intakes</button>
          <button onClick={() => setAll(true)} className={`rounded-md px-2.5 py-1 text-[11.5px] font-semibold ${all ? "bg-beam-fill text-white" : "text-muted hover:text-ink"}`}>All coastal assets</button>
        </div>}
        className="min-w-0 xl:min-h-0" bodyClass="flex min-h-0 flex-col gap-2 px-3 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          {(Object.keys(LEVEL) as Level[]).map((l) => (
            <div key={l} title={LEVEL[l].rule} className="flex items-center gap-2 rounded-md border border-edge bg-deep/60 px-3 py-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: LEVEL[l].color, boxShadow: `0 0 8px ${LEVEL[l].color}` }} />
              <span className="hud-value text-[15px] font-bold" style={{ color: LEVEL[l].color }}>{counts[l] || 0}</span>
              <span className="text-[11.5px] text-muted">{LEVEL[l].text}</span>
            </div>))}
          <Pager {...pg} className="ml-auto" />
        </div>
        <div ref={tableBox} className="scroll-quiet min-h-0 flex-1 overflow-y-auto rounded-md border border-edge">
          {loading && !rows.length ? <Loading className="p-4" label="Loading assets and open incidents…" /> : (
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 z-10 bg-panel"><tr className="border-b border-edge text-left text-[10.5px] uppercase tracking-wider text-dim">
                <th className="whitespace-nowrap px-3 py-2">Status</th><th className="pr-3">Asset</th><th className="whitespace-nowrap pr-3">Nearest open incident</th>
                <th className="whitespace-nowrap pr-3 text-right" title="Wind-only drift scenario: closest approach of the modelled drift">Drift scenario</th>
                <th className="whitespace-nowrap pr-3" title="Latest usable Sentinel-2 image over the area, and the next expected pass">Eyes on it</th></tr></thead>
              <tbody>
                {pg.rows.map((r) => {
                  const np = r.aoi ? nextPass([r.aoi], now) : null;
                  return (
                    <tr key={r.asset.id} onClick={() => setSel(r.asset.id)} className={`cursor-pointer border-b border-edge/60 hover:bg-panel2/50 ${cur?.asset.id === r.asset.id ? "bg-beam/10" : ""}`}>
                      <td className="px-3 py-2"><Chip label={LEVEL[r.level].text} color={LEVEL[r.level].color} /></td>
                      <td className="pr-3"><div className="font-semibold text-ink">{r.asset.name}</div><div className="text-[10.5px] text-dim">{INTAKE_TYPES[r.asset.type] || r.asset.type.replace(/_/g, " ").toLowerCase()}{r.aoi ? ` · ${r.aoi.name}` : ""}</div></td>
                      <td className="pr-3">{r.inc ? <><span className="hud-value">{fmt.km(r.distM)}</span> <span className="text-muted">{r.dir}</span><div className="text-[10.5px] text-dim">{r.inc.id} · {fmt.utc(r.inc.observation_time, false)}</div></> : <span className="text-dim">none within 30 km</span>}</td>
                      <td className="hud-value pr-3 text-right">{r.drift ? <>{r.drift.km} km<div className="text-[10.5px] text-dim">at +{r.drift.hours} h</div></> : <span className="text-dim">–</span>}</td>
                      <td className="pr-3 text-muted">{r.aoi?.last_observation ? fmt.utc(r.aoi.last_observation, false) : "–"}<div className="text-[10.5px] text-dim">{np ? `next pass in ${np.inText}` : r.aoi ? "" : "not in WATCH"}</div></td>
                    </tr>);
                })}
              </tbody>
            </table>)}
        </div>
        <p className="text-[11px] text-dim">Distances are to the facility centre (OpenStreetMap): intake positions are not public, so none is guessed. Status rules: {(["ALERT", "WATCH"] as Level[]).map((l) => `${LEVEL[l].text}: ${LEVEL[l].rule.toLowerCase()}`).join(" · ")}.</p>
      </Panel>

      <Panel kicker="What the operator receives" title={cur ? cur.asset.name : "Alert preview"} className="min-w-0 xl:min-h-0" bodyClass="flex min-h-0 flex-col gap-3 scroll-quiet overflow-y-auto px-4 pb-4">
        {!cur ? <Loading /> : !cur.inc ? (
          <div className="rounded-md border border-edge bg-deep/60 p-4 text-[12.5px] text-muted">
            <Chip label={LEVEL[cur.level].text} color={LEVEL[cur.level].color} />
            <p className="mt-2">{cur.level === "NOT_MONITORED" ? "This facility is outside the ten monitored areas. Draw its waters on the map in Incident Control to add it to WATCH; its seasonal baseline is then built from the Sentinel-2 archive." : "No open incident within 30 km. BLUEBAN keeps screening every new Sentinel-2 image of this water against its own seasonal history."}</p>
          </div>
        ) : (<>
          <div className="flex items-center gap-2"><Siren size={18} style={{ color: LEVEL[cur.level].color }} /><Chip label={LEVEL[cur.level].text} color={LEVEL[cur.level].color} /><span className="text-[11.5px] text-muted">{LEVEL[cur.level].rule}</span></div>
          <pre className="whitespace-pre-wrap rounded-md border border-edge bg-deep/80 p-3 font-mono text-[11.5px] leading-relaxed text-ink">{alertText(cur)}</pre>
          <div className="flex flex-wrap gap-2">
            <button className="btn px-3 py-1.5 text-[12px]" onClick={() => { navigator.clipboard?.writeText(alertText(cur)).then(() => toast("Alert text copied"), () => toast("Copy failed", "err")); }}><Copy size={14} /> Copy alert</button>
            <Link href={`/incident?id=${cur.inc.id}`} className="btn px-3 py-1.5 text-[12px]"><ExternalLink size={14} /> Open the evidence</Link>
            <Link href={`/field?id=${cur.inc.id}`} className="btn btn-primary px-3 py-1.5 text-[12px]"><FlaskConical size={14} /> Plan water samples</Link>
          </div>
          <div className="rounded-md border border-edge bg-deep/50 p-3 text-[11.5px] text-muted">
            <div className="hud-kicker mb-1">How it is delivered</div>
            The API raises an alert on each new incident and posts it as JSON to the operator&apos;s webhook (<span className="hud-value">BLUEBAN_ALERT_WEBHOOK</span>), from where their own email, SMS or control-room system takes over. This hosted demo shows the message instead of sending it.
          </div>
          {cur.score != null && <div className="text-[11px] text-dim" title="Proximity × drift reach × asset sensitivity, from pipeline/exposure.py">Exposure score {fmt.num(cur.score, 3)} (proximity × drift reach × sensitivity)</div>}
        </>)}
      </Panel>
    </div>
  );
}
