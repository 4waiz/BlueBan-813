"""Critical asset exposure assessment.

BLUEBAN 813 is asset-aware: the operational question is never "is the water
unusual" in the abstract, it is "is something I am responsible for about to be
affected".

Assets are always operator-supplied. The system ships NO infrastructure
coordinates of its own. Intake locations for desalination and industrial plants
are frequently treated as sensitive, and guessing them from imagery and then
publishing them would be both unreliable and irresponsible. Operators pin their
own assets, or upload GeoJSON/CSV.
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field

import numpy as np

ASSET_TYPES = {
    "DESALINATION_INTAKE": {
        "label": "Desalination intake",
        "default_sensitivity": 1.0,
        "why": "Source water quality directly affects membrane fouling, "
               "pre-treatment load and, in the worst case, forces a shutdown "
               "of potable supply.",
        "primary_concerns": ["algal bloom", "turbidity", "hydrocarbon", "organics"],
    },
    "AQUACULTURE": {
        "label": "Aquaculture facility",
        "default_sensitivity": 0.95,
        "why": "Stock mortality from harmful blooms and oxygen depletion; "
               "cages cannot be moved quickly.",
        "primary_concerns": ["harmful algal bloom", "dissolved oxygen", "pollution"],
    },
    "PUBLIC_BEACH": {
        "label": "Public beach / bathing water",
        "default_sensitivity": 0.8,
        "why": "Public health exposure and bathing-water compliance.",
        "primary_concerns": ["harmful algal bloom", "microbial", "visible pollution"],
    },
    "MARINE_PROTECTED_AREA": {
        "label": "Marine protected area",
        "default_sensitivity": 0.9,
        "why": "Ecological damage is often irreversible on management timescales.",
        "primary_concerns": ["sedimentation", "eutrophication", "pollution"],
    },
    "PORT": {
        "label": "Port / harbour",
        "default_sensitivity": 0.5,
        "why": "Operational and environmental-compliance relevance.",
        "primary_concerns": ["turbidity", "pollution"],
    },
    "INDUSTRIAL_INTAKE": {
        "label": "Industrial water intake",
        "default_sensitivity": 0.7,
        "why": "Process water quality and filtration load.",
        "primary_concerns": ["turbidity", "biofouling"],
    },
    "CUSTOM": {
        "label": "Custom asset",
        "default_sensitivity": 0.6,
        "why": "Operator-defined.",
        "primary_concerns": [],
    },
}


@dataclass
class Asset:
    id: str
    name: str
    type: str
    lon: float
    lat: float
    sensitivity: float = None
    notes: str = ""
    source: str = "operator"

    def __post_init__(self):
        if self.type not in ASSET_TYPES:
            self.type = "CUSTOM"
        if self.sensitivity is None:
            self.sensitivity = ASSET_TYPES[self.type]["default_sensitivity"]

    def to_dict(self) -> dict:
        t = ASSET_TYPES[self.type]
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "type_label": t["label"], "lon": self.lon, "lat": self.lat,
            "sensitivity": self.sensitivity, "notes": self.notes,
            "source": self.source, "why_it_matters": t["why"],
            "primary_concerns": t["primary_concerns"],
        }


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
EARTH_R = 6_371_000.0


def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bearing_deg(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(deg: float) -> str:
    pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return pts[int((deg + 11.25) % 360 // 22.5)]


# --------------------------------------------------------------------------- #
# Exposure
# --------------------------------------------------------------------------- #
@dataclass
class Exposure:
    asset: Asset
    distance_m: float
    bearing_from_event_deg: float
    direction: str
    closest_approach_m: float
    closest_approach_hours: float | None
    intersects_forecast: bool
    eta_hours: float | None
    exposure_score: float
    basis: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "asset": self.asset.to_dict(),
            "distance_m": round(self.distance_m, 1),
            "distance_km": round(self.distance_m / 1000.0, 3),
            "bearing_from_event_deg": round(self.bearing_from_event_deg, 1),
            "direction": self.direction,
            "closest_approach_m": round(self.closest_approach_m, 1),
            "closest_approach_hours": (round(self.closest_approach_hours, 2)
                                       if self.closest_approach_hours is not None else None),
            "intersects_forecast": self.intersects_forecast,
            "eta_hours": round(self.eta_hours, 2) if self.eta_hours is not None else None,
            "exposure_score": round(self.exposure_score, 4),
            "basis": self.basis,
        }


def assess(asset: Asset, event_lon: float, event_lat: float,
           forecast_steps=None, event_radius_m: float = 0.0) -> Exposure:
    """Exposure of one asset to one event, now and along the forecast track.

    ``eta_hours`` is the first forecast horizon at which the particle cloud
    reaches within ``event_radius_m + spread`` of the asset. It is reported only
    when the forecast track actually gets there; we do not extrapolate a
    constant-velocity arrival beyond the modelled horizons, because the drift
    estimate has no skill claim beyond them.
    """
    d0 = float(haversine_m(event_lon, event_lat, asset.lon, asset.lat))
    brg = bearing_deg(event_lon, event_lat, asset.lon, asset.lat)
    basis = [f"Current separation {d0/1000:.2f} km, asset lies "
             f"{compass(brg)} of the event centroid."]

    closest, closest_h, eta, intersects = d0, 0.0, None, False
    if forecast_steps:
        for step in forecast_steps:
            plon = np.asarray(step.particles_lon)
            plat = np.asarray(step.particles_lat)
            if plon.size == 0:
                continue
            dists = haversine_m(plon, plat, asset.lon, asset.lat)
            dmin = float(dists.min())
            # Fraction of the particle cloud inside the asset's neighbourhood.
            reach = max(event_radius_m, 250.0)
            frac = float((dists <= reach).mean())
            if dmin < closest:
                closest, closest_h = dmin, step.hours
            if frac > 0.01 and eta is None and step.hours > 0:
                eta = step.hours
                intersects = True
                basis.append(
                    f"{frac*100:.1f}% of drift particles come within "
                    f"{reach:.0f} m of the asset by +{step.hours:.0f} h.")
        if not intersects:
            basis.append(
                f"No modelled drift particle reaches the asset within the "
                f"forecast horizon; closest approach {closest/1000:.2f} km at "
                f"+{closest_h:.0f} h.")

    # Exposure combines proximity, trajectory and the asset's own sensitivity.
    # Distance decays over a 5 km scale, which is the range over which a coastal
    # plume is operationally relevant at these drift speeds.
    prox = float(np.exp(-closest / 5000.0))
    traj = 1.0 if intersects else 0.35
    score = float(np.clip(prox * traj * asset.sensitivity, 0.0, 1.0))
    basis.append(
        f"Exposure = proximity {prox:.3f} x trajectory {traj:.2f} x "
        f"asset sensitivity {asset.sensitivity:.2f} = {score:.3f}.")

    return Exposure(asset, d0, brg, compass(brg), closest, closest_h,
                    intersects, eta, score, basis)


# --------------------------------------------------------------------------- #
# Loading operator assets
# --------------------------------------------------------------------------- #
def from_geojson(text: str) -> list:
    """Load point assets from a GeoJSON FeatureCollection."""
    gj = json.loads(text) if isinstance(text, str) else text
    out = []
    for i, f in enumerate(gj.get("features", [])):
        g = f.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"][:2]
        p = f.get("properties", {}) or {}
        out.append(Asset(
            id=str(p.get("id", f"A{i+1:02d}")),
            name=str(p.get("name", f"Asset {i+1}")),
            type=str(p.get("type", "CUSTOM")).upper(),
            lon=float(lon), lat=float(lat),
            sensitivity=(float(p["sensitivity"]) if "sensitivity" in p else None),
            notes=str(p.get("notes", "")), source="geojson_upload",
        ))
    return out


def from_csv(text: str) -> list:
    """Load point assets from CSV with lon/lat (or longitude/latitude) columns."""
    rdr = csv.DictReader(io.StringIO(text))
    out = []
    for i, row in enumerate(rdr):
        low = {k.strip().lower(): (v.strip() if isinstance(v, str) else v)
               for k, v in row.items() if k}
        lon = low.get("lon") or low.get("longitude") or low.get("x")
        lat = low.get("lat") or low.get("latitude") or low.get("y")
        if lon in (None, "") or lat in (None, ""):
            continue
        out.append(Asset(
            id=str(low.get("id") or f"A{i+1:02d}"),
            name=str(low.get("name") or f"Asset {i+1}"),
            type=str(low.get("type") or "CUSTOM").upper(),
            lon=float(lon), lat=float(lat),
            sensitivity=(float(low["sensitivity"]) if low.get("sensitivity") else None),
            notes=str(low.get("notes") or ""), source="csv_upload",
        ))
    return out
