"""Sentinel-1 SAR surface-dark-anomaly mode (optional, P1).

A dark patch in C-band VV backscatter means the sea surface is locally smooth.
That happens under oil, but also under low wind, natural biogenic films (blooms
produce them), rain cells, upwelling and wind shadow behind headlands. The
output of this module is therefore always a SURFACE_DARK_ANOMALY with a
lookalike list, never "oil": BLUEBAN will not call a SAR dark spot oil without
independent evidence (optical sheen, a reported release, a field sample).

Method (standard dark-spot detection, e.g. Solberg et al. 1999; Fingas & Brown 2014):

* sigma0 VV in dB, land and near-shore masked;
* local background = median over a moving window (default 3 km);
* dark = sigma0 < background - contrast_db (default 3 dB), connected, >= min area;
* confidence is reduced when the scene-wide wind is below ~3 m/s (the whole sea
  is dark: lookalikes dominate) or above ~12 m/s (films break up);
* geometry features (area, elongation) are reported to help an analyst, not to
  classify.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

LOOKALIKES = ("low wind area", "biogenic surface film (blooms)", "rain cell", "upwelling",
              "wind shadow behind land", "grease ice / newly formed ice (not in the UAE)")


@dataclass
class DarkAnomaly:
    label: int
    n_px: int
    area_km2: float
    contrast_db: float
    elongation: float
    centroid_rc: tuple
    event_type: str = "SURFACE_DARK_ANOMALY"
    lookalikes: tuple = LOOKALIKES
    confidence: float = 0.0
    notes: list = field(default_factory=list)


def detect_dark(sigma0_db: np.ndarray, water: np.ndarray, pixel_m: float = 20.0,
                window_m: float = 3000.0, contrast_db: float = 3.0, min_area_km2: float = 0.5,
                wind_ms: float | None = None) -> list:
    """Dark-spot candidates in a calibrated VV sigma0 image (dB)."""
    from scipy import ndimage as ndi
    s = np.where(water, sigma0_db, np.nan).astype("float64")
    win = max(3, int(round(window_m / pixel_m)) | 1)
    fill = np.where(np.isfinite(s), s, np.nanmedian(s))
    bg = ndi.median_filter(fill, size=win, mode="nearest")
    dark = water & np.isfinite(s) & (s < bg - contrast_db)
    dark = ndi.binary_opening(dark, iterations=1)
    lab, n = ndi.label(dark)
    px_km2 = pixel_m ** 2 / 1e6
    out = []
    for k in range(1, n + 1):
        m = lab == k
        npx = int(m.sum())
        if npx * px_km2 < min_area_km2:
            continue
        rr, cc = np.nonzero(m)
        cov = np.cov(np.vstack([rr, cc])) if npx > 2 else np.eye(2)
        ev = np.sort(np.linalg.eigvalsh(cov))[::-1]
        elong = float(np.sqrt(ev[0] / max(ev[1], 1e-9)))
        contrast = float(np.median(bg[m] - s[m]))
        conf = min(1.0, contrast / 6.0)
        notes = []
        if wind_ms is not None and wind_ms < 3.0:
            conf *= 0.3
            notes.append(f"wind {wind_ms:.1f} m/s: most of the sea is smooth, lookalikes dominate")
        elif wind_ms is not None and wind_ms > 12.0:
            conf *= 0.5
            notes.append(f"wind {wind_ms:.1f} m/s: surface films break up; a dark patch is unusual")
        out.append(DarkAnomaly(label=k, n_px=npx, area_km2=npx * px_km2, contrast_db=contrast,
                               elongation=elong, centroid_rc=(float(rr.mean()), float(cc.mean())),
                               confidence=round(conf, 3), notes=notes))
    return out
