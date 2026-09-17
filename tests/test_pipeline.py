"""Tests for the BLUEBAN 813 pipeline.

These test the properties that would silently corrupt a result rather than
raise: band selection, units and scaling, no-data handling, mask polarity,
coordinate transforms, index bounds, uncertainty propagation, threshold
calibration, score bounds, and provenance completeness.

Run: python -m pytest tests -q
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import anomaly as AN            # noqa: E402
from pipeline import exposure as EX           # noqa: E402
from pipeline import export as XP             # noqa: E402
from pipeline import fingerprint as FP        # noqa: E402
from pipeline import forecast as FC           # noqa: E402
from pipeline import indices as IX            # noqa: E402
from pipeline import quality as Q             # noqa: E402
from pipeline import risk as RK               # noqa: E402
from pipeline import sampling as SM           # noqa: E402
from pipeline import sentinel2 as S2          # noqa: E402
from pipeline import spectral as SP           # noqa: E402
from pipeline import temporal as TP           # noqa: E402
from pipeline import water_mask as WM         # noqa: E402
from pipeline.provenance import (AlgorithmRecord, Provenance,  # noqa: E402
                                 SourceRecord)
from pipeline.satellite813 import (SensorSpec, gaussian_srf_matrix,  # noqa: E402
                                   resample_spectra, spec_813,
                                   spec_sentinel2, _runs_to_ranges)

TRANSFORM = (367950.0, 30.0, 0.0, 4102500.0, 0.0, -30.0)
EPSG = 32632


# --------------------------------------------------------------------------- #
# Band selection and spectral resampling
# --------------------------------------------------------------------------- #
def test_srf_rows_sum_to_one_where_supported():
    """A spectral response must conserve energy, or reflectance is rescaled."""
    src = np.arange(400.0, 900.0, 5.0)
    spec = SensorSpec("t", np.array([500.0, 700.0]), np.array([10.0, 10.0]), 20.0)
    W = gaussian_srf_matrix(src, spec)
    sums = W.sum(axis=1)
    assert np.allclose(sums[sums > 0], 1.0)


def test_resample_preserves_a_flat_spectrum():
    """Convolving a constant spectrum must return that constant."""
    src = np.arange(400.0, 900.0, 5.0)
    vals = np.full((3, src.size), 0.042)
    out, _ = resample_spectra(src, vals, spec_813())
    ok = np.isfinite(out)
    assert ok.any()
    assert np.allclose(out[ok], 0.042, atol=1e-5)


def test_resample_does_not_interpolate_across_a_gap():
    """A target band with no finite source support must be NaN, not invented.

    This is what keeps the 813 simulation honest across Tanager's water-vapour
    windows: interpolating there would fabricate the exact region where the
    atmosphere destroyed the signal.
    """
    src = np.arange(400.0, 900.0, 5.0)
    vals = np.full((1, src.size), 0.05)
    gap = (src >= 600) & (src <= 700)
    vals[:, gap] = np.nan
    spec = SensorSpec("t", np.array([650.0]), np.array([5.0]), 20.0)
    out, _ = resample_spectra(src, vals, spec)
    assert not np.isfinite(out[0, 0])


def test_813_spec_matches_published_numbers():
    s = spec_813()
    assert s.n_bands == 205
    assert math.isclose(s.centres_nm[0], 400.0)
    assert math.isclose(s.centres_nm[-1], 1700.0)
    assert s.spatial_resolution_m == 20.0


def test_sentinel2_spec_excludes_atmospheric_bands():
    """B9 (945 nm water vapour) and B10 (1375 nm cirrus) carry atmosphere."""
    c = spec_sentinel2().centres_nm
    assert not any(940 <= x <= 950 for x in c)
    assert not any(1370 <= x <= 1380 for x in c)


def test_bad_band_runs_are_contiguous_ranges():
    wl = np.arange(400.0, 500.0, 10.0)
    flag = np.array([False, True, True, False, False, True, False, False, False, False])
    runs = _runs_to_ranges(flag, wl)
    assert runs == [[410.0, 420.0, 2], [450.0, 450.0, 1]]


# --------------------------------------------------------------------------- #
# Water-informative band selection
# --------------------------------------------------------------------------- #
def test_informative_bands_exclude_nir_and_low_snr():
    wl = np.array([450.0, 550.0, 650.0, 950.0, 1600.0])
    snr = np.array([30.0, 30.0, 1.0, 30.0, 30.0])
    m = SP.water_informative_bands(wl, snr)
    assert list(m) == [True, True, False, False, False]


def test_band_snr_is_median_signal_over_sigma():
    cube = np.full((2, 4, 4), 0.02)
    unc = np.full((2, 4, 4), 0.002)
    mask = np.ones((4, 4), dtype=bool)
    snr = SP.band_snr(cube, unc, mask)
    assert np.allclose(snr, 10.0)


# --------------------------------------------------------------------------- #
# Band depth
# --------------------------------------------------------------------------- #
def test_local_band_depth_is_zero_on_a_straight_line():
    """No feature means no depth, whatever the slope."""
    wl = np.arange(600.0, 761.0, 5.0)
    spec = 0.05 - 0.0001 * (wl - 600.0)
    d = SP.local_band_depth(wl, spec, 650.0, 675.0, 715.0)
    assert abs(d) < 1e-6


def test_local_band_depth_detects_an_absorption():
    wl = np.arange(600.0, 761.0, 5.0)
    spec = np.full_like(wl, 0.05)
    spec[np.abs(wl - 675.0) <= 5.0] = 0.04      # a 20 % dip
    d = SP.local_band_depth(wl, spec, 650.0, 675.0, 715.0)
    assert 0.15 < d < 0.25


def test_local_band_depth_is_negative_for_a_peak():
    wl = np.arange(600.0, 761.0, 5.0)
    spec = np.full_like(wl, 0.05)
    spec[np.abs(wl - 675.0) <= 5.0] = 0.06
    assert SP.local_band_depth(wl, spec, 650.0, 675.0, 715.0) < 0


# --------------------------------------------------------------------------- #
# Indices: bounds and uncertainty
# --------------------------------------------------------------------------- #
def test_normalised_indices_stay_within_physical_bounds():
    rng = np.random.default_rng(0)
    a = rng.uniform(0.001, 0.2, 500)
    b = rng.uniform(0.001, 0.2, 500)
    for v in (IX.ndwi(a, b), IX.ndci(a, b), IX.turbidity_proxy(a, b)):
        assert np.all(v >= -1.0) and np.all(v <= 1.0)


def test_significance_mask_rejects_a_noise_floor_denominator():
    """The failure mode this guards against: division by noise over dark water."""
    a = np.array([0.0005, 0.05])
    b = np.array([-0.0004, 0.04])
    sa = np.array([0.0004, 0.0004])
    sb = np.array([0.0004, 0.0004])
    m = IX.significance_mask(a, b, sa, sb, k=3.0)
    assert m[0] == False     # noqa: E712 - denominator is at the noise floor
    assert m[1] == True      # noqa: E712


def test_uncertainty_propagation_matches_the_analytic_form():
    a, b, sa, sb = 0.05, 0.03, 0.001, 0.002
    nd, sig = IX.nd_with_uncertainty(np.array([a]), np.array([b]),
                                     np.array([sa]), np.array([sb]))
    expect = 2.0 * math.sqrt((b * sa) ** 2 + (a * sb) ** 2) / (a + b) ** 2
    assert math.isclose(sig[0], expect, rel_tol=1e-9)
    assert math.isclose(nd[0], (a - b) / (a + b), rel_tol=1e-9)


def test_guarded_indices_are_nan_where_insignificant():
    bands = {k: np.array([0.0005, 0.05]) for k in
             ("green", "red", "red_edge", "nir", "swir1")}
    bands["red"] = np.array([-0.0004, 0.04])
    sig = {k: np.full(2, 0.0004) for k in bands}
    vals, uncs, masks = IX.compute_all_with_uncertainty(bands, sig, k=3.0)
    assert not np.isfinite(vals["NDCI"][0])
    assert np.isfinite(vals["NDCI"][1])


def test_clip_to_valid_uses_nan_not_clamping():
    """Clamping hides a processing fault; NaN surfaces it."""
    out = IX.clip_to_valid("NDWI", np.array([-2.0, 0.3, 2.0]))
    assert not np.isfinite(out[0]) and not np.isfinite(out[2])
    assert out[1] == 0.3


def test_every_index_declares_its_units_and_source():
    for name, spec in IX.ALL_SPECS.items():
        assert spec.reference, f"{name} has no citation"
        assert spec.units_out, f"{name} has no output units"
        assert spec.input_quantity, f"{name} does not declare its input quantity"
        assert spec.wavelengths_nm, f"{name} does not declare its wavelengths"


def test_proxy_indices_never_claim_physical_units():
    """A proxy must declare itself dimensionless and explicitly disclaim units.

    The unit strings deliberately name NTU and mg/m3 in order to say they are
    NOT that, so this asserts on the claim rather than on the substring.
    """
    for name in ("NDCI", "TURBIDITY_PROXY"):
        u = IX.ALL_SPECS[name].units_out.lower()
        assert "dimensionless" in u, f"{name} does not declare dimensionlessness"
        assert "not" in u, f"{name} does not disclaim a physical unit"
        # And the assumptions must say a calibration is still required.
        joined = " ".join(IX.ALL_SPECS[name].assumptions).lower()
        assert "calibrat" in joined, f"{name} does not state it needs calibration"


# --------------------------------------------------------------------------- #
# Quality and masking
# --------------------------------------------------------------------------- #
def test_mask_polarity_true_means_usable():
    ok, rep = Q.sunglint_mask(np.array([0.01, 0.20]), threshold=0.05)
    assert ok[0] == True and ok[1] == False      # noqa: E712
    assert rep.kept == 1 and rep.removed == 1


def test_uncertainty_mask_rejects_sigma_above_signal():
    ok, _ = Q.uncertainty_mask(np.array([0.01, 0.001]),
                               np.array([0.002, 0.005]), max_ratio=1.0)
    assert ok[0] == True and ok[1] == False      # noqa: E712


def test_mask_report_fractions_are_consistent():
    ok, rep = Q.sunglint_mask(np.array([0.01, 0.01, 0.9, 0.9]), 0.05)
    assert rep.total == 4
    assert rep.kept + rep.removed == rep.total
    assert math.isclose(rep.kept_fraction, 0.5)


def test_water_mask_erodes_the_shoreline():
    g = np.zeros((20, 20)); s = np.zeros((20, 20)); n = np.zeros((20, 20))
    g[5:15, 5:15] = 0.03
    valid = np.ones((20, 20), dtype=bool)
    r = WM.water_mask(g, s, n, valid, min_component_px=4, shoreline_buffer_px=1)
    assert r.raw_mask.sum() == 100
    assert r.mask.sum() == 64            # a one-pixel ring removed
    assert r.stats["shoreline_px_removed"] == 36


def test_offshore_background_requires_distance_from_land():
    water = np.zeros((30, 30), dtype=bool)
    water[5:25, 5:25] = True
    off = WM.offshore_background(water, min_distance_px=8)
    assert off.sum() > 0
    assert off.sum() < water.sum()
    assert not off[5, 5]                  # a corner pixel is not offshore


def test_sentinel2_harmonisation_applies_the_baseline_offset():
    """Ignoring the 04.00 offset silently mixes two radiometric scales."""
    raw = np.array([[2000.0]])
    before = S2.harmonize(raw.copy(), "2021-06-01")
    after = S2.harmonize(raw.copy(), "2023-06-01")
    # Values are float32, so compare at single precision.
    assert math.isclose(float(before[0, 0]), 0.2, rel_tol=1e-6)
    assert math.isclose(float(after[0, 0]), 0.1, rel_tol=1e-6)


def test_sentinel2_zero_is_nodata_not_zero_reflectance():
    out = S2.harmonize(np.array([[0.0]]), "2021-06-01")
    assert not np.isfinite(out[0, 0])


def test_scl_masks_reject_cloud_and_accept_water():
    scl = np.array([[6, 9, 4, 3]])
    usable, water = S2.scl_masks(scl)
    assert list(usable[0]) == [True, False, True, False]
    assert list(water[0]) == [True, False, False, False]


# --------------------------------------------------------------------------- #
# Anomaly detection
# --------------------------------------------------------------------------- #
def test_rx_scores_a_planted_anomaly_above_background():
    rng = np.random.default_rng(3)
    cube = rng.normal(0.02, 0.001, (12, 40, 40)).astype("float32")
    cube[:, 20:23, 20:23] += 0.03
    water = np.ones((40, 40), dtype=bool)
    res = AN.rx_anomaly(cube, water, water, n_components=5, alpha=0.01)
    assert np.nanmean(res.score[20:23, 20:23]) > 10 * np.nanmedian(res.score)


def test_rx_reports_both_thresholds_and_uses_the_empirical_one():
    rng = np.random.default_rng(4)
    cube = rng.normal(0.02, 0.001, (10, 30, 30)).astype("float32")
    water = np.ones((30, 30), dtype=bool)
    res = AN.rx_anomaly(cube, water, water, n_components=4, alpha=0.01)
    assert res.params["threshold_rule"].startswith("empirical")
    assert res.params["threshold_chi2_nominal"] is not None
    # params carries the value rounded for the JSON payload.
    assert math.isclose(res.threshold_score, res.params["threshold_empirical"],
                        rel_tol=1e-4)


def test_extract_events_drops_speckle_and_reports_area():
    score = np.zeros((40, 40)); score[10:20, 10:20] = 100.0
    score[0, 0] = 100.0                   # a single-pixel speck
    p = np.zeros((40, 40))
    lab, regions = AN.extract_events(score, p, 50.0, 30.0, min_pixels=25)
    assert len(regions) == 1
    assert math.isclose(regions[0].area_km2, 100 * 900 / 1e6)
    assert lab[0, 0] == 0


def test_spectral_angle_is_zero_for_parallel_spectra():
    a = np.array([[0.1, 0.2, 0.3]])
    assert SP.spectral_angle(a, a * 3.0, axis=1)[0] < 1e-6


# --------------------------------------------------------------------------- #
# Fingerprinting
# --------------------------------------------------------------------------- #
def test_fingerprint_returns_background_for_identical_spectra():
    wl = np.arange(400.0, 900.0, 5.0)
    bg = 0.06 * np.exp(-(wl - 400.0) / 300.0)
    fp = FP.fingerprint_spectrum(wl, bg.copy(), bg, 1500.0, 0.0)
    assert fp.top_class == "BACKGROUND_WATER"


def test_fingerprint_calls_a_red_tilted_enhancement_sediment():
    wl = np.arange(400.0, 900.0, 5.0)
    bg = 0.06 * np.exp(-(wl - 400.0) / 300.0)
    ev = bg.copy()
    ev[wl >= 500] *= 4.0                  # broadband, red-weighted
    fp = FP.fingerprint_spectrum(wl, ev, bg, 1500.0, 0.0)
    assert fp.scores["SEDIMENT_LIKE"] > fp.scores["BLOOM_LIKE"]


def test_fingerprint_always_carries_its_disclaimer():
    wl = np.arange(400.0, 900.0, 5.0)
    bg = np.full_like(wl, 0.02)
    d = FP.fingerprint_spectrum(wl, bg.copy(), bg).to_dict()
    assert "NOT a chemical" in d["disclaimer"]
    for cls in FP.CLASSES.values():
        assert cls["optical_definition"]


def test_nearshore_pixels_get_a_bottom_influence_caveat():
    wl = np.arange(400.0, 900.0, 5.0)
    bg = np.full_like(wl, 0.02)
    fp = FP.fingerprint_spectrum(wl, bg * 2, bg, distance_from_shore_m=50.0)
    assert any("Bottom reflectance" in c for c in fp.caveats)


# --------------------------------------------------------------------------- #
# Temporal statistics
# --------------------------------------------------------------------------- #
def test_percentile_of_is_monotonic_and_bounded():
    h = np.arange(100.0)
    assert TP.percentile_of(-1.0, h) == 0.0
    assert TP.percentile_of(200.0, h) == 100.0
    assert 45 <= TP.percentile_of(50.0, h) <= 55


def test_seasonal_percentile_restricts_to_the_same_season():
    dates, vals = [], []
    for y in range(2019, 2025):
        dates += [f"{y}-01-15", f"{y}-07-15"]
        vals += [0.1, 0.9]                # winter low, summer high
    out = TP.seasonal_percentile(0.9, vals, dates, "2025-07-15", window_days=45)
    assert out["n_seasonal"] == 6
    # 0.9 is typical for summer, so it must not read as an extreme.
    assert out["seasonal_percentile"] < 60
    # Against the full record it would look high, which is the point.
    assert out["all_time_percentile"] > 40


def test_classify_state_thresholds():
    assert TP.classify_state(10.0) == "NORMAL"
    assert TP.classify_state(92.0) == "WATCH"
    assert TP.classify_state(96.0) == "INVESTIGATE"
    assert TP.classify_state(99.0) == "HIGH_PRIORITY"
    assert TP.classify_state(None) == "UNKNOWN"


def test_trend_recovers_a_known_slope():
    dates = [f"20{y:02d}-01-01" for y in range(10, 20)]
    vals = [1.0 + 0.5 * i for i in range(10)]
    t = TP.trend(vals, dates)
    assert math.isclose(t["slope_per_year"], 0.5, rel_tol=0.02)
    assert t["r_squared"] > 0.99


# --------------------------------------------------------------------------- #
# Risk: bounds, separation and the veto
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("area,anom,mag,hist", [
    (0.0, 0.0, 1.0, 0.0), (1e6, 100.0, 1e6, 100.0), (1.0, 50.0, 2.0, 50.0),
])
def test_severity_is_bounded(area, anom, mag, hist):
    s, _ = RK.severity(area, anom, mag, hist)
    assert 0.0 <= s <= 1.0


def test_confidence_is_bounded_and_capped_without_in_situ():
    c, _ = RK.confidence(1.0, 0.0, 10 ** 9, 1000.0, 1.0, 1.0, 0.0,
                         has_in_situ=False, bottom_influence_risk=0.0)
    assert 0.0 <= c <= 1.0
    capped, notes = RK.apply_caps(c, has_in_situ=False)
    assert capped <= RK.NO_IN_SITU_CAP
    assert notes


def test_severity_and_confidence_are_independent():
    """They must never be combined: the same product hides opposite situations."""
    s1, _ = RK.severity(5.0, 99.0, 5.0, 99.0)
    c1, _ = RK.confidence(0.2, 0.7, 20, 3.0, 0.05)
    s2, _ = RK.severity(0.1, 10.0, 1.1, 5.0)
    c2, _ = RK.confidence(1.0, 0.0, 5000, 30.0, 0.9)
    assert s1 > s2 and c1 < c2


def test_low_confidence_raises_priority_when_severity_is_high():
    hi, _, _ = RK.priority(0.6, 0.9, 0.1, None)
    lo, _, _ = RK.priority(0.6, 0.2, 0.1, None)
    order = RK.PRIORITY_LEVELS
    assert order.index(lo) >= order.index(hi)


def test_temporal_veto_caps_priority_and_explains_itself():
    lvl_no, _, _ = RK.priority(0.7, 0.7, 0.45, 6.0, historical_percentile=None)
    lvl_veto, reason, fired = RK.priority(0.7, 0.7, 0.45, 6.0,
                                          historical_percentile=6.6)
    assert lvl_no == "HIGH_PRIORITY"
    assert RK.PRIORITY_LEVELS.index(lvl_veto) < RK.PRIORITY_LEVELS.index(lvl_no)
    assert "TEMPORAL VETO" in reason
    assert any(f.get("veto") for f in fired)


def test_high_percentile_does_not_trigger_the_veto():
    lvl, _, _ = RK.priority(0.7, 0.7, 0.45, 6.0, historical_percentile=97.0)
    assert lvl == "HIGH_PRIORITY"


def test_every_priority_decision_is_auditable():
    a = RK.assess_event(1.0, 95.0, 3.0, 96.0, 0.9, 0.01, 500, 25.0, 0.6,
                        max_exposure=0.5, eta_hours=12.0)
    assert a.priority in RK.PRIORITY_LEVELS
    assert a.rules_fired
    assert a.priority_reason
    for c in a.severity_components + a.confidence_components:
        assert c.description


# --------------------------------------------------------------------------- #
# Exposure geometry
# --------------------------------------------------------------------------- #
def test_haversine_against_a_known_separation():
    d = EX.haversine_m(0.0, 0.0, 0.0, 1.0)
    assert abs(d - 111195.0) < 300.0


def test_bearing_and_compass_cardinals():
    assert abs(EX.bearing_deg(0, 0, 0, 1) - 0.0) < 0.5      # due north
    assert abs(EX.bearing_deg(0, 0, 1, 0) - 90.0) < 0.5     # due east
    assert EX.compass(0) == "N" and EX.compass(90) == "E"
    assert EX.compass(180) == "S" and EX.compass(270) == "W"


def test_exposure_is_bounded_and_falls_with_distance():
    near = EX.assess(EX.Asset("a", "n", "PORT", 7.77, 36.90), 7.77, 36.89)
    far = EX.assess(EX.Asset("b", "f", "PORT", 7.77, 37.05), 7.77, 36.89)
    assert 0.0 <= far.exposure_score <= near.exposure_score <= 1.0
    assert near.basis


def test_unknown_asset_type_falls_back_to_custom():
    a = EX.Asset("x", "x", "NOT_A_REAL_TYPE", 0.0, 0.0)
    assert a.type == "CUSTOM"
    assert a.sensitivity == EX.ASSET_TYPES["CUSTOM"]["default_sensitivity"]


def test_geojson_and_csv_asset_loaders_agree():
    gj = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [7.7, 36.9]},
        "properties": {"id": "A1", "name": "X", "type": "PORT"}}]}
    csv = "id,name,type,lat,lon\nA1,X,PORT,36.9,7.7\n"
    a, b = EX.from_geojson(gj)[0], EX.from_csv(csv)[0]
    assert (a.id, a.name, a.type) == (b.id, b.name, b.type)
    assert math.isclose(a.lon, b.lon) and math.isclose(a.lat, b.lat)


def test_real_asset_register_is_loadable_and_cites_osm():
    path = os.path.join("config", "assets.geojson")
    if not os.path.exists(path):
        pytest.skip("asset register not present")
    gj = json.load(open(path, encoding="utf-8"))
    assets = EX.from_geojson(gj)
    assert len(assets) >= 1
    for f in gj["features"]:
        assert f["properties"].get("osm"), "every asset must cite its OSM element"
    assert "OpenStreetMap" in gj["properties"]["source"]


# --------------------------------------------------------------------------- #
# Forecast
# --------------------------------------------------------------------------- #
def test_wind_direction_convention_is_from_not_toward():
    """Meteorological direction is where wind comes FROM. Getting this backwards
    sends every plume 180 degrees wrong."""
    # A northerly (from 0 deg) must push southward: v negative.
    u, v = FC.surface_drift(-0.0, -10.0, factor=1.0, deflection_deg=0.0)
    assert v < 0 and abs(u) < 1e-9


def test_surface_drift_scales_and_deflects():
    u, v = FC.surface_drift(10.0, 0.0, factor=0.03, deflection_deg=0.0)
    assert math.isclose(math.hypot(u, v), 0.3, rel_tol=1e-6)
    u2, v2 = FC.surface_drift(10.0, 0.0, factor=0.03, deflection_deg=90.0)
    assert v2 < 0 and abs(u2) < 1e-6      # rotated clockwise


def test_advection_step_displaces_in_the_drift_direction():
    wind = FC.WindSeries(times=[f"2025-06-01T{h:02d}:00" for h in range(24)],
                         u=np.full(24, 10.0), v=np.zeros(24),
                         speed=np.full(24, 10.0), direction_from=np.full(24, 270.0),
                         source="test", latitude=36.9, longitude=7.7)
    steps = FC.advect([7.70], [36.90], wind, 0, horizons_h=(0, 6),
                      diffusivity=0.0)
    assert steps[-1].centroid_lon > steps[0].centroid_lon   # eastward
    assert steps[-1].displacement_m > 0


def test_beaching_stops_particles_at_the_coastline():
    """Without this an onshore wind puts a forecast plume over a town."""
    water = np.zeros((40, 40), dtype=bool)
    water[:, :20] = True                   # water west, land east
    dom = FC.WaterDomain(water, TRANSFORM, EPSG)
    wind = FC.WindSeries(times=[f"2025-06-01T{h:02d}:00" for h in range(48)],
                         u=np.full(48, 30.0), v=np.zeros(48),
                         speed=np.full(48, 30.0), direction_from=np.full(48, 270.0),
                         source="test", latitude=37.0, longitude=7.6)
    x0, dx, _, y0, _, dy = TRANSFORM
    from pyproj import Transformer
    tr = Transformer.from_crs(f"EPSG:{EPSG}", "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(x0 + 10 * dx, y0 + 20 * dy)
    steps = FC.advect([lon] * 20, [lat] * 20, wind, 0, horizons_h=(0, 24),
                      diffusivity=0.0, domain=dom)
    assert steps[-1].beached_fraction > 0.5


def test_forecast_metadata_never_claims_to_be_hydrodynamic():
    wind = FC.WindSeries(["2025-06-01T00:00"], np.array([1.0]), np.array([1.0]),
                         np.array([1.4]), np.array([225.0]), "test", 0.0, 0.0)
    md = FC.forecast_metadata(wind, 0)
    assert md["is_hydrodynamic_model"] is False
    assert md["not_included"]
    assert "not validated" in md["validation_status"].lower()


# --------------------------------------------------------------------------- #
# Sampling
# --------------------------------------------------------------------------- #
def test_sampling_plan_always_includes_a_background_control():
    """An absolute laboratory value is uninterpretable without a same-day control."""
    score = np.full((60, 60), 5.0)
    score[10:20, 10:20] = 5000.0
    water = np.ones((60, 60), dtype=bool)
    event = np.zeros((60, 60), dtype=bool); event[10:20, 10:20] = True
    dist = np.full((60, 60), 2000.0)
    pts = SM.plan(score, water, event, TRANSFORM, EPSG,
                  distance_from_shore_m=dist, max_points=6)
    roles = {p.role for p in pts}
    assert "EVENT_CORE" in roles
    assert "BACKGROUND_CONTROL" in roles


def test_sample_points_respect_minimum_separation():
    score = np.full((60, 60), 5.0); score[10:20, 10:20] = 5000.0
    water = np.ones((60, 60), dtype=bool)
    event = np.zeros((60, 60), dtype=bool); event[10:20, 10:20] = True
    pts = SM.plan(score, water, event, TRANSFORM, EPSG,
                  distance_from_shore_m=np.full((60, 60), 2000.0),
                  min_separation_m=400.0, max_points=6)
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            assert EX.haversine_m(a.lon, a.lat, b.lon, b.lat) >= 399.0


def test_every_sample_point_states_its_question_and_analytes():
    score = np.full((40, 40), 5.0); score[5:15, 5:15] = 900.0
    water = np.ones((40, 40), dtype=bool)
    event = np.zeros((40, 40), dtype=bool); event[5:15, 5:15] = True
    pts = SM.plan(score, water, event, TRANSFORM, EPSG,
                  distance_from_shore_m=np.full((40, 40), 2000.0))
    for p in pts:
        assert p.rationale and p.expected_variables
        assert SM.ROLES[p.role]["question"]


def test_sampling_exports_are_wellformed():
    score = np.full((40, 40), 5.0); score[5:15, 5:15] = 900.0
    water = np.ones((40, 40), dtype=bool)
    event = np.zeros((40, 40), dtype=bool); event[5:15, 5:15] = True
    pts = SM.plan(score, water, event, TRANSFORM, EPSG,
                  distance_from_shore_m=np.full((40, 40), 2000.0))
    gj = SM.to_geojson(pts)
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == len(pts)
    for f in gj["features"]:
        lon, lat = f["geometry"]["coordinates"]
        assert -180 <= lon <= 180 and -90 <= lat <= 90
    csv = SM.to_csv(pts)
    assert csv.splitlines()[0].startswith("id,role,lat,lon")
    assert len(csv.splitlines()) == len(pts) + 1


# --------------------------------------------------------------------------- #
# Coordinate transforms and export
# --------------------------------------------------------------------------- #
def test_grid_to_lonlat_lands_in_the_expected_region():
    lon, lat = XP.grid_to_lonlat([0], [0], TRANSFORM, EPSG)
    assert 7.4 < float(np.atleast_1d(lon)[0]) < 7.7
    assert 36.9 < float(np.atleast_1d(lat)[0]) < 37.2


def test_bounds_walk_the_whole_perimeter():
    """Sampling only the corners understates a rotated or projected extent."""
    b = XP.bounds_lonlat((697, 871), TRANSFORM, EPSG)
    assert b[0] < b[2] and b[1] < b[3]
    lon, lat = XP.grid_to_lonlat([348], [435], TRANSFORM, EPSG)
    assert b[0] <= float(np.atleast_1d(lon)[0]) <= b[2]
    assert b[1] <= float(np.atleast_1d(lat)[0]) <= b[3]


def test_stretch_is_bounded():
    out, (lo, hi) = XP.stretch(np.array([0.0, 0.5, 1.0, 100.0]))
    assert np.all(out >= 0) and np.all(out <= 1)
    assert lo < hi


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
def _full_source():
    return SourceRecord(
        satellite="Tanager-1", sensor="HYP", scene_id="s", acquisition_utc="t",
        product="ortho_sr_hdf5", processing_level="L2 SR", provider="Planet",
        licence="CC-BY-4.0", units="unitless")


def test_provenance_completeness_reaches_one_when_complete():
    p = Provenance(result_id="r", result_kind="k")
    p.add_source(_full_source())
    p.algorithm = AlgorithmRecord(name="n", description="d")
    c, missing = p.completeness()
    assert c == 1.0 and missing == []


def test_provenance_names_what_is_missing():
    p = Provenance(result_id="r", result_kind="k")
    p.add_source(SourceRecord(satellite="X", sensor="", scene_id="", acquisition_utc="",
                              product="", processing_level="", provider="", licence=""))
    c, missing = p.completeness()
    assert c < 1.0
    assert any("licence" in m for m in missing)
    assert any("algorithm" in m for m in missing)


def test_provenance_with_no_sources_is_flagged():
    c, missing = Provenance(result_id="r", result_kind="k").completeness()
    assert c < 1.0
    assert any("sources" in m for m in missing)


def test_provenance_serialises():
    p = Provenance(result_id="r", result_kind="k")
    p.add_source(_full_source())
    p.algorithm = AlgorithmRecord(name="n", description="d")
    d = p.to_dict()
    json.dumps(d)                     # must be JSON-serialisable
    assert d["sources"][0]["licence"] == "CC-BY-4.0"
    assert d["code_version"]


# --------------------------------------------------------------------------- #
# The built event, when it exists
# --------------------------------------------------------------------------- #
def _event():
    idx = os.path.join("outputs", "events", "index.json")
    if not os.path.exists(idx):
        pytest.skip("pipeline outputs not built")
    eid = json.load(open(idx, encoding="utf-8"))["events"][0]["event_id"]
    return json.load(open(os.path.join("outputs", "events", f"{eid}.json"),
                          encoding="utf-8"))


def test_built_event_scores_are_in_range():
    e = _event()
    assert 0.0 <= e["severity"] <= 1.0
    assert 0.0 <= e["confidence"] <= 1.0
    assert e["state"] in RK.PRIORITY_LEVELS
    for x in e["exposure"]:
        assert 0.0 <= x["exposure_score"] <= 1.0


def test_built_event_never_reports_a_concentration():
    """No in-situ data exists for this AOI, so nothing may be reported in
    physical concentration units.

    Checked structurally rather than by substring: every index carried in the
    event must declare dimensionless output and disclaim a physical unit. The
    only place a physical unit may legitimately appear is in the units field of
    an external reference product (OLCI stores log10 mg/m3), which is a
    description of someone else's data, not a value we are claiming.
    """
    e = _event()
    for name, d in e["indices"].items():
        spec = d.get("spec")
        if not spec:
            continue
        u = (spec.get("units_out") or "").lower()
        assert "dimensionless" in u or "unitless" in u or "reflectance" in u, (
            f"index {name} reports units '{u}', which reads as a physical "
            f"quantity; no in-situ calibration exists for this AOI")

    # And no event field may be named as a concentration.
    for key in json.dumps(e).lower().split('"'):
        assert not key.endswith("_mg_m3")
        assert not key.endswith("_ntu")


def test_built_event_declares_813_as_simulated():
    e = _event()
    assert e["satellite_813"]["status"] == "SIMULATED"
    assert "No real Satellite 813 data" in e["satellite_813"]["warning"]


def test_built_event_provenance_is_complete():
    e = _event()
    assert e["provenance_summary"]["completeness"] == 1.0
    assert e["provenance_summary"]["missing_fields"] == []
    assert e["provenance_summary"]["n_sources"] >= 4


def test_built_event_confidence_respects_the_no_in_situ_cap():
    e = _event()
    assert e["confidence"] <= RK.NO_IN_SITU_CAP + 1e-9


def test_built_event_indices_are_physically_bounded():
    e = _event()
    for name, d in e["indices"].items():
        if name == "FAI":
            continue
        for k in ("event_median", "background_median", "event_p95"):
            assert -1.0 <= d[k] <= 1.0, f"{name}.{k} = {d[k]} out of range"
