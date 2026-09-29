# Authenticated Data Audit (re-audit from scratch)

**BLUEBAN 813** · Team Kanban · started 2026-09-30

This audit replaces the 2026-09-15 conclusions (archived at
[`archive/DATA_ACCESS_AUDIT_2026-09-15.md`](archive/DATA_ACCESS_AUDIT_2026-09-15.md))
that gIQ was unavailable, that Satellite 813 was not practically available and
that the in-situ records could not be downloaded. The team now holds an
authenticated gIQ account and Cockpit dataset cards for **813 Aquatic
Hyperspectral**, **Sentinel-3 OLCI**, **Landsat 8/9** and **In-situ WQ records**,
so every one of those conclusions is re-tested here.

## Status: COMPLETED 2026-09-30 (team leader signed in; inspected by the team's automation browser)

| Resource | Result |
|---|---|
| Hackathon platform: Cockpit, Dashboard, Tasks, Onboarding, Prep Training | Inspected |
| gIQ: Home, Explore, Data Directory (Uploaded / Sharing / Generated / Exports), Reference Data, Models, Acquire (view only) | Inspected |
| Paid actions (gIQ Buy / Tasking / Orders, Marketplace purchases) | **Not touched** |

## Access rules for this audit

Allowed: the team's existing participant access, normal page navigation, and
normal download/export buttons for datasets already included in the hackathon
entitlement.

Never: extracting passwords, cookies or tokens; bypassing access controls or
bot challenges; purchasing data; placing a paid imagery order; triggering a
commercial acquisition. If a control appears to cost money or place an order,
the audit stops and asks the team.

## Storage rules

* Authenticated or restricted raw data goes only to `data/raw/private/`, which
  is gitignored (`.gitignore` line `data/raw/private/`), as is all of
  `data/raw/`.
* Restricted imagery, credentials, tokens, large HDF5/NetCDF files and
  restricted field data are never committed. Derived, non-restricted outputs
  and metadata records may be.

## Record kept for every file obtained

Each download gets a JSON sidecar in `data/metadata/private/` (gitignored if it
reveals restricted content) with:

| Field | Meaning |
|---|---|
| provider | e.g. UAE Space Agency hackathon platform, gIQ / Space42 |
| source_page | page and control used |
| sensor, product, processing_level | as stated by the provider and as read from the file |
| scene_id, acquisition_time_utc | from the file's own metadata |
| download_time_utc, file_size_bytes, sha256 | computed locally |
| licence, access_restriction | as stated on the page / in the file |
| projection, resolution_m | from the file (CRS, transform) |
| units, quantity | read from the file: radiance vs reflectance vs Rrs, scale and offset |
| bands | centres, widths, count, bad-band flags |
| quality_masks, nodata | as provided |

For the **813 product specifically**, the Cockpit card says *"Optimized bands
for water-leaving radiance"*. The first thing read from any 813 file is its
declared quantity and units. If it is water-leaving radiance (Lw,
W m⁻² sr⁻¹ µm⁻¹), no reflectance index is computed on it until a documented
Lw → Rrs conversion (which needs downwelling irradiance) is in place;
`pipeline/satellite813_real.py` refuses to proceed otherwise.

## Results

### 1. Cockpit dataset cards: still informational only

The four cards read, verbatim: *813 Aquatic Hyperspectral - GeoTIFF - on-demand -
Optimized bands for water-leaving radiance*; *Sentinel-3 OLCI - NetCDF -
on-demand - Ocean colour and coastal water quality*; *Landsat-8/9 OLI-TIRS -
GeoTIFF - on-demand - Thermal + optical for surface temperature*; *In-situ WQ
records - CSV - variable - Ground-truth for select MENA water bodies*.

Checked in the live DOM, not just the accessibility tree: each card's list item
has **no anchor, no button or input, no pointer cursor, no inline handler and no
data attributes**. There is nothing to click. "On-demand" can only mean a
request to the organisers, whose channel on the platform is the Cockpit's
*Mentor & Organizer Chat*. The Data providers & tools section links only to
public providers (Copernicus Data Space, Planetary Computer, USGS, Planet,
Planet STAC, EnMAP, ESA WorldCover, STAC spec, geojson.io).

