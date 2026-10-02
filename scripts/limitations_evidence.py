"""Evidence that closes three limitations in docs/LIMITATIONS.md (sections 5, 8, 10).

Nothing here validates anything that was not validated before. Each block is a
BOUND or a PROXY, computed from open data the project already uses, and it is
written into LIMITATIONS.md as an appended sub-section, never replacing text.

1. Drift (section 5). A multi-year ERA5 hourly 10 m wind record at the same
   offshore sample point the Annaba scenario used is pushed through the SAME
   surface-drift physics as pipeline/forecast.py (3 % of the wind, 15 degree
   deflection) from every 6-hourly start. Reported: how far a surface parcel
   plausibly travels by each horizon under the observed range of winds, and the
   gap between "hold the start wind constant" and "follow the real hourly
   wind", which bounds the error a wind forecast no better than persistence
   would add. Missing physics (tides, currents, waves) is NOT in the bound.
2. Second hyperspectral date (section 8). The 2020-2025 Sentinel-2 record of the
   event zone bounds how much the optical signal shifts between acquisitions a
   few days apart: a proxy for day-to-day variability, not hyperspectral
   validation.
3. Geography (section 10). The UAE build runs the same local seasonal-percentile
   thresholds, untouched, across ten AOIs on two very different seas; the
   per-AOI cross-sensor confirmation rates are the portability evidence, mixed
   results included.

Writes outputs/validation/limitations_evidence.json and refreshes the marked
sub-sections in docs/LIMITATIONS.md.

    python scripts/limitations_evidence.py [--start 2019-01-01 --end 2025-12-31]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import detect, forecast  # noqa: E402

HORIZONS_H = (6, 12, 24, 48)


def _pct(a, q):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return float(np.percentile(a, q)) if a.size else None


def drift_bounds(lat: float, lon: float, start: str, end: str, season_center: str | None, label: str) -> dict:
    """Displacement and persistence-error distributions from a long ERA5 record."""
    w = forecast.fetch_wind(lat, lon, start, end, timeout=180)
    u = np.asarray(w.u, float)
    v = np.asarray(w.v, float)
    ok = np.isfinite(u) & np.isfinite(v)
    du = np.full_like(u, np.nan)
    dv = np.full_like(v, np.nan)
    for i in np.nonzero(ok)[0]:
        du[i], dv[i] = forecast.surface_drift(u[i], v[i])
    times = [dt.datetime.fromisoformat(t) for t in w.times]
    hmax = max(HORIZONS_H)
    starts = range(0, len(u) - hmax, 6)
    disp = {h: [] for h in HORIZONS_H}
    pers = {h: [] for h in HORIZONS_H}
    season = {h: [] for h in HORIZONS_H}
    season_pers = {h: [] for h in HORIZONS_H}
    cday = dt.date.fromisoformat(season_center).timetuple().tm_yday if season_center else None
    for s in starts:
        seg_u, seg_v = du[s:s + hmax], dv[s:s + hmax]
        if not (np.isfinite(seg_u).all() and np.isfinite(seg_v).all()):
            continue
        x = np.cumsum(seg_u) * 3600.0          # metres east, hourly Euler steps
        y = np.cumsum(seg_v) * 3600.0          # metres north
        in_season = False
        if cday is not None:
            dd = abs(times[s].timetuple().tm_yday - cday)
            in_season = min(dd, 365 - dd) <= 45
        for h in HORIZONS_H:
            d = math.hypot(x[h - 1], y[h - 1])
            px, py = seg_u[0] * 3600.0 * h, seg_v[0] * 3600.0 * h     # persistence of the start wind
            e = math.hypot(x[h - 1] - px, y[h - 1] - py)
            disp[h].append(d)
            pers[h].append(e)
            if in_season:
                season[h].append(d)
                season_pers[h].append(e)

    def summ(dct):
        return {str(h): {"n": len(dct[h]), "median_km": _pct(dct[h], 50) / 1000 if dct[h] else None,
                         "p90_km": _pct(dct[h], 90) / 1000 if dct[h] else None,
                         "p95_km": _pct(dct[h], 95) / 1000 if dct[h] else None,
                         "max_km": float(np.max(dct[h])) / 1000 if dct[h] else None} for h in HORIZONS_H}
    k = forecast.HORIZONTAL_DIFFUSIVITY
    return {
        "label": label, "sample_point_lonlat": [lon, lat], "era5_cell_lonlat": [w.longitude, w.latitude],
        "record": [w.times[0], w.times[-1]], "n_hours": int(len(u)), "n_starts": len(disp[HORIZONS_H[0]]),
        "wind_speed_ms": {"median": _pct(w.speed, 50), "p95": _pct(w.speed, 95), "max": _pct(w.speed, 100)},
        "drift_physics": {"wind_drift_factor": forecast.WIND_DRIFT_FACTOR, "deflection_deg": forecast.DEFLECTION_DEG},
        "displacement_all_year": summ(disp), "persistence_error_all_year": summ(pers),
        "season_center": season_center, "displacement_season": summ(season) if cday else None,
        "persistence_error_season": summ(season_pers) if cday else None,
        "diffusion_sigma_km": {str(h): math.sqrt(2 * k * h * 3600.0) / 1000 for h in HORIZONS_H},
        "source": w.source,
    }


def s2_variability(path: str, zone: str, variable: str, max_gap_days: float, min_water_frac: float = 0.5) -> dict:
    ts = json.load(open(path, encoding="utf-8"))[zone]
    nmax = max(r.get("n_water_px") or 0 for r in ts)
    rows = sorted([r for r in ts if (r.get("n_water_px") or 0) >= min_water_frac * nmax and r.get(variable) is not None],
                  key=lambda r: r["datetime"])
    pairs = []
    for a, b in zip(rows, rows[1:]):
        ta = dt.datetime.fromisoformat(a["datetime"].replace("Z", "+00:00"))
        tb = dt.datetime.fromisoformat(b["datetime"].replace("Z", "+00:00"))
        gap = (tb - ta).total_seconds() / 86400.0
        if gap <= max_gap_days:
            pairs.append((gap, abs(b[variable] - a[variable])))
    vals = np.array([r[variable] for r in rows], float)
    d = np.array([p[1] for p in pairs], float)
    return {"zone": zone, "variable": variable, "max_gap_days": max_gap_days, "n_observations": len(rows),
            "n_pairs": len(pairs), "median_abs_change": _pct(d, 50), "p90_abs_change": _pct(d, 90),
            "p95_abs_change": _pct(d, 95), "record_p5": _pct(vals, 5), "record_p95": _pct(vals, 95),
            "record_p5_p95_range": (_pct(vals, 95) - _pct(vals, 5)) if len(vals) else None,
            "min_water_fraction_of_max": min_water_frac}


def portability() -> dict:
    import yaml
    coast = {k: v.get("coast") for k, v in yaml.safe_load(open(os.path.join(ROOT, "config", "aois_uae.yaml"), encoding="utf-8"))["aois"].items()}
    labels = json.load(open(os.path.join(ROOT, "outputs", "labels", "seed_labels.json"), encoding="utf-8"))
    vs = json.load(open(os.path.join(ROOT, "outputs", "validation", "validation_summary.json"), encoding="utf-8"))
    loao = {r["held_out_aoi"]: r for r in vs["E_spatial_holdout"].get("triage_leave_one_aoi_out", [])}
    rows = []
    for aoi, st in sorted(labels.get("stats", {}).items()):
        n = (st.get("positive") or 0) + (st.get("negative") or 0)
        d = json.load(open(os.path.join(ROOT, "outputs", "detect", f"{aoi}.json"), encoding="utf-8"))
        r = loao.get(aoi, {})
        rows.append({"aoi": aoi, "coast": coast.get(aoi), "acquisitions": d.get("n_acquisitions"), "candidates": len(d.get("candidates", [])),
                     "olci_confirmed": st.get("positive"), "olci_not_confirmed": st.get("negative"),
                     "confirmation_rate": (st["positive"] / n) if n else None,
                     "loao_candidate_auprc": (r.get("candidate") or {}).get("auprc"),
                     "loao_rule_auprc": (r.get("production") or {}).get("auprc")})
    rates = [r["confirmation_rate"] for r in rows if r["confirmation_rate"] is not None]
    by_coast = {}
    for r in rows:
        c = by_coast.setdefault(r["coast"], {"aois": 0, "confirmed": 0, "referenced": 0})
        c["aois"] += 1
        c["confirmed"] += r["olci_confirmed"] or 0
        c["referenced"] += (r["olci_confirmed"] or 0) + (r["olci_not_confirmed"] or 0)
    for c in by_coast.values():
        c["pooled_rate"] = c["confirmed"] / c["referenced"] if c["referenced"] else None
    scorable = [r for r in rows if r["loao_candidate_auprc"] is not None and r["loao_rule_auprc"] is not None]
    return {"by_coast": by_coast,
            "loao_candidate_beats_rule": [sum(r["loao_candidate_auprc"] > r["loao_rule_auprc"] for r in scorable), len(scorable)],
            "thresholds_unchanged_across_aois": {"z_min": detect.Z_MIN, "pct_min": detect.PCT_MIN,
                                                 "min_area_km2": detect.MIN_AREA_KM2, "floors": detect.FLOORS},
            "per_aoi": rows, "confirmation_rate_range": [min(rates), max(rates)] if rates else None,
            "by_hypothesis": vs["B_matchups"]["cross_sensor"].get("per_hypothesis"),
            "agreement": vs["B_matchups"]["cross_sensor"].get("agreement")}


# --------------------------------------------------------------------------- docs
def _f(v, d=1):
    return "n/a" if v is None else f"{v:.{d}f}"


def write_docs(ev: dict) -> None:
    path = os.path.join(ROOT, "docs", "LIMITATIONS.md")
    doc = open(path, encoding="utf-8").read()
    a = ev["drift"][0]
    b = ev["drift"][1]
    db, pb = b["displacement_all_year"], b["persistence_error_all_year"]
    da, pa, ds, ps = a["displacement_all_year"], a["persistence_error_all_year"], a["displacement_season"], a["persistence_error_season"]
    rows = "\n".join(
        f"| +{h} h | {_f(da[str(h)]['median_km'])} / {_f(da[str(h)]['p95_km'])} | {_f(ds[str(h)]['median_km'])} / {_f(ds[str(h)]['p95_km'])} "
        f"| {_f(pa[str(h)]['median_km'])} / {_f(pa[str(h)]['p95_km'])} | {_f(a['diffusion_sigma_km'][str(h)], 2)} |" for h in HORIZONS_H)
    s5 = f"""### Added 2026-10-02: a bounded drift estimate from {a['record'][0][:4]}–{a['record'][1][:4]} ERA5 winds

