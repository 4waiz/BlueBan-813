"""Build the public inland summary for Shawka Dam from the precomputed outputs.

    python scripts/inland/build_inland_bundle.py

Reads the teammate's already-computed, already-validated outputs in data/inland/
(nothing in pipeline/inland/ is executed) and writes:

    outputs/inland/summary.json     one compact file the API (/api/inland/summary)
                                    and the static site (/inland) serve
    docs/inland/REVIEW_FLAGS.md     the integration review: what looks off, with
                                    evidence; flagged, not fixed

What the public summary deliberately leaves out: per-pixel EnMAP reflectance
(the brightness / darkness layers, band-group means, simulated 813 spectra).
EnMAP's licence is "proprietary" and its redistribution terms are not yet
confirmed for public submission, so those stay in data/inland/restricted/
(gitignored). Derived classifications, scores, counts and sensor metadata are
included. If the restricted folder is absent (a fresh clone), the summary is
still built; the few counts that come from it are marked unavailable.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from pipeline.inland.satellite813 import spec_813  # noqa: E402

DATA = os.path.join(ROOT, "data", "inland")
RESTRICTED = os.path.join(DATA, "restricted")
OUT = os.path.join(ROOT, "outputs", "inland", "summary.json")
FLAGS_MD = os.path.join(ROOT, "docs", "inland", "REVIEW_FLAGS.md")

# Carried over exactly from the integration brief; never paraphrased.
CAVEATS = [
    'EnMAP\'s license is "proprietary" with redistribution terms not yet confirmed for public submission',
    "the anomaly/fingerprint results are based on a ~10-17 pixel background population, not a calibrated detector",
]
ATTRIBUTION = "Contains modified EnMAP data © DLR (2022, 2024)"
DATES = ("2022-09-08", "2024-04-24")
BUFFER_M = 150.0      # scripts/inland/crop_enmap_scene.py


def jl(*parts):
    p = os.path.join(*parts)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def rc(mask: np.ndarray) -> list:
    return [[int(r), int(c)] for r, c in zip(*np.nonzero(mask))]


# --------------------------------------------------------------------------- geometry
def window_geometry(poly_lonlat: list, live: dict) -> dict:
    """Reconstruct the 25 x 30 crop window from the scene grid and the locked polygon.

    The package ships the masks but not the window transform. Both scenes sit on
    the same 30 m UTM 40N lattice (origins = 15 m mod 30, from DLR's STAC), and
    the crop rule is documented (polygon bbox + 150 m, scripts/inland/
    crop_enmap_scene.py), so the window can be rebuilt and checked against the
    reported 84 pixels inside the polygon.
    """
    from matplotlib.path import Path
    from rasterio.transform import Affine
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
    from pyproj import Transformer

    item = live["items"]["2024-04-24"]
    a, b, x0, d, e, y0 = item["proj:transform"]
    T = Affine(a, b, x0, d, e, y0)
    lons, lats = [p[0] for p in poly_lonlat], [p[1] for p in poly_lonlat]
    left, bottom, right, top = transform_bounds("EPSG:4326", f"EPSG:{item['proj:epsg']}",
                                                min(lons), min(lats), max(lons), max(lats))
    win = from_bounds(left - BUFFER_M, bottom - BUFFER_M, right + BUFFER_M, top + BUFFER_M,
                      transform=T).round_offsets().round_lengths()
    wx0, wy0 = x0 + win.col_off * a, y0 + win.row_off * e
    tr = Transformer.from_crs(4326, item["proj:epsg"], always_xy=True)
    xs, ys = tr.transform(lons, lats)
    px = [[(x - wx0) / a, (y - wy0) / e] for x, y in zip(xs, ys)]          # [col, row], fractional
    path = Path(px)
    h, w = int(win.height), int(win.width)
    centres = [(c + 0.5, r + 0.5) for r in range(h) for c in range(w)]
    inside = np.array(path.contains_points(centres)).reshape(h, w)
    area = 0.5 * abs(sum(xs[i] * ys[i + 1] - xs[i + 1] * ys[i] for i in range(len(xs) - 1)))
    return {
        "shape": [h, w], "resolution_m": a, "epsg": item["proj:epsg"],
        "transform": [a, b, wx0, d, e, wy0], "col_off": int(win.col_off), "row_off": int(win.row_off),
        "polygon_px": [[round(c, 3), round(r, 3)] for c, r in px],
        "inside_polygon_px": rc(inside), "n_inside_reconstructed": int(inside.sum()),
        "polygon_size_m": [round(max(xs) - min(xs)), round(max(ys) - min(ys))],
        "polygon_area_m2": round(area),
        "method": ("Reconstructed: DLR STAC scene grid (both dates on the same 30 m lattice) + the documented "
                   "crop rule (polygon bbox + 150 m). The package does not ship the window transform."),
    }


# --------------------------------------------------------------------------- sections
def masks_section(geom: dict) -> dict:
    wm = os.path.join(DATA, "water_mask")
    s22, s24 = jl(wm, "enmap_20220908_derivation_stats.json"), jl(wm, "enmap_20240424_derivation_stats.json")
    core, cmp_ = jl(wm, "persistent_wet_core_derivation_stats.json"), jl(wm, "persistent_wet_core_mndwi_comparison.json")
    inside = {tuple(p) for p in geom["inside_polygon_px"]}

    def entry(fn, label, method, stats):
        m = np.load(os.path.join(wm, fn))
        px = rc(m)
        return {"label": label, "method": method, "px": px, "n": len(px),
                "n_inside_reconstructed_polygon": sum(tuple(p) in inside for p in px),
                "wet_fraction_of_polygon_pct": stats.get("wet_fraction_of_polygon_pct") if stats else None,
                "source": f"data/inland/water_mask/{fn}"}
    return {
        "2022-09-08": entry("enmap_20220908_mask.npy", "EnMAP 2022-09-08, single date",
                            "brightness < 0.11 and short/long index >= 0 (v1 thresholds)", s22),
        "2024-04-24": entry("enmap_20240424_mask.npy", "EnMAP 2024-04-24, single date (same unchanged thresholds)",
                            "brightness < 0.11 and short/long index >= 0 (v1 thresholds)", s24),
        "persistent_core": entry("persistent_wet_core_mask.npy", "Persistent wet core (both dates)",
                                 "max broadband reflectance across both dates < 0.10 (two-date persistence)", core),
        "mndwi_core": entry("persistent_wet_core_mndwi_mask.npy", "MNDWI cross-check (both dates)",
                            f"real MNDWI from B{561.112:.0f}/{1609.02:.0f} nm, persistent across both dates", {"wet_fraction_of_polygon_pct": 0.0}),
        "px_inside_locked_polygon_reported": core.get("px_inside_locked_polygon"),
        "threshold_sweep_persistent_core": core.get("threshold_sweep"),
        "mndwi_threshold_sweep": cmp_.get("mndwi_threshold_sweep"),
        "bad_bands_dropped_per_date": core.get("bad_bands_dropped_per_date"),
    }


def anomaly_section() -> dict:
    prov = jl(DATA, "anomaly", "provenance_anomaly_fingerprint.json") or {}
    rep = jl(RESTRICTED, "anomaly", "anomaly_fingerprint_report.json")
    out = {"available": rep is not None, "provenance": "data/inland/anomaly/provenance_anomaly_fingerprint.json",
           "method": "RX / Mahalanobis in PCA-of-band-group-means space (inland adaptation, Reed & Yu 1990) + rule-based fingerprint scores",
           "algorithm_parameters": (prov.get("algorithm") or {}).get("parameters")}
    if rep is None:
        out["note"] = "Restricted report not present in this checkout; scores unavailable."
        return out
    out.update({k: rep[k] for k in ("background_d620_mean", "background_d620_std", "background_d620_n",
                                     "test_mask_px", "background_mask_px", "background_is_superset_of_test", "n_groups")})
    out["per_date"] = {}
    for date, d in rep["per_date"].items():
        ar = d["anomaly_result"]
        px = []
        for p in d["pixel_fingerprints"]:      # group_values (band-group reflectance) are NOT published
            fp = p.get("fingerprint") or {}
            px.append({"row": p["row"], "col": p["col"], "rx_score": round(p["rx_score"], 4),
                       "rx_threshold": round(p["rx_threshold"], 4), "sam_rad": round(p["sam_rad"], 4),
                       "d620": p.get("d620_this_pixel"), "top_class": fp.get("top_class"),
                       "label": fp.get("label"), "scores": fp.get("scores")})
        out["per_date"][date] = {
            "test_pixels": ar["test_pixels"], "background_pixels": ar["background_pixels"],
            "threshold_score": ar["threshold_score"], "n_components": ar["n_components"],
            "explained_variance": ar["explained_variance"], "n_events": len(d["events"]),
            "fingerprint_top_class_counts": d["fingerprint_top_class_counts"],
            "small_sample_caveat": (ar.get("params") or {}).get("small_sample_caveat"),
            "pixels": px}
    return out


def temporal_section() -> dict:
    t = jl(DATA, "temporal", "temporal_deviations.json")
    zt = t["z_threshold"]
    p1 = math.erfc(zt / math.sqrt(2))                  # two-sided P(|z| > zt) for one Gaussian index
    k = 4
    n = len(t["deviations"])
    obs = [{"datetime": dv["datetime"], "date": dv["datetime"][:10], "sensor": dv["collection"],
            "item_id": dv["item_id"], "z": dv["z_scores"], "max_abs_z": dv["max_abs_z"],
            "flagged": dv["flagged"], "flagged_index": dv["flagged_index"]} for dv in t["deviations"]]
    return {
        "z_threshold": zt, "n_observations": n, "n_flagged": t["n_flagged"],
        "per_sensor_n": t["per_sensor_n"], "per_sensor_mean": t["per_sensor_mean"], "per_sensor_std": t["per_sensor_std"],
        "observations": sorted(obs, key=lambda o: o["datetime"]),
        "enmap_date_context": t["enmap_date_context"],
        "chance_level": {
            "p_one_index": round(p1, 4), "n_indices": k,
            "expected_flags_if_indices_perfectly_correlated": round(n * p1, 1),
            "expected_flags_if_indices_independent": round(n * (1 - (1 - p1) ** k), 1),
            "note": ("BLUEBAN review note: with |z| > 1.5 on any of 4 indices, pure Gaussian noise alone flags "
                     "between these two counts of 28 observations, so the 7 flags are within chance; the "
                     "cross-sensor Sep-Oct 2025 cluster is the part worth reading."),
        },
        "source": "data/inland/temporal/temporal_deviations.json",
    }


def baseline_section() -> dict:
    rows = list(csv.DictReader(open(os.path.join(DATA, "baseline_indices_s2_landsat.csv"), encoding="utf-8")))
    f = lambda v: float(v) if v not in ("", None) else None
    keep = [{"date": r["datetime"][:10], "sensor": r["collection"], "item_id": r["item_id"],
             "cloud_frac_aoi": f(r["cloud_frac_aoi"]), "NDCI": f(r["NDCI_chl_proxy"]),
             "NDTI": f(r["NDTI_turbidity_proxy"]), "RTI": f(r["RedTideIndex_proxy"]), "NDWI": f(r["NDWI_water_check"])}
            for r in rows if r["aoi"] == "shawka_dam" and not r.get("error")]
    other = sorted({r["aoi"] for r in rows} - {"shawka_dam"})
    return {"rows": sorted(keep, key=lambda r: r["date"]), "n": len(keep),
            "other_aois_in_file": {a: sum(r["aoi"] == a for r in rows) for a in other},
            "source": "data/inland/baseline_indices_s2_landsat.csv (AOI means; Sentinel-2 L2A and Landsat C2 L2, open data)"}


def water_presence_periods() -> list:
    """The per-scene CSV the log cites is not in the package; parse the log's own period table."""
    md = open(os.path.join(ROOT, "docs", "inland", "data-access-log", "shawka_dam_water_check.md"), encoding="utf-8").read()
    out = []
    for line in md.splitlines():
        m = re.match(r"^\|\s*\**([^|*]+?)\**\s*\|\s*\**([\d.]+)[–-]([\d.]+)%\**\s*\|\s*\**([\d.]+)(?:[–-]([\d.]+))?%\**\s*\|", line)
        if m:
            out.append({"period": m.group(1).strip(), "ndwi_gt0_pct": [float(m.group(2)), float(m.group(3))],
                        "ndwi_gt01_pct": [float(m.group(4)), float(m.group(5) or m.group(4))]})
    return out


def sat813_section(live: dict) -> dict:
    cov = jl(DATA, "satellite813", "enmap_813_coverage_comparison.json")
    sim = jl(RESTRICTED, "satellite813", "enmap_to_813_simulation.json")
    spec = spec_813()
    bt = jl(DATA, "metadata", "enmap_band_characterisation.json")
    support = None
    if sim:
        support = {d: {"n_with_real_support": v["n_813_bands_with_real_support"],
                       "n_without_real_support": v["n_813_bands_without_real_support"],
                       "unsupported_ranges_nm": [[round(a, 1), round(b, 1), n] for a, b, n in v["unsupported_813_wavelength_ranges_nm"]]}
                   for d, v in sim["per_date"].items()}
    c22 = [b["center_wavelength_nm"] for b in live["items"]["2022-09-08"]["bands"]]
    c24 = [b["center_wavelength_nm"] for b in live["items"]["2024-04-24"]["bands"]]
    pkg = [b["center_wavelength_nm"] for b in bt["bands"]]
    return {
        "coverage_comparison": cov,
        "simulation_support": support,
        "spec813": {"n_bands": spec.n_bands, "centres_nm": [round(float(x), 3) for x in spec.centres_nm],
                    "fwhm_nm": float(spec.fwhm_nm[0]), "spatial_resolution_m": spec.spatial_resolution_m,
                    "status": "813 grid ASSUMED from the published configuration (same as the coastal simulator)"},
        "enmap_bands_package": [{"n": b["index_1based"], "nm": b["center_wavelength_nm"], "fwhm": b["fwhm_nm"]} for b in bt["bands"]],
        "band_table_check": {
            "delta_2022_minus_package_nm": [round(a - b, 3) for a, b in zip(c22, pkg)],
            "delta_2024_minus_package_nm": [round(a - b, 3) for a, b in zip(c24, pkg)],
            "source": "data/inland/metadata/enmap_stac_live_check.json",
        },
    }


# --------------------------------------------------------------------------- review flags
def water_mask_sections() -> str:
    md = open(os.path.join(ROOT, "docs", "inland", "WATER_MASK.md"), encoding="utf-8").read()
    return ", ".join(re.findall(r"^## (\d+)\.", md, flags=re.M))


def overlap(a: dict, b: dict) -> int:
    return len({tuple(p) for p in a["px"]} & {tuple(p) for p in b["px"]})


def review_flags(s: dict, live: dict) -> list:
    bc = s["satellite813"]["band_table_check"]
    d22 = np.abs(np.array(bc["delta_2022_minus_package_nm"]))
    d24 = np.abs(np.array(bc["delta_2024_minus_package_nm"]))
    shift = [i + 1 for i, v in enumerate(d22) if 5 < v <= 50]       # shifted within the same window
    jump = [i + 1 for i, v in enumerate(d22) if v > 50]             # moved across the 1800-1940 nm gap
    pkg = s["satellite813"]["enmap_bands_package"]
    live22 = [b["center_wavelength_nm"] for b in live["items"]["2022-09-08"]["bands"]]
    t = s["temporal"]
    m = s["masks"]
    g = s["window"]
    base = s["baseline"]
    an = s["anomaly"]
    flags = [
        {"id": "F1", "severity": "high", "title": "EnMAP licence vs a public repository",
         "detail": ("The DLR STAC collection record says license \"proprietary\" (re-checked live 2026-10-02) and this "
                    "repository and its static site are public. The package's own audit says to confirm the terms before "
                    "any public repo or submission. Per-pixel reflectance layers and spectra are therefore kept out of git "
                    "(data/inland/restricted/) and out of the public summary; derived masks, scores and counts are published "
                    f"with the attribution \"{ATTRIBUTION}\". Someone should confirm the terms with DLR before submission."),
         "evidence": "data/inland/metadata/enmap_stac_live_check.json (collection_license)"},
        {"id": "F2", "severity": "high", "title": "The band table matches the 2024-04-24 scene only",
         "detail": (f"Fetched from the STAC items endpoint, the 2024-04-24 table equals the package table (max |Δ| "
                    f"{d24.max():.3f} nm) but the 2022-09-08 table does not. Most bands differ by ~0.3 nm (median "
                    f"{np.median(d22):.2f} nm), but B{shift[0]:03d}-B{shift[-1]:03d} sit "
                    f"{min(d22[i - 1] for i in shift):.0f}-{max(d22[i - 1] for i in shift):.0f} nm higher on 2022-09-08 and "
                    f"B{jump[0]:03d}-B{jump[-1]:03d} lie at {live22[jump[0] - 1]:.0f}-{live22[jump[-1] - 1]:.0f} nm instead of "
                    f"{pkg[jump[0] - 1]['nm']:.0f}-{pkg[jump[-1] - 1]['nm']:.0f} nm, across the water-vapour gap: a different "
                    "SWIR band arrangement, not rounding. The package's 'bit-for-bit identical across two scenes' check used "
                    "/search?ids=..., and that endpoint ignores ids, so it most likely returned the same item twice. Effect: on "
                    f"2022-09-08 the 813 simulation above ~{pkg[shift[0] - 1]['nm']:.0f} nm and the SWIR band groups use "
                    f"wavelengths up to ~12 nm off (the MNDWI cross-check's B150 is {live22[149]:.1f} nm, not {pkg[149]['nm']:.1f} nm); "
                    "the 620 nm test is unaffected (Δ ≈ 0.3 nm)."),
         "evidence": "data/inland/metadata/enmap_stac_live_check.json vs data/inland/metadata/enmap_band_characterisation.json"},
        {"id": "F3", "severity": "low", "title": "Real band-centre range quoted as 418.4-2450.3 nm",
         "detail": (f"SATELLITE_813_DECISION.md quotes the real band table as 418.4-2450.3 nm; its centres run "
                    f"{pkg[0]['nm']:.1f}-{pkg[-1]['nm']:.1f} nm (B224 = {pkg[-1]['nm']:.1f} nm). The 420-2450 nm figures "
                    "elsewhere are the instrument specification and are fine. Separately, the note inside "
                    "enmap_813_coverage_comparison.json still says the wavelength table is missing, though it was obtained the same day."),
         "evidence": "docs/inland/SATELLITE_813_DECISION.md; data/inland/satellite813/enmap_813_coverage_comparison.json"},
        {"id": "F4", "severity": "medium", "title": "Temporal flags are within chance",
         "detail": (f"With |z| > {t['z_threshold']} on any of 4 indices, pure noise flags "
                    f"{t['chance_level']['expected_flags_if_indices_perfectly_correlated']}-"
                    f"{t['chance_level']['expected_flags_if_indices_independent']} of {t['n_observations']} observations; "
                    f"{t['n_flagged']} were flagged. The cross-sensor Sep-Oct 2025 cluster is the notable part; the count is not."),
         "evidence": "data/inland/temporal/temporal_deviations.json"},
        {"id": "F5", "severity": "medium", "title": "Zero RX events is structural",
         "detail": ("background_is_superset_of_test is true: the test pixels are part of the background they are scored "
                    "against, which pulls their Mahalanobis distance down, so 0 events cannot be read as 'no anomaly'."
                    if an.get("available") and an.get("background_is_superset_of_test") else
                    "Restricted report not present; flag carried from the integration review."),
         "evidence": "anomaly_fingerprint_report.json: background_is_superset_of_test"},
        {"id": "F6", "severity": "low", "title": "'RedTideIndex' at an inland dam",
         "detail": "The index name implies marine harmful algal blooms; for a freshwater wadi pool a neutral name (red-edge ratio) would avoid misreading.",
         "evidence": "data/inland/baseline_indices_s2_landsat.csv"},
        {"id": "F7", "severity": "low", "title": "Referenced per-scene water-presence CSV is missing",
         "detail": "data/shawka_dam_water_presence.csv is cited for the per-scene table but is not in the package; only the period ranges in the log survive.",
         "evidence": "docs/inland/data-access-log/shawka_dam_water_check.md"},
        {"id": "F8", "severity": "low", "title": "Baseline CSV carries other-AOI rows",
         "detail": ("The baseline file also holds " + ", ".join(f"{n} {a}" for a, n in base["other_aois_in_file"].items())
                    + " rows that the inland docs do not mention; only the shawka_dam rows are used here."),
         "evidence": "data/inland/baseline_indices_s2_landsat.csv"},
        {"id": "F9", "severity": "low", "title": "AOI size quoted as ~660 m x 460 m",
         "detail": f"The polygon's projected extent is {g['polygon_size_m'][0]} m x {g['polygon_size_m'][1]} m (UTM 40N).",
         "evidence": "config/inland/shawka_dam.geojson"},
        {"id": "F10", "severity": "low", "title": "WATER_MASK.md section order",
         "detail": ("Top-level sections in docs/inland/WATER_MASK.md run " + water_mask_sections()
                    + ": section 11 is missing and 14 comes before 13. Cosmetic, but section cross-references depend on it."),
         "evidence": "docs/inland/WATER_MASK.md"},
        {"id": "F11", "severity": "medium", "title": "The two single-date masks disagree; the MNDWI cross-check finds nothing",
         "detail": (f"2022-09-08: {m['2022-09-08']['n']} px; 2024-04-24: {m['2024-04-24']['n']} px with the same thresholds, "
                    f"overlapping the 2022 pixels in {overlap(m['2022-09-08'], m['2024-04-24'])}; the persistent core "
                    f"({m['persistent_core']['n']} px) shares {overlap(m['2022-09-08'], m['persistent_core'])} pixels with the 2022 mask; "
                    f"real-MNDWI core: {m['mndwi_core']['n']} px. The wet core rests on a darkness criterion that a standard "
                    "water index does not reproduce (the package documents this; it is the main thing to keep in view)."),
         "evidence": "data/inland/water_mask/*_mask.npy"},
        {"id": "F12", "severity": "low", "title": "Project naming in the inland docs",
         "detail": ("The inland docs refer to the coastal project as DesalGuard-main and describe it as the Gulf of Annaba PoC "
                    "with no inland component; in BLUEBAN the coastal hero is now Fujairah (UAE), with Annaba kept as the "
                    "earlier PoC. The texts are kept verbatim; readers should map the names."),
         "evidence": "docs/inland/*.md"},
        {"id": "F13", "severity": "low", "title": "Scripts need renamed imports and the raw scenes",
         "detail": "scripts/inland/*.py import pipeline.satellite813 / pipeline.provenance (BLUEBAN's coastal modules) and read 'sourced data/' raw scenes, which are not here and will not be sourced without the owner. 2022-09-08 also predates the S2/Landsat baseline by about a year.",
         "evidence": "scripts/inland/README.md"},
        {"id": "F14", "severity": "low", "title": "224 vs 222 bands",
         "detail": ("The package already flags that the 2022-09-08 GeoTIFF has 224 bands while DLR's product specification "
                    "states a nominal 91 VNIR + 131 SWIR = 222. Still unreconciled; the STAC tables for both dates also list 224."),
         "evidence": "docs/inland/DATA_ACCESS_AUDIT.md"},
        {"id": "F15", "severity": "info", "title": "Crop window reconstructed, not shipped",
         "detail": (f"The window transform is not in the package. Rebuilt from DLR's STAC grid and the documented crop rule, it has "
                    f"{g['n_inside_reconstructed']} pixels inside the polygon (package: {m['px_inside_locked_polygon_reported']}), "
                    f"and {m['persistent_core']['n_inside_reconstructed_polygon']}/{m['persistent_core']['n']} wet-core pixels fall inside it."),
         "evidence": "outputs/inland/summary.json: window"},
    ]
    return flags


def write_flags_md(flags: list) -> None:
    lines = ["# Shawka Dam integration review: flags", "",
             "Generated by `scripts/inland/build_inland_bundle.py` when the inland package was integrated",
             "(2026-10-02). Per the integration brief these are **flagged, not fixed**: nothing in the",
             "teammate's files was changed. Each flag names the evidence it rests on.", "",
             "| # | Severity | Flag |", "|---|---|---|"]
    lines += [f"| {f['id']} | {f['severity']} | {f['title']} |" for f in flags]
    lines.append("")
    for f in flags:
        lines += [f"## {f['id']}. {f['title']}", "", f["detail"], "", f"*Evidence:* `{f['evidence']}`", ""]
    os.makedirs(os.path.dirname(FLAGS_MD), exist_ok=True)
    with open(FLAGS_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main():
    t0 = time.time()
    gj = jl(ROOT, "config", "inland", "shawka_dam.geojson")
    poly = gj["features"][0]["geometry"]["coordinates"][0]
    live = jl(DATA, "metadata", "enmap_stac_live_check.json")
    lons, lats = [p[0] for p in poly], [p[1] for p in poly]
    s = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "site": {"id": "AE-SHAWKA", "name": "Shawka Dam", "emirate": "Ras Al Khaimah", "kind": "inland_reservoir",
                  "polygon": poly, "bbox": [min(lons), min(lats), max(lons), max(lats)],
                  "centroid": [float(np.mean(lons[:-1])), float(np.mean(lats[:-1]))],
                  "status": "STATIC RESULTS: two fixed EnMAP acquisition dates, not a live feed"},
         "caveats": CAVEATS, "licence": {"enmap": "proprietary", "attribution": ATTRIBUTION,
                                         "withheld": ["per-pixel brightness / darkness layers", "band-group reflectance means",
                                                      "simulated 813 per-pixel spectra"]},
         "scenes": {d: {k: v for k, v in live["items"][d].items() if k != "bands"} for d in DATES}}
    s["window"] = window_geometry(poly, live)
    s["masks"] = masks_section(s["window"])
    s["anomaly"] = anomaly_section()
    s["temporal"] = temporal_section()
    s["baseline"] = baseline_section()
    s["water_presence_periods"] = water_presence_periods()
    s["satellite813"] = sat813_section(live)
    s["flags"] = review_flags(s, live)
    s["docs"] = sorted(os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, "/")
                       for dp, _, fs in os.walk(os.path.join(ROOT, "docs", "inland")) for f in fs if f.endswith(".md"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(s, f, separators=(",", ":"))
    write_flags_md(s["flags"])
    print(f"-> {os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT) / 1024:.0f} KB), "
          f"{os.path.relpath(FLAGS_MD, ROOT)}; window inside={s['window']['n_inside_reconstructed']} "
          f"(reported {s['masks']['px_inside_locked_polygon_reported']}), {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
