"""Water masking for the inland AOI (Shawka Dam) — EnMAP hyperspectral.

This is NOT a port of DesalGuard-main's `pipeline/water_mask.py`. That module's
thresholds (mndwi_threshold=0.15, nir_max=0.10, min_component_px=50,
shoreline_buffer_px=2) are tuned for a large, developed coastline observed with
Tanager's 30 m bands at known wavelengths, and were explicitly forbidden from
being carried forward as working values here (project owner instruction,
2026-09-18): a ~1.2 ha wet core at Shawka Dam is smaller than DesalGuard's own
`min_component_px` speckle filter, and its own `shoreline_buffer_px=2` erosion
would very likely erase the entire signal. Only the *interface shape* —
a small dataclass result, connected-component filtering, an optional erosion
buffer, and a stats dict — is carried over, for the same reason
`pipeline/provenance.py` was carried over unmodified: so folding this into
DesalGuard-main later is a copy-and-namespace operation, not a rewrite.

Why band GROUPS instead of MNDWI (green vs SWIR1) / NDWI (green vs NIR):
the two EnMAP L2A GeoTIFFs in hand carry no per-band wavelength metadata at
all (verified directly against the file's own TIFF tags — see
docs/DATA_ACCESS_AUDIT.md section 2.1a). The product's own METADATA.XML does
carry a `specific/bandCharacterisation` structure with exact per-band center
wavelength and FWHM (confirmed via EnMAP's own FAQ), but the copy pasted into
this project's chat history was truncated before reaching that section, and
the file itself was not saved locally, so it is not available to build from
yet (flagged as an open item, not a blocker for a v1 mask). Until that table
is in hand, band selection here relies only on the one thing that does not
require it: EnMAP bands are stored in increasing-wavelength order (standard
convention for imaging-spectrometer cubes; indirectly supported here by the
AOI's own mean spectrum rising from ~0.09 at band 1 through a NIR-region peak
around bands 90-160 and falling into the SWIR tail — the physically expected
shape for bare soil/rock, not an arbitrary band ordering). Splitting the
*valid* band sequence into three equal-count groups (short/mid/long, a crude
VNIR-visible / VNIR-NIR / SWIR proxy) and using GROUP MEANS rather than a
single narrow band also makes the result less sensitive to exactly where the
true VNIR/SWIR boundary falls.

This module and its threshold constants apply to the Shawka Dam AOI only, as
derived in scripts/derive_water_mask.py against the 2022-09-08 EnMAP scene's
own pixel histogram (see docs/WATER_MASK.md for the full derivation and
validation against the reused Sentinel-2/Landsat NDWI baseline). They are not
a general-purpose inland water-masking recipe.

UPDATE (2026-09-19): `water_mask()`'s second criterion (`short_long_index`,
a single-date spectral-shape test) was found not to generalize to a second
acquisition date — see docs/WATER_MASK.md section 9. `water_mask()` is kept
as-is, both as the historical single-date v1 record and because it remains
valid for single-scene work; it is just no longer the recommended tool for
anything that needs to hold across dates. `persistent_wet_core()`, added
below, is a genuinely two-date-derived replacement built and validated on
BOTH acquired scenes together — see its docstring and
docs/WATER_MASK.md section 12.

UPDATE (2026-09-19, later same day): the per-band wavelength/FWHM gap this
module's original docstring (above) describes is now RESOLVED — a real
per-band table was obtained from the EnMAP scenes' own STAC item metadata
(`eo:bands`, cross-validated across both scenes; see
`data/metadata/enmap_band_characterisation.json` and
`docs/WATER_MASK.md` section 13). `real_mndwi()` and
`persistent_wet_core_mndwi()`, added below, use two REAL named bands
(nearest to 560 nm / 1610 nm) instead of the band-GROUPS proxy, and are
compared directly against `persistent_wet_core()`'s group-based result in
docs/WATER_MASK.md section 13. Both functions are kept — the group-based
one as the already-validated, already-documented tool; the real-band one
as the now-possible, more standard-form index — with the comparison
stated plainly rather than one silently replacing the other.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:                                            # optional, used when available
    from scipy import ndimage as _ndi
except Exception:                               # pragma: no cover
    _ndi = None


# Derived against the 2022-09-08 EnMAP scene, Shawka Dam AOI window (84 valid
# pixels inside the locked polygon). See docs/WATER_MASK.md for how these were
# chosen — NOT copied from DesalGuard-main's coastal defaults.
#
# STATUS (2026-09-19): short_long_index_min was found NOT to generalize to a
# second date (docs/WATER_MASK.md section 9 — it flips sign at the same
# physical wet-core location between 2022-09-08 and 2024-04-24). It is kept
# here, unchanged, as the historical single-date v1 record and because
# water_mask() itself is still a valid single-scene tool. For anything that
# needs to hold across dates, use persistent_wet_core() below instead, which
# was derived and validated jointly from both dates (docs/WATER_MASK.md
# section 12).
DEFAULT_BRIGHTNESS_MAX = 0.11
DEFAULT_SHORT_LONG_INDEX_MIN = 0.0
DEFAULT_MIN_COMPONENT_PX = 3        # not 50 — the whole AOI window is 84 px
DEFAULT_BUFFER_PX = 0               # not 2 — an erosion buffer this AOI's
                                     # size would likely erase the entire core

# Derived jointly from the 2022-09-08 AND 2024-04-24 scenes together (both on
# the verified-identical pixel grid — docs/WATER_MASK.md section 8). See
# persistent_wet_core() below and docs/WATER_MASK.md section 12 for the full
# threshold sweep and validation that motivate this value.
DEFAULT_DARKNESS_MAX = 0.10


@dataclass
class BandGroups:
    """Three broad, index-based proxies for VNIR-visible / VNIR-NIR / SWIR.

    Built by splitting the *valid* (non-nodata-anywhere) band sequence into
    three equal-count contiguous groups, in band order. Not a substitute for
    true wavelength-labeled bands — see module docstring.
    """
    short: np.ndarray   # group-mean reflectance, shortest-wavelength third
    mid: np.ndarray      # group-mean reflectance, middle third
    long: np.ndarray      # group-mean reflectance, longest-wavelength third
    good_band_idx: np.ndarray   # indices (into the original band axis) used
    bad_band_idx: np.ndarray    # indices dropped for carrying nodata anywhere
    split_points: tuple[int, int]  # (t1, t2) group boundaries within good bands


def find_bad_bands(cube: np.ndarray, nodata: float) -> np.ndarray:
    """Bands (axis 0) that carry `nodata` anywhere in `cube`.

    On the 2022-09-08 scene's AOI window this found exactly one 6-band block
    (bands 130-135, 1-indexed) uniformly nodata across all 750 sampled pixels
    — not obviously either of the two strong-water-vapour-absorption windows
    EnMAP's own Land_Mode processing note describes as always excluded
    (1331.0-1460.0 nm and 1796.0-1938.0 nm); this is recorded as an observed,
    not fully reconciled, fact rather than assumed to be one or the other.
    """
    return np.where((cube == nodata).any(axis=(1, 2)))[0]


def band_groups(cube: np.ndarray, nodata: float, scale: float = 1.0 / 10000.0) -> BandGroups:
    """Reflectance band-group means, after dropping bands with any nodata.

    `scale` converts stored int16 DN to reflectance (0-1); EnMAP L2A carries
    no per-band scale/offset tag on either acquired GeoTIFF (checked directly:
    rasterio reports scale=1.0, offset=0.0 on every band), so the 1/10000
    factor is taken from EnMAP-Box's own import documentation ("data is
    scaled into the 0 to 10000 range"), not assumed from a generic convention.
    """
    bad = find_bad_bands(cube, nodata)
    n_bands = cube.shape[0]
    good = np.array([b for b in range(n_bands) if b not in bad])
    refl = cube[good].astype(np.float64) * scale

    n = len(good)
    t1, t2 = n // 3, 2 * n // 3
    return BandGroups(
        short=refl[:t1].mean(axis=0),
        mid=refl[t1:t2].mean(axis=0),
        long=refl[t2:].mean(axis=0),
        good_band_idx=good,
        bad_band_idx=bad,
        split_points=(t1, t2),
    )


@dataclass
class WaterMaskResult:
    mask: np.ndarray                # True = candidate water/wet-core pixel
    raw_mask: np.ndarray            # before component filtering
    brightness: np.ndarray          # mean reflectance across all valid bands
    short_long_index: np.ndarray    # (short-long)/(short+long) broad-group index
    min_component_px: int
    buffer_px: int
    stats: dict = field(default_factory=dict)


def water_mask(cube: np.ndarray, nodata: float,
                brightness_max: float = DEFAULT_BRIGHTNESS_MAX,
                short_long_index_min: float = DEFAULT_SHORT_LONG_INDEX_MIN,
                min_component_px: int = DEFAULT_MIN_COMPONENT_PX,
                buffer_px: int = DEFAULT_BUFFER_PX) -> WaterMaskResult:
    """Candidate water/wet-core mask for an EnMAP reflectance cube window.

    `cube` is (bands, rows, cols) raw DN (int16) as stored in the L2A GeoTIFF,
    already windowed to (at least) the AOI. Two criteria, both required:

    1. brightness (mean reflectance across all valid bands) < brightness_max
       — water is dark broadband; DesalGuard's NIR-darkness test analog.
    2. short_long_index (visible-proxy minus SWIR-proxy, normalized) >
       short_long_index_min — water absorbs SWIR far more strongly than
       visible light; bare soil/rock at this AOI does not (see
       docs/WATER_MASK.md for the measured group means that motivate this).

    On the 2022-09-08 scene, criterion 1 alone already produced a mask with
    zero pixels outside the locked AOI polygon in the sampled window — stated
    here, not assumed, because it is worth knowing whether criterion 2 is
    load-bearing for false-positive rejection at this AOI or mostly
    redundant; docs/WATER_MASK.md records that check.
    """
    groups = band_groups(cube, nodata)
    brightness = (cube[groups.good_band_idx].astype(np.float64) / 10000.0).mean(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        short_long_index = (groups.short - groups.long) / (groups.short + groups.long + 1e-9)

    raw = (
        np.isfinite(brightness) & (brightness < brightness_max)
        & np.isfinite(short_long_index) & (short_long_index > short_long_index_min)
    )

    filtered = _label_and_filter(raw, min_component_px)
    final = _erode(filtered, buffer_px) if buffer_px > 0 else filtered

    stats = {
        "brightness_max": brightness_max,
        "short_long_index_min": short_long_index_min,
        "min_component_px": min_component_px,
        "buffer_px": buffer_px,
        "scipy_available": _ndi is not None,
        "bad_bands_dropped": groups.bad_band_idx.tolist(),
        "px_water_raw": int(raw.sum()),
        "px_water_after_components": int(filtered.sum()),
        "px_water_final": int(final.sum()),
    }
    return WaterMaskResult(mask=final, raw_mask=raw, brightness=brightness,
                           short_long_index=short_long_index,
                           min_component_px=min_component_px, buffer_px=buffer_px,
                           stats=stats)


# --------------------------------------------------------------------------- #
# Two-date-derived criterion: persistent broadband darkness
# --------------------------------------------------------------------------- #
def brightness(cube: np.ndarray, nodata: float,
                scale: float = 1.0 / 10000.0) -> tuple[np.ndarray, np.ndarray]:
    """Mean reflectance across all valid (non-nodata-anywhere) bands.

    Factored out of water_mask() so persistent_wet_core() can compute
    per-date brightness without also computing the short/long band groups
    that only the (now-superseded-for-cross-date-use) short_long_index
    criterion needs. Same bad-band handling and 1/10000 scale as
    band_groups() — see that function's docstring for sourcing.

    Returns ``(brightness_array, bad_band_idx)``.
    """
    bad = find_bad_bands(cube, nodata)
    n_bands = cube.shape[0]
    good = np.array([b for b in range(n_bands) if b not in bad])
    refl = cube[good].astype(np.float64) * scale
    return refl.mean(axis=0), bad


@dataclass
class DateBrightness:
    """One date's contribution to a persistent_wet_core() run."""
    date_label: str
    brightness: np.ndarray
    bad_band_idx: np.ndarray


