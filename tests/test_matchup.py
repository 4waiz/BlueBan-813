"""Matchup engine: tolerances, quality criteria and auditability."""
import numpy as np

from pipeline import matchup as M


def rec(t="2026-04-02T07:00:00Z", lat=25.15, lon=56.45, value=3.0):
    return M.FieldRecord("R1", "ST1", lat, lon, t, "chlorophyll_a", value, "mg m-3")


def good_box(v=0.02, n=3):
    return {"valid": np.ones((n, n), bool),
            "bands": {"B04": np.full((n, n), v)},
            "features": {"NDCI": np.full((n, n), 0.1)},
            "distance_m": 5.0, "flags": {"cloud_in_box": False}}


SCENE = {"id": "S2A_X", "time": "2026-04-02T06:46:19Z"}


def test_a_clean_coincident_box_passes_and_records_everything():
    m = M.evaluate_box(rec(), SCENE, good_box(), M.MatchupConfig(), 20.0)
    assert m.passed and m.reasons == []
    row = m.to_row()
    for k in ("rec_station", "rec_lat", "rec_lon", "rec_time_utc", "rec_parameter",
              "rec_value", "rec_unit", "scene_id", "scene_time", "delta_time_h",
              "distance_m", "valid_frac", "cv_primary", "band_B04", "feat_NDCI"):
        assert k in row
    assert abs(row["delta_time_h"] + 0.229) < 0.01


def test_time_tolerance_is_enforced_and_configurable():
    far = rec(t="2026-04-04T07:00:00Z")
    assert not M.evaluate_box(far, SCENE, good_box(), M.MatchupConfig(), 20).passed
    ok = M.evaluate_box(far, SCENE, good_box(), M.MatchupConfig(max_dt_hours=72), 20)
    assert ok.passed


def test_heterogeneous_or_cloudy_or_sparse_boxes_fail_with_reasons():
    b = good_box()
    b["bands"]["B04"] = np.array([[0.01, 0.05, 0.01], [0.05, 0.01, 0.05], [0.01, 0.05, 0.01]])
    m = M.evaluate_box(rec(), SCENE, b, M.MatchupConfig(), 20)
    assert not m.passed and any("CV" in r for r in m.reasons)
    b = good_box()
    b["flags"]["cloud_in_box"] = True
    assert "flag cloud_in_box" in M.evaluate_box(rec(), SCENE, b, M.MatchupConfig(), 20).reasons
    b = good_box()
    b["valid"][:] = False
    b["valid"][0, 0] = True
    assert any("valid fraction" in r for r in
               M.evaluate_box(rec(), SCENE, b, M.MatchupConfig(), 20).reasons)


def test_build_matchups_keeps_failures_and_picks_the_closest_passing_scene():
    scenes = [{"id": "far", "time": "2026-04-03T06:46:00Z"},
              {"id": "near", "time": "2026-04-02T06:46:00Z"}]
    ms = M.build_matchups([rec(), rec(t="2025-01-01T00:00:00Z")], scenes,
                          lambda r, s: good_box(), M.MatchupConfig(), 20)
    assert ms[0].passed and ms[0].scene_id == "near"
    assert not ms[1].passed and "no scene within" in ms[1].reasons[0]
    s = M.summary(ms)
    assert s["n_records"] == 2 and s["n_passed"] == 1


def test_sensitivity_reports_counts_per_tolerance():
    scenes = [{"id": "d2", "time": "2026-04-04T07:00:00Z"}]
    out = M.sensitivity([rec()], scenes, lambda r, s: good_box(), M.MatchupConfig(), 20,
                        dt_values=(3.0, 24.0, 72.0))
    assert [o["n_passed"] for o in out] == [0, 0, 1]
