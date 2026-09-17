"""Smart field-sampling planner.

Satellite remote sensing does not replace physical water testing, and BLUEBAN
813 does not pretend otherwise. What it can do is tell a field team WHERE a
water sample carries the most information, so a limited sampling budget is spent
where it resolves the most uncertainty.

Each suggested point has a role, and the roles are chosen so the resulting set
answers a specific question:

    EVENT_CORE          What is actually in the water at the strongest signal?
    LEADING_EDGE        Where is the boundary now, and is it advancing?
    ASSET_BOUNDARY      Has anything reached the thing we are protecting?
    BACKGROUND_CONTROL  What does normal look like today? Without this, every
                        other measurement is uncalibrated.
    UNCERTAINTY_POINT   Where does the model least know what it is looking at?
                        Sampling here buys the most future accuracy.

A sampling plan without a background control is close to useless: an absolute
laboratory value cannot be interpreted without knowing what the same water body
reads when nothing is happening. The planner always includes one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .exposure import haversine_m

ROLES = {
    "EVENT_CORE": {
        "priority": 1,
        "question": "What is actually present at the point of strongest signal?",
        "recommended_analyses": ["Chlorophyll-a (spectrophotometric or HPLC)",
                                 "Total suspended solids (gravimetric)",
                                 "Turbidity (nephelometric, NTU)",
                                 "Phytoplankton identification and cell counts"],
    },
    "LEADING_EDGE": {
        "priority": 2,
        "question": "Where is the boundary, and is the event advancing?",
        "recommended_analyses": ["Turbidity (NTU)", "Chlorophyll-a",
                                 "Temperature and salinity profile"],
    },
    "ASSET_BOUNDARY": {
        "priority": 1,
        "question": "Has anything reached the protected asset yet?",
        "recommended_analyses": ["Turbidity (NTU)", "Chlorophyll-a",
                                 "Total organic carbon",
                                 "Algal toxins if a bloom is suspected"],
    },
    "BACKGROUND_CONTROL": {
        "priority": 2,
        "question": "What does unaffected water in this body read today?",
        "recommended_analyses": ["Same analyte suite as the event core, "
                                 "for direct comparison"],
    },
    "UNCERTAINTY_POINT": {
        "priority": 3,
        "question": "Where is the interpretation least certain?",
        "recommended_analyses": ["Full analyte suite",
                                 "Secchi depth",
                                 "Water depth (to test bottom-reflectance influence)"],
    },
}


@dataclass
class SamplePoint:
    id: str
    role: str
    lon: float
    lat: float
    priority: int
    rationale: str
    expected_variables: list = field(default_factory=list)
    anomaly_score: float | None = None
    distance_from_shore_m: float | None = None
    distance_to_asset_m: float | None = None
    confidence: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "role": self.role,
            "role_question": ROLES[self.role]["question"],
            "lon": round(self.lon, 6), "lat": round(self.lat, 6),
            "priority": self.priority, "rationale": self.rationale,
            "expected_variables": self.expected_variables,
            "anomaly_score": (round(float(self.anomaly_score), 2)
                              if self.anomaly_score is not None else None),
            "distance_from_shore_m": (round(float(self.distance_from_shore_m), 0)
                                      if self.distance_from_shore_m is not None else None),
            "distance_to_asset_m": (round(float(self.distance_to_asset_m), 0)
                                    if self.distance_to_asset_m is not None else None),
            "confidence": (round(float(self.confidence), 3)
                           if self.confidence is not None else None),
        }


def _rc_to_lonlat(rows, cols, transform, epsg, transformer=None):
    x0, dx, _, y0, _, dy = transform
    x = x0 + (np.asarray(cols) + 0.5) * dx
    y = y0 + (np.asarray(rows) + 0.5) * dy
    if transformer is None:
        from pyproj import Transformer
        transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    return transformer.transform(x, y)


def _min_separation_ok(lon, lat, chosen, min_m):
    for c in chosen:
        if haversine_m(lon, lat, c.lon, c.lat) < min_m:
            return False
    return True


def plan(score: np.ndarray, water: np.ndarray, event_mask: np.ndarray,
         transform, epsg: int,
         distance_from_shore_m: np.ndarray | None = None,
         forecast_steps=None, assets=None,
         confidence_field: np.ndarray | None = None,
         max_points: int = 6, min_separation_m: float = 400.0) -> list:
    """Generate a field-sampling plan for one event.

    ``min_separation_m`` enforces spatial spread: two samples 50 m apart in the
    same plume measure the same water twice and waste a boat trip.
    """
    from pyproj import Transformer
    tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    pts: list[SamplePoint] = []
    n = 0

    def add(role, r, c, rationale, **kw):
        nonlocal n
        lon, lat = _rc_to_lonlat([r], [c], transform, epsg, tr)
        lon, lat = float(np.atleast_1d(lon)[0]), float(np.atleast_1d(lat)[0])
        if not _min_separation_ok(lon, lat, pts, min_separation_m):
            return False
        n += 1
        pts.append(SamplePoint(
            id=f"S{n:02d}", role=role, lon=lon, lat=lat,
            priority=ROLES[role]["priority"], rationale=rationale,
            expected_variables=ROLES[role]["recommended_analyses"],
            anomaly_score=float(score[r, c]) if np.isfinite(score[r, c]) else None,
            distance_from_shore_m=(float(distance_from_shore_m[r, c])
                                   if distance_from_shore_m is not None else None),
            **kw))
        return True

    # 1. EVENT CORE - highest anomaly inside the event.
    if event_mask.any():
        masked = np.where(event_mask, score, -np.inf)
        r, c = np.unravel_index(np.nanargmax(masked), score.shape)
        add("EVENT_CORE", r, c,
            f"Highest spectral anomaly in the event (RX {score[r, c]:.0f}). "
            f"The strongest signal gives laboratory analysis the best chance of "
            f"identifying what is actually present.")

    # 2. LEADING EDGE - event pixel closest to the forecast direction of travel.
    if event_mask.any() and forecast_steps and len(forecast_steps) > 1:
        last = forecast_steps[-1]
        tgt_lon = float(np.mean(last.particles_lon)) if last.particles_lon else None
        if tgt_lon is not None:
            tgt_lat = float(np.mean(last.particles_lat))
            rr, cc = np.where(event_mask)
            lons, lats = _rc_to_lonlat(rr, cc, transform, epsg, tr)
            d = haversine_m(np.asarray(lons), np.asarray(lats), tgt_lon, tgt_lat)
            i = int(np.argmin(d))
            add("LEADING_EDGE", rr[i], cc[i],
                f"Edge of the event nearest the modelled drift direction "
                f"(bearing {last.bearing_deg:.0f}deg). Sampling here tests "
                f"whether the event is advancing and how sharp the front is.")

    # 3. ASSET BOUNDARY - water immediately seaward of the most exposed asset.
    if assets:
        best = max(assets, key=lambda a: a.get("exposure_score", 0.0))
        alon = best["asset"]["lon"] if "asset" in best else best["lon"]
        alat = best["asset"]["lat"] if "asset" in best else best["lat"]
        rr, cc = np.where(water)
        lons, lats = _rc_to_lonlat(rr, cc, transform, epsg, tr)
        d = haversine_m(np.asarray(lons), np.asarray(lats), alon, alat)
        order = np.argsort(d)
        name = (best["asset"]["name"] if "asset" in best else best.get("name", "asset"))
        for i in order[:400]:
            if add("ASSET_BOUNDARY", rr[i], cc[i],
                   f"Nearest analysable water to {name}, "
                   f"{d[i]:.0f} m away. This is the measurement that answers "
                   f"whether the asset is affected yet.",
                   distance_to_asset_m=float(d[i])):
                break

    # 4. BACKGROUND CONTROL - clean water, far from both event and shore.
    bg = water & ~event_mask & np.isfinite(score)
    if distance_from_shore_m is not None:
        bg &= distance_from_shore_m > 800.0
    if bg.any():
        cand = np.where(bg, score, np.inf)
        flat = np.argsort(cand, axis=None)
        for idx in flat[:5000]:
            r, c = np.unravel_index(idx, score.shape)
            if not bg[r, c]:
                continue
            if add("BACKGROUND_CONTROL", r, c,
                   f"Lowest-anomaly water at least 800 m offshore (RX "
                   f"{score[r, c]:.1f}). Without a same-day control, an absolute "
                   f"laboratory value from the event cannot be interpreted."):
                break

    # 5. UNCERTAINTY POINT - where the method is least sure.
    if len(pts) < max_points:
        if confidence_field is not None:
            cand = np.where(water & np.isfinite(confidence_field),
                            confidence_field, np.inf)
            idx = int(np.nanargmin(cand))
            r, c = np.unravel_index(idx, score.shape)
            add("UNCERTAINTY_POINT", r, c,
                "Lowest model confidence in the AOI. A measurement here "
                "constrains the interpretation more than one where the model "
                "is already sure.")
        else:
            # Without an explicit confidence field, the most informative
            # uncertain place is the transition zone: water that is anomalous
            # but below the detection threshold, in shallow water where bottom
            # reflectance competes with a water-column explanation.
            sc = np.where(water, score, np.nan)
            lo, hi = np.nanpercentile(sc, 85), np.nanpercentile(sc, 97)
            band = water & (sc >= lo) & (sc <= hi) & ~event_mask
            if distance_from_shore_m is not None:
                band &= distance_from_shore_m < 300.0
            if band.any():
                rr, cc = np.where(band)
                j = len(rr) // 2
                add("UNCERTAINTY_POINT", rr[j], cc[j],
                    f"Marginal anomaly (RX between the {85}th and {97}th "
                    f"percentile) in shallow water, where bottom reflectance "
                    f"and suspended matter are hard to separate optically. "
                    f"A depth reading and a TSS sample here would resolve the "
                    f"ambiguity for the whole nearshore band.")

    pts.sort(key=lambda p: (p.priority, p.id))
    for i, p in enumerate(pts[:max_points], 1):
        p.id = f"S{i:02d}"
    return pts[:max_points]


def to_geojson(points) -> dict:
    return {
        "type": "FeatureCollection",
        "properties": {
            "generator": "BLUEBAN 813 smart sampling planner",
            "note": "Suggested field-sampling locations. Satellite observation "
                    "is a screening tool; laboratory analysis of physical "
                    "samples is required to confirm any interpretation.",
        },
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p.lon, p.lat]},
            "properties": p.to_dict(),
        } for p in points],
    }


def to_csv(points) -> str:
    cols = ["id", "role", "lat", "lon", "priority", "anomaly_score",
            "distance_from_shore_m", "distance_to_asset_m", "rationale",
            "expected_variables"]
    lines = [",".join(cols)]
    for p in points:
        d = p.to_dict()
        row = []
        for c in cols:
            v = d.get(c)
            if isinstance(v, list):
                v = "; ".join(v)
            v = "" if v is None else str(v)
            row.append('"' + v.replace('"', '""') + '"' if ("," in v or '"' in v) else v)
        lines.append(",".join(row))
    return "\n".join(lines)
