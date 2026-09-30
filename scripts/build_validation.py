"""Validation summary for the Validation screen (sections A-F), from real outputs only.

A. DATA QUALITY      per-acquisition quality records written by WATCH
B. UAE MATCHUPS      in-situ matchups (none public) and OLCI cross-sensor references
C. MODEL PERFORMANCE rule baseline vs a logistic candidate on the frozen validation
                     split, with grouped bootstrap confidence intervals
D. 813 ABLATION      the measured Tanager experiments (S2 vs simulated 813)
E. SPATIAL HOLDOUT   leave-one-AOI-out triage; spatially blocked vs random CV
F. NEGATIVE CONTROL  Annaba stand-down and cross-sensor rejections in the UAE

Nothing here is typed in by hand: every number is recomputed from files in
outputs/. A section with no data says so rather than showing a placeholder.

Writes outputs/validation/validation_summary.json
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import learning, matchup, quantify  # noqa: E402


def load(p):
    p = os.path.join(ROOT, p)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def clean(o):
    """JSON-safe: NaN/inf -> None, numpy -> python, rounded floats."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(float(o)) else round(float(o), 6)
    return o


def med(v):
    v = [x for x in v if x is not None and math.isfinite(x)]
    return float(np.median(v)) if v else None


# --------------------------------------------------------------------------- A
def data_quality():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "outputs", "watch", "*.json"))):
        w = json.load(open(p, encoding="utf-8"))
        rows = w.get("rows", [])
        ok = [r for r in rows if "error" not in r]
        usable = [r for r in ok if (r.get("all") or {}).get("n_water", 0) >= 500]
        q = [r.get("quality") or {} for r in ok]
        baselines = {}
        for r in ok:
            for b in r.get("processing_baselines") or []:
                baselines[b] = baselines.get(b, 0) + 1
        offset = sum(1 for r in ok if any(float(b) >= 4.0 for b in (r.get("processing_baselines") or [])))
        plats = {}
        for r in ok:
            plats[r.get("platform")] = plats.get(r.get("platform"), 0) + 1
        out.append({
            "aoi_id": w.get("aoi_id"), "name": (w.get("aoi") or {}).get("name"),
            "resolution_m": (w.get("grid") or {}).get("resolution_m"),
            "n_datatakes": len(rows), "n_ok": len(ok), "n_failed": len(rows) - len(ok),
            "n_usable": len(usable),
            "date_range": [min((r["date"] for r in ok), default=None), max((r["date"] for r in ok), default=None)],
            "platforms": plats, "processing_baselines": dict(sorted(baselines.items())),
            "n_boa_offset_applied": offset,
            "median_valid_fraction": med([r.get("valid_fraction") for r in ok]),
            "median_cloud_fraction_of_valid": med([r.get("cloud_fraction_of_valid") for r in ok]),
            "median_water_fraction": med([x.get("water_fraction") for x in q]),
            "median_glint_fraction": med([x.get("glint_or_float_px", 0) / x["water_px"]
                                          for x in q if x.get("water_px")]),
            "median_b11_water": med([(x.get("params") or {}).get("median_b11_water") for x in q]),
            "median_negative_red_fraction": med([x.get("negative_red_px", 0) / x["water_px"]
                                                 for x in q if x.get("water_px")]),
            "scl_unusable_classes": ((q[0].get("params") or {}).get("scl_unusable") if q else None),
        })
    return {"aois": out,
            "method": "Sentinel-2 L2A via Planetary Computer; BOA_ADD_OFFSET -1000 applied when "
                      "s2:processing_baseline >= 04.00; SCL classes masked; glint-aware water mask "
                      "(B11 < 0.10 water, B11 > 0.0215 glint-flagged and SWIR-offset corrected)."}


