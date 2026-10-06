"""Regenerate data/sample_input/, the small offline input of notebooks/blueban813_poc.ipynb.

Source: Microsoft Planetary Computer. Items are found with an anonymous STAC
search (collection ``sentinel-2-l2a``) and every asset URL is signed with
``planetary_computer.sign`` (a short-lived public SAS token: no account, no key).

Everything is read with the pipeline's own code: ``pipeline.watch.load_datatake``
(per-tile decoding with each tile's processing baseline, mosaicking onto a UTM
grid) through ``scripts/build_incidents.py:load_features`` (features, water
mask), on the 20 m analysis grid of incident BB-AE-2024-001 exactly as the
incident builder derives it. The files keep a 12.0 x 11.2 km window of that grid
(same pixels, same alignment): the coast, the whole event and its surroundings.

Files written to data/sample_input/:

* ``s2l2a_20240217_fujairah_20m_dn.tif``: the event acquisition, Sentinel-2A L2A
  item S2A_MSIL2A_20240217T064941_R020_T40RDN_20240217T105525 (2024-02-17
  06:49:41 UTC, processing baseline 05.10). Ten float32 bands of digital numbers
  (B01 B02 B03 B04 B05 B06 B8A B11 B12, SCL). Reflectance is
  (DN + BOA_ADD_OFFSET) / 10000 with BOA_ADD_OFFSET = -1000 for baseline >= 04.00
  (``pipeline.s2_features.dn_to_reflectance``); DN 0 is no-data. The 20 m and
  60 m bands land 1:1 on the grid and are the original integer DN. The 10 m bands
  are averaged onto the 20 m grid by the reader, so they are not integers: B04
  is stored at full float precision (decodes bit-identically: NDCI over clear
  water divides by a near-zero red-edge sum and is sensitive to it), B02 and B03
  are rounded to the nearest DN (at most 0.5 DN = 0.00005 reflectance).
* ``seasonal_baseline_20m.tif``: per-pixel statistics of the same-season
  climatology (36 acquisitions, 2018-2026, within +/-45 days of day-of-year,
  2024 excluded, selected by the incident builder's own rule) for NDCI, MCI, hue
  angle and turbidity: count ``n``, ``median`` and ``mad`` (computed exactly as
  ``pipeline.detect.robust_anomaly`` does), and for NDCI the order statistics
  ``q95`` (the ceil(0.95 n)-th smallest past value: seasonal percentile >= 95
  exactly when the event value exceeds it) and ``max`` (percentile 100 when the
  event value exceeds it). Values are rounded to a fixed binary step before
  storage (see BASELINE_LAYERS) so the file compresses; the manifest's
  reference check shows the event obtained from these files next to the
  full-precision one.
* ``seasonal_baseline_transect.npz``: the FULL climatology (all 36 acquisitions,
  four features, float32) along one west-east row through the event, so the
  notebook can run ``pipeline.detect.robust_anomaly`` itself.
* ``manifest.json``: every STAC item id (event and each baseline acquisition)
  with datetime, platform and processing baseline; grid; bands; checksums; the
  regeneration command; licence and attribution; the reference check.

Usage (from the repository root, with network access):

  python scripts/fetch_sample_input.py              # re-read the exact items listed below
                                                    # (37 datatakes; about 3 minutes)
  python scripts/fetch_sample_input.py --reselect   # also re-derive the climatology list with the
                                                    # incident builder's rule (115 more reads at
                                                    # 120 m, 10-15 minutes) and stop if it differs
  python scripts/fetch_sample_input.py --cache-dir DIR   # keep raw per-datatake reads (resumable)

A regeneration on 2026-10-07 reproduced the committed files byte for byte (the
SHA-256 sums in manifest.json).

This script writes only to data/sample_input/ (or --out). It reads the
committed outputs/detect/AE-FUJ.json and outputs/watch/AE-FUJ.json to derive
the grid and (with --reselect) the climatology, exactly as the incident builder.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform as _platform
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np

# NaN arithmetic over land, cloud and no-data pixels is expected (it also runs in the workers).
warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import yaml  # noqa: E402

import build_incidents as BI  # noqa: E402  (incident builder: window rule + per-datatake worker)
from pipeline import detect, watch  # noqa: E402
from pipeline import s2_features as s2f  # noqa: E402

# --------------------------------------------------------------------------- #
# Fixed parameters (copied from the run that produced BB-AE-2024-001)
# --------------------------------------------------------------------------- #
INCIDENT_ID = "BB-AE-2024-001"
AOI_ID = "AE-FUJ"
EVENT_DATE = "2024-02-17"
HYPOTHESIS = "BLOOM_LIKE"
COLLECTION = "sentinel-2-l2a"
SEARCH_DATES = ("2017-01-01", "2026-09-30")   # the WATCH archive window for AE-FUJ
MAX_CLOUD = 30.0                              # eo:cloud_cover per tile, as WATCH
HALF_KM = 9.0                                 # build_incidents --half-km (default)
RES_M = 20.0                                  # build_incidents --res (default)
CLIM_MAX = 36                                 # build_incidents --clim-max (default)
CLIM_SEED = 813                               # build_incidents: np.random.default_rng(813)
CLIM_WATER_MIN = 0.25                         # build_incidents: 120 m water fraction near the candidate

#: The incident's 20 m grid: EPSG, GDAL-order affine (a, b, c, d, e, f), (rows, cols).
INCIDENT_GRID = {"epsg": 32640, "transform": [20.0, 0.0, 435300.0, 0.0, -20.0, 2786560.0],
                 "shape": [800, 904]}
#: The window kept in the sample files: rows/cols of the incident grid (end exclusive).
WINDOW = {"row0": 200, "row1": 800, "col0": 0, "col1": 560}

#: The event datatake (date_Rorbit_platform) and its STAC item ids in mosaic order.
EVENT = {"tag": "2024-02-17_R020_2A",
         "items": ["S2A_MSIL2A_20240217T064941_R020_T40RDN_20240217T105525"]}

#: The 36 same-season climatology datatakes, as selected by scripts/build_incidents.py
#: for BB-AE-2024-001 (re-derive and compare with --reselect). Item ids are in mosaic
#: order (the first item covering a pixel wins).
CLIMATOLOGY_JSON = r"""
[
 {"tag": "2018-01-14_R020_2B", "items": ["S2B_MSIL2A_20180114T065229_R020_T40RDN_20201025T201845"]},
 {"tag": "2018-01-19_R020_2A", "items": ["S2A_MSIL2A_20180119T065201_R020_T40RDN_20201014T065252"]},
 {"tag": "2018-01-24_R020_2B", "items": ["S2B_MSIL2A_20180124T065149_R020_T40RDN_20201025T215020"]},
 {"tag": "2018-02-03_R020_2B", "items": ["S2B_MSIL2A_20180203T065059_R020_T40RDN_20201013T183255"]},
 {"tag": "2018-03-05_R020_2B", "items": ["S2B_MSIL2A_20180305T064739_R020_T40RDN_20201013T070026"]},
 {"tag": "2018-03-20_R020_2A", "items": ["S2A_MSIL2A_20180320T064621_R020_T40RDN_20201013T113230"]},
 {"tag": "2019-01-29_R020_2B", "items": ["S2B_MSIL2A_20190129T065129_R020_T40RDN_20201008T054254"]},
 {"tag": "2019-02-03_R020_2A", "items": ["S2A_MSIL2A_20190203T065101_R020_T40RDN_20201007T133512"]},
 {"tag": "2019-02-08_R020_2B", "items": ["S2B_MSIL2A_20190208T065029_R020_T40RDN_20201007T150732"]},
 {"tag": "2019-02-13_R020_2A", "items": ["S2A_MSIL2A_20190213T065001_R020_T40RDN_20201007T162109"]},
 {"tag": "2019-02-23_R020_2A", "items": ["S2A_MSIL2A_20190223T064851_R020_T40RDN_20201030T022514"]},
 {"tag": "2019-03-05_R020_2A", "items": ["S2A_MSIL2A_20190305T064741_R020_T40RDN_20201030T153909"]},
 {"tag": "2019-03-30_R020_2B", "items": ["S2B_MSIL2A_20190330T064629_R020_T40RDN_20201007T122813"]},
 {"tag": "2020-01-04_R020_2B", "items": ["S2B_MSIL2A_20200104T065249_R020_T40RDN_20201002T225336"]},
 {"tag": "2020-02-08_R020_2A", "items": ["S2A_MSIL2A_20200208T065021_R020_T40RDN_20201001T082208"]},
 {"tag": "2020-02-28_R020_2A", "items": ["S2A_MSIL2A_20200228T064821_R020_T40RDN_20200928T220645"]},
 {"tag": "2021-01-28_R020_2B", "items": ["S2B_MSIL2A_20210128T065129_R020_T40RDN_20210130T001436"]},
 {"tag": "2021-02-17_R020_2B", "items": ["S2B_MSIL2A_20210217T064929_R020_T40RDN_20210219T045642"]},
 {"tag": "2021-02-27_R020_2B", "items": ["S2B_MSIL2A_20210227T064829_R020_T40RDN_20210227T154256"]},
 {"tag": "2021-03-14_R020_2A", "items": ["S2A_MSIL2A_20210314T064641_R020_T40RDN_20210314T204618"]},
 {"tag": "2021-03-19_R020_2B", "items": ["S2B_MSIL2A_20210319T064629_R020_T40RDN_20210319T192203"]},
 {"tag": "2021-04-03_R020_2A", "items": ["S2A_MSIL2A_20210403T064621_R020_T40RDN_20210613T090711"]},
 {"tag": "2022-01-13_R020_2B", "items": ["S2B_MSIL2A_20220113T065229_R020_T40RDN_20220113T173822"]},
 {"tag": "2022-01-23_R020_2B", "items": ["S2B_MSIL2A_20220123T065149_R020_T40RDN_20220123T233448"]},
 {"tag": "2022-02-07_R020_2A", "items": ["S2A_MSIL2A_20220207T065031_R020_T40RDN_20220219T215142"]},
 {"tag": "2022-02-12_R020_2B", "items": ["S2B_MSIL2A_20220212T065009_R020_T40RDN_20220222T043519"]},
 {"tag": "2022-02-17_R020_2A", "items": ["S2A_MSIL2A_20220217T064941_R020_T40RDN_20220224T131159"]},
 {"tag": "2022-02-27_R020_2A", "items": ["S2A_MSIL2A_20220227T064831_R020_T40RDN_20220302T181759"]},
 {"tag": "2023-03-04_R020_2A", "items": ["S2A_MSIL2A_20230304T064751_R020_T40RDN_20240819T072511", "S2A_MSIL2A_20230304T064751_R020_T40RDN_20230304T121437"]},
 {"tag": "2025-01-12_R020_2A", "items": ["S2A_MSIL2A_20250112T065241_R020_T40RDN_20250112T101851"]},
 {"tag": "2025-02-01_R020_2C", "items": ["S2C_MSIL2A_20250201T065141_R020_T40RDN_20250201T104612"]},
 {"tag": "2025-02-26_R020_2B", "items": ["S2B_MSIL2A_20250226T064739_R020_T40RDN_20250226T085342"]},
 {"tag": "2025-03-23_R020_2C", "items": ["S2C_MSIL2A_20250323T064651_R020_T40RDN_20250323T123317"]},
 {"tag": "2026-01-12_R020_2B", "items": ["S2B_MSIL2A_20260112T065139_R020_T40RDN_20260112T090525"]},
 {"tag": "2026-01-22_R020_2B", "items": ["S2B_MSIL2A_20260122T065059_R020_T40RDN_20260122T090256"]},
 {"tag": "2026-02-11_R020_2A", "items": ["S2A_MSIL2A_20260211T070201_R020_T40RDN_20260211T094207"]}
]
"""
CLIMATOLOGY = json.loads(CLIMATOLOGY_JSON)

BANDS = list(watch.SCREEN_BANDS)          # B01 B02 B03 B04 B05 B06 B8A B11 B12
#: 10 m bands: the reader averages them onto the 20 m grid (non-integer DN).
EXACT_FLOAT_BANDS = ("B04",)              # kept bit-exact as float DN
ROUNDED_BANDS = ("B02", "B03")            # rounded to the nearest DN
BASELINE_FEATURES = ("NDCI", "MCI", "HUE_ANGLE", "TUR_NECHAD2016")
#: Stored baseline layers and the binary rounding step 2**k applied before storage
#: (None = stored exactly). Rounding to a power of two zeroes the low mantissa bits,
#: which is what lets the float32 GeoTIFF compress.
BASELINE_LAYERS = [
    ("NDCI_n", None), ("NDCI_median", -13), ("NDCI_mad", -13), ("NDCI_q95", -13), ("NDCI_max", -8),
    ("MCI_n", None), ("MCI_median", -22), ("MCI_mad", -22),
    ("HUE_ANGLE_n", None), ("HUE_ANGLE_median", -6), ("HUE_ANGLE_mad", -2),
    ("TUR_NECHAD2016_n", None), ("TUR_NECHAD2016_median", -5),
]

EVENT_FILE = "s2l2a_20240217_fujairah_20m_dn.tif"
BASELINE_FILE = "seasonal_baseline_20m.tif"
TRANSECT_FILE = "seasonal_baseline_transect.npz"

LICENCE = ("Copernicus Sentinel data are free and open (Copernicus Sentinel Data Terms and Conditions; "
           "Commission Delegated Regulation (EU) No 1159/2013).")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class SubGrid:
    """Minimal grid record (epsg, affine transform, shape) for the sample window."""
    epsg: int
    transform: object
    shape: tuple


# --------------------------------------------------------------------------- #
# Grid: derived exactly as scripts/build_incidents.py does, then checked
# --------------------------------------------------------------------------- #
def derive_grid() -> dict:
    from pyproj import Transformer
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "aois_uae.yaml"), encoding="utf-8"))["aois"]
    aoi = cfg[AOI_ID]
    det = json.load(open(os.path.join(ROOT, "outputs", "detect", f"{AOI_ID}.json"), encoding="utf-8"))
    ws = json.load(open(os.path.join(ROOT, "outputs", "watch", f"{AOI_ID}.json"), encoding="utf-8"))
    cands = [c for c in det["candidates"] if c["date"] == EVENT_DATE and c["hypothesis"] == HYPOTHESIS]
    cand = max(cands, key=lambda c: c["area_km2"] * (c["features"].get("robust_z_primary") or 0))
    g120 = watch.AoiGrid.from_bbox(AOI_ID, aoi["bbox"], ws["grid"]["resolution_m"])
    r, c = cand["centroid_rc"]
    cx, cy = g120.transform * (c + 0.5, r + 0.5)
    lon0, lat0 = Transformer.from_crs(f"EPSG:{g120.epsg}", "EPSG:4326", always_xy=True).transform(cx, cy)
    win = BI._grid_window((lon0, lat0), HALF_KM, aoi["bbox"])
    grid = watch.AoiGrid.from_bbox(INCIDENT_ID, win, RES_M)
    got = {"epsg": grid.epsg, "transform": [float(v) for v in list(grid.transform)[:6]],
           "shape": [int(v) for v in grid.shape]}
    if got != INCIDENT_GRID:
        raise SystemExit(f"derived grid {got} differs from the documented grid {INCIDENT_GRID}")
    from affine import Affine
    sub = SubGrid(grid.epsg, grid.transform * Affine.translation(WINDOW["col0"], WINDOW["row0"]),
                  (WINDOW["row1"] - WINDOW["row0"], WINDOW["col1"] - WINDOW["col0"]))
    return {"grid": grid, "sub": sub, "aoi": aoi, "cand": cand, "g120": g120, "window_lonlat": win,
            "candidate_lonlat": [lon0, lat0], "watch": ws, "det": det}


def crop(a: np.ndarray) -> np.ndarray:
    return a[..., WINDOW["row0"]:WINDOW["row1"], WINDOW["col0"]:WINDOW["col1"]]


# --------------------------------------------------------------------------- #
# STAC access
# --------------------------------------------------------------------------- #
def items_by_id(ids: list) -> dict:
    from pystac_client import Client
    cat = Client.open(watch.PC_STAC)
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        for it in cat.search(collections=[COLLECTION], ids=chunk, max_items=len(chunk)).items():
            out[it.id] = it
    missing = [i for i in ids if i not in out]
    if missing:
        raise SystemExit(f"STAC items not found on Planetary Computer: {missing}")
    return out


def _key_from_items(items) -> tuple:
    p = items[0].properties
    return (p["datetime"][:10], p.get("sat:relative_orbit") or 0, p.get("platform"))


# --------------------------------------------------------------------------- #
# --reselect: the incident builder's climatology selection, re-run
# --------------------------------------------------------------------------- #
def _water_fraction_120(args):
    """Worker: one datatake on the 120 m AOI grid -> water fraction near the candidate.

    Same reader and water mask as pipeline.watch.process_datatake, whose cached
    ``water`` array scripts/build_incidents.py tests (> 0.25) for this selection.
    """
    tag, item_dicts, grid_d, sub = args
    import pystac
    items = [pystac.Item.from_dict(d) for d in item_dicts]
    grid = watch._grid_from_dict(grid_d)
    try:
        refl, scl, _ = watch.load_datatake(items, grid)
        water, _ = s2f.water_quality_mask(refl, scl, pixel_size_m=grid.resolution_m,
                                          shoreline_buffer_m=max(40.0, grid.resolution_m))
        r0, r1, c0, c1 = sub
        return {"tag": tag, "ok": True, "fraction": float(water[r0:r1, c0:c1].mean())}
    except Exception as e:                                    # recorded, never hidden
        return {"tag": tag, "ok": False, "error": repr(e)[:300]}


def reselect(ctx: dict, workers: int) -> dict:
    ws, cand = ctx["watch"], ctx["cand"]
    files = sorted(r["cache_file"] for r in ws["rows"] if r.get("cache_file"))
    dates = [dt.date.fromisoformat(f[:10]) for f in files]
    t_idx = files.index(cand["cache_file"])
    clim_idx = detect.climatology_indices(dates, t_idx, ctx["det"]["window_days"])
    r0, c0, r1, c1 = [int(v) for v in cand["bbox_rc"]]
    sub = (max(0, r0 - 30), r1 + 30, max(0, c0 - 30), c1 + 30)
    log(f"reselect: {len(clim_idx)} same-season datatakes in other years; reading each at 120 m")
    groups = watch.search_items(ctx["aoi"]["bbox"], *SEARCH_DATES, MAX_CLOUD)
    by_tag = {watch.datatake_tag(*k): items for k, items in groups}
    gd = watch._grid_to_dict(ctx["g120"])
    tasks = [(files[i][:-4], [it.to_dict() for it in by_tag[files[i][:-4]]], gd, sub)
             for i in clim_idx if files[i][:-4] in by_tag]
    fr = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(_water_fraction_120, tasks):
            fr[res["tag"]] = res
    good = [i for i in clim_idx if (fr.get(files[i][:-4]) or {}).get("fraction", 0.0) > CLIM_WATER_MIN]
    rng = np.random.default_rng(CLIM_SEED)
    if len(good) > CLIM_MAX:
        good = sorted(rng.choice(good, CLIM_MAX, replace=False).tolist())
    win_groups = watch.search_items(ctx["window_lonlat"], *SEARCH_DATES, MAX_CLOUD)
    wt = {watch.datatake_tag(*k): [it.id for it in items] for k, items in win_groups}
    derived = [{"tag": files[i][:-4], "items": wt[files[i][:-4]]} for i in good if files[i][:-4] in wt]
    return {"n_same_season_other_years": len(clim_idx),
            "n_water_fraction_gt_0.25": sum(1 for r in fr.values() if r.get("fraction", 0) > CLIM_WATER_MIN),
            "n_failed_reads": sum(1 for r in fr.values() if not r.get("ok")),
            "derived": derived}


# --------------------------------------------------------------------------- #
# Reading (the incident builder's own worker)
# --------------------------------------------------------------------------- #
FEATURE_KEYS = ("NDCI", "MCI", "TUR_NECHAD2016", "HUE_ANGLE", "FAI", "SPM_NECHAD2016")


def read_datatakes(entries: list, grid, workers: int, cache_dir: str | None):
    """Yield scripts/build_incidents.load_features results for {tag, items} entries."""
    todo, cached = [], {}
    for e in entries:
        p = os.path.join(cache_dir, f"{e['tag']}.npz") if cache_dir else None
        if p and os.path.exists(p):
            cached[e["tag"]] = p
        else:
            todo.append(e)
    for tag, p in cached.items():
        z = np.load(p, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        yield {"key": tuple(meta["key"]), "ok": True, "water": z["water"], "body": z["body"],
               "feats": {k: z[f"f_{k}"] for k in FEATURE_KEYS}, "meta": meta["meta"],
               "quality": meta["quality"], "refl": {b: z[f"r_{b}"] for b in BANDS}, "scl": z["scl"]}
    if not todo:
        return
    stac = items_by_id([i for e in todo for i in e["items"]])
    gd = watch._grid_to_dict(grid)
    tasks = []
    for e in todo:
        items = [stac[i] for i in e["items"]]
        tasks.append((_key_from_items(items), [it.to_dict() for it in items], gd))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(BI.load_features, tasks):
            if not res["ok"]:
                raise SystemExit(f"datatake {res['key']} failed: {res.get('error')}")
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
                tag = watch.datatake_tag(*res["key"])
                np.savez(os.path.join(cache_dir, f"{tag}.npz"), water=res["water"], body=res["body"],
                         scl=res["scl"], meta=json.dumps({"key": list(res["key"]), "meta": res["meta"],
                                                          "quality": res["quality"]}),
                         **{f"f_{k}": res["feats"][k] for k in FEATURE_KEYS},
                         **{f"r_{b}": res["refl"][b] for b in BANDS})
            yield res


# --------------------------------------------------------------------------- #
# Encoding
# --------------------------------------------------------------------------- #
def encode_dn(refl: np.ndarray, baseline: str, mode: str):
    """Float32 DN for one band, checked against pipeline.s2_features.dn_to_reflectance.

    mode ``integer``: the reader's values must already be integer DN (bit-identical
    round trip). ``exact``: the float32 DN that decodes bit-identically to the
    reader's reflectance. ``rounded``: nearest integer DN. Returns (dn, max |error|
    in DN); 0 = no data.
    """
    off = s2f.boa_offset_for_baseline(baseline)
    fin = np.isfinite(refl)
    raw = refl.astype("float64") * s2f.S2_QUANTIFICATION - off
    if mode == "exact":
        dn = np.where(fin, raw, 0).astype("float32")
        bad = fin & (s2f.dn_to_reflectance(dn, baseline) != refl)
        for step in (1, -1, 2, -2, 3, -3):                    # float32 division: try neighbours
            if not bad.any():
                break
            cand = dn.copy()
            for _ in range(abs(step)):
                cand = np.nextafter(cand, np.float32(np.inf if step > 0 else -np.inf))
            ok = bad & (s2f.dn_to_reflectance(cand, baseline) == refl)
            dn[ok] = cand[ok]
            bad &= ~ok
        if bad.any():
            raise SystemExit(f"{int(bad.sum())} pixels have no bit-exact float32 DN")
    else:
        dn = np.where(fin, np.rint(raw), 0).astype("float32")
    if fin.any() and (dn[fin].min() < 1 or dn[fin].max() > 65535):
        raise SystemExit("DN outside 1..65535")
    err = float(np.max(np.abs(dn[fin] - raw[fin]))) if fin.any() else 0.0
    if mode == "integer":
        back = s2f.dn_to_reflectance(dn, baseline)
        if err > 1e-3 or not bool(((back == refl) | (np.isnan(back) & ~fin)).all()):
            raise SystemExit(f"band is not an integer DN grid (max error {err:.3f})")
    return dn, err


def binround(a: np.ndarray, k: int | None) -> np.ndarray:
    """Round to a multiple of 2**k (k None: unchanged), as float32."""
    if k is None:
        return a.astype("float32")
    s = 2.0 ** k
    return np.where(np.isfinite(a), np.rint(a.astype("float64") / s) * s, np.nan).astype("float32")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def order_stat(sorted_stack: np.ndarray, k: np.ndarray) -> np.ndarray:
    """k-th smallest finite value per pixel (k is 1-based; NaN where k < 1)."""
    kk = np.clip(k - 1, 0, sorted_stack.shape[0] - 1)
    v = np.take_along_axis(sorted_stack, kk[None], 0)[0]
    return np.where(k >= 1, v, np.nan).astype("float32")


def baseline_layers(stack: np.ndarray, name: str) -> dict:
    """Per-pixel climatology statistics of one feature (full precision).

    ``median`` and ``mad`` use pipeline.detect.fast_nanmedian on float32, as
    robust_anomaly does. robust_anomaly's percentile is 100 * #(clim < x) / n, so
    pct >= 95 holds exactly when x > the ceil(0.95 n)-th smallest value (``q95``)
    and pct = 100 when x > ``max``.
    """
    n = np.sum(np.isfinite(stack), axis=0).astype("int32")
    with np.errstate(invalid="ignore"):
        med = detect.fast_nanmedian(stack, 0)
        mad = detect.fast_nanmedian(np.abs(stack - med), 0)
    srt = np.sort(stack, axis=0)                      # NaN sort last
    k95 = np.ceil(0.95 * n - 1e-9).astype("int32")
    out = {f"{name}_n": n.astype("float32"), f"{name}_median": med.astype("float32"),
           f"{name}_mad": mad.astype("float32"), f"{name}_q95": order_stat(srt, k95),
           f"{name}_max": order_stat(srt, n)}
    for k in out:
        if not k.endswith("_n"):
            out[k] = np.where(n > 0, out[k], np.nan).astype("float32")
    return out


# --------------------------------------------------------------------------- #
# The event rule (scripts/build_incidents.py, --keep all) and its summary
# --------------------------------------------------------------------------- #
def event_from_maps(water, z, pct_ge95, z_mci, grid, lon0, lat0) -> np.ndarray:
    from pyproj import Transformer
    from scipy import ndimage as ndi
    hit = water & (z >= detect.Z_MIN) & pct_ge95
    for name, sign in detect.HYPOTHESIS_FEATURES[HYPOTHESIS][1:]:
        hit &= (sign * np.nan_to_num(z_mci)) >= 1.0
    hit = ndi.binary_opening(hit, iterations=1)
    lab, nlab = ndi.label(hit)
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{grid.epsg}", always_xy=True)
    ex_, ey_ = tr.transform(lon0, lat0)
    cc0 = int((ex_ - grid.transform.c) / grid.transform.a)
    rr0 = int((ey_ - grid.transform.f) / grid.transform.e)
    sizes = ndi.sum(hit, lab, range(1, nlab + 1)) if nlab else []
    rad = int(1500 / RES_M)
    near = lab[max(0, rr0 - rad):rr0 + rad, max(0, cc0 - rad):cc0 + rad]
    keep = set(np.unique(near[near > 0]).tolist())
    min_px = max(1, int(detect.MIN_AREA_KM2 * 1e6 / 4 / RES_M ** 2))
    keep |= {k for k in range(1, nlab + 1) if sizes[k - 1] >= min_px}
    if not keep and nlab:
        keep = {int(np.argmax(sizes)) + 1}
    return np.isin(lab, list(keep))


def event_summary(event, water, body, x: dict, z: dict, pct_ndci, n: dict, med: dict) -> dict:
    from scipy import ndimage as ndi

    def m(a):
        v = a[event]
        v = v[np.isfinite(v)]
        return round(float(np.median(v)), 6) if v.size else None
    dist = ndi.distance_transform_edt(ndi.binary_fill_holes(body | water)) * RES_M / 1000.0
    npx = int(event.sum())
    return {"n_px": npx, "area_km2": round(npx * RES_M ** 2 / 1e6, 4), "water_px": int(water.sum()),
            "ndci_value": m(x["NDCI"]), "ndci_z": m(z["NDCI"]), "ndci_pct": m(pct_ndci),
            "n_seasonal_ndci": int(np.median(n["NDCI"][event])) if npx else None,
            "n_seasonal_mci": int(np.median(n["MCI"][event])) if npx else None,
            "n_seasonal_hue": int(np.median(n["HUE_ANGLE"][event])) if npx else None,
            "ndci_baseline_median": m(med["NDCI"]), "mci_value": m(x["MCI"]), "mci_z": m(z["MCI"]),
            "mci_baseline_median": m(med["MCI"]), "hue_value": m(x["HUE_ANGLE"]), "hue_z": m(z["HUE_ANGLE"]),
            "hue_baseline_median": m(med["HUE_ANGLE"]), "tur_value": m(x["TUR_NECHAD2016"]),
            "tur_baseline_median": m(med["TUR_NECHAD2016"]), "dist_coast_km": m(dist)}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "sample_input"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--reselect", action="store_true",
                    help="re-derive the climatology list with the incident builder's rule and compare")
    ap.add_argument("--cache-dir", default=None, help="keep raw per-datatake reads here (resumable)")
    a = ap.parse_args()
    t0 = time.time()
    import rasterio

    ctx = derive_grid()
    grid, sub = ctx["grid"], ctx["sub"]
    lon0, lat0 = ctx["candidate_lonlat"]
    log(f"incident grid EPSG:{grid.epsg} {grid.shape[0]} x {grid.shape[1]} px @ {RES_M:.0f} m; sample window "
        f"rows {WINDOW['row0']}-{WINDOW['row1'] - 1}, cols {WINDOW['col0']}-{WINDOW['col1'] - 1}")

    reselect_report = None
    if a.reselect:
        rs = reselect(ctx, a.workers)
        same = rs["derived"] == CLIMATOLOGY
        reselect_report = {k: v for k, v in rs.items() if k != "derived"} | {
            "selected": [e["tag"] for e in rs["derived"]], "identical_to_documented_list": same}
        log(f"reselect: {len(rs['derived'])} selected; identical to the documented list: {same}")
        if not same:
            print("CLIMATOLOGY_JSON = " + json.dumps(rs["derived"], indent=0))
            raise SystemExit("the re-derived climatology differs from the documented list (printed above)")

    # ---- event (full incident grid, as the incident builder) -------------------------
    log(f"reading the event datatake {EVENT['tag']}")
    ev = list(read_datatakes([EVENT], grid, 1, a.cache_dir))[0]
    meta = ev["meta"]
    if len(meta["processing_baselines"]) != 1:
        raise SystemExit(f"event mosaic mixes processing baselines {meta['processing_baselines']}")
    baseline = meta["processing_baselines"][0]
    water, body, refl_full = ev["water"], ev["body"], ev["refl"]
    F = {k: ev["feats"][k] for k in BASELINE_FEATURES}

    # ---- climatology --------------------------------------------------------------
    log(f"reading {len(CLIMATOLOGY)} climatology datatakes at {RES_M:.0f} m")
    order = [e["tag"] for e in CLIMATOLOGY]
    stacks = {k: [None] * len(order) for k in BASELINE_FEATURES}
    clim_meta = {}
    for res in read_datatakes(CLIMATOLOGY, grid, a.workers, a.cache_dir):
        tag = watch.datatake_tag(*res["key"])
        i = order.index(tag)
        for k in BASELINE_FEATURES:
            stacks[k][i] = np.where(res["water"], res["feats"][k], np.nan).astype("float32")
        m = res["meta"]
        clim_meta[tag] = {"tag": tag, "datetime": m["datetime"], "platform": m["platform"],
                          "relative_orbit": m["relative_orbit"], "stac_item_ids": m["item_ids"],
                          "skipped_redundant_tiles": m["skipped_redundant_tiles"],
                          "processing_baselines": m["processing_baselines"],
                          "water_px_incident_grid": int(res["water"].sum())}
    if sorted(clim_meta) != sorted(order):
        raise SystemExit("climatology reads incomplete")
    S = {k: np.stack(v) for k, v in stacks.items()}

    # ---- full-precision reference on the full incident grid (what build_incidents computes) ----
    ref = {k: detect.robust_anomaly(np.where(water, F[k], np.nan), S[k], detect.FLOORS[k])
           for k in BASELINE_FEATURES}
    ev_full = event_from_maps(water, ref["NDCI"][0], ref["NDCI"][1] >= detect.PCT_MIN, ref["MCI"][0],
                              grid, lon0, lat0)
    s_full = event_summary(ev_full, water, body, {k: np.where(water, F[k], np.nan) for k in BASELINE_FEATURES},
                           {k: ref[k][0] for k in BASELINE_FEATURES}, ref["NDCI"][1],
                           {k: ref[k][2] for k in BASELINE_FEATURES}, {k: ref[k][3] for k in BASELINE_FEATURES})
    if crop(ev_full).sum() != ev_full.sum():
        raise SystemExit("the event polygon is not fully inside the sample window")
    log(f"full precision: event {s_full['n_px']} px = {s_full['area_km2']} km2, NDCI z {s_full['ndci_z']:.4f}")

    # ---- write the event clip ----------------------------------------------------------
    os.makedirs(a.out, exist_ok=True)
    prof = {"driver": "GTiff", "height": sub.shape[0], "width": sub.shape[1], "crs": f"EPSG:{sub.epsg}",
            "transform": sub.transform, "compress": "deflate", "zlevel": 9, "tiled": True,
            "blockxsize": 256, "blockysize": 256, "interleave": "band", "predictor": 3, "dtype": "float32"}
    lam = s2f.S2_CENTRES_NM[meta["platform"]]
    dn, dn_err = {}, {}
    for b in BANDS:
        mode = "exact" if b in EXACT_FLOAT_BANDS else "rounded" if b in ROUNDED_BANDS else "integer"
        dn[b], dn_err[b] = encode_dn(crop(refl_full[b]), baseline, mode)
    ev_path = os.path.join(a.out, EVENT_FILE)
    with rasterio.open(ev_path, "w", count=len(BANDS) + 1, nodata=0, **prof) as dst:
        for i, b in enumerate(BANDS, 1):
            dst.write(dn[b], i)
            dst.set_band_description(i, b)
            prec = ("float DN, bit-exact pipeline value (10 m band averaged to 20 m)" if b in EXACT_FLOAT_BANDS
                    else "nearest integer DN of the pipeline value (10 m band averaged to 20 m)"
                    if b in ROUNDED_BANDS else "original integer DN")
            dst.update_tags(i, band=b, central_wavelength_nm=lam[b], native_resolution_m=s2f.S2_NATIVE_RES_M[b],
                            precision=prec)
        dst.write(crop(ev["scl"]).astype("float32"), len(BANDS) + 1)
        dst.set_band_description(len(BANDS) + 1, "SCL")
        dst.update_tags(len(BANDS) + 1, band="SCL", precision="Sen2Cor scene classification class (0 = no data)")
        dst.update_tags(
            STAC_ITEMS=",".join(meta["item_ids"]), DATETIME_UTC=meta["datetime"], PLATFORM=meta["platform"],
            PROCESSING_BASELINE=baseline, BOA_ADD_OFFSET=str(s2f.boa_offset_for_baseline(baseline)),
            QUANTIFICATION_VALUE=str(s2f.S2_QUANTIFICATION), NODATA_DN="0",
            REFLECTANCE="(DN + BOA_ADD_OFFSET) / QUANTIFICATION_VALUE (pipeline.s2_features.dn_to_reflectance)",
            SOURCE="Microsoft Planetary Computer, collection sentinel-2-l2a",
            ATTRIBUTION="Contains modified Copernicus Sentinel data 2024",
            GENERATED_BY="scripts/fetch_sample_input.py")
    log(f"wrote {EVENT_FILE} ({os.path.getsize(ev_path) / 1e6:.2f} MB)")

    # ---- write the baseline -----------------------------------------------------------
    full_layers = {}
    for k in BASELINE_FEATURES:
        full_layers.update(baseline_layers(S[k], k))
    names = [n_ for n_, _ in BASELINE_LAYERS]
    stored = {n_: binround(crop(full_layers[n_]), k2) for n_, k2 in BASELINE_LAYERS}
    bl_path = os.path.join(a.out, BASELINE_FILE)
    with rasterio.open(bl_path, "w", count=len(names), nodata=float("nan"), **prof) as dst:
        for i, (n_, k2) in enumerate(BASELINE_LAYERS, 1):
            dst.write(stored[n_], i)
            dst.set_band_description(i, n_)
            dst.update_tags(i, rounding=("exact" if k2 is None else f"multiple of 2^{k2} = {2.0 ** k2:.3g}"))
        dst.update_tags(
            FEATURES=",".join(BASELINE_FEATURES), N_ACQUISITIONS=str(len(order)),
            WINDOW_DAYS=str(ctx["det"]["window_days"]), EXCLUDED_YEAR=EVENT_DATE[:4],
            STATISTICS="n = finite count; median, mad = pipeline.detect.fast_nanmedian (as robust_anomaly); "
                       "q95 = ceil(0.95 n)-th smallest (pct >= 95 iff x > q95); max (pct = 100 iff x > max)",
            Z="z = (x - median) / (1.4826 * mad + pipeline.detect.FLOORS[feature]), valid where n >= 6",
            WATER_MASK="per acquisition: s2_features.water_quality_mask(hole_buffer=False, 60 m buffer)",
            ATTRIBUTION="Contains modified Copernicus Sentinel data 2018-2026",
            GENERATED_BY="scripts/fetch_sample_input.py")
    log(f"wrote {BASELINE_FILE} ({os.path.getsize(bl_path) / 1e6:.2f} MB)")

    # ---- transect: full climatology along the event row nearest the event centroid ----
    evc = crop(ev_full)
    rows_with_event = np.where(evc.any(axis=1))[0]
    row = int(rows_with_event[np.argmin(np.abs(rows_with_event - np.where(evc)[0].mean()))])
    tr_path = os.path.join(a.out, TRANSECT_FILE)
    np.savez_compressed(tr_path, row=np.int32(row), incident_grid_row=np.int32(row + WINDOW["row0"]),
                        tags=np.array(order), datetimes=np.array([clim_meta[t]["datetime"] for t in order]),
                        **{k: crop(S[k])[:, row, :].astype("float32") for k in BASELINE_FEATURES})
    log(f"wrote {TRANSECT_FILE} ({os.path.getsize(tr_path) / 1e6:.2f} MB, window row {row})")

    # ---- reference check: the event from the stored files vs full precision ----------
    with rasterio.open(bl_path) as src:
        B = {src.descriptions[i]: src.read(i + 1) for i in range(src.count)}
    with rasterio.open(ev_path) as src:
        D = {src.descriptions[i]: src.read(i + 1) for i in range(src.count)}
    refl_b = {b: s2f.dn_to_reflectance(D[b], baseline) for b in BANDS}
    feats_b = s2f.compute_features(refl_b, platform=meta["platform"])
    water_b, _ = s2f.water_quality_mask(refl_b, D["SCL"].astype("uint8"), pixel_size_m=RES_M,
                                        shoreline_buffer_m=60, hole_buffer=False)
    body_b = (np.isfinite(refl_b["B03"]) & np.isfinite(refl_b["B11"]) & (refl_b["B11"] < 0.10)
              & ((refl_b["B03"] - refl_b["B11"]) > 0))
    xb = {k: np.where(water_b, feats_b[k], np.nan) for k in BASELINE_FEATURES}

    def zf(name):
        sc = 1.4826 * B[f"{name}_mad"] + detect.FLOORS[name]
        z = (xb[name] - B[f"{name}_median"]) / sc
        return np.where((B[f"{name}_n"] >= detect.MIN_CLIM_N) & np.isfinite(xb[name]), z, np.nan).astype("float32")

    zb = {k: zf(k) for k in BASELINE_FEATURES if f"{k}_mad" in B}      # turbidity: median only
    okn = B["NDCI_n"] >= detect.MIN_CLIM_N
    with np.errstate(invalid="ignore"):
        ge95 = okn & (xb["NDCI"] > B["NDCI_q95"])
        p100 = okn & (xb["NDCI"] > B["NDCI_max"])
    ev_b = event_from_maps(water_b, zb["NDCI"], ge95, zb["MCI"], sub, lon0, lat0)
    s_b = event_summary(ev_b, water_b, body_b, xb, zb, np.where(p100, 100.0, np.where(ge95, 95.0, 0.0)),
                        {k: B[f"{k}_n"] for k in BASELINE_FEATURES}, {k: B[f"{k}_median"] for k in BASELINE_FEATURES})
    inc = json.load(open(os.path.join(ROOT, "outputs", "incidents", f"{INCIDENT_ID}.json"), encoding="utf-8"))
    wq = inc["water_quality"]["features"]
    check = {
        "committed_incident": {"area_km2": inc["area_km2"], "ndci_z": wq["NDCI"]["z"],
                               "ndci_pct": wq["NDCI"]["seasonal_percentile"],
                               "n_seasonal": inc["temporal"]["n_seasonal"], "ndci_value": wq["NDCI"]["value"],
                               "mci_value": wq["MCI"]["value"], "mci_baseline_median": wq["MCI"]["baseline_median"],
                               "hue_value": wq["HUE_ANGLE"]["value"],
                               "hue_baseline_median": wq["HUE_ANGLE"]["baseline_median"],
                               "dist_coast_km": inc["model_features"]["dist_shore_km"]},
        "full_precision_incident_grid": s_full,
        "from_sample_files": s_b,
        "event_mask_identical": bool(np.array_equal(crop(ev_full), ev_b)),
        "max_abs_ndci_z_difference_water": float(np.nanmax(np.abs(np.where(crop(water) & water_b, zb["NDCI"] - crop(ref["NDCI"][0]), np.nan)))),
        "pct_ge95_identical_on_common_water": bool(np.array_equal((crop(ref["NDCI"][1]) >= detect.PCT_MIN) & crop(water) & water_b,
                                                                  ge95 & crop(water) & water_b)),
        "water_mask_px_differing": int((crop(water) != water_b).sum()),
        "dn_rounding_max_abs": {b: round(dn_err[b], 4) for b in ROUNDED_BANDS},
        "notes": ["full_precision_incident_grid: the reader's values and the 36-acquisition climatology at full "
                  "precision on the full 800 x 904 incident grid (what scripts/build_incidents.py computes)",
                  "from_sample_files: the same rule on the files in this folder (12.0 x 11.2 km window, B02/B03 "
                  "rounded to integer DN, baseline layers rounded to binary steps); ndci_pct there is the exact "
                  "percentile class (0 = below 95, 95 = 95 to <100, 100 = above every past value)",
                  "water_mask_px_differing: pixels whose analysable-water flag changes because B02/B03 are "
                  "rounded (MNDWI near 0 at the coast and at ships; the 60 m buffer enlarges each flip)"]}
    log(f"reference check: event {s_full['n_px']} px (full precision) vs {s_b['n_px']} px (sample files), "
        f"identical: {check['event_mask_identical']}")

    # ---- manifest ---------------------------------------------------------------------------
    import pystac_client
    bl_ll = watch.AoiGrid(INCIDENT_ID, (0, 0, 0, 0), sub.epsg, sub.transform, sub.shape, RES_M).lonlat_bounds()
    clim_rows = [clim_meta[t] for t in order]
    years = sorted({r["datetime"][:4] for r in clim_rows})
    T = list(sub.transform)[:6]
    manifest = {
        "name": "BLUEBAN 813 sample input: BB-AE-2024-001 (Fujairah, UAE, 17 Feb 2024)",
        "purpose": "Offline input of notebooks/blueban813_poc.ipynb: the event acquisition and the per-pixel "
                   "same-season baseline on the incident's own 20 m grid.",
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regenerate": {"command": "python scripts/fetch_sample_input.py",
                       "audit_climatology_selection": "python scripts/fetch_sample_input.py --reselect",
                       "network": "anonymous HTTPS to planetarycomputer.microsoft.com and *.blob.core.windows.net",
                       "credentials": "none",
                       "environment_used": {"python": _platform.python_version(), "numpy": np.__version__,
                                            "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__,
                                            "pystac_client": pystac_client.__version__}},
        "source": {"stac_api": watch.PC_STAC, "collection": COLLECTION,
                   "signing": "planetary_computer.sign (anonymous SAS token)",
                   "search": {"datetime": f"{SEARCH_DATES[0]}/{SEARCH_DATES[1]}",
                              "max_eo_cloud_cover_per_tile": MAX_CLOUD,
                              "bbox_lonlat": [round(v, 8) for v in ctx["window_lonlat"]]}},
        "grid": {"crs": f"EPSG:{sub.epsg}", "crs_name": "WGS 84 / UTM zone 40N",
                 "transform_gdal_order": [float(v) for v in T], "shape_rows_cols": list(sub.shape),
                 "pixel_size_m": RES_M,
                 "bbox_utm": [T[2], T[5] + T[4] * sub.shape[0], T[2] + T[0] * sub.shape[1], T[5]],
                 "bbox_lonlat": [round(v, 6) for v in bl_ll],
                 "size_km": [round(sub.shape[0] * RES_M / 1000, 2), round(sub.shape[1] * RES_M / 1000, 2)],
                 "incident_grid": INCIDENT_GRID | {"bbox_lonlat": [round(v, 6) for v in grid.lonlat_bounds()]},
                 "window_in_incident_grid": WINDOW,
                 "derivation": "scripts/build_incidents.py: 9 km half-window around the DETECT candidate centroid "
                               f"({lat0:.5f} N, {lon0:.5f} E; outputs/detect/AE-FUJ.json, label "
                               f"{ctx['cand']['label']}), clipped to the AE-FUJ AOI, 20 m UTM; the sample keeps "
                               "rows 200-799 and cols 0-559 of it (coast, the whole event, surrounding water)."},
        "event": {"incident_id": INCIDENT_ID, "datatake": EVENT["tag"], "stac_item_ids": meta["item_ids"],
                  "skipped_redundant_tiles": meta["skipped_redundant_tiles"], "datetime_utc": meta["datetime"],
                  "platform": meta["platform"], "relative_orbit": meta["relative_orbit"],
                  "mgrs_tile": "40RDN", "processing_baseline": baseline,
                  "boa_add_offset": s2f.boa_offset_for_baseline(baseline),
                  "quantification_value": s2f.S2_QUANTIFICATION,
                  "reflectance": "(DN + boa_add_offset) / quantification_value; DN 0 = no data "
                                 "(pipeline.s2_features.dn_to_reflectance)",
                  "file": EVENT_FILE, "dtype": "float32",
                  "bands": [{"band": b, "central_wavelength_nm": lam[b], "native_resolution_m": s2f.S2_NATIVE_RES_M[b],
                             "stored": ("float32 DN; decodes bit-identically to the reader's reflectance"
                                        if b in EXACT_FLOAT_BANDS else
                                        f"nearest integer DN (max change {dn_err[b]:.2f} DN = "
                                        f"{dn_err[b] / s2f.S2_QUANTIFICATION:.5f} reflectance)"
                                        if b in ROUNDED_BANDS else
                                        "original integer DN; decodes bit-identically to the reader's reflectance")}
                            for b in BANDS]
                  + [{"band": "SCL", "native_resolution_m": 20, "stored": "Sen2Cor class"}],
                  "reader": "pipeline.watch.load_datatake via scripts/build_incidents.py:load_features: 20 m bands "
                            "land 1:1 on the grid, 60 m B01 is replicated (each 20 m pixel inside one 60 m pixel), "
                            "10 m bands are averaged by GDAL to 20 m (non-integer), SCL nearest"},
        "baseline": {"file": BASELINE_FILE, "transect_file": TRANSECT_FILE, "dtype": "float32",
                     "features": list(BASELINE_FEATURES),
                     "layers": [{"name": n_, "rounding": "exact" if k2 is None else f"multiple of 2^{k2}"}
                                for n_, k2 in BASELINE_LAYERS],
                     "n_acquisitions": len(order), "years": years, "window_days": ctx["det"]["window_days"],
                     "excluded_year": int(EVENT_DATE[:4]),
                     "selection": "same-season acquisitions within +/-45 days of the event day-of-year in other "
                                  "years (pipeline.detect.climatology_indices over the WATCH archive), kept when the "
                                  "120 m WATCH water fraction near the candidate exceeds 0.25, then 36 drawn with "
                                  "numpy default_rng(813) (scripts/build_incidents.py)",
                     "per_acquisition": "s2_features.compute_features (SWIR-B12 surface correction) masked to "
                                        "s2_features.water_quality_mask(hole_buffer=False, 60 m buffer), exactly as "
                                        "build_incidents.load_features",
                     "z": "z = (x - median) / (1.4826 * mad + FLOORS[feature]), valid where n >= 6 "
                          "(pipeline.detect.robust_anomaly)",
                     "percentile": "robust_anomaly: pct = 100 * #(clim < x) / n; pct >= 95 iff x > q95; pct = 100 "
                                   "iff x > max",
                     "transect": {"window_row": row, "incident_grid_row": row + WINDOW["row0"]},
                     "acquisitions": clim_rows},
        "files": {},
        "reference_check": check,
        "licence": LICENCE,
        "attribution": f"Contains modified Copernicus Sentinel data 2024 (event) and {years[0]}-{years[-1]} "
                       "(seasonal baseline), processed by ESA, accessed via Microsoft Planetary Computer.",
    }
    if reselect_report:
        manifest["baseline"]["reselect"] = reselect_report
    for fn in (EVENT_FILE, BASELINE_FILE, TRANSECT_FILE):
        p = os.path.join(a.out, fn)
        manifest["files"][fn] = {"bytes": os.path.getsize(p), "sha256": sha256_file(p)}
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    total = sum(v["bytes"] for v in manifest["files"].values())
    log(f"wrote manifest.json; data files {total / 1e6:.2f} MB; done in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
