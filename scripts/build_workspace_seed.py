"""Assemble the operational seed: incidents, models, labels, AOIs and assets.

One file, ``outputs/workspace/seed.json``, feeds BOTH deployments:

* the hosted static site copies it to ``/pipeline/workspace/seed.json`` and the
  in-browser workspace (apps/web/lib/engine/local.ts) initialises from it;
* ``scripts/seed_db.py`` loads it into the FastAPI SQLite database.

Nothing here is invented: every incident comes from a pipeline output
(``outputs/incidents/*.json`` for the UAE, ``outputs/events/BB-2026-001*.json``
for the Annaba negative control), every AOI from config/aois_uae.yaml plus the
WATCH time series, every asset from an OpenStreetMap register.
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import yaml  # noqa: E402

from pipeline import incidents as inc_mod  # noqa: E402
from pipeline import learning as L  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "workspace")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _utc(s: str) -> str:
    return s.replace(".000000Z", "Z").split(".")[0].rstrip("Z") + "Z"


# --------------------------------------------------------------------------- #
# Negative control: the Gulf of Annaba case, re-expressed as an incident
# --------------------------------------------------------------------------- #
def annaba_incident() -> dict | None:
    ep = os.path.join(ROOT, "outputs", "events", "BB-2026-001.json")
    if not os.path.exists(ep):
        return None
    e = _read(ep)
    sp = _read(os.path.join(ROOT, "outputs", "events", "BB-2026-001_spectra.json"))
    prov = _read(os.path.join(ROOT, "outputs", "events", "BB-2026-001_provenance.json"))
    polys = _read(os.path.join(ROOT, "outputs", "layers", "event_polygons.geojson"))
    rb = _read(os.path.join(ROOT, "outputs", "layers", "raster_bounds.json"))
    primary = next((f for f in polys["features"] if f["properties"].get("is_primary")),
                   polys["features"][0])
    t = e["temporal"]["assessment"]
    idx = e["indices"]
    g = e["geometry"]
    b = rb["bounds_lonlat"]
    feats = {
        "seasonal_pct_primary": t["seasonal_percentile"],
        "robust_z_primary": None,
        "rx_pct": e["anomaly"]["event_percentile_in_scene"],
        "log10_area_km2": math.log10(g["area_km2"]),
        "persistence_frac": None,
        "dist_shore_km": g["median_distance_from_shore_m"] / 1000.0,
        "ndci_delta": idx["NDCI"]["event_median"] - idx["NDCI"]["background_median"],
        "mci_delta": None,
        "tur_delta": idx["TURBIDITY_PROXY"]["event_median"] - idx["TURBIDITY_PROXY"]["background_median"],
        "fai_mean": idx["FAI"]["event_median"],
        "hue_delta_deg": None,
        "cloud_adjacent_frac": 0.0,
        "valid_frac_aoi": e["quality"]["scene"]["valid_fraction"],
    }
    wl = sp["wavelengths_nm"]
    exposure = [{"asset": {k: x["asset"][k] for k in ("id", "name", "type", "type_label", "lon", "lat", "source")},
                 "distance_m": x["distance_m"], "direction": x.get("direction"),
                 "exposure_score": x.get("exposure_score"), "basis": x.get("basis", [])}
                for x in e.get("exposure", [])]
    return {
        "id": "BB-DZ-2025-001", "aliases": ["BB-2026-001"],
        "status": "MONITORING", "aoi_id": "DZ-ANNABA",
        "aoi_name": "Gulf of Annaba, Algeria (negative control)",
        "detected_at": _utc(e["generated_utc"]), "observation_time": _utc(e["observation"]["acquisition_utc"]),
        "event_type_hypothesis": "PERSISTENT_FEATURE",
        "severity": round(e["severity"], 4), "confidence": round(e["confidence"], 4),
        "priority": e["assessment"]["priority"], "model_id": "triage-1.0.0",
        "role": "negative_control",
        "title": "Spatial anomaly stood down: persistent coastal feature",
        "summary": ("RX flags a 1.13 km² nearshore region at the 99.7th percentile of the scene's water, "
                    "with a sediment-like spectrum. Against 428 Sentinel-2 observations of the same zone "
                    "(2020-2025) it sits at the 6.6th seasonal percentile: cleaner than usual. BlueBan "
                    "stands down. This is the false-alarm suppression the product is built around."),
        "geometry": primary["geometry"], "centroid": g["centroid_lonlat"], "area_km2": g["area_km2"],
        "water_quality": {"features": {
            "NDCI": {"value": idx["NDCI"]["event_median"], "units": "dimensionless", "quantity_kind": "PROXY",
                     "baseline_median": idx["NDCI"]["background_median"], "label": "Chlorophyll proxy (NDCI)"},
            "TURBIDITY_PROXY": {"value": idx["TURBIDITY_PROXY"]["event_median"], "units": "dimensionless",
                                "quantity_kind": "PROXY", "label": "Turbidity proxy (red/green)",
                                "baseline_median": idx["TURBIDITY_PROXY"]["background_median"],
                                "seasonal_percentile": t["seasonal_percentile"]},
            "FAI": {"value": idx["FAI"]["event_median"], "units": "reflectance", "quantity_kind": "PROXY",
                    "label": "Floating Algae Index"}}},
        "temporal": {"seasonal_percentile": t["seasonal_percentile"], "n_seasonal": t["n_seasonal"],
                     "persistence_frac": None,
                     "note": "Zone P95 of the turbidity proxy against 106 same-season Sentinel-2 observations."},
        "spatial": {"rx_percentile": e["anomaly"]["event_percentile_in_scene"]},
        "sensor_agreement": {
            "Tanager-1 (hyperspectral)": {"agrees": True, "note": "RX 99.7th percentile of scene water"},
            "Sentinel-2 L2A baseline": {"agrees": False, "note": "6.6th seasonal percentile (428 obs)"},
            "813 (simulated)": {"agrees": True, "note": "simulated from Tanager; not independent"}},
        "quality_flags": ["Nearshore: median 90 m from shore; bottom reflectance is a competing explanation",
                          "Cloud 0.08 %, product bad bands excluded (58 of 426)"],
        "exposure": exposure,
        "field_validation": {"status": "NOT_REQUIRED (stood down)"},
        "provenance": {"sources": prov.get("sources", []), "algorithm": prov.get("algorithm"),
                       "code_version": prov.get("code_version")},
        "model_features": {k: (None if v is None or (isinstance(v, float) and not math.isfinite(v))
                               else round(float(v), 5)) for k, v in feats.items()},
        "spectral": {"wavelengths_nm": wl, "event": sp["event"]["mean"], "background": sp["background"]["mean"],
                     "background_p05": sp["background"]["p05"], "background_p95": sp["background"]["p95"],
                     "sensor": "Tanager-1 (real hyperspectral, 30 m)", "simulated": False},
        "layers": {"bounds": b, "default": ["rgb", "anomaly"], "rasters": [
            {"key": "rgb", "label": "True colour (Tanager 665/561/441 nm)", "url": "layers/annaba/rgb_water.png",
             "bounds": b, "sensor": "Tanager-1", "date": "2025-06-01"},
            {"key": "anomaly", "label": "RX spectral anomaly", "url": "layers/annaba/anomaly.png", "bounds": b,
             "sensor": "Tanager-1"},
            {"key": "ndci", "label": "NDCI (chlorophyll proxy)", "url": "layers/annaba/ndci.png", "bounds": b,
             "sensor": "Tanager-1"},
            {"key": "turbidity", "label": "Turbidity proxy", "url": "layers/annaba/turbidity.png", "bounds": b,
             "sensor": "Tanager-1"}]},
        "disposition": ("AUTO_STAND_DOWN: temporal veto at the 6.6th seasonal percentile; persistent "
                        "coastal feature, not a new event"),
        "forecast": _annaba_forecast(),
        "context": [{"title": "Annaba negative control", "source": "docs/archive/AOI_SELECTION_TANAGER_2026-09-15.md",
                     "note": "Originally the primary demo; demoted under the mentor brief."}],
        "samples": [],
    }


def _annaba_forecast():
    fp = os.path.join(ROOT, "outputs", "events", "BB-2026-001_forecast.json")
    if not os.path.exists(fp):
        return None
    f = _read(fp)
    steps = []
    for s in f.get("steps", []):
        parts = s.get("particles") or []
        steps.append({"hours": s["hours"], "centroid": s["centroid"], "spread_radius_m": s["spread_radius_m"],
                      "bearing_deg": s.get("bearing_deg"), "displacement_m": s.get("displacement_m"),
                      "particles": parts[::max(1, len(parts) // 150)]})
    meta = f.get("metadata") or f.get("meta") or {}
    w = meta.get("wind_at_t0") or {}
    return {"steps": steps, "label": "SCENARIO TRAJECTORY ESTIMATE (wind-only)",
            "is_hydrodynamic_model": False,
            "wind": ({"speed_kmh": w.get("speed_ms", 0) * 3.6, "from": f"{w.get('direction_from_deg', 0):.0f} deg"} if w else None)}


# --------------------------------------------------------------------------- #
# AOIs with their latest observation and pass pattern
# --------------------------------------------------------------------------- #
def aoi_rows(incidents: list) -> list:
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "aois_uae.yaml"), encoding="utf-8"))["aois"]
    rows = []
    for aid, a in cfg.items():
        row = {"id": aid, "name": a["name"], "emirate": a.get("emirate"), "coast": a.get("coast"),
               "bbox": a["bbox"], "optical_regime": a.get("optical_regime"), "status": "MONITORING",
               "created_by": "config", "open_incidents": sum(1 for i in incidents if i["aoi_id"] == aid
                                                             and i["status"] in inc_mod.OPEN_STATES)}
        wp = os.path.join(ROOT, "outputs", "watch", f"{aid}.json")
        if os.path.exists(wp):
            w = _read(wp)
            ok = [r for r in w["rows"] if "error" not in r and (r.get("all") or {}).get("n_water", 0) >= 200]
            if ok:
                last = ok[-1]
                row["last_observation"] = last.get("datetime", last["date"])
                row["last_platform"] = last.get("platform")
                row["n_valid_observations"] = len(ok)
                now = dt.datetime.now(dt.timezone.utc)
                row["n_obs_7d"] = sum(1 for r in ok if (now - dt.datetime.fromisoformat(
                    r.get("datetime", r["date"] + "T00:00:00+00:00").replace("Z", "+00:00"))).days <= 7)
                def p95(f):
                    z = (last.get("all") or {}).get(f) or {}
                    return z.get("p95")
                row["latest"] = {"NDCI_p95": p95("NDCI"), "MCI_p95": p95("MCI"),
                                 "TUR_p95": p95("TUR_NECHAD2016"), "HUE_p50": ((last.get("all") or {}).get("HUE_ANGLE") or {}).get("p50")}
            passes = {}
            for r in w["rows"]:
                if "datetime" in r and r.get("relative_orbit") is not None:
                    k = f"{r.get('platform')}|{r['relative_orbit']}"
                    passes[k] = max(passes.get(k, ""), r["datetime"])
            row["pass_pattern"] = [{"platform": k.split("|")[0], "relative_orbit": int(k.split("|")[1]),
                                    "last": v} for k, v in sorted(passes.items())]
        rows.append(row)
    rows.append({"id": "DZ-ANNABA", "name": "Gulf of Annaba (negative control)", "emirate": None,
                 "coast": "Mediterranean", "bbox": [7.5175, 36.8739, 7.8093, 37.0599],
                 "optical_regime": "nearshore turbid band, deep offshore", "status": "ARCHIVED_CONTROL",
                 "created_by": "config", "open_incidents": 0})
    return rows


def asset_rows() -> list:
    out = []
    for p in ("assets_uae.geojson", "assets.geojson"):
        fp = os.path.join(ROOT, "config", p)
        if not os.path.exists(fp):
            continue
        for f in _read(fp)["features"]:
            pr = f["properties"]
            lon, lat = f["geometry"]["coordinates"][:2]
            out.append({"id": pr.get("id"), "name": pr.get("name"), "type": pr.get("type"),
                        "lon": lon, "lat": lat, "source": pr.get("source") or pr.get("osm") or "osm",
                        "aoi_id": pr.get("aoi_id") or ("DZ-ANNABA" if p == "assets.geojson" else None),
                        "notes": pr.get("notes")})
    return out


def rules_model(val_labels: list) -> dict:
    """Production model v1.0: the documented rule-based triage."""
    m = {"id": "triage-1.0.0", "task": "triage", "version": "1.0.0", "model_type": "rules",
         "created_at": "2026-09-30T00:00:00Z", "training_dataset_version": None,
         "validation_dataset_hash": None, "feature_set": L.TRIAGE_FEATURES,
         "params": {"rule": "p = 0.05 + 0.9 * clip((seasonal_pct - 80)/20) * (1 - persistence) "
                            "* (1 - 0.6 cloud_adjacent)"},
         "artifact": {"kind": "rules", "reference": "pipeline/learning.py:rules_score"},
         "status": "PRODUCTION", "parent_model": None,
         "notes": "Transparent detection rule used to raise incidents. The learned candidates must beat "
                  "it on the frozen validation set before a human may promote them.",
         "gate": None, "promoted_by": "Team Kanban (initial deployment)",
         "promoted_at": "2026-09-30T00:00:00Z", "metrics": []}
    if val_labels:
        import numpy as np
        X, y, _, _, _ = L.to_matrix(val_labels, L.TRIAGE_FEATURES)
        ok = np.isin(y, [0, 1])
        if ok.sum() and len(set(y[ok].tolist())) == 2:
            mt = L.classification_metrics(y[ok], L.rules_score(X[ok]))
            m["metrics"] = [{"split": "validation", "subgroup": "all", "metric": k, "value": mt[k],
                             "n": mt["n"]} for k in ("auroc", "auprc", "f1", "precision", "recall",
                                                     "brier", "ece")]
            m["validation_dataset_hash"] = L.dataset_hash([l for l, keep in zip(val_labels, ok) if keep])
    return m


def main():
    incidents = []
    for p in sorted(glob.glob(os.path.join(ROOT, "outputs", "incidents", "BB-*.json"))):
        incidents.append(_read(p))
    ctl = annaba_incident()
    if ctl:
        incidents.append(ctl)
    for inc in incidents:
        problems = inc_mod.validate_payload(inc)
        if problems:
            raise SystemExit(f"{inc['id']}: invalid payload: {problems}")
    lp = os.path.join(ROOT, "outputs", "labels", "seed_labels.json")
    labels = _read(lp)["labels"] if os.path.exists(lp) else []
    val = [l for l in labels if l["split"] == "validation"]
    seed = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "incidents": incidents, "models": [rules_model(val)], "labels": labels,
            "aois": aoi_rows(incidents), "assets": asset_rows(),
            # Reference only: each engine freezes its OWN validation hash on first
            # training (the browser hashes canonical JSON differently from Python).
            "meta": {"python_validation_hash:triage": L.dataset_hash(val) if val else None}}
    body = json.dumps({k: v for k, v in seed.items() if k != "generated_utc"}, sort_keys=True, default=str)
    seed["seed_version"] = hashlib.sha256(body.encode()).hexdigest()[:12]
    if seed["meta"]["python_validation_hash:triage"] is None:
        seed["meta"].pop("python_validation_hash:triage")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "seed.json"), "w", encoding="utf-8") as f:
        json.dump(seed, f, separators=(",", ":"), default=str)
    print(f"seed {seed['seed_version']}: {len(incidents)} incidents, {len(labels)} labels, "
          f"{len(seed['aois'])} AOIs, {len(seed['assets'])} assets")


if __name__ == "__main__":
    main()
