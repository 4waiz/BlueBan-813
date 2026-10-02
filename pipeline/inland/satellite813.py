"""Satellite 813 — inland decision, REVISED (2026-09-19): a pixel-level
EnMAP-to-813 simulator IS now built.

--------------------------------------------------------------------------
ORIGINAL DECISION (superseded, kept below for the record) and WHY IT
CHANGED
--------------------------------------------------------------------------
This module originally declined to build a per-band Gaussian-SRF simulator
because doing so would have required stacking TWO independently assumed
wavelength grids: EnMAP's (not known — neither acquired GeoTIFF carried
per-band metadata at the time) laid evenly across its published 420-2450 nm
range, AND 813's own published configuration (`spec_813()`, already an
explicit assumption per DesalGuard-main's own note). DesalGuard-main's own
`simulate_813()` only ever assumes ONE grid (813's) because its OTHER axis
(Tanager's) is real, read directly from the source file's own calibration
attributes. Stacking two guesses here would have produced a cube of
per-813-band numbers indistinguishable in form from a real simulation while
being built from two guesses — "fabricated detail presented as real,"
which this project's honesty standard rules out. So the decision was:
build `enmap_813_coverage_comparison()` (below, unchanged, still useful)
instead of a per-band resampler.

That reasoning explicitly named its own reversal condition (see the
now-superseded text this replaces, and `docs/SATELLITE_813_DECISION.md`
section 3): "if the per-band wavelength table is obtained later... a
faithful Gaussian-SRF simulator becomes buildable with the same
one-assumption standard as DesalGuard's own." That condition is now met —
`data/metadata/enmap_band_characterisation.json` holds this project's own
independently cross-validated (see that file's own `source.cross_validation`
field) real per-band centre-wavelength/FWHM table for all 224 EnMAP bands,
pulled from the DLR STAC catalog's own `eo:bands` metadata (not assumed,
not evenly-spaced-guessed). EnMAP's axis is now exactly as real as
Tanager's was for DesalGuard — read from the source product's own metadata,
not laid out evenly by this project. 813's own grid remains the ONE
explicit, documented assumption (`spec_813()`, unchanged, copied verbatim),
which is exactly DesalGuard's own situation, not a weaker one.

--------------------------------------------------------------------------
THE REVISED DECISION: `simulate_813_enmap()` below, a real per-band
Gaussian-SRF resample of EnMAP onto 813's published configuration
--------------------------------------------------------------------------
`gaussian_srf_matrix()` and `resample_spectra()` are copied UNMODIFIED from
DesalGuard-main/pipeline/satellite813.py — this is general cross-sensor
band-synthesis machinery (the standard Gaussian spectral-response-function
convolution used for sensor intercomparison in ISOFIT/HyTools), not
coastal-tuned business logic, so there is nothing AOI-specific to
re-derive. `min_support=0.5` is likewise a general engineering default (how
much of a target band's Gaussian weight must land on finite source data
before the resampled value is trusted vs. marked NaN), not a value fit to
any AOI's data population — the same category as DesalGuard's own
`truncate=3.0 sigma` Gaussian window default. It is reused at DesalGuard's
own value, not re-derived, because it is a structural resampling-honesty
knob, not a detection threshold.

`enmap_813_coverage_comparison()` (below, unchanged) remains useful as the
coarse, whole-range-average companion view; it is not removed or
superseded, just no longer the ONLY available comparison.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SensorSpec:
    """A target sensor's spectral configuration. Same shape as
    DesalGuard-main's dataclass of the same name."""
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
    """Published Satellite 813 configuration. COPIED UNMODIFIED from
    DesalGuard-main/pipeline/satellite813.py (not imported from that
    repository at runtime — copied, the same pattern as
    pipeline/provenance.py, because this project does not depend on
    DesalGuard-main's tree). This function is general sensor-configuration
    data with no coastal-specific tuning in it, so there is nothing to
    adapt for the inland case.

    Source: UAE Space Agency hackathon data page
    (spaceacademy-hackathons.space.gov.ae/data), which states
    "Satellite 813: ~205 bands; ~400-1700 nm; ~5 nm spectral sampling; 20 m".

    400-1700 nm at 5 nm would give 261 slots, but the published band count
    is ~205, so the real instrument does not sample the full range
    contiguously at 5 nm. Absent a public band table we lay 205 bands
    evenly across the stated range and keep the stated 5 nm FWHM. This is
    an explicit, documented assumption (DesalGuard-main's own note,
    reproduced here verbatim because it still applies unchanged).
    """
    centres = np.linspace(lo, hi, n_bands)
    return SensorSpec(
        name="Satellite 813 (published config, simulated band layout)",
        centres_nm=centres,
        fwhm_nm=np.full(n_bands, sampling),
        spatial_resolution_m=spatial_m,
        source="https://spaceacademy-hackathons.space.gov.ae/data",
    )


