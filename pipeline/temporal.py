"""Temporal baselines and local anomaly statistics.

An absolute threshold ("NDCI above 0.2 is a bloom") is meaningless across
different water bodies: what is alarming in the clear Mediterranean is normal in
a turbid estuary. BLUEBAN 813 judges every observation against the LOCAL
historical distribution for that place and that time of year.

This module also settles a question a single scene cannot: whether elevated
nearshore brightness is an EVENT or a PERMANENT feature. Bottom reflectance in
shallow water is present on every clear date, so it sits at the middle of the
historical distribution. A genuine plume sits in the upper tail. The percentile
is the discriminator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class BaselineStats:
    """Historical distribution of one variable at one place."""

    variable: str
    n_observations: int
    date_range: tuple
    median: float
    mean: float
    std: float
    percentiles: dict
    seasonal: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        def r(x):
            return None if x is None or not np.isfinite(x) else round(float(x), 6)
        return {
            "variable": self.variable,
            "n_observations": int(self.n_observations),
            "date_range": list(self.date_range),
            "median": r(self.median),
            "mean": r(self.mean),
            "std": r(self.std),
            "percentiles": {k: r(v) for k, v in self.percentiles.items()},
            "seasonal": {k: {kk: r(vv) for kk, vv in v.items()}
                         for k, v in self.seasonal.items()},
        }


PCTS = (1, 5, 10, 25, 50, 75, 90, 95, 98, 99)


def build_baseline(values, dates, variable: str,
                   seasonal_window_days: int = 45) -> BaselineStats:
    """Summarise a historical series, including a day-of-year seasonal view.

    ``values`` and ``dates`` are parallel sequences; ``dates`` are ISO strings or
    numpy datetime64. Non-finite values are dropped and reported.
    """
    v = np.asarray(values, dtype="float64")
    d = np.asarray(dates, dtype="datetime64[D]")
    ok = np.isfinite(v)
    v, d = v[ok], d[ok]
    if v.size == 0:
        return BaselineStats(variable, 0, ("", ""), np.nan, np.nan, np.nan,
                             {str(p): np.nan for p in PCTS})

    doy = ((d - d.astype("datetime64[Y]")).astype(int)) + 1
    seasonal = {}
    for month in range(1, 13):
        centre = int((month - 0.5) * 30.44)
        dist = np.minimum(np.abs(doy - centre), 365 - np.abs(doy - centre))
        sel = dist <= seasonal_window_days
        if sel.sum() >= 3:
            seasonal[f"{month:02d}"] = {
                "n": int(sel.sum()),
                "median": float(np.median(v[sel])),
                "p90": float(np.percentile(v[sel], 90)),
                "p95": float(np.percentile(v[sel], 95)),
            }

    return BaselineStats(
        variable=variable,
        n_observations=int(v.size),
        date_range=(str(d.min()), str(d.max())),
        median=float(np.median(v)),
        mean=float(v.mean()),
        std=float(v.std(ddof=1)) if v.size > 1 else 0.0,
        percentiles={str(p): float(np.percentile(v, p)) for p in PCTS},
        seasonal=seasonal,
    )


def percentile_of(value: float, history) -> float:
    """Where ``value`` falls in ``history``, as a percentile in [0, 100]."""
    h = np.asarray(history, dtype="float64")
    h = h[np.isfinite(h)]
    if h.size == 0 or not np.isfinite(value):
        return float("nan")
    return float(100.0 * (h < value).mean())


def seasonal_percentile(value: float, values, dates, target_date,
                        window_days: int = 45) -> dict:
    """Percentile of ``value`` against same-season history only.

    Comparing a June observation against a full-year record confuses a seasonal
    cycle with an event. This restricts the comparison to observations within
    ``window_days`` of the same day-of-year, wrapping across the year boundary.
    """
    v = np.asarray(values, dtype="float64")
    d = np.asarray(dates, dtype="datetime64[D]")
    ok = np.isfinite(v)
    v, d = v[ok], d[ok]
    t = np.datetime64(target_date, "D")

    doy = ((d - d.astype("datetime64[Y]")).astype(int)) + 1
    tdoy = int((t - t.astype("datetime64[Y]")).astype(int)) + 1
    dist = np.minimum(np.abs(doy - tdoy), 365 - np.abs(doy - tdoy))
    sel = dist <= window_days

    return {
        "value": None if not np.isfinite(value) else float(value),
        "n_seasonal": int(sel.sum()),
        "seasonal_percentile": percentile_of(value, v[sel]) if sel.sum() >= 3 else None,
        "all_time_percentile": percentile_of(value, v),
        "n_all_time": int(v.size),
        "window_days": window_days,
        "seasonal_median": float(np.median(v[sel])) if sel.sum() >= 3 else None,
    }


def trend(values, dates):
    """Ordinary least-squares slope of a series, in units per year.

    Returned with an R-squared so a weak trend is not presented as a strong one.
    """
    v = np.asarray(values, dtype="float64")
    d = np.asarray(dates, dtype="datetime64[D]")
    ok = np.isfinite(v)
    v, d = v[ok], d[ok]
    if v.size < 4:
        return {"slope_per_year": None, "r_squared": None, "n": int(v.size)}
    t = (d - d.min()).astype("float64") / 365.25
    A = np.vstack([t, np.ones_like(t)]).T
    coef, *_ = np.linalg.lstsq(A, v, rcond=None)
    pred = A @ coef
    ss_res = float(((v - pred) ** 2).sum())
    ss_tot = float(((v - v.mean()) ** 2).sum())
    return {
        "slope_per_year": float(coef[0]),
        "intercept": float(coef[1]),
        "r_squared": (1 - ss_res / ss_tot) if ss_tot > 0 else None,
        "n": int(v.size),
        "span_years": float(t.max() - t.min()),
    }


def classify_state(pct: float | None, p_watch: float = 90.0,
                   p_investigate: float = 95.0, p_high: float = 98.0) -> str:
    """Map a percentile to an operational state label."""
    if pct is None or not np.isfinite(pct):
        return "UNKNOWN"
    if pct >= p_high:
        return "HIGH_PRIORITY"
    if pct >= p_investigate:
        return "INVESTIGATE"
    if pct >= p_watch:
        return "WATCH"
    return "NORMAL"
