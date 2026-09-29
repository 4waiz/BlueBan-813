"""Build the UAE coastal asset register from OpenStreetMap.

Same policy as the Annaba register: every asset is a real, publicly mapped
feature with its OpenStreetMap element id, placed at the mapped FACILITY
centroid. Intake structures are not public and are never estimated. The
register is a starting point an operator replaces with their own.

Query: one Overpass request over the union of the UAE AOIs, for desalination
and power plants (UAE plants are mostly combined power-and-water), ports,
oil terminals and named beaches.

Writes config/assets_uae.geojson. Licence: ODbL, (c) OpenStreetMap contributors.
Usage: python scripts/build_assets_uae.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERPASS = "https://overpass-api.de/api/interpreter"


def classify(tags: dict) -> str | None:
    name = (tags.get("name:en") or tags.get("name") or "").lower()
    ww = tags.get("water_works", "")
    if (tags.get("man_made") == "water_works" and ("desal" in ww or "desal" in name)) \
            or tags.get("industrial") == "desalination" or "desalination" in name \
            or tags.get("plant:output:water") or "iwpp" in name:
        return "DESALINATION_PLANT"
    if tags.get("power") == "plant":
        # Solar and wind farms have no seawater intake; they are not water assets.
        if tags.get("plant:source") in ("solar", "wind") or "solar" in name or "photovoltaic" in name:
            return None
        return "POWER_PLANT"
    if tags.get("industrial") in ("oil_terminal",) or "oil terminal" in name:
        return "OIL_TERMINAL"
    if tags.get("landuse") == "port" or tags.get("industrial") == "port" or tags.get("harbour") == "yes":
        return "PORT"
    if tags.get("natural") == "beach" and tags.get("name"):
        return "PUBLIC_BEACH"
    return None


def main():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "aois_uae.yaml"), encoding="utf-8"))["aois"]
    boxes = [v["bbox"] for v in cfg.values()]
    s, w = min(b[1] for b in boxes), min(b[0] for b in boxes)
    n, e = max(b[3] for b in boxes), max(b[2] for b in boxes)
    bb = f"{s},{w},{n},{e}"
    q = f"""[out:json][timeout:120];
(
  nwr["man_made"="water_works"]({bb});
  nwr["industrial"="desalination"]({bb});
  nwr["plant:output:water"]({bb});
  nwr["power"="plant"]({bb});
  nwr["landuse"="port"]({bb});
  nwr["industrial"="port"]({bb});
  nwr["industrial"="oil_terminal"]({bb});
  nwr["natural"="beach"]["name"]({bb});
);
out center tags;"""
    r = requests.post(OVERPASS, data={"data": q}, timeout=180,
                      headers={"User-Agent": "BLUEBAN-813/0.2 (Team Kanban hackathon; research)"})
    r.raise_for_status()
    els = r.json().get("elements", [])
    feats = []
    for el in els:
        tags = el.get("tags", {})
        typ = classify(tags)
        if not typ:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue
        aoi = next((k for k, v in cfg.items()
                    if v["bbox"][0] <= lon <= v["bbox"][2] and v["bbox"][1] <= lat <= v["bbox"][3]), None)
        if aoi is None:
            continue
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                      "properties": {"id": f"osm:{el['type']}/{el['id']}", "name": name, "type": typ,
                                     "aoi_id": aoi, "source": f"osm:{el['type']}/{el['id']}",
                                     "operator": tags.get("operator"),
                                     "notes": "Mapped facility centroid; intake location is not public "
                                              "and is not estimated.",
                                     "osm_tags": {k: tags[k] for k in ("man_made", "water_works", "power",
                                                                        "plant:source", "plant:output:water",
                                                                        "landuse", "industrial", "natural")
                                                  if k in tags}}})
    # de-duplicate by name + type within 1 km (nodes and ways of the same site)
    out, seen = [], []
    for f in sorted(feats, key=lambda f: (f["properties"]["type"], f["properties"]["name"])):
        x, y = f["geometry"]["coordinates"]
        key = (f["properties"]["type"], f["properties"]["name"].lower())
        if any(k == key and abs(x - sx) < 0.01 and abs(y - sy) < 0.01 for k, sx, sy in seen):
            continue
        seen.append((key, x, y))
        out.append(f)
    fc = {"type": "FeatureCollection",
          "properties": {"source": "OpenStreetMap via Overpass API", "licence": "ODbL",
                         "attribution": "(c) OpenStreetMap contributors",
                         "queried_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "bbox": [w, s, e, n],
                         "policy": "Real, publicly mapped facilities only; facility centroids, never "
                                   "estimated intake locations. Operators replace this register."},
          "features": out}
    p = os.path.join(ROOT, "config", "assets_uae.geojson")
    json.dump(fc, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    counts = {}
    for f in out:
        counts[f["properties"]["type"]] = counts.get(f["properties"]["type"], 0) + 1
    print(f"{len(out)} assets -> {p}: {counts}")


if __name__ == "__main__":
    sys.exit(main())