@dataclass
class PersistentWetCoreResult:
    mask: np.ndarray                # True = candidate persistent wet-core pixel
    raw_mask: np.ndarray            # before component filtering
    joint_darkness: np.ndarray      # max brightness across ALL input dates
    per_date: list                  # list[DateBrightness]
    darkness_max: float
    min_component_px: int
    buffer_px: int
    stats: dict = field(default_factory=dict)


def persistent_wet_core(cubes: list, nodatas: list,
                         date_labels: list | None = None,
                         darkness_max: float = DEFAULT_DARKNESS_MAX,
                         min_component_px: int = DEFAULT_MIN_COMPONENT_PX,
                         buffer_px: int = DEFAULT_BUFFER_PX) -> PersistentWetCoreResult:
    """Water mask from TEMPORAL PERSISTENCE of broadband darkness, derived
    and validated jointly across every date passed in — the redesign
    requested after short_long_index_min was found not to transfer between
    dates (docs/WATER_MASK.md section 9).

    Why this replaces short_long_index_min for cross-date use
    -----------------------------------------------------------
    At the exact physical location of the 2022-09-08 wet core,
    short_long_index — a spectral-SHAPE criterion fit to that one date's
    histogram — flips from its threshold's positive side to strongly
    negative (-0.15 to -0.33) in 2024-04-24, even though broadband
    darkness at that same location stayed stable and low in both dates.
    That is a real generalization failure of a single-date shape
    criterion, confirmed against the raw mask arrays (not assumed to be
    noise). Broadband darkness itself is what held up across dates, so
    this function makes that the criterion directly, instead of layering
    a shape test on top of it: a pixel qualifies only if it is dark
    (mean reflectance below ``darkness_max``) in EVERY date supplied.

    Validation
    ----------
    Swept darkness_max from 0.078 to 0.13 against both acquired scenes on
    their verified-identical pixel grid (docs/WATER_MASK.md section 8;
    reproduced by scripts/derive_persistent_wet_core.py). Across that
    entire range: a single connected component, and zero candidate pixels
    outside the locked AOI polygon in either date — i.e. no leakage at any
    threshold tested, unlike short_long_index_min, whose failure was a
    location-specific sign flip rather than a magnitude problem that a
    different cutoff could fix. ``darkness_max=0.10`` (the default) sits
    just past a natural gap in the sorted joint-darkness distribution and
    gives a clean 10-pixel single component at the same physical location
    (rows 7-10, cols 13-15 of the shared grid) as the original
    2022-09-08-only result. Full numbers in docs/WATER_MASK.md section 12.

    Parameters
    ----------
    cubes
        List of (bands, rows, cols) raw DN cubes, one per date, already
        windowed/cropped to an IDENTICAL real-world pixel grid (same
        affine transform — this function does NOT itself verify spatial
        alignment, only that array shapes match; see
        docs/WATER_MASK.md section 8 for how the 2022/2024 grids used
        here were confirmed identical before comparing them).
    nodatas
        Per-cube nodata value, same length as ``cubes``.
    date_labels
        Optional labels for ``stats``/``per_date`` (defaults to
        positional indices as strings).

    Requires at least 2 dates. With only one date this criterion
    degenerates to a plain single-date brightness threshold — exactly the
    single-date-fitting failure mode this function exists to avoid, so it
    is refused rather than silently computed.
    """
    if len(cubes) < 2:
        raise ValueError(
            "persistent_wet_core() requires at least 2 dates: with one date "
            "this is just a single-date brightness threshold, i.e. the same "
            "kind of single-date fitting that made short_long_index_min not "
            "generalize (see docstring and docs/WATER_MASK.md section 9)."
        )
    if len(cubes) != len(nodatas):
        raise ValueError("cubes and nodatas must be the same length")
    shapes = {c.shape[1:] for c in cubes}
    if len(shapes) != 1:
        raise ValueError(
            f"All cubes must share the same (rows, cols) grid; got {shapes}. "
            "persistent_wet_core() checks array shape only, not real-world "
            "alignment — see docs/WATER_MASK.md section 8."
        )

    labels = date_labels or [str(i) for i in range(len(cubes))]
    per_date: list[DateBrightness] = []
    brightness_stack = []
    for cube, nodata, label in zip(cubes, nodatas, labels):
        b, bad = brightness(cube, nodata)
        per_date.append(DateBrightness(date_label=label, brightness=b, bad_band_idx=bad))
        brightness_stack.append(b)

    joint_darkness = np.maximum.reduce(brightness_stack)
    raw = np.isfinite(joint_darkness) & (joint_darkness < darkness_max)

    filtered = _label_and_filter(raw, min_component_px)
    final = _erode(filtered, buffer_px) if buffer_px > 0 else filtered

    stats = {
        "darkness_max": darkness_max,
        "min_component_px": min_component_px,
        "buffer_px": buffer_px,
        "n_dates": len(cubes),
        "date_labels": labels,
        "bad_bands_dropped_per_date": {
            dbr.date_label: dbr.bad_band_idx.tolist() for dbr in per_date
        },
        "scipy_available": _ndi is not None,
        "px_water_raw": int(raw.sum()),
        "px_water_after_components": int(filtered.sum()),
        "px_water_final": int(final.sum()),
        "criterion": (
            "max(brightness across all supplied dates) < darkness_max -- "
            "temporal persistence of broadband darkness, not a single-date "
            "spectral-shape index. See docs/WATER_MASK.md section 12."
        ),
    }
    return PersistentWetCoreResult(
        mask=final, raw_mask=raw, joint_darkness=joint_darkness,
        per_date=per_date, darkness_max=darkness_max,
        min_component_px=min_component_px, buffer_px=buffer_px, stats=stats,
    )


