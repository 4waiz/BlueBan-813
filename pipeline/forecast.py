"""Short-horizon plume drift forecasting.

What this is, stated up front so nothing downstream can overclaim it:

    This is a WIND-DRIVEN SURFACE DRIFT ESTIMATE, not a hydrodynamic model.

It advects the detected event with a wind-driven surface current derived from
ERA5 reanalysis winds, plus a turbulent diffusion term. It does NOT solve the
shallow-water equations, and it does NOT include tidal currents, geostrophic
circulation, density-driven flow, river discharge momentum, bathymetric
steering or coastline-induced eddies. In a semi-enclosed gulf those terms can
dominate.

The physics that IS included
----------------------------
Wind stress on the sea surface drives a surface drift that, in operational
search-and-rescue and oil-spill practice, is taken as roughly 3 % of the 10 m
wind speed, rotated by the Coriolis effect (to the right in the northern
hemisphere). The Ekman surface-deflection angle is theoretically 45 degrees but
observed surface drift deflection is typically 0-25 degrees in shallow coastal
water where the Ekman spiral is not fully developed.

References:
* Ekman (1905), Ark. Mat. Astr. Fys. 2(11) - wind-driven surface layer theory
* ASCE (1996), "State-of-the-art review of modeling transport and fate of oil
  spills", J. Hydraulic Engineering 122(11):594-609 - the ~3 % wind factor
* Breivik et al. (2011), "Wind-induced drift of objects at sea", - leeway
  coefficients and deflection for operational drift prediction

Wind data: ERA5 reanalysis 10 m winds, obtained from the Open-Meteo historical
archive API (open access, no authentication). ERA5 is produced by ECMWF for the
Copernicus Climate Change Service.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import numpy as np

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Wind-drift parameterisation.
WIND_DRIFT_FACTOR = 0.03        # surface drift as a fraction of 10 m wind speed
DEFLECTION_DEG = 15.0           # clockwise deflection, northern hemisphere
HORIZONTAL_DIFFUSIVITY = 5.0    # m^2/s, typical coastal turbulent diffusivity


@dataclass
class WindSeries:
    times: list
    u: np.ndarray               # eastward component, m/s
    v: np.ndarray               # northward component, m/s
    speed: np.ndarray
    direction_from: np.ndarray  # meteorological convention, degrees
    source: str
    latitude: float
    longitude: float

    def to_dict(self) -> dict:
        return {
            "times": self.times,
            "u_ms": [round(float(x), 4) for x in self.u],
            "v_ms": [round(float(x), 4) for x in self.v],
            "speed_ms": [round(float(x), 4) for x in self.speed],
            "direction_from_deg": [round(float(x), 1) for x in self.direction_from],
            "source": self.source,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


def fetch_wind(lat: float, lon: float, start_date: str, end_date: str,
               timeout: int = 90) -> WindSeries:
    """Hourly ERA5 10 m wind for one point.

    Meteorological wind direction is the direction the wind blows FROM, so the
    vector components are negated:  u = -speed * sin(dir),  v = -speed * cos(dir).
    Getting that sign wrong sends every plume in exactly the wrong direction.
    """
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": start_date, "end_date": end_date,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms", "timezone": "UTC",
    })
    req = urllib.request.Request(f"{ARCHIVE_URL}?{q}",
                                 headers={"User-Agent": "blueban813/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    h = d["hourly"]
    speed = np.asarray(h["wind_speed_10m"], dtype=float)
    dirf = np.asarray(h["wind_direction_10m"], dtype=float)
    rad = np.radians(dirf)
    u = -speed * np.sin(rad)
    v = -speed * np.cos(rad)
    return WindSeries(
        times=h["time"], u=u, v=v, speed=speed, direction_from=dirf,
        source="ERA5 reanalysis via Open-Meteo historical archive API",
        latitude=float(d["latitude"]), longitude=float(d["longitude"]),
    )


def surface_drift(u_wind: float, v_wind: float,
                  factor: float = WIND_DRIFT_FACTOR,
                  deflection_deg: float = DEFLECTION_DEG,
                  hemisphere: str = "north") -> tuple:
    """Wind-driven surface current from a 10 m wind vector.

    Applies the drift factor and rotates the vector by the deflection angle
    (clockwise in the northern hemisphere, anticlockwise in the southern).
    """
    theta = np.radians(-deflection_deg if hemisphere == "north" else deflection_deg)
    ct, st = np.cos(theta), np.sin(theta)
    du = factor * (u_wind * ct - v_wind * st)
    dv = factor * (u_wind * st + v_wind * ct)
    return float(du), float(dv)


@dataclass
class ForecastStep:
    hours: float
    timestamp: str
    centroid_lon: float
    centroid_lat: float
    displacement_m: float
    bearing_deg: float
    spread_radius_m: float
    particles_lon: list = field(default_factory=list)
    particles_lat: list = field(default_factory=list)
    beached_fraction: float = 0.0

    def to_dict(self, include_particles: bool = True) -> dict:
        d = {
            "hours": self.hours,
            "timestamp": self.timestamp,
            "centroid": [round(self.centroid_lon, 6), round(self.centroid_lat, 6)],
            "displacement_m": round(self.displacement_m, 1),
            "bearing_deg": round(self.bearing_deg, 1),
            "spread_radius_m": round(self.spread_radius_m, 1),
            "beached_fraction": round(float(self.beached_fraction), 4),
        }
        if include_particles:
            d["particles"] = [[round(a, 6), round(b, 6)]
                              for a, b in zip(self.particles_lon, self.particles_lat)]
        return d


class WaterDomain:
    """Tests whether a lon/lat position is water, using the scene's water mask.

    Without this, an onshore wind drives every particle straight over the
    coastline and inland, which is both physically wrong and operationally
    misleading: it would put a forecast plume on top of a town. Particles that
    reach land are BEACHED, meaning they stop moving and are recorded as
    stranded, which is what actually happens to surface material driven ashore.
    """

    def __init__(self, water_mask: np.ndarray, transform, epsg: int):
        from pyproj import Transformer
        self.mask = water_mask
        self.rows, self.cols = water_mask.shape
        self.x0, self.dx, _, self.y0, _, self.dy = transform
        self._to_native = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}",
                                               always_xy=True)

    def is_water(self, lon, lat) -> np.ndarray:
        x, y = self._to_native.transform(np.asarray(lon), np.asarray(lat))
        c = ((x - self.x0) / self.dx).astype(int)
        r = ((y - self.y0) / self.dy).astype(int)
        inside = (r >= 0) & (r < self.rows) & (c >= 0) & (c < self.cols)
        out = np.zeros(np.shape(lon), dtype=bool)
        rr = np.clip(r, 0, self.rows - 1)
        cc = np.clip(c, 0, self.cols - 1)
        out[inside] = self.mask[rr[inside], cc[inside]]
        # Positions outside the scene footprint are unknown rather than land;
        # treating them as water lets a plume leave the scene instead of being
        # artificially pinned at the edge.
        out[~inside] = True
        return out


def advect(seed_lon, seed_lat, wind: WindSeries, start_index: int,
           horizons_h=(0, 6, 12, 24, 48), dt_s: float = 900.0,
           diffusivity: float = HORIZONTAL_DIFFUSIVITY,
           rng_seed: int = 813, domain: "WaterDomain | None" = None) -> list:
    """Advect seed particles with wind drift plus a random-walk diffusion term.

    Returns one :class:`ForecastStep` per horizon. Diffusion uses the standard
    random-walk representation of a Fickian diffusivity: each step adds a
    Gaussian displacement with standard deviation sqrt(2 * K * dt) per axis.

    If ``domain`` is given, particles that would move onto land are beached at
    their last water position and stop contributing to the drift.
    """
    rng = np.random.default_rng(rng_seed)
    lon = np.asarray(seed_lon, dtype=float).copy()
    lat = np.asarray(seed_lat, dtype=float).copy()
    lon0, lat0 = float(lon.mean()), float(lat.mean())
    active = np.ones(lon.size, dtype=bool)

    m_per_deg_lat = 110_574.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat0))

    out: list[ForecastStep] = []
    max_h = max(horizons_h)
    n_steps = int(max_h * 3600.0 / dt_s)
    horizon_steps = {int(round(h * 3600.0 / dt_s)): h for h in horizons_h}

    def emit(h, hours):
        cx, cy = float(lon.mean()), float(lat.mean())
        dx = (cx - lon0) * m_per_deg_lon
        dy = (cy - lat0) * m_per_deg_lat
        step = ForecastStep(
            hours=float(hours),
            timestamp=wind.times[min(start_index + int(hours), len(wind.times) - 1)],
            centroid_lon=cx, centroid_lat=cy,
            displacement_m=float(np.hypot(dx, dy)),
            bearing_deg=float((np.degrees(np.arctan2(dx, dy)) + 360) % 360),
            spread_radius_m=_spread(lon, lat, m_per_deg_lon, m_per_deg_lat),
            particles_lon=lon.tolist(), particles_lat=lat.tolist())
        step.beached_fraction = float(1.0 - active.mean())
        out.append(step)

    if 0 in horizon_steps:
        emit(0, 0.0)

    sigma = np.sqrt(2.0 * diffusivity * dt_s)
    for s in range(1, n_steps + 1):
        t_h = s * dt_s / 3600.0
        wi = min(start_index + int(t_h), len(wind.u) - 1)
        du, dv = surface_drift(wind.u[wi], wind.v[wi])
        nlon = lon.copy()
        nlat = lat.copy()
        step_lon = (du * dt_s + rng.normal(0, sigma, lon.size)) / m_per_deg_lon
        step_lat = (dv * dt_s + rng.normal(0, sigma, lat.size)) / m_per_deg_lat
        nlon[active] = lon[active] + step_lon[active]
        nlat[active] = lat[active] + step_lat[active]

        if domain is not None and active.any():
            ok = domain.is_water(nlon, nlat)
            beach = active & ~ok
            if beach.any():
                nlon[beach] = lon[beach]     # stay at the last water position
                nlat[beach] = lat[beach]
                active &= ~beach
        lon, lat = nlon, nlat

        if s in horizon_steps:
            emit(s, horizon_steps[s])
    return out


def _spread(lon, lat, mx, my) -> float:
    """One-sigma radius of the particle cloud, in metres."""
    dx = (lon - lon.mean()) * mx
    dy = (lat - lat.mean()) * my
    return float(np.sqrt(np.mean(dx ** 2 + dy ** 2)))


def forecast_metadata(wind: WindSeries, start_index: int) -> dict:
    """Everything a reviewer needs to judge the forecast's standing."""
    return {
        "method": "Wind-driven surface drift with random-walk diffusion",
        "model_class": "Lagrangian particle advection",
        "is_hydrodynamic_model": False,
        "wind_source": wind.source,
        "wind_at_t0": {
            "time": wind.times[start_index],
            "speed_ms": round(float(wind.speed[start_index]), 3),
            "direction_from_deg": round(float(wind.direction_from[start_index]), 1),
            "u_ms": round(float(wind.u[start_index]), 3),
            "v_ms": round(float(wind.v[start_index]), 3),
        },
        "parameters": {
            "wind_drift_factor": WIND_DRIFT_FACTOR,
            "deflection_deg": DEFLECTION_DEG,
            "horizontal_diffusivity_m2_s": HORIZONTAL_DIFFUSIVITY,
        },
        "references": [
            "Ekman (1905) Ark. Mat. Astr. Fys. 2(11)",
            "ASCE (1996) J. Hydraulic Engineering 122(11):594-609",
            "Breivik et al. (2011) wind-induced drift of objects at sea",
        ],
        "coastline_handling": (
            "Particles driven onto land are beached at their last water "
            "position and stop drifting. beached_fraction reports how much of "
            "the cloud has stranded by each horizon."),
        "not_included": [
            "Tidal currents",
            "Geostrophic and density-driven circulation",
            "River discharge momentum",
            "Bathymetric steering and coastline-induced eddies",
            "Stokes drift from surface waves",
            "Particle settling, resuspension and biological growth or decay",
        ],
        "interpretation": (
            "A scenario estimate of where surface material would go under the "
            "observed wind alone. Treat the envelope as a search area for field "
            "teams, not as a prediction of concentration at a location."
        ),
        "validation_status": (
            "Not validated against observed plume motion for this AOI: no repeat "
            "hyperspectral pass and no drifter data were available. Reported as "
            "an unvalidated scenario estimate."
        ),
    }
