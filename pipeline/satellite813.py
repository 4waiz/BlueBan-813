"""Tanager-1 hyperspectral reader and the Satellite 813 sensor simulator.

Two responsibilities:

1. ``TanagerScene`` reads Planet Tanager-1 ortho surface-reflectance HDF5 cubes,
   honouring the product's own metadata: wavelengths, FWHM, per-band
   ``good_wavelengths`` flags, per-pixel uncertainty, quality masks and the
   geotransform in StructMetadata.0. Nothing here is hardcoded from a tutorial;
   every number comes out of the file.

2. ``simulate_813`` resamples a Tanager cube onto the published Satellite 813
   band configuration. 813 is incubation-only data (see docs/813_PRODUCT_NOTES.md),
   so the PoC answers the mission-utility question with an auditable simulator
   instead of pretending to hold data it does not have.

Spectral resampling uses Gaussian spectral response functions, the standard
approach for cross-sensor band synthesis and the same convolution used for
sensor intercomparison in ISOFIT/HyTools.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import h5py
import numpy as np

HDF_ROOT = "HDFEOS/GRIDS/HYP/Data Fields"
GRID_GROUP = "HDFEOS/GRIDS/HYP"
STRUCT_META = "HDFEOS INFORMATION/StructMetadata.0"
FILL = -9999.0


# --------------------------------------------------------------------------- #
# Tanager reader
# --------------------------------------------------------------------------- #
@dataclass
class SceneGrid:
    """Georeferencing of the cube, parsed from StructMetadata.0."""

    epsg: int
    transform: tuple           # GDAL-style (x0, dx, 0, y0, 0, dy)
    shape: tuple               # (rows, cols)
    pixel_size_m: float

    @property
    def bounds_native(self) -> tuple:
        x0, dx, _, y0, _, dy = self.transform
        rows, cols = self.shape
        return (x0, y0 + dy * rows, x0 + dx * cols, y0)


class TanagerScene:
    """Lazy reader for a Tanager-1 ortho SR cube.

    A full cube is 426 x rows x cols float32 (~1.4 GB in memory for a standard
    scene), so bands are read on demand and cached.
    """

    def __init__(self, path: str):
        self.path = path
        self._cache: dict[int, np.ndarray] = {}
        with h5py.File(path, "r") as f:
            sr = f[f"{HDF_ROOT}/surface_reflectance"]
            self.wavelengths = np.asarray(sr.attrs["wavelengths"], dtype=float)
            self.fwhm = np.asarray(sr.attrs["fwhm"], dtype=float)
            self.good_wavelengths = np.asarray(
                sr.attrs["good_wavelengths"]).astype(bool)
            self.units = str(sr.attrs.get("Unit", "unitless"))
            self.fill_value = float(sr.attrs.get("_FillValue", FILL))
            self.n_bands, self.rows, self.cols = sr.shape
            g = f[GRID_GROUP]
            self.epsg = int(g.attrs["epsg_code"])
            self.strip_id = str(g.attrs.get("strip_id", ""))
            self.created_at = str(g.attrs.get("created_at", ""))
            self.grid = self._parse_struct_meta(
                f[STRUCT_META][()].decode("utf-8", "replace"), self.epsg)
        self.scene_id = os.path.basename(path).split("_ortho")[0]

    # -- georeferencing ----------------------------------------------------- #
    @staticmethod
    def _parse_struct_meta(text: str, epsg: int) -> SceneGrid:
        def grab(key):
            m = re.search(rf"{key}=\(([^)]*)\)", text)
            return [float(v) for v in m.group(1).split(",")] if m else None

        def grab_i(key):
            m = re.search(rf"{key}=(\d+)", text)
            return int(m.group(1)) if m else None

        ul = grab("UpperLeftPointMtrs")
        lr = grab("LowerRightMtrs")
        cols = grab_i("XDim")
        rows = grab_i("YDim")
        if not (ul and lr and cols and rows):
            raise ValueError("Could not parse StructMetadata.0 georeferencing")
        dx = (lr[0] - ul[0]) / cols
        dy = (lr[1] - ul[1]) / rows          # negative (north-up)
        return SceneGrid(epsg=epsg, transform=(ul[0], dx, 0.0, ul[1], 0.0, dy),
                         shape=(rows, cols), pixel_size_m=abs(dx))

    # -- band access -------------------------------------------------------- #
    def band_index(self, target_nm: float) -> int:
        """Nearest band to a wavelength, restricted to product-good bands."""
        wl = np.where(self.good_wavelengths, self.wavelengths, np.inf)
        return int(np.argmin(np.abs(wl - target_nm)))

    def read_band(self, idx: int, mask_fill: bool = True) -> np.ndarray:
        if idx in self._cache:
            return self._cache[idx]
        with h5py.File(self.path, "r") as f:
            a = f[f"{HDF_ROOT}/surface_reflectance"][idx, :, :].astype("float32")
        if mask_fill:
            a[a == self.fill_value] = np.nan
        self._cache[idx] = a
        return a

    def read_at(self, target_nm: float):
        """Read the band nearest ``target_nm``; returns (array, actual_nm, idx)."""
        i = self.band_index(target_nm)
        return self.read_band(i), float(self.wavelengths[i]), i

    def read_cube(self, band_idx=None, row_step: int = 1, col_step: int = 1,
                  mask_fill: bool = True) -> np.ndarray:
        """Read a (bands, rows, cols) subcube. ``band_idx=None`` uses good bands."""
        if band_idx is None:
            band_idx = np.where(self.good_wavelengths)[0]
        band_idx = np.asarray(band_idx)
        with h5py.File(self.path, "r") as f:
            ds = f[f"{HDF_ROOT}/surface_reflectance"]
            out = ds[band_idx, ::row_step, ::col_step].astype("float32")
        if mask_fill:
            out[out == self.fill_value] = np.nan
        return out

    def read_spectrum(self, row: int, col: int, good_only: bool = True):
        """Full spectrum of one pixel, plus its per-band uncertainty."""
        with h5py.File(self.path, "r") as f:
            spec = f[f"{HDF_ROOT}/surface_reflectance"][:, row, col].astype("float32")
            unc = f[f"{HDF_ROOT}/surface_reflectance_uncertainty"][:, row, col].astype("float32")
        spec[spec == self.fill_value] = np.nan
        unc[unc == self.fill_value] = np.nan
        if good_only:
            g = self.good_wavelengths
            return self.wavelengths[g], spec[g], unc[g]
        return self.wavelengths, spec, unc

    def read_uncertainty_cube(self, band_idx=None, row_step=1, col_step=1) -> np.ndarray:
        if band_idx is None:
            band_idx = np.where(self.good_wavelengths)[0]
        band_idx = np.asarray(band_idx)
        with h5py.File(self.path, "r") as f:
            out = f[f"{HDF_ROOT}/surface_reflectance_uncertainty"][
                band_idx, ::row_step, ::col_step].astype("float32")
        out[out == self.fill_value] = np.nan
        return out

    # -- ancillary ---------------------------------------------------------- #
    def read_ancillary(self, name: str) -> np.ndarray:
        with h5py.File(self.path, "r") as f:
            a = f[f"{HDF_ROOT}/{name}"][:]
        a = a.astype("float32")
        a[a == FILL] = np.nan
        return a

    def quality_masks(self) -> dict:
        with h5py.File(self.path, "r") as f:
            r = f[HDF_ROOT]
            return {
                "nodata": r["nodata_pixels"][:],
                "cloud": r["beta_cloud_mask"][:],
                "cirrus": r["beta_cirrus_mask"][:],
            }

    def summary(self) -> dict:
        m = self.quality_masks()
        valid = (m["nodata"] == 0) & (m["cloud"] == 0) & (m["cirrus"] == 0)
        bad = ~self.good_wavelengths
        return {
            "scene_id": self.scene_id,
            "shape": [self.n_bands, self.rows, self.cols],
            "epsg": self.epsg,
            "transform": list(self.grid.transform),
            "pixel_size_m": self.grid.pixel_size_m,
            "units": self.units,
            "fill_value": self.fill_value,
            "wavelength_range_nm": [float(self.wavelengths.min()),
                                    float(self.wavelengths.max())],
            "median_spacing_nm": float(np.median(np.diff(self.wavelengths))),
            "fwhm_median_nm": float(np.median(self.fwhm)),
            "n_bands_total": int(self.n_bands),
            "n_bands_good": int(self.good_wavelengths.sum()),
            "n_bands_flagged_bad": int(bad.sum()),
            "bad_band_ranges_nm": _runs_to_ranges(bad, self.wavelengths),
            "valid_fraction": float(valid.mean()),
            "cloud_fraction": float((m["cloud"] != 0).mean()),
            "cirrus_fraction": float((m["cirrus"] != 0).mean()),
            "nodata_fraction": float((m["nodata"] != 0).mean()),
            "created_at": self.created_at,
        }


def _runs_to_ranges(flag: np.ndarray, wl: np.ndarray) -> list:
    """Collapse a boolean band flag into [start_nm, end_nm, count] runs."""
    idx = np.where(flag)[0]
    if len(idx) == 0:
        return []
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i != prev + 1:
            out.append([float(wl[start]), float(wl[prev]), int(prev - start + 1)])
            start = i
        prev = i
    out.append([float(wl[start]), float(wl[prev]), int(prev - start + 1)])
    return out


# --------------------------------------------------------------------------- #
# Satellite 813 sensor simulator
# --------------------------------------------------------------------------- #
@dataclass
class SensorSpec:
    """A target sensor's spectral configuration."""

    name: str
    centres_nm: np.ndarray
    fwhm_nm: np.ndarray
    spatial_resolution_m: float
    source: str = ""

    @property
    def n_bands(self) -> int:
        return len(self.centres_nm)


