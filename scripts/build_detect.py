"""Run DETECT over every cached acquisition of an AOI.

Reads ``data/cache/watch/<AOI>/`` (written by build_watch.py --cache) and writes
``outputs/detect/<AOI>.json``: every candidate region on every date with its
triage feature vector, plus a per-date anomaly summary used by the WATCH screen.

Usage: python scripts/build_detect.py --aoi AE-AUH-NORTH [--res 120]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import detect  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", required=True, action="append")
    ap.add_argument("--res", type=float, default=120.0)
    ap.add_argument("--window", type=int, default=45)
    ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    os.makedirs(os.path.join(ROOT, "outputs", "detect"), exist_ok=True)
    for aoi in a.aoi:
        t0 = time.time()
        folder = os.path.join(ROOT, "data", "cache", "watch", aoi + a.suffix)
        ci = detect.CacheIndex.load(folder, aoi)
        pw, frac = detect.persistent_water(ci)
        dshore = detect.distance_to_shore_px(pw)
        stacks = {f: ci.stack(f).astype("float16") for f in detect.FLOORS}
        print(f"{aoi}: {len(ci.files)} acquisitions loaded in {time.time() - t0:.0f}s",
              flush=True)

        class _S(dict):                   # float16 in memory, float32 per slice
            def __getitem__(self, k):
                return _Slicer(dict.__getitem__(self, k))

        class _Slicer:
            def __init__(self, arr):
                self.arr = arr

            def __getitem__(self, idx):
                return self.arr[idx].astype("float32")

        s32 = _S(stacks)
        dates, cands = [], []
        for t in range(len(ci.files)):
            r = detect.detect_at(ci, t, a.res, a.window, dshore, s32)
            summ = {"date": r["date"], "cache_file": r["cache_file"],
                    "n_climatology": r["n_climatology"], "water_px": r["water_px"],
                    "skipped": r.get("skipped")}
            for hyp in detect.HYPOTHESIS_FEATURES:
                cs = [c for c in r["candidates"] if c.hypothesis == hyp]
                summ[hyp] = {"n": len(cs),
                             "area_km2": round(sum(c.area_km2 for c in cs), 3),
                             "max_z": max((c.features["robust_z_primary"] or 0 for c in cs),
                                          default=None)}
            dates.append(summ)
            cands.extend(c.to_dict() for c in r["candidates"])
            if (t + 1) % 50 == 0:
                print(f"  {t + 1}/{len(ci.files)} ({time.time() - t0:.0f}s), "
                      f"{len(cands)} candidates", flush=True)
        out = {"aoi_id": aoi, "resolution_m": a.res, "window_days": a.window,
               "thresholds": {"z_min": detect.Z_MIN, "pct_min": detect.PCT_MIN,
                              "min_area_km2": detect.MIN_AREA_KM2,
                              "min_climatology_n": detect.MIN_CLIM_N,
                              "floors": detect.FLOORS},
               "persistent_water_px": int(pw.sum()),
               "n_acquisitions": len(ci.files), "dates": dates, "candidates": cands,
               "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        np.savez_compressed(os.path.join(folder, "_static.npz"),
                            persistent_water=pw, water_frequency=frac.astype("float32"),
                            dist_shore_px=dshore.astype("float32"))
        p = os.path.join(ROOT, "outputs", "detect", f"{aoi}{a.suffix}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, separators=(",", ":"))
        print(f"  -> {p}: {len(cands)} candidates on "
              f"{sum(1 for d in dates if any(d[h]['n'] for h in detect.HYPOTHESIS_FEATURES))}"
              f" dates, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