@dataclass
class EnMAPCoverage:
    """This project's own EnMAP coverage facts — every field here is a
    value already verified elsewhere (see `source`), NOT a new assumption
    introduced by this module."""
    n_bands_total: int
    n_bands_valid_this_aoi: int   # after dropping nodata-carrying bands
    wavelength_range_nm: tuple    # (lo, hi), published INSTRUMENT range
    spatial_resolution_m: float
    source: str


def enmap_coverage_from_project(n_bands_valid: int = 218) -> EnMAPCoverage:
    """Build an EnMAPCoverage from the values already verified and cited in
    config/project.yaml / docs/DATA_ACCESS_AUDIT.md — not re-derived here.

    ``n_bands_valid`` defaults to 218 (224 total minus the 6-band nodata gap
    found in the 2022-09-08 scene, docs/WATER_MASK.md section 4); the
    2024-04-24 scene drops 5, an observed, unreconciled difference — see
    that same section. Pass the actual count for a specific scene if it
    matters for the comparison being made.
    """
    return EnMAPCoverage(
        n_bands_total=224,
        n_bands_valid_this_aoi=n_bands_valid,
        wavelength_range_nm=(420.0, 2450.0),
        spatial_resolution_m=30.0,
        source=(
            "config/project.yaml enmap.spec (DLR EnMAP_Specs.pdf for range/"
            "resolution; direct GeoTIFF band-count check for n_bands_total; "
            "docs/WATER_MASK.md section 4 for the per-scene valid-band count)"
        ),
    )


def enmap_813_coverage_comparison(enmap: EnMAPCoverage, spec813: SensorSpec) -> dict:
    """Coarse spectral-configuration comparison between this project's EnMAP
    scenes and 813's published configuration.

    Deliberately NOT a per-band resampling — see module docstring for why.
    Every number here is either a directly-verified input or a SCENE-AVERAGE
    arithmetic derived from directly-verified inputs (total range / total
    band count), never a per-band value. `enmap_avg_band_spacing_nm` in
    particular is explicitly an average across the WHOLE 420-2450 nm range,
    not a claim that EnMAP's bands are evenly spaced — it answers "roughly
    how dense is EnMAP's sampling compared to 813's," nothing finer.
    """
    e_lo, e_hi = enmap.wavelength_range_nm
    s_lo, s_hi = float(spec813.centres_nm.min()), float(spec813.centres_nm.max())

    overlap_lo, overlap_hi = max(e_lo, s_lo), min(e_hi, s_hi)
    overlap_nm = max(0.0, overlap_hi - overlap_lo)

    enmap_range_nm = e_hi - e_lo
    enmap_avg_spacing_nm = enmap_range_nm / max(enmap.n_bands_valid_this_aoi - 1, 1)

    s813_range_nm = s_hi - s_lo
    s813_avg_spacing_nm = s813_range_nm / max(spec813.n_bands - 1, 1)

    return {
        "enmap_wavelength_range_nm": [e_lo, e_hi],
        "spec813_wavelength_range_nm": [s_lo, s_hi],
        "overlap_range_nm": [overlap_lo, overlap_hi] if overlap_nm > 0 else None,
        "overlap_width_nm": overlap_nm,
        "enmap_n_bands_valid_this_aoi": enmap.n_bands_valid_this_aoi,
        "enmap_avg_band_spacing_nm": round(enmap_avg_spacing_nm, 3),
        "spec813_n_bands": spec813.n_bands,
        "spec813_avg_band_spacing_nm": round(s813_avg_spacing_nm, 3),
        "spatial_resolution_ratio_enmap_over_813": round(
            enmap.spatial_resolution_m / spec813.spatial_resolution_m, 3
        ),
        "note": (
            "Coverage/configuration comparison only -- NOT a per-band or "
            "per-pixel spectral simulation. EnMAP's spectral range fully "
            "contains 813's published range (420-2450 nm vs 400-1700 nm, "
            "overlapping at 420-1700 nm). On a whole-range-AVERAGE basis "
            f"(not a per-band claim), EnMAP's {enmap.n_bands_valid_this_aoi} "
            f"valid bands across its much wider 2030 nm range average "
            f"~{round(enmap_avg_spacing_nm, 1)} nm/band, coarser than 813's "
            f"published config averaging ~{round(s813_avg_spacing_nm, 1)} "
            "nm/band across its narrower 1300 nm range -- i.e. 813's "
            "published configuration is the denser one on this whole-range "
            "average, not EnMAP; EnMAP's own per-band resolution within its "
            "VNIR portion is likely finer than this whole-range average "
            "suggests (nominal 6.5 nm VNIR / 10 nm SWIR per "
            "config/project.yaml), but that per-band detail cannot be "
            "placed without the still-missing wavelength table, so it is "
            "not claimed here. EnMAP is spatially coarser (30 m vs 813's "
            "20 m) -- the direction DesalGuard-main's own simulator also "
            "does not correct for (it states outright that upsampling "
            "Tanager's 30 m to 813's 20 m 'would invent spatial detail the "
            "source never measured' and declines to do it -- same "
            "reasoning applies here)."
        ),
        "decision": (
            "This coarse comparison is retained alongside, not instead of, "
            "a real per-band simulator: as of 2026-09-19 "
            "data/metadata/enmap_band_characterisation.json provides "
            "EnMAP's real per-band wavelength grid (pulled from DLR's own "
            "STAC eo:bands metadata, cross-validated -- see that file's "
            "source.cross_validation field), so simulate_813_enmap() below "
            "performs the real Gaussian-SRF resample onto 813's published "
            "(still assumed, per spec_813()) configuration. See "
            "pipeline/satellite813.py module docstring and "
            "docs/SATELLITE_813_DECISION.md for the full reasoning behind "
            "this reversal from the original inland_simulator_built=false "
            "decision."
        ),
    }


