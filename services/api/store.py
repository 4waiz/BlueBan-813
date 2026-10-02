"""Operational persistence for BLUEBAN 813.

SQLite by default (``data/blueban.sqlite``); ``DATABASE_URL=sqlite:///path``
selects another file. The schema (``services/db/schema.sql``) is shared with the
Cloudflare D1 deployment, which is also SQLite. A PostgreSQL adapter is a
planned extension; the schema avoids SQLite-only types apart from
``AUTOINCREMENT`` so the port is mechanical.

Every mutating method writes an audit event. Audit events are hash-chained:
``hash = sha256(prev_hash + canonical_json(event))``, so editing or deleting an
audit row after the fact is detectable with :meth:`Store.verify_audit_chain`.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager

from pipeline import incidents as inc_mod

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA = os.path.join(ROOT, "services", "db", "schema.sql")
GENESIS = "0" * 64

MEASUREMENT_PARAMETERS = {
    # parameter: accepted units (first is canonical)
    "chlorophyll_a": ["mg m-3", "ug/L", "mg/m3"],
    "turbidity": ["NTU", "FNU"],
    "tss": ["mg/L", "g m-3"],
    "temperature": ["degC"],
    "salinity": ["PSU", "g/kg"],
    "conductivity": ["mS/cm"],
    "ph": ["pH"],
    "dissolved_oxygen": ["mg/L"],
    "nitrate": ["umol/L", "mg/L"],
    "phosphate": ["umol/L", "mg/L"],
    "secchi_depth": ["m"],
    "water_depth": ["m"],
    "hydrocarbon_indicator": ["qualitative"],
    "phytoplankton_id": ["qualitative"],
}


def _db_path(url: str | None) -> str:
    url = url or os.environ.get("DATABASE_URL") or ""
    if not url:
        return os.path.join(ROOT, "data", "blueban.sqlite")
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    if url == "sqlite://:memory:" or url == ":memory:":
        return ":memory:"
    raise NotImplementedError(
        f"DATABASE_URL {url.split(':')[0]}:// is not supported yet; use sqlite:///path. "
        "The schema is portable (see services/db/schema.sql).")


def _canon(d) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)


def _post_webhook(alert: dict) -> None:
    """POST an alert to BLUEBAN_ALERT_WEBHOOK, if configured.

    Delivery (email, chat, pager) stays outside the product: the webhook gets
    the alert JSON and does what the operator's organisation needs. It runs in
    a daemon thread with a short timeout and never raises into the request.
    """
    url = os.environ.get("BLUEBAN_ALERT_WEBHOOK", "").strip()
    if not url.startswith(("https://", "http://")):
        return
    import threading
    import urllib.request

    def send():
        try:
            req = urllib.request.Request(url, data=json.dumps(alert).encode(), method="POST",
                                         headers={"content-type": "application/json",
                                                  "user-agent": "BLUEBAN-813-alerts"})
            urllib.request.urlopen(req, timeout=5).close()
        except Exception as e:                                     # logged, never fatal
            print(f"[alerts] webhook delivery failed: {e!r}")

    threading.Thread(target=send, daemon=True).start()


class Store:
    def __init__(self, url: str | None = None):
        self.path = _db_path(url)
        self._lock = threading.RLock()
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._mem = sqlite3.connect(":memory:", check_same_thread=False) \
            if self.path == ":memory:" else None
        self.init_schema()

    # ------------------------------------------------------------------ infra
    @contextmanager
    def conn(self):
        with self._lock:
            c = self._mem or sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise
            finally:
                if self._mem is None:
                    c.close()

    def init_schema(self):
        with self.conn() as c:
            if self._mem is None:
                c.execute("PRAGMA journal_mode=WAL")
            c.executescript(open(SCHEMA, encoding="utf-8").read())

    def _audit(self, c, actor, action, entity_type, entity_id, detail=None):
        row = c.execute("SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        ev = {"at": inc_mod.now_utc(), "actor": actor, "action": action,
              "entity_type": entity_type, "entity_id": entity_id,
              "detail": detail or {}}
        h = hashlib.sha256((prev + _canon(ev)).encode()).hexdigest()
        c.execute("INSERT INTO audit_events(at,actor,action,entity_type,entity_id,detail,"
                  "prev_hash,hash) VALUES (?,?,?,?,?,?,?,?)",
                  (ev["at"], actor, action, entity_type, entity_id, _canon(ev["detail"]),
                   prev, h))
        return h

    def verify_audit_chain(self) -> dict:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM audit_events ORDER BY seq").fetchall()
        prev = GENESIS
        for r in rows:
            ev = {"at": r["at"], "actor": r["actor"], "action": r["action"],
                  "entity_type": r["entity_type"], "entity_id": r["entity_id"],
                  "detail": json.loads(r["detail"] or "{}")}
            h = hashlib.sha256((prev + _canon(ev)).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != h:
                return {"ok": False, "first_bad_seq": r["seq"], "n": len(rows)}
            prev = h
        return {"ok": True, "n": len(rows), "head": prev}

    def audit_log(self, entity_type=None, entity_id=None, limit=200) -> list:
        q, a = "SELECT * FROM audit_events", []
        cond = []
        if entity_type:
            cond.append("entity_type=?")
            a.append(entity_type)
        if entity_id:
            cond.append("entity_id=?")
            a.append(entity_id)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY seq DESC LIMIT ?"
        a.append(limit)
        with self.conn() as c:
            return [dict(r) | {"detail": json.loads(r["detail"] or "{}")}
                    for r in c.execute(q, a).fetchall()]

    def meta_get(self, key, default=None):
        with self.conn() as c:
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def meta_set(self, key, value):
        with self.conn() as c:
            c.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) "
                      "DO UPDATE SET value=excluded.value", (key, _canon(value)))

    # ------------------------------------------------------------------- AOIs
    def upsert_aoi(self, aoi: dict, actor="system"):
        with self.conn() as c:
            c.execute(
                "INSERT INTO aois(id,name,emirate,coast,bbox,optical_regime,status,created_at,"
                "created_by) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, emirate=excluded.emirate, coast=excluded.coast, "
                "bbox=excluded.bbox, optical_regime=excluded.optical_regime",
                (aoi["id"], aoi["name"], aoi.get("emirate"), aoi.get("coast"),
                 _canon(aoi["bbox"]), aoi.get("optical_regime"),
                 aoi.get("status", "MONITORING"), inc_mod.now_utc(), actor))
            self._audit(c, actor, "aoi.upsert", "aoi", aoi["id"], {"bbox": aoi["bbox"]})

    def list_aois(self) -> list:
        with self.conn() as c:
            return [dict(r) | {"bbox": json.loads(r["bbox"])}
                    for r in c.execute("SELECT * FROM aois ORDER BY id").fetchall()]

    # -------------------------------------------------------------- assets
    def list_assets(self) -> list:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM assets ORDER BY type, name").fetchall()]

    def add_asset(self, a: dict, actor: str) -> dict:
        if not (a.get("name") or "").strip():
            raise ValueError("asset name is required")
        if not (-180 <= float(a["lon"]) <= 180 and -90 <= float(a["lat"]) <= 90):
            raise ValueError("lon/lat out of range")
        aid = a.get("id") or f"OP-{uuid.uuid4().hex[:6].upper()}"
        with self.conn() as c:
            c.execute("INSERT INTO assets(id,name,type,lon,lat,aoi_id,sensitivity,source,notes,"
                      "created_at,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                      "name=excluded.name, type=excluded.type, lon=excluded.lon, lat=excluded.lat",
                      (aid, a["name"].strip(), a.get("type", "OTHER"), float(a["lon"]), float(a["lat"]),
                       a.get("aoi_id"), a.get("sensitivity"), a.get("source", "operator"), a.get("notes"),
                       inc_mod.now_utc(), actor))
            self._audit(c, actor, "asset.create", "asset", aid,
                        {"name": a["name"], "type": a.get("type"), "lon": a["lon"], "lat": a["lat"]})
            return dict(c.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone())

    # -------------------------------------------------------------- incidents
    def upsert_incident(self, payload: dict, actor="pipeline") -> dict:
        problems = inc_mod.validate_payload(payload)
        if problems:
            raise ValueError("invalid incident payload: " + "; ".join(problems))
        now = inc_mod.now_utc()
        g = payload.get("geometry")
        with self.conn() as c:
            existed = c.execute("SELECT id FROM incidents WHERE id=?",
                                (payload["id"],)).fetchone()
            c.execute(
                "INSERT INTO incidents(id,aoi_id,status,detected_at,observation_time,"
                "event_type_hypothesis,severity,confidence,priority,model_id,geometry,"
                "centroid_lon,centroid_lat,area_km2,role,disposition,payload,created_at,"
                "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, "
                "updated_at=excluded.updated_at, geometry=excluded.geometry, "
                "area_km2=excluded.area_km2",
                (payload["id"], payload["aoi_id"], payload["status"],
                 payload["detected_at"], payload["observation_time"],
                 payload["event_type_hypothesis"], payload.get("severity"),
                 payload.get("confidence"), payload.get("priority"),
                 payload.get("model_id"), _canon(g) if g else None,
                 payload.get("centroid", [None, None])[0],
                 payload.get("centroid", [None, None])[1], payload.get("area_km2"),
                 payload.get("role", "operational"), payload.get("disposition"),
                 _canon(payload), now, now))
            if not existed:
                c.execute("INSERT INTO predictions(incident_id,model_id,created_at,output) "
                          "VALUES (?,?,?,?)",
                          (payload["id"], payload.get("model_id") or "unknown", now,
                           _canon({"event_type_hypothesis": payload["event_type_hypothesis"],
                                   "severity": payload.get("severity"),
                                   "confidence": payload.get("confidence"),
                                   "priority": payload.get("priority")})))
            self._audit(c, actor, "incident.upsert" if existed else "incident.create",
                        "incident", payload["id"],
                        {"status": payload["status"], "model_id": payload.get("model_id")})
        if (not existed and payload.get("role", "operational") == "operational"
                and payload["status"] in inc_mod.OPEN_STATES):
            level = {"HIGH": "HIGH", "MEDIUM": "MEDIUM"}.get(str(payload.get("priority") or "").upper(), "LOW")
            self.add_alert(level, inc_mod.alert_message(payload), actor=actor,
                           incident_id=payload["id"], aoi_id=payload["aoi_id"])
        return self.get_incident(payload["id"])

    def list_incidents(self, status: str | None = None, include_controls=True) -> list:
        q = ("SELECT id,aoi_id,status,detected_at,observation_time,event_type_hypothesis,"
             "severity,confidence,priority,model_id,centroid_lon,centroid_lat,area_km2,role,"
             "disposition,updated_at FROM incidents")
        cond, a = [], []
        if status:
            cond.append("status=?")
            a.append(status)
        if not include_controls:
            cond.append("role='operational'")
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY observation_time DESC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(q, a).fetchall()]

    def get_incident(self, iid: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
            if not r:
                return None
            p = json.loads(r["payload"])
            p["status"] = r["status"]
            p["event_type_hypothesis"] = r["event_type_hypothesis"]
            p["disposition"] = r["disposition"]
            p["updated_at"] = r["updated_at"]
            p["reviews"] = [dict(x) | {"evidence_viewed": json.loads(x["evidence_viewed"] or "[]")}
                            for x in c.execute("SELECT * FROM reviews WHERE incident_id=? "
                                               "ORDER BY created_at", (iid,)).fetchall()]
            p["samples"] = [dict(x) | {"analytes": json.loads(x["analytes"] or "[]")}
                            for x in c.execute("SELECT * FROM samples WHERE incident_id=? "
                                               "AND status!='REMOVED' ORDER BY code",
                                               (iid,)).fetchall()]
            p["measurements"] = [dict(x) for x in c.execute(
                "SELECT * FROM measurements WHERE incident_id=? ORDER BY entered_at",
                (iid,)).fetchall()]
            p["predictions"] = [dict(x) | {"output": json.loads(x["output"])}
                                for x in c.execute("SELECT * FROM predictions WHERE "
                                                   "incident_id=? ORDER BY id",
                                                   (iid,)).fetchall()]
        p["field_validation"] = dict(p.get("field_validation") or {})
        p["field_validation"]["measurements"] = p["measurements"]
        p["recommendation"] = inc_mod.recommend(p).to_dict()
        return p

    def _set_status(self, c, iid, status, disposition=None, hypothesis=None):
        sets, a = ["status=?", "updated_at=?"], [status, inc_mod.now_utc()]
        if disposition is not None:
            sets.append("disposition=?")
            a.append(disposition)
        if hypothesis is not None:
            sets.append("event_type_hypothesis=?")
            a.append(hypothesis)
        a.append(iid)
        c.execute(f"UPDATE incidents SET {', '.join(sets)} WHERE id=?", a)

    def transition(self, iid: str, to: str, actor: str, reason: str = "") -> dict:
        with self.conn() as c:
            r = c.execute("SELECT status FROM incidents WHERE id=?", (iid,)).fetchone()
            if not r:
                raise KeyError(iid)
            new = inc_mod.admin_transition(r["status"], to)
            self._set_status(c, iid, new)
            self._audit(c, actor, "incident.transition", "incident", iid,
                        {"from": r["status"], "to": new, "reason": reason})
        return self.get_incident(iid)

    # ----------------------------------------------------------------- review
    def add_review(self, iid: str, reviewer: str, decision: str,
                   new_hypothesis: str | None = None, note: str = "",
                   evidence_viewed: list | None = None) -> dict:
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer is required")
        if new_hypothesis and new_hypothesis not in inc_mod.EVENT_TYPES:
            raise ValueError(f"unknown event type {new_hypothesis!r}")
        if decision == "RECLASSIFY" and not new_hypothesis:
            raise ValueError("RECLASSIFY requires new_hypothesis")
        now = inc_mod.now_utc()
        with self.conn() as c:
            r = c.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
            if not r:
                raise KeyError(iid)
            before = r["status"]
            after = inc_mod.review_transition(before, decision)
            has_field = c.execute("SELECT COUNT(*) n FROM measurements WHERE incident_id=?",
                                  (iid,)).fetchone()["n"] > 0
            basis = "field" if has_field else "analyst"
            rid = f"RV-{uuid.uuid4().hex[:10]}"
            c.execute("INSERT INTO reviews(id,incident_id,reviewer,created_at,model_id,"
                      "previous_hypothesis,decision,new_hypothesis,note,evidence_viewed,"
                      "status_before,status_after) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (rid, iid, reviewer.strip(), now, r["model_id"],
                       r["event_type_hypothesis"], decision, new_hypothesis, note,
                       _canon(evidence_viewed or []), before, after))
            disposition = None
            if after == "CONFIRMED":
                disposition = (f"Confirmed by "
                               f"{'field evidence' if basis == 'field' else 'an analyst'}"
                               f": the unusual water is real. The substance or species is not confirmed"
                               + ("." if basis == "field" else " without a water sample."))
            elif after == "FALSE_POSITIVE":
                disposition = f"False alarm ({basis} review)"
            self._set_status(c, iid, after, disposition,
                             new_hypothesis if new_hypothesis else None)
            self._audit(c, reviewer, f"review.{decision.lower()}", "incident", iid,
                        {"review_id": rid, "from": before, "to": after,
                         "model_id": r["model_id"], "new_hypothesis": new_hypothesis,
                         "basis": basis})
            lab = inc_mod.label_from_review(decision, r["event_type_hypothesis"],
                                            new_hypothesis, basis)
            label_id = None
            if lab is not None and lab.get("y") is not None:
                payload = json.loads(r["payload"])
                feats = payload.get("model_features") or {}
                label_id = self._insert_label(
                    c, task="triage", incident_id=iid, aoi_id=r["aoi_id"],
                    target=lab, features=feats,
                    source="field_measurement" if basis == "field" else "analyst_review",
                    source_ref=rid, group_key=f"{r['aoi_id']}|{r['observation_time'][:7]}",
                    actor=reviewer)
        return {"review_id": rid, "status_before": before, "status_after": after,
                "label_id": label_id, "incident": self.get_incident(iid)}

    # ----------------------------------------------------------------- labels
    def _insert_label(self, c, task, incident_id, aoi_id, target, features, source,
                      source_ref, group_key, actor, split="train"):
        lid = f"LB-{uuid.uuid4().hex[:10]}"
        # A newer label from the same incident supersedes older ones for that task.
        prev = c.execute("SELECT id FROM labels WHERE task=? AND incident_id=? AND "
                         "superseded_by IS NULL", (task, incident_id)).fetchall() \
            if incident_id else []
        c.execute("INSERT INTO labels(id,task,incident_id,aoi_id,target,features,source,"
                  "source_ref,weight,split,group_key,created_at,created_by) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (lid, task, incident_id, aoi_id, _canon(target), _canon(features),
                   source, source_ref, inc_mod.LABEL_WEIGHTS.get(source, 1.0), split,
                   group_key, inc_mod.now_utc(), actor))
        for p in prev:
            c.execute("UPDATE labels SET superseded_by=? WHERE id=?", (lid, p["id"]))
        self._audit(c, actor, "label.create", "label", lid,
                    {"task": task, "incident_id": incident_id, "source": source,
                     "target": target, "split": split})
        return lid

    def add_label(self, task, target, features, source, actor, incident_id=None,
                  aoi_id=None, source_ref=None, group_key=None, split="train") -> str:
        with self.conn() as c:
            return self._insert_label(c, task, incident_id, aoi_id, target, features,
                                      source, source_ref, group_key, actor, split)

    def labels(self, task: str, split: str | None = None, active_only=True) -> list:
        q, a = "SELECT * FROM labels WHERE task=?", [task]
        if split:
            q += " AND split=?"
            a.append(split)
        if active_only:
            q += " AND superseded_by IS NULL"
        q += " ORDER BY created_at"
        with self.conn() as c:
            return [dict(r) | {"target": json.loads(r["target"]),
                               "features": json.loads(r["features"])}
                    for r in c.execute(q, a).fetchall()]

    def label_summary(self) -> dict:
        with self.conn() as c:
            rows = c.execute("SELECT task, source, split, COUNT(*) n FROM labels WHERE "
                             "superseded_by IS NULL GROUP BY task, source, split").fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- samples
    def replace_sample_plan(self, iid: str, points: list, actor: str) -> list:
        now = inc_mod.now_utc()
        with self.conn() as c:
            if not c.execute("SELECT 1 FROM incidents WHERE id=?", (iid,)).fetchone():
                raise KeyError(iid)
            c.execute("UPDATE samples SET status='REMOVED', updated_at=? WHERE incident_id=? "
                      "AND status='PLANNED'", (now, iid))
            for i, p in enumerate(points, 1):
                code = p.get("code") or f"S{i:02d}"
                sid = f"{iid}-{code}"
                c.execute(
                    "INSERT INTO samples(id,incident_id,code,role,lon,lat,status,question,"
                    "analytes,rationale,planned_by,planned_at,updated_at) VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "lon=excluded.lon, lat=excluded.lat, role=excluded.role, "
                    "status=CASE WHEN samples.status='REMOVED' THEN 'PLANNED' "
                    "ELSE samples.status END, updated_at=excluded.updated_at",
                    (sid, iid, code, p["role"], float(p["lon"]), float(p["lat"]),
                     p.get("status", "PLANNED"), p.get("question"),
                     _canon(p.get("analytes", [])), p.get("rationale"), actor, now, now))
            self._audit(c, actor, "samples.plan", "incident", iid,
                        {"n": len(points), "codes": [p.get("code") for p in points]})
        return self.get_incident(iid)["samples"]

    def update_sample(self, sid: str, patch: dict, actor: str) -> dict:
        allowed = {"lon", "lat", "status", "role"}
        bad = set(patch) - allowed
        if bad:
            raise ValueError(f"cannot update {sorted(bad)}")
        if "status" in patch and patch["status"] not in (
                "PLANNED", "COLLECTED", "LAB_PENDING", "RESULT_RECEIVED", "REMOVED"):
            raise ValueError(f"invalid sample status {patch['status']!r}")
        now = inc_mod.now_utc()
        with self.conn() as c:
            r = c.execute("SELECT * FROM samples WHERE id=?", (sid,)).fetchone()
            if not r:
                raise KeyError(sid)
            sets, a = ["updated_at=?"], [now]
            for k, v in patch.items():
                sets.append(f"{k}=?")
                a.append(v)
            if patch.get("status") == "COLLECTED":
                sets += ["collected_by=?", "collected_at=?"]
                a += [actor, now]
            a.append(sid)
            c.execute(f"UPDATE samples SET {', '.join(sets)} WHERE id=?", a)
            self._audit(c, actor, "sample.update", "sample", sid,
                        {"patch": patch, "incident_id": r["incident_id"]})
            out = dict(c.execute("SELECT * FROM samples WHERE id=?", (sid,)).fetchone())
        return out

    # ----------------------------------------------------------- measurements
    def add_measurement(self, iid: str, parameter: str, value, unit: str, actor: str,
                        sample_id: str | None = None, method: str | None = None,
                        measured_at: str | None = None, lab: str | None = None,
                        qc_flag: str = "UNCHECKED", source: str = "manual",
                        raw: dict | None = None) -> dict:
        if parameter not in MEASUREMENT_PARAMETERS:
            raise ValueError(f"unsupported parameter {parameter!r}")
        if unit not in MEASUREMENT_PARAMETERS[parameter]:
            raise ValueError(f"unit {unit!r} not accepted for {parameter} "
                             f"(use one of {MEASUREMENT_PARAMETERS[parameter]})")
        v = float(value)
        if v != v:
            raise ValueError("value is NaN")
        if parameter not in ("temperature",) and v < 0:
            raise ValueError(f"{parameter} cannot be negative")
        now = inc_mod.now_utc()
        mid = f"MS-{uuid.uuid4().hex[:10]}"
        with self.conn() as c:
            r = c.execute("SELECT status FROM incidents WHERE id=?", (iid,)).fetchone()
            if not r:
                raise KeyError(iid)
            if sample_id and not c.execute("SELECT 1 FROM samples WHERE id=? AND incident_id=?",
                                           (sample_id, iid)).fetchone():
                raise KeyError(sample_id)
            c.execute("INSERT INTO measurements(id,incident_id,sample_id,parameter,value,unit,"
                      "method,measured_at,lab,qc_flag,source,entered_by,entered_at,raw) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (mid, iid, sample_id, parameter, v, unit, method, measured_at, lab,
                       qc_flag, source, actor, now, _canon(raw or {})))
            if sample_id:
                c.execute("UPDATE samples SET status='RESULT_RECEIVED', updated_at=? "
                          "WHERE id=?", (now, sample_id))
            if r["status"] == "FIELD_VALIDATION_REQUIRED":
                self._set_status(c, iid, "UNDER_REVIEW")
                self._audit(c, actor, "incident.transition", "incident", iid,
                            {"from": "FIELD_VALIDATION_REQUIRED", "to": "UNDER_REVIEW",
                             "reason": "field result received"})
            self._audit(c, actor, "measurement.create", "measurement", mid,
                        {"incident_id": iid, "sample_id": sample_id,
                         "parameter": parameter, "value": v, "unit": unit,
                         "source": source})
        return {"id": mid, "incident_id": iid, "sample_id": sample_id,
                "parameter": parameter, "value": v, "unit": unit}

    def import_lab_csv(self, iid: str, text: str, actor: str) -> dict:
        """Import a laboratory CSV.

        Required columns: ``parameter,value,unit``. Optional: ``sample_code``
        (S01...), ``method``, ``measured_at``, ``lab``, ``qc_flag``. Rows that fail
        validation are returned with their reason, never silently dropped.
        """
        rows = list(csv.DictReader(io.StringIO(text)))
        ok, bad = [], []
        for i, row in enumerate(rows, 2):
            try:
                code = (row.get("sample_code") or "").strip()
                sid = f"{iid}-{code}" if code else None
                ok.append(self.add_measurement(
                    iid, row["parameter"].strip(), row["value"], row["unit"].strip(),
                    actor, sample_id=sid, method=row.get("method"),
                    measured_at=row.get("measured_at"), lab=row.get("lab"),
                    qc_flag=(row.get("qc_flag") or "UNCHECKED").strip(),
                    source="lab_csv", raw=row))
            except (KeyError, ValueError) as e:
                bad.append({"line": i, "row": row, "error": str(e)})
        return {"imported": len(ok), "rejected": bad, "measurements": ok}

    # ----------------------------------------------------------------- models
    def add_model(self, m: dict, metrics: list | None = None, actor="system") -> dict:
        with self.conn() as c:
            c.execute("INSERT INTO models(id,task,version,model_type,created_at,"
                      "training_dataset_version,validation_dataset_hash,feature_set,params,"
                      "artifact,status,parent_model,notes,gate) VALUES "
                      "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (m["id"], m["task"], m["version"], m["model_type"],
                       m.get("created_at") or inc_mod.now_utc(),
                       m.get("training_dataset_version"), m.get("validation_dataset_hash"),
                       _canon(m.get("feature_set", [])), _canon(m.get("params", {})),
                       _canon(m.get("artifact", {})), m.get("status", "CANDIDATE"),
                       m.get("parent_model"), m.get("notes"), _canon(m.get("gate") or {})))
            for mt in metrics or []:
                c.execute("INSERT INTO model_metrics(model_id,split,subgroup,metric,value,"
                          "ci_low,ci_high,n) VALUES (?,?,?,?,?,?,?,?)",
                          (m["id"], mt.get("split", "validation"), mt.get("subgroup", "all"),
                           mt["metric"], mt.get("value"), mt.get("ci_low"),
                           mt.get("ci_high"), mt.get("n")))
            self._audit(c, actor, "model.register", "model", m["id"],
                        {"task": m["task"], "status": m.get("status", "CANDIDATE"),
                         "parent": m.get("parent_model")})
        return self.get_model(m["id"])

    def get_model(self, mid: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM models WHERE id=?", (mid,)).fetchone()
            if not r:
                return None
            d = dict(r)
            for k in ("feature_set", "params", "artifact", "gate"):
                d[k] = json.loads(d[k]) if d[k] else None
            d["metrics"] = [dict(x) for x in c.execute(
                "SELECT split,subgroup,metric,value,ci_low,ci_high,n FROM model_metrics "
                "WHERE model_id=? ORDER BY id", (mid,)).fetchall()]
        return d

    def list_models(self, task: str | None = None) -> list:
        q, a = "SELECT id FROM models", []
        if task:
            q += " WHERE task=?"
            a.append(task)
        q += " ORDER BY created_at DESC"
        with self.conn() as c:
            ids = [r["id"] for r in c.execute(q, a).fetchall()]
        return [self.get_model(i) for i in ids]

    def production_model(self, task: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT id FROM models WHERE task=? AND status='PRODUCTION'",
                          (task,)).fetchone()
        return self.get_model(r["id"]) if r else None

    def set_model_status(self, mid: str, status: str, actor: str, gate: dict | None = None,
                         note: str = "") -> dict:
        allowed = ("TRAINING", "CANDIDATE", "REJECTED", "STAGING", "PRODUCTION", "RETIRED")
        if status not in allowed:
            raise ValueError(status)
        now = inc_mod.now_utc()
        with self.conn() as c:
            r = c.execute("SELECT * FROM models WHERE id=?", (mid,)).fetchone()
            if not r:
                raise KeyError(mid)
            retired = None
            if status == "PRODUCTION":
                prev = c.execute("SELECT id FROM models WHERE task=? AND status='PRODUCTION' "
                                 "AND id!=?", (r["task"], mid)).fetchone()
                if prev:
                    retired = prev["id"]
                    c.execute("UPDATE models SET status='RETIRED' WHERE id=?", (retired,))
                c.execute("UPDATE models SET status=?, promoted_by=?, promoted_at=?, gate=? "
                          "WHERE id=?", (status, actor, now, _canon(gate or {}), mid))
            else:
                c.execute("UPDATE models SET status=?, gate=COALESCE(?, gate) WHERE id=?",
                          (status, _canon(gate) if gate else None, mid))
            self._audit(c, actor, f"model.{status.lower()}", "model", mid,
                        {"from": r["status"], "to": status, "retired": retired,
                         "note": note, "gate_passed": (gate or {}).get("passed")})
        return self.get_model(mid)

    # ------------------------------------------------------------------- jobs
    def create_job(self, task: str, actor: str) -> dict:
        jid = f"JOB-{uuid.uuid4().hex[:8]}"
        with self.conn() as c:
            c.execute("INSERT INTO training_jobs(id,task,requested_by,created_at,status,log) "
                      "VALUES (?,?,?,?,?,?)", (jid, task, actor, inc_mod.now_utc(),
                                               "QUEUED", "[]"))
            self._audit(c, actor, "training.request", "training_job", jid, {"task": task})
        return self.get_job(jid)

    def update_job(self, jid: str, actor="trainer", **kw) -> dict:
        cols = {"status", "started_at", "finished_at", "dataset_version", "n_train",
                "n_validation", "candidate_model_id", "log", "error"}
        sets, a = [], []
        for k, v in kw.items():
            if k not in cols:
                raise ValueError(k)
            sets.append(f"{k}=?")
            a.append(_canon(v) if k == "log" else v)
        a.append(jid)
        with self.conn() as c:
            c.execute(f"UPDATE training_jobs SET {', '.join(sets)} WHERE id=?", a)
            if "status" in kw:
                self._audit(c, actor, "training.status", "training_job", jid,
                            {"status": kw["status"],
                             "candidate": kw.get("candidate_model_id")})
        return self.get_job(jid)

    def get_job(self, jid: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM training_jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            return None
        return dict(r) | {"log": json.loads(r["log"] or "[]")}

    def list_jobs(self, limit=50) -> list:
        with self.conn() as c:
            return [dict(r) | {"log": json.loads(r["log"] or "[]")} for r in c.execute(
                "SELECT * FROM training_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()]

    # ----------------------------------------------------------------- alerts
    def add_alert(self, level, message, actor="system", incident_id=None, aoi_id=None):
        aid = f"AL-{uuid.uuid4().hex[:8]}"
        at = inc_mod.now_utc()
        with self.conn() as c:
            c.execute("INSERT INTO alerts(id,incident_id,aoi_id,level,message,created_at) "
                      "VALUES (?,?,?,?,?,?)", (aid, incident_id, aoi_id, level, message, at))
            self._audit(c, actor, "alert.create", "alert", aid,
                        {"incident_id": incident_id, "level": level})
        _post_webhook({"id": aid, "level": level, "message": message, "incident_id": incident_id,
                       "aoi_id": aoi_id, "created_at": at})
        return aid

    def list_alerts(self, unacknowledged_only=False) -> list:
        q = "SELECT * FROM alerts"
        if unacknowledged_only:
            q += " WHERE acknowledged_at IS NULL"
        q += " ORDER BY created_at DESC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(q).fetchall()]

    def ack_alert(self, aid: str, actor: str):
        with self.conn() as c:
            c.execute("UPDATE alerts SET acknowledged_by=?, acknowledged_at=? WHERE id=?",
                      (actor, inc_mod.now_utc(), aid))
            self._audit(c, actor, "alert.ack", "alert", aid, {})
