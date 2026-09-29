# UAE Coastal Water Event Register

**BLUEBAN 813** · Team Kanban · compiled 30 September 2026

Documented UAE coastal water events that could anchor a satellite
demonstration, with what is actually known about each. Used by the AOI
tournament and to choose the positive (actionable) case.

**[V]** = checked in the cited source. **[U]** = unverified or inferred.
Coordinates marked ≈ are gazetteer estimates, not from the sources.

## Headline

* **No UAE event since 2017 combines** a published Sentinel-2/3 image, an exact
  date and a species-level field confirmation. Every candidate is missing at
  least one of the three.
* **The widely cited "UAE oil spill, March 2017" is not a UAE-coast spill.** It
  is Sentinel-1A imagery from 8 and 11 March 2017 of crude traced to Iran's Siri
  offshore field that drifted toward UAE waters (SkyTruth, 27 Mar 2017 update;
  ScanEx / IO RAS name the Siri-E field). A EUMETSAT case study says the slick
  "reached the Al-Fujairah coast", which is geographically impossible
  (Fujairah is on the Gulf of Oman) and is treated here as an error. No
  downloadable reference outlines were found. BLUEBAN uses it, if at all, as a
  **regional SAR benchmark**, never as a UAE incident.

## Ranked candidates

| # | Event | Date(s) | Location | Confirmation | Published imagery | Sources |
|---|---|---|---|---|---|---|
| 1 | Green *Noctiluca scintillans* reaching the UAE east coast | MODIS chl ~10 mg m⁻³ mid-Feb 2017; MOCCAE sampling reported 29 Mar and 11 Apr 2017 | Sea of Oman off Fujairah (≈25.1 N, 56.4–56.6 E) | MOCCAE samples confirmed the species; "not concentrated enough" to harm reefs [V] | MODIS maps in the press only | The National (2017) |
| 2 | Al Raha Beach discolouration (non-toxic bloom) | From Dec 2022; NYUAD weekly sampling from Apr 2023; beach closed Jul 2023 | Al Raha channel, Abu Dhabi (≈24.45 N, 54.61 E) | Non-toxic species in July tests [V] | None; optically shallow channel | The National (2023-10-09) |
| 3 | Siri-field crude slick drifting toward UAE waters | S1A 8 and 11 Mar 2017 | South of Siri Island, Iranian sector (≈25.9 N, 54.5 E) | 334→620 km² (SkyTruth); 486→783 km² (ScanEx) [V] | Sentinel-1 figures only | SkyTruth; ScanEx; Mar. Pollut. Bull. 2024 |
| 4 | MOCCAE-announced bloom (mixed phytoplankton, low biomass) | Announced 23–25 Jan 2018; dissipated ~26 Jan | ~20 km offshore, Kalba→Dibba and RAK→Dubai | Satellite chlorophyll plus water samples; no harmful species [V] | None | The National; Khaleej Times; Al Bayan (2018) |
| 5 | Diesel spill after a ship collision | Collision Oct 2019; Sentinel-1 slick 31 Oct 2019, 54.8 km² | Fujairah–Kalba (study centroid 25.281 N, 56.483 E [V]) | 3 km of shore oiled; ships impounded; damages awarded [V] | Sentinel-1 figure (Al Teneiji et al. 2024) | GISTAM 2024; The National |
| 6 | Saadiyat Beach algal bloom (irritant dinoflagellate) | Beach closure reported 13 May 2018 | Saadiyat Island (≈24.54 N, 54.43 E) | EAD sampling [V] | None | The National (2018) |
| 7 | "Greenish seawater" off Fujairah | FEA statement 24 Apr 2026 (onset not given) | Fujairah coast | FEA: non-harmful algae; species not named [V] | None found | Khaleej Times (2026) |
| 8 | Red-tide patch (dinoflagellates) | ~30 Sep 2019 [U], lasted a day | Off Al Jazira Al Hamra, RAK (≈25.7 N, 55.8 E) | Fishermen and MOCCAE statements [V] | None | The National; Khaleej Times (2019) |
| 9 | Slicks off the east coast | Sentinel-1 12 Aug 2022 (13.1 km²) and 16 Aug 2022 (164.9 km²) | Off Fujairah / Khor Fakkan | Cause inconsistent in the paper [U] | Sentinel-1 figures | GISTAM 2024 |
| 10 | Fluorescent *N. scintillans* | Nov–Dec 2023 | Kalba | Sharjah EPAA, personal communication in a 2025 paper | None | Front. Mar. Sci. 2025 |
| 11 | "Ghost" slick linked to 39 sea-snake deaths | Nov 2021 | Kalba | Peer-reviewed necropsies [V]; slick date/extent unknown | None | Sci. Total Environ. 2022 |

**Lower-usability records** (for context and SAR search windows): oil on
beaches at Fujairah (26 Jan 2018), Al Aqah (1 Mar 2020), Khor Fakkan (29 Jun
2020, 19 May 2025), Kalba (26 Jul 2020, 25 Aug 2020), Al Aqah / Snoopy Island
(≈18 Oct 2024) — sheens too thin for optical sensors; a fish kill in Abu Dhabi's
Al Muzoon canal (2 Dec 2025, EAD); EAD's record of 268 algal-bloom incidents in
2002–2018, mostly in the Mussafah channels; *Noctiluca* images off Oman in the
Gulf of Oman (S2B 15 Feb 2019; S2 14 Mar 2019, Gernez et al. 2023; PACE 17 Mar
2024; Landsat-8/PACE 8 Mar 2025; S2 30 Mar 2025).

## What the literature says about detecting these from space

* Seabed reflectance in water shallower than ~20 m degrades standard
  ocean-colour algorithms more than sediment does (Al Shehhi et al. 2017,
  *J. Photochem. Photobiol. B* 175:235).
* Satellite chlorophyll in the Gulf is consistently overestimated against
  in-situ stations and sees only the top 6–10 m (Al-Naimi et al. 2017,
  *Remote Sens.* 9:301).
* For the 2008 *Cochlodinium* bloom, fluorescence outperformed chlorophyll
  anomalies but was sensitive to aerosol and benthic vegetation (Zhao et al.
  2015, *ISPRS J.* 101:125).
* MOCCAE's 2008–2018 bloom log: blooms declined on the Gulf coast and rose in
  the Sea of Oman; they peak November–April and are most frequent at Dibba
  (Al-Shehhi et al. 2021, *Ocean Coast. Manage.* 213:105840).
* Sentinel-2 red-tide optical types, including green *Noctiluca* in the Oman
  Sea on 14 Mar 2019 (Gernez et al. 2023, *RSE* 287:113486).
* Sentinel-2 L2A chl-a/TSS models against EAD in-situ data in Abu Dhabi reached
  R² 0.65–0.70 / 0.61 and under-predicted bloom peaks (Ibrahim et al. 2026,
  *Front. Mar. Sci.* 13:1787597).
* Sen2Cor "is designed for land with no water application as part of its
  specification"; across processors, red/NIR errors over coastal water were
  often above 1000 % (Warren et al. 2019, *RSE* 225:267).

## How BLUEBAN uses the register

1. **Search windows.** The WATCH screen and DETECT are run over the whole
   2017–2026 archive; the register says where the product *should* find
   something, which is a direct check on the detector.
2. **Honesty in the positive case.** A detection that coincides with a
   register entry is reported with that entry as *context* ("FEA reported
   greenish water attributed to non-harmful algae"), not as BLUEBAN's own field
   confirmation.
3. **Negative evidence.** An entry the detector misses is reported as a miss,
   with the reason (cloud, glint, resolution, sheen too thin for optics).