# --------------------------------------------------------------------------- #
# Real per-band simulator (added 2026-09-19, once EnMAP's real wavelength
# grid became available) -- copied UNMODIFIED from DesalGuard-main's own
# gaussian_srf_matrix() / resample_spectra(), general cross-sensor
# resampling machinery, not coastal-specific.
# --------------------------------------------------------------------------- #
def gaussian_srf_matrix(src_nm: np.ndarray, spec: SensorSpec,
                        truncate: float = 3.0) -> np.ndarray:
    """Build an (n_target, n_source) spectral response matrix, rows summing to 1.

    Each target band is a Gaussian centred on its centre wavelength with the
    given FWHM, sampled at the source band centres and renormalised. Target
    bands with no source support inside ``truncate`` sigma get an all-zero
    row. Copied verbatim from DesalGuard-main/pipeline/satellite813.py --
    general Gaussian spectral-response-function convolution, no
    coastal-specific values."""
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

    ``min_support`` is the fraction of each target band's Gaussian weight
    that must land on *finite* source bands. Target 813 bands whose Gaussian
    weight straddles one of EnMAP's own nodata gaps (the water-vapor
    absorption windows documented in docs/WATER_MASK.md section 12 -- real,
    not assumed, gaps in the source data used here) fall below it and come
    back as NaN rather than being silently interpolated across the gap.
    Copied verbatim from DesalGuard-main (there it protects the same
    property across Tanager's own bad-band windows)."""
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


def enmap_wavelengths_from_band_table(bands: list) -> np.ndarray:
    """Real EnMAP per-band centre wavelengths (nm), in cube band order, from
    the same table pipeline/water_mask.py's real_mndwi() and
    pipeline/fingerprint.py's CYANO_LIKE use -- one shared source of truth
    for "what is EnMAP band i's real wavelength," not a value re-derived or
    re-assumed per module."""
    return np.array([b["center_wavelength_nm"] for b in bands])


def simulate_813_enmap(cube: np.ndarray, nodata: float, bands: list,
                       spec: SensorSpec | None = None,
                       scale: float = 1.0 / 10000.0, min_support: float = 0.5):
    """Resample an EnMAP (bands, rows, cols) reflectance cube onto 813's
    published band configuration, using EnMAP's REAL per-band wavelength
    grid as the source axis (not an evenly-spaced guess -- see module
    docstring for why this is now possible where it previously was not).

    813's own grid (``spec``, default ``spec_813()``) remains the one
    explicit, documented assumption -- same as DesalGuard-main's own
    simulate_813() for Tanager. No spatial resampling is attempted (EnMAP's
    30 m is coarser than 813's 20 m; upsampling would invent spatial detail
    the source never measured, the same position DesalGuard-main's own
    simulator takes and states outright).

    Per-band nodata (EnMAP's real water-vapor-absorption gaps, NOT a
    per-pixel data-quality issue -- see docs/WATER_MASK.md section 12) is
    converted to NaN before resampling, so resample_spectra()'s min_support
    gating decides -- per 813 target band, per pixel -- whether enough real
    EnMAP support exists near that 813 band's centre, rather than a whole
    pixel being dropped because of a gap band unrelated to that particular
    813 band.

    Returns ``(cube_813, spec, supported_mask, source_wavelengths_nm)``:
    ``cube_813`` is (spec.n_bands, rows, cols) with NaN where min_support
    was not met; ``supported_mask`` (spec.n_bands,) is True where the 813
    band's Gaussian window has ANY EnMAP source support at all (independent
    of any particular pixel's nodata); ``source_wavelengths_nm`` is the real
    EnMAP wavelength array used, for provenance.
    """
    spec = spec or spec_813()
    src_nm = enmap_wavelengths_from_band_table(bands)
    if cube.shape[0] != len(src_nm):
        raise ValueError(
            f"cube has {cube.shape[0]} bands but the band table has "
            f"{len(src_nm)} -- these must be the same EnMAP product's cube "
            "and its own band table, in the same band order.")
    b, r, c = cube.shape
    flat = cube.astype("float64")
    flat = np.where(flat == nodata, np.nan, flat) * scale
    flat = np.moveaxis(flat, 0, -1).reshape(-1, b)                 # (px, b)
    out, supported = resample_spectra(src_nm, flat, spec, min_support=min_support)
    cube_813 = np.moveaxis(out.reshape(r, c, spec.n_bands), -1, 0)
    return cube_813, spec, supported, src_nm
