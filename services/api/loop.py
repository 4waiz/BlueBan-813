"""Closed-loop endpoints: incidents, reviews, field data, training, models, audit.

Mounted by ``services/api/main.py``. All writes go through
:class:`services.api.store.Store`, which audits every change.
"""
from __future__ import annotations

import csv
import io
import json
import os
from functools import lru_cache

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from pipeline import incidents as inc_mod
from . import trainer
from .store import MEASUREMENT_PARAMETERS, Store

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
router = APIRouter(prefix="/api")


@lru_cache(maxsize=1)
def store() -> Store:
    return Store()


def _404(e):
    raise HTTPException(404, f"not found: {e}")


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class ReviewIn(BaseModel):
    reviewer: str = Field(..., min_length=1, max_length=80)
    decision: str = Field(..., pattern="^(CONFIRM|FALSE_POSITIVE|RECLASSIFY|"
                                       "NEEDS_FIELD_SAMPLE|INSUFFICIENT_EVIDENCE)$")
    new_hypothesis: str | None = Field(None, max_length=40)
    note: str = Field("", max_length=2000)
    evidence_viewed: list[str] = Field(default_factory=list, max_length=20)


class TransitionIn(BaseModel):
    to: str
    actor: str = Field(..., min_length=1, max_length=80)
    reason: str = Field("", max_length=500)


class SampleIn(BaseModel):
    code: str | None = Field(None, max_length=8)
    role: str = Field(..., max_length=24)
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)
    question: str | None = Field(None, max_length=300)
    analytes: list[str] = Field(default_factory=list)
    rationale: str | None = Field(None, max_length=600)


class SamplePlanIn(BaseModel):
    actor: str = Field(..., min_length=1, max_length=80)
    points: list[SampleIn] = Field(..., max_length=20)


class SamplePatchIn(BaseModel):
    actor: str = Field(..., min_length=1, max_length=80)
    lon: float | None = Field(None, ge=-180, le=180)
    lat: float | None = Field(None, ge=-90, le=90)
    status: str | None = None
    role: str | None = None


class MeasurementIn(BaseModel):
    actor: str = Field(..., min_length=1, max_length=80)
    parameter: str
    value: float
    unit: str
    sample_id: str | None = None
    method: str | None = Field(None, max_length=120)
    measured_at: str | None = None
    lab: str | None = Field(None, max_length=120)
    qc_flag: str = Field("UNCHECKED", max_length=24)


class CsvIn(BaseModel):
    actor: str = Field(..., min_length=1, max_length=80)
    csv: str = Field(..., max_length=200_000)


class RetrainIn(BaseModel):
    task: str = Field("triage", pattern=r"^(triage|quantify:[a-z_]+)$")
    requested_by: str = Field(..., min_length=1, max_length=80)


class PromoteIn(BaseModel):
    approved_by: str = Field(..., min_length=1, max_length=80)
    note: str = Field("", max_length=1000)


class ActorNoteIn(BaseModel):
    actor: str = Field(..., min_length=1, max_length=80)
    note: str = Field("", max_length=1000)


# --------------------------------------------------------------------------- #
# Incidents
# --------------------------------------------------------------------------- #
@router.get("/incidents", tags=["incidents"])
def list_incidents(status: str | None = None, operational_only: bool = False):
    return {"incidents": store().list_incidents(status, not operational_only),
            "states": inc_mod.STATES, "decisions": inc_mod.DECISIONS,
            "event_types": inc_mod.EVENT_TYPES}


@router.get("/incidents/{iid}", tags=["incidents"])
def get_incident(iid: str):
    inc = store().get_incident(iid)
    if not inc:
        _404(iid)
    inc["audit_trail"] = store().audit_log("incident", iid, limit=100)
    return inc


@router.post("/incidents/{iid}/review", tags=["verify"])
def review(iid: str, body: ReviewIn):
    try:
        return store().add_review(iid, body.reviewer, body.decision,
                                  body.new_hypothesis, body.note, body.evidence_viewed)
    except KeyError as e:
        _404(e)
    except (ValueError, inc_mod.TransitionError) as e:
        raise HTTPException(409, str(e))


@router.post("/incidents/{iid}/transition", tags=["verify"])
def transition(iid: str, body: TransitionIn):
    try:
        return store().transition(iid, body.to, body.actor, body.reason)
    except KeyError as e:
        _404(e)
    except inc_mod.TransitionError as e:
        raise HTTPException(409, str(e))


# --------------------------------------------------------------------------- #
# Field validation
# --------------------------------------------------------------------------- #
@router.put("/incidents/{iid}/samples", tags=["field"])
def plan_samples(iid: str, body: SamplePlanIn):
    try:
        return {"samples": store().replace_sample_plan(
            iid, [p.model_dump() for p in body.points], body.actor)}
    except KeyError as e:
        _404(e)


@router.patch("/samples/{sid}", tags=["field"])
def patch_sample(sid: str, body: SamplePatchIn):
    patch = {k: v for k, v in body.model_dump().items() if k != "actor" and v is not None}
    try:
        return store().update_sample(sid, patch, body.actor)
    except KeyError as e:
        _404(e)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/incidents/{iid}/samples.csv", tags=["field"], response_class=PlainTextResponse)
