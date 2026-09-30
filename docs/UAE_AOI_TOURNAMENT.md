# UAE AOI tournament

**BLUEBAN 813** · Team Kanban · generated 30 September 2026 by `scripts/build_tournament.py`

Which UAE area of interest should carry the demonstration, decided from the data rather than chosen in advance. Each criterion is in [0, 1]; the total is the weighted sum. Re-run the script after new screening.

| Criterion | Weight | How it is measured |
|---|---|---|
| Data | 0.15 | usable Sentinel-2 acquisitions (≥ 500 water pixels), relative to the best AOI |
| Optics | 0.20 | optical regime from config: optically deep 1.0 · shelf 0.55 · shallow 0.4 · shallow lagoon 0.2 (bright seabed degrades water-colour algorithms more than sediment does; Al Shehhi et al. 2017) |
| Evidence | 0.30 | half OLCI-confirmed candidates (saturating at 10), half documented events in `UAE_EVENT_REGISTER.md` (saturating at 3) |
| Exposure | 0.20 | desalination and power plants within 0.15° of the AOI (OpenStreetMap), relative to the best AOI |
| Burden | 0.15 | share of OLCI-referenced candidates that OLCI confirms (a detector that mostly finds artefacts here scores low); 0.5 when unreferenced |

## Ranking

| # | AOI | Coast | Usable scenes | Candidates (bloom-like) | OLCI refs +/− | Plants nearby | Data | Optics | Evidence | Exposure | Burden | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **AE-FUJ** Fujairah / Qidfa / anchorage | Gulf of Oman | 456 | 257 (23) | 11/20 | 5 | 0.76 | 1.00 | 1.00 | 0.62 | 0.35 | **0.79** |
| 2 | **AE-AUH-NORTH** Abu Dhabi island north coast / Saadiyat | Arabian Gulf | 597 | 681 (151) | 41/19 | 8 | 1.00 | 0.40 | 0.67 | 1.00 | 0.68 | **0.73** |
| 3 | **AE-SHJ-KALBA** Kalba | Gulf of Oman | 241 | 57 (12) | 11/3 | 1 | 0.40 | 1.00 | 1.00 | 0.12 | 0.79 | **0.70** |
| 4 | **AE-FUJ-DIBBA** Dibba | Gulf of Oman | 278 | 57 (11) | 12/7 | 0 | 0.47 | 1.00 | 0.83 | 0.00 | 0.63 | **0.61** |
| 5 | **AE-SHJ-KHORFAKKAN** Khor Fakkan | Gulf of Oman | 263 | 75 (8) | 5/10 | 4 | 0.44 | 1.00 | 0.42 | 0.50 | 0.33 | **0.54** |

**Pending (screening not finished; not scored, not guessed):** AE-AUH-LAGOON (Abu Dhabi / Musaffah lagoons), AE-AUH-TAWEELAH (Al Taweelah / Khalifa Port), AE-DXB-JEBELALI (Dubai / Jebel Ali), AE-SHJ-AJM (Sharjah / Ajman), AE-UAQ-RAK (Umm Al Quwain / Ras Al Khaimah).

## Result

**AE-FUJ (Fujairah / Qidfa / anchorage)** ranks first. Its nearby plants include Fujairah F2 power and desalination plant, Fujairah Qidfa F1 power and desalination plant, Fujairah F3 power plant, Kalba Power Plant; documented events: 2017 green Noctiluca (MOCCAE sampling); Oct 2019 diesel spill (S1 slick); Apr 2026 FEA 'greenish water'.

The hero incident, **BB-AE-2024-001**, comes from this AOI: bright-green filaments on 17 February 2024 that Sentinel-3 OLCI independently resolved the same morning.

**AE-AUH-NORTH** is second (0.73), strongest on data, exposure, burden. It is an optically shallow shelf: there Sentinel-2 and OLCI can both respond to seabed reflectance and resuspension, so their agreement is weaker evidence of a water-column event than in deep water. That is why the optics criterion carries weight, and why a high candidate count there is not by itself an advantage.

The first AOI's burden score is a reminder, not a flaw to hide: over its very clear water NDCI becomes unstable and many candidates there are ratio artefacts that OLCI does not confirm (BB-AE-2023-001 is one). The verification queue and the learning loop exist for exactly that.

## Why Annaba is no longer the hero

The Gulf of Annaba (Algeria) was the original demonstration because an open Tanager hyperspectral scene exists there. It stays in the product as the **negative control**: spatially unusual but ordinary for the season, so the system stands down.

## Caveats

* OLCI references are a model product (Case-2 neural net), not in-situ truth, and cannot label candidates smaller than a few 300 m pixels or after 23 February 2026.
* The event register is incomplete and uneven across emirates; it is used as weak prior evidence only.
* Weights are a judgement, stated here so a reviewer can change them and re-run the script.
