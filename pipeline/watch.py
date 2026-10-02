"""WATCH: continuous monitoring of an AOI through the Sentinel-2 L2A archive.

For every usable acquisition over an AOI this module produces ONE row of zone
statistics (water fraction, valid pixels and robust percentiles of every
water-quality feature). The resulting time series answers the WATCH questions:

* When was this area last observed with valid imagery?
* Is today unusual FOR THIS PLACE AND SEASON? (see ``pipeline.temporal``)
* Which dates, historically, were the outliers worth an analyst's time?

Design decisions
----------------
* **Common grid.** Each AOI gets one fixed grid in its UTM zone. Sentinel-2
  tiles of one datatake are read in their native CRS (the UAE straddles UTM 39
  and 40), reprojected onto that grid and mosaicked. Without this, an AOI on a
  tile boundary would report half-scenes as separate observations.
* **Redundant tiles skipped.** Neighbouring UTM 39 / 40 tiles cover the same
  ground in the UAE. Tiles in the AOI's own zone are read first and a tile that
  adds no new pixels is skipped.
* **Overview reads.** Screening runs at 60-120 m. Reading the COG window with a
  reduced ``out_shape`` lets GDAL use the internal overviews, which is what
  makes a multi-year screen of several AOIs tractable. Incident mapping is done
  later at native 20 m.
* **Zone percentiles, not means.** A plume covering 2 % of an AOI barely moves
  the AOI mean or median. The P95/P99 of the water population follows the most
  affected water (the same reasoning as the Annaba baseline).
* **Static zones.** Nearshore / offshore zones come from ESA WorldCover, not
  from each scene's water mask, so the series compares the same water through
  time regardless of tide or glint.
* **Optically shallow water.** Much of the UAE Gulf coast is optically shallow:
  bright sand, seagrass and microbial mats raise red-edge indices (MCI, NDCI)
  with no chlorophyll in the water at all. A per-scene zone statistic cannot
  separate the two; the per-pixel seasonal climatology built from the feature
  cache can, because a static bottom is present on every clear date.
"""
from __future__ import annotations

import math
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from . import s2_features as s2f

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.tiff")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "4")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
# Without these a stalled blob read blocks a worker forever. GDAL's open() can
# hold the Python GIL while it waits on HTTP, which freezes every thread in the
# process; hence short timeouts, no HEAD requests, and PROCESS-level parallelism
# in screen_aoi rather than threads.
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "20")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "10")
os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")
os.environ.setdefault("GDAL_INGESTED_BYTES_AT_OPEN", "32768")
os.environ.setdefault("VSI_CACHE", "TRUE")

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SCREEN_BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B8A", "B11", "B12"]
STAT_FEATURES = ["NDCI", "MCI", "FAI", "RE_RATIO", "CDOM_RATIO",
                 "TUR_NECHAD2016", "SPM_NECHAD2016", "TUR_DOGLIOTTI2015",
                 "HUE_ANGLE"]
CACHE_FEATURES = ["NDCI", "MCI", "FAI", "TUR_NECHAD2016", "HUE_ANGLE", "CDOM_RATIO"]
PCTS = (5, 25, 50, 75, 95, 99)


def utm_epsg(lon: float, lat: float) -> int:
    zone = int(math.floor((lon + 180) / 6) + 1)
    return (32600 if lat >= 0 else 32700) + zone


