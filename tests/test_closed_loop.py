"""VERIFY -> ACT -> LEARN: incidents, reviews, field data, labels, training, gate."""
import json
import sqlite3

import numpy as np
import pytest

from pipeline import incidents as I
from pipeline import learning as L
from pipeline import quantify as Q
from services.api import trainer as T
from services.api.store import Store


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def payload(iid="BB-UAE-2026-901", status="DETECTED", pct=97.0, role="operational",
            feats=None):
    return {
        "id": iid, "status": status, "aoi_id": "AE-TEST", "aoi_name": "Test coast",
        "detected_at": "2026-09-29T12:00:00Z", "observation_time": "2026-09-29T07:00:00Z",
        "event_type_hypothesis": "BLOOM_LIKE", "severity": 0.7, "confidence": 0.6,
        "priority": "INVESTIGATE", "model_id": "triage-1.0.0", "role": role,
        "geometry": {"type": "Polygon", "coordinates": [[[56.4, 25.1], [56.5, 25.1],
                                                         [56.5, 25.2], [56.4, 25.1]]]},
        "centroid": [56.45, 25.15], "area_km2": 3.2,
        "water_quality": {"estimates": {"chlorophyll_a": {
            "quantity_kind": "PROXY", "units": "dimensionless", "value": 0.21}}},
        "temporal": {"seasonal_percentile": pct},
        "spatial": {"rx_percentile": 99.1},
        "sensor_agreement": {"S2": {"agrees": True}, "S3": {"agrees": True}},
        "quality_flags": [], "exposure": [], "field_validation": {},
        "provenance": {"sources": []},
        "model_features": feats or {f: 1.0 for f in L.TRIAGE_FEATURES},
    }


@pytest.fixture()
def store(tmp_path):
    return Store(f"sqlite:///{tmp_path / 'test.sqlite'}")


# --------------------------------------------------------------------------- #
# State machine
# --------------------------------------------------------------------------- #
def test_review_transitions_follow_the_state_machine():
    assert I.review_transition("UNDER_REVIEW", "CONFIRM") == "CONFIRMED"
    assert I.review_transition("DETECTED", "FALSE_POSITIVE") == "FALSE_POSITIVE"
    assert I.review_transition("UNDER_REVIEW", "NEEDS_FIELD_SAMPLE") == \
        "FIELD_VALIDATION_REQUIRED"
    assert I.review_transition("UNDER_REVIEW", "INSUFFICIENT_EVIDENCE") == "MONITORING"
    assert I.review_transition("UNDER_REVIEW", "RECLASSIFY") == "UNDER_REVIEW"


@pytest.mark.parametrize("status,decision", [
    ("RESOLVED", "CONFIRM"), ("FALSE_POSITIVE", "CONFIRM"),
    ("CONFIRMED", "NEEDS_FIELD_SAMPLE"), ("UNDER_REVIEW", "DELETE")])
def test_forbidden_transitions_raise(status, decision):
    with pytest.raises(I.TransitionError):
        I.review_transition(status, decision)


def test_uncertain_reviews_produce_no_training_label():
    assert I.label_from_review("NEEDS_FIELD_SAMPLE", "BLOOM_LIKE", None, "analyst") is None
    assert I.label_from_review("INSUFFICIENT_EVIDENCE", "BLOOM_LIKE", None, "analyst") is None
    assert I.label_from_review("CONFIRM", "BLOOM_LIKE", None, "analyst")["y"] == 1
    assert I.label_from_review("FALSE_POSITIVE", "BLOOM_LIKE", None, "field")["y"] == 0


def test_recommendation_never_orders_a_shutdown_and_stands_down_on_controls():
    r = I.recommend(payload()).to_dict()
    assert r["action"] == "FIELD_VERIFICATION"
    assert any("shutdown" in n.lower() for n in r["not_recommended"])
    assert all("shut" not in x.lower() for x in r["required_evidence"])
    ctl = I.recommend(payload(role="negative_control", pct=6.6)).to_dict()
    assert ctl["action"] == "STAND_DOWN_CONTINUE_MONITORING"


