"""UAE AOI tournament, step 1: measure what data actually exists over each candidate.

Every number in docs/UAE_AOI_TOURNAMENT.md comes from this script's output
(outputs/aoi/census.json). Nothing is typed in by hand.

For each candidate AOI it counts, over a fixed window:

* Sentinel-2 L2A acquisitions and how many are usable (scene cloud <= 10 %),
* Sentinel-3 OLCI WFR L2 acquisitions,
* Sentinel-1 GRD acquisitions (for the optional surface-film mode),
* Landsat 8/9 Collection 2 Level-2 acquisitions (thermal context),
* Planet Tanager-1 open-archive hyperspectral items intersecting the AOI,

using the public, anonymous Microsoft Planetary Computer STAC API and the Planet
open STAC catalog. In-situ availability and 813 availability are not queryable
here; they are scored from docs/AUTHENTICATED_DATA_AUDIT.md and the public data
search, and the script leaves those columns to be merged in.

Usage: python scripts/aoi_census.py [--start 2023-01-01] [--end 2026-09-30]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
TANAGER_STAC = "https://www.planet.com/data/stac/tanager-core-imagery"

# Candidate AOIs. Boxes are drawn around the WATER in front of each coastal
# asset cluster, not around the town. They are deliberately similar in size
# (~20-35 km across) so acquisition counts are comparable.
CANDIDATES = {
    "AE-AUH-MUSAFFAH": {
        "name": "Abu Dhabi / Musaffah - Umm Al Nar coastal waters",
        "coast": "Arabian Gulf",
        "bbox": [54.30, 24.28, 54.62, 24.55],
    },
    "AE-AUH-TAWEELAH": {
        "name": "Al Taweelah / Khalifa Port",
        "coast": "Arabian Gulf",
        "bbox": [54.60, 24.68, 54.92, 24.90],
    },
    "AE-DXB-JEBELALI": {
        "name": "Dubai / Jebel Ali",
        "coast": "Arabian Gulf",
        "bbox": [54.95, 24.95, 55.22, 25.12],
    },
    "AE-SHJ-AJM": {
        "name": "Sharjah / Ajman",
        "coast": "Arabian Gulf",
        "bbox": [55.30, 25.30, 55.55, 25.48],
    },
    "AE-UAQ-RAK": {
        "name": "Umm Al Quwain / Ras Al Khaimah",
        "coast": "Arabian Gulf",
        "bbox": [55.55, 25.50, 55.95, 25.85],
    },
    "AE-FUJ": {
        "name": "Fujairah / Qidfa / anchorage",
        "coast": "Gulf of Oman",
        "bbox": [56.30, 25.05, 56.55, 25.40],
    },
    "AE-SHJ-KALBA": {
        "name": "Kalba",
        "coast": "Gulf of Oman",
        "bbox": [56.33, 24.95, 56.50, 25.10],
    },
    "AE-SHJ-KHORFAKKAN": {
        "name": "Khor Fakkan",
        "coast": "Gulf of Oman",
        "bbox": [56.33, 25.30, 56.45, 25.42],
    },
    "AE-FUJ-DIBBA": {
        "name": "Dibba",
        "coast": "Gulf of Oman",
        "bbox": [56.25, 25.55, 56.40, 25.68],
    },
}

COLLECTIONS = {
    "s2": "sentinel-2-l2a",
    "s3": "sentinel-3-olci-wfr-l2-netcdf",
    "s1": "sentinel-1-grd",
    "landsat": "landsat-c2-l2",
}


def _pc_items(collection: str, bbox, start: str, end: str, query=None):
    from pystac_client import Client
    cat = Client.open(PC_STAC)
    search = cat.search(collections=[collection], bbox=bbox,
                        datetime=f"{start}/{end}", query=query or {},
                        max_items=5000)
    out = []
    for it in search.items():
        p = it.properties
        out.append({
            "id": it.id,
            "datetime": p.get("datetime"),
            "cloud": p.get("eo:cloud_cover"),
            "platform": p.get("platform"),
        })
    return out


def census_one(aoi_id: str, aoi: dict, start: str, end: str) -> dict:
    bbox = aoi["bbox"]
    res = {"id": aoi_id, **aoi, "window": [start, end]}
    for key, coll in COLLECTIONS.items():
        q = None
        if key == "landsat":
            q = {"platform": {"in": ["landsat-8", "landsat-9"]}}
        t0 = time.time()
        try:
            items = _pc_items(coll, bbox, start, end, q)
        except Exception as e:                      # network hiccups are recorded, not hidden
            res[key] = {"error": repr(e)}
            continue
        dates = sorted({i["datetime"][:10] for i in items if i["datetime"]})
        clouds = [i["cloud"] for i in items if i["cloud"] is not None]
        entry = {
            "collection": coll,
            "n_items": len(items),
            "n_dates": len(dates),
            "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None,
            "query_seconds": round(time.time() - t0, 1),
        }
        if clouds:
            entry["n_items_cloud_le_10"] = sum(c <= 10 for c in clouds)
            entry["n_dates_cloud_le_10"] = len({i["datetime"][:10] for i in items
                                                if i["cloud"] is not None
                                                and i["cloud"] <= 10})
            entry["median_cloud"] = sorted(clouds)[len(clouds) // 2]
        if key == "s2":
            clear = sorted([i for i in items if (i["cloud"] or 100) <= 5],
                           key=lambda i: i["datetime"])
            entry["latest_clear"] = clear[-5:] if clear else []
        res[key] = entry
    return res


def tanager_items_uae() -> list:
    """Walk the Planet open Tanager catalog and keep items touching the UAE."""
    import requests
    uae = (51.0, 22.5, 56.6, 26.3)
    out = []
    root = requests.get(f"{TANAGER_STAC}/catalog.json", timeout=60).json()
    for link in root.get("links", []):
        if link.get("rel") != "child":
            continue
        href = link["href"]
        if not href.startswith("http"):
            href = f"{TANAGER_STAC}/{href.lstrip('./')}"
        coll = requests.get(href, timeout=60).json()
        base = href.rsplit("/", 1)[0]
        for il in coll.get("links", []):
            if il.get("rel") != "item":
                continue
            ih = il["href"]
            if not ih.startswith("http"):
                ih = f"{base}/{ih.lstrip('./')}"
            try:
                item = requests.get(ih, timeout=60).json()
            except Exception:
                continue
            bb = item.get("bbox") or []
            if len(bb) >= 4 and not (bb[2] < uae[0] or bb[0] > uae[2]
                                     or bb[3] < uae[1] or bb[1] > uae[3]):
                p = item.get("properties", {})
                out.append({
                    "id": item.get("id"),
                    "collection": coll.get("id"),
                    "datetime": p.get("datetime"),
                    "cloud_percent": p.get("cloud_percent", p.get("eo:cloud_cover")),
                    "bbox": bb,
                    "href": ih,
                })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--skip-tanager", action="store_true")
    a = ap.parse_args()

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {k: ex.submit(census_one, k, v, a.start, a.end)
                for k, v in CANDIDATES.items()}
        results = {k: f.result() for k, f in futs.items()}

    tanager = [] if a.skip_tanager else tanager_items_uae()
    for k, r in results.items():
        bb = r["bbox"]
        r["tanager"] = [t for t in tanager
                        if not (t["bbox"][2] < bb[0] or t["bbox"][0] > bb[2]
                                or t["bbox"][3] < bb[1] or t["bbox"][1] > bb[3])]

    out = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {"planetary_computer": PC_STAC, "tanager": TANAGER_STAC},
        "window": [a.start, a.end],
        "tanager_items_in_uae": tanager,
        "candidates": results,
    }
    os.makedirs(os.path.join(ROOT, "outputs", "aoi"), exist_ok=True)
    path = os.path.join(ROOT, "outputs", "aoi", "census.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    for k, r in results.items():
        s2, s3, s1, ls = (r.get(x, {}) for x in ("s2", "s3", "s1", "landsat"))
        print(f"{k:20s} S2 {s2.get('n_dates','?'):>4} ({s2.get('n_dates_cloud_le_10','?')} clear)  "
              f"S3 {s3.get('n_dates','?'):>4}  S1 {s1.get('n_dates','?'):>4}  "
              f"LS {ls.get('n_dates','?'):>4}  Tanager {len(r['tanager'])}")
    print(f"Tanager items touching UAE: {len(tanager)}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