# --------------------------------------------------------------------------- #
# Real-band MNDWI-style index — now possible with the per-band wavelength
# table obtained 2026-09-19 (data/metadata/enmap_band_characterisation.json).
# See docs/WATER_MASK.md section 13 for the full derivation, the direct
# comparison against persistent_wet_core()'s band-GROUPS result, and how the
# wavelength table itself was verified (WebFetch against the EnMAP STAC
# item's own eo:bands field, cross-validated bit-for-bit across both
# acquired scenes).
# --------------------------------------------------------------------------- #
def load_band_characterisation(path: str) -> list:
    """Load data/metadata/enmap_band_characterisation.json and return its
    ``bands`` list (each entry: index_1based, name, center_wavelength_nm,
    fwhm_nm). Raises if the file's own internal consistency checks
    (224 bands, sequential indices) don't hold -- this table backs a real
    scientific claim (named-wavelength band selection) and should fail
    loudly rather than silently if it's ever swapped for something bad.
    """
    import json
    with open(path) as f:
        d = json.load(f)
    bands = d["bands"]
    if len(bands) != d.get("n_bands", len(bands)):
        raise ValueError(f"{path}: declared n_bands does not match len(bands)")
    idx = [b["index_1based"] for b in bands]
    if idx != list(range(1, len(bands) + 1)):
        raise ValueError(f"{path}: band indices are not a sequential 1..N range")
    return bands


