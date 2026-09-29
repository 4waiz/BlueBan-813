"""Quantification: turning optical features into physical estimates, honestly.

Mentor point 4: an index is not a concentration. A chlorophyll-a value in
mg/m3 (or turbidity in NTU, TSS in mg/L) can only be reported after the optical
features have been calibrated against legitimate reference measurements from
the same kind of water, and validated on data the model never saw.

This module:

1. compares candidate regressors (linear, PLSR, random forest, gradient
   boosting, SVR, plus the ridge-on-log model used in the LEARN loop) under
   GROUPED cross-validation, where a group is a station or a sampling day, so
   neighbouring pixels and repeat visits cannot leak across folds;
2. reports MAE, RMSE, R2, bias and n per model with grouped-bootstrap
   confidence intervals, never training-set performance;
3. decides whether a calibration is good enough to be used at all
   (``calibration_verdict``). If it is not, the product keeps reporting the
   PROXY and says why.

Selection is by the grouped-CV score with a parsimony rule: a more complex
model must beat the simplest adequate one by more than its own CI half-width,
otherwise the simpler model is kept.
"""
from __future__ import annotations

import math

import numpy as np

#: Sentinel-2 features offered to calibration models. Band reflectances plus
#: the documented indices from pipeline/s2_features.py.
QUANT_FEATURES = ["B02", "B03", "B04", "B05", "B06", "B8A",
                  "NDCI", "MCI", "RE_RATIO", "CDOM_RATIO", "TUR_NECHAD2016", "HUE_ANGLE"]

#: Minimum evidence before a calibration may be used to print physical units.
MIN_MATCHUPS = 20
MIN_GROUPS = 5
MIN_R2_LOG = 0.4


def _models(n_features: int, seed: int = 813) -> dict:
    from sklearn.cross_decomposition import PLSRegression
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR
    return {
        "linear": make_pipeline(StandardScaler(), LinearRegression()),
        "ridge_log10": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "plsr": make_pipeline(StandardScaler(),
                              PLSRegression(n_components=max(1, min(3, n_features)))),
        "random_forest": RandomForestRegressor(n_estimators=300, min_samples_leaf=3,
                                               random_state=seed, n_jobs=-1),
        "gradient_boosting": GradientBoostingRegressor(n_estimators=200, max_depth=2,
                                                       learning_rate=0.05, subsample=0.8,
                                                       random_state=seed),
        "svr": make_pipeline(StandardScaler(), SVR(C=3.0, epsilon=0.05)),
    }


MODEL_COMPLEXITY = ["linear", "ridge_log10", "plsr", "svr", "random_forest",
                    "gradient_boosting"]


def grouped_cv_predictions(model, X, ly, groups, n_splits: int = 5):
    """Out-of-fold predictions with GroupKFold (or leave-one-group-out if few groups)."""
    from sklearn.base import clone
    from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
    ug = len(set(groups.tolist()))
    splitter = LeaveOneGroupOut() if ug < n_splits else GroupKFold(n_splits=n_splits)
    pred = np.full(len(ly), np.nan)
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    for tr, te in splitter.split(X, ly, groups):
        Xtr = np.where(np.isfinite(X[tr]), X[tr], med)
        Xte = np.where(np.isfinite(X[te]), X[te], med)
        m = clone(model).fit(Xtr, ly[tr])
        pred[te] = np.ravel(m.predict(Xte))
    return pred


def _metrics_log(ly, p):
    r = p - ly
    ss_tot = float(((ly - ly.mean()) ** 2).sum())
    return {"rmse": float(np.sqrt(np.mean(r ** 2))), "mae": float(np.mean(np.abs(r))),
            "bias": float(np.mean(r)),
            "r2": 1 - float((r ** 2).sum()) / ss_tot if ss_tot > 0 else math.nan}


def _boot(ly, p, groups, n=1000, seed=813):
    rng = np.random.default_rng(seed)
    ug = np.array(sorted(set(groups.tolist())))
    gi = {g: np.where(groups == g)[0] for g in ug}
    vals = {"rmse": [], "r2": [], "mae": [], "bias": []}
    for _ in range(n):
        ix = np.concatenate([gi[g] for g in rng.choice(ug, len(ug), replace=True)])
        m = _metrics_log(ly[ix], p[ix])
        for k in vals:
            if m[k] == m[k]:
                vals[k].append(m[k])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
            if v else [math.nan, math.nan] for k, v in vals.items()}


def compare_models(X, y, groups, feature_names=None, target_name="target",
                   unit="", seed: int = 813) -> dict:
    """Grouped-CV comparison of the candidate regressors on log10(target)."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    groups = np.asarray(groups)
    ok = np.isfinite(y) & (y > 0)
    X, y, groups = X[ok], y[ok], groups[ok]
    ly = np.log10(y)
    res = {"target": target_name, "unit": unit, "n": int(len(y)),
           "n_groups": int(len(set(groups.tolist()))),
           "features": list(feature_names or []), "space": "log10",
           "validation": "grouped CV (GroupKFold, or leave-one-group-out if < 5 groups)",
           "models": {}}
    if len(y) < 6 or res["n_groups"] < 3:
        res["error"] = "too few matchups / groups for grouped validation"
        res["verdict"] = calibration_verdict(res)
        return res
    for name, model in _models(X.shape[1], seed).items():
        p = grouped_cv_predictions(model, X, ly, groups)
        m = _metrics_log(ly, p)
        m["ci95"] = _boot(ly, p, groups, seed=seed)
        lin = np.power(10.0, p)
        m["linear"] = {"rmse": float(np.sqrt(np.mean((lin - y) ** 2))),
                       "mae": float(np.mean(np.abs(lin - y))),
                       "bias": float(np.mean(lin - y))}
        res["models"][name] = m
    res["selected"] = select_model(res)
    res["verdict"] = calibration_verdict(res)
    return res


def select_model(res: dict) -> str | None:
    """Simplest model whose grouped-CV RMSE is within the best model's CI."""
    ms = res.get("models") or {}
    if not ms:
        return None
    best = min(ms, key=lambda k: ms[k]["rmse"])
    hi = ms[best]["ci95"]["rmse"][1]
    for name in MODEL_COMPLEXITY:
        if name in ms and ms[name]["rmse"] <= hi:
            return name
    return best


def calibration_verdict(res: dict) -> dict:
    """May this calibration be used to print physical units? Explicit reasons."""
    reasons = []
    n, g = res.get("n", 0), res.get("n_groups", 0)
    if n < MIN_MATCHUPS:
        reasons.append(f"only {n} matchups (need >= {MIN_MATCHUPS})")
    if g < MIN_GROUPS:
        reasons.append(f"only {g} independent groups (need >= {MIN_GROUPS})")
    sel = res.get("selected")
    if sel:
        r2 = res["models"][sel]["r2"]
        lo = res["models"][sel]["ci95"]["r2"][0]
        if not (r2 >= MIN_R2_LOG):
            reasons.append(f"grouped-CV R2 {r2:.2f} below {MIN_R2_LOG}")
        elif not (lo > 0):
            reasons.append("R2 confidence interval includes zero")
    else:
        reasons.append("no model could be evaluated")
    usable = not reasons
    return {"usable_for_physical_units": usable,
            "quantity_kind": "CALIBRATED" if usable else "PROXY",
            "reasons": reasons or ["meets matchup, group and skill thresholds"],
            "thresholds": {"min_matchups": MIN_MATCHUPS, "min_groups": MIN_GROUPS,
                           "min_r2_log10": MIN_R2_LOG}}
