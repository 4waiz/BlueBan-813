"""DETECT: per-pixel seasonal anomaly detection over the WATCH feature cache.

A spatial detector compares a pixel with its neighbours, so on a coast with
bright sand, seagrass and dredged channels it flags the same places every clear
day. DETECT instead compares every pixel with ITSELF: its own distribution of
values at the same time of year in OTHER years. A persistent feature sits in
the middle of its own history and is ignored; a new event sits in the tail.

For a target acquisition t and a feature F:

    clim(p)  = values of F at pixel p on acquisitions within +/- window days of
               t's day-of-year, excluding t's own year (no self-comparison)
    z(p)     = (F_t(p) - median(clim(p))) / (1.4826 * MAD(clim(p)) + floor_F)
    pct(p)   = percentile of F_t(p) within clim(p)

``floor_F`` is a per-feature noise floor so a pixel whose history is almost
constant cannot produce an enormous z from sensor noise. It is set from the
feature's own measurement scale, documented in FLOORS.

A candidate region is a connected set of water pixels with z >= Z_MIN and
pct >= PCT_MIN on the primary feature, at least MIN_AREA_KM2 in size. Every
candidate carries the triage feature vector consumed by the LEARN loop.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
from dataclasses import dataclass, field

import numpy as np

#: Per-feature robust-scale floors (units of the feature). Chosen from the
#: feature's measurement scale: ~0.02 in normalised-difference units (the NDCI
#: propagated sigma on the Annaba Tanager scene was 0.033), 0.002 reflectance for
#: baseline-height indices, 1 FNU for turbidity, 5 degrees of hue.
FLOORS = {"NDCI": 0.02, "MCI": 0.002, "FAI": 0.002, "TUR_NECHAD2016": 1.0,
          "HUE_ANGLE": 5.0, "CDOM_RATIO": 0.1}

#: Which features define each event hypothesis, and in which direction.
HYPOTHESIS_FEATURES = {
    "BLOOM_LIKE": [("NDCI", +1), ("MCI", +1)],
    "SEDIMENT_LIKE": [("TUR_NECHAD2016", +1)],
    "SURFACE_FILM_LIKE": [("FAI", +1)],
}

Z_MIN = 3.0
PCT_MIN = 95.0
MIN_AREA_KM2 = 0.5
MIN_CLIM_N = 6


@dataclass
class CacheIndex:
    aoi_id: str
    folder: str
    files: list          # sorted file names
    dates: list          # datetime.date per file

    @classmethod
    def load(cls, folder: str, aoi_id: str = "") -> "CacheIndex":
        files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(folder, "20*.npz")))
        dates = [dt.date.fromisoformat(f[:10]) for f in files]
        return cls(aoi_id, folder, files, dates)

    def stack(self, feature: str, idx=None) -> np.ndarray:
        idx = range(len(self.files)) if idx is None else idx
        return np.stack([np.load(os.path.join(self.folder, self.files[i]))[feature]
                         .astype("float32") for i in idx])


def _doy_dist(a: dt.date, b: dt.date) -> int:
    d = abs(a.timetuple().tm_yday - b.timetuple().tm_yday)
    return min(d, 365 - d)


def climatology_indices(dates: list, t: int, window_days: int = 45,
                        exclude_same_year: bool = True) -> list:
    target = dates[t]
    out = []
    for i, d in enumerate(dates):
        if i == t:
            continue
        if exclude_same_year and d.year == target.year:
            continue
        if _doy_dist(d, target) <= window_days:
            out.append(i)
    return out


def fast_nanmedian(x: np.ndarray, axis: int = 0) -> np.ndarray:
    """NaN-aware median along ``axis`` by sorting (NaNs sort last).

    Identical to ``np.nanmedian`` (verified to 0.0 difference on 120 x 64k
    arrays) and about 5x faster, which is what makes a per-pixel climatology
    for every acquisition of a multi-year archive tractable.
    """
    x = np.moveaxis(x, axis, 0)
    srt = np.sort(x, axis=0)
    n = np.sum(np.isfinite(x), axis=0)
    lo = np.clip((n - 1) // 2, 0, None)
    hi = np.clip(n // 2, 0, None)
    a = np.take_along_axis(srt, lo[None], 0)[0]
    b = np.take_along_axis(srt, hi[None], 0)[0]
    out = 0.5 * (a + b)
    out[n == 0] = np.nan
    return out


def robust_anomaly(x_t: np.ndarray, clim: np.ndarray, floor: float):
    """Per-pixel robust z, seasonal percentile, climatology count, median, scale."""
    n = np.sum(np.isfinite(clim), axis=0)
    with np.errstate(invalid="ignore"):
        med = fast_nanmedian(clim, 0)
        mad = fast_nanmedian(np.abs(clim - med), 0)
    scale = 1.4826 * mad + floor
    z = (x_t - med) / scale
    with np.errstate(invalid="ignore"):
        below = np.sum(clim < x_t, axis=0)
    pct = 100.0 * below / np.maximum(n, 1)
    ok = (n >= MIN_CLIM_N) & np.isfinite(x_t)
    z = np.where(ok, z, np.nan)
    pct = np.where(ok, pct, np.nan)
    return (z.astype("float32"), pct.astype("float32"), n, med.astype("float32"),
            scale.astype("float32"))


@dataclass
class Candidate:
    aoi_id: str
    date: str
    cache_file: str
    hypothesis: str
    label: int
    n_px: int
    area_km2: float
    centroid_rc: tuple
    bbox_rc: tuple
    features: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"aoi_id": self.aoi_id, "date": self.date, "cache_file": self.cache_file,
                "hypothesis": self.hypothesis, "label": self.label, "n_px": self.n_px,
                "area_km2": round(self.area_km2, 4),
                "centroid_rc": [round(v, 2) for v in self.centroid_rc],
                "bbox_rc": list(self.bbox_rc), "features": self.features,
                "evidence": self.evidence}


def _rx_percentile(feats: dict, water: np.ndarray, region: np.ndarray) -> float:
    """Spatial RX of the region mean against the scene's water population."""
    from .anomaly import robust_background
    names = [k for k in ("NDCI", "MCI", "TUR_NECHAD2016", "FAI", "HUE_ANGLE") if k in feats]
    X = np.stack([feats[k][water] for k in names], axis=1)
    ok = np.all(np.isfinite(X), axis=1)
    X = X[ok]
    if len(X) < 200:
        return float("nan")
    sd = X.std(axis=0)
    sd[sd == 0] = 1
    Z = (X - X.mean(axis=0)) / sd
    mu, cov, _ = robust_background(Z)
    inv = np.linalg.pinv(cov)
    d = Z - mu
    rx_all = np.einsum("ij,jk,ik->i", d, inv, d)
    R = np.stack([feats[k][region] for k in names], axis=1)
    R = R[np.all(np.isfinite(R), axis=1)]
    if len(R) == 0:
        return float("nan")
    r = ((R.mean(axis=0) - X.mean(axis=0)) / sd - mu)
    rx_r = float(r @ inv @ r)
    return float(100.0 * (rx_all < rx_r).mean())


