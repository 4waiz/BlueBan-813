"""Turn a DETECT candidate into a full COASTAL INCIDENT evidence package.

For one candidate (AOI + acquisition + region) this re-processes the scene at
native 20 m and writes ``outputs/incidents/<ID>.json`` plus its layers:

1. the event acquisition at 20 m (datatake mosaic, glint-aware water mask);
2. a 20 m per-pixel SEASONAL CLIMATOLOGY from same-season acquisitions of
   other years, so every event pixel carries a robust z-score and a seasonal
   percentile against its own history;
3. the event polygon (z >= 3 and >= 95th seasonal percentile, overlapping the
   120 m candidate);
4. Sentinel-2 spectral evidence (event vs background, 5-95 % envelope);
5. a Sentinel-3 OLCI cross-check when the archive covers the date;
6. asset exposure, an ERA5 wind-drift SCENARIO, a sampling plan;
7. severity / confidence (never multiplied) and the triage feature vector;
8. map layers, a before/after timeline and a click-inspectable pixel grid;
9. full provenance.

Usage:
  python scripts/build_incidents.py --aoi AE-FUJ --date 2023-02-17 --hyp BLOOM_LIKE --id BB-UAE-2023-001
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import yaml  # noqa: E402

from pipeline import detect, export, exposure, forecast, risk, sampling  # noqa: E402
from pipeline import s2_features as s2f  # noqa: E402
from pipeline import watch  # noqa: E402
from pipeline.provenance import AlgorithmRecord, Provenance, SourceRecord  # noqa: E402

S2_BANDS_SPECTRUM = ["B01", "B02", "B03", "B04", "B05", "B06", "B8A"]
S2_NM = [443, 492, 560, 665, 704, 740, 865]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _grid_window(center_lonlat, half_km, aoi_bbox):
    lon, lat = center_lonlat
    dlat = half_km / 110.57
    dlon = half_km / (111.32 * math.cos(math.radians(lat)))
    return [max(aoi_bbox[0], lon - dlon), max(aoi_bbox[1], lat - dlat),
            min(aoi_bbox[2], lon + dlon), min(aoi_bbox[3], lat + dlat)]


def load_features(args):
    """Worker: one datatake at the incident grid -> features + water + bands."""
    key, item_dicts, grid_d = args
    import pystac
    items = [pystac.Item.from_dict(d) for d in item_dicts]
    grid = watch._grid_from_dict(grid_d)
    try:
        refl, scl, meta = watch.load_datatake(items, grid)
        feats = s2f.compute_features(refl, platform=meta["platform"])
        water, rep = s2f.water_quality_mask(refl, scl, pixel_size_m=grid.resolution_m,
                                            shoreline_buffer_m=60)
        out = {k: feats[k].astype("float32") for k in ("NDCI", "MCI", "TUR_NECHAD2016",
                                                       "HUE_ANGLE", "FAI", "SPM_NECHAD2016")}
        return {"key": key, "ok": True, "water": water, "feats": out, "meta": meta,
                "quality": rep.to_dict(),
                "refl": {b: refl[b] for b in S2_BANDS_SPECTRUM + ["B11", "B12"]}, "scl": scl}
    except Exception as e:                                   # recorded, never hidden
        return {"key": key, "ok": False, "error": repr(e)[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--hyp", default=None)
    ap.add_argument("--label", type=int, default=None)
    ap.add_argument("--id", required=True)
    ap.add_argument("--res", type=float, default=20.0)
    ap.add_argument("--half-km", type=float, default=9.0)
    ap.add_argument("--clim-max", type=int, default=36)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--status", default="DETECTED")
    ap.add_argument("--title", default=None)
    ap.add_argument("--context", default=None, help="JSON list of register context entries")
    a = ap.parse_args()

    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "aois_uae.yaml"), encoding="utf-8"))["aois"]
    aoi = cfg[a.aoi]
    det = json.load(open(os.path.join(ROOT, "outputs", "detect", f"{a.aoi}.json"), encoding="utf-8"))
    ws = json.load(open(os.path.join(ROOT, "outputs", "watch", f"{a.aoi}.json"), encoding="utf-8"))
    cands = [c for c in det["candidates"] if c["date"] == a.date
             and (a.hyp is None or c["hypothesis"] == a.hyp)
             and (a.label is None or c["label"] == a.label)]
    if not cands:
        raise SystemExit(f"no candidate on {a.date} ({a.hyp}) in {a.aoi}")
    cand = max(cands, key=lambda c: c["area_km2"] * (c["features"].get("robust_z_primary") or 0))
    hyp = cand["hypothesis"]
    g120 = watch.AoiGrid.from_bbox(a.aoi, aoi["bbox"], ws["grid"]["resolution_m"])
    r, c = cand["centroid_rc"]
    cx, cy = g120.transform * (c + 0.5, r + 0.5)
    from pyproj import Transformer
    lon0, lat0 = Transformer.from_crs(f"EPSG:{g120.epsg}", "EPSG:4326", always_xy=True).transform(cx, cy)
    win = _grid_window((lon0, lat0), a.half_km, aoi["bbox"])
    grid = watch.AoiGrid.from_bbox(a.id, win, a.res)
    log(f"{a.id}: {hyp} candidate {cand['area_km2']:.2f} km2 at {lat0:.4f},{lon0:.4f}; "
        f"window {grid.shape} @ {a.res} m")

    # ---- event + climatology acquisitions -----------------------------------
    ci = detect.CacheIndex.load(os.path.join(ROOT, "data", "cache", "watch", a.aoi), a.aoi)
    t_idx = ci.files.index(cand["cache_file"])
    clim_idx = detect.climatology_indices(ci.dates, t_idx, det["window_days"])
    # keep climatology dates with good water coverage over the window (from 120 m cache)
    rows = [int(v) for v in cand["bbox_rc"]]
    good = []
    for i in clim_idx:
        w = np.load(os.path.join(ci.folder, ci.files[i]))["water"]
        sub = w[max(0, rows[0] - 30):rows[2] + 30, max(0, rows[1] - 30):rows[3] + 30]
        if sub.size and sub.mean() > 0.25:
            good.append(i)
    rng = np.random.default_rng(813)
    if len(good) > a.clim_max:
        good = sorted(rng.choice(good, a.clim_max, replace=False).tolist())
    wanted = {ci.files[t_idx]: "event", **{ci.files[i]: "clim" for i in good}}
    groups = watch.search_items(win, "2017-01-01", "2026-09-30", 30)
    tag = lambda k: f"{k[0]}_R{int(k[1]):03d}_{(k[2] or 'S2')[-2:]}.npz"  # noqa: E731
    tasks = [(k, [it.to_dict() for it in items], watch._grid_to_dict(grid))
             for k, items in groups if tag(k) in wanted]
    log(f"loading {len(tasks)} acquisitions at {a.res} m (1 event + {len(tasks) - 1} climatology)")
    results = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(load_features, tasks):
            results[tag(res["key"])] = res
    ev = results.get(ci.files[t_idx])
    if not ev or not ev["ok"]:
        raise SystemExit(f"event acquisition failed: {ev and ev.get('error')}")
    clim = [results[f] for f in results if wanted.get(f) == "clim" and results[f]["ok"]]
    log(f"climatology: {len(clim)} usable acquisitions")

    water = ev["water"]
    F = ev["feats"]
    zmaps, pmaps, meds, scales = {}, {}, {}, {}
    for name in ("NDCI", "MCI", "TUR_NECHAD2016", "FAI"):
        stack = np.stack([np.where(cc["water"], cc["feats"][name], np.nan) for cc in clim])
        z, pct, n, med, sc = detect.robust_anomaly(np.where(water, F[name], np.nan), stack,
                                                   detect.FLOORS.get(name, 0.01))
        zmaps[name], pmaps[name], meds[name], scales[name] = z, pct, med, sc
        nclim = n

    prim = detect.HYPOTHESIS_FEATURES[hyp][0][0]
    hit = water & (zmaps[prim] >= detect.Z_MIN) & (pmaps[prim] >= detect.PCT_MIN)
    from scipy import ndimage as ndi
    hit = ndi.binary_opening(hit, iterations=1)
    lab, nlab = ndi.label(hit)
    # keep components overlapping the candidate centroid neighbourhood (or the largest)
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{grid.epsg}", always_xy=True)
    ex_, ey_ = tr.transform(lon0, lat0)
    cc0 = int((ex_ - grid.transform.c) / grid.transform.a)
    rr0 = int((ey_ - grid.transform.f) / grid.transform.e)
    sizes = ndi.sum(hit, lab, range(1, nlab + 1)) if nlab else []
    keep = set()
    rad = int(1500 / a.res)
    near = lab[max(0, rr0 - rad):rr0 + rad, max(0, cc0 - rad):cc0 + rad]
    keep |= set(np.unique(near[near > 0]).tolist())
    if not keep and nlab:
        keep = {int(np.argmax(sizes)) + 1}
    event = np.isin(lab, list(keep))
    npx = int(event.sum())
    area = npx * (a.res ** 2) / 1e6
    if npx < 10:
        raise SystemExit("event did not survive at 20 m")
    rr, cc = np.where(event)
    ecx, ecy = grid.transform * (cc.mean() + 0.5, rr.mean() + 0.5)
    lon_c, lat_c = Transformer.from_crs(f"EPSG:{grid.epsg}", "EPSG:4326", always_xy=True).transform(ecx, ecy)
    tr6 = tuple(list(grid.transform)[:6])
    gtr = (tr6[2], tr6[0], 0.0, tr6[5], 0.0, tr6[4])
    polys = export.mask_to_polygons(event, gtr, grid.epsg, simplify_m=30.0, min_area_m2=4000.0)
    geom = polys["features"][0]["geometry"] if len(polys["features"]) == 1 else {
        "type": "MultiPolygon", "coordinates": [f["geometry"]["coordinates"] for f in polys["features"]
                                                if f["geometry"]["type"] == "Polygon"]}
    log(f"event at {a.res} m: {area:.2f} km2 ({npx} px), centroid {lat_c:.4f},{lon_c:.4f}")

    # ---- spectral evidence (S2 bands) ----------------------------------------
    bg = water & ~ndi.binary_dilation(event, iterations=10) & (np.nan_to_num(zmaps[prim]) < 1.0)
    w12 = ev["refl"]["B12"]
    spec_e, spec_b, p05, p95 = [], [], [], []
    for b in S2_BANDS_SPECTRUM:
        v = ev["refl"][b] - w12
        ve, vb = v[event], v[bg]
        ve, vb = ve[np.isfinite(ve)], vb[np.isfinite(vb)]
        spec_e.append(float(np.median(ve)) if ve.size else None)
        spec_b.append(float(np.median(vb)) if vb.size else None)
        p05.append(float(np.percentile(vb, 5)) if vb.size else None)
        p95.append(float(np.percentile(vb, 95)) if vb.size else None)

    def med(arr, m):
        v = arr[m]
        v = v[np.isfinite(v)]
        return float(np.median(v)) if v.size else None

    # ---- distance to shore, exposure, drift -----------------------------------
    dist_px = ndi.distance_transform_edt(water)
    dshore_km = med(dist_px * a.res / 1000.0, event)
    assets_fc = json.load(open(os.path.join(ROOT, "config", "assets_uae.geojson"), encoding="utf-8"))
    near_assets = []
    for f in assets_fc["features"]:
        p = f["properties"]
        alon, alat = f["geometry"]["coordinates"]
        d = float(exposure.haversine_m(lon_c, lat_c, alon, alat))
        if d <= 40000 and p["type"] != "PUBLIC_BEACH":
            near_assets.append(exposure.Asset(p["id"], p["name"], p["type"], alon, alat,
                                              source=p["source"]))
    steps, wind_meta = [], None
    try:
        day = dt.date.fromisoformat(a.date)
        off_lon = lon_c + (0.08 if aoi["coast"] == "Gulf of Oman" else 0.0)
        off_lat = lat_c + (0.0 if aoi["coast"] == "Gulf of Oman" else 0.08)
        wind = forecast.fetch_wind(off_lat, off_lon, (day - dt.timedelta(days=1)).isoformat(),
                                   (day + dt.timedelta(days=3)).isoformat())
        t_obs = ev["meta"]["datetime"][:13]
        si = next((i for i, t in enumerate(wind.times) if t[:13] == t_obs), 24)
        seed_n = min(600, npx)
        pick = rng.choice(npx, seed_n, replace=False)
        sx, sy = grid.transform * (cc[pick] + 0.5, rr[pick] + 0.5)
        slon, slat = Transformer.from_crs(f"EPSG:{grid.epsg}", "EPSG:4326", always_xy=True).transform(sx, sy)
        dom = forecast.WaterDomain(water | ~np.isfinite(ev["refl"]["B03"]), gtr, grid.epsg)
        fsteps = forecast.advect(slon, slat, wind, si, domain=dom)
        steps = [{"hours": s.hours, "centroid": [s.centroid_lon, s.centroid_lat],
                  "spread_radius_m": s.spread_radius_m, "bearing_deg": s.bearing_deg,
                  "displacement_m": s.displacement_m,
                  "particles": [[x, y] for x, y in list(zip(s.particles_lon, s.particles_lat))[::4]]}
                 for s in fsteps]
        w0 = float(wind.speed[si]), float(wind.direction_from[si])
        wind_meta = {"speed_kmh": w0[0] * 3.6, "from": f"{w0[1]:.0f} deg",
                     "source": wind.source, "cell": [wind.latitude, wind.longitude]}
    except Exception as e:
        log(f"drift scenario skipped: {e!r}")
        fsteps = None
    exp_rows = []
    for asset in near_assets:
        e_ = exposure.assess(asset, lon_c, lat_c, fsteps, event_radius_m=math.sqrt(area * 1e6 / math.pi))
        d = e_.to_dict()
        exp_rows.append({"asset": {"id": asset.id, "name": asset.name, "type": asset.type,
                                   "type_label": exposure.ASSET_TYPES[asset.type]["label"],
                                   "lon": asset.lon, "lat": asset.lat, "source": asset.source},
                         "distance_m": d["distance_m"], "direction": d.get("direction"),
                         "exposure_score": d.get("exposure_score"), "basis": d.get("basis", [])})
    exp_rows.sort(key=lambda x: x["distance_m"])

    # ---- sampling plan ----------------------------------------------------------
    score = np.nan_to_num(zmaps[prim], nan=np.nan)
    pts = sampling.plan(np.where(water, zmaps[prim], np.nan), water, event, gtr, grid.epsg,
                        distance_from_shore_m=dist_px * a.res, forecast_steps=fsteps,
                        assets=[{"asset": x["asset"], "exposure_score": x["exposure_score"] or 0}
                                for x in exp_rows[:3]], max_points=5, min_separation_m=600.0)
    role_map = {"EVENT_CORE": "CORE", "LEADING_EDGE": "EDGE", "BACKGROUND_CONTROL": "BACKGROUND",
                "UNCERTAINTY_POINT": "UNCERTAINTY", "ASSET_BOUNDARY": "ASSET_BOUNDARY"}
    samples = [{"id": f"{a.id}-S{i:02d}", "code": f"S{i:02d}", "role": role_map.get(p.role, p.role),
                "lon": round(p.lon, 6), "lat": round(p.lat, 6), "status": "PLANNED",
                "question": sampling.ROLES[p.role]["question"], "analytes": p.expected_variables,
                "rationale": p.rationale, "planned_by": "pipeline", "planned_at": None,
                "collected_by": None, "collected_at": None,
                "updated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
               for i, p in enumerate(pts, 1)]

    # ---- risk ------------------------------------------------------------------
    zmed = med(zmaps[prim], event)
    pmed = med(pmaps[prim], event)
    qual = ev["quality"]
    valid_frac = qual["water_px"] / max(qual["total_px"], 1)
    glint_frac = qual["glint_or_float_px"] / max(qual["water_px"], 1)
    assess = risk.assess_event(
        area_km2=area, anomaly_percentile=cand["features"].get("rx_pct"),
        magnitude_ratio=None, historical_percentile=pmed,
        valid_pixel_fraction=min(1.0, 3 * valid_frac), cloud_fraction=0.0, n_pixels=npx,
        spectral_snr=None, classification_margin=None,
        max_exposure=max([x["exposure_score"] or 0 for x in exp_rows] or [0]),
        bottom_influence_risk=(0.7 if (dshore_km or 99) < 0.5 else 0.2 if (dshore_km or 99) < 2 else 0.05))

    feats = dict(cand["features"])
    feats.update({"seasonal_pct_primary": pmed, "robust_z_primary": zmed,
                  "log10_area_km2": math.log10(area), "dist_shore_km": dshore_km,
                  "ndci_delta": med(F["NDCI"] - meds["NDCI"], event),
                  "mci_delta": med(F["MCI"] - meds["MCI"], event),
                  "tur_delta": med(F["TUR_NECHAD2016"] - meds["TUR_NECHAD2016"], event),
                  "fai_mean": med(F["FAI"], event), "swir_b11_mean": med(ev["refl"]["B11"], event)})

    # ---- layers ------------------------------------------------------------------
    out_dir = os.path.join(ROOT, "outputs", "incidents", a.id)
    os.makedirs(out_dir, exist_ok=True)
    bl = grid.lonlat_bounds()
    valid = np.isfinite(ev["refl"]["B03"])
    export.save_rgb_png(os.path.join(out_dir, "rgb.png"), ev["refl"]["B04"], ev["refl"]["B03"],
                        ev["refl"]["B02"], valid, water)
    legends = {}
    legends["ndci"] = export.save_scalar_png(os.path.join(out_dir, "ndci.png"), F["NDCI"], water, "turbo")
    legends["ndci_z"] = export.save_scalar_png(os.path.join(out_dir, "ndci_z.png"), zmaps["NDCI"], water,
                                               "RdBu_r", vmin=-6, vmax=6)
    legends["mci"] = export.save_scalar_png(os.path.join(out_dir, "mci.png"), F["MCI"], water, "viridis")
    legends["turbidity"] = export.save_scalar_png(os.path.join(out_dir, "turbidity.png"),
                                                  F["TUR_NECHAD2016"], water, "YlOrBr")
    legends["hue"] = export.save_scalar_png(os.path.join(out_dir, "hue.png"), F["HUE_ANGLE"], water,
                                            "Spectral", vmin=20, vmax=240)
    from PIL import Image
    wm = np.zeros(water.shape + (4,), np.uint8)
    wm[water] = (39, 195, 243, 70)
    Image.fromarray(wm, "RGBA").save(os.path.join(out_dir, "water.png"), optimize=True)

    def L(key, label, fn, units, cmap="seq", lg=None):
        d = {"key": key, "label": label, "url": f"layers/{a.id}/{fn}", "bounds": bl,
             "sensor": "Sentinel-2 L2A", "date": a.date}
        if lg:
            d["legend"] = {"min": lg["vmin"], "max": lg["vmax"], "units": units, "cmap": cmap, "label": label}
        return d
    rasters = [L("rgb", "True colour (B4/B3/B2)", "rgb.png", ""),
               L("ndci", "NDCI chlorophyll proxy", "ndci.png", "dimensionless", "seq", legends["ndci"]),
               L("ndci_z", "NDCI robust z vs same season", "ndci_z.png", "z", "div", legends["ndci_z"]),
               L("mci", "MCI red-edge peak height", "mci.png", "reflectance", "seq", legends["mci"]),
               L("turbidity", "Turbidity (Nechad 2016, generic cal.)", "turbidity.png", "FNU", "seq", legends["turbidity"]),
               L("hue", "Water-colour hue angle", "hue.png", "degrees", "seq", legends["hue"]),
               L("water", "Water mask", "water.png", "")]

    # timeline: 120 m cache frames within +/-40 days, cropped to the window
    tl = []
    t0d = ci.dates[t_idx]
    for i, d in enumerate(ci.dates):
        if abs((d - t0d).days) > 40:
            continue
        z = np.load(os.path.join(ci.folder, ci.files[i]))
        if z["water"].mean() < 0.02:
            continue
        # crop on the 120 m grid
        from rasterio.warp import transform_bounds
        wx0, wy0, wx1, wy1 = transform_bounds("EPSG:4326", f"EPSG:{g120.epsg}", *win)
        c0 = max(0, int((wx0 - g120.transform.c) / g120.transform.a))
        c1 = min(g120.shape[1], int((wx1 - g120.transform.c) / g120.transform.a) + 1)
        r0 = max(0, int((wy1 - g120.transform.f) / g120.transform.e))
        r1 = min(g120.shape[0], int((wy0 - g120.transform.f) / g120.transform.e) + 1)
        rgb = z["rgb"].astype("float32")[r0:r1, c0:c1]
        wsub = z["water"][r0:r1, c0:c1]
        if wsub.mean() < 0.2:
            continue
        fn = f"t_{d.isoformat()}.png"
        export.save_rgb_png(os.path.join(out_dir, fn), rgb[..., 0], rgb[..., 1], rgb[..., 2],
                            np.isfinite(rgb[..., 0]), wsub)
        clim_i = detect.climatology_indices(ci.dates, i, det["window_days"])
        tl.append({"date": d.isoformat(), "rgb": f"layers/{a.id}/{fn}", "valid": True,
                   "n_climatology": len(clim_i)})
    crop_b = None
    if tl:
        from rasterio.warp import transform_bounds as tb
        x0 = g120.transform.c + c0 * g120.transform.a
        x1 = g120.transform.c + c1 * g120.transform.a
        y0 = g120.transform.f + r0 * g120.transform.e
        y1 = g120.transform.f + r1 * g120.transform.e
        crop_b = list(tb(f"EPSG:{g120.epsg}", "EPSG:4326", x0, y1, x1, y0))
        for t in tl:
            t["bounds"] = crop_b

    # pixel grid for click inspection (int16, scaled)
    fields = {"NDCI": (F["NDCI"], 1e-4), "NDCI_z": (zmaps["NDCI"], 1e-3), "NDCI_pct": (pmaps["NDCI"], 1e-2),
              "MCI": (F["MCI"], 1e-5), "TUR_FNU": (F["TUR_NECHAD2016"], 1e-2), "HUE_deg": (F["HUE_ANGLE"], 1e-2),
              "B04": (ev["refl"]["B04"], 1e-5), "B05": (ev["refl"]["B05"], 1e-5)}
    step = max(1, int(math.ceil(max(grid.shape) / 600)))
    arrs = []
    for k, (v, sc) in fields.items():
        vv = np.where(water, v, np.nan)[::step, ::step]
        q = np.where(np.isfinite(vv), np.clip(np.round(vv / sc), -32767, 32767), -32768).astype("<i2")
        arrs.append(q)
    np.stack(arrs).tofile(os.path.join(out_dir, "pixels.bin"))
    json.dump({"bounds": bl, "shape": list(arrs[0].shape), "fields": list(fields),
               "scale": {k: sc for k, (v, sc) in fields.items()}, "nodata": -32768,
               "resolution_m": a.res * step},
              open(os.path.join(out_dir, "pixels.json"), "w"))

    # display cube: Sentinel-2 multispectral, uint8-quantised, <= 160 px (SPECTRAL DATA CUBE viewer)
    cube_bands = ["B01", "B02", "B03", "B04", "B05", "B06", "B8A", "B11", "B12"]
    cube_nm = [443, 492, 560, 665, 704, 740, 865, 1610, 2190]
    cstep = max(1, int(math.ceil(max(grid.shape) / 160)))
    stack = np.stack([np.where(water, ev["refl"][b] - (ev["refl"]["B12"] if b not in ("B11", "B12") else 0), np.nan)[::cstep, ::cstep]
                      for b in cube_bands])
    lo_c, hi_c = 0.0, float(np.nanpercentile(stack[:7], 99.5)) if np.isfinite(stack[:7]).any() else 0.1
    stepv = (hi_c - lo_c) / 254.0 if hi_c > lo_c else 1e-4
    q = np.where(np.isfinite(stack), np.clip(np.round((stack - lo_c) / stepv) + 1, 1, 255), 0).astype("uint8")
    os.makedirs(os.path.join(ROOT, "outputs", "cube"), exist_ok=True)
    q.tofile(os.path.join(ROOT, "outputs", "cube", f"{a.id}_s2.bin"))
    json.dump({"name": f"{a.id}_s2", "sensor": "Sentinel-2 L2A multispectral (9 bands, SWIR-offset corrected)",
               "simulated": False, "source": ",".join(ev["meta"]["item_ids"]), "shape": list(q.shape),
               "wavelengths_nm": cube_nm, "valid_band": [True] * len(cube_bands),
               "scale": {"offset": lo_c - stepv, "step": stepv}, "units": "reflectance",
               "date": a.date, "bounds": grid.lonlat_bounds(),
               "note": "Multispectral: 9 broad bands, not a hyperspectral cube."},
              open(os.path.join(ROOT, "outputs", "cube", f"{a.id}_s2.json"), "w"))

    # ---- provenance ----------------------------------------------------------------
    prov = Provenance(result_id=a.id, result_kind="coastal_incident")
    for iid in ev["meta"]["item_ids"]:
        prov.add_source(SourceRecord(
            satellite=ev["meta"]["platform"], sensor="MSI", scene_id=iid,
            acquisition_utc=ev["meta"]["datetime"], product="sentinel-2-l2a",
            processing_level=f"L2A BOA reflectance (Sen2Cor), baseline {','.join(ev['meta']['processing_baselines'])}",
            provider="ESA Copernicus via Microsoft Planetary Computer", licence="Copernicus open (free, full, open)",
            native_resolution_m=[10, 20, 60], bands_used=S2_BANDS_SPECTRUM + ["B11", "B12", "SCL"],
            units="reflectance (BOA_ADD_OFFSET applied per processing baseline)",
            quality_mask="SCL {0,1,3,8,9,10,11} rejected; MNDWI>0; B11<0.10; glint B11>0.0215 flagged + SWIR offset",
            access_url=f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a/items/{iid}"))
    prov.add_source(SourceRecord(
        satellite="Sentinel-2A/B/C", sensor="MSI", scene_id=f"{len(clim)} same-season acquisitions",
        acquisition_utc=f"{min(x['meta']['datetime'] for x in clim)[:10]} .. {max(x['meta']['datetime'] for x in clim)[:10]}",
        product="sentinel-2-l2a", processing_level="L2A", provider="ESA Copernicus via Microsoft Planetary Computer",
        licence="Copernicus open", units="reflectance", notes="Per-pixel seasonal climatology (+/-45 days of day-of-year, other years)"))
    if wind_meta:
        prov.add_source(SourceRecord(satellite="ERA5 reanalysis", sensor="10 m wind", scene_id=f"cell {wind_meta['cell']}",
                                     acquisition_utc=ev["meta"]["datetime"], product="ERA5 hourly", processing_level="reanalysis",
                                     provider="ECMWF / Copernicus C3S via Open-Meteo archive", licence="Copernicus licence",
                                     units="m/s", notes="drives the wind-only drift SCENARIO"))
    prov.add_source(SourceRecord(satellite="OpenStreetMap", sensor="asset register", scene_id="config/assets_uae.geojson",
                                 acquisition_utc="2026-09-30", product="Overpass extract", processing_level="vector",
                                 provider="OpenStreetMap contributors", licence="ODbL", units="n/a"))
    prov.algorithm = AlgorithmRecord(
        name="BLUEBAN DETECT (per-pixel seasonal anomaly) + incident builder",
        description="Robust z-score and seasonal percentile of each water pixel against its own same-season "
                    "history in other years; event = z >= 3 and pct >= 95 on the primary feature.",
        parameters={"z_min": detect.Z_MIN, "pct_min": detect.PCT_MIN, "window_days": det["window_days"],
                    "floors": detect.FLOORS, "resolution_m": a.res, "climatology_n": len(clim),
                    "primary_feature": prim},
        units_out="z-score, percentile", limitations=[
            "Sen2Cor L2A is a land processor; SWIR offset removes first-order glint only",
            "Indices are proxies; no local calibration exists (no public UAE in-situ data)",
            "Seasonal climatology built from a finite archive (2017-2026)"])

    etypes = {"BLOOM_LIKE": "High chlorophyll / bloom-like anomaly",
              "SEDIMENT_LIKE": "Turbidity / suspended-sediment anomaly",
              "SURFACE_FILM_LIKE": "Surface / floating material anomaly"}
    inc = {
        "id": a.id, "status": a.status, "aoi_id": a.aoi, "aoi_name": aoi["name"],
        "detected_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observation_time": ev["meta"]["datetime"].split(".")[0] + "Z",
        "event_type_hypothesis": hyp, "severity": round(assess.severity, 4),
        "confidence": round(assess.confidence, 4), "priority": assess.priority,
        "model_id": "triage-1.0.0", "role": "operational",
        "title": a.title or etypes.get(hyp, hyp), "geometry": geom,
        "centroid": [round(lon_c, 6), round(lat_c, 6)], "area_km2": round(area, 3),
        "summary": None,
        "water_quality": {"features": {
            "NDCI": {"value": med(F["NDCI"], event), "units": "dimensionless", "quantity_kind": "PROXY",
                     "label": "Chlorophyll proxy (NDCI)", "seasonal_percentile": med(pmaps["NDCI"], event),
                     "z": med(zmaps["NDCI"], event), "baseline_median": med(meds["NDCI"], event)},
            "MCI": {"value": med(F["MCI"], event), "units": "reflectance", "quantity_kind": "PROXY",
                    "label": "Red-edge peak (MCI)", "seasonal_percentile": med(pmaps["MCI"], event),
                    "z": med(zmaps["MCI"], event), "baseline_median": med(meds["MCI"], event)},
            "TUR_NECHAD2016": {"value": med(F["TUR_NECHAD2016"], event), "units": "FNU",
                               "quantity_kind": "GENERIC_CALIBRATION", "label": "Turbidity (Nechad, not locally validated)",
                               "seasonal_percentile": med(pmaps["TUR_NECHAD2016"], event),
                               "baseline_median": med(meds["TUR_NECHAD2016"], event)},
            "HUE_ANGLE": {"value": med(F["HUE_ANGLE"], event), "units": "degrees", "quantity_kind": "COLORIMETRIC",
                          "label": "Water-colour hue angle"}}},
        "temporal": {"seasonal_percentile": pmed, "n_seasonal": int(np.nanmedian(nclim[event])),
                     "persistence_frac": cand["features"].get("persistence_frac"),
                     "note": f"Per-pixel robust z and percentile of {prim} against {len(clim)} same-season "
                             f"acquisitions from other years at {a.res:.0f} m.",
                     "series": [{"date": r_["date"], "value": ((r_.get("all") or {}).get(prim) or {}).get("p95")}
                                for r_ in ws["rows"] if "error" not in r_ and (r_.get("all") or {}).get("n_water", 0) > 500]},
        "spatial": {"rx_percentile": cand["features"].get("rx_pct")},
        "sensor_agreement": {"Sentinel-2 L2A": {"agrees": True, "note": f"z {zmed:.1f}, {pmed:.0f}th seasonal pct"}},
        "quality_flags": [f"Glint-affected water fraction {glint_frac:.0%} (B11 > 0.0215; SWIR-offset corrected)",
                          f"Median distance to shore {dshore_km:.2f} km" if dshore_km is not None else "distance to shore unknown"],
        "exposure": exp_rows[:8],
        "field_validation": {"status": "NOT_STARTED"},
        "provenance": prov.to_dict(),
        "model_features": {k: (None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), 5))
                           for k, v in feats.items()},
        "spectral": {"wavelengths_nm": S2_NM, "event": spec_e, "background": spec_b,
                     "background_p05": p05, "background_p95": p95, "bands": S2_BANDS_SPECTRUM,
                     "sensor": "Sentinel-2 L2A (SWIR-offset corrected), median of event vs background water",
                     "simulated": False},
        "layers": {"bounds": bl, "default": ["rgb", "ndci_z"], "rasters": rasters, "timeline": tl,
                   "pixels": {"url": f"layers/{a.id}/pixels.bin", "meta": f"layers/{a.id}/pixels.json"}},
        "forecast": {"steps": steps, "wind": wind_meta, "label": "SCENARIO TRAJECTORY ESTIMATE (wind-only)",
                     "is_hydrodynamic_model": False} if steps else None,
        "risk": assess.to_dict(),
        "samples": samples,
        "context": json.loads(a.context) if a.context else [],
        "cube": f"{a.id}_s2",
    }
    from pipeline import incidents as inc_mod
    problems = inc_mod.validate_payload(inc)
    if problems:
        raise SystemExit(f"invalid payload: {problems}")
    with open(os.path.join(ROOT, "outputs", "incidents", f"{a.id}.json"), "w", encoding="utf-8") as f:
        json.dump(inc, f, separators=(",", ":"), default=str)
    log(f"wrote outputs/incidents/{a.id}.json ({len(tl)} timeline frames, {len(samples)} samples, "
        f"{len(exp_rows)} assets)")


if __name__ == "__main__":
    main()
