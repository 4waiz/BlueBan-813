"""Sentinel-2 MSI Level-2A water-quality features.

This is the primary high-resolution detection path (mentor points 1-4). It
turns an atmospherically corrected Sentinel-2 L2A acquisition into a documented
set of water-quality FEATURES. Every feature declares:

* its formula and the Sentinel-2 bands it uses,
* the native resolution it is really valid at (the coarsest band it touches),
* the published source of the formula and of any coefficients,
* its known limitations,
* its QUANTITY KIND, which decides what the interface is allowed to print:

    PROXY                an index; unitless or reflectance units. Never a
                         concentration.
    GENERIC_CALIBRATION  a semi-analytical algorithm with PUBLISHED coefficients
                         (e.g. Nechad 2016 turbidity). It has physical units, but
                         the coefficients were calibrated elsewhere and have not
                         been validated in UAE waters. Shown with its units and a
                         "not locally validated" flag.
    COLORIMETRIC         a physical colour metric (hue angle, degrees).
    MASK                 a water/quality mask input.

A value only becomes CALIBRATED (and may be printed as mg/m3 or NTU with an
interval) after pipeline/quantify.py has fitted it against local in-situ
matchups under grouped validation. Nothing in this module can produce that.

Coefficient provenance. Every coefficient below is copied from the ACOLITE
repository's tabulations of the original publications (github.com/acolite/acolite,
data/Shared/algorithms/{Nechad,Dogliotti,VanderWoerd}), which are the reference
implementations the ocean-colour community uses. None was typed from memory.

Reflectance convention. Sen2Cor L2A delivers bottom-of-atmosphere surface
reflectance rho_s. The semi-analytical algorithms expect water-leaving
reflectance rho_w = pi * Rrs. Over water rho_s = rho_w + surface-reflected sky and
sun light + residual atmospheric error. Liquid water leaves essentially no signal
at 2190 nm, so B12 estimates that residual under a spectrally flat assumption
(Kay et al. 2009 review of glint correction; Harmel et al. 2018 use SWIR for the
same purpose). ``surface_correction="swir_b12"`` subtracts it; the choice is
recorded on every output. Sen2Cor is a land processor (Warren et al. 2019, RSE
225:267-289: "designed for land with no water application"), and this
correction does not turn it into a water processor; it removes the largest
first-order bias only.

Glint. Over the UAE, and especially the Gulf of Oman in spring and summer,
Sen2Cor L2A B11 over open water is typically 0.03-0.05 (measured: median 0.037
over the Fujairah sea on 2026-04-02, SCL = water for 99.6 % of it). ACOLITE's
non-water threshold rho_s(1600) > 0.0215 assumes ACOLITE's own glint-corrected
output; applied to raw L2A it discards almost all water. Here SWIR is therefore
used only to reject land, cloud, whitecaps and strong glint (B11 >= 0.10), pixels
with B11 > 0.0215 are FLAGGED as glint-affected, and every water-colour feature is
computed on the SWIR-offset-corrected reflectance. MCI and FAI are baseline
heights and are unchanged by a spectrally flat offset; normalised differences and
ratios (NDCI, RE_RATIO, CDOM_RATIO) are biased toward zero by it, which is why
they are computed after the correction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

EPS = 1e-9

# --------------------------------------------------------------------------- #
# Band table
# --------------------------------------------------------------------------- #
# Central wavelengths per platform from the ESA Sentinel-2 MSI spectral response
# functions (S2-SRF, COPE-GSEG-EOPG-TN-15-0007). S2C has no separate table in
# ACOLITE either; it is treated as S2B, which is what ACOLITE does
# (hue_angle.txt: "S2C as copy of S2B").
S2_CENTRES_NM = {
    "Sentinel-2A": {"B01": 442.7, "B02": 492.7, "B03": 559.8, "B04": 664.6,
                    "B05": 704.1, "B06": 740.5, "B07": 782.8, "B08": 832.8,
                    "B8A": 864.7, "B09": 945.1, "B11": 1613.7, "B12": 2202.4},
    "Sentinel-2B": {"B01": 442.2, "B02": 492.1, "B03": 559.0, "B04": 664.9,
                    "B05": 703.8, "B06": 739.1, "B07": 779.7, "B08": 832.9,
                    "B8A": 864.0, "B09": 943.2, "B11": 1610.4, "B12": 2185.7},
}
S2_CENTRES_NM["Sentinel-2C"] = dict(S2_CENTRES_NM["Sentinel-2B"])

S2_NATIVE_RES_M = {"B01": 60, "B02": 10, "B03": 10, "B04": 10, "B05": 20,
                   "B06": 20, "B07": 20, "B08": 10, "B8A": 20, "B09": 60,
                   "B11": 20, "B12": 20}

#: Bands read for water work. B09 (water vapour) carries atmosphere, not water.
WATER_BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A",
               "B11", "B12"]

# Sentinel-2 L2A integer encoding. From processing baseline 04.00 ESA added
# BOA_ADD_OFFSET = -1000 to every band (S2 L2A PSD v14.9; ESA "Sentinel-2
# Processing Baseline 04.00" note, 2021-11). The switch is the PRODUCT'S OWN
# processing baseline, not its acquisition date: ESA has reprocessed older data
# with new baselines, so a date rule silently mis-scales reprocessed products.
S2_QUANTIFICATION = 10000.0
S2_BOA_ADD_OFFSET = -1000.0


def boa_offset_for_baseline(baseline: str | float | None) -> float:
    """BOA_ADD_OFFSET implied by an L2A processing baseline string ("05.13")."""
    if baseline is None:
        raise ValueError("processing baseline is required to decode L2A DNs; "
                         "refusing to guess from the acquisition date")
    try:
        b = float(baseline)
    except (TypeError, ValueError) as e:
        raise ValueError(f"unparseable processing baseline {baseline!r}") from e
    return S2_BOA_ADD_OFFSET if b >= 4.0 else 0.0


def dn_to_reflectance(dn: np.ndarray, baseline: str | float | None) -> np.ndarray:
    """Decode raw L2A digital numbers to surface reflectance.

    ``0`` is the L2A no-data value and becomes NaN. Values are NOT clipped at 0:
    small negative reflectances over dark water are a real symptom of
    atmospheric over-correction and must stay visible to the quality checks.
    """
    a = np.asarray(dn, dtype="float32")
    out = (a + boa_offset_for_baseline(baseline)) / S2_QUANTIFICATION
    out[a == 0] = np.nan
    return out


# --------------------------------------------------------------------------- #
# Scene Classification Layer
# --------------------------------------------------------------------------- #
SCL_CLASSES = {
    0: "no_data", 1: "saturated_defective", 2: "topographic_casted_shadows",
    3: "cloud_shadow", 4: "vegetation", 5: "not_vegetated", 6: "water",
    7: "unclassified", 8: "cloud_medium_probability",
    9: "cloud_high_probability", 10: "thin_cirrus", 11: "snow_ice",
}
#: Classes that make a pixel unusable for water optics. Class 2 (dark area /
#: casted shadow) is NOT excluded: Sen2Cor frequently assigns it to clear dark
#: water. Classes 4/5 are not excluded either, because dense surface blooms and
#: very turbid water are regularly misclassified as vegetation or bare soil; the
#: water decision is made by the reflectance-based mask, not by SCL.
SCL_UNUSABLE = (0, 1, 3, 8, 9, 10, 11)


def scl_usable(scl: np.ndarray) -> np.ndarray:
    return ~np.isin(np.asarray(scl), SCL_UNUSABLE)


# --------------------------------------------------------------------------- #
# Feature specifications
# --------------------------------------------------------------------------- #
QUANTITY_KINDS = ("PROXY", "GENERIC_CALIBRATION", "COLORIMETRIC", "MASK")


@dataclass
class FeatureSpec:
    name: str
    long_name: str
    formula: str
    bands: list
    native_resolution_m: int
    quantity_kind: str
    units: str
    reference: str
    limitations: list
    coefficients: dict = field(default_factory=dict)
    coefficient_source: str = ""
    valid_range: tuple = (-np.inf, np.inf)

    def __post_init__(self):
        if self.quantity_kind not in QUANTITY_KINDS:
            raise ValueError(f"{self.name}: unknown quantity kind {self.quantity_kind}")

    def to_dict(self) -> dict:
        return {
            "name": self.name, "long_name": self.long_name,
            "formula": self.formula, "bands": self.bands,
            "native_resolution_m": self.native_resolution_m,
            "quantity_kind": self.quantity_kind, "units": self.units,
            "reference": self.reference, "limitations": self.limitations,
            "coefficients": self.coefficients,
            "coefficient_source": self.coefficient_source,
            "valid_range": [None if not np.isfinite(v) else v
                            for v in self.valid_range],
            "locally_validated": False,
        }


def _res(*bands) -> int:
    return max(S2_NATIVE_RES_M[b] for b in bands)


ACOLITE_SRC = ("ACOLITE tabulation, github.com/acolite/acolite "
               "data/Shared/algorithms/")

# Nechad 2016 Sentinel-2 calibration ("coefficients provided by BN 201609,
# tabulated by QV 201610"), file Nechad/Nechad_calibration_201609.txt.
NECHAD2016_MSI = {
    "TUR": {"B04": (366.14, 0.19563), "B05": (439.09, 0.18753),
            "B8A": (3250.32, 0.21151)},
    "SPM": {"B04": (342.10, 0.19563), "B05": (444.36, 0.18753),
            "B8A": (2932.21, 0.21151)},
}
#: ACOLITE default: values with rho_w >= 0.5 C are outside the algorithm's
#: validity (the denominator approaches zero) and are masked
#: (config/defaults.txt, nechad_max_rhow_C_factor=0.5).
NECHAD_MAX_RHOW_C_FACTOR = 0.5

# Dogliotti et al. (2015) switching turbidity, Dogliotti/defaults.txt.
DOGLIOTTI2015 = {"A_red": 228.1, "C_red": 0.1641, "wave_red": 645,
                 "A_nir": 3078.9, "C_nir": 0.2112, "wave_nir": 859,
                 "lower_lim": 0.05, "upper_lim": 0.07}

# Van der Woerd & Wernand (2018) hue angle, VanderWoerd/hue_angle.txt.
HUE_COEF = {
    "Sentinel-2A": {
        "bands": ["B01", "B02", "B03", "B04", "B05"],
        "X": [11.756, 6.423, 53.696, 32.028, 0.529],
        "Y": [1.744, 22.289, 65.702, 16.808, 0.192],
        "Z": [62.696, 31.101, 1.778, 0.015, 0.000],
        "coef": [-68.76, 495.18, -1315.60, 1547.60, -748.36, 113.25],
    },
    "Sentinel-2B": {
        "bands": ["B01", "B02", "B03", "B04", "B05"],
        "X": [11.756, 6.423, 53.696, 32.028, 0.529],
        "Y": [1.744, 22.289, 65.702, 16.808, 0.192],
        "Z": [62.696, 31.101, 1.778, 0.015, 0.000],
        "coef": [-70.78, 510.49, -1360.3, 1608.6, -785.63, 121.34],
    },
}
HUE_COEF["Sentinel-2C"] = HUE_COEF["Sentinel-2B"]

FEATURES: dict[str, FeatureSpec] = {}


def _register(spec: FeatureSpec) -> FeatureSpec:
    FEATURES[spec.name] = spec
    return spec


_register(FeatureSpec(
    "MNDWI", "Modified Normalized Difference Water Index",
    "(B03 - B11) / (B03 + B11)", ["B03", "B11"], _res("B03", "B11"), "MASK",
    "dimensionless", "Xu (2006) Int. J. Remote Sens. 27(14):3025-3033",
    ["Water/non-water separation only",
     "Built surfaces and wet sand can exceed low thresholds"],
    valid_range=(-1.0, 1.0)))

_register(FeatureSpec(
    "SWIR_B11", "Short-wave infrared surface reflectance at 1610 nm",
    "B11", ["B11"], _res("B11"), "MASK", "reflectance",
    "ACOLITE default non-water mask rho_s(1600) > 0.0215 "
    "(config/defaults.txt l2w_mask_threshold)",
    ["Also flags glint, whitecaps and floating material as non-water"]))

_register(FeatureSpec(
    "NDCI", "Normalized Difference Chlorophyll Index",
    "(B05 - B04) / (B05 + B04)", ["B04", "B05"], _res("B04", "B05"), "PROXY",
    "dimensionless", "Mishra & Mishra (2012) Remote Sens. Environ. 117:394-406",
    ["Proxy for chlorophyll-a absorption contrast, NOT mg/m3",
     "Designed for turbid productive water; weak in clear oligotrophic water",
     "Raised by bright bottom and by sediment red-edge scattering",
     "Becomes a concentration only after local in-situ calibration"],
    valid_range=(-1.0, 1.0)))

_register(FeatureSpec(
    "MCI", "Maximum Chlorophyll Index (Sentinel-2 adaptation)",
    "B05 - B04 - (B06 - B04) * (l5 - l4) / (l6 - l4)",
    ["B04", "B05", "B06"], _res("B04", "B05", "B06"), "PROXY", "reflectance",
    "Gower et al. (2005) Int. J. Remote Sens. 26(9):2005-2012 (MERIS); "
    "S2 band adaptation as in Toming et al. (2016) Remote Sens. 8(8):640",
    ["Peak height above a red-to-NIR baseline; responds to high-biomass "
     "blooms and floating vegetation",
     "S2 B05 (20 m, ~15 nm wide) is broader than MERIS 709 nm, so absolute "
     "values are not comparable with MERIS/OLCI MCI",
     "Negative in clear water; sediment-rich water can also raise it"]))

_register(FeatureSpec(
    "FAI", "Floating Algae Index (Sentinel-2 adaptation)",
    "B8A - [B04 + (B11 - B04) * (l8A - l4) / (l11 - l4)]",
    ["B04", "B8A", "B11"], _res("B04", "B8A", "B11"), "PROXY", "reflectance",
    "Hu (2009) Remote Sens. Environ. 113:2118-2129",
    ["Detects material AT the surface (floating algae, scum, sargassum, "
     "some surface films); subsurface blooms may not register",
     "Positive values also come from whitecaps and land adjacency"]))

_register(FeatureSpec(
    "RE_RATIO", "Red-edge to red band ratio",
    "B05 / B04", ["B04", "B05"], _res("B04", "B05"), "PROXY", "dimensionless",
    "Gitelson et al. (2008) Remote Sens. Environ. 112:3582-3593 "
    "(two-band red-edge model)",
    ["Proxy until locally calibrated",
     "Unstable when B04 approaches the noise floor"],
    valid_range=(0.0, 10.0)))

_register(FeatureSpec(
    "CDOM_RATIO", "Green-to-red ratio (CDOM / clarity proxy)",
    "B03 / B04", ["B03", "B04"], _res("B03", "B04"), "PROXY", "dimensionless",
    "Kutser et al. (2005) Remote Sens. Environ. 94:535-540 (green/red ratio "
    "for CDOM); used with S2 in Toming et al. (2016)",
    ["Confounded by chlorophyll and sediment; a relative indicator only",
     "Calibrations are water-body specific"],
    valid_range=(0.0, 20.0)))

_register(FeatureSpec(
    "TUR_NECHAD2016", "Turbidity, Nechad single-band algorithm (S2 B04)",
    "A * rho_w / (1 - rho_w / C), rho_w at B04",
    ["B04", "B12"], _res("B04"), "GENERIC_CALIBRATION", "FNU",
    "Nechad, Ruddick & Park (2009) Remote Sens. Environ. 113:2141-2154; "
    "S2 MSI coefficients: Nechad 2016 calibration",
    ["Coefficients calibrated on North Sea / Scheldt data, NOT on UAE waters",
     "Saturates in very turbid water (use the NIR branch / Dogliotti)",
     "Bright shallow bottom is read as turbidity",
     "Requires water-leaving reflectance; L2A surface reflectance is an "
     "approximation even after the SWIR offset"],
    coefficients={"A": NECHAD2016_MSI["TUR"]["B04"][0],
                  "C": NECHAD2016_MSI["TUR"]["B04"][1],
                  "mask_rho_w_ge_C_times": NECHAD_MAX_RHOW_C_FACTOR},
    coefficient_source=ACOLITE_SRC + "Nechad/Nechad_calibration_201609.txt",
    valid_range=(0.0, 1000.0)))

_register(FeatureSpec(
    "SPM_NECHAD2016", "Suspended particulate matter, Nechad (S2 B04)",
    "A * rho_w / (1 - rho_w / C), rho_w at B04",
    ["B04", "B12"], _res("B04"), "GENERIC_CALIBRATION", "g m-3",
    "Nechad, Ruddick & Park (2010) Remote Sens. Environ. 114:854-866; "
    "S2 MSI coefficients: Nechad 2016 calibration",
    ["Coefficients calibrated outside the UAE; mass-specific scattering of "
     "Gulf carbonate sediment differs from North Sea mineral sediment",
     "Not a laboratory TSS value"],
    coefficients={"A": NECHAD2016_MSI["SPM"]["B04"][0],
                  "C": NECHAD2016_MSI["SPM"]["B04"][1],
                  "mask_rho_w_ge_C_times": NECHAD_MAX_RHOW_C_FACTOR},
    coefficient_source=ACOLITE_SRC + "Nechad/Nechad_calibration_201609.txt",
    valid_range=(0.0, 1000.0)))

_register(FeatureSpec(
    "TUR_DOGLIOTTI2015", "Turbidity, Dogliotti red/NIR switching algorithm",
    "T_red if rho_w(B04)<0.05; T_nir if >0.07; linear blend between; "
    "T = A rho_w / (1 - rho_w / C)",
    ["B04", "B8A", "B12"], _res("B04", "B8A"), "GENERIC_CALIBRATION", "FNU",
    "Dogliotti et al. (2015) Remote Sens. Environ. 156:157-168",
    ["Published coefficients are for 645/859 nm and are applied to the "
     "closest S2 bands (665/865 nm), exactly as ACOLITE does",
     "Not validated in UAE waters", "Bright bottom is read as turbidity"],
    coefficients=dict(DOGLIOTTI2015),
    coefficient_source=ACOLITE_SRC + "Dogliotti/defaults.txt",
    valid_range=(0.0, 4000.0)))

_register(FeatureSpec(
    "HUE_ANGLE", "Water-colour hue angle (Forel-Ule compatible)",
    "alpha = atan2(y - 1/3, x - 1/3) from CIE chromaticity of B01-B05, "
    "plus a 5th-order sensor correction polynomial",
    ["B01", "B02", "B03", "B04", "B05"], _res("B01", "B02", "B03", "B04", "B05"),
    "COLORIMETRIC", "degrees",
    "Van der Woerd & Wernand (2018) Remote Sens. 10(2):180; "
    "Wernand et al. (2013) PLoS ONE 8(6):e63766",
    ["A colour, not a constituent. The angle DECREASES from blue to brown: "
     "clear blue water ~200-230 deg, green ~90-120 deg, brown ~20-60 deg",
     "B01 is 60 m, so the angle is effectively a 60 m product"],
    coefficients={"S2A": HUE_COEF["Sentinel-2A"]["coef"],
                  "S2B/S2C": HUE_COEF["Sentinel-2B"]["coef"]},
    coefficient_source=ACOLITE_SRC + "VanderWoerd/hue_angle.txt",
    valid_range=(0.0, 360.0)))


# --------------------------------------------------------------------------- #
# Computation
# --------------------------------------------------------------------------- #
def _nd(a, b):
    with np.errstate(invalid="ignore", divide="ignore"):
        return (a - b) / (a + b)


def _baseline_height(peak, left, right, l_peak, l_left, l_right):
    """Height of ``peak`` above the straight line joining ``left`` and ``right``."""
    frac = (l_peak - l_left) / (l_right - l_left)
    return peak - (left + (right - left) * frac)


def _nechad(rho_w, A, C, factor=NECHAD_MAX_RHOW_C_FACTOR):
    with np.errstate(invalid="ignore", divide="ignore"):
        out = A * rho_w / (1.0 - rho_w / C)
    out = np.where(rho_w >= factor * C, np.nan, out)
    return out


def surface_corrected(refl: dict, method: str | None = "swir_b12") -> dict:
    """Approximate water-leaving reflectance by removing a flat SWIR residual."""
    if method is None:
        return dict(refl)
    if method != "swir_b12":
        raise ValueError(f"unknown surface correction {method!r}")
    off = refl["B12"]
    return {b: (v - off if b not in ("B11", "B12") else v)
            for b, v in refl.items()}


def hue_angle(refl: dict, platform: str) -> np.ndarray:
    """Van der Woerd & Wernand (2018) hue angle, reproducing ACOLITE's code."""
    c = HUE_COEF.get(platform)
    if c is None:
        raise ValueError(f"no hue-angle coefficients for {platform!r}")
    X = sum(refl[b] * w for b, w in zip(c["bands"], c["X"]))
    Y = sum(refl[b] * w for b, w in zip(c["bands"], c["Y"]))
    Z = sum(refl[b] * w for b, w in zip(c["bands"], c["Z"]))
    with np.errstate(invalid="ignore", divide="ignore"):
        den = X + Y + Z
        x, y = X / den, Y / den
    alpha = np.degrees(np.mod(np.arctan2(y - 1 / 3, x - 1 / 3), 2 * np.pi))
    h = alpha / 100.0
    k = c["coef"]
    corr = k[0] * h ** 5 + k[1] * h ** 4 + k[2] * h ** 3 + k[3] * h ** 2 + k[4] * h + k[5]
    return alpha + corr


