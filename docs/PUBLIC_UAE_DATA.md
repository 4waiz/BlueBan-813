# Public UAE Water-Quality Data: What Exists and What It Can Be Used For

**BLUEBAN 813** · Team Kanban · searched 29–30 September 2026

This is the public-source half of the data re-audit (the authenticated half is
[`AUTHENTICATED_DATA_AUDIT.md`](AUTHENTICATED_DATA_AUDIT.md)). The question was
narrow: **is there any public, per-sample UAE coastal measurement of
chlorophyll-a, turbidity or TSS, with coordinates and a date, that can be
matched to Sentinel-2 or Sentinel-3?**

A usable calibration record needs latitude, longitude, measurement date and
time, parameter, value, unit and quality information. A monitoring-site
location is not a measurement. An annual average is not a same-day matchup.

---

## Answer: no public per-sample UAE coastal dataset exists

| Source | Verdict | What it is |
|---|---|---|
| EAD marine water-quality programme (per-sample records, buoys) | **NOT ACCESSIBLE** (request only) | The data exists and is exactly what calibration needs, but it is confidential to the Environment Agency – Abu Dhabi |
| MOCCAE sea-water monitoring stations (ArcGIS FeatureServer) | **CONTEXT ONLY** | Annual station means 2015–2023 with station coordinates |
| Bayanat "Parameters of sea water quality (2015–2023)" | **CONTEXT ONLY** | The same annual means, without coordinates |
| SCAD Marine Water Quality statistics (quarterly) | **CONTEXT ONLY** | Quarterly means of EAD stations, without coordinates or dates |
| AD-SDI `MarineWaterQuality_AutomatedBuoys`, `MarineWaterQualitySampleSites`; EAD monitoring-station layers | **LOCATIONS ONLY** | Site and buoy positions; no values, no times |
| BGC-Argo float 6990700 (Ifremer ERDDAP) | Usable for matchups **offshore Oman only** | Fluorescence chlorophyll profiles, 2025-04 to 2026-09, 22.5–24.9 N, 58.1–60.4 E |
| Glider sea057 (OceanGliders ERDDAP) | Usable for matchups **offshore Muscat only** | 2021–2022 deployments |
| Cormorant bio-logging SST (Zenodo 15427503, CC-BY-4.0) | Usable for **temperature** only | 863 451 dives, 2020–2024, southern Gulf |
| AERONET-OC, SeaBASS, GLORIA, Valente compilation, PANGAEA | **No Sentinel-era Gulf data** | Checked; nothing in 22–27 N, 51–57.5 E after 2015 |

### Consequence for the product

Without per-sample reference measurements, **BLUEBAN 813 cannot report a
calibrated chlorophyll-a, turbidity or TSS value for UAE waters**, and it does
not. It reports documented proxies (NDCI, MCI, FAI, red-edge ratio, hue angle)
and published semi-analytical estimates labelled `GENERIC_CALIBRATION, not
locally validated` (Nechad 2016, Dogliotti 2015). The calibration machinery
(`pipeline/matchup.py`, `pipeline/quantify.py`) is built, tested and waiting
for the EAD records or the hackathon's in-situ card; the day matched records
arrive, the same code produces a grouped-validated estimate with an interval,
or explains why it still cannot.

---

## 1. EAD per-sample monitoring data — the source that matters

* **Programme** (EAD Marine Water Quality Annual Summary Report 2022): running
  since 2006; 23 sites in 9 categories in 2022; Abu Dhabi City sites sampled
  monthly, Al Dhafra quarterly; 228 samples in 2022. A multiparameter sonde
  measures temperature, salinity, DO, chlorophyll-a and pH at surface and
  bottom; the laboratory measures nutrients, TSS, BOD, metals and bacteria.
  Nine automated buoys record salinity, conductivity, temperature, pH, DO,
  chlorophyll and cyanobacteria every 15 minutes.
  `https://www.ead.gov.ae/-/media/Project/EAD/EAD/Documents/KnowledgeHub/Resources-and-Materials/Marian-Water-Quality-_ANNUAL-REPORT-2022.pdf`
* **Proof the records exist and work with Sentinel-2:** Ibrahim et al. (2026),
  *Front. Mar. Sci.* 13:1787597, doi:10.3389/fmars.2026.1787597. 22 sites,
  2023-01-25 to 2024-12-18; n = 365 chl-a, 196 TSS, 128 turbidity; 165 chl-a
  and 77 TSS Sentinel-2 L2A matchups within ±1 day; grouped models reached
  R² 0.65–0.70 (chl-a) and 0.61 (TSS). The paper's data statement: *"The
  in-situ dataset is confidential with the Environment Agency-Abu Dhabi (EAD)."*
* **How to request:** EAD research guidance (EAD-TMBS-TG-02) directs data
  requests to `eimsupport@ead.ae`, stating type, location, period and format;
  EAD must be acknowledged and a draft publication shared for approval. This
  guidance is from 2016 and may have changed. **A draft request is in
  §7 for the team to send; BLUEBAN does not send it on the team's behalf.**
* EAD's internal ArcGIS folder `https://edp.ead.ae/server/rest/services/MWQ`
  returns *Token Required*. It was not probed further.

## 2. MOCCAE sea-water monitoring stations — context, with coordinates

* Service:
  `https://gis.moccae.gov.ae/server/rest/services/marine_research/monitoring_Stations_for_Gulf_waters_2015_2022/FeatureServer/0`
