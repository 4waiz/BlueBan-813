"""Water-quality spectral indices.

Every index below carries its source, the wavelengths it needs, the input
quantity it expects, its output units and the assumptions under which it is
valid. Nothing is computed from a formula whose provenance we cannot state.

IMPORTANT, and repeated in docs/LIMITATIONS.md: these are OPTICAL PROXIES.
NDCI is not chlorophyll-a in mg/m3. A turbidity index is not laboratory NTU.
They become quantitative only after calibration against in-situ measurements,
which this PoC does not have for the Gulf of Annaba. They are used here as
screening indicators and as features, never as reported concentrations.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

EPS = 1e-6


@dataclass
class IndexSpec:
    """Full declaration of one index, carried into provenance."""

    name: str
    long_name: str
    formula: str
    wavelengths_nm: dict
    reference: str
    input_quantity: str
    units_out: str
    valid_range: tuple
    interpretation: str
    assumptions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "long_name": self.long_name,
            "formula": self.formula,
            "wavelengths_nm": self.wavelengths_nm,
            "reference": self.reference,
            "input_quantity": self.input_quantity,
            "units_out": self.units_out,
            "valid_range": list(self.valid_range),
            "interpretation": self.interpretation,
            "assumptions": self.assumptions,
        }


def _nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Normalised difference with a guarded denominator."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return (a - b) / (a + b + EPS)


# --------------------------------------------------------------------------- #
# Index specifications
# --------------------------------------------------------------------------- #
SPEC_NDWI = IndexSpec(
    name="NDWI",
    long_name="Normalized Difference Water Index",
    formula="(Green - NIR) / (Green + NIR)",
    wavelengths_nm={"green": 560, "nir": 860},
    reference="McFeeters (1996), Int. J. Remote Sensing 17(7):1425-1432",
    input_quantity="surface reflectance (unitless, 0-1)",
    units_out="dimensionless",
    valid_range=(-1.0, 1.0),
    interpretation="> 0 generally open water; sensitive to built surfaces",
    assumptions=["Atmospherically corrected reflectance",
                 "Breaks down over bright urban surfaces (use MNDWI there)"],
)

SPEC_MNDWI = IndexSpec(
    name="MNDWI",
    long_name="Modified Normalized Difference Water Index",
    formula="(Green - SWIR1) / (Green + SWIR1)",
    wavelengths_nm={"green": 560, "swir1": 1610},
    reference="Xu (2006), Int. J. Remote Sensing 27(14):3025-3033",
    input_quantity="surface reflectance (unitless, 0-1)",
    units_out="dimensionless",
    valid_range=(-1.0, 1.0),
    interpretation="> 0 water; suppresses built-up false positives better than NDWI",
    assumptions=["Requires a clean SWIR band",
                 "SWIR is strongly absorbed by water, so contrast is high"],
)

SPEC_NDCI = IndexSpec(
    name="NDCI",
    long_name="Normalized Difference Chlorophyll Index",
    formula="(RE705 - Red665) / (RE705 + Red665)",
    wavelengths_nm={"red_edge": 705, "red": 665},
    reference="Mishra & Mishra (2012), Remote Sensing of Environment 117:394-406",
    input_quantity="surface reflectance / Rrs (unitless)",
    units_out="dimensionless proxy (NOT mg/m3)",
    valid_range=(-1.0, 1.0),
    interpretation="Higher values indicate stronger chlorophyll-a absorption "
                   "contrast; a screening proxy only",
    assumptions=[
        "Designed for turbid productive inland/coastal water",
        "Loses sensitivity in clear oligotrophic water where the 705 nm peak is weak",
        "Requires an in-situ calibration to become a concentration",
    ],
)

SPEC_TURBIDITY = IndexSpec(
    name="TURBIDITY_PROXY",
    long_name="Red/Green normalized turbidity proxy",
    formula="(Red665 - Green560) / (Red665 + Green560)",
    wavelengths_nm={"red": 665, "green": 560},
    reference="Used as the turbidity proxy in the official 813 challenge "
              "notebook 06; consistent in form with red-band turbidity "
              "indicators such as Nechad et al. (2009), RSE 113:2141-2154",
    input_quantity="surface reflectance (unitless, 0-1)",
    units_out="dimensionless proxy (NOT NTU/FNU)",
    valid_range=(-1.0, 1.0),
    interpretation="Higher values indicate relatively stronger red backscatter, "
                   "typical of suspended sediment",
    assumptions=["Not a calibrated turbidity retrieval",
                 "Sensitive to bottom reflectance in shallow water"],
)

SPEC_FAI = IndexSpec(
    name="FAI",
    long_name="Floating Algae Index",
    formula="R_NIR - [R_RED + (R_SWIR - R_RED) * (nir - red)/(swir - red)]",
    wavelengths_nm={"red": 665, "nir": 859, "swir": 1610},
    reference="Hu (2009), Remote Sensing of Environment 113:2118-2129",
    input_quantity="surface reflectance (unitless, 0-1)",
    units_out="reflectance difference (unitless)",
    valid_range=(-0.1, 0.3),
    interpretation="Positive values indicate NIR elevation above the baseline, "
                   "characteristic of floating/surface algal material",
    assumptions=["More robust to thin cloud and glint than NDVI over water",
                 "Detects FLOATING material; subsurface blooms may not register"],
)

SPEC_CHL_RED_EDGE = IndexSpec(
    name="CHL_RE_RATIO",
    long_name="Red-edge to red band ratio",
    formula="R_705 / R_665",
    wavelengths_nm={"red_edge": 705, "red": 665},
    reference="Gitelson et al. (2008), RSE 112:3582-3593 (two-band red-edge model)",
    input_quantity="surface reflectance / Rrs (unitless)",
    units_out="dimensionless ratio",
    valid_range=(0.0, 5.0),
    interpretation="The two-band red-edge model underlying many chlorophyll-a "
                   "retrievals; a proxy until locally calibrated",
    assumptions=["Requires narrow bands near 665 and 705 nm",
                 "Multispectral sensors without a 705 nm band cannot form it"],
)

ALL_SPECS = {
    s.name: s for s in (SPEC_NDWI, SPEC_MNDWI, SPEC_NDCI, SPEC_TURBIDITY,
                        SPEC_FAI, SPEC_CHL_RED_EDGE)
}


# --------------------------------------------------------------------------- #
# Computation
# --------------------------------------------------------------------------- #
def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    return _nd(green, nir)


def mndwi(green: np.ndarray, swir1: np.ndarray) -> np.ndarray:
    return _nd(green, swir1)


def ndci(red_edge: np.ndarray, red: np.ndarray) -> np.ndarray:
    return _nd(red_edge, red)


def turbidity_proxy(red: np.ndarray, green: np.ndarray) -> np.ndarray:
    return _nd(red, green)


def chl_red_edge_ratio(red_edge: np.ndarray, red: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return red_edge / (red + EPS)


def fai(red: np.ndarray, nir: np.ndarray, swir: np.ndarray,
        red_nm: float = 665.0, nir_nm: float = 859.0,
        swir_nm: float = 1610.0) -> np.ndarray:
    """Floating Algae Index (Hu 2009).

    Baseline-subtracted NIR: linearly interpolate between the red and SWIR
    bands to the NIR wavelength, then measure how far the observed NIR sits
    above that baseline.
    """
    frac = (nir_nm - red_nm) / (swir_nm - red_nm)
    baseline = red + (swir - red) * frac
    return nir - baseline


def compute_all(bands: dict) -> dict:
    """Compute the standard index set from a dict of named reflectance arrays.

    ``bands`` must contain keys: green, red, red_edge, nir, swir1.
    """
    out = {
        "NDWI": ndwi(bands["green"], bands["nir"]),
        "MNDWI": mndwi(bands["green"], bands["swir1"]),
        "NDCI": ndci(bands["red_edge"], bands["red"]),
        "TURBIDITY_PROXY": turbidity_proxy(bands["red"], bands["green"]),
        "CHL_RE_RATIO": chl_red_edge_ratio(bands["red_edge"], bands["red"]),
        "FAI": fai(bands["red"], bands["nir"], bands["swir1"]),
    }
    return out


def clip_to_valid(name: str, arr: np.ndarray) -> np.ndarray:
    """Set physically impossible values to NaN rather than clamping them.

    Clamping would hide a processing problem; NaN surfaces it.
    """
    spec = ALL_SPECS.get(name)
    if spec is None:
        return arr
    lo, hi = spec.valid_range
    out = arr.copy()
    out[(out < lo) | (out > hi)] = np.nan
    return out


# --------------------------------------------------------------------------- #
# Uncertainty-aware normalised differences
# --------------------------------------------------------------------------- #
def nd_with_uncertainty(a: np.ndarray, b: np.ndarray,
                        sigma_a: np.ndarray, sigma_b: np.ndarray):
    """Normalised difference plus its propagated 1-sigma uncertainty.

    For ND = (a - b) / (a + b), standard first-order propagation gives

        d(ND)/da =  2b / (a + b)^2
        d(ND)/db = -2a / (a + b)^2
        sigma_ND = 2 * sqrt(b^2 * sigma_a^2 + a^2 * sigma_b^2) / (a + b)^2

    Returns ``(nd, sigma_nd)``.
    """
    s = a + b
    with np.errstate(invalid="ignore", divide="ignore"):
        nd = (a - b) / s
        sig = 2.0 * np.sqrt((b * sigma_a) ** 2 + (a * sigma_b) ** 2) / (s ** 2)
    return nd, sig


def significance_mask(a: np.ndarray, b: np.ndarray,
                      sigma_a: np.ndarray, sigma_b: np.ndarray,
                      k: float = 3.0) -> np.ndarray:
    """Pixels where a normalised difference is numerically meaningful.

    Over dark water the denominator (a + b) approaches the noise floor, and the
    ratio explodes: on the Gulf of Annaba scene, a naive NDCI on all water
    pixels spans -1907 to +2407 because ~0.5% of pixels have R705 + R665 <= 0
    after atmospheric correction. Those values are not weak signal, they are
    division by noise.

    This test keeps a pixel only when the denominator exceeds ``k`` times its
    own propagated uncertainty, using the sensor's per-pixel uncertainty layer
    rather than a hand-tuned epsilon.
    """
    s = a + b
    sig_s = np.sqrt(sigma_a ** 2 + sigma_b ** 2)
    return np.isfinite(s) & np.isfinite(sig_s) & (s > k * sig_s)


def compute_all_with_uncertainty(bands: dict, sigmas: dict, k: float = 3.0):
    """Index set with propagated uncertainty and a significance mask per index.

    ``bands`` and ``sigmas`` share keys: green, red, red_edge, nir, swir1.
    Returns ``(values, uncertainties, masks)``; values are already NaN where the
    significance test fails, so downstream code cannot accidentally use them.
    """
    pairs = {
        "NDWI": ("green", "nir"),
        "MNDWI": ("green", "swir1"),
        "NDCI": ("red_edge", "red"),
        "TURBIDITY_PROXY": ("red", "green"),
    }
    values, uncs, masks = {}, {}, {}
    for name, (ka, kb) in pairs.items():
        a, b = bands[ka], bands[kb]
        sa, sb = sigmas[ka], sigmas[kb]
        nd, sig = nd_with_uncertainty(a, b, sa, sb)
        m = significance_mask(a, b, sa, sb, k)
        nd = np.where(m, nd, np.nan)
        sig = np.where(m, sig, np.nan)
        values[name] = clip_to_valid(name, nd)
        uncs[name] = sig
        masks[name] = m

    # FAI is a difference, not a ratio, so it has no denominator blow-up.
    values["FAI"] = fai(bands["red"], bands["nir"], bands["swir1"])
    frac = (859.0 - 665.0) / (1610.0 - 665.0)
    uncs["FAI"] = np.sqrt(
        sigmas["nir"] ** 2
        + ((1 - frac) * sigmas["red"]) ** 2
        + (frac * sigmas["swir1"]) ** 2
    )
    masks["FAI"] = np.isfinite(values["FAI"])
    return values, uncs, masks