The scenario above used ERA5 wind for the event window only. To bound what the
same model implies, the full hourly ERA5 record at the same offshore sample
point (ERA5 cell {a['era5_cell_lonlat'][1]:.2f} N, {a['era5_cell_lonlat'][0]:.2f} E; {a['n_hours']:,} hours) was pushed through the same drift physics
(3 % of the 10 m wind, 15° deflection) from {a['n_starts']:,} start times, six hours apart.
Generated by `scripts/limitations_evidence.py` → `outputs/validation/limitations_evidence.json`.

| Horizon | Parcel displacement, median / P95 (km), all year | Same, ±45 days of 1 June | Wind-persistence error, median / P95 (km) | Diffusion σ (km) |
|---|---|---|---|---|
{rows}

How to read it. **Displacement** is how far a surface parcel plausibly travels under
the observed range of winds, so it bounds the search radius a field team should
expect. **Wind-persistence error** is the distance between holding the start wind
constant and following the real hourly wind: an upper-end estimate of the
position error a wind forecast no better than persistence would add (an
operational forecast should do better). **This is a bounded estimate, not a
validated accuracy figure.** It covers wind variability only; tidal and
density-driven currents, waves and coastline effects are outside it and can be
larger in a semi-enclosed gulf. A drifter release or a repeat pass is still what
would turn it into a validated error statistic.

