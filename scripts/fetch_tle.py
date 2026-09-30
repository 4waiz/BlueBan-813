"""Snapshot of public orbital elements (TLE) for the Satellite View.

Source: CelesTrak GP data (https://celestrak.org), public. Positions are
propagated in the browser with SGP4 (satellite.js); accuracy degrades by
roughly a kilometre per day after the TLE epoch, which is irrelevant at globe
scale but is shown next to every position. Re-run to refresh.

Writes config/tle_eo.json
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: Satellite name on CelesTrak -> (key, role in BLUEBAN 813)
WANTED = {
    "SENTINEL-2A": ("S2A", "Sentinel-2 MSI: primary detection sensor"),
    "SENTINEL-2B": ("S2B", "Sentinel-2 MSI: primary detection sensor"),
    "SENTINEL-2C": ("S2C", "Sentinel-2 MSI: primary detection sensor"),
    "SENTINEL-3A": ("S3A", "Sentinel-3 OLCI: cross-sensor reference"),
    "SENTINEL-3B": ("S3B", "Sentinel-3 OLCI: cross-sensor reference"),
    "SENTINEL-1A": ("S1A", "Sentinel-1 SAR: optional surface-dark-anomaly mode"),
    "SENTINEL-1C": ("S1C", "Sentinel-1 SAR: optional surface-dark-anomaly mode"),
    "SENTINEL-1D": ("S1D", "Sentinel-1 SAR: optional surface-dark-anomaly mode"),
    "LANDSAT 8": ("L8", "Landsat 8 OLI/TIRS: thermal context"),
    "LANDSAT 9": ("L9", "Landsat 9 OLI-2/TIRS-2: thermal context"),
    "PACE": ("PACE", "NASA PACE OCI hyperspectral ocean colour (imaged the 2024 Gulf of Oman bloom)"),
    "TANAGER-1": ("TAN1", "Planet Tanager-1 hyperspectral: source pixels of the simulated 813 product"),
}


def fetch(query: str) -> str:
    url = "https://celestrak.org/NORAD/elements/gp.php?" + urllib.parse.urlencode({"NAME": query, "FORMAT": "TLE"})
    req = urllib.request.Request(url, headers={"User-Agent": "BLUEBAN-813 satellite view (research demo)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def main():
    got = {}
    for q in ("SENTINEL", "LANDSAT", "PACE", "TANAGER"):
        txt = fetch(q).strip().splitlines()
        for i in range(0, len(txt) - 2, 3):
            name, l1, l2 = txt[i].strip(), txt[i + 1].strip(), txt[i + 2].strip()
            if name in WANTED and l1.startswith("1 ") and l2.startswith("2 "):
                got[name] = (l1, l2)
        time.sleep(1.0)
    sats = []
    for name, (key, role) in WANTED.items():
        if name not in got:
            print("missing:", name)
            continue
        l1, l2 = got[name]
        yy, doy = int(l1[18:20]), float(l1[20:32])
        epoch = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(
            time.mktime(time.strptime(f"{2000 + yy if yy < 57 else 1900 + yy}", "%Y")) - time.timezone + (doy - 1) * 86400))
        sats.append({"key": key, "name": name, "norad": int(l1[2:7]), "role": role, "line1": l1, "line2": l2, "epoch": epoch})
    out = {"fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "CelesTrak GP (public TLE)",
           "satellites": sats}
    with open(os.path.join(ROOT, "config", "tle_eo.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(len(sats), "satellites ->", "config/tle_eo.json")


if __name__ == "__main__":
    main()
