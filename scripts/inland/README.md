# scripts/inland: Shawka Dam (inland complement)

These are the derivation scripts that produced `data/inland/`, copied
**unmodified** from the separately built inland package, plus one BLUEBAN script.

| Script | What it did | Needs |
|---|---|---|
| `crop_enmap_scene.py` | Cropped the 2024-04-24 EnMAP scene to the AOI + 150 m | raw scene |
| `derive_water_mask.py` | Single-date wet mask per EnMAP date | raw scenes |
| `derive_persistent_wet_core.py` | Two-date persistent wet core | raw scenes |
| `derive_persistent_wet_core_mndwi.py` | Real-MNDWI cross-check of the core | raw scenes |
| `derive_anomaly_and_fingerprint.py` | RX anomaly + fingerprint on the core | raw scenes |
| `derive_813_simulation.py` | 813 simulated on EnMAP (Gaussian SRFs) | raw scenes |
| `derive_813_coverage_comparison.py` | EnMAP vs 813 coverage comparison | none |
| `derive_temporal_baseline_detector.py` | z-score deviation detector on the S2/Landsat baseline | `data/baseline_indices_s2_landsat.csv` |
| **`build_inland_bundle.py`** (BLUEBAN) | Builds `outputs/inland/summary.json` and `docs/inland/REVIEW_FLAGS.md` from `data/inland/` | nothing restricted is published |

BLUEBAN does **not** run the derivation scripts: their outputs are already in
`data/inland/` and are this site's data source. To re-run one against a future
scene, map the paths the scripts were written for:

| In the scripts | In this repository |
|---|---|
| `from pipeline.water_mask / anomaly / fingerprint / satellite813 / temporal import ...` | `pipeline.inland.<module>` (`pipeline.satellite813` here is BLUEBAN's coastal simulator; same 813 spec, different module) |
| `from pipeline.provenance import ...` | `pipeline.inland.provenance` (functionally identical to BLUEBAN's `pipeline/provenance.py`) |
| `aoi/shawka_dam.geojson` | `config/inland/shawka_dam.geojson` |
| `data/...` | `data/inland/...` |
| per-pixel layers and spectra (`*_brightness.npy`, `persistent_wet_core_joint_darkness.npy`, `persistent_wet_core_mndwi_joint_min.npy`, `anomaly_fingerprint_report.json`, `enmap_to_813_simulation.json`) | `data/inland/restricted/...` (gitignored) |
| `sourced data/` (raw EnMAP scenes) | **not in this repository.** The module owner holds them; ask them directly rather than sourcing scenes yourself |

`pipeline/inland/temporal.py` needs pandas: `pip install -e ".[inland]"`.

Before re-running anything on the 2022-09-08 scene, read
`docs/inland/REVIEW_FLAGS.md` F2: the per-band wavelength table in
`data/inland/metadata/enmap_band_characterisation.json` matches the 2024-04-24
item only, and the DLR STAC `/search` endpoint ignores `ids`. Fetch each scene's
own table from `/collections/ENMAP_HSI_L2A/items/{id}` (both are saved in
`data/inland/metadata/enmap_stac_live_check.json`).
