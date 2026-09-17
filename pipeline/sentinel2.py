"""Sentinel-2 MSI access and water-quality processing.

Sentinel-2 is Stage B of the cascade: it supplies the spatial detail and, far
more importantly, the TEMPORAL BASELINE. A single hyperspectral scene can show
that nearshore water looks different from offshore water, but it cannot say
whether that difference is an event or simply what this coastline always looks
like. Only a multi-year record can, and that record is what separates a
sediment plume from permanent bottom reflectance in shallow water.

Data source: Microsoft Planetary Computer, collection ``sentinel-2-l2a``
(ESA Copernicus Sentinel-2 Level-2A surface reflectance).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

# Sentinel-2 L2A is stored as integers with a fixed scale, and from processing
# baseline 04.00 (2022-01-25) ESA added a radiometric offset.
S2_SCALE = 1.0 / 10000.0
S2_OFFSET_BASELINE_0400 = -1000.0
S2_BASELINE_CHANGE = "2022-01-25"

# Scene Classification Layer values (Sentinel-2 L2A SCL band).
SCL_CLASSES = {
    0: "no_data", 1: "saturated_defective", 2: "dark_area_pixels",
    3: "cloud_shadow", 4: "vegetation", 5: "not_vegetated",
    6: "water", 7: "unclassified", 8: "cloud_medium_probability",
    9: "cloud_high_probability", 10: "thin_cirrus", 11: "snow_ice",
}
SCL_BAD = {0, 1, 3, 8, 9, 10, 11}          # unusable for water optics
SCL_WATER = {6}

# Band centre wavelengths (S2A), used for provenance and index selection.
S2_BANDS_NM = {
    "B01": 443, "B02": 492, "B03": 560, "B04": 665, "B05": 704,
    "B06": 740, "B07": 783, "B08": 833, "B8A": 865, "B09": 945,
    "B11": 1610, "B12": 2190,
}


@dataclass
class S2Observation:
    """One Sentinel-2 acquisition reduced to water-quality statistics."""

    item_id: str
    datetime: str
    cloud_cover: float
    n_water_px: int
    stats: dict

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "datetime": self.datetime,
            "cloud_cover": self.cloud_cover,
            "n_water_px": self.n_water_px,
            **{k: (None if v is None or not np.isfinite(v) else round(float(v), 6))
               for k, v in self.stats.items()},
        }


def harmonize(arr: np.ndarray, datetime_str: str) -> np.ndarray:
    """Convert raw Sentinel-2 L2A DNs to reflectance, handling the 04.00 offset.

    ESA processing baseline 04.00 (from 2022-01-25) shifted L2A values by
    -1000 DN. Ignoring this makes pre- and post-2022 scenes incomparable, which
    silently corrupts any multi-year baseline. Planetary Computer serves the
    raw values, so the correction is ours to apply.
    """
    a = arr.astype("float32")
    a[a == 0] = np.nan                       # 0 is the L2A no-data value
    if datetime_str >= S2_BASELINE_CHANGE:
        a = a + S2_OFFSET_BASELINE_0400
    return a * S2_SCALE


def scl_masks(scl: np.ndarray):
    """Return ``(usable, water)`` boolean masks from the Scene Classification Layer."""
    bad = np.isin(scl, list(SCL_BAD))
    water = np.isin(scl, list(SCL_WATER))
    return ~bad, water


def search(bbox, datetime_range: str, max_cloud: float = 20.0,
           limit: int = 1000):
    """Search Planetary Computer for Sentinel-2 L2A items over ``bbox``."""
    from pystac_client import Client
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=bbox,
                            datetime=datetime_range, max_items=limit).items())
    keep = [i for i in items
            if (i.properties.get("eo:cloud_cover") or 100) <= max_cloud]
    keep.sort(key=lambda i: i.properties["datetime"])
    return keep


def load_bands(item, bands, bbox, resolution: int = 20):
    """Read named assets for one item, clipped to ``bbox`` (EPSG:4326).

    Sentinel-2 bands are stored at three different native resolutions
    (10 / 20 / 60 m), so every band is resampled onto ONE common grid defined by
    ``resolution``. Returning them at native shapes would make them
    non-broadcastable, and silently mismatched arrays are a classic source of
    wrong multi-band results.

    Nearest-neighbour resampling is used deliberately: it preserves the original
    measured values, and for SCL (a class label layer) any averaging would be
    meaningless.

    Returns ``(dict_of_arrays, transform, crs)``. Values are raw DNs; call
    :func:`harmonize` for reflectance.
    """
    import planetary_computer as pc
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    signed = pc.sign(item)
    out = {}
    transform = crs = None
    target_shape = None
    bounds_native = None

    for b in bands:
        href = signed.assets[b].href
        with rasterio.open(href) as src:
            if bounds_native is None:
                bounds_native = transform_bounds("EPSG:4326", src.crs, *bbox,
                                                 densify_pts=21)
                crs = src.crs
                left, bottom, right, top = bounds_native
                w = max(1, int(round((right - left) / resolution)))
                h = max(1, int(round((top - bottom) / resolution)))
                target_shape = (h, w)
                transform = rasterio.transform.from_bounds(
                    left, bottom, right, top, w, h)
            win = from_bounds(*bounds_native, src.transform)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                a = src.read(1, window=win, out_shape=target_shape,
                             boundless=True, fill_value=0,
                             resampling=Resampling.nearest)
            out[b] = a
    return out, transform, crs


def water_indices(refl: dict) -> dict:
    """Water-quality indices from harmonised Sentinel-2 reflectance.

    ``refl`` keys are Sentinel-2 band names. Uses the same index definitions as
    the hyperspectral path (see :mod:`pipeline.indices`) so the two sensors are
    directly comparable.
    """
    eps = 1e-6
    g, r = refl.get("B03"), refl.get("B04")
    re, nir = refl.get("B05"), refl.get("B8A")
    swir = refl.get("B11")
    out = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        if g is not None and swir is not None:
            out["MNDWI"] = (g - swir) / (g + swir + eps)
        if g is not None and nir is not None:
            out["NDWI"] = (g - nir) / (g + nir + eps)
        if re is not None and r is not None:
            out["NDCI"] = (re - r) / (re + r + eps)
        if r is not None and g is not None:
            out["TURBIDITY_PROXY"] = (r - g) / (r + g + eps)
        if r is not None:
            out["R665"] = r
        if g is not None:
            out["R560"] = g
    return out
