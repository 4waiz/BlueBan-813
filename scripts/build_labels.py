"""Seed labels for the LEARN loop: Sentinel-3 OLCI cross-sensor references.

Why this exists. The triage model needs labelled examples before any analyst
has reviewed anything. Labels derived from the detection rule itself would be
circular, and inventing analyst decisions would be fabrication. These labels
come from a DIFFERENT SENSOR, a DIFFERENT atmospheric correction and a
DIFFERENT retrieval looking at the same water on the same morning:

* Sentinel-3 OLCI (300 m, 21 bands) passes over the UAE between about 06:00
  and 07:30 UTC; Sentinel-2 at about 06:55 UTC.
* For every DETECT candidate, the candidate's own pixels are mapped onto the
  OLCI swath and ESA's operational Case-2 neural-network products are compared
  inside the region and in the surrounding water (a 25 km pad around the AOI,
  excluding a 360 m ring around the region):
    - BLOOM_LIKE     -> CHL_NN  (mg m^-3)
    - SEDIMENT_LIKE  -> TSM_NN  (g m^-3)
    - SURFACE_FILM_LIKE has no OLCI counterpart and stays unlabelled.
* REFERENCE POSITIVE: region median >= 1.5 x background median (and a region
  median of at least 2 units), or a region median >= 10 units outright (a
  bloom- or plume-level value that a scene-wide event would show even with no
  contrast).
* REFERENCE NEGATIVE: ratio <= 1.15 and region median < 5 units.
* Otherwise, or with < 8 valid OLCI pixels in the region, UNLABELLED.

What these labels are NOT: in-situ ground truth. CHL_NN and TSM_NN are model
products with their own errors, worst in optically shallow water. That is why
every label carries weight 0.5 (analyst 1.0, field 2.0), the source
``cross_sensor_reference`` and the OLCI numbers it was derived from, so the
LEARN screen can show exactly what the model was taught.

OLCI on the Planetary Computer ends on 2026-02-23; later candidates stay
unlabelled until an analyst or field result labels them.

Extracts are cached under data/cache/olci/<AOI>/ (gitignored).
Writes outputs/labels/seed_labels.json. Split: stratified and grouped. Labels
from the same AOI and month always share a side (near-duplicate scenes never
straddle the split); groups are taken in a deterministic hash order until the
validation side holds ~20 % of each class, so the frozen set can measure both
precision and recall.

Usage: python scripts/build_labels.py --aoi AE-FUJ [--aoi ...] [--workers 3]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import detect, learning, sentinel3 as s3, watch  # noqa: E402

REFERENCE = s3.REFERENCE_VARIABLE
PAD_DEG = 0.25
MIN_REGION_PX = 8
MIN_BG_PX = 30
OLCI_END = dt.date.fromisoformat(s3.PC_OLCI_END)


def olci_extract(args):
    """Worker: best OLCI granule of one date, windowed to the AOI (cached)."""
    aoi, date, bbox, s2_time, cache = args
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        return date, {k: z[k] for k in z.files}
    try:
        items = s3.search(bbox, f"{date}T03:30:00Z/{date}T10:00:00Z")
    except Exception as e:
        return date, {"error": repr(e)[:200]}
    best = None
    for it in items[:3]:
        try:
            w = s3.load_window(it, bbox, PAD_DEG, variables=("chl-nn", "tsm-nn"))
        except Exception as e:                       # recorded, never hidden
            w = {"error": repr(e)[:200]}
        if not w or "error" in w:
            continue
        inb = ((w["lon"] >= bbox[0]) & (w["lon"] <= bbox[2]) & (w["lat"] >= bbox[1])
               & (w["lat"] <= bbox[3]) & w["valid"])
        score = int(inb.sum())
        if best is None or score > best[0]:
            best = (score, w)
    if best is None:
        out = {"error": "no usable OLCI granule"}
    else:
        w = best[1]
        t_olci = dt.datetime.fromisoformat(str(w["datetime"]).replace("Z", "+00:00"))
        w["dt_minutes"] = np.array((t_olci - s2_time).total_seconds() / 60.0)
        out = w
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    np.savez_compressed(cache, **{k: np.asarray(v) for k, v in out.items()})
    return date, out


def stratified_group_split(labels: list, frac: float = 0.2) -> None:
    """Assign whole AOI-month groups to validation until ~frac of EACH class is held out."""
    groups: dict = {}
    for l in labels:
        groups.setdefault(l["group_key"], []).append(l)
    tot_p = sum(l["target"]["y"] == 1 for l in labels)
    tot_n = len(labels) - tot_p
    tp, tn = frac * tot_p, frac * tot_n
    vp = vn = 0
    chosen = set()
    for g in sorted(groups, key=lambda g: hashlib.sha256(g.encode()).hexdigest()):
        gp = sum(l["target"]["y"] == 1 for l in groups[g])
        gn = len(groups[g]) - gp
        short_p, short_n = vp < tp, vn < tn
        if not (short_p or short_n):
            break
        helps = (short_p and gp > 0) or (short_n and gn > 0)
        if helps and vp + gp <= 1.5 * tp + 1 and vn + gn <= 1.5 * tn + 1:
            chosen.add(g)
            vp, vn = vp + gp, vn + gn
    for l in labels:
        l["split"] = "validation" if l["group_key"] in chosen else "train"


def region_mask(ci, stacks, t, cand, window):
    """The candidate's pixels on its own date (z >= Z_MIN and pct >= PCT_MIN inside its bbox)."""
    prim = detect.HYPOTHESIS_FEATURES[cand["hypothesis"]][0][0]
    idx = detect.climatology_indices(ci.dates, t, window)
    z, pct, _, _, _ = detect.robust_anomaly(stacks[prim][t].astype("float32"),
                                            stacks[prim][idx].astype("float32"), detect.FLOORS[prim])
    r0, c0, r1, c1 = cand["bbox_rc"]
    m = np.zeros(z.shape, bool)
    m[r0:r1 + 1, c0:c1 + 1] = True
    return m & (np.nan_to_num(z) >= detect.Z_MIN) & (np.nan_to_num(pct) >= detect.PCT_MIN)


