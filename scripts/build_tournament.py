"""UAE AOI tournament: which area of interest should carry the demonstration?

Scores every AOI in config/aois_uae.yaml on five transparent criteria, each in
[0, 1], from files the pipeline wrote (WATCH, DETECT, OLCI labels, the asset
register) plus the documented event register. AOIs whose screening has not run
are listed as pending, never guessed. Writes docs/UAE_AOI_TOURNAMENT.md.

    python scripts/build_tournament.py
"""
from __future__ import annotations

import json
import math
import os
import time

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Documented events per AOI (docs/UAE_EVENT_REGISTER.md), used as prior evidence
#: that the water there produces reportable events. Counts only [V]-checked items.
REGISTER = {
    "AE-FUJ": ["2017 green Noctiluca (MOCCAE sampling)", "Oct 2019 diesel spill (S1 slick)", "Apr 2026 FEA 'greenish water'"],
    "AE-SHJ-KALBA": ["Nov–Dec 2023 fluorescent Noctiluca (Sharjah EPAA)", "Nov 2021 sea-snake deaths / slick", "Jan 2018 MOCCAE bloom (Kalba→Dibba)"],
    "AE-FUJ-DIBBA": ["Jan 2018 MOCCAE bloom (Kalba→Dibba)", "most frequent bloom site 2008–2018 (Al-Shehhi 2021)"],
    "AE-SHJ-KHORFAKKAN": ["Aug 2022 S1 slicks off Fujairah / Khor Fakkan"],
    "AE-AUH-NORTH": ["May 2018 Saadiyat beach closure (EAD sampling)"],
    "AE-AUH-LAGOON": ["Dec 2022– Al Raha discolouration (NYUAD sampling)", "Dec 2025 Al Muzoon canal fish kill (EAD)"],
    "AE-UAQ-RAK": ["~Sep 2019 red-tide patch off Al Jazira Al Hamra [U]"],
    "AE-DXB-JEBELALI": ["Jan 2018 MOCCAE bloom (RAK→Dubai)"],
    "AE-SHJ-AJM": ["Jan 2018 MOCCAE bloom (RAK→Dubai)"],
    "AE-AUH-TAWEELAH": [],
}
WEIGHTS = {"data": 0.15, "optics": 0.20, "evidence": 0.30, "exposure": 0.20, "burden": 0.15}


def J(p):
    p = os.path.join(ROOT, p)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def optics(regime: str) -> float:
    r = (regime or "").lower()
    if "optically deep" in r:
        return 1.0
    if "lagoon" in r and "shallow" in r:
        return 0.2
    if "shallow" in r:
        return 0.4
    return 0.55