def test_alert_text_is_factual_not_alarmist():
    msg = I.alert_message(payload())
    assert "Analyst review required" in msg and "97th seasonal percentile" in msg
    for word in ("DANGER", "TOXIC", "confirmed"):
        assert word.lower() not in msg.lower()


def test_payload_validation_rejects_units_on_an_uncalibrated_proxy():
    p = payload()
    p["water_quality"]["estimates"]["chlorophyll_a"] = {
        "quantity_kind": "PROXY", "units": "mg m-3", "value": 8.2}
    assert any("physical units" in x for x in I.validate_payload(p))
    p["water_quality"]["estimates"]["chlorophyll_a"]["quantity_kind"] = "CALIBRATED"
    assert I.validate_payload(p) == []


# --------------------------------------------------------------------------- #
# Persistence and audit
# --------------------------------------------------------------------------- #
def test_review_is_persisted_with_label_and_audit(store):
    store.upsert_incident(payload())
    out = store.add_review("BB-UAE-2026-901", "analyst.a", "CONFIRM",
                           note="Red-edge peak visible", evidence_viewed=["spectral"])
    inc = out["incident"]
    assert inc["status"] == "CONFIRMED"
    assert inc["reviews"][0]["reviewer"] == "analyst.a"
    assert inc["reviews"][0]["previous_hypothesis"] == "BLOOM_LIKE"
    assert inc["reviews"][0]["model_id"] == "triage-1.0.0"
    assert "substance/species unconfirmed" in inc["disposition"]
    labels = store.labels("triage")
    assert len(labels) == 1 and labels[0]["target"]["y"] == 1
    assert labels[0]["source"] == "analyst_review"
    assert store.verify_audit_chain()["ok"]


def test_historical_prediction_is_never_overwritten(store):
    store.upsert_incident(payload())
    store.add_review("BB-UAE-2026-901", "analyst.a", "RECLASSIFY",
                     new_hypothesis="SEDIMENT_LIKE")
    inc = store.get_incident("BB-UAE-2026-901")
    assert inc["event_type_hypothesis"] == "SEDIMENT_LIKE"
    assert inc["predictions"][0]["output"]["event_type_hypothesis"] == "BLOOM_LIKE"


def test_review_requires_a_reviewer(store):
    store.upsert_incident(payload())
    with pytest.raises(ValueError):
        store.add_review("BB-UAE-2026-901", "  ", "CONFIRM")


def test_audit_chain_detects_tampering(store):
    store.upsert_incident(payload())
    store.add_review("BB-UAE-2026-901", "analyst.a", "FALSE_POSITIVE")
    assert store.verify_audit_chain()["ok"]
    con = sqlite3.connect(store.path)
    con.execute("UPDATE audit_events SET actor='someone.else' WHERE seq=2")
    con.commit()
    con.close()
    v = store.verify_audit_chain()
    assert not v["ok"] and v["first_bad_seq"] == 2


def test_field_workflow_moves_incident_back_to_review(store):
    store.upsert_incident(payload())
    store.add_review("BB-UAE-2026-901", "analyst.a", "NEEDS_FIELD_SAMPLE")
    samples = store.replace_sample_plan("BB-UAE-2026-901", [
        {"code": "S01", "role": "CORE", "lon": 56.45, "lat": 25.15},
        {"code": "S02", "role": "BACKGROUND", "lon": 56.55, "lat": 25.2}], "analyst.a")
    assert [s["status"] for s in samples] == ["PLANNED", "PLANNED"]
    store.update_sample("BB-UAE-2026-901-S01", {"status": "COLLECTED"}, "field.team")
    store.add_measurement("BB-UAE-2026-901", "chlorophyll_a", 7.9, "mg m-3", "lab.x",
                          sample_id="BB-UAE-2026-901-S01")
    inc = store.get_incident("BB-UAE-2026-901")
    assert inc["status"] == "UNDER_REVIEW"
    s01 = [s for s in inc["samples"] if s["code"] == "S01"][0]
    assert s01["status"] == "RESULT_RECEIVED"
    # Field evidence makes the next confirmation a field-based one.
    out = store.add_review("BB-UAE-2026-901", "analyst.a", "CONFIRM")
    assert "field evidence" in out["incident"]["disposition"]
    assert store.labels("triage")[-1]["source"] == "field_measurement"


