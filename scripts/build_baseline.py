"""Build the multi-year Sentinel-2 water-quality baseline for the AOI.

This answers the question a single hyperspectral scene cannot: is the elevated
nearshore signal on 2025-06-01 an EVENT, or is it what this coastline always
looks like (permanent bottom reflectance in shallow water)?

Two zones are tracked:

* HOTSPOT  - the inner Gulf of Annaba where the RX detector found anomalies
* REFERENCE- offshore water in the same scene, as a control

For every usable Sentinel-2 acquisition we record zone-median reflectance and
index values. If the hotspot is elevated on every clear date, it is bottom or
another permanent feature. If 2025-06-01 sits in the upper tail, it is an event.

Usage: python scripts/build_baseline.py [--years 6] [--out outputs/validation]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import sentinel2 as S2   # noqa: E402
from pipeline import temporal as TP    # noqa: E402

# Zones in EPSG:4326. HOTSPOT covers the inner-gulf anomaly chain (regions
# L4-L7, centroids 36.886-36.931 N / 7.770-7.777 E). REFERENCE is open water in
# the north of the same Tanager footprint.
ZONES = {
    "hotspot_inner_gulf": [7.752, 36.878, 7.800, 36.940],
    "reference_offshore": [7.560, 37.000, 7.700, 37.055],
}
AOI_BBOX = [7.5174573391889, 36.87386550739371, 7.809339376236341, 37.05991800372398]
BANDS = ["B03", "B04", "B05", "B8A", "B11", "SCL"]


def process_item(item, bbox):
    """Reduce one Sentinel-2 item over one zone to median water statistics."""
    raw, _, _ = S2.load_bands(item, BANDS, bbox, resolution=20)
    dt = item.properties["datetime"][:10]

    scl = raw["SCL"]
    usable, water_scl = S2.scl_masks(scl)

    refl = {b: S2.harmonize(raw[b], dt) for b in BANDS if b != "SCL"}

    # Independent water test rather than trusting SCL alone: SCL misclassifies
    # turbid and shallow water as land surprisingly often.
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = (refl["B03"] - refl["B11"]) / (refl["B03"] + refl["B11"] + 1e-6)
    water = usable & (water_scl | (np.isfinite(mndwi) & (mndwi > 0.15))) \
        & np.isfinite(refl["B8A"]) & (refl["B8A"] < 0.10)

    n = int(water.sum())
    if n < 30:
        return None

    idx = S2.water_indices(refl)
    stats = {}
    for k, arr in idx.items():
        v = arr[water]
        v = v[np.isfinite(v)]
        if v.size < 30:
            stats[k] = np.nan
            stats[k + "_p95"] = np.nan
            continue
        # Median AND upper percentile. A localised plume of ~1 km2 inside a
        # ~30 km2 monitoring zone barely shifts the median: the zone can look
        # entirely normal while a real event sits inside it. The 95th
        # percentile tracks the most affected part of the zone, which is what
        # an event actually moves.
        stats[k] = float(np.median(v))
        stats[k + "_p95"] = float(np.percentile(v, 95))
    stats["water_fraction"] = float(water.sum() / max(usable.sum(), 1))

    return S2Obs(item.id, item.properties["datetime"],
                 float(item.properties.get("eo:cloud_cover") or -1), n, stats)


class S2Obs(S2.S2Observation):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--max-cloud", type=float, default=15.0)
    ap.add_argument("--out", default="outputs/validation")
    ap.add_argument("--limit", type=int, default=0, help="cap items (debug)")
    args = ap.parse_args()

    end = 2025
    start = end - args.years + 1
    dr = f"{start}-01-01/2025-12-31"
    print(f"Searching Sentinel-2 L2A  {dr}  cloud<={args.max_cloud}%")
    items = S2.search(AOI_BBOX, dr, max_cloud=args.max_cloud, limit=2000)
    if args.limit:
        items = items[:args.limit]
    print(f"  {len(items)} candidate acquisitions")

    results = {z: [] for z in ZONES}
    t0 = time.time()

    # Each (item, zone) pair is an independent set of HTTP range reads against
    # Planetary Computer, so the work is network-bound and parallelises well.
    import concurrent.futures as cf
    tasks = [(item, zname, zbox) for item in items for zname, zbox in ZONES.items()]
    done = 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(process_item, it, zb): (it, zn)
                for it, zn, zb in tasks}
        for fut in cf.as_completed(futs):
            it, zn = futs[fut]
            done += 1
            try:
                obs = fut.result()
                if obs is not None:
                    results[zn].append(obs.to_dict())
            except Exception as e:                      # noqa: BLE001
                print(f"  [{it.id[:38]} {zn}] FAILED {type(e).__name__}: {e}",
                      flush=True)
            if done % 20 == 0:
                print(f"  {done}/{len(tasks)}  {time.time()-t0:.0f}s  "
                      f"hotspot={len(results['hotspot_inner_gulf'])} "
                      f"ref={len(results['reference_offshore'])}", flush=True)

    for z in results:
        results[z].sort(key=lambda r: r["datetime"])

    os.makedirs(args.out, exist_ok=True)
    raw_path = os.path.join(args.out, "s2_timeseries.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print(f"\nWrote {raw_path}")

    # Baselines and the verdict on 2025-06-01.
    report = {"zones": {}, "target_date": "2025-06-01", "verdict": {}}
    for zname, obs in results.items():
        if not obs:
            continue
        dates = [o["datetime"][:10] for o in obs]
        z = {"n_observations": len(obs), "baselines": {}}
        for var in ("TURBIDITY_PROXY", "NDCI", "R560", "R665", "MNDWI",
                    "TURBIDITY_PROXY_p95", "NDCI_p95", "R560_p95", "R665_p95"):
            vals = [o.get(var) for o in obs]
            vals = [np.nan if v is None else v for v in vals]
            bs = TP.build_baseline(vals, dates, var)
            z["baselines"][var] = bs.to_dict()

            near = [(abs(np.datetime64(d) - np.datetime64("2025-06-01")).astype(int), i)
                    for i, d in enumerate(dates)]
            near.sort()
            if near and near[0][0] <= 10:
                i = near[0][1]
                sp = TP.seasonal_percentile(vals[i], vals, dates, "2025-06-01")
                sp["matched_date"] = dates[i]
                sp["days_from_target"] = int(near[0][0])
                sp["state"] = TP.classify_state(sp.get("seasonal_percentile"))
                z["baselines"][var]["target_assessment"] = sp
            z["baselines"][var]["trend"] = TP.trend(vals, dates)
        report["zones"][zname] = z

    rep_path = os.path.join(args.out, "s2_baseline_report.json")
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"Wrote {rep_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