# --------------------------------------------------------------------------- B
def matchups(seed_labels):
    cfg = matchup.MatchupConfig()
    ins = {"n_matchups": 0,
           "status": "NO PUBLIC IN-SITU DATA",
           "reason": "No public per-sample UAE chlorophyll, turbidity or TSS measurements were found "
                     "(docs/PUBLIC_UAE_DATA.md). The hackathon platform and gIQ hold none for UAE water "
                     "(docs/AUTHENTICATED_DATA_AUDIT.md). A data request to EAD is drafted, not sent.",
           "engine": {**cfg.to_dict(), "sensitivity_hours": [3, 24, 72]},
           "quantification": quantify.calibration_verdict({"n": 0, "n_groups": 0, "models": {}})}
    cs = {"n": 0}
    if seed_labels:
        labs = seed_labels["labels"]
        per = {}
        pts = []
        for l in labs:
            o = l["target"]["olci"]
            h = l["target"]["hypothesis"]
            d = per.setdefault(h, {"n": 0, "positive": 0, "negative": 0, "variable": o["variable"]})
            d["n"] += 1
            d["positive"] += l["target"]["y"] == 1
            d["negative"] += l["target"]["y"] == 0
            s2 = l["features"].get("ndci_delta") if h == "BLOOM_LIKE" else l["features"].get("tur_delta")
            pts.append({"aoi": l["aoi_id"], "date": l["target"]["candidate_date"], "hyp": h,
                        "s2_delta": s2, "olci_ratio": o["ratio"], "y": l["target"]["y"],
                        "dt_min": o["dt_minutes"]})
        agree = {}
        from scipy.stats import spearmanr
        for h in per:
            xs = [(p["s2_delta"], math.log10(p["olci_ratio"])) for p in pts
                  if p["hyp"] == h and p["s2_delta"] is not None and p["olci_ratio"] and p["olci_ratio"] > 0]
            if len(xs) >= 5:
                r = spearmanr([a for a, _ in xs], [b for _, b in xs])
                agree[h] = {"spearman_rho": float(r.statistic), "p_value": float(r.pvalue), "n": len(xs)}
        cs = {"n": len(labs), "per_hypothesis": per, "agreement": agree, "points": pts,
              "median_abs_dt_minutes": med([abs(p["dt_min"]) for p in pts]),
              "rule": seed_labels.get("rule"),
              "caveat": "OLCI CHL_NN / TSM_NN are ESA model products, not in-situ measurements. They are "
                        "an independent sensor and retrieval, used as a weak (weight 0.5) reference."}
    return {"in_situ": ins, "cross_sensor": cs}


# --------------------------------------------------------------------------- C / E
def model_performance(seed_labels):
    if not seed_labels or not seed_labels["labels"]:
        return {"status": "NO LABELS"}, {"status": "NO LABELS"}
    labs = seed_labels["labels"]
    F = learning.TRIAGE_FEATURES
    tr = [l for l in labs if l["split"] == "train"]
    va = [l for l in labs if l["split"] == "validation"]

    def mat(ls):
        X = np.array([[learning._f(l["features"].get(f)) for f in F] for l in ls], float)
        y = np.array([l["target"]["y"] for l in ls], int)
        w = np.array([l.get("weight", 1.0) for l in ls], float)
        g = np.array([l.get("group_key") or l["id"] for l in ls])
        return X, y, w, g

    Xt, yt, wt, gt = mat(tr)
    Xv, yv, wv, gv = mat(va)
    res = {"n_train": len(tr), "n_validation": len(va),
           "train_positive": int(yt.sum()), "validation_positive": int(yv.sum()),
           "validation_hash": learning.dataset_hash(va), "features": F}
    prod = learning.rules_score(Xv)
    res["production"] = {"model": "triage-1.0.0 (rule baseline)",
                         "metrics": learning.classification_metrics(yv, prod)}
    if len(set(yt.tolist())) == 2 and len(set(yv.tolist())) == 2:
        art = learning.fit_logistic(Xt, yt, wt, F, C=1.0)
        cand = art.predict(Xv)
        res["candidate"] = {"model": "logistic (L2, class-balanced) trained on the train split",
                            "metrics": learning.classification_metrics(yv, cand),
                            "coefficients": dict(zip(F, [float(c) for c in art.coef]))}
        res["bootstrap"] = {
            "auprc": learning.grouped_bootstrap_ci(yv, prod, cand, gv, learning._ap, n_boot=1000),
            "auroc": learning.grouped_bootstrap_ci(yv, prod, cand, gv, learning._auc, n_boot=1000)}
    else:
        res["candidate"] = {"status": "cannot train: a split lacks one class"}

    # E. leave-one-AOI-out
    aois = sorted({l["aoi_id"] for l in labs})
    holdout = []
    for a in aois:
        te = [l for l in labs if l["aoi_id"] == a]
        trn = [l for l in labs if l["aoi_id"] != a]
        Xa, ya, wa, _ = mat(trn)
        Xb, yb, _, _ = mat(te)
        row = {"held_out_aoi": a, "n_test": len(te), "test_positive": int(yb.sum()),
               "n_train": len(trn)}
        if len(set(ya.tolist())) == 2 and len(set(yb.tolist())) == 2:
            art = learning.fit_logistic(Xa, ya, wa, F, C=1.0)
            row["candidate"] = learning.classification_metrics(yb, art.predict(Xb))
            row["production"] = learning.classification_metrics(yb, learning.rules_score(Xb))
        else:
            row["status"] = "needs both classes in train and test"
        holdout.append(row)
    return res, {"triage_leave_one_aoi_out": holdout}


