"""Bake the pipeline artefacts into the web app for a static deployment.

The BLUEBAN 813 API is read-only: it serves JSON, GeoJSON, PNG and CSV that the
offline pipeline already produced. That means the whole product can ship as a
static site with no server, which is what makes a Cloudflare Pages deployment
possible and keeps the hosted demo free and fast.

This script copies every artefact into ``apps/web/public/pipeline`` and synthesises
the few endpoints that the FastAPI service computes on the fly (``/api/status``,
``/api/layers``, ``/api/validation``, ``/api/hyperspectral-lift``,
``/api/assets``, ``/api/docs-list``) as files with the same shape, so the client
does not need to know which mode it is running in.

Usage: python scripts/build_static_site.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

EVENTS = os.path.join(ROOT, "outputs", "events")
LAYERS = os.path.join(ROOT, "outputs", "layers")
VALIDATION = os.path.join(ROOT, "outputs", "validation")
DOCS = os.path.join(ROOT, "docs")
# Not "public/data": /data is also an app route, so the bundle lives under
# /pipeline to keep the two namespaces separate.
OUT = os.path.join(ROOT, "apps", "web", "public", "pipeline")

# Mirrors services/api/main.py:DOCS so both modes expose the same set.
DOC_KEYS = {
    "data-access-audit": "DATA_ACCESS_AUDIT.md",
    "official-resource-audit": "OFFICIAL_RESOURCE_AUDIT.md",
    "aoi-selection": "AOI_SELECTION.md",
    "813-product-notes": "813_PRODUCT_NOTES.md",
    "methodology": "METHODOLOGY.md",
    "validation-report": "VALIDATION_REPORT.md",
    "limitations": "LIMITATIONS.md",
    "data-lineage": "DATA_LINEAGE.md",
    "business-case": "BUSINESS_CASE.md",
    "judging-matrix": "JUDGING_MATRIX.md",
}

LAYER_FILES = {
    "rgb": ("rgb_water.png", "raster",
            "True colour (665/561/441 nm), water-stretched"),
    "anomaly": ("anomaly.png", "raster", "RX spectral anomaly (log scale)"),
    "ndci": ("ndci.png", "raster", "NDCI chlorophyll proxy"),
    "turbidity": ("turbidity.png", "raster", "Turbidity proxy"),
    "events": ("event_polygons.geojson", "vector", "Detected event regions"),
    "water": ("water_mask.geojson", "vector", "Open-water mask"),
}


def log(m):
    print(f"  {m}", flush=True)


def copy_tree(src, dst, exts=None):
    if not os.path.isdir(src):
        log(f"SKIP (missing): {os.path.relpath(src, ROOT)}")
        return 0
    os.makedirs(dst, exist_ok=True)
    n = 0
    for fn in sorted(os.listdir(src)):
        sp = os.path.join(src, fn)
        if not os.path.isfile(sp):
            continue
        if exts and os.path.splitext(fn)[1].lower() not in exts:
            continue
        shutil.copy2(sp, os.path.join(dst, fn))
        n += 1
    return n


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    print("Baking static data bundle")

    # ---------------------------------------------------------------- events
    n = copy_tree(EVENTS, os.path.join(OUT, "events"),
                  {".json", ".geojson", ".csv"})
    log(f"events: {n} files")

    # ---------------------------------------------------------------- layers
    n = copy_tree(LAYERS, os.path.join(OUT, "layers"),
                  {".png", ".geojson", ".json"})
    log(f"layers: {n} files")

    # ------------------------------------------------------------ validation
    n = copy_tree(VALIDATION, os.path.join(OUT, "validation"), {".json"})
    log(f"validation: {n} files")

    # ------------------------------------------------------------------ docs
    doc_index = []
    os.makedirs(os.path.join(OUT, "docs"), exist_ok=True)
    for key, fn in DOC_KEYS.items():
        sp = os.path.join(DOCS, fn)
        if not os.path.exists(sp):
            continue
        shutil.copy2(sp, os.path.join(OUT, "docs", f"{key}.md"))
        doc_index.append({"key": key, "file": fn, "bytes": os.path.getsize(sp)})
    write(os.path.join(OUT, "docs", "index.json"), {"docs": doc_index})
    log(f"docs: {len(doc_index)} files")

    # ---------------------------------------------------------------- config
    try:
        import yaml
        cfg = yaml.safe_load(
            open(os.path.join(ROOT, "config", "project.yaml"), encoding="utf-8"))
        write(os.path.join(OUT, "config.json"), cfg)
        log("config.json written")
    except Exception as e:                                     # noqa: BLE001
        log(f"config skipped: {e}")

    # ---------------------------------------------------------------- health
    write(os.path.join(OUT, "health.json"),
          {"status": "ok", "service": "blueban-813", "version": "0.1.0",
           "mode": "static"})

    # ---------------------------------------------------------------- layers
    rb_path = os.path.join(LAYERS, "raster_bounds.json")
    if os.path.exists(rb_path):
        rb = read(rb_path)
        avail = {}
        for key, (fn, kind, label) in LAYER_FILES.items():
            if os.path.exists(os.path.join(LAYERS, fn)):
                avail[key] = {
                    "kind": kind, "label": label,
                    "url": f"/pipeline/layers/{fn}",
                    "bounds_lonlat": rb["bounds_lonlat"] if kind == "raster" else None,
                }
        write(os.path.join(OUT, "layers", "index.json"),
              {"bounds_lonlat": rb["bounds_lonlat"], "grid": rb, "layers": avail})
        log(f"layers/index.json: {len(avail)} layers")
    else:
        log("WARNING: raster_bounds.json missing; the map will not load")

    # ---------------------------------------------------------------- status
    ev_index = os.path.join(EVENTS, "index.json")
    n_events = len(read(ev_index)["events"]) if os.path.exists(ev_index) else 0
    write(os.path.join(OUT, "status.json"), {
        "events_available": n_events,
        "mode": "static",
        "artefacts": {
            "event_index": os.path.exists(ev_index),
            "layers": os.path.exists(rb_path),
            "rgb": os.path.exists(os.path.join(LAYERS, "rgb_water.png")),
            "anomaly": os.path.exists(os.path.join(LAYERS, "anomaly.png")),
            "hyperspectral_lift": os.path.exists(
                os.path.join(VALIDATION, "hyperspectral_lift.json")),
            "detectability_lift": os.path.exists(
                os.path.join(VALIDATION, "detectability_lift_hard.json")),
            "simulator_validation": os.path.exists(
                os.path.join(VALIDATION, "simulator_validation.json")),
            "temporal_baseline": os.path.exists(
                os.path.join(VALIDATION, "s2_baseline_report.json")),
        },
        "data_policy": {
            "real_813_data_used": False,
            "813_status": "SIMULATED from Planet Tanager-1",
            "in_situ_available": False,
            "note": "Satellite 813 is incubation-only for this programme phase. "
                    "See docs/813_PRODUCT_NOTES.md.",
        },
        "write_endpoints": False,
        "write_note": "Static deployment. Asset registration is unavailable; "
                      "run the FastAPI service locally to persist assets.",
    })
    log(f"status.json: {n_events} event(s)")

    # ------------------------------------------------------------ validation
    bundle = {}
    for key, fn in [
        ("simulator_validation", "simulator_validation.json"),
        ("olci_retrieval_ablation", "hyperspectral_lift.json"),
        ("detectability_hard", "detectability_lift_hard.json"),
        ("detectability_easy", "detectability_lift_easy.json"),
        ("temporal_baseline", "s2_baseline_report.json"),
    ]:
        p = os.path.join(VALIDATION, fn)
        if os.path.exists(p):
            bundle[key] = read(p)

    if bundle:
        # Reuse the API's own summariser so both modes produce byte-identical
        # summaries rather than two implementations that can drift apart.
        from services.api.main import _validation_summary
        bundle["summary"] = _validation_summary(bundle)
        write(os.path.join(OUT, "validation", "index.json"), bundle)
        write(os.path.join(OUT, "validation", "lift.json"), bundle["summary"])
        log("validation/index.json + lift.json written")
    else:
        log("WARNING: no validation artefacts found")

    # ---------------------------------------------------------------- assets
    from pipeline import exposure as EX
    assets = []
    if n_events:
        e = read(os.path.join(EVENTS, f"{read(ev_index)['events'][0]['event_id']}.json"))
        assets = [x["asset"] for x in e.get("exposure", [])]
    write(os.path.join(OUT, "assets.json"), {
        "assets": assets,
        "types": EX.ASSET_TYPES,
        "policy": "Operator-configured only. No infrastructure coordinates are "
                  "bundled with this software.",
    })
    log(f"assets.json: {len(assets)} demonstration assets")

    # -------------------------------------------------------------- manifest
    total = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fs in os.walk(OUT) for f in fs)
    write(os.path.join(OUT, "manifest.json"), {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bytes": total,
        "note": "Generated by scripts/build_static_site.py from outputs/. "
                "Do not edit by hand.",
    })
    print(f"\nStatic bundle: {total/1e6:.2f} MB at "
          f"{os.path.relpath(OUT, ROOT).replace(os.sep, '/')}")
    print("Next: bash scripts/deploy_cloudflare.sh   (or build manually:")
    print("  cd apps/web && BLUEBAN_STATIC=1 NEXT_PUBLIC_DATA_MODE=static npx next build)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