def nearest_band_index_0based(bands: list, target_nm: float) -> tuple:
    """Nearest band (by center wavelength) to ``target_nm``.

    Returns ``(index_0based, band_entry, abs_offset_nm)`` -- the offset is
    always reported, never silently dropped, so a caller (or a doc) can
    state exactly how far the real band sits from the textbook target
    wavelength rather than implying an exact match that may not exist.
    """
    best = min(bands, key=lambda b: abs(b["center_wavelength_nm"] - target_nm))
    return best["index_1based"] - 1, best, abs(best["center_wavelength_nm"] - target_nm)


@dataclass
class RealMNDWIResult:
    mndwi: np.ndarray            # (rows, cols)
    green_band_idx_0based: int
    swir1_band_idx_0based: int
    green_wavelength_nm: float
    swir1_wavelength_nm: float
    green_offset_nm: float       # |actual - requested target|
    swir1_offset_nm: float


def real_mndwi(cube: np.ndarray, nodata: float, bands: list,
               green_nm: float = 560.0, swir1_nm: float = 1610.0,
               scale: float = 1.0 / 10000.0) -> RealMNDWIResult:
    """Modified NDWI (Xu 2006: (Green - SWIR1) / (Green + SWIR1)) using the
    two REAL EnMAP bands nearest the standard Green (~560 nm) and SWIR1
    (~1610 nm) reference wavelengths -- not a band-GROUP proxy.

    Defaults (560 nm, 1610 nm) follow the widely-used Landsat TM/Sentinel-2
    MNDWI band convention (Xu 2006's own Green/MIR pairing; 1610 nm matches
    Sentinel-2 B11 / Landsat TM Band 5 almost exactly). These are the
    STANDARD reference wavelengths for this index, not a value tuned to
    this AOI -- see docs/WATER_MASK.md section 13 for how close EnMAP's
    real nearest bands land to them (B030 / B150, both within ~1 nm) and
    why no further tuning of the wavelength choice was done.

    A single nodata-affected pixel (per find_bad_bands()) in EITHER
    selected band would silently corrupt this index, so both bands are
    checked and any pixel where either band equals ``nodata`` is set NaN.
    """
    green_idx, green_band, green_off = nearest_band_index_0based(bands, green_nm)
    swir1_idx, swir1_band, swir1_off = nearest_band_index_0based(bands, swir1_nm)

    if cube.shape[0] != len(bands):
        raise ValueError(
            f"cube has {cube.shape[0]} bands but the wavelength table has "
            f"{len(bands)} -- these must be the same product/band count to "
            "trust the index-to-wavelength correspondence."
        )

    green = cube[green_idx].astype(np.float64)
    swir1 = cube[swir1_idx].astype(np.float64)
    bad = (green == nodata) | (swir1 == nodata)

    g = green * scale
    s = swir1 * scale
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = (g - s) / (g + s + 1e-9)
    mndwi = np.where(bad, np.nan, mndwi)

    return RealMNDWIResult(
        mndwi=mndwi, green_band_idx_0based=green_idx, swir1_band_idx_0based=swir1_idx,
        green_wavelength_nm=green_band["center_wavelength_nm"],
        swir1_wavelength_nm=swir1_band["center_wavelength_nm"],
        green_offset_nm=green_off, swir1_offset_nm=swir1_off,
    )


