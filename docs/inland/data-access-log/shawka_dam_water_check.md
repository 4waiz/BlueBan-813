# Shawka Dam AOI — water presence flag (briefing Section 9, item 5)

**Method:** for each of the 14 monthly Sentinel-2 L2A scenes selected for
the baseline (Sept 2023 – Oct 2025, one per month, lowest cloud cover),
NDWI = (Green − NIR)/(Green + NIR) was computed per 10 m pixel across the
full `aoi/shawka_dam.geojson` bbox window (2,806 pixels/scene), not just
the AOI-mean value — because a mean over a mostly-dry AOI can hide a
small wet patch. Full per-scene table: `data/shawka_dam_water_presence.csv`.

## Finding: the AOI does show real, usable water — but it is small, seasonal, and shrinking in the most recent scenes

| Period | % of AOI pixels with NDWI > 0 | % with NDWI > 0.1 (stricter open-water) |
|---|---|---|
| Sep–Oct 2023 | 6.5–6.7% | 4.9–5.2% |
| **Nov–Dec 2023 (peak)** | **8.6–16.1%** | **6.8–13.6%** |
| Jan–Feb 2024 | 7.7–8.9% | 5.9–7.6% |
| Sep 2024–Feb 2025 | 1.7–12.2% | 0.5–8.5% |
| **Sep–Oct 2025 (most recent)** | **0.2–1.0%** | **0.0%** |

- **The AOI mean NDWI is negative in every single one of the 14 scenes** (range −0.06 to −0.13) — confirming the briefing's caveat that the traced polygon follows the wadi *channel*, not the wet extent, and a naive AOI-mean check would read as "no water" every time.
- **But a real, persistent wet core exists inside the polygon**: max per-pixel NDWI reaches 0.41 (Nov 2023) and stays positive (0.15–0.33) through most of the 14 months, meaning a genuine standing-water patch — consistent with a small dam pool — is present and trackable at the pixel level even though it's a small minority of the AOI.
- **The wet fraction is not stable — it trends down sharply in the two most recent scenes available** (Sept 2025: 1.0% wet, max NDWI 0.074; Oct 2025: 0.2% wet, max NDWI 0.025, and 0 pixels above the stricter 0.1 threshold). This is the most recent imagery available in Phase 2 access, so **as of now, the AOI is close to fully dry.**

## Recommendation

Don't discard the AOI or fully replace it — the peak-season data (esp.
Nov 2023–Feb 2025) is genuinely usable and shows a repeatable wet-pixel
cluster we can isolate and tighten the polygon around for Section 3
onward. But two follow-ups are worth doing before committing further
build time to Shawka Dam alone:

1. **Tighten the AOI** to the sub-polygon where NDWI > 0.1 recurs across
   the wettest months (a ~150–450-pixel core, not the full 2,806-pixel
   channel trace) — this both improves signal-to-noise for the
   hyperspectral unmixing step and gives a cleaner "is there water right
   now" check per incoming scene.
2. **Identify one backup inland candidate AOI** in case the current fall
   /winter 2026 season stays as dry as the last two available scenes —
   another UAE Ministry of Energy & Infrastructure dam with a more
   reliably wet reservoir would de-risk the inland half of the
   submission. This is flagged as an open decision, not resolved here,
   per the briefing's instruction to flag it rather than decide it
   unilaterally.

Sentinel-3 OLCI WFR (300 m) is confirmed unusable for this AOI regardless
of season — all 6 sampled scenes returned 0 valid water pixels, because
WFR is land-masked and the AOI is mostly land at that resolution. Water
detection and monitoring here has to run on Sentinel-2 (10 m), Landsat
(30 m), or the 813 hyperspectral allocation once requested — not OLCI.