@dataclass
class AoiGrid:
    aoi_id: str
    bbox: tuple                # lon/lat
    epsg: int
    transform: object          # affine.Affine
    shape: tuple               # rows, cols
    resolution_m: float

    @classmethod
    def from_bbox(cls, aoi_id: str, bbox, resolution_m: float = 60.0) -> "AoiGrid":
        from rasterio.transform import from_origin
        from rasterio.warp import transform_bounds
        lon_c, lat_c = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        epsg = utm_epsg(lon_c, lat_c)
        l, b, r, t = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *bbox, densify_pts=21)
        l = math.floor(l / resolution_m) * resolution_m
        t = math.ceil(t / resolution_m) * resolution_m
        cols = int(math.ceil((r - l) / resolution_m))
        rows = int(math.ceil((t - b) / resolution_m))
        return cls(aoi_id, tuple(bbox), epsg,
                   from_origin(l, t, resolution_m, resolution_m),
                   (rows, cols), resolution_m)

    def lonlat_bounds(self) -> list:
        from rasterio.warp import transform_bounds
        x0, y0 = self.transform.c, self.transform.f
        x1 = x0 + self.transform.a * self.shape[1]
        y1 = y0 + self.transform.e * self.shape[0]
        return list(transform_bounds(f"EPSG:{self.epsg}", "EPSG:4326",
                                     x0, y1, x1, y0, densify_pts=21))


def search_items(bbox, start: str, end: str, max_cloud: float = 30.0):
    """All Sentinel-2 L2A items over ``bbox``, grouped by datatake.

    Returns a list of ``(datatake_key, [items])`` sorted by time. The key is
    date + relative orbit + platform, i.e. one physical overpass.
    """
    from pystac_client import Client
    cat = Client.open(PC_STAC)
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=bbox,
                            datetime=f"{start}/{end}", max_items=10000).items())
    groups: dict = {}
    for it in items:
        p = it.properties
        if (p.get("eo:cloud_cover") or 100) > max_cloud:
            continue
        key = (p["datetime"][:10], p.get("sat:relative_orbit") or 0, p.get("platform"))
        groups.setdefault(key, []).append(it)
    return sorted(groups.items(), key=lambda kv: kv[0][0])


