"""Satellite <-> field matchups.

A matchup pairs one field/reference measurement with the satellite pixels over
it. Whether a pair is usable depends on how far apart they are in time and
space and on the quality of the pixels, and every one of those tolerances is a
CHOICE. None is universally "scientifically accepted"; they are configurable,
recorded on every row, and the defaults below cite where they come from:

* ``max_dt_hours``: strict ocean-colour validation uses +/- 3 h (Bailey &
  Werdell 2006, RSE 102:12-23). Coastal Sentinel-2 studies with a 5-day revisit
  commonly accept +/- 1 day (e.g. Ibrahim et al. 2026, Front. Mar. Sci.
  13:1787597, for Abu Dhabi). Default 24 h; the report always includes the
  sensitivity to 3 h and 72 h.
* ``window_px``: a centred box of pixels, not a single pixel, so geolocation
  error and speckle average out. Bailey & Werdell use 5x5 at 1 km; at 20 m a 3x3
  box (60 m) keeps the footprint small in patchy coastal water.
* ``min_valid_frac``: at least half of the box must be valid water
  (Bailey & Werdell 2006).
* ``max_cv``: the box must be homogeneous; coefficient of variation of the
  primary band <= 0.15 (Bailey & Werdell 2006 use the median CV of several
  bands). A heterogeneous box means the field point may not represent the pixel.

Every record is kept in the output with ``passed`` and the list of reasons it
failed, so the matchup table can be audited rather than trusted.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field, asdict

import numpy as np


@dataclass
class MatchupConfig:
    max_dt_hours: float = 24.0
    window_px: int = 3
    min_valid_frac: float = 0.5
    max_cv: float = 0.15
    primary_band: str = "B04"
    max_distance_m: float | None = None     # centre-pixel distance; default = pixel size

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FieldRecord:
    record_id: str
    station: str
    lat: float
    lon: float
    time_utc: str
    parameter: str
    value: float
    unit: str
    depth_m: float | None = None
    qc: str = ""
    source: str = ""

    def time(self) -> dt.datetime:
        return parse_time(self.time_utc)


def parse_time(s: str) -> dt.datetime:
    s = s.strip().replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t


@dataclass
class Matchup:
    record: dict
    scene_id: str | None
    scene_time: str | None
    delta_time_h: float | None
    distance_m: float | None
    valid_frac: float | None
    cv_primary: float | None
    flags: dict = field(default_factory=dict)
    bands: dict = field(default_factory=dict)       # name -> {median, std, n}
    features: dict = field(default_factory=dict)    # name -> {median, std, n}
    passed: bool = False
    reasons: list = field(default_factory=list)

    def to_row(self) -> dict:
        row = {**{f"rec_{k}": v for k, v in self.record.items()},
               "scene_id": self.scene_id, "scene_time": self.scene_time,
               "delta_time_h": self.delta_time_h, "distance_m": self.distance_m,
               "valid_frac": self.valid_frac, "cv_primary": self.cv_primary,
               "passed": self.passed, "reasons": "; ".join(self.reasons)}
        for k, v in self.flags.items():
            row[f"flag_{k}"] = v
        for k, v in self.bands.items():
            row[f"band_{k}"] = v.get("median")
        for k, v in self.features.items():
            row[f"feat_{k}"] = v.get("median")
        return row


def box_stats(arr: np.ndarray, valid: np.ndarray) -> dict:
    v = arr[valid & np.isfinite(arr)]
    if v.size == 0:
        return {"median": None, "std": None, "n": 0}
    return {"median": float(np.median(v)), "std": float(np.std(v)), "n": int(v.size)}


def evaluate_box(record: FieldRecord, scene: dict, box: dict, cfg: MatchupConfig,
                 pixel_size_m: float) -> Matchup:
    """Apply the matchup criteria to an extracted pixel box.

    ``scene``: {"id", "time"}; ``box``: {"valid": bool array, "bands": {name:
    array}, "features": {name: array}, "distance_m": float, "flags": {...}}.
    """
    rec = asdict(record)
    reasons = []
    t_scene = parse_time(scene["time"]) if scene.get("time") else None
    dth = ((t_scene - record.time()).total_seconds() / 3600.0) if t_scene else None
    if dth is None or abs(dth) > cfg.max_dt_hours:
        reasons.append(f"|dt| {abs(dth):.1f} h > {cfg.max_dt_hours:g} h" if dth is not None
                       else "no scene time")
    valid = np.asarray(box.get("valid"), dtype=bool)
    vf = float(valid.mean()) if valid.size else 0.0
    if vf < cfg.min_valid_frac:
        reasons.append(f"valid fraction {vf:.2f} < {cfg.min_valid_frac:g}")
    bands = {k: box_stats(np.asarray(a, float), valid) for k, a in box.get("bands", {}).items()}
    feats = {k: box_stats(np.asarray(a, float), valid)
             for k, a in box.get("features", {}).items()}
    cv = None
    pb = bands.get(cfg.primary_band)
    if pb and pb["n"] > 1 and pb["median"] not in (None, 0):
        cv = float(pb["std"] / abs(pb["median"]))
        if cv > cfg.max_cv:
            reasons.append(f"box CV {cv:.2f} > {cfg.max_cv:g} (heterogeneous)")
    elif pb is not None:
        reasons.append("primary band not measurable in box")
    dist = box.get("distance_m")
    max_d = cfg.max_distance_m if cfg.max_distance_m is not None else pixel_size_m
    if dist is None or dist > max_d:
        reasons.append(f"centre-pixel distance {dist} m > {max_d:g} m")
    for flag, bad in (box.get("flags") or {}).items():
        if bad is True:
            reasons.append(f"flag {flag}")
    return Matchup(rec, scene.get("id"), scene.get("time"),
                   None if dth is None else round(dth, 3),
                   None if dist is None else round(float(dist), 2), round(vf, 3),
                   None if cv is None else round(cv, 4), box.get("flags") or {},
                   bands, feats, not reasons, reasons)


def nearest_scenes(record: FieldRecord, scenes: list, max_dt_hours: float) -> list:
    """Scenes within the time tolerance, closest first."""
    t = record.time()
    out = []
    for s in scenes:
        d = abs((parse_time(s["time"]) - t).total_seconds()) / 3600.0
        if d <= max_dt_hours:
            out.append((d, s))
    return [s for _, s in sorted(out, key=lambda x: x[0])]


def build_matchups(records: list, scenes: list, extract_fn, cfg: MatchupConfig,
                   pixel_size_m: float) -> list:
    """For each record: the best passing matchup, else the closest failure.

    ``extract_fn(record, scene) -> box`` performs the pixel extraction, so the
    engine is independent of the sensor and of where the data lives.
    """
    out = []
    for r in records:
        cands = nearest_scenes(r, scenes, cfg.max_dt_hours)
        if not cands:
            out.append(Matchup(asdict(r), None, None, None, None, None, None,
                               passed=False,
                               reasons=[f"no scene within {cfg.max_dt_hours:g} h"]))
            continue
        best_fail = None
        chosen = None
        for s in cands:
            box = extract_fn(r, s)
            m = evaluate_box(r, s, box, cfg, pixel_size_m)
            if m.passed:
                chosen = m
                break
            if best_fail is None:
                best_fail = m
        out.append(chosen or best_fail)
    return out


def summary(matchups: list) -> dict:
    n = len(matchups)
    ok = [m for m in matchups if m.passed]
    reasons: dict = {}
    for m in matchups:
        for rsn in m.reasons:
            key = rsn.split(" ")[0] if not rsn.startswith("flag") else rsn
            reasons[key] = reasons.get(key, 0) + 1
    return {"n_records": n, "n_passed": len(ok),
            "pass_rate": round(len(ok) / n, 4) if n else 0.0,
            "n_stations": len({m.record.get("station") for m in ok}),
            "failure_reasons": reasons,
            "median_abs_dt_h": (float(np.median([abs(m.delta_time_h) for m in ok]))
                                if ok else None)}


def sensitivity(records, scenes, extract_fn, cfg: MatchupConfig, pixel_size_m: float,
                dt_values=(3.0, 24.0, 72.0)) -> list:
    """How the matchup count changes with the time tolerance (always reported)."""
    out = []
    for d in dt_values:
        c = MatchupConfig(**{**cfg.to_dict(), "max_dt_hours": d})
        ms = build_matchups(records, scenes, extract_fn, c, pixel_size_m)
        out.append({"max_dt_hours": d, **summary(ms)})
    return out


def haversine_m(lon1, lat1, lon2, lat2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------- #
# Sentinel-2 L2A extractor (Planetary Computer COGs)
# --------------------------------------------------------------------------- #
def s2_extract_fn(cfg: MatchupConfig, bands=("B02", "B03", "B04", "B05", "B06",
                                             "B8A", "B11", "B12")):
    """Box extractor for Sentinel-2 L2A items (``scene["item"]`` = pystac Item)."""
    def fn(record: FieldRecord, scene: dict) -> dict:
        import planetary_computer as pc
        import rasterio
        from rasterio.warp import transform as rtransform
        from rasterio.windows import Window

        from . import s2_features as s2f
        item = scene["item"]
        signed = pc.sign(item)
        baseline = item.properties.get("s2:processing_baseline")
        half = cfg.window_px // 2
        out_b, dist = {}, None
        with rasterio.open(signed.assets["B05"].href) as ref:
            xs, ys = rtransform("EPSG:4326", ref.crs, [record.lon], [record.lat])
            row, col = ref.index(xs[0], ys[0])
            cx, cy = ref.xy(row, col)
            dist = float(math.hypot(cx - xs[0], cy - ys[0]))
            win = Window(col - half, row - half, cfg.window_px, cfg.window_px)
            ref_tr, ref_shape = ref.transform, (cfg.window_px, cfg.window_px)
        for b in list(bands) + ["SCL"]:
            with rasterio.open(signed.assets[b].href) as src:
                scale = abs(ref_tr.a / src.transform.a)
                w2 = Window(win.col_off * scale, win.row_off * scale,
                            win.width * scale, win.height * scale)
                a = src.read(1, window=w2, out_shape=ref_shape, boundless=True, fill_value=0)
            out_b[b] = a
        scl = out_b.pop("SCL")
        refl = {b: s2f.dn_to_reflectance(out_b[b], baseline) for b in bands}
        full = {b: refl.get(b, np.full(ref_shape, np.nan)) for b in s2f.WATER_BANDS}
        feats = s2f.compute_features(full, platform=item.properties.get("platform", ""))
        water, _ = s2f.water_quality_mask(full, scl, shoreline_buffer_m=0, pixel_size_m=20)
        valid = water & s2f.scl_usable(scl)
        flags = {"cloud_in_box": bool(np.isin(scl, (8, 9, 10)).any()),
                 "glint_b11_gt_0.0215": bool(np.nanmedian(refl["B11"]) > 0.0215)}
        return {"valid": valid, "bands": refl,
                "features": {k: feats[k] for k in ("NDCI", "MCI", "RE_RATIO", "CDOM_RATIO",
                                                    "TUR_NECHAD2016", "HUE_ANGLE")},
                "distance_m": dist, "flags": {"cloud_in_box": flags["cloud_in_box"]},
                "info": flags}
    return fn
