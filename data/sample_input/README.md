# Sample input: BB-AE-2024-001 (Fujairah, 17 Feb 2024)

The offline input of [`notebooks/blueban813_poc.ipynb`](../../notebooks/blueban813_poc.ipynb), about 8.7 MB.
Everything is on one grid: a 12.0 x 11.2 km window (600 x 560 pixels at 20 m, EPSG:32640, WGS 84 / UTM 40N,
origin 435300 E, 2782560 N; lon 56.3580-56.4696 E, lat 25.0493-25.1581 N) of the incident's own 20 m analysis
grid, with the same pixels and alignment as `outputs/incidents/BB-AE-2024-001.json`. It holds the coast, the
whole event and the water around it.

| File | What it is |
|---|---|
| `s2l2a_20240217_fujairah_20m_dn.tif` | The event image: Sentinel-2A L2A item `S2A_MSIL2A_20240217T064941_R020_T40RDN_20240217T105525`, 2024-02-17 06:49:41 UTC, processing baseline 05.10. Ten float32 bands of digital numbers: B01 B02 B03 B04 B05 B06 B8A B11 B12 and SCL. Reflectance = (DN - 1000) / 10000 (BOA_ADD_OFFSET -1000 because the baseline is >= 04.00; `pipeline.s2_features.dn_to_reflectance`); DN 0 = no data. Read with the pipeline's own reader (`pipeline.watch.load_datatake`). The 20 m and 60 m bands are the original integer DN. The reader averages the 10 m bands onto the 20 m grid: B04 is kept at full float precision (it decodes bit-identically; NDCI over clear water is very sensitive to it), B02 and B03 are rounded to the nearest DN (at most 0.00005 reflectance). |
| `seasonal_baseline_20m.tif` | The per-pixel same-season baseline from 36 Sentinel-2 L2A acquisitions (2018-2026, within +/-45 days of day-of-year, 2024 excluded), selected by the incident builder's own rule. For NDCI, MCI, hue angle and turbidity: the count `n` and the `median`; `mad` for NDCI, MCI and hue; and for NDCI the order statistics `q95` (the ceil(0.95 n)-th smallest past value: seasonal percentile >= 95 exactly when the event value exceeds it) and `max`. Float32, each layer rounded to a fixed binary step (band tags and `manifest.json`) so the file compresses. |
| `seasonal_baseline_transect.npz` | The full history (all 36 acquisitions, the four features) along one west-east row through the event, so the notebook can run `pipeline.detect.robust_anomaly` on it and compare with the compact baseline. |
| `manifest.json` | Every STAC item id (event and each baseline acquisition) with datetime, platform and processing baseline; the grid and its place in the incident grid; bands; SHA-256 checksums; the regeneration command; licence and attribution; and a reference check: the event computed at full precision on the full incident grid (identical to the committed incident: 5,984 pixels, 2.394 km2, NDCI robust z 7.32) next to the event computed from these files (the same 5,984 pixels). |

## Regenerate

```bash
python scripts/fetch_sample_input.py             # re-reads the exact item ids listed in the script (about 3 minutes)
python scripts/fetch_sample_input.py --reselect  # also re-derives the 36 baseline acquisitions with the incident builder's rule (10-15 more minutes)
```

Anonymous Microsoft Planetary Computer access (STAC search, assets signed with `planetary_computer.sign`): no
account, no key.

## Licence and attribution

Copernicus Sentinel data are free and open. Contains modified Copernicus Sentinel data 2024 (event) and
2018-2026 (seasonal baseline), processed by ESA, accessed via Microsoft Planetary Computer.