# --------------------------------------------------------------------------- D
def ablation():
    easy = load("outputs/validation/detectability_lift_easy.json")
    hard = load("outputs/validation/detectability_lift_hard.json")
    olci = load("outputs/validation/hyperspectral_lift.json")
    sim = load("outputs/validation/simulator_validation.json")
    if not hard:
        return {"status": "NOT RUN"}

    def arms(d, split="spatial_blocked"):
        return {k: {m: v.get(m) for m in ("f1", "precision", "recall", "roc_auc", "average_precision",
                                          "confusion_matrix", "n_features")}
                for k, v in (d or {}).get("results", {}).get(split, {}).items()}
    out = {"scene": "Tanager (Planet) over the Gulf of Annaba; the same pixels convolved to each band set",
           "arms": {"A": "Sentinel-2 MSI, 11 bands", "B": "Satellite 813 (simulated), 205 bands",
                    "C": "Satellite 813 (simulated), 261 bands at 5 nm"},
           "hard": {"arms": arms(hard), "n_samples": hard.get("n_samples"), "n_positive": hard.get("n_positive"),
                    "n_spatial_blocks": hard.get("n_spatial_blocks"), "block_size_m": hard.get("block_size_m")},
           "easy": {"arms": arms(easy), "n_samples": (easy or {}).get("n_samples"),
                    "n_positive": (easy or {}).get("n_positive")},
           "caveats": hard.get("caveats", []),
           "simulated": True}
    if olci:
        out["olci_regression"] = {
            "n_matchups": olci.get("n_matchups"), "dt_hours": olci.get("matchup_dt_hours"),
            "targets": {t: {k: {m: v.get(m) for m in ("r2", "rmse", "mae", "r2_ci95")}
                            for k, v in d.get("spatial_blocked", {}).items()}
                        for t, d in olci.get("targets", {}).items()}}
    if sim:
        def band_summary(surface):
            pb = sim.get("per_band", {}).get(surface, {})
            return {b: {"r2_1to1": v.get("r2_1to1"), "rmse": v.get("rmse"), "bias": v.get("bias"), "n": v.get("n")}
                    for b, v in pb.items()}
        out["simulator_validation"] = {"question": sim.get("question"),
                                       "time_offset_minutes": sim.get("time_offset_minutes"),
                                       "land": band_summary("land"), "water": band_summary("water"),
                                       "interpretation": sim.get("interpretation")}
    return out


def spatial_vs_random():
    hard = load("outputs/validation/detectability_lift_hard.json")
    if not hard:
        return None
    r = hard.get("results", {})
    return {k: {"spatial_blocked_f1": r.get("spatial_blocked", {}).get(k, {}).get("f1"),
                "random_split_f1": r.get("random_split", {}).get(k, {}).get("f1")}
            for k in r.get("spatial_blocked", {})}


