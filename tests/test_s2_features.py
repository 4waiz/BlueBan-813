"""Sentinel-2 L2A feature set: decoding, formulas, coefficients and masks."""
import numpy as np
import pytest

from pipeline import s2_features as s2


# --------------------------------------------------------------------------- #
# L2A decoding
# --------------------------------------------------------------------------- #
def test_boa_offset_follows_the_processing_baseline_not_the_date():
    assert s2.boa_offset_for_baseline("05.13") == -1000.0
    assert s2.boa_offset_for_baseline("04.00") == -1000.0
    assert s2.boa_offset_for_baseline("02.12") == 0.0
    assert s2.boa_offset_for_baseline(3.99) == 0.0


def test_missing_baseline_refuses_to_guess():
    with pytest.raises(ValueError):
        s2.boa_offset_for_baseline(None)
    with pytest.raises(ValueError):
        s2.boa_offset_for_baseline("N/A")


def test_dn_decoding_applies_offset_and_nodata():
    dn = np.array([0, 1000, 1500, 900], dtype="uint16")
    new = s2.dn_to_reflectance(dn, "05.13")
    assert np.isnan(new[0])                       # 0 is L2A no-data
    assert new[1] == pytest.approx(0.0)
    assert new[2] == pytest.approx(0.05)
    assert new[3] == pytest.approx(-0.01)         # negative kept, not clipped
    old = s2.dn_to_reflectance(dn, "02.12")
    assert old[2] == pytest.approx(0.15)


# --------------------------------------------------------------------------- #
# Formulas
# --------------------------------------------------------------------------- #
def _flat(v=0.02, shape=(4, 4)):
    return {b: np.full(shape, v, dtype="float32") for b in s2.WATER_BANDS}


def test_ndci_is_bounded_and_matches_the_definition():
    r = _flat()
    r["B05"][:] = 0.03
    r["B04"][:] = 0.01
    f = s2.compute_features(r, surface_correction=None)
    assert np.allclose(f["NDCI"], (0.03 - 0.01) / (0.03 + 0.01))
    assert np.nanmax(np.abs(f["NDCI"])) <= 1.0


def test_mci_and_fai_are_zero_on_a_straight_spectrum_and_positive_on_a_peak():
    lam = s2.S2_CENTRES_NM["Sentinel-2A"]
    r = {b: np.full((2, 2), 0.01 + 1e-5 * (lam[b] - 400), dtype="float64")
         for b in s2.WATER_BANDS}
    f = s2.compute_features(r, surface_correction=None)
    assert np.allclose(f["MCI"], 0.0, atol=1e-7)
    assert np.allclose(f["FAI"], 0.0, atol=1e-7)
    r["B05"] = r["B05"] + 0.01                     # red-edge peak
    r["B8A"] = r["B8A"] + 0.02                     # NIR above baseline
    f = s2.compute_features(r, surface_correction=None)
    assert np.all(f["MCI"] > 0.009)
    assert np.all(f["FAI"] > 0.019)


def test_nechad_coefficients_match_the_published_tabulation():
    tur = s2.FEATURES["TUR_NECHAD2016"].coefficients
    spm = s2.FEATURES["SPM_NECHAD2016"].coefficients
    assert (tur["A"], tur["C"]) == (366.14, 0.19563)
    assert (spm["A"], spm["C"]) == (342.10, 0.19563)
    d = s2.FEATURES["TUR_DOGLIOTTI2015"].coefficients
    assert (d["A_red"], d["C_red"], d["A_nir"], d["C_nir"]) == (228.1, 0.1641, 3078.9, 0.2112)


def test_nechad_value_and_validity_mask():
    r = _flat(0.0)
    r["B04"][:] = 0.02
    f = s2.compute_features(r, surface_correction=None)
    expect = 366.14 * 0.02 / (1 - 0.02 / 0.19563)
    assert np.allclose(f["TUR_NECHAD2016"], expect, rtol=1e-5)
    r["B04"][:] = 0.5 * 0.19563 + 0.001            # beyond 0.5 C: masked
    f = s2.compute_features(r, surface_correction=None)
    assert np.all(np.isnan(f["TUR_NECHAD2016"]))


def test_dogliotti_blend_is_continuous_across_the_switch():
    reds = np.linspace(0.02, 0.10, 400)
    r = _flat(0.0, shape=reds.shape)
    r["B04"] = reds.astype("float64")
    r["B8A"] = (reds * 0.4).astype("float64")
    t = s2.compute_features(r, surface_correction=None)["TUR_DOGLIOTTI2015"]
    assert np.all(np.isfinite(t))
    jumps = np.abs(np.diff(t))
    assert jumps.max() < 5 * np.median(jumps) + 1.0


def test_flat_glint_offset_is_removed_and_baseline_heights_are_invariant():
    lam = s2.S2_CENTRES_NM["Sentinel-2A"]
    clean = {b: np.full((2, 2), 0.01 + 1e-5 * (lam[b] - 400)) for b in s2.WATER_BANDS}
    clean["B05"] = clean["B05"] + 0.004              # a real red-edge signal
    clean["B11"][:] = 0.0
    clean["B12"][:] = 0.0
    glinty = {b: v + 0.035 for b, v in clean.items()}  # spectrally flat glint
    a = s2.compute_features(clean, surface_correction="swir_b12")
    b = s2.compute_features(glinty, surface_correction="swir_b12")
    assert np.allclose(a["NDCI"], b["NDCI"], atol=1e-6)   # glint removed
    assert np.allclose(a["MCI"], b["MCI"], atol=1e-9)     # offset-invariant
    assert np.allclose(a["FAI"], b["FAI"], atol=1e-9)
    raw = s2.compute_features(glinty, surface_correction=None)
    assert np.all(np.abs(raw["NDCI"]) < np.abs(a["NDCI"]))  # glint shrinks NDCI
    with pytest.raises(ValueError):
        s2.compute_features(clean, surface_correction="magic")