def spec_813(lo: float = 400.0, hi: float = 1700.0, sampling: float = 5.0,
             n_bands: int = 205, spatial_m: float = 20.0) -> SensorSpec:
    """Published Satellite 813 configuration.

    Source: UAE Space Agency hackathon data page
    (spaceacademy-hackathons.space.gov.ae/data), which states
    "Satellite 813: ~205 bands; ~400-1700 nm; ~5 nm spectral sampling; 20 m".

    400-1700 nm at 5 nm would give 261 slots, but the published band count is
    ~205, so the real instrument does not sample the full range contiguously at
    5 nm. Absent a public band table we lay 205 bands evenly across the stated
    range and keep the stated 5 nm FWHM. This is an explicit, documented
    assumption; see docs/813_PRODUCT_NOTES.md.
    """
    centres = np.linspace(lo, hi, n_bands)
    return SensorSpec(
        name="Satellite 813 (simulated)",
        centres_nm=centres,
        fwhm_nm=np.full(n_bands, sampling),
        spatial_resolution_m=spatial_m,
        source="https://spaceacademy-hackathons.space.gov.ae/data",
    )


def spec_sentinel2() -> SensorSpec:
    """Sentinel-2 MSI bands inside the Tanager range that matter for water.

    Centres and bandwidths follow the ESA Sentinel-2 User Handbook / MSI
    spectral response functions (S2A). B9 (945 nm water vapour) and B10
    (1375 nm cirrus) are excluded: they carry atmosphere, not water-leaving
    signal, and B10 sits inside a Tanager bad-band window anyway.
    """
    #      B1    B2    B3    B4    B5    B6    B7    B8   B8A    B11     B12
    c = [443., 492., 560., 665., 704., 740., 783., 833., 865., 1610., 2190.]
    w = [21.,   66.,  36.,  31.,  15.,  15.,  20., 106.,  21.,   91.,  175.]
    return SensorSpec(
        name="Sentinel-2 MSI (simulated)",
        centres_nm=np.asarray(c), fwhm_nm=np.asarray(w),
        spatial_resolution_m=20.0,
        source="ESA Sentinel-2 User Handbook / MSI Spectral Response Functions",
    )


