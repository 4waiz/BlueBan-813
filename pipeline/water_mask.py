"""Water masking and coastline handling.

Getting the water mask wrong is the single most common way a coastal
water-quality product produces nonsense: land pixels leak into the statistics
and a bright beach becomes an "algal bloom".

The approach here is deliberately conservative:

1. MNDWI (green vs SWIR) rather than NDWI, because SWIR separates water from
   built and bare surfaces far more cleanly on a developed coastline.
2. A NIR darkness test, because water must be dark beyond ~750 nm.
3. Removal of small connected components (speckle).
4. An erosion buffer away from land, because 30 m pixels straddling the
   shoreline mix land and water spectra and cannot be interpreted as either.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:                                            # optional, used when available
    from scipy import ndimage as _ndi
except Exception:                               # pragma: no cover
    _ndi = None


@dataclass
class WaterMaskResult:
    mask: np.ndarray                # True = open water usable for water optics
    raw_mask: np.ndarray            # before component filtering / erosion
    shoreline_buffer_px: int
    stats: dict


def _label_and_filter(mask: np.ndarray, min_px: int) -> np.ndarray:
    """Drop connected components smaller than ``min_px``."""
    if _ndi is None or min_px <= 1:
        return mask
    lab, n = _ndi.label(mask)
    if n == 0:
        return mask
    counts = np.bincount(lab.ravel())
    keep = np.zeros(counts.shape[0], dtype=bool)
    keep[1:] = counts[1:] >= min_px
    return keep[lab]


def _erode(mask: np.ndarray, iterations: int) -> np.ndarray:
    """Pull the mask away from its own boundary by ``iterations`` pixels."""
    if _ndi is None or iterations <= 0:
        return mask
    return _ndi.binary_erosion(mask, iterations=iterations, border_value=0)


def water_mask(green: np.ndarray, swir1: np.ndarray, nir: np.ndarray,
               valid: np.ndarray,
               mndwi_threshold: float = 0.15,
               nir_max: float = 0.10,
               min_component_px: int = 50,
               shoreline_buffer_px: int = 2) -> WaterMaskResult:
    """Build an open-water mask suitable for water-colour analysis.

    Parameters are in reflectance units (0-1). ``shoreline_buffer_px`` erodes
    the mask inward so mixed land/water edge pixels are excluded; at 30 m a
    buffer of 2 removes a 60 m coastal fringe.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = (green - swir1) / (green + swir1 + 1e-6)

    raw = (
        valid
        & np.isfinite(mndwi)
        & (mndwi > mndwi_threshold)
        & np.isfinite(nir)
        & (nir < nir_max)
    )

    filtered = _label_and_filter(raw, min_component_px)
    eroded = _erode(filtered, shoreline_buffer_px)

    total = raw.size
    stats = {
        "mndwi_threshold": mndwi_threshold,
        "nir_max": nir_max,
        "min_component_px": min_component_px,
        "shoreline_buffer_px": shoreline_buffer_px,
        "scipy_available": _ndi is not None,
        "px_valid": int(valid.sum()),
        "px_water_raw": int(raw.sum()),
        "px_water_after_components": int(filtered.sum()),
        "px_water_final": int(eroded.sum()),
        "water_fraction_of_valid": float(eroded.sum() / max(int(valid.sum()), 1)),
        "water_fraction_of_scene": float(eroded.sum() / total),
        "shoreline_px_removed": int(filtered.sum() - eroded.sum()),
    }
    return WaterMaskResult(mask=eroded, raw_mask=raw,
                           shoreline_buffer_px=shoreline_buffer_px, stats=stats)


def distance_from_land_px(water: np.ndarray) -> np.ndarray:
    """Euclidean distance (in pixels) from each water pixel to the nearest non-water.

    Used to separate nearshore water (shallow, bottom-influenced, land-adjacent)
    from offshore water when building the background population for anomaly
    detection.
    """
    if _ndi is None:
        return np.where(water, np.inf, 0.0)
    return _ndi.distance_transform_edt(water)


def offshore_background(water: np.ndarray, min_distance_px: int = 8) -> np.ndarray:
    """Water pixels far enough from land to serve as an optical background.

    At 30 m, ``min_distance_px=8`` means at least 240 m from any non-water pixel,
    which excludes most bottom-reflectance and adjacency contamination.
    """
    d = distance_from_land_px(water)
    return water & (d >= min_distance_px)


def shallow_nearshore(water: np.ndarray, max_distance_px: int = 8) -> np.ndarray:
    """Water pixels close to land, where bottom reflectance may matter."""
    d = distance_from_land_px(water)
    return water & (d < max_distance_px)