def compute_features(refl: dict, platform: str = "Sentinel-2A",
                     surface_correction: str | None = "swir_b12") -> dict:
    """All features for one acquisition.

    ``refl`` maps band name -> surface-reflectance array (already decoded with
    :func:`dn_to_reflectance`). MNDWI and SWIR_B11 (mask inputs) and FAI (which
    needs the SWIR band itself) use the uncorrected reflectance; every other
    water-colour feature uses the ``surface_correction`` reflectance, because the
    indices are defined on water-leaving reflectance and a flat glint offset
    biases every ratio.

    Returns ``{name: array}``. Values outside a feature's valid range become NaN
    rather than being clamped, so a processing problem stays visible.
    """
    lam = S2_CENTRES_NM.get(platform, S2_CENTRES_NM["Sentinel-2A"])
    r = refl
    w = surface_corrected(refl, surface_correction)
    out = {}
    out["MNDWI"] = _nd(r["B03"], r["B11"])
    out["SWIR_B11"] = r["B11"]
    out["NDCI"] = _nd(w["B05"], w["B04"])
    out["MCI"] = _baseline_height(w["B05"], w["B04"], w["B06"],
                                  lam["B05"], lam["B04"], lam["B06"])
    out["FAI"] = _baseline_height(r["B8A"], r["B04"], r["B11"],
                                  lam["B8A"], lam["B04"], lam["B11"])
    with np.errstate(invalid="ignore", divide="ignore"):
        out["RE_RATIO"] = np.where(w["B04"] > 1e-3, w["B05"] / w["B04"], np.nan)
        out["CDOM_RATIO"] = np.where(w["B04"] > 1e-3, w["B03"] / w["B04"], np.nan)
    A, C = NECHAD2016_MSI["TUR"]["B04"]
    out["TUR_NECHAD2016"] = _nechad(w["B04"], A, C)
    A, C = NECHAD2016_MSI["SPM"]["B04"]
    out["SPM_NECHAD2016"] = _nechad(w["B04"], A, C)
    d = DOGLIOTTI2015
    red, nir = w["B04"], w["B8A"]
    with np.errstate(invalid="ignore", divide="ignore"):
        t_red = d["A_red"] * red / (1.0 - red / d["C_red"])
        t_nir = d["A_nir"] * nir / (1.0 - nir / d["C_nir"])
    wgt = np.clip((red - d["lower_lim"]) / (d["upper_lim"] - d["lower_lim"]), 0, 1)
    out["TUR_DOGLIOTTI2015"] = (1 - wgt) * t_red + wgt * t_nir
    if all(b in w for b in HUE_COEF["Sentinel-2A"]["bands"]):
        out["HUE_ANGLE"] = hue_angle(w, platform if platform in HUE_COEF
                                     else "Sentinel-2A")
    for name, arr in out.items():
        lo, hi = FEATURES[name].valid_range
        a = np.asarray(arr, dtype="float32")
        a = np.where(np.isfinite(a) & ((a < lo) | (a > hi)), np.nan, a)
        out[name] = a
    return out