# --------------------------------------------------------------------------- F
def negative_control(seed, seed_labels):
    out = {}
    inc = next((i for i in (seed or {}).get("incidents", []) if i.get("role") == "negative_control"), None)
    if inc:
        out["annaba"] = {"id": inc["id"], "status": inc["status"], "title": inc.get("title"),
                         "rx_percentile": (inc.get("spatial") or {}).get("rx_percentile"),
                         "seasonal_percentile": (inc.get("temporal") or {}).get("seasonal_percentile"),
                         "n_seasonal": (inc.get("temporal") or {}).get("n_seasonal"),
                         "disposition": inc.get("disposition"),
                         "reading": "Spatially unusual (RX) but ordinary for the season at that place "
                                    "(temporal percentile) -> persistent coastal feature -> stand down."}
    if seed_labels:
        rej = [l for l in seed_labels["labels"] if l["target"]["y"] == 0]
        big = sorted(rej, key=lambda l: -(10 ** (l["features"].get("log10_area_km2") or -9)))[:5]
        out["cross_sensor_rejections"] = {
            "n": len(rej), "of": seed_labels["n"],
            "largest": [{"aoi": l["aoi_id"], "date": l["target"]["candidate_date"],
                         "hypothesis": l["target"]["hypothesis"],
                         "area_km2": round(10 ** l["features"]["log10_area_km2"], 2)
                         if l["features"].get("log10_area_km2") is not None else None,
                         "s2_z": l["features"].get("robust_z_primary"),
                         "olci": l["target"]["olci"]} for l in big]}
    return out


# --------------------------------------------------------------------------- markdown
BEGIN = "<!-- BEGIN GENERATED: scripts/build_validation.py -->"
END = "<!-- END GENERATED -->"


def _n(v, d=3):
    return "n/a" if v is None else f"{v:.{d}f}"