def _read_band_to_grid(href: str, grid: AoiGrid, resampling_name: str):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject, transform_bounds
    from rasterio.windows import from_bounds

    categorical = resampling_name in ("nearest", "mode")
    resampling = getattr(Resampling, resampling_name)
    with rasterio.Env(GDAL_HTTP_TIMEOUT=20, GDAL_HTTP_CONNECTTIMEOUT=10,
                      GDAL_HTTP_MAX_RETRY=3, GDAL_HTTP_RETRY_DELAY=2,
                      CPL_VSIL_CURL_USE_HEAD="NO"), \
            rasterio.open(href) as src:
        l, b, r, t = transform_bounds("EPSG:4326", src.crs, *grid.bbox, densify_pts=21)
        pad = 2 * grid.resolution_m
        win = from_bounds(l - pad, b - pad, r + pad, t + pad, src.transform)
        win = win.round_offsets().round_lengths()
        # Read at roughly the target resolution so GDAL can use overviews.
        src_res = abs(src.transform.a)
        scale = max(1.0, grid.resolution_m / src_res)
        out_h = max(1, int(round(win.height / scale)))
        out_w = max(1, int(round(win.width / scale)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            arr = src.read(1, window=win, out_shape=(out_h, out_w), boundless=True,
                           fill_value=0,
                           resampling=Resampling.nearest if categorical
                           else Resampling.average)
        win_tr = src.window_transform(win)
        win_tr = win_tr * win_tr.scale(win.width / out_w, win.height / out_h)
        dst = np.zeros(grid.shape, dtype="float32")
        reproject(arr.astype("float32"), dst, src_transform=win_tr, src_crs=src.crs,
                  dst_transform=grid.transform, dst_crs=f"EPSG:{grid.epsg}",
                  src_nodata=0, dst_nodata=0, resampling=resampling)
    return dst


def load_datatake(items, grid: AoiGrid, bands=SCREEN_BANDS, band_workers: int = 1):
    """Mosaic one datatake's tiles onto ``grid``.

    Returns ``(reflectance_dict, scl, meta)``. Reflectance is decoded per tile
    with that tile's own processing baseline BEFORE mosaicking, so a datatake
    whose tiles were processed with different baselines is still consistent.
    """
    import planetary_computer as pc

    refl = {b: np.full(grid.shape, np.nan, dtype="float32") for b in bands}
    scl = np.zeros(grid.shape, dtype="uint8")
    ids, baselines, skipped = [], [], []
    items = sorted(items, key=lambda it: 0 if it.properties.get("proj:code")
                   == f"EPSG:{grid.epsg}" else 1)
    for it in items:
        if (scl > 0).all():
            skipped.append(it.id)
            continue
        signed = pc.sign(it)
        baseline = it.properties.get("s2:processing_baseline")
        s = _read_band_to_grid(signed.assets["SCL"].href, grid, "nearest")
        fill = (scl == 0) & (s > 0)
        if not fill.any():
            skipped.append(it.id)
            continue
        ids.append(it.id)
        baselines.append(baseline)
        scl[fill] = s[fill].astype("uint8")
        if band_workers <= 1:
            dns = {b: _read_band_to_grid(signed.assets[b].href, grid, "average") for b in bands}
        else:
            with ThreadPoolExecutor(max_workers=band_workers) as ex:
                dns = dict(zip(bands, ex.map(
                    lambda b: _read_band_to_grid(signed.assets[b].href, grid, "average"),
                    bands)))
        for b in bands:
            r = s2f.dn_to_reflectance(dns[b], baseline)
            m = np.isnan(refl[b]) & np.isfinite(r) & fill
            refl[b][m] = r[m]
    p = items[0].properties
    meta = {
        "item_ids": ids,
        "skipped_redundant_tiles": skipped,
        "processing_baselines": sorted(set(b for b in baselines if b)),
        "datetime": p["datetime"],
        "platform": p.get("platform"),
        "relative_orbit": p.get("sat:relative_orbit"),
        "cloud_cover_tiles": [it.properties.get("eo:cloud_cover") for it in items],
        "sun_zenith": p.get("s2:mean_solar_zenith"),
    }
    return refl, scl, meta


def worldcover_zones(grid: AoiGrid, nearshore_m: float = 1500.0) -> dict:
    """Static land/water zoning from ESA WorldCover 2021 (10 m, CC-BY-4.0).

    Returns boolean masks on ``grid``: ``nearshore`` (water within
    ``nearshore_m`` of WorldCover land), ``offshore`` (beyond it) and ``all``.
    The scene's own water mask is still applied per acquisition; this only
    decides which ZONE a water pixel reports into.
    """
    import planetary_computer as pc
    from pystac_client import Client
    from scipy import ndimage as ndi

    cat = Client.open(PC_STAC)
    items = list(cat.search(collections=["esa-worldcover"], bbox=grid.bbox,
                            max_items=20).items())
    items = [i for i in items if "2021" in i.id] or items
    water = np.zeros(grid.shape, dtype="float32")
    have = np.zeros(grid.shape, dtype=bool)
    for it in items:
        href = pc.sign(it).assets["map"].href
        wc = _read_band_to_grid(href, grid, "mode")
        m = (wc > 0) & ~have
        water[m] = (wc[m] == 80).astype("float32")
        have |= wc > 0
    land = have & (water < 0.5)
    dist_m = ndi.distance_transform_edt(~land) * grid.resolution_m
    wmask = ~land
    return {"all": wmask,
            "nearshore": wmask & (dist_m < nearshore_m),
            "offshore": wmask & (dist_m >= nearshore_m)}


def zone_statistics(refl: dict, scl: np.ndarray, platform: str,
                    resolution_m: float, zones: dict | None = None,
                    feats: dict | None = None, water=None) -> dict:
    """Water mask + feature percentiles for one mosaicked acquisition."""
    if feats is None:
        feats = s2f.compute_features(refl, platform=platform)
    if water is None:
        water, rep = s2f.water_quality_mask(refl, scl, pixel_size_m=resolution_m,
                                            shoreline_buffer_m=max(40.0, resolution_m))
    else:
        _, rep = s2f.water_quality_mask(refl, scl, pixel_size_m=resolution_m,
                                        shoreline_buffer_m=max(40.0, resolution_m))
    valid = np.isfinite(refl["B03"])
    out = {"quality": rep.to_dict(),
           "valid_fraction": float(valid.mean()),
           "cloud_fraction_of_valid": float(
               (np.isin(scl, (8, 9, 10)) & valid).sum() / max(valid.sum(), 1))}
    zones = zones or {"all": np.ones_like(water)}
    for zname, zmask in zones.items():
        wz = water & zmask
        z = {"n_water": int(wz.sum()), "zone_px": int(zmask.sum())}
        for f in STAT_FEATURES:
            v = feats[f][wz]
            v = v[np.isfinite(v)]
            if v.size < 30:
                z[f] = None
                continue
            z[f] = {f"p{q}": float(np.percentile(v, q)) for q in PCTS}
            z[f]["mean"] = float(v.mean())
            z[f]["n"] = int(v.size)
        out[zname] = z
    return out


def _grid_to_dict(grid: AoiGrid) -> dict:
    return {"aoi_id": grid.aoi_id, "bbox": list(grid.bbox), "epsg": grid.epsg,
            "transform": list(grid.transform)[:6], "shape": list(grid.shape),
            "resolution_m": grid.resolution_m}


def _grid_from_dict(d: dict) -> AoiGrid:
    from affine import Affine
    return AoiGrid(d["aoi_id"], tuple(d["bbox"]), d["epsg"], Affine(*d["transform"]),
                   tuple(d["shape"]), d["resolution_m"])


def datatake_tag(date: str, orbit, platform) -> str:
    """Cache/sidecar name of one datatake: date, relative orbit, platform suffix."""
    return f"{date}_R{int(orbit):03d}_{(platform or 'S2')[-2:]}"


def process_datatake(args) -> dict:
    """One datatake -> one time-series row (+ cache file). Runs in a worker process."""
    key, item_dicts, grid_d, cache_dir, zones_path = args
    import json as _json
    import pystac
    tag = datatake_tag(key[0], key[1], key[2])
    sidecar = os.path.join(cache_dir, f"{tag}.row.json") if cache_dir else None
    if sidecar and os.path.exists(sidecar) and os.path.exists(os.path.join(cache_dir, f"{tag}.npz")):
        with open(sidecar, encoding="utf-8") as f:                 # resume: already processed
            return _json.load(f)
    items = [pystac.Item.from_dict(d) for d in item_dicts]
    grid = _grid_from_dict(grid_d)
    res = grid.resolution_m
    try:
        zmasks = ({k: v.astype(bool) for k, v in np.load(zones_path).items()}
                  if zones_path else None)
        refl, scl, meta = load_datatake(items, grid)
        feats = s2f.compute_features(refl, platform=meta["platform"])
        water, _ = s2f.water_quality_mask(refl, scl, pixel_size_m=res,
                                          shoreline_buffer_m=max(40.0, res))
        st = zone_statistics(refl, scl, meta["platform"], res, zmasks, feats=feats, water=water)
        row = {"date": key[0], **meta, **st}
        if cache_dir:
            np.savez_compressed(
                os.path.join(cache_dir, f"{tag}.npz"), water=water, scl=scl,
                **{f: np.where(water, feats[f], np.nan).astype("float16") for f in CACHE_FEATURES},
                rgb=np.dstack([refl["B04"], refl["B03"], refl["B02"]]).astype("float16"))
            row["cache_file"] = f"{tag}.npz"
            with open(sidecar, "w", encoding="utf-8") as f:            # lets an interrupted run resume
                _json.dump(row, f, default=float)
        return row
    except Exception as e:                                    # recorded, not hidden
        return {"date": key[0], "error": repr(e)[:300], "item_ids": [i.id for i in items]}


def screen_aoi(aoi_id: str, bbox, start: str, end: str, resolution_m: float = 60.0,
               max_cloud: float = 30.0, workers: int = 6, zones: str | None = None,
               cache_dir: str | None = None, progress=print, reuse: dict | None = None) -> dict:
    """Screen every usable acquisition over one AOI. Returns the time series.

    Datatakes are processed in separate PROCESSES: a network stall inside GDAL
    can hold the GIL, and in a thread pool that freezes every worker. With
    ``cache_dir`` set, each acquisition's water-masked feature rasters are also
    written there (float16 ``.npz``, gitignored) for per-pixel climatologies.

    ``reuse`` maps datatake tags to rows from a previous run: those datatakes are
    not read again (their cached raster must still exist when ``cache_dir`` is
    set), so a refresh only screens what is new.
    """
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

    grid = AoiGrid.from_bbox(aoi_id, bbox, resolution_m)
    groups = search_items(bbox, start, end, max_cloud)
    zmasks = worldcover_zones(grid) if zones == "worldcover" else None
    zones_path = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        if zmasks is not None:
            zones_path = os.path.join(cache_dir, "_zones.npz")
            np.savez_compressed(zones_path, **zmasks)
    gd = _grid_to_dict(grid)
    tasks = [(key, [it.to_dict() for it in items], gd, cache_dir, zones_path)
             for key, items in groups]
    reused = []
    if reuse:
        fresh = []
        for t in tasks:
            tag = datatake_tag(*t[0][:3])
            if tag in reuse and (not cache_dir or os.path.exists(os.path.join(cache_dir, f"{tag}.npz"))):
                reused.append(reuse[tag])
            else:
                fresh.append(t)
        progress(f"  {aoi_id}: {len(reused)} datatakes already screened, {len(fresh)} new")
        tasks = fresh
    t0 = time.time()
    rows, pending, started = list(reused), {}, {}
    stall_s, done_n = 300.0, 0
    ex = ProcessPoolExecutor(max_workers=workers)
    queue = list(tasks)
    try:
        while queue or pending:
            while queue and len(pending) < workers:
                t = queue.pop(0)
                f = ex.submit(process_datatake, t)
                pending[f], started[f] = t, time.time()
            finished, _ = wait(list(pending), timeout=10, return_when=FIRST_COMPLETED)
            for f in finished:
                t = pending.pop(f)
                try:
                    rows.append(f.result())
                except Exception as e:                        # worker crash
                    rows.append({"date": t[0][0], "error": f"worker failed: {e!r}"[:300]})
                done_n += 1
                if done_n % 25 == 0:
                    progress(f"  {aoi_id}: {done_n}/{len(tasks)} datatakes "
                             f"({time.time() - t0:.0f}s)")
            now = time.time()
            for f in [f for f in pending if now - started[f] > stall_s]:
                t = pending.pop(f)
                rows.append({"date": t[0][0], "error": f"stalled > {stall_s:.0f}s (abandoned)"})
                done_n += 1
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    rows.sort(key=lambda r: r.get("datetime", r["date"]))
    return {
        "aoi_id": aoi_id, "bbox": list(bbox), "grid": {
            "epsg": grid.epsg, "shape": list(grid.shape),
            "resolution_m": resolution_m,
            "transform": list(grid.transform)[:6],
            "bounds_lonlat": grid.lonlat_bounds()},
        "window": [start, end], "max_cloud": max_cloud,
        "zones": ({k: int(v.sum()) for k, v in zmasks.items()} if zmasks else None),
        "n_datatakes": len(groups), "n_ok": sum("error" not in r for r in rows),
        "features": {f: s2f.FEATURES[f].to_dict() for f in STAT_FEATURES},
        "rows": rows,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def series(ts: dict, feature: str, stat: str = "p95", zone: str = "all",
           min_water_px: int = 200):
    """Extract (dates, values) for one feature statistic from a screen result."""
    d, v = [], []
    for r in ts["rows"]:
        z = r.get(zone)
        if not z or z.get("n_water", 0) < min_water_px:
            continue
        f = z.get(feature)
        if not f or f.get(stat) is None:
            continue
        d.append(r["date"])
        v.append(f[stat])
    return d, v
