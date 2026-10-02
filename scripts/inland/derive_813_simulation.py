"""Run the REVISED Satellite 813 decision: a real per-band Gaussian-SRF
resample of both EnMAP scenes onto 813's published band configuration,
using EnMAP's real per-band wavelength grid (data/metadata/
enmap_band_characterisation.json) as the source axis.

See pipeline/satellite813.py module docstring and docs/SATELLITE_813_DECISION.md
for why this is now buildable where it previously was not (EnMAP's grid is
real now, 813's remains the one explicit assumption -- same one-assumption
standard as DesalGuard-main's own Tanager-to-813 simulator).

This does NOT replace scripts/derive_813_coverage_comparison.py -- that
coarse, no-scene-file comparison is still saved and still useful as a
whole-range-average companion view. This script is the finer, per-band,
per-pixel one.

Usage (from the project root):

    python3 scripts/derive_813_simulation.py \
        "<uploads>/...20220908...SPECTRAL_IMAGE_COG.tiff" \
        "<uploads>/...20240424...AOI_CROP.tiff"

Same two inputs as scripts/derive_anomaly_and_fingerprint.py. Saves a full
report and provenance record to data/satellite813/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.water_mask import persistent_wet_core, load_band_characterisation  # noqa: E402
from pipeline.satellite813 import (  # noqa: E402
    spec_813, simulate_813_enmap, enmap_wavelengths_from_band_table,
)
from pipeline.provenance import Provenance, AlgorithmRecord  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AOI_GEOJSON = PROJECT_ROOT / "aoi" / "shawka_dam.geojson"
BAND_TABLE = PROJECT_ROOT / "data" / "metadata" / "enmap_band_characterisation.json"
OUT_DIR = PROJECT_ROOT / "data" / "satellite813"
BUFFER_M = 150.0


def _window_first_scene(path: Path):
    with open(AOI_GEOJSON) as f:
        gj = json.load(f)
    geom4326 = gj["features"][0]["geometry"]
    lons = [p[0] for p in geom4326["coordinates"][0]]
    lats = [p[1] for p in geom4326["coordinates"][0]]
    with rasterio.open(path) as ds:
        crs = ds.crs
        left, bottom, right, top = transform_bounds(
            "EPSG:4326", crs, min(lons), min(lats), max(lons), max(lats))
        win = from_bounds(left - BUFFER_M, bottom - BUFFER_M, right + BUFFER_M, top + BUFFER_M,
                           transform=ds.transform).round_offsets().round_lengths()
        cube = ds.read(window=win)
        return cube, ds.nodata


def _read_precropped(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(), ds.nodata


def _runs_to_ranges(flag: np.ndarray, wl: np.ndarray) -> list:
    """Collapse a boolean band flag into contiguous [start_nm, end_nm, count]
    runs, rather than a naive min/max (which would wrongly imply one
    contiguous span when the flagged bands are actually disjoint -- e.g.
    813's low-end bands below EnMAP's real floor AND a separate run of 813
    bands landing in EnMAP's real 1390-1449 nm wavelength-axis gap are two
    different things, not one). Same method as DesalGuard-main's own
    _runs_to_ranges() in pipeline/satellite813.py, copied here for the same
    purpose (summarizing a boolean band flag), not re-derived."""
    idx = np.where(flag)[0]
    if len(idx) == 0:
        return []
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i != prev + 1:
            out.append([float(wl[start]), float(wl[prev]), int(prev - start + 1)])
            start = i
        prev = i
    out.append([float(wl[start]), float(wl[prev]), int(prev - start + 1)])
    return out


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    path_2022, path_2024 = Path(sys.argv[1]), Path(sys.argv[2])

    cube22, nodata22 = _window_first_scene(path_2022)
    cube24, nodata24 = _read_precropped(path_2024)
    assert cube22.shape[1:] == cube24.shape[1:], "grid mismatch -- see derive_persistent_wet_core.py"

    cubes = [cube22, cube24]
    nodatas = [nodata22, nodata24]
    labels = ["2022-09-08", "2024-04-24"]

    bands = load_band_characterisation(str(BAND_TABLE))
    src_nm = enmap_wavelengths_from_band_table(bands)
    spec813 = spec_813()

    core_test = persistent_wet_core(cubes, nodatas, labels, darkness_max=0.10)
    rr, cc = np.where(core_test.mask)
    print(f"Test-core pixels: {len(rr)}")
    print(f"EnMAP real source wavelengths: {len(src_nm)} bands, "
          f"{src_nm.min():.1f}-{src_nm.max():.1f} nm")
    print(f"813 target: {spec813.n_bands} bands, "
          f"{spec813.centres_nm.min():.1f}-{spec813.centres_nm.max():.1f} nm "
          f"({spec813.source})")

    report = {
        "enmap_source_wavelength_range_nm": [float(src_nm.min()), float(src_nm.max())],
        "enmap_n_source_bands": int(len(src_nm)),
        "spec813_wavelength_range_nm": [float(spec813.centres_nm.min()), float(spec813.centres_nm.max())],
        "spec813_n_bands": int(spec813.n_bands),
        "per_date": {},
    }

    for cube, nodata, lbl in zip(cubes, nodatas, labels):
        cube_813, spec, supported, _ = simulate_813_enmap(cube, nodata, bands, spec=spec813)

        # "supported" (spec.n_bands,) is True wherever the 813 band's Gaussian
        # window has ANY real EnMAP source band inside it at all -- independent
        # of any specific pixel's nodata. This is the real, computed answer to
        # "how much of 813's published range does EnMAP's real per-band grid
        # actually cover," which docs/SATELLITE_813_DECISION.md's coarse
        # comparison could previously only state as a whole-range average.
        n_supported = int(supported.sum())
        n_unsupported = int((~supported).sum())
        unsupported_ranges = _runs_to_ranges(~supported, spec.centres_nm)

        # Per-pixel: how many of the 813 bands come back NaN (min_support not
        # met) for the test-core pixels specifically, vs. how many are simply
        # unsupported everywhere (813 band outside EnMAP's real coverage).
        core_spectra = []
        nan_counts_beyond_unsupported = []
        for r, c in zip(rr, cc):
            spec813_pixel = cube_813[:, r, c]
            n_nan_total = int(np.isnan(spec813_pixel).sum())
            n_nan_beyond = n_nan_total - n_unsupported
            nan_counts_beyond_unsupported.append(n_nan_beyond)
            core_spectra.append({
                "row": int(r), "col": int(c),
                "n_813_bands_nan": n_nan_total,
                "n_813_bands_nan_beyond_range_gap": n_nan_beyond,
                "spectrum_813": [None if np.isnan(v) else round(float(v), 5) for v in spec813_pixel],
            })

        print(f"\n--- {lbl} ---")
        print(f"  813 bands with ANY real EnMAP support: {n_supported}/{spec.n_bands}")
        print(f"  813 bands with NO real EnMAP support (outside EnMAP's real coverage): "
              f"{n_unsupported}/{spec.n_bands} ({unsupported_ranges})")
        extra_gaps = [n for n in nan_counts_beyond_unsupported if n > 0]
        print(f"  Test-core pixels with EXTRA NaN 813 bands from the real EnMAP nodata "
              f"gaps (beyond the out-of-range ones): {len(extra_gaps)}/{len(rr)} pixels"
              + (f", extra-NaN counts {extra_gaps}" if extra_gaps else ""))

        report["per_date"][lbl] = {
            "n_813_bands_with_real_support": n_supported,
            "n_813_bands_without_real_support": n_unsupported,
            "unsupported_813_wavelength_ranges_nm": unsupported_ranges,
            "core_pixel_spectra_813": core_spectra,
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "enmap_to_813_simulation.json", "w") as fh:
        json.dump(report, fh, indent=1)

    prov = Provenance(
        result_id="satellite813_real_simulation_shawka_dam_v1",
        result_kind="satellite813_simulation",
        algorithm=AlgorithmRecord(
            name="simulate_813_enmap (Gaussian-SRF resample, real EnMAP source axis)",
            description=(
                "Per-band Gaussian spectral-response-function resample of "
                "both EnMAP scenes' persistent-wet-core test pixels onto "
                "Satellite 813's published band configuration. EnMAP's "
                "source wavelength axis is REAL (data/metadata/"
                "enmap_band_characterisation.json, cross-validated against "
                "DLR's own STAC eo:bands metadata) -- this REVERSES the "
                "prior inland_simulator_built=false decision now that the "
                "condition that decision itself named for reversal is met. "
                "813's own band grid remains the one explicit, documented "
                "assumption (spec_813(), copied unmodified from "
                "DesalGuard-main), matching DesalGuard's own one-assumption "
                "standard for its Tanager-to-813 simulator."
            ),
            reference=(
                "pipeline/satellite813.py; DesalGuard-main/pipeline/"
                "satellite813.py gaussian_srf_matrix()/resample_spectra() "
                "(copied verbatim, general method); "
                "data/metadata/enmap_band_characterisation.json (real "
                "EnMAP source axis)"
            ),
            parameters={
                "spec_813_defaults": "lo=400, hi=1700, sampling=5.0, n_bands=205, spatial_m=20.0",
                "min_support": 0.5,
                "gaussian_truncate_sigma": 3.0,
                "reflectance_scale": "1/10000",
            },
            inputs=[
                str(path_2022), str(path_2024), str(BAND_TABLE),
                "https://spaceacademy-hackathons.space.gov.ae/data",
            ],
            units_out="simulated 813-band reflectance (unitless, EnMAP DN/10000 convention), NaN where unsupported",
            assumptions=[
                "813's band layout is evenly spaced across its published range "
                "(DesalGuard-main's own explicit, documented assumption in "
                "spec_813(), reproduced unmodified here) -- the ONE remaining "
                "assumption in this simulation, same as DesalGuard's own "
                "Tanager-to-813 case.",
            ],
            limitations=[
                "No spatial resampling: EnMAP's 30 m stays 30 m, not upsampled "
                "to 813's 20 m (would invent spatial detail the source never "
                "measured -- same position DesalGuard-main's own simulator "
                "takes).",
                "Only the persistent-wet-core test pixels (10 per date) are "
                "resampled and saved per-pixel here, not the full AOI window "
                "-- this project's validated water population, per "
                "docs/WATER_MASK.md section 12.",
                "813 bands below EnMAP's real coverage floor (EnMAP starts at "
                "420 nm; 813's published range starts at 400 nm) have NO real "
                "EnMAP support at any pixel and come back NaN -- a real, "
                "computed finding (see unsupported_813_wavelength_ranges_nm "
                "in the saved report), not an approximation.",
                "813's own configuration remains assumed (evenly-spaced across "
                "its published range) -- this simulation is only as faithful "
                "as that published-spec assumption, exactly DesalGuard's own "
                "caveat for its Tanager simulator.",
            ],
        ),
        extra={"summary": {
            lbl: {
                "n_813_bands_with_real_support": report["per_date"][lbl]["n_813_bands_with_real_support"],
                "n_813_bands_without_real_support": report["per_date"][lbl]["n_813_bands_without_real_support"],
            }
            for lbl in labels
        }},
    )
    prov_path = prov.save(str(OUT_DIR / "provenance_satellite813_simulation.json"))
    print(f"\nSaved simulation report and provenance to {OUT_DIR}")
    print(f"Provenance: {prov_path}")


if __name__ == "__main__":
    main()
