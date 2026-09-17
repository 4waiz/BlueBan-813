"""The hyperspectral ablation: does 813's spectral detail measurably help?

This is a controlled experiment, not a comparison of two different scenes.

Both candidate sensors are simulated from the SAME Tanager pixels, so there is
no difference in acquisition time, atmosphere, illumination, geolocation or
water state between the two arms. The only variable is spectral configuration:

    arm A   Sentinel-2 MSI       11 broad bands   (the multispectral baseline)
    arm B   Satellite 813       205 narrow bands  (the hyperspectral candidate)

Target: ESA Sentinel-3 OLCI Level-2 operational retrievals (CHL_NN, TSM_NN),
produced by a different instrument through a different processing chain, so
neither arm can trivially reproduce it.

Validation protocol
-------------------
Splits are SPATIAL, not random. Neighbouring water pixels are near-duplicates,
so a random split leaks almost-identical samples across train and test and
inflates every score. The official participant guide names this explicitly as a
mistake that sinks a PoC. We tile the AOI into blocks and assign whole blocks to
folds, and we report the random-split number too so the size of that inflation
is visible.

Model: Partial Least Squares Regression. Hyperspectral bands are almost
perfectly collinear, which makes ordinary least squares unstable; PLSR projects
onto a small number of latent components that maximise covariance with the
target, and is the standard choice for spectroscopic regression.

Usage: python experiments/hyperspectral_ablation.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.satellite813 import (spec_813, spec_sentinel2,          # noqa: E402
                                   resample_spectra)

MATCHUP = "data/cache/matchup"
OUT = "outputs/validation"
MAX_DT_HOURS = 30.0        # matchup window; see caveats in the output
BLOCK_KM = 3.0             # spatial block size for blocked cross-validation
N_FOLDS = 5
RNG = np.random.default_rng(813)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def regression_metrics(y_true, y_pred):
    ok = np.isfinite(y_true) & np.isfinite(y_pred)
    y, p = y_true[ok], y_pred[ok]
    n = y.size
    if n < 5:
        return {"n": int(n)}
    resid = p - y
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "n": int(n),
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else None,
        "rmse": float(np.sqrt(np.mean(resid ** 2))),
        "mae": float(np.mean(np.abs(resid))),
        "bias": float(np.mean(resid)),
        "pearson_r": float(np.corrcoef(y, p)[0, 1]) if n > 2 else None,
    }


def bootstrap_ci(y_true, y_pred, stat="r2", n_boot=2000, alpha=0.05):
    """Percentile bootstrap confidence interval for one metric."""
    ok = np.isfinite(y_true) & np.isfinite(y_pred)
    y, p = y_true[ok], y_pred[ok]
    n = y.size
    if n < 10:
        return None
    vals = []
    for _ in range(n_boot):
        i = RNG.integers(0, n, n)
        m = regression_metrics(y[i], p[i])
        v = m.get(stat)
        if v is not None and np.isfinite(v):
            vals.append(v)
    if not vals:
        return None
    lo, hi = np.percentile(vals, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"lo": float(lo), "hi": float(hi), "n_boot": len(vals)}


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #
def spatial_blocks(lon, lat, block_km=BLOCK_KM):
    """Assign each sample to a spatial block id."""
    lat0 = float(np.mean(lat))
    kx = 111.320 * np.cos(np.radians(lat0))
    bx = np.floor((lon - lon.min()) * kx / block_km).astype(int)
    by = np.floor((lat - lat.min()) * 110.574 / block_km).astype(int)
    return bx * 10_000 + by


def blocked_folds(blocks, n_folds=N_FOLDS):
    """Assign whole spatial blocks to folds."""
    uniq = np.unique(blocks)
    RNG.shuffle(uniq)
    assign = {b: i % n_folds for i, b in enumerate(uniq)}
    return np.array([assign[b] for b in blocks]), len(uniq)


def random_folds(n, n_folds=N_FOLDS):
    f = np.arange(n) % n_folds
    RNG.shuffle(f)
    return f


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
MAX_COMPONENTS = 15


def fit_predict_plsr(Xtr, ytr, Xte, blocks_tr, max_components=MAX_COMPONENTS):
    """PLSR whose component count is chosen by SPATIALLY BLOCKED inner CV.

    The inner split must be blocked for the same reason the outer one is. With a
    random inner split, neighbouring near-duplicate samples sit on both sides of
    the inner fold, every extra latent component looks like it helps, and the
    selector runs to the cap. The resulting model then collapses on a genuinely
    held-out spatial block. In an early run of this experiment, a random inner
    split drove selection to the 20-component cap and produced an outer
    R2 of -15.7; that was a flaw in the protocol, not a property of the data.
    """
    from sklearn.cross_decomposition import PLSRegression
    from sklearn.preprocessing import StandardScaler

    sx = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = sx.transform(Xtr), sx.transform(Xte)

    ub = np.unique(blocks_tr)
    n_inner = int(min(4, max(2, len(ub) // 3)))
    order = ub.copy()
    RNG.shuffle(order)
    inner_of_block = {b: i % n_inner for i, b in enumerate(order)}
    inner = np.array([inner_of_block[b] for b in blocks_tr])

    # Never allow more components than the smallest inner training set can
    # support, and never more than the number of features.
    min_inner_train = min((inner != f).sum() for f in range(n_inner))
    ncomp_max = int(min(max_components, Xtr.shape[1], max(2, min_inner_train // 10)))

    best_k, best_score = 1, -np.inf
    curve = []
    for k in range(1, ncomp_max + 1):
        preds = np.full(len(ytr), np.nan)
        for f in range(n_inner):
            tr, te = inner != f, inner == f
            if tr.sum() < k + 2 or te.sum() < 2:
                continue
            try:
                m = PLSRegression(n_components=k).fit(Xtr_s[tr], ytr[tr])
                preds[te] = m.predict(Xtr_s[te]).ravel()
            except Exception:                              # noqa: BLE001
                pass
        s = regression_metrics(ytr, preds).get("r2")
        curve.append((k, s))
        if s is not None and np.isfinite(s) and s > best_score:
            best_score, best_k = s, k

    model = PLSRegression(n_components=best_k).fit(Xtr_s, ytr)
    return model.predict(Xte_s).ravel(), best_k


def cross_validate(X, y, folds, blocks, label=""):
    pred = np.full(len(y), np.nan)
    ks = []
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        if tr.sum() < 20 or te.sum() < 3:
            continue
        p, k = fit_predict_plsr(X[tr], y[tr], X[te], blocks[tr])
        pred[te] = p
        ks.append(k)
    m = regression_metrics(y, pred)
    m["mean_n_components"] = float(np.mean(ks)) if ks else None
    m["max_components_allowed"] = MAX_COMPONENTS
    m["n_features"] = int(X.shape[1])
    m["label"] = label
    return m, pred


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    os.makedirs(OUT, exist_ok=True)
    meta = json.load(open(os.path.join(MATCHUP, "matchup_meta.json"), encoding="utf-8"))
    recs = json.load(open(os.path.join(MATCHUP, "matchup_records.json"), encoding="utf-8"))
    wl = np.asarray(meta["wavelengths_nm"], dtype=float)
    print(f"Loaded {len(recs)} matchups, {len(wl)} source bands")

    keep = [r for r in recs if abs(r["dt_hours"]) <= MAX_DT_HOURS]
    print(f"Within +/-{MAX_DT_HOURS} h: {len(keep)}")
    if len(keep) < 60:
        print("Too few matchups; aborting.")
        return 1

    spectra = np.array([r["spectrum"] for r in keep], dtype="float64")
    lon = np.array([r["lon"] for r in keep])
    lat = np.array([r["lat"] for r in keep])
    dts = sorted({r["olci_datetime"][:10] for r in keep})
    dt_h = np.array([r["dt_hours"] for r in keep])

    sensors = {
        "S2_multispectral_11band": spec_sentinel2(),
        "813_hyperspectral_205band": spec_813(),
        "813_hyperspectral_261band_5nm": spec_813(n_bands=261),
    }
    features = {}
    for name, spec in sensors.items():
        F, sup = resample_spectra(wl, spectra, spec)
        colok = np.isfinite(F).all(axis=0)
        features[name] = F[:, colok]
        print(f"  {name:<32} {spec.n_bands:>4} bands -> {int(colok.sum()):>4} usable")

    targets = {}
    for tname, key in (("CHL_NN_log10", "CHL_NN"), ("TSM_NN_log10", "TSM_NN")):
        if key in keep[0]:
            targets[tname] = np.array([r[key] for r in keep], dtype="float64")

    blocks = spatial_blocks(lon, lat)
    bfolds, n_blocks = blocked_folds(blocks)
    rfolds = random_folds(len(keep))
    print(f"Spatial blocks: {n_blocks} of {BLOCK_KM} km -> {N_FOLDS} folds")

    report = {
        "experiment": "Multispectral vs simulated-813 hyperspectral ablation",
        "design": "Both feature sets convolved from the SAME Tanager pixels; "
                  "only spectral configuration differs.",
        "source_scene": meta["tanager_scene"],
        "source_datetime": meta["tanager_datetime"],
        "target_source": "Sentinel-3 OLCI WFR Level-2 (ESA operational)",
        "target_dates": dts,
        "matchup_window_hours": MAX_DT_HOURS,
        "matchup_dt_hours": {"min": float(dt_h.min()), "max": float(dt_h.max()),
                             "median": float(np.median(dt_h))},
        "n_matchups": len(keep),
        "n_spatial_blocks": int(n_blocks),
        "block_km": BLOCK_KM,
        "n_folds": N_FOLDS,
        "model": "PLSR, components chosen by inner blocked CV",
        "targets": {},
    }

    for tname, y in targets.items():
        ok = np.isfinite(y)
        print(f"\n=== TARGET {tname}  (n={int(ok.sum())}, "
              f"range {y[ok].min():.3f}..{y[ok].max():.3f}, sd={y[ok].std():.4f}) ===")
        tblock = {
            "n": int(ok.sum()),
            "target_min": float(y[ok].min()), "target_max": float(y[ok].max()),
            "target_sd": float(y[ok].std()),
            "units": "log10(mg m^-3)" if "CHL" in tname else "log10(g m^-3)",
            "spatial_blocked": {}, "random_split": {},
        }
        preds_store = {}
        for sname, X in features.items():
            m_b, p_b = cross_validate(X[ok], y[ok], bfolds[ok], blocks[ok], sname)
            m_b["r2_ci95"] = bootstrap_ci(y[ok], p_b, "r2")
            m_b["rmse_ci95"] = bootstrap_ci(y[ok], p_b, "rmse")
            tblock["spatial_blocked"][sname] = m_b
            preds_store[sname] = p_b
            m_r, _ = cross_validate(X[ok], y[ok], rfolds[ok], rfolds[ok], sname)
            tblock["random_split"][sname] = m_r
            print(f"  {sname:<32} BLOCKED r2={m_b.get('r2'):+.4f} "
                  f"rmse={m_b.get('rmse'):.4f} mae={m_b.get('mae'):.4f} "
                  f"k={m_b.get('mean_n_components')}  | RANDOM r2={m_r.get('r2'):+.4f}")

        base = tblock["spatial_blocked"]["S2_multispectral_11band"]
        lift = {}
        for sname in ("813_hyperspectral_205band", "813_hyperspectral_261band_5nm"):
            hs = tblock["spatial_blocked"][sname]
            d = {}
            for k in ("r2", "rmse", "mae"):
                b, h = base.get(k), hs.get(k)
                if b is None or h is None:
                    continue
                d[f"{k}_baseline"] = round(b, 6)
                d[f"{k}_hyperspectral"] = round(h, 6)
                d[f"{k}_absolute_change"] = round(h - b, 6)
                if k == "r2":
                    d["r2_gain"] = round(h - b, 6)
                elif b != 0:
                    d[f"{k}_reduction_pct"] = round(100.0 * (b - h) / abs(b), 3)
            # Paired bootstrap on the difference, which is the honest way to
            # ask whether the improvement survives resampling.
            pb, ph = preds_store["S2_multispectral_11band"], preds_store[sname]
            good = np.isfinite(pb) & np.isfinite(ph)
            yv = y[ok][good]
            diffs = []
            for _ in range(2000):
                i = RNG.integers(0, yv.size, yv.size)
                rb = regression_metrics(yv[i], pb[good][i]).get("r2")
                rh = regression_metrics(yv[i], ph[good][i]).get("r2")
                if rb is not None and rh is not None:
                    diffs.append(rh - rb)
            if diffs:
                lo, hi = np.percentile(diffs, [2.5, 97.5])
                d["r2_gain_ci95"] = {"lo": float(lo), "hi": float(hi)}
                d["r2_gain_significant"] = bool(lo > 0)
                d["p_gain_positive"] = float(np.mean(np.array(diffs) > 0))
            lift[sname] = d
            print(f"  LIFT {sname}: dR2={d.get('r2_gain'):+.4f} "
                  f"RMSE-{d.get('rmse_reduction_pct', 0):.1f}% "
                  f"significant={d.get('r2_gain_significant')}")
        tblock["hyperspectral_lift"] = lift
        report["targets"][tname] = tblock

    report["caveats"] = [
        f"OLCI matchups are offset from the Tanager acquisition by a median "
        f"{np.median(dt_h):+.1f} h. Coastal water can change materially in a day, "
        f"so the target carries real temporal noise. This depresses ALL arms "
        f"equally and therefore does not bias the comparison between them, but "
        f"it does cap the achievable absolute R2.",
        "OLCI is 300 m; Tanager spectra were averaged over the OLCI footprint "
        "(>= 25 contributing 30 m water pixels per matchup).",
        "OLCI CHL_NN and TSM_NN are model retrievals, not in-situ measurements. "
        "This experiment measures agreement with an operational product, not "
        "accuracy against ground truth.",
        "The 813 arm is simulated at Tanager's 30 m, not 813's specified 20 m, "
        "so it is pessimistic about the real sensor's spatial capability.",
        "No in-situ data was available for this AOI (see DATA_ACCESS_AUDIT.md).",
    ]

    path = os.path.join(OUT, "hyperspectral_lift.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