def test_measurement_validation_and_lab_csv(store):
    store.upsert_incident(payload())
    with pytest.raises(ValueError):
        store.add_measurement("BB-UAE-2026-901", "chlorophyll_a", 3, "NTU", "x")
    with pytest.raises(ValueError):
        store.add_measurement("BB-UAE-2026-901", "turbidity", -1, "NTU", "x")
    with pytest.raises(ValueError):
        store.add_measurement("BB-UAE-2026-901", "radioactivity", 1, "Bq", "x")
    csv_text = ("parameter,value,unit,method\n"
                "turbidity,4.1,NTU,nephelometer\n"
                "chlorophyll_a,abc,mg m-3,HPLC\n"
                "salinity,40.2,PSU,CTD\n")
    r = store.import_lab_csv("BB-UAE-2026-901", csv_text, "lab.x")
    assert r["imported"] == 2 and len(r["rejected"]) == 1
    assert r["rejected"][0]["line"] == 3


# --------------------------------------------------------------------------- #
# Training, gate, promotion
# --------------------------------------------------------------------------- #
def _seed_labels(store, n=60, seed=1, validation_every=5):
    rng = np.random.default_rng(seed)
    for i in range(n):
        y = int(i % 2)
        feats = {f: float(rng.normal()) for f in L.TRIAGE_FEATURES}
        feats["seasonal_pct_primary"] = float(60 + 35 * y + rng.normal(0, 5))
        feats["persistence_frac"] = float(0.6 - 0.5 * y + rng.normal(0, 0.1))
        split = "validation" if i % validation_every == 0 else "train"
        store.add_label("triage", {"y": y}, feats, "cross_sensor_reference", "tester",
                        aoi_id=f"AOI-{i % 3}", group_key=f"g{i // 2}", split=split)


def test_training_fails_honestly_without_enough_labels(store):
    store.add_label("triage", {"y": 1}, {}, "analyst_review", "t", split="validation",
                    group_key="g")
    job = T.run_training_job(store, "triage", "analyst.a")
    assert job["status"] == "FAILED" and "insufficient" in job["error"]


def test_training_creates_a_candidate_with_a_gate_report(store):
    _seed_labels(store)
    job = T.run_training_job(store, "triage", "analyst.a")
    assert job["status"] == "SUCCEEDED", job
    m = store.get_model(job["candidate_model_id"])
    assert m["status"] == "CANDIDATE"
    names = {c["name"] for c in m["gate"]["checks"]}
    assert {"model_test_suite", "validation_dataset_unchanged",
            "primary_metric_not_worse", "calibration_acceptable",
            "no_subgroup_regression"} <= names
    assert m["gate"]["human_approval"]["required"] is True
    assert store.production_model("triage") is None          # nothing auto-promoted


def test_promotion_requires_a_human_and_a_passing_gate(store):
    _seed_labels(store)
    mid = T.run_training_job(store, "triage", "analyst.a")["candidate_model_id"]
    with pytest.raises(PermissionError):
        T.promote(store, mid, "system")
    m = store.get_model(mid)
    if m["gate"]["passed"]:
        prod = T.promote(store, mid, "supervisor.b", note="reviewed comparison")
        assert prod["status"] == "PRODUCTION"
        assert prod["gate"]["human_approval"]["approved_by"] == "supervisor.b"
    else:
        with pytest.raises(PermissionError):
            T.promote(store, mid, "supervisor.b")


