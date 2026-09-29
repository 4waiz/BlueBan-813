"""Run the WATCH screen over the UAE AOIs and write their time series.

Writes ``outputs/watch/<AOI>.json`` (zone statistics per acquisition, committed)
and, with ``--cache``, per-acquisition feature rasters under
``data/cache/watch/<AOI>/`` (gitignored) for per-pixel climatologies.

Usage:
    python scripts/build_watch.py --res 120 --start 2023-01-01 --end 2026-09-30
    python scripts/build_watch.py --aoi AE-FUJ --res 60 --start 2019-01-01 --cache
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import yaml  # noqa: E402

from pipeline import watch  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", action="append", help="AOI id (repeatable); default all")
    ap.add_argument("--res", type=float, default=120.0)
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--max-cloud", type=float, default=30.0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cache", action="store_true")
    ap.add_argument("--suffix", default="")
    ap.add_argument("--zones", default="none", choices=["none", "worldcover"])
    a = ap.parse_args()

    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "aois_uae.yaml"),
                              encoding="utf-8"))["aois"]
    ids = a.aoi or list(cfg)
    os.makedirs(os.path.join(ROOT, "outputs", "watch"), exist_ok=True)
    for aoi_id in ids:
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] {aoi_id} ...", flush=True)
        cache = (os.path.join(ROOT, "data", "cache", "watch",
                              f"{aoi_id}{a.suffix}") if a.cache else None)
        ts = watch.screen_aoi(aoi_id, cfg[aoi_id]["bbox"], a.start, a.end,
                              resolution_m=a.res, max_cloud=a.max_cloud,
                              workers=a.workers, cache_dir=cache,
                              zones=None if a.zones == "none" else a.zones,
                              progress=lambda m: print(m, flush=True))
        ts["aoi"] = cfg[aoi_id]
        out = os.path.join(ROOT, "outputs", "watch", f"{aoi_id}{a.suffix}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(ts, f, separators=(",", ":"))
        print(f"  -> {out}  ok={ts['n_ok']}/{ts['n_datatakes']}  "
              f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
