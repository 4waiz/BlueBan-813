"""Reader contract for REAL Satellite 813 aquatic products (none are accessible yet).

The authenticated audit (docs/AUTHENTICATED_DATA_AUDIT.md, 30 Sep 2026) found no
downloadable 813 product, so nothing in the pipeline uses real 813 data. This
module fixes, in code, what a real product must provide before BLUEBAN will use
it, so the day a product arrives it cannot be misread:

* **Remote-sensing reflectance** (Rrs, sr^-1) or water-leaving reflectance
  (rho_w = pi * Rrs) is accepted directly.
* **Water-leaving radiance** (Lw, W m^-2 sr^-1 nm^-1) is accepted **only with the
  matching downwelling irradiance** (Ed, same bands and time), because
  Rrs = Lw / Ed. The Cockpit's description of the product ("optimized bands for
  water-leaving radiance") does not say which one ships; guessing Ed from a
  climatology would silently bias every index.
* Band centres must lie in the published 400-1700 nm range; per-band validity is
  kept (NaN), never interpolated across bad bands.

The simulated product (pipeline/satellite813.py) is always labelled SIMULATED;
a product read here is labelled REAL with its source.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SPEC_RANGE_NM = (400.0, 1700.0)
ACCEPTED_QUANTITIES = ("Rrs", "rho_w", "Lw")


class Refused(ValueError):
    """The product cannot be used without guessing something."""


@dataclass
class Real813Product:
    rrs: np.ndarray                 # (bands, rows, cols) remote-sensing reflectance, sr^-1
    wavelengths_nm: np.ndarray
    source: str
    valid_band: np.ndarray
    notes: list = field(default_factory=list)
    simulated: bool = False

    @property
    def label(self) -> str:
        return f"813 REAL ({self.source})"


def read(data: np.ndarray, wavelengths_nm, quantity: str, source: str,
         ed: np.ndarray | None = None) -> Real813Product:
    """Validate and convert a real 813 array to Rrs. Raises Refused rather than guess."""
    if quantity not in ACCEPTED_QUANTITIES:
        raise Refused(f"unknown quantity {quantity!r}; expected one of {ACCEPTED_QUANTITIES}")
    wl = np.asarray(wavelengths_nm, float)
    data = np.asarray(data, float)
    if data.ndim != 3 or data.shape[0] != wl.size:
        raise Refused(f"expected (bands, rows, cols) with {wl.size} bands, got {data.shape}")
    if wl.min() < SPEC_RANGE_NM[0] - 5 or wl.max() > SPEC_RANGE_NM[1] + 5:
        raise Refused(f"band centres {wl.min():.0f}-{wl.max():.0f} nm fall outside the published "
                      f"{SPEC_RANGE_NM[0]:.0f}-{SPEC_RANGE_NM[1]:.0f} nm range")
    notes = []
    if quantity == "Lw":
        if ed is None:
            raise Refused("water-leaving radiance (Lw) needs the matching downwelling irradiance (Ed): "
                          "Rrs = Lw / Ed. BLUEBAN will not assume an Ed climatology.")
        ed = np.asarray(ed, float)
        if ed.shape not in (data.shape, (wl.size,), (wl.size, 1, 1)):
            raise Refused(f"Ed shape {ed.shape} does not match Lw {data.shape}")
        ed_b = ed.reshape(wl.size, 1, 1) if ed.ndim == 1 else ed
        with np.errstate(divide="ignore", invalid="ignore"):
            rrs = np.where(ed_b > 0, data / ed_b, np.nan)
        notes.append("Rrs computed as Lw / Ed from the product's own irradiance")
    elif quantity == "rho_w":
        rrs = data / np.pi
        notes.append("Rrs = rho_w / pi")
    else:
        rrs = data
    valid = np.array([np.isfinite(b).any() for b in rrs])
    if (rrs[np.isfinite(rrs)] < -0.01).any():
        notes.append("negative Rrs below -0.01 present: atmospheric over-correction; affected pixels kept as values, "
                     "downstream masks decide")
    return Real813Product(rrs=rrs, wavelengths_nm=wl, source=source, valid_band=valid, notes=notes)