@dataclass
class PersistentWetCoreMNDWIResult:
    mask: np.ndarray
    raw_mask: np.ndarray
    joint_mndwi_min: np.ndarray     # MIN mndwi across all supplied dates (water needs high MNDWI in every date)
    per_date_mndwi: list            # list[RealMNDWIResult]
    mndwi_min: float
    min_component_px: int
    buffer_px: int
    stats: dict = field(default_factory=dict)


def persistent_wet_core_mndwi(cubes: list, nodatas: list, bands: list,
                              date_labels: list | None = None,
                              green_nm: float = 560.0, swir1_nm: float = 1610.0,
                              mndwi_min: float = 0.0,
                              min_component_px: int = DEFAULT_MIN_COMPONENT_PX,
                              buffer_px: int = DEFAULT_BUFFER_PX) -> PersistentWetCoreMNDWIResult:
    """Same two-date PERSISTENCE structure as persistent_wet_core() (a pixel
    must qualify in EVERY supplied date), but the per-date criterion is a
    real-band MNDWI threshold (mndwi > mndwi_min) instead of broadband
    darkness from band GROUPS.

    ``mndwi_min=0.0`` is Xu (2006)'s own standard MNDWI water/non-water
    threshold -- a literature convention, not fit to this AOI. See
    docs/WATER_MASK.md section 13 for a threshold sweep run against this
    AOI's own MNDWI distribution (the same validation style used for
    persistent_wet_core()'s darkness_max) and for the direct comparison of
    this function's result against persistent_wet_core()'s.

    Parameters mirror persistent_wet_core() otherwise -- see that
    function's docstring for the shape/alignment preconditions (same
    (rows, cols) grid required for every cube, checked here too).
    """
    if len(cubes) < 2:
        raise ValueError(
            "persistent_wet_core_mndwi() requires at least 2 dates -- see "
            "persistent_wet_core()'s docstring for why a single-date "
            "criterion is exactly the failure mode this project has been "
            "avoiding."
        )
    if len(cubes) != len(nodatas):
        raise ValueError("cubes and nodatas must be the same length")
    shapes = {c.shape[1:] for c in cubes}
    if len(shapes) != 1:
        raise ValueError(f"All cubes must share the same (rows, cols) grid; got {shapes}")

    labels = date_labels or [str(i) for i in range(len(cubes))]
    per_date: list[RealMNDWIResult] = []
    mndwi_stack = []
    for cube, nodata in zip(cubes, nodatas):
        r = real_mndwi(cube, nodata, bands, green_nm=green_nm, swir1_nm=swir1_nm)
        per_date.append(r)
        mndwi_stack.append(r.mndwi)

    # water needs mndwi > mndwi_min in EVERY date -> the binding case is the
    # MINIMUM mndwi across dates (mirrors persistent_wet_core()'s use of the
    # MAXIMUM brightness across dates for a "dark in every date" criterion).
    joint_min = np.minimum.reduce(mndwi_stack)
    raw = np.isfinite(joint_min) & (joint_min > mndwi_min)

    filtered = _label_and_filter(raw, min_component_px)
    final = _erode(filtered, buffer_px) if buffer_px > 0 else filtered

    stats = {
        "mndwi_min": mndwi_min,
        "green_nm_requested": green_nm, "swir1_nm_requested": swir1_nm,
        "green_nm_actual": per_date[0].green_wavelength_nm,
        "swir1_nm_actual": per_date[0].swir1_wavelength_nm,
        "green_offset_nm": per_date[0].green_offset_nm,
        "swir1_offset_nm": per_date[0].swir1_offset_nm,
        "min_component_px": min_component_px, "buffer_px": buffer_px,
        "n_dates": len(cubes), "date_labels": labels,
        "px_water_raw": int(raw.sum()),
        "px_water_after_components": int(filtered.sum()),
        "px_water_final": int(final.sum()),
        "criterion": (
            "min(real MNDWI across all supplied dates) > mndwi_min -- real "
            "named-band MNDWI, persistence structure mirrors "
            "persistent_wet_core(). See docs/WATER_MASK.md section 13."
        ),
    }
    return PersistentWetCoreMNDWIResult(
        mask=final, raw_mask=raw, joint_mndwi_min=joint_min, per_date_mndwi=per_date,
        mndwi_min=mndwi_min, min_component_px=min_component_px, buffer_px=buffer_px,
        stats=stats,
    )


def _label_and_filter(mask: np.ndarray, min_px: int) -> np.ndarray:
    """Drop connected components smaller than ``min_px``. Same shape as
    DesalGuard-main's helper of the same purpose, copied because the logic
    itself (not the threshold) is sensor/AOI-agnostic."""
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
    if _ndi is None or iterations <= 0:
        return mask
    return _ndi.binary_erosion(mask, iterations=iterations, border_value=0)
