"""Spectral forensics over water.

This is where hyperspectral data earns its place. A multispectral sensor gives
a handful of broad numbers per pixel; a hyperspectral sensor gives a curve. The
functions here turn that curve into evidence:

* per-band signal-to-noise over water, computed from the sensor's own
  uncertainty layer, which tells us which part of the spectrum is actually
  informative rather than assuming it;
* background and hotspot mean spectra with dispersion envelopes;
* difference spectra;
* Spectral Angle Mapper, a magnitude-invariant shape comparison;
* continuum removal, which isolates absorption features from overall brightness.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# --------------------------------------------------------------------------- #
# Which bands actually carry water-leaving signal
# --------------------------------------------------------------------------- #
def band_snr(cube: np.ndarray, unc_cube: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Median signal-to-noise per band over the masked population.

    ``cube`` and ``unc_cube`` are (bands, rows, cols); ``mask`` is (rows, cols).
    """
    b = cube.shape[0]
    out = np.full(b, np.nan)
    for i in range(b):
        v = cube[i][mask]
        u = unc_cube[i][mask]
        ok = np.isfinite(v) & np.isfinite(u) & (u > 0)
        if ok.sum() > 10:
            out[i] = np.median(np.abs(v[ok]) / u[ok])
    return out


def water_informative_bands(wavelengths: np.ndarray, snr: np.ndarray,
                            min_snr: float = 3.0,
                            max_nm: float = 900.0,
                            min_nm: float = 400.0) -> np.ndarray:
    """Boolean mask of bands usable for water-colour interpretation.

    Two independent criteria, both physical:

    1. Wavelength range. Liquid water absorbs strongly beyond roughly 750 nm and
       almost totally beyond 900 nm, so there is essentially no water-leaving
       signal in the NIR/SWIR: what remains is surface reflection and residual
       atmosphere. Bands past ``max_nm`` are therefore excluded from
       water-colour interpretation. They are still useful as glint and
       atmospheric diagnostics, which is why they are kept in the cube and only
       masked here.

    2. Measured SNR. A band whose median signal does not exceed ``min_snr``
       times its own reported uncertainty over water cannot support an
       inference, whatever its wavelength.
    """
    in_range = (wavelengths >= min_nm) & (wavelengths <= max_nm)
    good_snr = np.isfinite(snr) & (snr >= min_snr)
    return in_range & good_snr


# --------------------------------------------------------------------------- #
# Population spectra
# --------------------------------------------------------------------------- #
@dataclass
class SpectrumStats:
    """Mean spectrum of a pixel population with dispersion."""

    wavelengths: np.ndarray
    mean: np.ndarray
    median: np.ndarray
    std: np.ndarray
    p05: np.ndarray
    p95: np.ndarray
    n_pixels: int

    def to_dict(self, round_to: int = 6) -> dict:
        r = lambda a: [None if not np.isfinite(x) else round(float(x), round_to) for x in a]
        return {
            "wavelengths_nm": [round(float(x), 2) for x in self.wavelengths],
            "mean": r(self.mean),
            "median": r(self.median),
            "std": r(self.std),
            "p05": r(self.p05),
            "p95": r(self.p95),
            "n_pixels": int(self.n_pixels),
        }


def population_spectrum(cube: np.ndarray, mask: np.ndarray,
                        wavelengths: np.ndarray) -> SpectrumStats:
    """Summarise the spectra of every pixel in ``mask``."""
    b = cube.shape[0]
    sel = cube[:, mask]                                  # (bands, n)
    n = sel.shape[1]
    with np.errstate(invalid="ignore"):
        mean = np.nanmean(sel, axis=1)
        med = np.nanmedian(sel, axis=1)
        std = np.nanstd(sel, axis=1)
        p05 = np.nanpercentile(sel, 5, axis=1)
        p95 = np.nanpercentile(sel, 95, axis=1)
    return SpectrumStats(wavelengths, mean, med, std, p05, p95, n)


