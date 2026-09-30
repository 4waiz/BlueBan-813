"""HTTP contracts of the closed-loop API (FastAPI TestClient, temp SQLite)."""
import importlib

import pytest
from fastapi.testclient import TestClient

from test_closed_loop import _seed_labels, payload


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.sqlite'}")
    from services.api import loop
    loop.store.cache_clear()
    main = importlib.import_module("services.api.main")
    c = TestClient(main.app)
    loop.store().upsert_incident(payload())
    yield c
    loop.store.cache_clear()


IID = "BB-UAE-2026-901"


def test_incident_list_and_detail_contract(client):
    r = client.get("/api/incidents").json()
    assert {"incidents", "states", "decisions", "event_types"} <= set(r)
    d = client.get(f"/api/incidents/{IID}").json()
    for k in ("id", "status", "reviews", "samples", "measurements", "predictions",
              "recommendation", "audit_trail", "field_validation"):
        assert k in d
    assert client.get("/api/incidents/NOPE").status_code == 404


def test_review_endpoint_persists_and_validates(client):
    bad = client.post(f"/api/incidents/{IID}/review",
                      json={"reviewer": "a", "decision": "LAUNCH_MISSILES"})
    assert bad.status_code == 422
    r = client.post(f"/api/incidents/{IID}/review",
                    json={"reviewer": "analyst.a", "decision": "NEEDS_FIELD_SAMPLE",
                          "note": "need chl-a", "evidence_viewed": ["temporal"]})
    assert r.status_code == 200 and r.json()["status_after"] == "FIELD_VALIDATION_REQUIRED"
    again = client.post(f"/api/incidents/{IID}/review",
                        json={"reviewer": "analyst.a", "decision": "INSUFFICIENT_EVIDENCE"})
    assert again.status_code == 409          # not allowed from FIELD_VALIDATION_REQUIRED


def test_field_endpoints_export_valid_csv_and_geojson(client):
    pts = {"actor": "analyst.a", "points": [
        {"code": "S01", "role": "CORE", "lon": 56.45, "lat": 25.15},
        {"code": "S02", "role": "BACKGROUND", "lon": 56.56, "lat": 25.22}]}
    assert client.put(f"/api/incidents/{IID}/samples", json=pts).status_code == 200
    csv_text = client.get(f"/api/incidents/{IID}/samples.csv").text
    assert csv_text.splitlines()[0].startswith("incident_id,sample_id,code,role,lat,lon")
    assert len(csv_text.strip().splitlines()) == 3
    gj = client.get(f"/api/incidents/{IID}/samples.geojson").json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == 2
    for f in gj["features"]:
        lon, lat = f["geometry"]["coordinates"]
        assert -180 <= lon <= 180 and -90 <= lat <= 90
    moved = client.patch(f"/api/samples/{IID}-S01",
                         json={"actor": "field.team", "lon": 56.451, "status": "COLLECTED"})
    assert moved.status_code == 200 and moved.json()["collected_by"] == "field.team"
    m = client.post(f"/api/incidents/{IID}/measurements",
                    json={"actor": "lab.x", "parameter": "turbidity", "value": 4.1,
                          "unit": "NTU", "sample_id": f"{IID}-S01"})
    assert m.status_code == 200
    wrong = client.post(f"/api/incidents/{IID}/measurements",
                        json={"actor": "lab.x", "parameter": "turbidity", "value": 4.1,
                              "unit": "mg/L"})
    assert wrong.status_code == 422
    up = client.post(f"/api/incidents/{IID}/measurements/csv",
                     json={"actor": "lab.x",
                           "csv": "parameter,value,unit,sample_code\nsalinity,40.1,PSU,S02\n"})
    assert up.json()["imported"] == 1


def test_training_and_promotion_contract(client):
    from services.api import loop
    _seed_labels(loop.store())
    job = client.post("/api/training/retrain",
                      json={"task": "triage", "requested_by": "analyst.a"}).json()
    assert job["status"] == "SUCCEEDED", job
    mid = job["candidate_model_id"]
    assert client.get("/api/training/jobs").json()["jobs"][0]["id"] == job["id"]
    cmp_ = client.get(f"/api/models/{mid}/compare").json()
    assert cmp_["candidate"]["id"] == mid and cmp_["production"] is None
    assert client.post(f"/api/models/{mid}/promote",
                       json={"approved_by": "system"}).status_code == 403
    ok = client.post(f"/api/models/{mid}/promote", json={"approved_by": "supervisor.b"})
    assert ok.status_code == 200 and ok.json()["status"] == "PRODUCTION"
    assert client.get("/api/audit/verify").json()["ok"] is True


def test_report_export_contains_the_evidence_chain(client):
    client.post(f"/api/incidents/{IID}/review",
                json={"reviewer": "analyst.a", "decision": "CONFIRM"})
    md = client.get(f"/api/incidents/{IID}/report").text
    assert md.startswith(f"# Incident report {IID}")
    assert "Operator reviews" in md and "Audit trail" in md
    assert "does not identify a species" in md


def test_new_operational_incident_raises_one_factual_alert(client):
    alerts = client.get("/api/alerts").json()["alerts"]
    mine = [a for a in alerts if a["incident_id"] == IID]
    assert len(mine) == 1
    msg = mine[0]["message"]
    assert msg.startswith("New coastal anomaly detected near") and "Analyst review required." in msg
    assert "toxic" not in msg.lower() and "confirmed" not in msg.lower()
    from services.api import loop
    loop.store().upsert_incident(payload())               # re-ingesting the same incident
    assert len([a for a in client.get("/api/alerts").json()["alerts"] if a["incident_id"] == IID]) == 1


def test_alert_webhook_is_posted_only_when_configured(client, monkeypatch):
    from services.api import store as st_mod
    sent = []
    monkeypatch.setattr(st_mod, "_post_webhook", lambda a: sent.append(a))
    from services.api import loop
    loop.store().add_alert("LOW", "test", incident_id=IID)
    assert sent and sent[-1]["message"] == "test"
    monkeypatch.undo()
    monkeypatch.delenv("BLUEBAN_ALERT_WEBHOOK", raising=False)
    st_mod._post_webhook({"id": "x"})                      # no URL configured: silently nothing


def test_assets_and_aois_endpoints_match_the_web_engine(client):
    r = client.post("/api/assets", json={"actor": "analyst.a", "name": "Intake F2", "type": "DESALINATION_PLANT",
                                         "lon": 56.35, "lat": 25.2})
    assert r.status_code == 200 and r.json()["source"] == "operator"
    assert any(a["name"] == "Intake F2" for a in client.get("/api/assets").json()["assets"])
    assert client.post("/api/assets", json={"actor": "a", "name": " ", "type": "PORT", "lon": 1, "lat": 1}).status_code == 422
    a = client.post("/api/aois", json={"actor": "analyst.a", "name": "Test AOI", "bbox": [56.3, 25.0, 56.5, 25.2]})
    assert a.status_code == 200 and a.json()["bbox"] == [56.3, 25.0, 56.5, 25.2]
    assert client.post("/api/aois", json={"actor": "a", "name": "bad", "bbox": [56.5, 25.0, 56.3, 25.2]}).status_code == 422
    kinds = {e["action"] for e in client.get("/api/audit").json()["events"]}
    assert {"asset.create", "aoi.upsert"} <= kinds
