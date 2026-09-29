"""Incident report export (Markdown).

The report is what an operator forwards to a regulator or an asset owner, so it
carries the whole evidence chain: what was observed, by which sensor and
product, what the model said and which model version said it, what humans
decided, what the field measured, and the audit trail with its hashes.
"""
from __future__ import annotations

from . import incidents as inc_mod


def _v(x, nd=3):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def incident_report_md(inc: dict) -> str:
    L = []
    etype = inc.get("event_type_hypothesis")
    L.append(f"# Incident report {inc['id']}")
    L.append("")
    L.append(f"**Status:** {inc.get('status')}  ")
    L.append(f"**Event type (hypothesis):** {etype} - "
             f"{inc_mod.EVENT_TYPES.get(etype, '')}  ")
    L.append(f"**AOI:** {inc.get('aoi_name') or inc.get('aoi_id')}  ")
    L.append(f"**Observation:** {inc.get('observation_time')}  ")
    L.append(f"**Detected:** {inc.get('detected_at')}  ")
    L.append(f"**Raised by model:** {inc.get('model_id')}  ")
    L.append(f"**Severity / confidence:** {_v(inc.get('severity'), 2)} / "
             f"{_v(inc.get('confidence'), 2)} (reported separately, never multiplied)  ")
    if inc.get("disposition"):
        L.append(f"**Disposition:** {inc['disposition']}  ")
    L.append("")
    L.append("> Optical satellite evidence identifies an anomaly in how the water "
             "scatters and absorbs light. It does not identify a species, a toxin or a "
             "substance. Field sampling and laboratory analysis confirm.")
    L.append("")

    rec = inc.get("recommendation") or inc_mod.recommend(inc).to_dict()
    L.append("## Recommended action")
    L.append(f"**{rec['action']}** (priority {rec['priority']})")
    for r in rec.get("reasons", []):
        L.append(f"- {r}")
    if rec.get("required_evidence"):
        L.append("")
        L.append("Required evidence:")
        for r in rec["required_evidence"]:
            L.append(f"- {r}")
    if rec.get("decision_deadline_utc"):
        L.append(f"\nDecision deadline: {rec['decision_deadline_utc']}")
    L.append("")

    L.append("## Evidence")
    t = inc.get("temporal") or {}
    L.append("### Temporal context")
    L.append(f"- Seasonal percentile of the primary indicator: "
             f"{_v(t.get('seasonal_percentile'), 1)} "
             f"(n = {t.get('n_seasonal', 'n/a')} same-season observations)")
    if t.get("persistence_frac") is not None:
        L.append(f"- Persistence at this location: {_v(t['persistence_frac'], 2)} of "
                 f"past same-season dates")
    wq = (inc.get("water_quality") or {}).get("estimates") or {}
    if wq:
        L.append("### Water-quality indicators")
        L.append("| Indicator | Value | Units | Kind |")
        L.append("|---|---|---|---|")
        for k, v in wq.items():
            L.append(f"| {k} | {_v(v.get('value'))} | {v.get('units', '')} | "
                     f"{v.get('quantity_kind', '')} |")
    agree = inc.get("sensor_agreement") or {}
    if agree:
        L.append("### Cross-sensor evidence")
        for k, v in agree.items():
            if isinstance(v, dict):
                L.append(f"- {k}: {'agrees' if v.get('agrees') else 'does not agree' if v.get('agrees') is False else 'not available'}"
                         f"{' - ' + v['note'] if v.get('note') else ''}")
    qf = inc.get("quality_flags") or []
    if qf:
        L.append("### Quality flags")
        for q in qf:
            L.append(f"- {q}")
    L.append("")

    if inc.get("reviews"):
        L.append("## Operator reviews")
        L.append("| When | Reviewer | Decision | From -> to | Note |")
        L.append("|---|---|---|---|---|")
        for r in inc["reviews"]:
            L.append(f"| {r['created_at']} | {r['reviewer']} | {r['decision']}"
                     f"{' -> ' + r['new_hypothesis'] if r.get('new_hypothesis') else ''} | "
                     f"{r['status_before']} -> {r['status_after']} | "
                     f"{(r.get('note') or '').replace('|', '/')} |")
        L.append("")
    if inc.get("samples"):
        L.append("## Field sampling plan")
        L.append("| Code | Role | Lat | Lon | Status |")
        L.append("|---|---|---|---|---|")
        for s in inc["samples"]:
            L.append(f"| {s['code']} | {s['role']} | {s['lat']:.5f} | {s['lon']:.5f} | "
                     f"{s['status']} |")
        L.append("")
    if inc.get("measurements"):
        L.append("## Field and laboratory measurements")
        L.append("| Parameter | Value | Unit | Sample | Method | QC | Entered by |")
        L.append("|---|---|---|---|---|---|---|")
        for m in inc["measurements"]:
            L.append(f"| {m['parameter']} | {m['value']} | {m['unit']} | "
                     f"{m.get('sample_id') or ''} | {m.get('method') or ''} | "
                     f"{m.get('qc_flag')} | {m['entered_by']} |")
        L.append("")

    prov = inc.get("provenance") or {}
    if prov.get("sources"):
        L.append("## Provenance")
        L.append("| Sensor | Scene | Acquired | Level | Provider | Licence |")
        L.append("|---|---|---|---|---|---|")
        for s in prov["sources"]:
            L.append(f"| {s.get('sensor', '')} | {s.get('scene_id', '')} | "
                     f"{s.get('acquisition_utc', '')} | {s.get('processing_level', '')} | "
                     f"{s.get('provider', '')} | {s.get('licence', '')} |")
        L.append("")
    if inc.get("audit_trail"):
        L.append("## Audit trail (hash-chained)")
        L.append("| Seq | When | Actor | Action | Hash |")
        L.append("|---|---|---|---|---|")
        for a in sorted(inc["audit_trail"], key=lambda x: x["seq"]):
            L.append(f"| {a['seq']} | {a['at']} | {a['actor']} | {a['action']} | "
                     f"`{a['hash'][:16]}` |")
    L.append("")
    L.append("_Generated by BLUEBAN 813. Built by Team Kanban._")
    return "\n".join(L)
