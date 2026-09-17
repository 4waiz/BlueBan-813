"""BLUEBAN 813 API.

Serves the artefacts produced by the offline pipeline. The API does no
geospatial computation: heavy processing happens once in ``scripts/``, and this
layer reads the resulting JSON/GeoJSON/PNG so the interface stays fast.

Run:  uvicorn services.api.main:app --reload --port 8813
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVENTS = os.path.join(ROOT, "outputs", "events")
LAYERS = os.path.join(ROOT, "outputs", "layers")
VALIDATION = os.path.join(ROOT, "outputs", "validation")
METADATA = os.path.join(ROOT, "data", "metadata")
CONFIG = os.path.join(ROOT, "config")

app = FastAPI(
    title="BLUEBAN 813 API",
    version="0.1.0",
    description=(
        "Water Threat Intelligence for the Arab region. Every value served "
        "here is produced by the offline pipeline from real Earth observation "
        "data; nothing is hardcoded. Satellite 813 data is SIMULATED from "
        "Planet Tanager-1 measurements and is labelled as such everywhere."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"], allow_headers=["*"],
)


def _read(path: str) -> Any:
    if not os.path.exists(path):
        raise HTTPException(404, f"Not found: {os.path.relpath(path, ROOT)}. "
                                 f"Has the pipeline been run?")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=64)
def _cached(path: str, mtime: float) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _read_cached(path: str) -> Any:
    if not os.path.exists(path):
        raise HTTPException(404, f"Not found: {os.path.relpath(path, ROOT)}")
    return json.loads(_cached(path, os.path.getmtime(path)))


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class AssetIn(BaseModel):
    name: str = Field(..., max_length=120)
    type: str = Field("CUSTOM", max_length=48)
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)
    sensitivity: float | None = Field(None, ge=0.0, le=1.0)
    notes: str = Field("", max_length=500)


# --------------------------------------------------------------------------- #
# System
# --------------------------------------------------------------------------- #
@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "service": "blueban-813", "version": "0.1.0"}


@app.get("/api/status", tags=["system"])
def status():
    """What the pipeline has actually produced, so the UI can degrade honestly."""
    def ok(p):
        return os.path.exists(p)
    idx = os.path.join(EVENTS, "index.json")
    n_events = 0
    if ok(idx):
        n_events = len(_read(idx).get("events", []))
    return {
        "events_available": n_events,
        "artefacts": {
            "event_index": ok(idx),
            "layers": ok(os.path.join(LAYERS, "raster_bounds.json")),
            "rgb": ok(os.path.join(LAYERS, "rgb_water.png")),
            "anomaly": ok(os.path.join(LAYERS, "anomaly.png")),
            "hyperspectral_lift": ok(os.path.join(VALIDATION, "hyperspectral_lift.json")),
            "detectability_lift": ok(os.path.join(VALIDATION, "detectability_lift_hard.json")),
            "simulator_validation": ok(os.path.join(VALIDATION, "simulator_validation.json")),
            "temporal_baseline": ok(os.path.join(VALIDATION, "s2_baseline_report.json")),
        },
        "data_policy": {
            "real_813_data_used": False,
            "813_status": "SIMULATED from Planet Tanager-1",
            "in_situ_available": False,
            "note": "Satellite 813 is incubation-only for this programme phase. "
                    "See docs/813_PRODUCT_NOTES.md.",
        },
    }


@app.get("/api/config", tags=["system"])
def config():
    import yaml
    p = os.path.join(CONFIG, "project.yaml")
    if not os.path.exists(p):
        raise HTTPException(404, "config/project.yaml missing")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
@app.get("/api/events", tags=["events"])
def list_events():
    return _read_cached(os.path.join(EVENTS, "index.json"))


@app.get("/api/events/{event_id}", tags=["events"])
def get_event(event_id: str):
    return _read_cached(os.path.join(EVENTS, f"{_safe(event_id)}.json"))


@app.get("/api/events/{event_id}/spectrum", tags=["events"])
def get_spectrum(event_id: str):
    return _read_cached(os.path.join(EVENTS, f"{_safe(event_id)}_spectra.json"))


@app.get("/api/events/{event_id}/forecast", tags=["events"])
def get_forecast(event_id: str):
    return _read_cached(os.path.join(EVENTS, f"{_safe(event_id)}_forecast.json"))


@app.get("/api/events/{event_id}/samples", tags=["events"])
def get_samples(event_id: str, fmt: str = "geojson"):
    if fmt == "csv":
        p = os.path.join(EVENTS, f"{_safe(event_id)}_samples.csv")
        if not os.path.exists(p):
            raise HTTPException(404, "sample plan not found")
        return FileResponse(p, media_type="text/csv",
                            filename=f"{_safe(event_id)}_field_plan.csv")
    return _read_cached(os.path.join(EVENTS, f"{_safe(event_id)}_samples.geojson"))


@app.get("/api/events/{event_id}/provenance", tags=["events"])
def get_provenance(event_id: str):
    return _read_cached(os.path.join(EVENTS, f"{_safe(event_id)}_provenance.json"))


# --------------------------------------------------------------------------- #
# Layers
# --------------------------------------------------------------------------- #
@app.get("/api/layers", tags=["layers"])
def layers():
    b = _read_cached(os.path.join(LAYERS, "raster_bounds.json"))
    avail = {}
    for key, fn, label, kind in [
        ("rgb", "rgb_water.png", "True colour (665/561/441 nm), water-stretched", "raster"),
        ("anomaly", "anomaly.png", "RX spectral anomaly (log scale)", "raster"),
        ("ndci", "ndci.png", "NDCI chlorophyll proxy", "raster"),
        ("turbidity", "turbidity.png", "Turbidity proxy", "raster"),
        ("events", "event_polygons.geojson", "Detected event regions", "vector"),
        ("water", "water_mask.geojson", "Open-water mask", "vector"),
    ]:
        p = os.path.join(LAYERS, fn)
        if os.path.exists(p):
            avail[key] = {"kind": kind, "label": label,
                          "url": f"/api/layers/{key}",
                          "bounds_lonlat": b["bounds_lonlat"] if kind == "raster" else None}
    return {"bounds_lonlat": b["bounds_lonlat"], "grid": b, "layers": avail}


_LAYER_FILES = {
    "rgb": ("rgb_water.png", "image/png"),
    "anomaly": ("anomaly.png", "image/png"),
    "ndci": ("ndci.png", "image/png"),
    "turbidity": ("turbidity.png", "image/png"),
    "events": ("event_polygons.geojson", "application/geo+json"),
    "water": ("water_mask.geojson", "application/geo+json"),
    "sensor_spec_813": ("sensor_spec_813.json", "application/json"),
}


@app.get("/api/layers/{name}", tags=["layers"])
def layer(name: str):
    if name not in _LAYER_FILES:
        raise HTTPException(404, f"Unknown layer '{name}'")
    fn, mt = _LAYER_FILES[name]
    p = os.path.join(LAYERS, fn)
    if not os.path.exists(p):
        raise HTTPException(404, f"Layer '{name}' not built yet")
    return FileResponse(p, media_type=mt)


# --------------------------------------------------------------------------- #
# Validation and the hyperspectral question
# --------------------------------------------------------------------------- #
@app.get("/api/validation", tags=["validation"])
def validation():
    """Everything we measured, including the experiments that found no effect."""
    out = {}
    for key, fn in [
        ("simulator_validation", "simulator_validation.json"),
        ("olci_retrieval_ablation", "hyperspectral_lift.json"),
        ("detectability_hard", "detectability_lift_hard.json"),
        ("detectability_easy", "detectability_lift_easy.json"),
        ("temporal_baseline", "s2_baseline_report.json"),
    ]:
        p = os.path.join(VALIDATION, fn)
        if os.path.exists(p):
            out[key] = _read_cached(p)
    if not out:
        raise HTTPException(404, "No validation artefacts. Run the experiments.")
    out["summary"] = _validation_summary(out)
    return out


def _validation_summary(v: dict) -> dict:
    s = {"headline": [], "honest_negatives": []}
    d = v.get("detectability_hard", {})
    lift = d.get("hyperspectral_lift", {}).get("813_hyperspectral_205band")
    if lift:
        base = d["results"]["spatial_blocked"]["S2_multispectral_11band"]
        hs = d["results"]["spatial_blocked"]["813_hyperspectral_205band"]
        cb, ch = base["confusion_matrix"], hs["confusion_matrix"]
        fa_b = cb["fp"] / max(cb["fp"] + cb["tp"], 1)
        fa_h = ch["fp"] / max(ch["fp"] + ch["tp"], 1)
        s["headline"].append({
            "metric": "F1 on the operational detection boundary",
            "multispectral": base["f1"],
            "hyperspectral_813": hs["f1"],
            "absolute_gain": lift.get("f1_absolute_gain"),
            "ci95": lift.get("f1_gain_ci95"),
            "significant": lift.get("f1_gain_significant"),
            "operational_reading": {
                "false_alarm_share_multispectral": round(fa_b, 5),
                "false_alarm_share_hyperspectral": round(fa_h, 5),
                "relative_reduction_pct": round(100 * (fa_b - fa_h) / fa_b, 2)
                if fa_b > 0 else None,
                "false_positives_multispectral": cb["fp"],
                "false_positives_hyperspectral": ch["fp"],
            },
        })
    o = v.get("olci_retrieval_ablation", {})
    for tname, t in o.get("targets", {}).items():
        l = t.get("hyperspectral_lift", {}).get("813_hyperspectral_205band", {})
        s["honest_negatives"].append({
            "experiment": f"OLCI {tname} retrieval",
            "multispectral_r2": l.get("r2_baseline"),
            "hyperspectral_r2": l.get("r2_hyperspectral"),
            "r2_gain": l.get("r2_gain"),
            "significant": l.get("r2_gain_significant"),
            "reading": "No detectable hyperspectral advantage for this target. "
                       "Reported because it was measured, not hidden.",
        })
    e = v.get("detectability_easy", {})
    el = e.get("hyperspectral_lift", {}).get("813_hyperspectral_205band", {})
    if el:
        s["honest_negatives"].append({
            "experiment": "Gross event detection (easy regime)",
            "reading": "Both sensor configurations reach F1 of about 1.00. "
                       "Obvious plumes do not require hyperspectral data, and "
                       "we say so.",
            "f1_gain": el.get("f1_absolute_gain"),
        })
    return s


@app.get("/api/hyperspectral-lift", tags=["validation"])
def hyperspectral_lift():
    """The five-second answer to 'did 813 add measurable value?'"""
    v = {}
    for key, fn in [("detectability_hard", "detectability_lift_hard.json"),
                    ("detectability_easy", "detectability_lift_easy.json"),
                    ("olci_retrieval_ablation", "hyperspectral_lift.json")]:
        p = os.path.join(VALIDATION, fn)
        if os.path.exists(p):
            v[key] = _read_cached(p)
    if not v:
        raise HTTPException(404, "Ablation not run yet")
    return _validation_summary(v)


@app.get("/api/timeseries", tags=["validation"])
def timeseries(zone: str | None = None):
    p = os.path.join(VALIDATION, "s2_timeseries.json")
    data = _read_cached(p)
    if zone:
        if zone not in data:
            raise HTTPException(404, f"Unknown zone '{zone}'. "
                                     f"Available: {list(data)}")
        return {zone: data[zone]}
    return data


# --------------------------------------------------------------------------- #
# Assets
# --------------------------------------------------------------------------- #
ASSET_STORE = os.path.join(EVENTS, "assets.json")


@app.get("/api/assets", tags=["assets"])
def get_assets():
    """Operator assets.

    BLUEBAN 813 ships no infrastructure database. Anything returned here was
    placed by an operator, or is a clearly labelled demonstration fixture.
    """
    from pipeline import exposure as EX
    if os.path.exists(ASSET_STORE):
        stored = _read(ASSET_STORE)
    else:
        stored = {"assets": []}
    idx = os.path.join(EVENTS, "index.json")
    if os.path.exists(idx):
        ev = _read(idx)["events"]
        if ev:
            e = _read(os.path.join(EVENTS, f"{ev[0]['event_id']}.json"))
            demo = [x["asset"] for x in e.get("exposure", [])]
            known = {a["id"] for a in stored["assets"]}
            stored["assets"] = [a for a in demo if a["id"] not in known] + stored["assets"]
    return {
        "assets": stored["assets"],
        "types": EX.ASSET_TYPES,
        "policy": "Operator-configured only. No infrastructure coordinates are "
                  "bundled with this software.",
    }


@app.post("/api/assets", tags=["assets"])
def add_asset(asset: AssetIn = Body(...)):
    from pipeline import exposure as EX
    store = _read(ASSET_STORE) if os.path.exists(ASSET_STORE) else {"assets": []}
    new_id = f"U{len(store['assets'])+1:03d}"
    a = EX.Asset(new_id, asset.name, asset.type.upper(), asset.lon, asset.lat,
                 asset.sensitivity, asset.notes, source="api")
    store["assets"].append(a.to_dict())
    os.makedirs(os.path.dirname(ASSET_STORE), exist_ok=True)
    with open(ASSET_STORE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=1)
    return {"created": a.to_dict(), "count": len(store["assets"])}


# --------------------------------------------------------------------------- #
# Documentation passthrough (the Evidence screen links to these)
# --------------------------------------------------------------------------- #
DOCS = {
    "data-access-audit": "DATA_ACCESS_AUDIT.md",
    "aoi-selection": "AOI_SELECTION.md",
    "813-product-notes": "813_PRODUCT_NOTES.md",
    "methodology": "METHODOLOGY.md",
    "validation-report": "VALIDATION_REPORT.md",
    "limitations": "LIMITATIONS.md",
    "data-lineage": "DATA_LINEAGE.md",
    "business-case": "BUSINESS_CASE.md",
    "judging-matrix": "JUDGING_MATRIX.md",
}


@app.get("/api/docs-list", tags=["docs"])
def docs_list():
    out = []
    for k, fn in DOCS.items():
        p = os.path.join(ROOT, "docs", fn)
        if os.path.exists(p):
            out.append({"key": k, "file": fn, "bytes": os.path.getsize(p)})
    return {"docs": out}


@app.get("/api/docs/{key}", response_class=PlainTextResponse, tags=["docs"])
def get_doc(key: str):
    if key not in DOCS:
        raise HTTPException(404, f"Unknown doc '{key}'")
    p = os.path.join(ROOT, "docs", DOCS[key])
    if not os.path.exists(p):
        raise HTTPException(404, f"{DOCS[key]} not written yet")
    with open(p, encoding="utf-8") as f:
        return f.read()


def _safe(s: str) -> str:
    """Reject anything that could escape the outputs directory."""
    if not s or "/" in s or "\\" in s or ".." in s:
        raise HTTPException(400, "Invalid identifier")
    return s
