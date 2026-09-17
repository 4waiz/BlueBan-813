# Area of Interest Selection

**Selected AOI: Gulf of Annaba, Algeria**
`bbox 7.5175, 36.8739, 7.8093, 37.0599` (EPSG:4326) — 26.13 × 20.91 km

This document records how that choice was made, which alternatives lost, and on
what evidence. The brief we set ourselves was explicit: **data quality and
validation potential outrank preferred geography.**

---

## 1. Method

The primary hyperspectral sensor available to us in this phase is Planet
Tanager-1 (see `DATA_ACCESS_AUDIT.md`). Tanager is a tasked instrument with a
sparse open archive, so the AOI is constrained by where Tanager has actually
imaged coastal water — not by where we would like to work.

We enumerated **every item in the Tanager open STAC catalog**: 236 items across
six themed collections, of which **43 are in `coastal-water-bodies`**. Of those
43, exactly **four** fall in the MENA / Arab region:

| Scene | Date | Location | Cloud | Footprint |
|---|---|---|---|---|
| `20250601_104901_58_4001` | 2025-06-01 | **Algeria (Gulf of Annaba)** | **0 %** | 7.517–7.809 E, 36.874–37.060 N |
| `20250606_090504_75_4001` | 2025-06-06 | Red Sea, Egypt | 7 % | 33.537–33.771 E, 27.566–27.746 N |
| `20250926_092059_95_4001` | 2025-09-26 | El Gouna, Red Sea, Egypt | 8 % | 33.511–33.758 E, 27.334–27.565 N |
| `20250511_074311_00_4001` | 2025-05-11 | **Tarif, Abu Dhabi, UAE** | **51 %** | 53.632–53.894 E, 23.990–24.192 N |

Each candidate was then scored on the criteria that actually determine whether a
PoC can produce a defensible result.

---

## 2. Decision matrix

| Criterion | **DZ Annaba** | EG Red Sea | AE Abu Dhabi |
|---|---|---|---|
| Tanager cloud cover | **0 %** | 7 % / 8 % | 51 % |
| Tanager usable pixels | **68.4 % of array; 0.08 % cloud** | not evaluated (lost earlier) | **38.6 %** — published in the official notebook |
| Sentinel-2 coincidence | **0.64 h** (38 min) | 47 h / 1.06 h | 24.8 h |
| Coincident S2 cloud | **0.0003 % and 0.0009 %** | 0.87 % / 0.06 % | 7.6 % |
| Landsat coincidence | **24.7 h @ 0.04 % cloud** | 72.9 h | 95.2 h |
| Sentinel-3 OLCI coincidence | 23.3 h | 1.32 h / none | 1.43 h |
| S2 archive depth (2025) | **413 scenes, 143 < 10 % cloud** | 88 / 72 | 88 / 57 |
| OLCI baseline depth 2022–25 | **993 scenes** | 921 | 875 |
| Landsat 2025 | 86 (40 clear) | 89 (68 clear) | **41 (26 clear)** |
| Single contiguous AOI | **Yes** | No — two abutting, non-overlapping footprints | Yes |
| **Verdict** | **SELECTED** | Runner-up | Rejected |

### Why Abu Dhabi lost, despite being the "obvious" choice

We wanted a UAE AOI. The only Tanager coastal-water scene over the UAE is
**51 % cloud with 38.6 % valid pixels** — that figure is not our estimate, it is
printed in the official challenge notebook's own output for this exact scene.
Two thirds of the imaged area is unusable, and the remaining third is
perforated with cloud holes.

Building the flagship demonstration on a scene that is two-thirds unusable
would have meant either showing a hole-ridden hero map, or quietly cropping to
the clear part and not mentioning why. Neither is defensible. **We chose the
data over the flag**, and say so.

### Why Egypt lost

Genuinely strong runner-up, and the Red Sea tourism/desalination story is
compelling. Two things beat it:

1. **The footprints do not overlap.** Scene A covers 27.566–27.746 N, scene B
   covers 27.334–27.565 N. They abut at 27.565/27.566. Two dates over *adjacent*
   ground is not a repeat pass, so it yields no same-pixel hyperspectral change
   detection — the thing that would have justified the split.
2. **No single date has strong coincidence across the cascade.** Scene A has
   OLCI at 1.3 h but Sentinel-2 only at 47 h; scene B has Sentinel-2 at 1.1 h
   but no OLCI within ±1 day. Annaba gets Sentinel-2 at 38 minutes *and*
   Landsat at 24.7 h *and* OLCI at 23.3 h on one footprint.

---

## 3. Why the Gulf of Annaba is the right AOI on its merits

### 3.1 The 38-minute coincidence is the decisive asset

| Sensor | Acquisition | Δt from Tanager | Cloud |
|---|---|---|---|
| **Tanager-1** (426 bands, 30 m) | 2025-06-01 10:49:01 Z | — | **0 %** |
| **Sentinel-2C** T32SLF | 2025-06-01 10:10:41 Z | **−38 min** | **0.0003 %** |
| **Sentinel-2C** T32SLG | 2025-06-01 10:10:41 Z | **−38 min** | **0.0009 %** |
| Landsat-9 193/034 | 2025-05-31 10:06:22 Z | −24.7 h | 1.09 % |
| Landsat-9 193/035 | 2025-05-31 10:06:46 Z | −24.7 h | 0.04 % |
| Sentinel-3B OLCI WFR | 2025-06-02 10:06:34 Z | +23.3 h | 16 % |

