"""Bake pipeline artefacts into the web app for the static deployment.

The hosted BLUEBAN 813 is a static site (Cloudflare Pages). Everything the
interface reads is copied here from ``outputs/`` and ``config/``:

    apps/web/public/pipeline/
      workspace/seed.json        incidents, models, labels, AOIs, assets (the
                                 in-browser workspace initialises from this)
      layers/<incident>/*.png    map layers per incident (+ annaba/ legacy)
      watch/<AOI>.json           slimmed WATCH time series per AOI
      registers/*.geojson        assets, monitoring stations
      validation/*.json          validation results
      cube/*                     display-ready spectral cube assets
      docs/*.md + index.json     documentation shown in the Data screen
      status.json                data policy and freshness

Usage: python scripts/build_static_site.py
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "apps", "web", "public", "pipeline")

DOC_KEYS = {
    "mentor-revamp-audit": "MENTOR_REVAMP_AUDIT.md",
    "authenticated-data-audit": "AUTHENTICATED_DATA_AUDIT.md",
    "public-uae-data": "PUBLIC_UAE_DATA.md",
    "uae-event-register": "UAE_EVENT_REGISTER.md",
    "uae-aoi-tournament": "UAE_AOI_TOURNAMENT.md",
    "813-product-notes": "813_PRODUCT_NOTES.md",
    "methodology": "METHODOLOGY.md",
    "validation-report": "VALIDATION_REPORT.md",
    "limitations": "LIMITATIONS.md",
    "data-lineage": "DATA_LINEAGE.md",
    "business-case": "BUSINESS_CASE.md",
    "judging-matrix": "JUDGING_MATRIX.md",
    "roadmap": "ROADMAP.md",
    "archive-data-access-audit-2026-09-15": "archive/DATA_ACCESS_AUDIT_2026-09-15.md",
    "archive-official-resource-audit-2026-09-17": "archive/OFFICIAL_RESOURCE_AUDIT_2026-09-17.md",
    "archive-aoi-selection-tanager": "archive/AOI_SELECTION_TANAGER_2026-09-15.md",
}


#: Every external dataset the product touches: provider, licence, role, status.
DATA_SOURCES = [
    {"name": "Sentinel-2 MSI L2A", "provider": "ESA Copernicus via Microsoft Planetary Computer",
     "licence": "Copernicus: free, full and open", "role": "Primary detection sensor (10/20/60 m, 2-5 day revisit)",
     "status": "USED", "url": "https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a"},
    {"name": "Sentinel-3 OLCI WFR L2", "provider": "EUMETSAT / ESA Copernicus via Microsoft Planetary Computer",
     "licence": "Copernicus: free, full and open",
     "role": "Cross-sensor reference (CHL_NN, TSM_NN; model products, never in-situ truth) and wide-area context",
     "status": "USED (archive ends 2026-02-23)", "url": "https://planetarycomputer.microsoft.com/dataset/sentinel-3-olci-wfr-l2-netcdf"},
    {"name": "Planet Tanager-1 hyperspectral", "provider": "Planet Labs PBC (open STAC)", "licence": "CC-BY-4.0",
     "role": "Source spectra for the SIMULATED 813 product and the 813 ablation (Gulf of Annaba)",
     "status": "USED for simulation; UAE (Tarif) scene awaiting download approval", "url": "https://www.planet.com/data/stac/"},
    {"name": "Satellite 813 products", "provider": "Arab Youth Space Hackathon / partners", "licence": "n/a",
     "role": "Target sensor", "status": "NOT ACCESSIBLE (authenticated audit, 30 Sep 2026)", "url": None},
    {"name": "ERA5 hourly 10 m wind", "provider": "ECMWF / Copernicus C3S via the Open-Meteo archive API",
     "licence": "Copernicus licence (attribution)", "role": "Wind-only drift SCENARIO (not a hydrodynamic forecast)",
     "status": "USED", "url": "https://open-meteo.com/en/docs/historical-weather-api"},
    {"name": "OpenStreetMap coastal assets", "provider": "OpenStreetMap contributors (Overpass extract)", "licence": "ODbL",
     "role": "Desalination plants, ports, power plants, beaches for exposure", "status": "USED (120 assets)",
     "url": "https://www.openstreetmap.org/copyright"},
    {"name": "EAD marine monitoring locations", "provider": "Abu Dhabi Spatial Data Infrastructure (EAD layers 170/171)",
     "licence": "ADSDI open data", "role": "Station LOCATIONS only; no measurement values are public",
     "status": "USED (50 locations)", "url": None},
    {"name": "Sentinel-2 cloudless 2021 basemap", "provider": "EOX IT Services GmbH (contains modified Copernicus data)",
     "licence": "CC BY-NC-SA 4.0", "role": "Basemap only; never analysed", "status": "DISPLAY", "url": "https://s2maps.eu"},
    {"name": "Terrain tiles (terrarium)", "provider": "AWS Open Data / Mapzen", "licence": "various open (see provider)",
     "role": "3D relief only", "status": "DISPLAY", "url": "https://registry.opendata.aws/terrain-tiles/"},
    {"name": "Hackathon platform datasets and gIQ", "provider": "Arab Youth Space Hackathon Cockpit; gIQ",
     "licence": "restricted", "role": "Audited for UAE water data", "status": "NOTHING USABLE FOR UAE WATER (see audit)",
     "url": None},
]


def lineage() -> dict:
    """Counts of what each pipeline stage produced, read from outputs/."""
    def jl(p):
        p = os.path.join(ROOT, p)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
    watch = [jl(os.path.relpath(p, ROOT)) for p in glob.glob(os.path.join(ROOT, "outputs", "watch", "*.json"))]
    det = [jl(os.path.relpath(p, ROOT)) for p in glob.glob(os.path.join(ROOT, "outputs", "detect", "*.json"))]
    labels = jl("outputs/labels/seed_labels.json") or {}
    incs = glob.glob(os.path.join(ROOT, "outputs", "incidents", "BB-*.json"))
    olci = glob.glob(os.path.join(ROOT, "data", "cache", "olci", "*", "*.npz"))
    return {
        "watch": {"aois": len(watch), "datatakes": sum(w.get("n_datatakes", 0) for w in watch),
                  "ok": sum(w.get("n_ok", 0) for w in watch)},
        "detect": {"aois": len(det), "acquisitions": sum(d.get("n_acquisitions", 0) for d in det),
                   "pixel_level": sum((d.get("two_stage") or {}).get("n_pixel_level", 0) for d in det),
                   "candidates": sum(len(d.get("candidates", [])) for d in det)},
        "olci_extracts": len(olci),
        "labels": {"n": labels.get("n", 0), "validation": labels.get("n_validation", 0),
                   "stats": labels.get("stats", {})},
        "incidents": sorted(os.path.basename(p)[:-5] for p in incs),
    }


def log(m):
    print(f"  {m}", flush=True)


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), default=str)


def copy(src, dst):
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def slim_watch(ts: dict) -> dict:
    """Keep only what the WATCH screen plots."""
    keep_f = ("NDCI", "MCI", "FAI", "TUR_NECHAD2016", "HUE_ANGLE", "CDOM_RATIO")
    rows = []
    for r in ts["rows"]:
        if "error" in r:
            rows.append({"date": r["date"], "error": True})
            continue
        z = r.get("all") or {}
        rows.append({"date": r["date"], "datetime": r.get("datetime"), "platform": r.get("platform"),
                     "orbit": r.get("relative_orbit"), "n_water": z.get("n_water"),
                     "cloud": round(r.get("cloud_fraction_of_valid") or 0, 4),
                     "glint": (r.get("quality") or {}).get("glint_or_float_px"),
                     "f": {k: ({"p50": round(z[k]["p50"], 5), "p95": round(z[k]["p95"], 5)}
                               if z.get(k) else None) for k in keep_f}})
    return {"aoi_id": ts["aoi_id"], "bbox": ts["bbox"], "window": ts["window"],
            "resolution_m": ts["grid"]["resolution_m"], "n_datatakes": ts["n_datatakes"],
            "n_ok": ts["n_ok"], "rows": rows, "generated_utc": ts["generated_utc"]}


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)

    seed = os.path.join(ROOT, "outputs", "workspace", "seed.json")
    if not copy(seed, os.path.join(OUT, "workspace", "seed.json")):
        raise SystemExit("outputs/workspace/seed.json missing: run scripts/build_workspace_seed.py")
    log("workspace seed")

    n = 0
    for fn in ("rgb_water.png", "anomaly.png", "ndci.png", "turbidity.png", "raster_bounds.json",
               "event_polygons.geojson", "water_mask.geojson", "sensor_spec_813.json"):
        n += copy(os.path.join(ROOT, "outputs", "layers", fn), os.path.join(OUT, "layers", "annaba", fn))
    for d in glob.glob(os.path.join(ROOT, "outputs", "incidents", "BB-*")):
        if os.path.isdir(d):
            for fp in glob.glob(os.path.join(d, "*")):
                n += copy(fp, os.path.join(OUT, "layers", os.path.basename(d), os.path.basename(fp)))
    log(f"layers: {n} files")

    n = 0
    for fp in glob.glob(os.path.join(ROOT, "outputs", "watch", "*.json")):
        with open(fp, encoding="utf-8") as f:
            write(os.path.join(OUT, "watch", os.path.basename(fp)), slim_watch(json.load(f)))
        n += 1
    for fp in glob.glob(os.path.join(ROOT, "outputs", "detect", "*.json")):
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
        write(os.path.join(OUT, "detect", os.path.basename(fp)),
              {k: d[k] for k in ("aoi_id", "resolution_m", "thresholds", "n_acquisitions", "dates")
               if k in d})
        n += 1
    log(f"watch/detect series: {n}")

    for name in ("assets_uae.geojson", "stations_ead.geojson", "aois_uae.yaml", "tle_eo.json"):
        copy(os.path.join(ROOT, "config", name), os.path.join(OUT, "registers", name))
    copy(os.path.join(ROOT, "outputs", "aoi", "census.json"), os.path.join(OUT, "registers", "census.json"))

    n = 0
    for fp in glob.glob(os.path.join(ROOT, "outputs", "validation", "*.json")):
        n += copy(fp, os.path.join(OUT, "validation", os.path.basename(fp)))
    for fp in glob.glob(os.path.join(ROOT, "outputs", "cube", "*")):
        n += copy(fp, os.path.join(OUT, "cube", os.path.basename(fp)))
    log(f"validation + cube: {n}")

    idx = []
    for key, fn in DOC_KEYS.items():
        sp = os.path.join(ROOT, "docs", fn)
        if copy(sp, os.path.join(OUT, "docs", f"{key}.md")):
            idx.append({"key": key, "file": fn, "bytes": os.path.getsize(sp)})
    write(os.path.join(OUT, "docs", "index.json"), {"docs": idx})
    log(f"docs: {len(idx)}")

    status = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "sources": DATA_SOURCES, "lineage": lineage(),
              "data_policy": {
                  "real_813_data_used": False,
                  "813_status": "SIMULATED (no Satellite 813 product accessible to the team; "
                                "see docs/AUTHENTICATED_DATA_AUDIT.md)",
                  "in_situ_available": False,
                  "quantification": "PROXY / GENERIC_CALIBRATION only; no calibrated concentrations",
                  "olci_archive_end": "2026-02-23 (Planetary Computer)"}}
    write(os.path.join(OUT, "status.json"), status)
    log(f"done in {time.time() - t0:.1f}s -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
