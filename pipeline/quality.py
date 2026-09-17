"""Quality screening.

Water-leaving signal is a few percent of what a sensor sees. Before any index
is computed we remove pixels where the measurement cannot be trusted: no-data,
cloud, cirrus, sun glint, and pixels whose own reported uncertainty is large
relative to their value.

Every mask returned here is boolean with ``True`` meaning USABLE, and every
function reports how much it removed so the numbers can be shown to a reviewer
instead of disappearing silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class MaskReport:
    """What a screening step removed, so it can be audited."""

    step: str
    kept: int
    removed: int
    total: int
    detail: dict = field(default_factory=dict)

    @property
    def kept_fraction(self) -> float:
        return self.kept / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "kept": int(self.kept),
            "removed": int(self.removed),
            "total": int(self.total),
            "kept_fraction": round(self.kept_fraction, 6),
            "detail": self.detail,
        }


def scene_valid_mask(scene) -> tuple:
    """Baseline validity from the product's own masks.

    Returns ``(mask, report)``. Tanager ships ``nodata_pixels``,
    ``beta_cloud_mask`` and ``beta_cirrus_mask`` as uint8 with 255 as fill;
    anything non-zero is unusable.
    """
    m = scene.quality_masks()
    nodata = m["nodata"] != 0
    cloud = m["cloud"] != 0
    cirrus = m["cirrus"] != 0
    valid = ~(nodata | cloud | cirrus)
    rep = MaskReport(
        step="product_quality_masks",
        kept=int(valid.sum()), removed=int((~valid).sum()), total=valid.size,
        detail={
            "nodata_fraction": float(nodata.mean()),
            "cloud_fraction": float(cloud.mean()),
            "cirrus_fraction": float(cirrus.mean()),
        },
    )
    return valid, rep


def sunglint_mask(nir: np.ndarray, threshold: float = 0.05) -> tuple:
    """Reject specular sun glint.

    Over open water, surface reflectance in the NIR should be near zero because
    liquid water absorbs strongly beyond ~750 nm. Elevated NIR over water means
    glint, whitecaps, foam or a mixed/land pixel, and any water-colour index
    computed there is unreliable.

    Reference: Hu (2009) Floating Algae Index; Wang & Shi (2007) NIR/SWIR
    correction approach for turbid coastal waters.
    """
    ok = np.isfinite(nir) & (nir < threshold)
    rep = MaskReport(
        step="sunglint_nir",
        kept=int(ok.sum()), removed=int((~ok).sum()), total=ok.size,
        detail={"nir_threshold": threshold},
    )
    return ok, rep


def uncertainty_mask(values: np.ndarray, uncertainty: np.ndarray,
                     max_ratio: float = 1.0, floor: float = 1e-4) -> tuple:
    """Reject pixels whose reported uncertainty swamps their value.

    Tanager ships a per-pixel, per-band ``surface_reflectance_uncertainty``
    layer. Using it is strictly better than a blanket SNR assumption: it is the
    instrument's own statement about that measurement.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.abs(uncertainty) / np.maximum(np.abs(values), floor)
    ok = np.isfinite(ratio) & (ratio <= max_ratio)
    rep = MaskReport(
        step="uncertainty_ratio",
        kept=int(ok.sum()), removed=int((~ok).sum()), total=ok.size,
        detail={"max_ratio": max_ratio,
                "median_ratio": float(np.nanmedian(ratio)) if np.isfinite(ratio).any() else None},
    )
    return ok, rep


def good_band_indices(scene) -> np.ndarray:
    """Band indices the product itself flags as good.

    Tanager stores a ``good_wavelengths`` attribute on the reflectance dataset.
    Using it is preferable to the hardcoded 1350-1450 / 1800-1950 nm rule in the
    tutorial notebooks: for this scene the product flags 1342.41-1437.55 nm and
    1782.58-1967.21 nm, which differ from the hardcoded windows at both edges.
    """
    return np.where(scene.good_wavelengths)[0]


def combine(*masks: np.ndarray) -> np.ndarray:
    out = masks[0].copy()
    for m in masks[1:]:
        out &= m
    return out


def summarise(reports) -> dict:
    """Roll a list of MaskReports into one auditable dictionary."""
    return {
        "steps": [r.to_dict() for r in reports],
        "final_kept": int(reports[-1].kept) if reports else 0,
        "final_kept_fraction": round(reports[-1].kept_fraction, 6) if reports else 0.0,
    }