def main():
    from pyproj import Transformer
    from scipy import ndimage as ndi

    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", action="append", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--val-frac", type=float, default=0.2)
    a = ap.parse_args()
    labels, stats = [], {}
    for aoi in a.aoi:
        t0 = time.time()
        det = json.load(open(os.path.join(ROOT, "outputs", "detect", f"{aoi}.json"), encoding="utf-8"))
        ws = json.load(open(os.path.join(ROOT, "outputs", "watch", f"{aoi}.json"), encoding="utf-8"))
        grid = watch.AoiGrid.from_bbox(aoi, ws["bbox"], ws["grid"]["resolution_m"])
        bbox = list(grid.bbox)
        s2_time = {r["cache_file"]: dt.datetime.fromisoformat(r["datetime"].replace("Z", "+00:00"))
                   for r in ws["rows"] if r.get("cache_file") and r.get("datetime")}
        cands = [c for c in det["candidates"] if c["hypothesis"] in REFERENCE
                 and dt.date.fromisoformat(c["date"]) <= OLCI_END]
        files = sorted({c["cache_file"] for c in cands})
        print(f"{aoi}: {len(cands)} candidates with an OLCI counterpart on {len(files)} dates", flush=True)
        jobs = [(aoi, f[:10], bbox, s2_time[f],
                 os.path.join(ROOT, "data", "cache", "olci", aoi, f[:-4] + ".npz"))
                for f in files if f in s2_time]
        extracts = {}
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for i, (date, w) in enumerate(ex.map(olci_extract, jobs), 1):
                extracts[date] = w
                if i % 10 == 0:
                    print(f"  OLCI {i}/{len(jobs)} ({time.time() - t0:.0f}s)", flush=True)

        ci = detect.CacheIndex.load(os.path.join(ROOT, "data", "cache", "watch", aoi), aoi)
        stacks = {f: ci.stack(f).astype("float16") for f in ("NDCI", "TUR_NECHAD2016")}
        fidx = {f: i for i, f in enumerate(ci.files)}
        tr = Transformer.from_crs("EPSG:4326", f"EPSG:{grid.epsg}", always_xy=True)
        T = grid.transform
        n_pos = n_neg = n_unl = 0
        reasons: dict = {}
        for cand in cands:
            w = extracts.get(cand["date"])
            t = fidx.get(cand["cache_file"])
            if t is None or not w or "error" in w:
                n_unl += 1
                reasons["no OLCI granule"] = reasons.get("no OLCI granule", 0) + 1
                continue
            var, units = REFERENCE[cand["hypothesis"]]
            mask = region_mask(ci, stacks, t, cand, det["window_days"])
            ring = ndi.binary_dilation(mask, iterations=3)
            x, y = tr.transform(w["lon"], w["lat"])
            col = np.floor((np.asarray(x) - T.c) / T.a).astype(int)
            row = np.floor((np.asarray(y) - T.f) / T.e).astype(int)
            ing = (row >= 0) & (row < grid.shape[0]) & (col >= 0) & (col < grid.shape[1])
            rin = np.zeros(len(row), bool)
            near = np.zeros(len(row), bool)
            rin[ing] = mask[row[ing], col[ing]]
            near[ing] = ring[row[ing], col[ing]]
            v = np.power(10.0, w[var].astype("float64"))
            ok = w["valid"].astype(bool) & np.isfinite(v)
            reg_px, bg_px = ok & rin, ok & ~near
            if reg_px.sum() < MIN_REGION_PX or bg_px.sum() < MIN_BG_PX:
                n_unl += 1
                reasons["too few valid OLCI pixels"] = reasons.get("too few valid OLCI pixels", 0) + 1
                continue
            y_, reg, bg, ratio = s3.reference_contrast(v[reg_px], v[bg_px])
            if y_ is None:
                n_unl += 1
                reasons["ambiguous contrast"] = reasons.get("ambiguous contrast", 0) + 1
                continue
            n_pos += y_ == 1
            n_neg += y_ == 0
            gk = f"{aoi}|{cand['date'][:7]}"
            lid = "LB-S3-" + hashlib.sha256(
                f"{aoi}|{cand['date']}|{cand['hypothesis']}|{cand['label']}".encode()).hexdigest()[:10]
            labels.append({
                "id": lid, "task": "triage", "incident_id": None, "aoi_id": aoi,
                "target": {"y": y_, "class": cand["hypothesis"] if y_ == 1 else "NOT_CONFIRMED",
                           "reference": f"Sentinel-3 OLCI {var} (ESA Case-2 neural net; a model product, not in situ)",
                           "olci": {"item_id": str(w["item_id"]), "dt_minutes": round(float(w["dt_minutes"]), 1),
                                    "variable": var, "units": units, "region_median": round(reg, 3),
                                    "background_median": round(bg, 3), "ratio": round(ratio, 3),
                                    "n_region_px": int(reg_px.sum()), "n_background_px": int(bg_px.sum())},
                           "candidate_date": cand["date"], "candidate_label": cand["label"],
                           "hypothesis": cand["hypothesis"]},
                "features": cand["features"], "source": "cross_sensor_reference",
                "source_ref": f"{aoi}:{cand['date']}:{cand['hypothesis']}:{cand['label']}",
                "weight": 0.5, "split": "train",
                "group_key": gk, "created_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "created_by": "pipeline (OLCI cross-sensor reference)", "superseded_by": None})
        stats[aoi] = {"candidates": len(cands), "positive": int(n_pos), "negative": int(n_neg),
                      "unlabelled": n_unl, "unlabelled_reasons": reasons,
                      "seconds": round(time.time() - t0, 1)}
        print(aoi, stats[aoi], flush=True)
    os.makedirs(os.path.join(ROOT, "outputs", "labels"), exist_ok=True)
    stratified_group_split(labels, a.val_frac)
    val = [l for l in labels if l["split"] == "validation"]
    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "method": "Sentinel-3 OLCI cross-sensor reference labels (see scripts/build_labels.py)",
           "rule": {"positive": "ratio >= 1.5 and region >= 2, or region >= 10",
                    "negative": "ratio <= 1.15 and region < 5", "min_region_px": MIN_REGION_PX,
                    "min_background_px": MIN_BG_PX, "pad_deg": PAD_DEG, "weight": 0.5},
           "stats": stats, "n": len(labels), "n_validation": len(val),
           "validation_hash_python": learning.dataset_hash(val) if val else None, "labels": labels}
    with open(os.path.join(ROOT, "outputs", "labels", "seed_labels.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"{len(labels)} labels ({len(val)} validation) -> outputs/labels/seed_labels.json")


if __name__ == "__main__":
    main()