def detect_at(ci: CacheIndex, t: int, resolution_m: float, window_days: int = 45,
              dist_shore_px: np.ndarray | None = None, stacks: dict | None = None,
              z_min: float = Z_MIN, pct_min: float = PCT_MIN,
              min_area_km2: float = MIN_AREA_KM2) -> dict:
    """Detect candidate regions on acquisition ``t`` of the cache."""
    from scipy import ndimage as ndi

    idx = climatology_indices(ci.dates, t, window_days)
    f_t = np.load(os.path.join(ci.folder, ci.files[t]))
    water = f_t["water"].astype(bool)
    feats = {k: f_t[k].astype("float32") for k in FLOORS if k in f_t.files}
    scl = f_t["scl"] if "scl" in f_t.files else None
    out = {"date": ci.dates[t].isoformat(), "cache_file": ci.files[t],
           "n_climatology": len(idx), "water_px": int(water.sum()), "candidates": [],
           "maps": {}}
    if len(idx) < MIN_CLIM_N or water.sum() < 200:
        out["skipped"] = "insufficient climatology or water"
        return out
    px_km2 = (resolution_m ** 2) / 1e6
    zmaps, pmaps, meds, scales, clims = {}, {}, {}, {}, {}
    for name in FLOORS:
        if name not in feats:
            continue
        clim = stacks[name][idx] if stacks and name in stacks else ci.stack(name, idx)
        z, pct, n, med, sc = robust_anomaly(feats[name], clim, FLOORS[name])
        zmaps[name], pmaps[name], meds[name], scales[name] = z, pct, med, sc
        clims[name] = clim
    out["maps"] = {"z": zmaps, "pct": pmaps, "median": meds}

    cloud = np.isin(scl, (3, 8, 9, 10)) if scl is not None else np.zeros_like(water)
    cloud_ring = ndi.binary_dilation(cloud, iterations=3) & ~cloud

    for hyp, parts in HYPOTHESIS_FEATURES.items():
        prim = parts[0][0]
        if prim not in zmaps:
            continue
        hit = water & (zmaps[prim] >= z_min) & (pmaps[prim] >= pct_min)
        for name, sign in parts[1:]:
            if name in zmaps:
                hit &= (sign * zmaps[name]) >= 1.0      # secondary feature must agree
        hit = ndi.binary_opening(hit, iterations=1)
        lab, n = ndi.label(hit)
        for k in range(1, n + 1):
            reg = lab == k
            npx = int(reg.sum())
            area = npx * px_km2
            if area < min_area_km2:
                continue
            rr, cc = np.where(reg)
            # Persistence: on how many past same-season dates did at least half
            # of this region already exceed HALF of today's detection threshold
            # (median + z_min/2 * scale, per pixel)? A permanent feature, such
            # as a bright bank or a dredged channel, scores high.
            thr = meds[prim][reg] + 0.5 * z_min * scales[prim][reg]
            past = clims[prim][:, reg]
            valid = np.isfinite(past)
            with np.errstate(invalid="ignore"):
                exceed = np.where(valid, past >= thr[None, :], False)
            nvalid = valid.sum(axis=1)
            usable = nvalid >= 0.5 * reg.sum()
            shows = exceed.sum(axis=1) >= 0.5 * np.maximum(nvalid, 1)
            persistence = float(shows[usable].mean()) if usable.any() else np.nan
            ring = ndi.binary_dilation(reg, iterations=2) & ~reg
            cloud_adj = float((ring & cloud_ring).sum() / max(ring.sum(), 1))
            dshore = (float(np.nanmedian(dist_shore_px[reg])) * resolution_m / 1000.0
                      if dist_shore_px is not None else np.nan)

            def reg_med(a):
                v = a[reg]
                v = v[np.isfinite(v)]
                return float(np.median(v)) if v.size else float("nan")

            fv = {
                "seasonal_pct_primary": reg_med(pmaps[prim]),
                "robust_z_primary": reg_med(zmaps[prim]),
                "rx_pct": _rx_percentile(feats, water, reg),
                "log10_area_km2": float(np.log10(area)),
                "persistence_frac": persistence,
                "dist_shore_km": dshore,
                "ndci_delta": reg_med(feats["NDCI"] - meds["NDCI"]) if "NDCI" in meds else np.nan,
                "mci_delta": reg_med(feats["MCI"] - meds["MCI"]) if "MCI" in meds else np.nan,
                "tur_delta": (reg_med(feats["TUR_NECHAD2016"] - meds["TUR_NECHAD2016"])
                              if "TUR_NECHAD2016" in meds else np.nan),
                "fai_mean": reg_med(feats["FAI"]) if "FAI" in feats else np.nan,
                "hue_delta_deg": (reg_med(feats["HUE_ANGLE"] - meds["HUE_ANGLE"])
                                  if "HUE_ANGLE" in meds else np.nan),
                "cloud_adjacent_frac": cloud_adj,
                "valid_frac_aoi": float(water.mean()),
            }
            ev = {f"{name}_value": reg_med(feats[name]) for name in feats}
            ev.update({f"{name}_z": reg_med(zmaps[name]) for name in zmaps})
            ev.update({f"{name}_pct": reg_med(pmaps[name]) for name in pmaps})
            out["candidates"].append(Candidate(
                ci.aoi_id, ci.dates[t].isoformat(), ci.files[t], hyp, k, npx, area,
                (float(rr.mean()), float(cc.mean())),
                (int(rr.min()), int(cc.min()), int(rr.max()), int(cc.max())),
                {k2: (None if not np.isfinite(v) else round(float(v), 5))
                 for k2, v in fv.items()},
                {k2: (None if not np.isfinite(v) else round(float(v), 5))
                 for k2, v in ev.items()}))
    return out


def persistent_water(ci: CacheIndex, min_fraction: float = 0.5, sample: int = 150):
    """Pixels classed as water on >= ``min_fraction`` of (a sample of) acquisitions."""
    step = max(1, len(ci.files) // sample)
    acc, cnt = None, 0
    for i in range(0, len(ci.files), step):
        w = np.load(os.path.join(ci.folder, ci.files[i]))["water"].astype("float32")
        acc = w if acc is None else acc + w
        cnt += 1
    frac = acc / max(cnt, 1)
    return frac >= min_fraction, frac


def distance_to_shore_px(persistent: np.ndarray) -> np.ndarray:
    from scipy import ndimage as ndi
    return ndi.distance_transform_edt(persistent)