def test_hue_angle_orders_blue_green_brown_water():
    def spec(b1, b2, b3, b4, b5):
        r = _flat(0.0, shape=(1,))
        for k, v in zip(["B01", "B02", "B03", "B04", "B05"], [b1, b2, b3, b4, b5]):
            r[k] = np.array([v])
        return s2.compute_features(r, surface_correction=None)["HUE_ANGLE"][0]
    blue = spec(0.030, 0.028, 0.012, 0.002, 0.001)
    green = spec(0.010, 0.014, 0.020, 0.008, 0.004)
    brown = spec(0.010, 0.016, 0.040, 0.050, 0.030)
    # Van der Woerd & Wernand convention: the hue angle falls from blue
    # (~230 deg, Forel-Ule 1) through green (~100 deg) to brown (~20 deg, FU 21).
    assert blue > green > brown
    assert 180 < blue < 260 and 60 < green < 140 and 0 < brown < 80


def test_values_outside_valid_range_become_nan_not_clamped():
    r = _flat()
    r["B04"][:] = 0.0                                     # RE_RATIO undefined
    f = s2.compute_features(r, surface_correction=None)
    assert np.all(np.isnan(f["RE_RATIO"]))


# --------------------------------------------------------------------------- #
# Declarations
# --------------------------------------------------------------------------- #
def test_every_feature_declares_source_resolution_and_kind():
    for spec in s2.FEATURES.values():
        d = spec.to_dict()
        assert d["reference"] and d["formula"] and d["limitations"]
        assert d["native_resolution_m"] in (10, 20, 60)
        assert d["quantity_kind"] in s2.QUANTITY_KINDS
        assert d["locally_validated"] is False


def test_proxies_never_declare_concentration_units():
    for spec in s2.FEATURES.values():
        if spec.quantity_kind == "PROXY":
            assert spec.units in ("dimensionless", "reflectance")
            assert "mg" not in spec.units and "NTU" not in spec.units


def test_generic_calibrations_cite_their_coefficient_file():
    for spec in s2.FEATURES.values():
        if spec.quantity_kind == "GENERIC_CALIBRATION":
            assert "acolite" in spec.coefficient_source.lower()
            assert any("UAE" in lim for lim in spec.limitations)


def test_native_resolution_is_the_coarsest_band_used():
    assert s2.FEATURES["NDCI"].native_resolution_m == 20      # B05
    assert s2.FEATURES["HUE_ANGLE"].native_resolution_m == 60  # B01


# --------------------------------------------------------------------------- #
# Masks
# --------------------------------------------------------------------------- #
def test_glinty_water_is_kept_and_flagged_not_discarded():
    n = 30
    r = _flat(0.02, shape=(n, n))
    r["B03"][:] = 0.06
    r["B11"][:] = 0.037                               # typical Sen2Cor glint residual
    r["B12"][:] = 0.034
    r["B04"][:] = 0.045
    m, rep_ = s2.water_quality_mask(r, np.full((n, n), 6), pixel_size_m=20)
    d = rep_.to_dict()
    assert m.sum() > 0.5 * n * n
    assert d["glint_or_float_px"] == d["water_px"]


def test_water_mask_rejects_cloud_land_and_the_shoreline():
    n = 40
    r = _flat(0.02, shape=(n, n))
    r["B03"][:] = 0.05
    r["B11"][:] = 0.005                               # water everywhere...
    r["B11"][:, :10] = 0.25                           # ...except a land strip
    scl = np.full((n, n), 6)
    scl[30:, 30:] = 9                                 # cloud block
    m, rep = s2.water_quality_mask(r, scl, shoreline_buffer_m=40, pixel_size_m=20)
    assert not m[:, :10].any()                        # land
    assert not m[:, 10:12].any()                      # 2 px (40 m) shoreline buffer
    assert not m[30:, 30:].any()                      # cloud
    assert m[15, 20]                                  # open water kept
    assert rep.to_dict()["water_px"] == int(m.sum())


def test_scl_dark_area_and_vegetation_classes_are_not_auto_excluded():
    # Dense blooms and clear dark water are often mislabelled 2/4/5 by Sen2Cor.
    assert s2.scl_usable(np.array([2, 4, 5, 6, 7])).all()
    assert not s2.scl_usable(np.array([0, 1, 3, 8, 9, 10, 11])).any()


def test_hole_buffer_off_keeps_open_water_around_single_bad_pixels():
    n = 40
    r = _flat(0.02, shape=(n, n))
    r["B03"][:] = 0.05
    r["B11"][:] = 0.005
    r["B11"][:, :10] = 0.25                           # land strip
    r["B04"][20, 25] = -0.05                          # one over-corrected pixel in open water
    scl = np.full((n, n), 6)
    old, _ = s2.water_quality_mask(r, scl, shoreline_buffer_m=40, pixel_size_m=20)
    new, rep = s2.water_quality_mask(r, scl, shoreline_buffer_m=40, pixel_size_m=20, hole_buffer=False)
    assert not old[20, 27] and new[20, 27]            # no halo around the bad pixel
    assert not new[20, 25]                            # the bad pixel itself is still excluded
    assert not new[:, 10:12].any()                    # the shoreline buffer is unchanged
    assert rep.to_dict()["params"]["hole_buffer"] is False