* 106 rows: one per station per year, 2015–2023 (stations ECS1–4 on the Gulf of
  Oman, WCS1–10 on the Arabian Gulf). Annual means of nutrients, chlorophyll-a
  (46 non-zero values, 2020–2023, 0.50–2.03 µg/L), salinity, temperature, pH,
  DO and others.
* Data-quality notes: missing values stored as 0.0; station WCS9 has latitude
  5.5 in 2023; station WCS1's longitude in 8 of 9 years equals ECS3's.
* **Not ingested.** The server rejects scripted clients. We did not work around
  that. If the station coordinates are wanted, a team member can export the
  106-row table from the MOCCAE geospatial portal in a browser.

## 3. Bayanat — "Parameters of sea water quality (2015–2023)" — context

* Page: `https://bayanat.ae/en/Datasets/Dataset-info?id=e72fRWQiUdryBqhMBw0SmbVS4e_o_N6ylNNt6aK4oPM`
  (publisher MOCCAE, updated 2024-09-26, licence **CC BY-SA**).
* Direct XLSX (public, no sign-in):
  `https://bayanat.ae/api/DatasetResources/DownloadSingle?resourceID=3fw8_28LcRRSQC7ivfZc_K5nzsX8yx04IcdrQ3UrJI0&fileName=Parameters%20of%20sea%20water%20quality`
* 126 rows (14 stations × 2015–2023), annual means; Fujairah, Sharjah (incl.
  Khor Fakkan, Kalba, Hamriyah), Ajman, Umm Al Quwain, Ras Al Khaimah and
  Dubai. **No Abu Dhabi rows, no coordinates, no dates.** Chlorophyll-a exists
  only for 2020–2023. Used in BLUEBAN only as seasonal context for WATCH.

## 4. SCAD Marine Water Quality statistics — context

* Quarterly XLSX releases, e.g. Q1 2026:
  `https://scad.gov.ae/w/marine-water-quality-statistics-quarterly-first-quarter-2026`
* Quarterly means for 18 EAD stations grouped by category, marked
  "preliminary". Chlorophyll values (0.8–7.4) are labelled mg/l but are
  consistent with µg/L; this should be confirmed with SCAD before any use.
  Reuse permitted with the credit *"Source: Statistics Centre – Abu Dhabi"*.

## 5. Location-only layers (join keys, not data)

* AD-SDI open data, layers 170 (`MarineWaterQuality_AutomatedBuoys`, 11 points)
  and 171 (`MarineWaterQualitySampleSites`, 39 points):
  `https://arcgis.sdi.abudhabi.ae/agspublish/rest/services/OpenData/ADSDI_OpenData/MapServer/<id>`
* EAD Enviroportal monitoring stations, layers 1 (77 sampling sites) and 2 (12
  buoys): `https://edp.ead.ae/server/rest/services/Enviroportal/MonitoringStations/MapServer/<id>`
* These are used in the product to draw **monitoring stations** on the map and
  to join future EAD records to positions. They are never displayed as
  measurements.

## 6. Offshore per-sample chlorophyll (not UAE coastal)

* **BGC-Argo** (Ifremer ERDDAP, `ArgoFloats-synthetic-BGC`): only two floats in
  22–27 N, 51–60.5 E since mid-2015. Float 6990700: 61 profiles, 2025-04-24 to
  2026-09-24, 22.5–24.9 N, 58.1–60.4 E, off Oman, ~200 km from Fujairah.
  Chlorophyll is fluorescence-derived (`chla_adjusted` with QC flags).
* **Glider sea057** (OceanGliders ERDDAP): 2021-11 to 2022-03 and 2022-07 to
  2022-10 off Muscat.
* Suitable for Sentinel-3 OLCI matchups offshore; Sentinel-2 does not image that
  open ocean. They say nothing about UAE coastal water.

## 7. Draft request to EAD (for the team to send, not sent)

> Subject: Research data request – marine water-quality monitoring records
>
> Dear EAD Environmental Information team,
>
> We are Team Kanban, participants in the UAE Space Agency's Arab Youth Space
> Hackathon 2026 (813 Challenge, water quality). We are developing an
> open-source method that calibrates Sentinel-2 observations of Abu Dhabi
> coastal waters against in-situ measurements, following the approach of
> Ibrahim et al. (2026, *Frontiers in Marine Science* 13:1787597), which used
> EAD's monitoring records.
>
> We would be grateful for access to the per-sample marine water-quality
> monitoring records for 2019–present: site code, latitude/longitude,
> sampling date and time, depth, parameter, value, unit and QC flag, for
> chlorophyll-a, turbidity, TSS, temperature and salinity; and, if possible,
> the 15-minute automated buoy series for the same period. CSV or XLSX would be
> ideal. We will acknowledge EAD in all outputs, will not redistribute the
> records, and will share any draft publication with EAD for approval.
>
> Kind regards, Team Kanban

---

## Sources

* EAD (2022) Marine Water Quality Annual Summary Report.
* Ibrahim et al. (2026) *Front. Mar. Sci.* 13:1787597.
* MOCCAE Environmental Geospatial Platform; Bayanat (CC BY-SA); SCAD quarterly
  statistics; AD-SDI and EAD Enviroportal map services.
* Ifremer ERDDAP (BGC-Argo, OceanGliders); Zenodo 15427503 (cormorant SST);
  Copernicus Marine In Situ TAC product INSITU_GLO_PHYBGCWAV_DISCRETE_MYNRT_013_030.
* AERONET-OC site list; NASA SeaBASS; GLORIA (PANGAEA.948492); Valente et al.
  v3 (PANGAEA.941314).