### 2. Programme rules: unchanged

The Onboarding guide's phase table is unchanged since 15 September: in the PoC
phase, open multispectral and hyperspectral data and the Planet Tanager open
archive only; *no commercial Planet data*, *no gIQ access*, *no guaranteed
Satellite 813 or MBZ-SAT data*. Section 07 still reads: *"Satellite 813 &
MBZ-SAT - INCUBATION ONLY, UPON AVAILABILITY ... do not design a PoC that
depends on this data."* The learning track now lists 6 items (two new since the
last audit: a Week-2 time-series notebook and "Orientation session 29-9"
slides, whose viewer reports *"No PDF URL configured"*). The Cockpit countdown
put the PoC deadline at 16 d 22 h from 2026-09-30 01:21 GST, i.e. about
**2026-10-17 00:00 GST**. Dashboard: no announcements. Tasks: the team's own
empty board.

### 3. gIQ: access works, but holds no 813 and no in-situ data

Contrary to the programme table ("no gIQ access" in the PoC phase), the team
leader's gIQ login works. What it contains:

| Module | Content on 2026-09-30 |
|---|---|
| Data Directory - Uploaded files | 2 items, both uploaded by other accounts on the (apparently shared) hackathon tenant: a Sentinel-1C IW GRDH scene (VV+VH, 13 Sep 2026 15:56 UTC, 842.8 MB) whose footprint is the **Nile Delta, Egypt** (29.7-32.7 E, 30.1-32.6 N), ingested by the organiser; and a polygon GeoJSON belonging to another participant. Neither covers the UAE; the second is not ours and was not downloaded. |
| Data Directory - Shared with us | Empty |
| Explore | Only the two layers above |
| Models | 0 |
| Reference Data | Empty |
| Acquire (viewed, nothing searched or ordered) | Vendors Airbus, Capella, ICEYE, Planet, Space42, Umbra and MBRSC, each priced (EUR/USD/AED), plus free archives for Sentinel-1, Sentinel-2 and Landsat. **No Satellite 813 vendor or product.** |

### 4. Satellite 813: NOT accessible

Neither the platform nor gIQ exposes any Satellite 813 product, file, layer,
share or order path for this team on 2026-09-30. BLUEBAN 813 therefore keeps
the 813 **simulator** as its hyperspectral path, labelled SIMULATED everywhere,
and `pipeline/satellite813_real.py` stays a documented, tested reader waiting
for a product.

### 5. In-situ WQ records: NOT downloadable

No file, link or API. The route is a request through the Cockpit chat. A draft
request (below) is prepared for the team; **nothing has been sent on the team's
behalf.** Public alternatives were exhausted separately in
[`PUBLIC_UAE_DATA.md`](PUBLIC_UAE_DATA.md).

### 6. Revised conclusions vs the 2026-09-15 audit

| 2026-09-15 conclusion | 2026-09-30 re-test |
|---|---|
| gIQ unavailable | **Changed:** login works; nothing in it serves this project today |
| Satellite 813 not practically available | **Confirmed** by direct inspection of both platforms |
| In-situ records not downloadable | **Confirmed**; request route identified (Cockpit chat) |
| Sentinel-3 OLCI via Planetary Computer | **New limitation:** Planetary Computer's OLCI WFR archive over the UAE ends 2026-02-23 (`outputs/aoi/census.json`); later OLCI needs the organisers' on-demand card or a CDSE account |

### Draft organiser request (for the team to send in the Cockpit chat)

> Hello, this is Team Kanban (Water Quality). We would like to request three
> of the on-demand datasets listed in our Cockpit, for the UAE coast:
> (1) **In-situ WQ records** for UAE coastal waters (chlorophyll-a, turbidity,
> TSS, temperature, salinity; with station coordinates, sampling date/time,
> units and QC), any period from 2019;
> (2) **Sentinel-3 OLCI** Level-2 WFR for the Gulf of Oman coast (Fujairah,
> Kalba, Khor Fakkan) and Abu Dhabi coast, March-September 2026;
> (3) any **813 Aquatic Hyperspectral** acquisition over those coasts, with its
> radiometric unit definition (Lw vs Rrs), band table and quality flags.
> We will keep restricted data out of our public repository. Thank you!
