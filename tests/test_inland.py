"""Inland complement (Shawka Dam): integration guards.

The site is wired in from precomputed outputs. These tests pin what must not
drift: the two caveats carried over verbatim, the published summary never
containing per-pixel EnMAP reflectance, the restricted folder never being
tracked or served, and the counts the docs quote.
"""
import importlib
import json
import os
import shutil
import subprocess

import pytest
import yaml
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY = os.path.join(ROOT, "outputs", "inland", "summary.json")
CAVEATS = [
    'EnMAP\'s license is "proprietary" with redistribution terms not yet confirmed for public submission',
    "the anomaly/fingerprint results are based on a ~10-17 pixel background population, not a calibrated detector",
]
#: Keys that would carry per-pixel reflectance or spectra in the source files.
WITHHELD_KEYS = {"group_values", "spectrum_813", "core_pixel_spectra_813", "brightness", "joint_darkness", "joint_min"}


@pytest.fixture(scope="module")
def summary():
    with open(SUMMARY, encoding="utf-8") as f:
        return json.load(f)


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def test_inland_modules_import():
    for m in ("water_mask", "anomaly", "fingerprint", "satellite813", "provenance"):
        importlib.import_module(f"pipeline.inland.{m}")
    pytest.importorskip("pandas")
    importlib.import_module("pipeline.inland.temporal")


def test_caveats_carried_over_verbatim(summary):
    assert summary["caveats"] == CAVEATS
    with open(os.path.join(ROOT, "config", "project.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["sites"]["shawka_dam"]["caveats"] == CAVEATS
    for k in ("project", "aoi", "sensors", "scenes", "water_mask", "quality", "anomaly", "temporal"):
        assert k in cfg, f"existing top-level key {k} must stay"


def test_public_summary_has_no_per_pixel_reflectance(summary):
    leaked = WITHHELD_KEYS & set(_keys(summary))
    assert not leaked, f"withheld EnMAP content in the public summary: {leaked}"
    assert summary["licence"]["enmap"] == "proprietary"


def test_counts_match_the_package(summary):
    m = summary["masks"]
    assert (m["2022-09-08"]["n"], m["2024-04-24"]["n"], m["persistent_core"]["n"], m["mndwi_core"]["n"]) == (10, 4, 10, 0)
    assert summary["window"]["shape"] == [25, 30]
    assert summary["window"]["n_inside_reconstructed"] == m["px_inside_locked_polygon_reported"] == 84
    assert m["persistent_core"]["n_inside_reconstructed_polygon"] == 10
    t = summary["temporal"]
    assert (t["n_observations"], t["n_flagged"], t["z_threshold"]) == (28, 7, 1.5)
    lo, hi = (t["chance_level"]["expected_flags_if_indices_perfectly_correlated"],
              t["chance_level"]["expected_flags_if_indices_independent"])
    assert lo < t["n_flagged"] < hi
    assert summary["baseline"]["n"] == 28
    assert {f["id"] for f in summary["flags"]} >= {"F1", "F2", "F5"}


def test_restricted_folder_is_ignored_and_untracked():
    if not shutil.which("git"):
        pytest.skip("git not available")
    probe = "data/inland/restricted/anomaly/anomaly_fingerprint_report.json"
    ignored = subprocess.run(["git", "check-ignore", "-q", probe], cwd=ROOT)
    assert ignored.returncode == 0, "data/inland/restricted/ must be gitignored"
    tracked = subprocess.run(["git", "ls-files", "data/inland/restricted"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
    assert tracked == "", f"restricted EnMAP files are tracked: {tracked}"


def test_api_serves_public_files_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.sqlite'}")
    main = importlib.import_module("services.api.main")
    c = TestClient(main.app)
    r = c.get("/api/inland/summary")
    assert r.status_code == 200 and r.json()["caveats"] == CAVEATS
    files = c.get("/api/inland/files").json()["files"]
    assert files and not any(f["path"].startswith("restricted") for f in files)
    assert c.get("/api/inland/files/temporal/temporal_deviations.json").status_code == 200
    assert c.get("/api/inland/files/restricted/anomaly/anomaly_fingerprint_report.json").status_code == 404
    assert c.get("/api/inland/files/water_mask/persistent_wet_core_mask.npy").status_code == 415
    assert c.get("/api/inland/files/..%2F..%2Fconfig%2Fproject.yaml").status_code == 404
    assert c.get("/api/inland/docs/REVIEW_FLAGS.md").status_code == 200
