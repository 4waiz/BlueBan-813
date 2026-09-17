"""Export derived layers for the web client.

Heavy geospatial work happens here, once, offline. The browser receives small
GeoJSON and PNG artefacts with explicit bounds, and never a hyperspectral cube.
"""
from __future__ import annotations

import json
import os

import numpy as np

try:
    from scipy import ndimage as _ndi
except Exception:                                   # pragma: no cover
    _ndi = None


def grid_to_lonlat(rows, cols, transform, epsg, transformer=None):
    from pyproj import Transformer
    x0, dx, _, y0, _, dy = transform
    x = x0 + (np.asarray(cols, dtype=float) + 0.5) * dx
    y = y0 + (np.asarray(rows, dtype=float) + 0.5) * dy
    if transformer is None:
        transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326",
                                           always_xy=True)
    return transformer.transform(x, y)


def bounds_lonlat(shape, transform, epsg):
    """Lon/lat bounding box of a raster, sampling the full border.

    Sampling only the four corners is wrong for a rotated or projected grid:
    the true extent can bulge beyond the corner envelope. We walk the whole
    perimeter instead.
    """
    rows, cols = shape
    rr = np.concatenate([
        np.zeros(cols), np.full(cols, rows - 1),
        np.arange(rows), np.arange(rows)])
    cc = np.concatenate([
        np.arange(cols), np.arange(cols),
        np.zeros(rows), np.full(rows, cols - 1)])
    lon, lat = grid_to_lonlat(rr, cc, transform, epsg)
    return [float(np.min(lon)), float(np.min(lat)),
            float(np.max(lon)), float(np.max(lat))]


def mask_to_polygons(mask: np.ndarray, transform, epsg,
                     simplify_m: float = 45.0, min_area_m2: float = 20000.0,
                     properties_fn=None) -> dict:
    """Vectorise a boolean mask into a GeoJSON FeatureCollection in EPSG:4326."""
    import rasterio.features
    from affine import Affine
    from pyproj import Transformer
    from shapely.geometry import shape as shp_shape, mapping
    from shapely.ops import transform as shp_transform

    x0, dx, _, y0, _, dy = transform
    aff = Affine(dx, 0.0, x0, 0.0, dy, y0)
    tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)

    feats = []
    labelled = mask.astype(np.int32)
    if _ndi is not None and mask.dtype == bool:
        labelled, _ = _ndi.label(mask)

    for geom, val in rasterio.features.shapes(labelled, mask=labelled > 0,
                                              transform=aff):
        g = shp_shape(geom)
        if g.area < min_area_m2:
            continue
        if simplify_m > 0:
            g = g.simplify(simplify_m, preserve_topology=True)
        if g.is_empty:
            continue
        gw = shp_transform(lambda a, b: tr.transform(a, b), g)
        props = {"value": int(val), "area_km2": round(g.area / 1e6, 5)}
        if properties_fn:
            props.update(properties_fn(int(val)) or {})
        feats.append({"type": "Feature", "geometry": mapping(gw),
                      "properties": props})
    feats.sort(key=lambda f: -f["properties"]["area_km2"])
    return {"type": "FeatureCollection", "features": feats}


def stretch(a: np.ndarray, mask: np.ndarray | None = None,
            lo_pct: float = 2.0, hi_pct: float = 98.0):
    v = a[mask] if mask is not None else a
    v = v[np.isfinite(v)]
    if v.size == 0:
        return np.zeros_like(a), (0.0, 1.0)
    lo, hi = np.percentile(v, [lo_pct, hi_pct])
    if hi <= lo:
        hi = lo + 1e-6
    return np.clip((a - lo) / (hi - lo), 0, 1), (float(lo), float(hi))