def difference_spectrum(hotspot: SpectrumStats, background: SpectrumStats):
    """Hotspot minus background, with a pooled-standard-error significance ratio.

    Returns ``(difference, z)`` where ``z`` is the difference divided by the
    standard error of the difference of the two means. |z| > 2 marks
    wavelengths where the two populations genuinely differ rather than
    overlapping within their own scatter.
    """
    diff = hotspot.mean - background.mean
    se = np.sqrt(
        (hotspot.std ** 2) / max(hotspot.n_pixels, 1)
        + (background.std ** 2) / max(background.n_pixels, 1)
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        z = diff / se
    return diff, z


# --------------------------------------------------------------------------- #
# Shape comparison
# --------------------------------------------------------------------------- #
def spectral_angle(a: np.ndarray, b: np.ndarray, axis: int = -1) -> np.ndarray:
    """Spectral Angle Mapper, in radians.

    SAM measures the angle between two spectra treated as vectors, so it
    compares SHAPE and ignores overall magnitude. That matters over water,
    where brightness varies with illumination geometry and glint while the
    shape carries the water-constituent information.

    Reference: Kruse et al. (1993), Remote Sensing of Environment 44:145-163.
    """
    num = np.nansum(a * b, axis=axis)
    da = np.sqrt(np.nansum(a * a, axis=axis))
    db = np.sqrt(np.nansum(b * b, axis=axis))
    with np.errstate(invalid="ignore", divide="ignore"):
        c = np.clip(num / (da * db), -1.0, 1.0)
    return np.arccos(c)


def sam_image(cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """SAM of every pixel against one reference spectrum. Returns (rows, cols)."""
    b, r, c = cube.shape
    flat = np.moveaxis(cube, 0, -1).reshape(-1, b)
    ang = spectral_angle(flat, reference[None, :], axis=1)
    return ang.reshape(r, c)


# --------------------------------------------------------------------------- #
# Absorption-feature isolation
# --------------------------------------------------------------------------- #
def continuum_removal(wavelengths: np.ndarray, spectrum: np.ndarray) -> np.ndarray:
    """Divide a spectrum by its upper convex hull.

    Continuum removal separates absorption features from overall brightness, so
    two spectra with different illumination can be compared feature by feature.
    Result is 1.0 on the hull and dips below 1.0 inside absorption features.

    Reference: Clark & Roush (1984), J. Geophysical Research 89(B7):6329-6340.
    """
    ok = np.isfinite(spectrum)
    if ok.sum() < 3:
        return np.full_like(spectrum, np.nan)
    x, y = wavelengths[ok], spectrum[ok]

    # Upper convex hull by monotone chain on (x, y).
    hull = []
    for i in range(len(x)):
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            # drop hull[-1] if it lies below the line hull[-2] -> current point
            if (x2 - x1) * (y[i] - y1) - (y2 - y1) * (x[i] - x1) >= 0:
                hull.pop()
            else:
                break
        hull.append((x[i], y[i]))
    hx = np.array([p[0] for p in hull])
    hy = np.array([p[1] for p in hull])

    cont = np.interp(wavelengths, hx, hy)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = spectrum / cont
    out[~np.isfinite(out)] = np.nan
    return out


def feature_depth(wavelengths: np.ndarray, cr_spectrum: np.ndarray,
                  centre_nm: float, halfwidth_nm: float = 20.0) -> float:
    """Depth of a continuum-removed absorption feature near ``centre_nm``.

    Returns ``1 - min(continuum_removed)`` inside the window; 0 means no feature.

    Only meaningful when ``cr_spectrum`` was produced by a continuum fitted over
    a narrow window. Over a full water spectrum the global hull is dominated by
    the steep blue-to-NIR decline and this will report large depths everywhere;
    use :func:`local_band_depth` for discrete features instead.
    """
    w = (wavelengths >= centre_nm - halfwidth_nm) & (wavelengths <= centre_nm + halfwidth_nm)
    v = cr_spectrum[w]
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan")
    return float(1.0 - v.min())


def _mean_around(wl: np.ndarray, spec: np.ndarray, nm: float,
                 halfwidth: float = 5.0) -> float:
    w = (wl >= nm - halfwidth) & (wl <= nm + halfwidth)
    v = spec[w]
    v = v[np.isfinite(v)]
    return float(v.mean()) if v.size else float("nan")


def local_band_depth(wl: np.ndarray, spec: np.ndarray, left_nm: float,
                     centre_nm: float, right_nm: float,
                     halfwidth: float = 5.0) -> float:
    """Absorption depth against a LOCAL continuum defined by two shoulders.

    The continuum is the straight line between the reflectance at ``left_nm``
    and at ``right_nm``; depth is how far the observed reflectance at
    ``centre_nm`` falls below it, as a fraction of the continuum:

        depth = 1 - R(centre) / R_continuum(centre)

    Positive means absorption, negative means a reflectance peak. This is the
    standard band-depth formulation and, unlike a global convex hull, it
    isolates a discrete feature from the overall spectral slope. Water
    reflectance falls steeply and convexly from blue to NIR, so a global hull
    over 400-900 nm sits far above the spectrum in the red and reports large
    apparent depths for every pixel, feature or not.

    Reference: Clark & Roush (1984), JGR 89(B7):6329-6340.
    """
    rl = _mean_around(wl, spec, left_nm, halfwidth)
    rc = _mean_around(wl, spec, centre_nm, halfwidth)
    rr = _mean_around(wl, spec, right_nm, halfwidth)
    if not all(np.isfinite([rl, rc, rr])) or right_nm == left_nm:
        return float("nan")
    frac = (centre_nm - left_nm) / (right_nm - left_nm)
    cont = rl + (rr - rl) * frac
    if abs(cont) < 1e-9:
        return float("nan")
    return float(1.0 - rc / cont)


# Shoulder definitions for the diagnostic features, chosen so the continuum
# sits on genuine local maxima either side of each absorption.
BAND_DEPTH_WINDOWS = {
    "chl_a_675": {"left": 650.0, "centre": 675.0, "right": 715.0,
                  "meaning": "Chlorophyll-a red absorption maximum"},
    "phycocyanin_620": {"left": 600.0, "centre": 620.0, "right": 650.0,
                        "meaning": "Phycocyanin absorption (cyanobacteria)"},
    "chl_a_443": {"left": 412.0, "centre": 443.0, "right": 490.0,
                  "meaning": "Chlorophyll-a Soret absorption"},
}


# --------------------------------------------------------------------------- #
# Diagnostic wavelengths for water constituents
# --------------------------------------------------------------------------- #
DIAGNOSTIC_FEATURES = {
    "chl_a_absorption_443": {
        "centre_nm": 443.0,
        "meaning": "Chlorophyll-a Soret absorption maximum",
        "reference": "Bricaud et al. (1995), JGR Oceans 100:13321-13332",
    },
    "chl_a_absorption_675": {
        "centre_nm": 675.0,
        "meaning": "Chlorophyll-a red absorption maximum",
        "reference": "Bricaud et al. (1995), JGR Oceans 100:13321-13332",
    },
    "chl_fluorescence_685": {
        "centre_nm": 685.0,
        "meaning": "Sun-induced chlorophyll fluorescence peak",
        "reference": "Gower et al. (1999), Int. J. Remote Sensing 20:1771-1786",
    },
    "red_edge_peak_705": {
        "centre_nm": 705.0,
        "meaning": "Red-edge reflectance peak; rises with algal biomass",
        "reference": "Gitelson et al. (2008), RSE 112:3582-3593",
    },
    "phycocyanin_620": {
        "centre_nm": 620.0,
        "meaning": "Phycocyanin absorption; cyanobacteria marker",
        "reference": "Simis et al. (2005), Limnol. Oceanogr. 50:237-245",
    },
    "cdom_slope_412_443": {
        "centre_nm": 412.0,
        "meaning": "Coloured dissolved organic matter; steep blue absorption",
        "reference": "Bricaud et al. (1981), Limnol. Oceanogr. 26:43-53",
    },
    "sediment_scatter_665": {
        "centre_nm": 665.0,
        "meaning": "Mineral suspended sediment backscatter",
        "reference": "Nechad et al. (2009), RSE 113:2141-2154",
    },
}