Thirty-eight minutes, both sensors effectively cloud-free, is close enough that
the water has not meaningfully changed. That turns the multispectral-versus-
hyperspectral comparison from an argument into a **controlled measurement**: the
same water, the same atmosphere, the same illumination, observed by a
multispectral and a hyperspectral instrument almost simultaneously. Very few
AOIs anywhere offer that.

### 3.2 The scene itself is excellent

Measured from the file, not assumed:

| Property | Value |
|---|---|
| Valid pixels | 68.38 % of the array (the remainder is the 19.9° off-nadir rotation border, not cloud) |
| Cloud | **0.08 %** |
| Cirrus | **0.0002 %** |
| Aerosol optical depth | mean 0.112 — clean atmosphere |
| Column water vapour | mean 1.39 g/cm² |
| Sun zenith | 16.98° (sun elevation 73°) — excellent illumination |
| Sensor zenith | 19.91° |
| Bands flagged good by the product | 368 of 426 |
| **Open water pixels after masking** | **209 077 → 188.2 km² of analysable water** |

### 3.3 The water is optically interesting, in a useful way

The scene contains both ends of the optical range in one frame:

* **Deep, clear Mediterranean water offshore** — an excellent, large, stable
  background population for anomaly detection (186 578 offshore pixels).
* **A turbid inner-gulf zone along the Annaba waterfront** — the anomaly.

Measured mean offshore water reflectance shows a textbook clear-water shape,
monotonically decreasing from blue to NIR:

| 411 nm | 441 nm | 491 nm | 561 nm | 621 nm | 666 nm | 706 nm | 866 nm |
|---|---|---|---|---|---|---|---|
| 0.0782 | 0.0633 | 0.0452 | 0.0210 | 0.0105 | 0.0074 | 0.0067 | 0.0056 |

High dynamic range against a clean, uniform background is exactly the condition
under which an anomaly detector can be demonstrated honestly.

### 3.4 Real, documented land-based pressure

The Gulf of Annaba receives the **Seybouse River**, one of Algeria's major
river systems draining an intensively farmed and industrialised catchment, and
hosts the **port of Annaba** plus heavy industry on its shore. It is a coastline
where episodic sediment and nutrient loading is a genuine, recurring management
question — not a hypothetical one.

> We deliberately do **not** name specific industrial operators as pollution
> sources. Attributing an observed optical anomaly to a named facility is not
> something satellite imagery can support, and BLUEBAN 813 never does it. See
> `LIMITATIONS.md`.

### 3.5 Regional relevance is preserved

Algeria is an Arab League member state and the AOI is Mediterranean MENA coast.
The operational problem — protecting coastal water intakes and bathing water
from episodic land-derived plumes — is the same problem faced across the Gulf,
the Red Sea and the Maghreb. The method is portable; the demonstration simply
happens where the data is best.

---

## 4. What we found there

The AOI delivered a real result rather than a contrived one. RX anomaly
detection over the 209 077 water pixels, thresholded at an empirically
calibrated 1 % background false-alarm rate, produced **7 event regions totalling
4.94 km²**, concentrated in a ~5 km coastal band along the Annaba waterfront:

| Region | Area km² | Centroid (lat, lon) | Median distance from shore |
|---|---|---|---|
| L4 | 3.136 | 36.9307, 7.7722 | 247 m |
| L7 | 1.129 | 36.8857, 7.7699 | 90 m |
| L6 | 0.257 | 36.9011, 7.7725 | 42 m |
| L3 | 0.231 | 36.9520, 7.7059 | 95 m |
| L1 | 0.095 | 36.9652, 7.6389 | 60 m |
| L2 | 0.068 | 36.9563, 7.7824 | 67 m |
| L5 | 0.024 | 36.9253, 7.7769 | 582 m |

The strongest region, L7, shows **5.3× background reflectance at 561 nm and
5.3× at 666 nm but only 1.4× at 443 nm** — broadband green/red elevation with a
weak blue response, which is the characteristic shape of mineral suspended
matter rather than of algal pigment.

Because these regions are nearshore, **bottom reflectance in shallow water is a
serious competing explanation**, and one that a single date cannot rule out.
That is precisely why the pipeline includes a multi-year Sentinel-2 baseline:
bottom reflectance is permanent and sits mid-distribution on every clear date,
whereas a plume sits in the upper tail. The test and its result are in
`VALIDATION_REPORT.md`.

---

## 5. Reproducing the selection

```bash
python scripts/discover_data.py --inventory   # enumerate all 236 Tanager items
python scripts/choose_aoi.py                  # rebuild the decision matrix above
```

Both write their raw outputs to `data/metadata/`, so the table in section 2 can
be regenerated and checked rather than taken on trust.
