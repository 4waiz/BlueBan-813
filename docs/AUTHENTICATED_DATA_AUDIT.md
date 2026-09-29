# Authenticated Data Audit (re-audit from scratch)

**BLUEBAN 813** · Team Kanban · started 2026-09-30

This audit replaces the 2026-09-15 conclusions (archived at
[`archive/DATA_ACCESS_AUDIT_2026-09-15.md`](archive/DATA_ACCESS_AUDIT_2026-09-15.md))
that gIQ was unavailable, that Satellite 813 was not practically available and
that the in-situ records could not be downloaded. The team now holds an
authenticated gIQ account and Cockpit dataset cards for **813 Aquatic
Hyperspectral**, **Sentinel-3 OLCI**, **Landsat 8/9** and **In-situ WQ records**,
so every one of those conclusions is re-tested here.

## Status: PENDING a team member's sign-in

| Resource | Status on 2026-09-30 | Why |
|---|---|---|
| Hackathon platform (`spaceacademy-hackathons.space.gov.ae`) | **Not yet inspected** | The automation browser is a separate profile and lands on the sign-in page, which uses an emailed one-time code. Signing in is a team member's action. |
| gIQ (`giq.ae`) | **Not yet inspected** | Same: redirected to `LOGIN`. |
| Claude-in-Chrome (the team leader's own signed-in Chrome) | **Not connected** | The extension reported "not connected". |

**What unblocks it** (either one):

1. Connect the Claude in Chrome extension to the team leader's Chrome, where
   both sites are already signed in; or
2. Sign in by hand in the automation browser window: on the platform tab enter
   the team e-mail, press **Send sign-in code**, enter the code; on the gIQ tab
   press **LOGIN**.

Until then **no conclusion about 813, gIQ or the in-situ card is drawn in
either direction.** The product treats 813 as SIMULATED and in-situ data as
ABSENT, and says so, because that is the state of the data the code can
actually read today.

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

*To be completed during the authenticated session.* Sections to fill:

1. Cockpit: dataset cards, their controls, and what each control returns.
2. Data / Tasks / Prep Training pages.
3. gIQ: Explore & Visualize, Data Directory, available imagery and reference
   data for the UAE AOIs.
4. Satellite 813: accessible or not; if accessible, product, units, bands,
   coverage and dates over the candidate AOIs.
5. In-situ WQ records: accessible or not; if accessible, stations, dates,
   parameters, units and QC, and how many matchups they yield with Sentinel-2.
6. Revised conclusions vs the 2026-09-15 audit.