def gaussian_srf_matrix(src_nm: np.ndarray, spec: SensorSpec,
                        truncate: float = 3.0) -> np.ndarray:
    """Build an (n_target, n_source) spectral response matrix, rows summing to 1.

    Each target band is a Gaussian centred on its centre wavelength with the
    given FWHM, sampled at the source band centres and renormalised. Target
    bands with no source support inside ``truncate`` sigma get an all-zero row.
    """
    sigma = spec.fwhm_nm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    d = spec.centres_nm[:, None] - src_nm[None, :]
    w = np.exp(-0.5 * (d / sigma[:, None]) ** 2)
    w[np.abs(d) > truncate * sigma[:, None]] = 0.0
    s = w.sum(axis=1, keepdims=True)
    ok = s[:, 0] > 0
    w[ok] /= s[ok]
    return w


def resample_spectra(src_nm: np.ndarray, values: np.ndarray, spec: SensorSpec,
                     min_support: float = 0.5):
    """Convolve source spectra onto a target sensor.

    ``values`` is (..., n_source_bands). Returns ``(resampled, supported_mask)``.

    ``min_support`` is the fraction of each target band's Gaussian weight that
    must land on *finite* source bands. Target bands straddling a Tanager
    bad-band gap fall below it and come back as NaN rather than being silently
    interpolated across the gap. That is what keeps the 813 simulation honest
    across the 1342-1438 nm and 1783-1967 nm water-vapour windows.
    """
    W = gaussian_srf_matrix(src_nm, spec)
    v = np.asarray(values, dtype="float64")
    finite = np.isfinite(v)
    vz = np.where(finite, v, 0.0)
    num = vz @ W.T
    support = finite.astype("float64") @ W.T
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / support
    out[support < min_support] = np.nan
    supported = W.sum(axis=1) > 0
    return out.astype("float32"), supported


def simulate_813(scene: TanagerScene, row_step: int = 1, col_step: int = 1,
                 spec: SensorSpec | None = None):
    """Resample a whole Tanager cube onto the 813 band configuration.

    Returns ``(cube_813, spec)`` with ``cube_813`` shaped (n_813, rows, cols).

    Spatial resampling to 813's 20 m is deliberately NOT performed: Tanager is
    30 m, and upsampling 30 m to 20 m would invent spatial detail the source
    never measured. The simulator reproduces 813's SPECTRAL configuration only;
    the spatial difference is stated as a limitation rather than faked.
    """
    spec = spec or spec_813()
    good = np.where(scene.good_wavelengths)[0]
    src_nm = scene.wavelengths[good]
    cube = scene.read_cube(good, row_step, col_step)             # (b, r, c)
    b, r, c = cube.shape
    flat = np.moveaxis(cube, 0, -1).reshape(-1, b)               # (px, b)
    out, _ = resample_spectra(src_nm, flat, spec)
    return np.moveaxis(out.reshape(r, c, spec.n_bands), -1, 0), spec


def save_sensor_spec(spec: SensorSpec, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "name": spec.name,
            "n_bands": spec.n_bands,
            "centres_nm": [round(float(x), 3) for x in spec.centres_nm],
            "fwhm_nm": [round(float(x), 3) for x in spec.fwhm_nm],
            "spatial_resolution_m": spec.spatial_resolution_m,
            "source": spec.source,
        }, f, indent=1)
    return path
