"""Spectral anomaly detection over the validated inland wet core.

Mirrors the INTERFACE SHAPE of DesalGuard-main's `pipeline/anomaly.py` (RX /
Mahalanobis distance in PCA-reduced space, robust iteratively-trimmed
background, empirical rather than chi-squared thresholding, SAM as a
secondary shape check, connected-component event extraction) — same reason
`pipeline/provenance.py` and `pipeline/water_mask.py`'s dataclass shapes were
carried over: so folding this into DesalGuard-main later is a
copy-and-namespace operation.

It does NOT reuse DesalGuard's coastal thresholds, endmembers, or default
parameter values (`n_components=12`, `min_pixels=25` at 30 m, etc.) — those
are tuned for a large developed coastline with a presumably-thousands-strong
background water population. Every threshold/default below is either derived
from this AOI's own pixels or explicitly marked PLACEHOLDER — see the
"Genuinely tuned vs. placeholder" table at the bottom of this docstring.

--------------------------------------------------------------------------
THE CENTRAL, STATED LIMITATION OF THIS MODULE — READ BEFORE USING SCORES
--------------------------------------------------------------------------
DesalGuard's `robust_background()` requires `n_background_pixels >=
n_features * 3` to avoid a degenerate covariance estimate, which is a
reasonable bar when the background population is thousands of pixels of
open coastal water. Here, the validated wet core at Shawka Dam is ~10
pixels in a SINGLE date, and even the loosest zero-leakage population found
during water-mask validation (docs/WATER_MASK.md section 12,
darkness_max=0.13) is only 17 pixels. Pooling both dates' spectra at every
qualifying spatial location (see `rx_anomaly()` below) raises this to
~34 background samples — still small, not "thousands." Two adaptations
follow directly from this, both explicit rather than silently applied:

1. Bands are reduced to a small number of wavelength-ordered GROUP means
   (default 6, vs. DesalGuard's use of the full ~218-band space reduced by
   PCA to 12 components) BEFORE PCA, so the feature space starts an order
   of magnitude smaller. This is defensible for the same reason
   `pipeline/water_mask.py` uses band groups: adjacent hyperspectral bands
   are almost perfectly correlated anyway (DesalGuard's own module
   docstring makes this point to justify PCA in the first place), so
   further group-averaging is a cruder version of the same dimensionality
   reduction, not a different kind of shortcut.
2. A small covariance shrinkage term is added on top of DesalGuard's
   pattern (see `robust_background()`), because even after reducing to ~6
   features, ~34 samples is thin for a stable 6x6 covariance estimate.

**Read the anomaly SCORES this module produces as a relative ranking of
which wet-core pixels are spectrally more or less unusual relative to
this AOI's own observed water population across the two available dates
— not as a calibrated detector with a defensible false-alarm rate.**
DesalGuard's empirical-percentile threshold is reported here too (for
interface parity and because it is still a useful rough marker), but at
n~34 a percentile estimate is coarse; `threshold_score` in the result
carries a `background_pixels` count precisely so this is never presented
as more solid than it is. This is the Task-2 analogue of the water-mask
finding stated plainly in docs/WATER_MASK.md section 9: a genuine
statistical limitation, reported rather than hidden or silently
worked around.

Reference: Reed & Yu (1990), IEEE Trans. ASSP 38(10):1760-1770 (same as
DesalGuard cites — the method itself is unchanged; only its inputs are
adapted here).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:
    from scipy import ndimage as _ndi
except Exception:                                   # pragma: no cover
    _ndi = None

from .water_mask import find_bad_bands


# --------------------------------------------------------------------------- #
# Feature extraction: wavelength-ORDERED band groups, finer than water_mask's
# 3-group split but still index-based (no wavelength table needed — see
# docs/WATER_MASK.md section 2 for why that table isn't available).
# --------------------------------------------------------------------------- #
DEFAULT_N_GROUPS = 6   # GENUINELY TUNED for this AOI's sample size: chosen so
                        # that even the pooled ~34-sample background clears
                        # DesalGuard's own robust_background() minimum
                        # (n_features * 3 = 18) with headroom, while still
                        # giving the detector more spectral resolution than
                        # water_mask.py's 3-group split. Not fit against any
                        # labeled anomaly example (none exist for this AOI) —
                        # chosen from the sample-size arithmetic alone.


def band_group_features(cube: np.ndarray, nodata: float, n_groups: int = DEFAULT_N_GROUPS,
                        scale: float = 1.0 / 10000.0):
    """Reflectance band-GROUP means, `n_groups` equal-count contiguous groups
    across the valid (non-nodata-anywhere) band sequence, in band order.

    Same bad-band handling and 1/10000 scale as pipeline/water_mask.py's
    band_groups() / brightness() — see those for sourcing. Generalizes the
    3-group split to an arbitrary count so the anomaly detector can use a
    different (finer) resolution than the water mask without duplicating
    the underlying nodata/scale logic twice, independently.

    Returns ``(features, good_band_idx, bad_band_idx)`` where ``features``
    is ``(n_groups, rows, cols)``.
    """
    bad = find_bad_bands(cube, nodata)
    n_bands = cube.shape[0]
    good = np.array([b for b in range(n_bands) if b not in bad])
    refl = cube[good].astype(np.float64) * scale
    n = len(good)
    edges = np.linspace(0, n, n_groups + 1).astype(int)
    feats = np.stack([refl[edges[i]:edges[i + 1]].mean(axis=0) for i in range(n_groups)], axis=0)
    return feats, good, bad


# --------------------------------------------------------------------------- #
# Background statistics — same algorithm as DesalGuard, small-n caveats added
# --------------------------------------------------------------------------- #
def robust_background(X: np.ndarray, n_iter: int = 3, trim_percentile: float = 95.0,
                       shrinkage: float = 0.15):
    """Iteratively trimmed mean/covariance, as DesalGuard-main's function of
    the same name (see that module's docstring for the rationale — an
    untrimmed mean is contaminated by the very anomaly being searched for).

    ADAPTATION vs. DesalGuard: a `shrinkage` term is blended into the
    covariance (`(1-shrinkage)*cov + shrinkage*mean_variance*I`) because at
    this AOI's sample size (tens, not thousands, of background pixels — see
    module docstring) an unregularized covariance estimate in even a 6-D
    feature space is materially less stable. `shrinkage=0.15` is a
    PLACEHOLDER: a round, conservative value in the range typically quoted
    for Ledoit-Wolf-style shrinkage, not fit against this AOI's own data
    (there is no labeled anomaly/non-anomaly split here to fit it against).
    Stops early (as DesalGuard's version does) if trimming would drop the
    sample below `n_features * 3`.

    Returns ``(mean, covariance, keep_mask)``.
    """
    keep = np.ones(X.shape[0], dtype=bool)
    mu = X.mean(axis=0)
    cov = np.cov(X, rowvar=False)
    if cov.ndim == 0:
        cov = np.array([[float(cov)]])
    for _ in range(n_iter):
        try:
            inv = np.linalg.pinv(cov)
        except np.linalg.LinAlgError:               # pragma: no cover
            break
        d = X - mu
        dist = np.einsum("ij,jk,ik->i", d, inv, d)
        cut = np.percentile(dist[keep], trim_percentile)
        keep = dist <= cut
        if keep.sum() < X.shape[1] * 3:
            break
        mu = X[keep].mean(axis=0)
        cov = np.cov(X[keep], rowvar=False)
        if cov.ndim == 0:
            cov = np.array([[float(cov)]])
    mean_var = float(np.trace(cov)) / max(cov.shape[0], 1)
    cov = (1.0 - shrinkage) * cov + shrinkage * mean_var * np.eye(cov.shape[0])
    return mu, cov, keep


def pca_fit(X: np.ndarray, n_components: int):
    """PCA by SVD, identical logic to DesalGuard-main's function of the same
    name. ``n_components`` should already be capped by the caller to a value
    safe for the actual sample size in hand (see rx_anomaly())."""
    mu = X.mean(axis=0)
    Xc = X - mu
    _, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    k = min(n_components, Vt.shape[0])
    var = S ** 2
    evr = float(var[:k].sum() / var.sum()) if var.sum() > 0 else 0.0
    return mu, Vt[:k], evr


# --------------------------------------------------------------------------- #
# Result containers — same shape as DesalGuard's AnomalyResult/EventRegion
# --------------------------------------------------------------------------- #
@dataclass
class AnomalyResult:
    date_label: str
    score: np.ndarray               # RX statistic (squared Mahalanobis distance)
    pvalue: np.ndarray              # chi-squared survival probability (reference only)
    sam: np.ndarray                 # spectral angle vs pooled background mean, radians
    n_components: int
    explained_variance: float
    background_pixels: int
    test_pixels: int
    threshold_score: float
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "date_label": self.date_label,
            "n_components": self.n_components,
            "explained_variance": round(float(self.explained_variance), 6),
            "background_pixels": int(self.background_pixels),
            "test_pixels": int(self.test_pixels),
            "threshold_score": round(float(self.threshold_score), 4),
            "params": self.params,
        }


@dataclass
class EventRegion:
    label: int
    pixel_count: int
    area_km2: float
    centroid_rc: tuple
    mean_score: float
    max_score: float
    min_pvalue: float
    bbox_rc: tuple


def extract_events(score: np.ndarray, pvalue: np.ndarray, threshold: float,
                   pixel_size_m: float, min_pixels: int = 1,
                   close_iterations: int = 0) -> tuple:
    """Group significant anomaly pixels into connected event regions. Same
    logic as DesalGuard-main's function of the same name.

    DEFAULTS CHANGED, GENUINELY TUNED for this AOI's scale: DesalGuard's
    `min_pixels=25` (2.25 ha at 30 m) would discard every possible event at
    Shawka Dam outright — the entire validated wet core is 10 pixels
    (0.9 ha). `min_pixels=1` here means no speckle filtering is applied at
    all; at this AOI's scale, a single anomalous pixel inside a 10-pixel
    core IS potentially the whole signal, not speckle to be filtered out.
    `close_iterations=0` (vs. DesalGuard's 1) for the same reason: a
    morphological closing step assumes gaps between pixels are worth
    bridging, which presumes a multi-pixel-wide feature; nothing here is
    large enough for that assumption to clearly hold.
    """
    sig = np.isfinite(score) & (score >= threshold)
    if _ndi is not None and close_iterations > 0:
        sig = _ndi.binary_closing(sig, iterations=close_iterations)
        sig &= np.isfinite(score)

    if _ndi is None:                                    # pragma: no cover
        return np.zeros_like(score, dtype=int), []

    lab, n = _ndi.label(sig)
    px_area = (pixel_size_m ** 2) / 1e6
    regions: list[EventRegion] = []
    out = np.zeros_like(lab)
    new_label = 0
    for i in range(1, n + 1):
        m = lab == i
        cnt = int(m.sum())
        if cnt < min_pixels:
            continue
        new_label += 1
        out[m] = new_label
        rr, cc = np.where(m)
        regions.append(EventRegion(
            label=new_label, pixel_count=cnt, area_km2=float(cnt * px_area),
            centroid_rc=(float(rr.mean()), float(cc.mean())),
            mean_score=float(np.nanmean(score[m])), max_score=float(np.nanmax(score[m])),
            min_pvalue=(float(np.nanmin(pvalue[m])) if np.isfinite(pvalue[m]).any() else float("nan")),
            bbox_rc=(int(rr.min()), int(cc.min()), int(rr.max()), int(cc.max())),
        ))
    regions.sort(key=lambda r: r.area_km2, reverse=True)
    return out, regions


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def rx_anomaly(cubes: list, nodatas: list, test_mask: np.ndarray,
               background_mask: np.ndarray, date_labels: list | None = None,
               n_groups: int = DEFAULT_N_GROUPS, n_components: int | None = None,
               alpha: float = 0.10, robust: bool = True,
               shrinkage: float = 0.15) -> dict:
    """RX anomaly score for every pixel in `test_mask`, scored separately
    per date but against ONE POOLED background built from every date
    supplied — see module docstring for why pooling across dates, not just
    within one, is necessary to get a workable sample size here.

    Parameters
    ----------
    cubes, nodatas
        One cube + nodata value per date, all on the SAME (rows, cols)
        pixel grid (same precondition as
        pipeline.water_mask.persistent_wet_core() — checked here by shape
        only, not re-verified for real-world alignment).
    test_mask, background_mask
        SHARED (rows, cols) boolean masks — the same spatial locations
        apply to every date. Recommended (and what
        scripts/derive_anomaly_scores.py actually uses): `test_mask` =
        `persistent_wet_core(darkness_max=0.10)` result (the validated
        10-pixel core); `background_mask` = the wider, still zero-leakage
        `persistent_wet_core(darkness_max=0.13)` result (17 px; the
        default-threshold core is a strict subset of it, since the
        underlying criterion is monotonic in the threshold — see
        docs/WATER_MASK.md section 12). `test_mask` may overlap
        `background_mask` — as in DesalGuard's version, the robust trimming
        is what handles that contamination, not mask disjointness.
    n_components
        PCA dimensionality requested. Actually-used value is capped to stay
        under `n_background_pixels / 3` (DesalGuard's own robust_background
        minimum) and is reported in the result rather than silently
        overridden.
    alpha
        False-alarm rate for the reported empirical threshold.
        DesalGuard's default is 0.01; 0.10 is used here as a PLACEHOLDER,
        widened because a 1%-tail estimate from a background of ~34 samples
        is close to meaningless (it is asking the data to resolve the
        99th percentile from ~34 points). Reported plainly as a rough
        marker, not a calibrated rate — see module docstring.

    Returns
    -------
    dict mapping date_label -> AnomalyResult.
    """
    if len(cubes) < 1:
        raise ValueError("rx_anomaly() needs at least one cube")
    if len(cubes) != len(nodatas):
        raise ValueError("cubes and nodatas must be the same length")
    shapes = {c.shape[1:] for c in cubes}
    if len(shapes) != 1:
        raise ValueError(f"All cubes must share the same (rows, cols) grid; got {shapes}")
    labels = date_labels or [str(i) for i in range(len(cubes))]

    feats_per_date = []
    for cube, nodata in zip(cubes, nodatas):
        feats, good, bad = band_group_features(cube, nodata, n_groups=n_groups)
        feats_per_date.append(feats)

    rows, cols = cubes[0].shape[1], cubes[0].shape[2]
    bm = background_mask.ravel()
    tm = test_mask.ravel()

    # Pool background across every date supplied.
    Xb_list = []
    for feats in feats_per_date:
        flat = np.moveaxis(feats, 0, -1).reshape(-1, n_groups)
        finite = np.isfinite(flat).all(axis=1)
        Xb_list.append(flat[bm & finite])
    Xb = np.concatenate(Xb_list, axis=0).astype("float64")
    n_bg = Xb.shape[0]

    if n_bg < n_groups * 3:
        # Not enough even for the reduced feature space -- refuse rather
        # than silently return a meaningless covariance.
        empty = np.full(rows * cols, np.nan, dtype="float32")
        note = (f"insufficient pooled background pixels ({n_bg}) for "
                f"{n_groups} features (need >= {n_groups * 3}); no scores computed")
        return {
            lbl: AnomalyResult(lbl, empty.reshape(rows, cols).copy(),
                               empty.reshape(rows, cols).copy(), empty.reshape(rows, cols).copy(),
                               0, 0.0, n_bg, int((tm).sum()), float("nan"), {"error": note})
            for lbl in labels
        }

    k_requested = n_components or min(n_groups, 4)
    k_safe = max(1, min(k_requested, n_groups, n_bg // 3 - 1 if n_bg // 3 > 1 else 1))

    mu_pca, comps, evr = pca_fit(Xb, k_safe)
    k = comps.shape[0]
    Zb = (Xb - mu_pca) @ comps.T
    if robust:
        mu_z, cov_z, keep = robust_background(Zb, shrinkage=shrinkage)
        n_bg_used = int(keep.sum())
    else:
        mu_z = Zb.mean(axis=0)
        cov_z = np.cov(Zb, rowvar=False)
        if cov_z.ndim == 0:
            cov_z = np.array([[float(cov_z)]])
        n_bg_used = Zb.shape[0]
    inv = np.linalg.pinv(cov_z)

    rx_bg = np.einsum("ij,jk,ik->i", Zb - mu_z, inv, (Zb - mu_z))
    thr_empirical = float(np.percentile(rx_bg, 100.0 * (1.0 - alpha)))
    ref = Xb.mean(axis=0)

    try:
        from scipy import stats as _stats
        thr_chi2 = float(_stats.chi2.isf(alpha, df=k))
    except Exception:
        _stats = None
        thr_chi2 = float("nan")

    results = {}
    for feats, nodata, lbl, cube in zip(feats_per_date, nodatas, labels, cubes):
        flat = np.moveaxis(feats, 0, -1).reshape(-1, n_groups)
        finite = np.isfinite(flat).all(axis=1)
        tm_d = tm & finite

        score = np.full(rows * cols, np.nan, dtype="float32")
        pval = np.full(rows * cols, np.nan, dtype="float32")
        sam = np.full(rows * cols, np.nan, dtype="float32")

        Xt = flat[tm_d].astype("float64")
        if Xt.shape[0] > 0:
            Zt = (Xt - mu_pca) @ comps.T
            d = Zt - mu_z
            rx = np.einsum("ij,jk,ik->i", d, inv, d)
            score[tm_d] = rx
            if _stats is not None:
                pval[tm_d] = _stats.chi2.sf(rx, df=k)
            num = Xt @ ref
            den = np.sqrt((Xt ** 2).sum(axis=1)) * np.sqrt((ref ** 2).sum())
            with np.errstate(invalid="ignore", divide="ignore"):
                sam[tm_d] = np.arccos(np.clip(num / den, -1.0, 1.0))

        results[lbl] = AnomalyResult(
            date_label=lbl,
            score=score.reshape(rows, cols), pvalue=pval.reshape(rows, cols),
            sam=sam.reshape(rows, cols), n_components=k, explained_variance=evr,
            background_pixels=n_bg_used, test_pixels=int(tm_d.sum()),
            threshold_score=thr_empirical,
            params={
                "alpha": alpha, "robust_background": robust, "shrinkage": shrinkage,
                "n_groups": n_groups, "n_components_requested": k_requested,
                "n_components_used": k, "pooled_background_pixels_total": n_bg,
                "method": "RX / Mahalanobis in PCA-of-band-group-means space (inland adaptation)",
                "reference": "Reed & Yu (1990) IEEE Trans. ASSP 38(10):1760-1770",
                "threshold_rule": "empirical percentile of pooled background RX distribution",
                "threshold_empirical": round(thr_empirical, 4),
                "threshold_chi2_nominal": round(thr_chi2, 4) if np.isfinite(thr_chi2) else None,
                "small_sample_caveat": (
                    f"Background pooled across {len(cubes)} date(s): {n_bg} total pixel-spectra "
                    f"({n_bg_used} after robust trimming). This is materially smaller than the "
                    "population this method assumes (DesalGuard-main's coastal case, thousands of "
                    "background pixels) -- scores here should be read as a relative ranking, not a "
                    "calibrated detection. See module docstring."
                ),
            },
        )
    return results