def save_rgb_png(path: str, r, g, b, valid: np.ndarray,
                 water: np.ndarray | None = None,
                 land_gain: float = 0.30, land_saturation: float = 0.18):
    """True-colour PNG for a WATER product.

    Water and land get different treatments on purpose.

    Water is stretched on its own percentiles, because water-leaving
    reflectance is roughly an order of magnitude darker than land and a
    land-inclusive stretch renders it almost black, which is exactly the part
    we need to read.

    Land is then rendered as a dark, desaturated backdrop rather than being
    left to saturate. Applying the water stretch to land blows it out to a flat
    bright field that dominates the frame and competes with the event. Land is
    context here, not the subject, so it is darkened to ``land_gain`` and
    desaturated toward grey by ``land_saturation``.
    """
    from PIL import Image
    ref = water if water is not None and water.any() else valid

    # A SHARED stretch across the three channels, not one per channel.
    # Stretching each channel to its own percentiles normalises away the
    # relative brightness between them, and clear water - which is genuinely
    # blue-dominated, roughly 0.063 at 441 nm against 0.007 at 666 nm here -
    # comes back as false magenta. A common range preserves the real colour.
    stack = np.dstack([r, g, b])
    vals = stack[ref]
    vals = vals[np.isfinite(vals)]
    if vals.size:
        lo, hi = np.percentile(vals, [1.0, 99.2])
    else:
        lo, hi = 0.0, 1.0
    if hi <= lo:
        hi = lo + 1e-6
    rgb = np.clip((stack - lo) / (hi - lo), 0, 1)
    # Mild gamma so the darkest water separates without lifting the whole frame.
    rgb = np.power(rgb, 0.78)
    rgb = np.nan_to_num(rgb, nan=0.0)
    r_rng = g_rng = b_rng = (float(lo), float(hi))

    if water is not None and water.any():
        land = valid & ~water
        # Independent, gentler stretch so land keeps its structure.
        lr, _ = stretch(r, land, 2, 98)
        lg, _ = stretch(g, land, 2, 98)
        lb, _ = stretch(b, land, 2, 98)
        lrgb = np.nan_to_num(np.dstack([lr, lg, lb]), nan=0.0)
        lum = lrgb.mean(axis=2, keepdims=True)
        lrgb = (lum + (lrgb - lum) * land_saturation) * land_gain
        rgb = np.where(land[..., None], lrgb, rgb)

    alpha = valid.astype(np.float32)
    arr = np.dstack([np.clip(rgb, 0, 1) * 255, alpha * 255]).astype(np.uint8)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Image.fromarray(arr, mode="RGBA").save(path, optimize=True)
    return {"path": path, "stretch": {"r": r_rng, "g": g_rng, "b": b_rng},
            "land_gain": land_gain, "land_saturation": land_saturation}


def save_scalar_png(path: str, values: np.ndarray, mask: np.ndarray,
                    cmap: str = "inferno", vmin=None, vmax=None,
                    log: bool = False):
    """Single-band field as a colour-mapped RGBA PNG, transparent off-mask."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import colors
    from PIL import Image

    v = values.astype("float64").copy()
    v[~mask] = np.nan
    finite = np.isfinite(v)
    if log:
        v = np.log10(np.clip(v, 1.0, None))
    # Default limits are the 2nd and 99th percentile of the masked population,
    # so the stretch adapts to the scene instead of being hand-tuned, and the
    # chosen values are returned for the legend to print.
    auto = vmin is None or vmax is None
    if vmin is None:
        vmin = float(np.nanpercentile(v[finite], 2)) if finite.any() else 0.0
    if vmax is None:
        vmax = float(np.nanpercentile(v[finite], 99)) if finite.any() else 1.0
    norm = colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    # matplotlib removed cm.get_cmap in 3.9; the registry is the supported API.
    try:
        cmap_obj = matplotlib.colormaps[cmap]
    except Exception:                                   # pragma: no cover
        from matplotlib import cm as _cm
        cmap_obj = _cm.get_cmap(cmap)
    rgba = cmap_obj(norm(v))
    rgba[..., 3] = np.where(finite, 0.88, 0.0)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Image.fromarray((rgba * 255).astype(np.uint8), mode="RGBA").save(
        path, optimize=True)
    return {"path": path, "vmin": round(float(vmin), 6),
            "vmax": round(float(vmax), 6), "log": log, "cmap": cmap,
            "limits": "2nd-99th percentile of masked pixels" if auto else "fixed",
            "n_pixels": int(finite.sum())}


def write_json(path: str, obj) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    return path
