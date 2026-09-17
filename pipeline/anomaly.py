"""Spectral anomaly detection over water.

The product of this module is a SPECTRAL ANOMALY SCORE, not a diagnosis. It
answers "how far does this pixel's spectrum sit from normal water here?", which
is a question remote sensing can actually answer. What the anomaly *is* is
handled separately in ``fingerprint.py``, and even there the output is a
weighted hypothesis, never a confirmed substance.

Primary detector is RX (Reed-Xiaoli): the Mahalanobis distance of each pixel
from the background water population, computed in a PCA-reduced space because
adjacent hyperspectral bands are almost perfectly correlated and the raw
covariance matrix is singular.

Reference: Reed & Yu (1990), IEEE Trans. ASSP 38(10):1760-1770.

A useful property: under the null hypothesis that a pixel is drawn from the
background multivariate normal, the squared Mahalanobis distance in k
dimensions follows a chi-squared distribution with k degrees of freedom. That
gives a principled significance threshold instead of a hand-picked cutoff.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:
    from scipy import stats as _stats
    from scipy import ndimage as _ndi
except Exception:                                   # pragma: no cover
    _stats = None
    _ndi = None


@dataclass
class AnomalyResult:
    score: np.ndarray               # RX statistic (squared Mahalanobis distance)
    pvalue: np.ndarray              # chi-squared survival probability
    sam: np.ndarray                 # spectral angle vs background mean, radians
    n_components: int
    explained_variance: float
    background_pixels: int
    test_pixels: int
    threshold_score: float
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "n_components": self.n_components,
            "explained_variance": round(float(self.explained_variance), 6),
            "background_pixels": int(self.background_pixels),
            "test_pixels": int(self.test_pixels),
            "threshold_score": round(float(self.threshold_score), 4),
            "params": self.params,
        }


def robust_background(X: np.ndarray, n_iter: int = 3,
                      trim_percentile: float = 95.0):
    """Iteratively trimmed mean/covariance of a spectral population.

    A plain mean over all water pixels is contaminated by the very anomaly we
    are trying to find: the event pulls the background toward itself and
    suppresses its own score. Each iteration drops the most distant
    ``100 - trim_percentile`` percent and recomputes, so the background
    converges on normal water.

    Returns ``(mean, covariance, keep_mask)``.
    """
    keep = np.ones(X.shape[0], dtype=bool)
    mu = X.mean(axis=0)
    cov = np.cov(X, rowvar=False)
    for _ in range(n_iter):
        try:
            inv = np.linalg.pinv(cov)
        except np.linalg.LinAlgError:               # pragma: no cover
            break
        d = X - mu
        dist = np.einsum("ij,jk,ik->i", d, inv, d)
        cut = np.percentile(dist[keep], trim_percentile)
        keep = dist <= cut
        if keep.sum() < X.shape[1] * 3:             # need n >> dimensions
            break
        mu = X[keep].mean(axis=0)
        cov = np.cov(X[keep], rowvar=False)
    return mu, cov, keep


def pca_fit(X: np.ndarray, n_components: int = 12):
    """PCA by SVD on the centred background matrix.

    Returns ``(mean, components, explained_variance_ratio_total)`` where
    ``components`` is (n_components, n_bands).
    """
    mu = X.mean(axis=0)
    Xc = X - mu
    # economy SVD; Xc is (n_samples, n_bands) with n_samples >> n_bands
    _, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    k = min(n_components, Vt.shape[0])
    var = S ** 2
    evr = float(var[:k].sum() / var.sum()) if var.sum() > 0 else 0.0
    return mu, Vt[:k], evr


def rx_anomaly(cube: np.ndarray, test_mask: np.ndarray,
               background_mask: np.ndarray,
               band_mask: np.ndarray | None = None,
               n_components: int = 12,
               alpha: float = 0.01,
               robust: bool = True) -> AnomalyResult:
    """RX anomaly score for every pixel in ``test_mask``.

    Parameters
    ----------
    cube
        (bands, rows, cols) reflectance.
    test_mask
        Pixels to score (normally all water).
    background_mask
        Pixels defining "normal" (normally offshore water). May overlap
        ``test_mask``; the robust trimming handles the contamination.
    band_mask
        Which bands to use. Defaults to all. Pass the water-informative band
        mask so the detector is not driven by NIR/SWIR noise.
    n_components
        PCA dimensionality. The chi-squared threshold uses this as its degrees
        of freedom.
    alpha
        False-alarm rate for the reported threshold.
    """
    b, rows, cols = cube.shape
    if band_mask is None:
        band_mask = np.ones(b, dtype=bool)
    sel = cube[band_mask]                              # (nb, rows, cols)
    nb = sel.shape[0]

    flat = np.moveaxis(sel, 0, -1).reshape(-1, nb)     # (px, nb)
    finite = np.isfinite(flat).all(axis=1)
    tm = test_mask.ravel() & finite
    bm = background_mask.ravel() & finite

    score = np.full(rows * cols, np.nan, dtype="float32")
    pval = np.full(rows * cols, np.nan, dtype="float32")
    sam = np.full(rows * cols, np.nan, dtype="float32")

    if bm.sum() < nb * 3 or tm.sum() == 0:
        return AnomalyResult(score.reshape(rows, cols), pval.reshape(rows, cols),
                             sam.reshape(rows, cols), 0, 0.0,
                             int(bm.sum()), int(tm.sum()), float("nan"),
                             {"error": "insufficient background pixels"})

    Xb = flat[bm].astype("float64")
    mu_pca, comps, evr = pca_fit(Xb, n_components)
    k = comps.shape[0]

    Zb = (Xb - mu_pca) @ comps.T                        # background scores
    if robust:
        mu_z, cov_z, keep = robust_background(Zb)
        n_bg_used = int(keep.sum())
    else:
        mu_z, cov_z = Zb.mean(axis=0), np.cov(Zb, rowvar=False)
        n_bg_used = Zb.shape[0]
    inv = np.linalg.pinv(cov_z)

    Xt = flat[tm].astype("float64")
    Zt = (Xt - mu_pca) @ comps.T
    d = Zt - mu_z
    rx = np.einsum("ij,jk,ik->i", d, inv, d)
    score[tm] = rx

    # Threshold calibration.
    #
    # The textbook RX threshold assumes the background is multivariate normal,
    # which makes the squared Mahalanobis distance chi-squared with k degrees of
    # freedom. Real coastal water is not: it is a mixture of offshore, nearshore
    # and depth-influenced populations, so the chi-squared tail is far too
    # optimistic. On the Gulf of Annaba scene the nominal 1% chi-squared
    # threshold flags about 15% of water pixels.
    #
    # We therefore report the chi-squared value for reference but threshold on
    # the EMPIRICAL distribution of the background population itself, which
    # gives a real false-alarm rate regardless of distribution shape.
    rx_bg = np.einsum("ij,jk,ik->i", Zb - mu_z, inv, (Zb - mu_z))
    thr_empirical = float(np.percentile(rx_bg, 100.0 * (1.0 - alpha)))
    thr_chi2 = (float(_stats.chi2.isf(alpha, df=k)) if _stats is not None
                else float("nan"))
    if _stats is not None:
        pval[tm] = _stats.chi2.sf(rx, df=k)
    thr = thr_empirical

    # Shape-only comparison against the background mean spectrum.
    ref = Xb.mean(axis=0)
    num = Xt @ ref
    den = np.sqrt((Xt ** 2).sum(axis=1)) * np.sqrt((ref ** 2).sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        sam[tm] = np.arccos(np.clip(num / den, -1.0, 1.0))

    return AnomalyResult(
        score=score.reshape(rows, cols),
        pvalue=pval.reshape(rows, cols),
        sam=sam.reshape(rows, cols),
        n_components=k,
        explained_variance=evr,
        background_pixels=n_bg_used,
        test_pixels=int(tm.sum()),
        threshold_score=thr,
        params={
            "alpha": alpha,
            "robust_background": robust,
            "n_bands_used": int(nb),
            "method": "RX / Mahalanobis in PCA space",
            "reference": "Reed & Yu (1990) IEEE Trans. ASSP 38(10):1760-1770",
            "threshold_rule": "empirical percentile of background RX distribution",
            "threshold_empirical": round(thr_empirical, 4),
            "threshold_chi2_nominal": (round(thr_chi2, 4)
                                       if np.isfinite(thr_chi2) else None),
            "chi2_assumption_note": (
                "Chi-squared threshold reported for reference only; the "
                "background is a mixture and is not multivariate normal, so the "
                "empirical threshold is used."
            ),
        },
    )


# --------------------------------------------------------------------------- #
# Turning a score field into discrete events
# --------------------------------------------------------------------------- #
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
                   pixel_size_m: float, min_pixels: int = 25,
                   close_iterations: int = 1) -> tuple:
    """Group significant anomaly pixels into connected event regions.

    A morphological closing bridges single-pixel gaps so one plume is not split
    into confetti, then components below ``min_pixels`` are discarded as
    speckle. At 30 m, ``min_pixels=25`` is 22 500 m2, about 2.25 ha.
    """
    sig = np.isfinite(score) & (score >= threshold)
    if _ndi is not None and close_iterations > 0:
        sig = _ndi.binary_closing(sig, iterations=close_iterations)
        sig &= np.isfinite(score)

    if _ndi is None:                                    # pragma: no cover
        return np.zeros_like(score, dtype=int), []

    lab, n = _ndi.label(sig)
    px_area = (pixel_size_m ** 2) / 1e6                 # km2 per pixel
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
            label=new_label,
            pixel_count=cnt,
            area_km2=float(cnt * px_area),
            centroid_rc=(float(rr.mean()), float(cc.mean())),
            mean_score=float(np.nanmean(score[m])),
            max_score=float(np.nanmax(score[m])),
            min_pvalue=float(np.nanmin(pvalue[m])) if np.isfinite(pvalue[m]).any() else float("nan"),
            bbox_rc=(int(rr.min()), int(cc.min()), int(rr.max()), int(cc.max())),
        ))
    regions.sort(key=lambda r: r.area_km2, reverse=True)
    return out, regions