def samples_csv(iid: str):
    inc = store().get_incident(iid)
    if not inc:
        _404(iid)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["incident_id", "sample_id", "code", "role", "lat", "lon", "status",
                "question", "analytes"])
    for s in inc["samples"]:
        w.writerow([iid, s["id"], s["code"], s["role"], f"{s['lat']:.6f}",
                    f"{s['lon']:.6f}", s["status"], s.get("question") or "",
                    "; ".join(s.get("analytes") or [])])
    return Response(buf.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{iid}_samples.csv"'})


@router.get("/incidents/{iid}/samples.geojson", tags=["field"])
def samples_geojson(iid: str):
    inc = store().get_incident(iid)
    if not inc:
        _404(iid)
    return {"type": "FeatureCollection", "properties": {"incident_id": iid},
            "features": [{"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                          "properties": {k: s[k] for k in ("id", "code", "role", "status",
                                                           "question")}}
                         for s in inc["samples"]]}


@router.get("/measurements/parameters", tags=["field"])
def measurement_parameters():
    return {"parameters": MEASUREMENT_PARAMETERS}


@router.post("/incidents/{iid}/measurements", tags=["field"])
def add_measurement(iid: str, body: MeasurementIn):
    try:
        return store().add_measurement(iid, body.parameter, body.value, body.unit,
                                       body.actor, body.sample_id, body.method,
                                       body.measured_at, body.lab, body.qc_flag)
    except KeyError as e:
        _404(e)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/incidents/{iid}/measurements/csv", tags=["field"])
def add_measurement_csv(iid: str, body: CsvIn):
    try:
        return store().import_lab_csv(iid, body.csv, body.actor)
    except KeyError as e:
        _404(e)


# --------------------------------------------------------------------------- #
# LEARN
# --------------------------------------------------------------------------- #
@router.get("/labels/summary", tags=["learn"])
def labels_summary():
    return {"summary": store().label_summary()}


@router.get("/labels", tags=["learn"])
def labels(task: str = "triage", split: str | None = None):
    return {"labels": store().labels(task, split)}


@router.post("/training/retrain", tags=["learn"])
def retrain(body: RetrainIn):
    return trainer.run_training_job(store(), body.task, body.requested_by)


@router.get("/training/jobs", tags=["learn"])
def jobs():
    return {"jobs": store().list_jobs()}


@router.get("/training/jobs/{jid}", tags=["learn"])
def job(jid: str):
    j = store().get_job(jid)
    if not j:
        _404(jid)
    return j


@router.get("/models", tags=["learn"])
def models(task: str | None = None):
    return {"models": store().list_models(task)}


@router.get("/models/{mid}", tags=["learn"])
def model(mid: str):
    m = store().get_model(mid)
    if not m:
        _404(mid)
    return m


@router.get("/models/{mid}/compare", tags=["learn"])
def compare(mid: str):
    try:
        return trainer.compare(store(), mid)
    except KeyError as e:
        _404(e)


@router.post("/models/{mid}/promote", tags=["learn"])
def promote(mid: str, body: PromoteIn):
    try:
        return trainer.promote(store(), mid, body.approved_by, body.note)
    except KeyError as e:
        _404(e)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/models/{mid}/reject", tags=["learn"])
def reject(mid: str, body: ActorNoteIn):
    try:
        return trainer.reject(store(), mid, body.actor, body.note)
    except KeyError as e:
        _404(e)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/models/{mid}/rollback", tags=["learn"])
def rollback(mid: str, body: ActorNoteIn):
    try:
        return trainer.rollback(store(), mid, body.actor, body.note)
    except KeyError as e:
        _404(e)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


# --------------------------------------------------------------------------- #
# Audit, alerts, AOIs
# --------------------------------------------------------------------------- #
@router.get("/audit", tags=["audit"])
def audit(entity_type: str | None = None, entity_id: str | None = None,
          limit: int = Query(200, le=1000)):
    return {"events": store().audit_log(entity_type, entity_id, limit)}


@router.get("/audit/verify", tags=["audit"])
def audit_verify():
    return store().verify_audit_chain()


@router.get("/alerts", tags=["alerts"])
def alerts(unacknowledged_only: bool = False):
    return {"alerts": store().list_alerts(unacknowledged_only)}


@router.post("/alerts/{aid}/ack", tags=["alerts"])
def ack(aid: str, body: ActorNoteIn):
    store().ack_alert(aid, body.actor)
    return {"ok": True}


@router.get("/aois", tags=["watch"])
def aois():
    return {"aois": store().list_aois()}


@router.get("/watch/{aoi_id}", tags=["watch"])
def watch_series(aoi_id: str):
    if "/" in aoi_id or ".." in aoi_id:
        raise HTTPException(400, "invalid id")
    p = os.path.join(ROOT, "outputs", "watch", f"{aoi_id}.json")
    if not os.path.exists(p):
        _404(aoi_id)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@router.get("/incidents/{iid}/report", tags=["incidents"], response_class=PlainTextResponse)
def report(iid: str):
    """Markdown incident report with the full evidence chain and audit trail."""
    from pipeline.report import incident_report_md
    inc = store().get_incident(iid)
    if not inc:
        _404(iid)
    inc["audit_trail"] = store().audit_log("incident", iid, limit=500)
    return Response(incident_report_md(inc), media_type="text/markdown", headers={
        "Content-Disposition": f'attachment; filename="{iid}_report.md"'})