For context, the same computation at the Fujairah hero's offshore sample point
(ERA5 cell {b['era5_cell_lonlat'][1]:.2f} N, {b['era5_cell_lonlat'][0]:.2f} E), where winds are stronger (median {_f(b['wind_speed_ms']['median'])} m/s against
{_f(a['wind_speed_ms']['median'])} m/s), gives a 24 h displacement of {_f(db['24']['median_km'])} / {_f(db['24']['p95_km'])} km and a 24 h
wind-persistence error of {_f(pb['24']['median_km'])} / {_f(pb['24']['p95_km'])} km (median / P95), under the same caveats."""
    v = ev["s2_variability"]
    s8 = f"""### Added 2026-10-02: what a second date would take, and a proxy bound on day-to-day change

**Operational path to a second hyperspectral date.**
* *Tanager open archive.* The open STAC grew from 236 to 276 items in three days
  in September 2026; re-running the existing footprint check periodically costs
  nothing and may surface a repeat pass.
* *Tanager tasking.* A targeted repeat requires a commercial tasking request to
  Planet (paid; not placed by this project). The request would name the AOI,
  a revisit window and a cloud ceiling.
* *Other open or science-access hyperspectral missions.* EnMAP (DLR; free for
  registered science users, tasking by proposal), PRISMA (ASI; registered
  users) and EMIT (NASA; open, ISS orbit, opportunistic coverage) could supply a
  second date at 30–60 m. Each would need the simulator re-run on that sensor's
  band set.

