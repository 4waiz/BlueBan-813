"""Real-813 reader contract and the Sentinel-1 surface-dark-anomaly mode."""
import numpy as np
import pytest

from pipeline import satellite813_real as r813
from pipeline import sentinel1 as s1


WL = np.linspace(400, 1700, 205)


def test_real_813_accepts_rrs_and_rho_w():
    rrs = np.full((205, 4, 4), 0.004)
    p = r813.read(rrs, WL, "Rrs", "test")
    assert p.label.startswith("813 REAL") and not p.simulated
    q = r813.read(rrs * np.pi, WL, "rho_w", "test")
    assert np.allclose(q.rrs, 0.004)


def test_real_813_refuses_radiance_without_irradiance():
    lw = np.full((205, 2, 2), 0.5)
    with pytest.raises(r813.Refused, match="downwelling irradiance"):
        r813.read(lw, WL, "Lw", "test")
    ed = np.full(205, 125.0)
    p = r813.read(lw, WL, "Lw", "test", ed=ed)
    assert np.allclose(p.rrs, 0.004)


def test_real_813_refuses_out_of_spec_bands_and_shapes():
    with pytest.raises(r813.Refused):
        r813.read(np.zeros((205, 2, 2)), np.linspace(350, 2500, 205), "Rrs", "x")
    with pytest.raises(r813.Refused):
        r813.read(np.zeros((10, 2, 2)), WL, "Rrs", "x")


def test_sentinel1_dark_patch_is_an_anomaly_with_lookalikes_never_oil():
    rng = np.random.default_rng(0)
    s = -18 + rng.normal(0, 0.8, (300, 300))
    s[120:170, 100:220] -= 7                      # smooth elongated patch
    water = np.ones_like(s, bool)
    found = s1.detect_dark(s, water, pixel_m=20, wind_ms=6.0)
    assert len(found) == 1
    a = found[0]
    assert a.event_type == "SURFACE_DARK_ANOMALY" and "oil" not in a.event_type.lower()
    assert a.contrast_db > 5 and a.elongation > 1.5 and 1.5 < a.area_km2 < 3.0
    assert any("film" in x for x in a.lookalikes)


def test_sentinel1_low_wind_lowers_confidence():
    rng = np.random.default_rng(1)
    s = -18 + rng.normal(0, 0.8, (200, 200))
    s[80:120, 80:140] -= 7
    water = np.ones_like(s, bool)
    calm = s1.detect_dark(s, water, pixel_m=20, wind_ms=2.0)[0]
    breezy = s1.detect_dark(s, water, pixel_m=20, wind_ms=6.0)[0]
    assert calm.confidence < breezy.confidence and calm.notes