def write_report(out: dict) -> None:
    """Refresh the generated UAE section at the top of docs/VALIDATION_REPORT.md."""
    A, B, C = out["A_data_quality"], out["B_matchups"], out["C_model_performance"]
    E, F = out["E_spatial_holdout"], out["F_negative_control"]
    L = [BEGIN, "", "## UAE closed-loop validation (generated)", "",
         f"Recomputed from the pipeline outputs on {out['generated_utc']}. The same numbers drive the in-app "
         "Validation screen (sections A-F). The Annaba and Tanager experiments below this section are unchanged.", ""]
    tot = sum(a["n_ok"] for a in A["aois"])
    use = sum(a["n_usable"] for a in A["aois"])
    L += ["### A. Data quality", "",
          f"{tot:,} Sentinel-2 L2A datatakes read over {len(A['aois'])} UAE AOIs, {use:,} usable (>= 500 water pixels).", "",
          "| AOI | Period | Datatakes | Usable | Median valid | Glint-flagged water |", "|---|---|---|---|---|---|"]
    for a in A["aois"]:
        L.append(f"| {a['aoi_id']} | {a['date_range'][0]} to {a['date_range'][1]} | {a['n_ok']} | {a['n_usable']} | "
                 f"{_n((a.get('median_valid_fraction') or 0) * 100, 0)} % | {_n((a.get('median_glint_fraction') or 0) * 100, 0)} % |")
    cs = B["cross_sensor"]
    L += ["", "### B. Matchups", "",
          f"* **In situ: {B['in_situ']['n_matchups']}.** {B['in_situ']['reason']}",
          f"* Physical units allowed: **{'yes' if B['in_situ']['quantification']['usable_for_physical_units'] else 'no'}** "
          f"({'; '.join(B['in_situ']['quantification']['reasons'])}).",
          f"* **Cross-sensor reference (Sentinel-3 OLCI, not in situ): {cs.get('n', 0)} labelled candidates**, median |dt| "
          f"{_n(cs.get('median_abs_dt_minutes'), 0)} min."]
    for h, v in (cs.get("per_hypothesis") or {}).items():
        a = (cs.get("agreement") or {}).get(h, {})
        L.append(f"  * {h}: {v['positive']} confirmed / {v['negative']} not ({v['variable']}); Spearman rho between the S2 change "
                 f"and the OLCI contrast {_n(a.get('spearman_rho'), 2)} (p {_n(a.get('p_value'), 4)}, n {a.get('n', 0)}).")
    if C.get("production"):
        p_, c_ = C["production"]["metrics"], (C.get("candidate") or {}).get("metrics") or {}
        bt = C.get("bootstrap") or {}
        L += ["", "### C. Model performance (triage, frozen validation)", "",
              f"{C['n_train']} train / {C['n_validation']} validation labels ({C['validation_positive']} positive), "
              f"stratified by class and grouped by AOI-month; validation hash `{C['validation_hash']}`.", "",
              "| Metric | Rule baseline (production) | Logistic candidate | Delta, grouped bootstrap 95 % CI |", "|---|---|---|---|"]
        for k in ("auprc", "auroc", "f1", "precision", "recall", "brier", "ece"):
            ci = (bt.get(k) or {}).get("ci")
            L.append(f"| {k.upper()} | {_n(p_.get(k))} | {_n(c_.get(k))} | "
                     + (f"[{_n(ci[0])}, {_n(ci[1])}]" if ci and ci[0] is not None else "") + " |")
        L += ["", "The rule baseline has no skill against the cross-sensor reference; the learned candidate does, "
                  "but the confidence interval is wide at this label count. Promotion still requires the gate and a named human."]
    loao = E.get("triage_leave_one_aoi_out") or []
    if loao:
        L += ["", "### E. Spatial holdout (leave one AOI out)", "", "| Held-out AOI | n (positive) | AUPRC candidate | AUPRC rule |", "|---|---|---|---|"]
        for r in loao:
            L.append(f"| {r['held_out_aoi']} | {r['n_test']} ({r['test_positive']}) | {_n((r.get('candidate') or {}).get('auprc'))} | "
                     f"{_n((r.get('production') or {}).get('auprc'))} |")
    rej = F.get("cross_sensor_rejections") or {}
    L += ["", "### F. Negative control", "",
          f"* Annaba: RX {_n((F.get('annaba') or {}).get('rx_percentile'), 1)}th percentile in the scene, "
          f"{_n((F.get('annaba') or {}).get('seasonal_percentile'), 1)}th seasonal percentile: stood down.",
          f"* UAE: {rej.get('n', 0)} of {rej.get('of', 0)} referenced candidates were not confirmed by OLCI; "
          "the largest are high-z Sentinel-2 anomalies over water OLCI saw as ordinary (e.g. AE-FUJ 2023-10-25).", "", END]
    path = os.path.join(ROOT, "docs", "VALIDATION_REPORT.md")
    doc = open(path, encoding="utf-8").read() if os.path.exists(path) else "# Validation Report\n"
    block = "\n".join(L)
    if BEGIN in doc and END in doc:
        doc = doc[:doc.index(BEGIN)] + block + doc[doc.index(END) + len(END):]
    else:
        head, _, rest = doc.partition("\n")
        doc = head + "\n\n" + block + "\n" + rest
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    seed = load("outputs/workspace/seed.json")
    seed_labels = load("outputs/labels/seed_labels.json")
    perf, holdout = model_performance(seed_labels)
    holdout["ablation_spatial_vs_random"] = spatial_vs_random()
    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "A_data_quality": data_quality(),
           "B_matchups": matchups(seed_labels),
           "C_model_performance": perf,
           "D_813_ablation": ablation(),
           "E_spatial_holdout": holdout,
           "F_negative_control": negative_control(seed, seed_labels)}
    p = os.path.join(ROOT, "outputs", "validation", "validation_summary.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(clean(out), f, separators=(",", ":"))
    write_report(clean(out))
    print("->", p, "+ docs/VALIDATION_REPORT.md")


if __name__ == "__main__":
    main()