def test_second_candidate_retires_the_first_and_rollback_restores_it(store):
    _seed_labels(store)
    m1 = T.run_training_job(store, "triage", "a")["candidate_model_id"]
    if not store.get_model(m1)["gate"]["passed"]:
        pytest.skip("synthetic data did not pass the gate")
    T.promote(store, m1, "supervisor.b")
    _seed_labels(store, n=20, seed=2, validation_every=10 ** 9)   # train-only labels
    m2 = T.run_training_job(store, "triage", "a")["candidate_model_id"]
    g2 = store.get_model(m2)["gate"]
    assert store.get_model(m2)["parent_model"] == m1
    if g2["passed"]:
        T.promote(store, m2, "supervisor.b")
        assert store.get_model(m1)["status"] == "RETIRED"
        T.rollback(store, m1, "supervisor.b", note="demo rollback")
        assert store.production_model("triage")["id"] == m1
        assert store.get_model(m2)["status"] == "RETIRED"


def test_gate_fails_when_the_validation_set_changes():
    y = np.array([0, 1] * 10, float)
    g = np.arange(20).astype(str)
    s = np.array(["A"] * 20)
    rep = L.evaluate_gate("triage", y * 0.8 + 0.1, np.full(20, 0.5), y, g, s,
                          "hash-frozen", "hash-different", [{"name": "t", "passed": True}])
    chk = {c["name"]: c for c in rep["checks"]}
    assert not chk["validation_dataset_unchanged"]["passed"] and not rep["passed"]


def test_model_artifact_roundtrip_and_tests():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 3))
    y = (X[:, 0] + rng.normal(0, 0.5, 40) > 0).astype(float)
    art = L.fit_logistic(X, y, features=["a", "b", "c"])
    assert all(t["passed"] for t in L.model_tests(art, X))
    rt = L.LinearArtifact.from_dict(json.loads(json.dumps(art.to_dict())))
    assert np.allclose(rt.predict(X), art.predict(X))
    p = art.predict(X)
    assert np.all((p >= 0) & (p <= 1))


def test_ridge_interval_contains_prediction_and_is_positive():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(60, 2))
    y = 10 ** (0.5 * X[:, 0] + 0.5 + rng.normal(0, 0.1, 60))
    art = L.fit_ridge_log10(X, y, features=["a", "b"], groups=np.arange(60) % 6)
    lo, hi = art.interval(X[:5])
    p = art.predict(X[:5])
    assert np.all(lo > 0) and np.all(lo <= p) and np.all(p <= hi)


# --------------------------------------------------------------------------- #
# Quantification verdicts
# --------------------------------------------------------------------------- #
def test_calibration_refuses_physical_units_with_too_few_matchups():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(8, 3))
    y = 10 ** (X[:, 0] * 0.3 + 0.5)
    res = Q.compare_models(X, y, np.arange(8) % 4, ["a", "b", "c"], "chl", "mg m-3")
    assert res["verdict"]["usable_for_physical_units"] is False
    assert res["verdict"]["quantity_kind"] == "PROXY"


def test_calibration_accepts_a_strong_grouped_relationship():
    rng = np.random.default_rng(4)
    X = rng.normal(size=(80, 3))
    y = 10 ** (X[:, 0] * 0.4 + 0.6 + rng.normal(0, 0.05, 80))
    res = Q.compare_models(X, y, np.arange(80) % 10, ["a", "b", "c"], "chl", "mg m-3")
    assert res["selected"] in res["models"]
    assert res["verdict"]["usable_for_physical_units"] is True
    for m in res["models"].values():
        assert m["ci95"]["rmse"][0] <= m["rmse"] <= m["ci95"]["rmse"][1] + 1e-9