**Proxy bound from the multi-year Sentinel-2 record (not hyperspectral validation).**
Across {v['n_observations']} usable Sentinel-2 acquisitions of the event zone (2020–2025), {v['n_pairs']} pairs were at most
{v['max_gap_days']:.0f} days apart. The zone's P95 turbidity proxy changed between them by a median of
{_f(v['median_abs_change'], 3)} (P90 {_f(v['p90_abs_change'], 3)}, P95 {_f(v['p95_abs_change'], 3)}), against a P5–P95 spread
over the whole record of {_f(v['record_p5_p95_range'], 3)}. A few days can therefore move this proxy by
roughly {100 * v['median_abs_change'] / v['record_p5_p95_range']:.0f} % (median) to {100 * v['p95_abs_change'] / v['record_p5_p95_range']:.0f} % (P95) of its full
multi-year range. That is the scale a second hyperspectral date would have to
beat before a difference could be read as change rather than ordinary variability.
Part of the upper tail is residual cloud, haze and glint that survive masking,
which a hyperspectral comparison would also have to control for. It is a
multispectral (Sentinel-2 only) proxy for the signal's variability, labelled as
such, not a hyperspectral measurement."""
    p = ev["portability"]
    t = p["thresholds_unchanged_across_aois"]
    order = sorted(p["per_aoi"], key=lambda r: (r["coast"] or "", r["aoi"]))
    lines = "\n".join(
        f"| {r['aoi']} | {r['coast']} | {r['candidates']} | {r['olci_confirmed']}/{(r['olci_confirmed'] or 0) + (r['olci_not_confirmed'] or 0)} "
        f"| {_f(100 * r['confirmation_rate'], 0) + ' %' if r['confirmation_rate'] is not None else 'n/a'} "
        f"| {_f(r['loao_candidate_auprc'], 2) + ' vs ' + _f(r['loao_rule_auprc'], 2) if r['loao_candidate_auprc'] is not None else 'not scorable (one class)'} |" for r in order)
    scored = [r for r in p["per_aoi"] if r["confirmation_rate"] is not None]
    lo = min(scored, key=lambda r: r["confirmation_rate"])
    hi = max(scored, key=lambda r: r["confirmation_rate"])
    bc = p["by_coast"]
    ag, go = bc.get("Arabian Gulf", {}), bc.get("Gulf of Oman", {})
    wins, nsc = p["loao_candidate_beats_rule"]
    hb = p.get("by_hypothesis") or {}
    s10 = f"""### Added 2026-10-02: a portability check on ten UAE AOIs

The September 2026 UAE build is a second geography reached with open data. Its
detector uses the same idea, a local seasonal-percentile test against the same
place's own history, with **one set of thresholds applied unchanged to every
AOI** (z ≥ {t['z_min']:.0f}, seasonal percentile ≥ {t['pct_min']:.0f}, area ≥ {t['min_area_km2']} km²), on two very different seas:
the shallow, hypersaline Arabian Gulf and the deep Gulf of Oman. It is a related
method, not the identical Annaba pipeline (per-pixel instead of zone-level).
Without any re-tuning, Sentinel-3 OLCI confirmed the following share of the
candidates it could reference:

| AOI | Coast | Candidates | OLCI confirmed / referenced | Rate | Held-out triage AUPRC, learned vs rule |
|---|---|---|---|---|---|
{lines}

**Result, stated plainly: it ports, but unevenly.** Confirmation rates range from
{_f(100 * lo['confirmation_rate'], 0)} % ({lo['aoi']}, {lo['olci_confirmed']} of {lo['olci_confirmed'] + lo['olci_not_confirmed']}) to {_f(100 * hi['confirmation_rate'], 0)} % ({hi['aoi']}, {hi['olci_confirmed']} of {hi['olci_confirmed'] + hi['olci_not_confirmed']}).
Pooled by sea: {ag.get('confirmed')} of {ag.get('referenced')} ({_f(100 * (ag.get('pooled_rate') or 0), 0)} %) on the Arabian Gulf against {go.get('confirmed')} of {go.get('referenced')}
({_f(100 * (go.get('pooled_rate') or 0), 0)} %) on the Gulf of Oman, so the clear, deep east coast, which includes the
hero AOI, carries the heavier false-alarm burden. Sediment-like candidates are mostly confirmed
({hb.get('SEDIMENT_LIKE', {}).get('positive', 'n/a')} of {hb.get('SEDIMENT_LIKE', {}).get('n', 'n/a')}); bloom-like candidates mostly are not
({hb.get('BLOOM_LIKE', {}).get('positive', 'n/a')} of {hb.get('BLOOM_LIKE', {}).get('n', 'n/a')}), because NDCI is unstable over very clear water. In the
shallow Gulf both sensors can respond to the seabed, so agreement there is weaker
evidence. The thresholds needed no re-tuning to run, but the false-alarm burden
does depend on water type, which is what the learning loop is for: trained
without the AOI it is scored on, the learned triage beats the fixed rule on
{wins} of {nsc} scorable AOIs (last column).
OLCI is a model product, not in-situ truth; a Mediterranean or Red Sea repeat
remains untested."""
    blocks = {"s5": (s5, "## 6. "), "s8": (s8, "## 9. "), "s10": (s10, "## 11. ")}
    for key, (text, next_heading) in blocks.items():
        tag_a, tag_b = f"<!-- BEGIN ADDED:{key} -->", f"<!-- END ADDED:{key} -->"
        block = f"{tag_a}\n{text}\n{tag_b}\n"
        if tag_a in doc:
            doc = re.sub(re.escape(tag_a) + r".*?" + re.escape(tag_b) + r"\n?", lambda m: block, doc, flags=re.S)
        else:
            i = doc.index(next_heading)
            j = doc.rindex("---", 0, i)            # insert before the section's closing rule
            doc = doc[:j] + block + "\n" + doc[j:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2025-12-31")
    a = ap.parse_args()
    t0 = time.time()
    ev = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    # Annaba: the same offshore sample point the event scenario used (outputs/events/BB-2026-001_forecast.json)
    ev["drift"] = [drift_bounds(37.00267, 7.67354, a.start, a.end, "2025-06-01", "Gulf of Annaba (BB-2026-001 sample point)")]
    # UAE hero for context: the offshore sample point scripts/build_incidents.py uses for BB-AE-2024-001
    ev["drift"].append(drift_bounds(25.1157, 56.5302, a.start, a.end, "2024-02-17", "Fujairah (BB-AE-2024-001 sample point)"))
    ev["s2_variability"] = s2_variability(os.path.join(ROOT, "outputs", "validation", "s2_timeseries.json"),
                                          "hotspot_inner_gulf", "TURBIDITY_PROXY_p95", 5.0)
    ev["portability"] = portability()
    out = os.path.join(ROOT, "outputs", "validation", "limitations_evidence.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(ev, f, indent=1)
    write_docs(ev)
    print(f"-> {out} + docs/LIMITATIONS.md ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