# --------------------------------------------------------------------------- #
# Water and quality masks
# --------------------------------------------------------------------------- #
@dataclass
class S2QualityReport:
    total_px: int
    valid_px: int
    scl_unusable_px: int
    water_px: int
    glint_or_float_px: int
    negative_red_px: int
    params: dict

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "total_px", "valid_px", "scl_unusable_px", "water_px",
            "glint_or_float_px", "negative_red_px")} | {
            "water_fraction": round(self.water_px / max(self.total_px, 1), 6),
            "params": self.params}


def water_quality_mask(refl: dict, scl: np.ndarray | None,
                       mndwi_min: float = 0.0, swir_reject: float = 0.10,
                       glint_flag: float = 0.0215,
                       shoreline_buffer_m: float = 40.0,
                       pixel_size_m: float = 20.0):
    """Open-water mask for water-colour work, plus an auditable report.

    A pixel is analysable water when it is valid, not flagged unusable by SCL,
    has MNDWI above ``mndwi_min`` and SWIR reflectance below ``swir_reject``
    (land, cloud, whitecaps, strong glint), is at least ``shoreline_buffer_m``
    from any non-water pixel, and keeps a non-negative red reflectance after the
    SWIR offset correction (negative corrected red is atmospheric
    over-correction). Pixels with B11 above ``glint_flag`` (the ACOLITE non-water
    threshold) stay in the mask but are counted as glint-affected.

    Returns ``(mask, report)``.
    """
    from .water_mask import _erode, _label_and_filter

    valid = np.isfinite(refl["B03"]) & np.isfinite(refl["B11"]) & np.isfinite(refl["B04"])
    usable = scl_usable(scl) if scl is not None else np.ones_like(valid)
    mndwi = _nd(refl["B03"], refl["B11"])
    swir_ok = refl["B11"] < swir_reject
    raw = valid & usable & (mndwi > mndwi_min) & swir_ok
    red_corr = refl["B04"] - refl["B12"] if "B12" in refl else refl["B04"]
    neg_red = raw & (red_corr < -0.002)
    raw &= ~neg_red
    raw = _label_and_filter(raw, 25)
    buf_px = int(round(shoreline_buffer_m / pixel_size_m))
    water = _erode(raw, buf_px)
    glinty = water & (refl["B11"] > glint_flag)
    rep_ = S2QualityReport(
        total_px=int(valid.size), valid_px=int(valid.sum()),
        scl_unusable_px=int((valid & ~usable).sum()),
        water_px=int(water.sum()),
        glint_or_float_px=int(glinty.sum()),
        negative_red_px=int(neg_red.sum()),
        params={"mndwi_min": mndwi_min, "swir_reject": swir_reject,
                "glint_flag_b11": glint_flag,
                "shoreline_buffer_m": shoreline_buffer_m,
                "pixel_size_m": pixel_size_m, "scl_unusable": list(SCL_UNUSABLE),
                "median_b11_water": (float(np.nanmedian(refl["B11"][water]))
                                     if water.any() else None)},
    )
    return water, rep_


def feature_table() -> list:
    """Every feature's declaration, for docs, provenance and the API."""
    return [s.to_dict() for s in FEATURES.values()]