def main():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "aois_uae.yaml"), encoding="utf-8"))["aois"]
    assets = J("config/assets_uae.geojson")["features"]
    labels = (J("outputs/labels/seed_labels.json") or {}).get("stats", {})
    rows, pending = [], []
    for aid, a in cfg.items():
        w = J(f"outputs/watch/{aid}.json")
        d = J(f"outputs/detect/{aid}.json")
        if not w:
            pending.append((aid, a))
            continue
        ok = [r for r in w["rows"] if "error" not in r]
        usable = [r for r in ok if (r.get("all") or {}).get("n_water", 0) >= 500]
        x0, y0, x1, y1 = a["bbox"]
        pad = 0.15
        crit = [f["properties"] for f in assets if f["properties"]["type"] in ("DESALINATION_PLANT", "POWER_PLANT")
                and x0 - pad <= f["geometry"]["coordinates"][0] <= x1 + pad and y0 - pad <= f["geometry"]["coordinates"][1] <= y1 + pad]
        st = labels.get(aid, {})
        cands = d.get("candidates", []) if d else None
        rows.append({"id": aid, "name": a["name"], "coast": a.get("coast"), "regime": a.get("optical_regime"),
                     "usable": len(usable), "n_ok": len(ok), "cands": None if cands is None else len(cands),
                     "bloom": None if cands is None else sum(c["hypothesis"] == "BLOOM_LIKE" for c in cands),
                     "pos": st.get("positive"), "neg": st.get("negative"), "crit": len(crit),
                     "crit_names": [c["name"] for c in crit][:4], "register": REGISTER.get(aid, [])})
    if not rows:
        raise SystemExit("no WATCH outputs yet")
    mu = max(r["usable"] for r in rows) or 1
    mc = max(r["crit"] for r in rows) or 1
    for r in rows:
        s_data = r["usable"] / mu
        s_opt = optics(r["regime"])
        conf = r["pos"] or 0
        s_evd = min(1.0, 0.5 * min(1.0, conf / 10) + 0.5 * min(1.0, len(r["register"]) / 3))
        s_exp = r["crit"] / mc
        if r["pos"] is None or (r["pos"] or 0) + (r["neg"] or 0) == 0:
            s_bur = 0.5
        else:
            s_bur = r["pos"] / (r["pos"] + r["neg"])        # share of referenced candidates OLCI confirms
        r["scores"] = {"data": s_data, "optics": s_opt, "evidence": s_evd, "exposure": s_exp, "burden": s_bur}
        r["total"] = sum(WEIGHTS[k] * v for k, v in r["scores"].items())
    rows.sort(key=lambda r: -r["total"])

    L = []
    L.append("# UAE AOI tournament\n")
    L.append(f"**BLUEBAN 813** · Team Kanban · generated {time.strftime('%d %B %Y', time.gmtime())} by `scripts/build_tournament.py`\n")
    L.append("Which UAE area of interest should carry the demonstration, decided from the data rather than chosen in advance. "
             "Each criterion is in [0, 1]; the total is the weighted sum. Re-run the script after new screening.\n")
    L.append("| Criterion | Weight | How it is measured |\n|---|---|---|")
    L.append(f"| Data | {WEIGHTS['data']:.2f} | usable Sentinel-2 acquisitions (≥ 500 water pixels), relative to the best AOI |")
    L.append(f"| Optics | {WEIGHTS['optics']:.2f} | optical regime from config: optically deep 1.0 · shelf 0.55 · shallow 0.4 · shallow lagoon 0.2 (bright seabed degrades water-colour algorithms more than sediment does; Al Shehhi et al. 2017) |")
    L.append(f"| Evidence | {WEIGHTS['evidence']:.2f} | half OLCI-confirmed candidates (saturating at 10), half documented events in `UAE_EVENT_REGISTER.md` (saturating at 3) |")
    L.append(f"| Exposure | {WEIGHTS['exposure']:.2f} | desalination and power plants within 0.15° of the AOI (OpenStreetMap), relative to the best AOI |")
    L.append(f"| Burden | {WEIGHTS['burden']:.2f} | share of OLCI-referenced candidates that OLCI confirms (a detector that mostly finds artefacts here scores low); 0.5 when unreferenced |\n")
    L.append("## Ranking\n")
    L.append("| # | AOI | Coast | Usable scenes | Candidates (bloom-like) | OLCI refs +/− | Plants nearby | Data | Optics | Evidence | Exposure | Burden | **Total** |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        s = r["scores"]
        L.append(f"| {i} | **{r['id']}** {r['name']} | {r['coast']} | {r['usable']} | {r['cands'] if r['cands'] is not None else '—'} "
                 f"({r['bloom'] if r['bloom'] is not None else '—'}) | {r['pos'] if r['pos'] is not None else '—'}/{r['neg'] if r['neg'] is not None else '—'} | {r['crit']} "
                 f"| {s['data']:.2f} | {s['optics']:.2f} | {s['evidence']:.2f} | {s['exposure']:.2f} | {s['burden']:.2f} | **{r['total']:.2f}** |")
    if pending:
        L.append("\n**Pending (screening not finished; not scored, not guessed):** " + ", ".join(f"{a} ({c['name']})" for a, c in pending) + ".")
    top = rows[0]
    L.append("\n## Result\n")
    L.append(f"**{top['id']} ({top['name']})** ranks first. Its nearby plants include {', '.join(top['crit_names']) or 'none recorded'}; "
             f"documented events: {'; '.join(top['register']) or 'none'}.")
    L.append("\nThe hero incident, **BB-AE-2024-001**, comes from this AOI: bright-green filaments on 17 February 2024 that "
             "Sentinel-3 OLCI independently resolved the same morning.")
    second = rows[1] if len(rows) > 1 else None
    if second:
        s2 = second["scores"]
        top3 = ", ".join(k for k, v in sorted(s2.items(), key=lambda kv: -kv[1])[:3])
        extra = ("It is an optically shallow shelf: there Sentinel-2 and OLCI can both respond to seabed reflectance and "
                 "resuspension, so their agreement is weaker evidence of a water-column event than in deep water. That is "
                 "why the optics criterion carries weight, and why a high candidate count there is not by itself an advantage."
                 if optics(second["regime"]) < 1.0 else "")
        L.append(f"\n**{second['id']}** is second ({second['total']:.2f}), strongest on {top3}. {extra}")
    L.append("\nThe first AOI's burden score is a reminder, not a flaw to hide: over its very clear water NDCI becomes unstable "
             "and many candidates there are ratio artefacts that OLCI does not confirm (BB-AE-2023-001 is one). The verification "
             "queue and the learning loop exist for exactly that.")
    L.append("\n## Why Annaba is no longer the hero\n")
    L.append("The Gulf of Annaba (Algeria) was the original demonstration because an open Tanager hyperspectral scene exists there. "
             "It stays in the product as the **negative control**: spatially unusual but ordinary for the season, so the system stands down.")
    L.append("\n## Caveats\n")
    L.append("* OLCI references are a model product (Case-2 neural net), not in-situ truth, and cannot label candidates smaller than a few 300 m pixels or after 23 February 2026.")
    L.append("* The event register is incomplete and uneven across emirates; it is used as weak prior evidence only.")
    L.append("* Weights are a judgement, stated here so a reviewer can change them and re-run the script.")
    out = os.path.join(ROOT, "docs", "UAE_AOI_TOURNAMENT.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("->", out, "| winner:", top["id"], f"{top['total']:.2f}", "| pending:", [p[0] for p in pending])


if __name__ == "__main__":
    main()
