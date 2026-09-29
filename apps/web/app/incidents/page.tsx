"use client";
/** VERIFICATION QUEUE - every incident, what it needs next, and who decided what. */
import React, { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Filter } from "lucide-react";
import { useEngineQuery } from "@/lib/engine";
import { EVENT_TYPES, OPEN_STATES } from "@/lib/engine/rules";
import type { IncidentStatus } from "@/lib/engine/types";
import { Chip, fmt, Panel } from "@/components/ui";

const FILTERS: { key: string; label: string; test: (s: IncidentStatus, role?: string) => boolean }[] = [
  { key: "review", label: "Needs review", test: (s) => s === "DETECTED" || s === "UNDER_REVIEW" },
  { key: "field", label: "Awaiting field", test: (s) => s === "FIELD_VALIDATION_REQUIRED" },
  { key: "open", label: "All open", test: (s) => OPEN_STATES.includes(s) },
  { key: "closed", label: "Closed", test: (s) => !OPEN_STATES.includes(s) },
  { key: "all", label: "All", test: () => true },
];

export default function IncidentsPage() {
  const list = useEngineQuery((e) => e.listIncidents());
  const alerts = useEngineQuery((e) => e.alerts());
  const [f, setF] = useState("open");
  const rows = useMemo(() => (list.data || []).filter((i) => FILTERS.find((x) => x.key === f)!.test(i.status, i.role)), [list.data, f]);
  const open = (alerts.data || []).filter((a) => !a.acknowledged_at);
  return (
    <div className="grid gap-3 p-3 xl:grid-cols-[1fr_380px]">
      <Panel title="Verification queue" kicker="DETECT → VERIFY" right={
        <div className="flex items-center gap-1"><Filter size={14} className="text-muted" />
          {FILTERS.map((x) => <button key={x.key} onClick={() => setF(x.key)} className={`rounded-md px-2.5 py-1 text-[11.5px] font-semibold ${f === x.key ? "bg-beam text-white" : "text-muted hover:text-ink"}`}>{x.label}</button>)}
        </div>} bodyClass="p-3">
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead><tr className="border-b border-edge text-left text-[10.5px] uppercase tracking-wider text-dim">
              <th className="py-2 pr-3">Incident</th><th className="pr-3">Status</th><th className="pr-3">Hypothesis</th><th className="pr-3">AOI</th>
              <th className="pr-3">Observed</th><th className="pr-3 text-right">Severity</th><th className="pr-3 text-right">Confidence</th><th className="pr-3 text-right">Area</th><th /></tr></thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.id} className="border-b border-edge/60 hover:bg-panel2/50">
                  <td className="py-2.5 pr-3"><div className="hud-value font-semibold">{i.id}</div>{i.role === "negative_control" && <div className="text-[10.5px] text-violet">negative control</div>}</td>
                  <td className="pr-3"><Chip label={i.status} /></td>
                  <td className="pr-3">{EVENT_TYPES[i.event_type_hypothesis]?.split(" /")[0] || i.event_type_hypothesis}</td>
                  <td className="pr-3 text-muted">{i.aoi_id}</td>
                  <td className="pr-3 text-muted">{fmt.utc(i.observation_time)}</td>
                  <td className="hud-value pr-3 text-right">{fmt.num(i.severity)}</td>
                  <td className="hud-value pr-3 text-right">{fmt.pct(i.confidence)}</td>
                  <td className="hud-value pr-3 text-right">{i.area_km2 != null ? `${i.area_km2.toFixed(2)} km²` : "n/a"}</td>
                  <td className="text-right"><Link href={`/incident?id=${i.id}`} className="btn px-2.5 py-1 text-[11.5px]">Investigate <ArrowRight size={13} /></Link></td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={9} className="py-6 text-center text-muted">No incidents in this view.</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[11px] text-dim">A decision here never edits the model's original prediction; it is recorded next to it, becomes a verified label when it is a CONFIRM or FALSE POSITIVE, and enters the LEARN queue.</p>
      </Panel>
      <Panel title="Alerts" kicker={`${open.length} unacknowledged`} bodyClass="p-3 space-y-2">
        {(alerts.data || []).map((a) => (
          <div key={a.id} className={`rounded-md border p-3 text-[12px] ${a.acknowledged_at ? "border-edge opacity-60" : "border-caution/50 bg-caution/5"}`}>
            <div className="flex justify-between"><span className="hud-value text-[11px] text-muted">{fmt.utc(a.created_at)}</span><Chip label={a.level} color={a.acknowledged_at ? "#5D7299" : "#FFC23D"} /></div>
            <p className="mt-1">{a.message}</p>
            {a.incident_id && <Link href={`/incident?id=${a.incident_id}`} className="mt-1 inline-block text-[11.5px] text-beam2">Open {a.incident_id} →</Link>}
            {a.acknowledged_at && <div className="text-[10.5px] text-dim">acknowledged by {a.acknowledged_by}</div>}
          </div>
        ))}
        {!alerts.data?.length && <p className="text-[12px] text-muted">No alerts.</p>}
        <p className="text-[10.5px] text-dim">Alerts are factual and ask for analyst review; they never announce a toxic bloom or a spill. Browser notifications and an e-mail/webhook channel are described in docs/METHODOLOGY.md (ACT).</p>
      </Panel>
    </div>
  );
}
