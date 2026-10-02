# Inland complement: Shawka Dam (Ras Al Khaimah)

A second site built separately on hyperspectral EnMAP L2A data and integrated
into BLUEBAN 813 as a pure add-on (2026-10-02). The coastal pipeline, its outputs
and its numbers are unchanged. The documents in this folder are the module's own,
kept verbatim; where they say "DesalGuard-main" they mean the coastal project
(BLUEBAN 813), and where they cite `pipeline/`, `scripts/`, `data/` or `aoi/`,
read the namespaced locations below.

**Static results, not a live feed:** two fixed EnMAP acquisition dates
(2022-09-08 and 2024-04-24) and a 28-observation Sentinel-2/Landsat baseline
(September 2023 to October 2025).

Two caveats, carried over exactly:

* EnMAP's license is "proprietary" with redistribution terms not yet confirmed for public submission.
* Caveat on the detector: the anomaly/fingerprint results are based on a ~10-17 pixel background population, not a calibrated detector.

| Document | What it covers |
|---|---|
| [REVIEW_FLAGS.md](REVIEW_FLAGS.md) | **Read first.** The integration review: what looks off, with evidence (flagged, not fixed) |
| [AOI_SELECTION.md](AOI_SELECTION.md) | Why Shawka Dam; Tanager negative, EnMAP positive; footprint checks; wet-core evidence |
| [DATA_ACCESS_AUDIT.md](DATA_ACCESS_AUDIT.md) | EnMAP access, licence, product and atmospheric-correction facts |
| [WATER_MASK.md](WATER_MASK.md) | Single-date masks, the two-date comparison, the persistent wet core, the band table |
| [ANOMALY_AND_FINGERPRINT.md](ANOMALY_AND_FINGERPRINT.md) | RX anomaly and fingerprint on the wet core, and the small-background caveat |
| [TEMPORAL_BASELINE_DETECTOR.md](TEMPORAL_BASELINE_DETECTOR.md) | z-score deviation detector on the S2/Landsat baseline |
| [SATELLITE_813_DECISION.md](SATELLITE_813_DECISION.md) | Why the 813 simulator was built on EnMAP, and what it can and cannot claim |
| [data-access-log/shawka_dam_water_check.md](data-access-log/shawka_dam_water_check.md) | Water presence over 14 monthly Sentinel-2 scenes |

| Their path | Here |
|---|---|
| `pipeline/*.py` | `pipeline/inland/` (byte-identical) |
| `scripts/*.py` | `scripts/inland/` (byte-identical; see its README for the import map) |
| `config/project.yaml` | `config/inland/project.yaml` (full original) and `config/project.yaml → sites.shawka_dam` (inland blocks, verbatim) |
| `aoi/shawka_dam.geojson` | `config/inland/shawka_dam.geojson` |
| `data/*` | `data/inland/*`; per-pixel EnMAP reflectance layers and spectra in `data/inland/restricted/` (gitignored) |

Served as `GET /api/inland/summary` (built by `scripts/inland/build_inland_bundle.py`)
and shown at `/inland` in the app.
