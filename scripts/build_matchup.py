"""Build the Tanager <-> Sentinel-3 OLCI matchup dataset for the ablation.

The ablation needs a target variable that neither candidate feature set can
trivially reproduce. Sentinel-3 OLCI Level-2 provides one: ESA's operational
chlorophyll-a (neural-network, Case-2) and total suspended matter retrievals,
produced by a different instrument through a different processing chain.

Procedure
---------
1. Take the Tanager cube over the AOI and its water mask.
2. Aggregate Tanager water pixels onto the OLCI footprint (~300 m) by taking
   the mean spectrum of the Tanager pixels falling within each OLCI pixel.
3. Attach the co-located OLCI CHL_NN and TSM_NN values.
4. Record the time offset for every matchup so the temporal mismatch is visible
   rather than hidden.

Only OLCI pixels with enough contributing Tanager water pixels are kept, so a
matchup is never built from a handful of edge pixels.

Usage: python scripts/build_matchup.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import sentinel3 as S3            # noqa: E402
from pipeline.satellite813 import TanagerScene  # noqa: E402

AOI = [7.5174573391889, 36.87386550739371, 7.809339376236341, 37.05991800372398]
TANAGER = "data/raw/tanager/20250601_104901_58_4001_ortho_sr_hdf5.h5"
TANAGER_TIME = "2025-06-01T10:49:01Z"
OUT = "data/cache/matchup"
MIN_CONTRIB = 25          # Tanager pixels required per OLCI pixel (300m/30m ~ 100)


def main():
    os.makedirs(OUT, exist_ok=True)
    scene = TanagerScene(TANAGER)
    water = np.load("data/cache/water.npy")
    good = np.where(scene.good_wavelengths)[0]
    wl = scene.wavelengths[good]
    print(f"Tanager: {len(good)} good bands, {water.sum()} water px")

    cube = scene.read_cube(good)
    print(f"cube {cube.shape}")

    # Tanager pixel centres in WGS84.
    from pyproj import Transformer
    x0, dx, _, y0, _, dy = scene.grid.transform
    rows, cols = scene.rows, scene.cols
    cc, rr = np.meshgrid(np.arange(cols), np.arange(rows))
    xs = x0 + (cc + 0.5) * dx
    ys = y0 + (rr + 0.5) * dy
    tr = Transformer.from_crs(f"EPSG:{scene.epsg}", "EPSG:4326", always_xy=True)
    lon_t, lat_t = tr.transform(xs, ys)

    t_ref = datetime.fromisoformat(TANAGER_TIME.replace("Z", "+00:00"))
    items = S3.search(AOI, "2025-05-29/2025-06-06")
    print(f"OLCI candidates: {len(items)}")

    records = []
    for it in items:
        t_i = datetime.fromisoformat(it.properties["datetime"].replace("Z", "+00:00"))
        dt_h = (t_i - t_ref).total_seconds() / 3600.0
        print(f"\n{it.id[:60]}  dt={dt_h:+.2f} h  cloud={it.properties.get('eo:cloud_cover')}")
        try:
            sc = S3.load(it, variables=("chl-nn", "tsm-nn"))
        except Exception as e:                                   # noqa: BLE001
            print(f"  load failed: {type(e).__name__}: {e}")
            continue
        if sc.lon is None:
            print("  no geolocation; skipped")
            continue
        sub = S3.subset_bbox(sc, AOI)
        print(f"  OLCI valid px in AOI: {sub['n']}  vars={[k for k in sub if k not in ('lon','lat','n')]}")
        if sub["n"] < 10:
            continue

        # For each OLCI pixel, average the Tanager water pixels inside a
        # 300 m box centred on it.
        half_deg_lat = 150.0 / 111320.0
        n_kept = 0
        for i in range(sub["n"]):
            olon, olat = sub["lon"][i], sub["lat"][i]
            half_deg_lon = 150.0 / (111320.0 * np.cos(np.radians(olat)))
            box = (
                water
                & (np.abs(lon_t - olon) <= half_deg_lon)
                & (np.abs(lat_t - olat) <= half_deg_lat)
            )
            n = int(box.sum())
            if n < MIN_CONTRIB:
                continue
            spec = np.nanmean(cube[:, box], axis=1)
            if not np.isfinite(spec).all():
                continue
            rec = {
                "olci_item": it.id,
                "olci_datetime": it.properties["datetime"],
                "dt_hours": round(dt_h, 3),
                "lon": float(olon), "lat": float(olat),
                "n_tanager_px": n,
                "spectrum": [round(float(v), 6) for v in spec],
            }
            for k in sub:
                if k in ("lon", "lat", "n"):
                    continue
                rec[k] = float(sub[k][i])
            records.append(rec)
            n_kept += 1
        print(f"  matchups kept: {n_kept}")

    meta = {
        "wavelengths_nm": [round(float(v), 3) for v in wl],
        "n_bands": len(wl),
        "tanager_scene": scene.scene_id,
        "tanager_datetime": TANAGER_TIME,
        "min_contributing_px": MIN_CONTRIB,
        "n_matchups": len(records),
        "aoi": AOI,
        "note": "OLCI CHL_NN and TSM_NN are stored as log10 by ESA; values here "
                "are as stored. dt_hours is OLCI minus Tanager acquisition time.",
    }
    with open(os.path.join(OUT, "matchup_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    with open(os.path.join(OUT, "matchup_records.json"), "w", encoding="utf-8") as f:
        json.dump(records, f)
    print(f"\nTotal matchups: {len(records)}")
    print(f"Wrote {OUT}/matchup_records.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
