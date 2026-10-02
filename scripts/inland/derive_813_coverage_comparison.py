"""Save the EnMAP-vs-813 coverage comparison (see pipeline/satellite813.py
for why this is a coverage comparison and NOT a pixel-level simulator) and
its provenance record.

Usage: python3 scripts/derive_813_coverage_comparison.py
No scene files needed -- every input is already-verified project metadata
(config/project.yaml / docs/DATA_ACCESS_AUDIT.md), not re-read from a raster.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.satellite813 import (  # noqa: E402
    spec_813, enmap_coverage_from_project, enmap_813_coverage_comparison,
)
from pipeline.provenance import Provenance, AlgorithmRecord  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "satellite813"


def main() -> None:
    spec813 = spec_813()
    enmap22 = enmap_coverage_from_project(n_bands_valid=218)  # 224 - 6, 2022-09-08
    enmap24 = enmap_coverage_from_project(n_bands_valid=219)  # 224 - 5, 2024-04-24

    cmp22 = enmap_813_coverage_comparison(enmap22, spec813)
    cmp24 = enmap_813_coverage_comparison(enmap24, spec813)

    print("2022-09-08 scene coverage comparison:")
    print(json.dumps(cmp22, indent=1))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {"2022-09-08": cmp22, "2024-04-24": cmp24}
    with open(OUT_DIR / "enmap_813_coverage_comparison.json", "w") as fh:
        json.dump(out, fh, indent=1)

    prov = Provenance(
        result_id="satellite813_coverage_comparison_shawka_dam_v1",
        result_kind="satellite813_decision",
        algorithm=AlgorithmRecord(
            name="enmap_813_coverage_comparison",
            description=(
                "Coarse spectral-range/band-density/spatial-resolution "
                "comparison between EnMAP (this project's scenes) and "
                "Satellite 813's published configuration. A DECISION not to "
                "build a per-band/per-pixel resampled simulator, documented "
                "here rather than left open -- see pipeline/satellite813.py "
                "module docstring for the full reasoning."
            ),
            reference="pipeline/satellite813.py; DesalGuard-main/pipeline/satellite813.py spec_813() (copied, cited)",
            parameters={"spec_813_defaults": "lo=400, hi=1700, sampling=5.0, n_bands=205, spatial_m=20.0"},
            inputs=["config/project.yaml enmap.spec", "https://spaceacademy-hackathons.space.gov.ae/data"],
            units_out="coverage-comparison dict (nm, band counts, ratios) -- not reflectance",
            assumptions=[
                "813's band layout is evenly spaced across its published range (DesalGuard-main's "
                "own explicit, documented assumption in spec_813(), reproduced unmodified here).",
            ],
            limitations=[
                "No per-band EnMAP-to-813 correspondence is computed or implied -- see decision "
                "field in the output and pipeline/satellite813.py module docstring for why a full "
                "Gaussian-SRF resampled simulator was deliberately NOT built for this AOI.",
                "enmap_avg_band_spacing_nm is a whole-range average, not a per-band value; EnMAP's "
                "real per-band spacing likely varies (finer in VNIR, coarser in SWIR per its nominal "
                "FWHM figures) but cannot be placed without the still-missing wavelength table.",
            ],
        ),
        extra={"comparison_2022_09_08": cmp22, "comparison_2024_04_24": cmp24},
    )
    prov_path = prov.save(str(OUT_DIR / "provenance_satellite813_decision.json"))
    print(f"\nSaved coverage comparison and provenance to {OUT_DIR}")
    print(f"Provenance: {prov_path}")


if __name__ == "__main__":
    main()
