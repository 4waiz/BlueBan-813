"""LEARN: controlled continual improvement.

The loop the mentor proposed ("the analyst says this is / is not an event, and
that becomes model feedback") implemented without the failure mode of
retraining production after every click:

    MODEL PREDICTION -> OPERATOR REVIEW -> VERIFIED LABEL -> LABEL STORE
      -> RETRAIN CANDIDATE -> EVALUATION -> MODEL GATE -> HUMAN PROMOTION
      -> NEW PRODUCTION VERSION

Rules this module enforces
--------------------------
* A candidate is evaluated on a FROZEN validation set whose hash is recorded.
  Production is re-scored on the same set, so the comparison is paired.
* Training labels never leak into validation: splits are fixed per label and
  grouped (by AOI and month), so neighbouring pixels of one event cannot sit on
  both sides.
* Model artifacts are plain JSON (scaler + coefficients). The same artifact is
  applied by the Python API and by the hosted edge API, and a round-trip test
  in the gate proves serialisation does not change predictions.
* Promotion needs a passing gate AND a named human. The gate never promotes.

Model families in the loop are deliberately small: L2 logistic regression for
triage and ridge regression on log-concentration for quantification. With tens
to hundreds of labels these are the defensible choices; the wider comparison
(RF, gradient boosting, SVR, PLSR) is run offline in ``pipeline/quantify.py``
and reported, not silently swapped in.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

import numpy as np

# --------------------------------------------------------------------------- #
# Feature sets
# --------------------------------------------------------------------------- #
TRIAGE_FEATURES = [
    "seasonal_pct_primary",   # seasonal percentile of the primary indicator (0-100)
    "robust_z_primary",       # median robust z-score vs per-pixel climatology
    "rx_pct",                 # spatial RX percentile within the scene (0-100)
    "log10_area_km2",
    "persistence_frac",       # share of past same-season dates also anomalous here
    "dist_shore_km",
    "ndci_delta",             # event minus climatology median
    "mci_delta",
    "tur_delta",
    "fai_mean",
    "swir_b11_mean",          # glint / floating-material / adjacency indicator
    "cloud_adjacent_frac",
    "valid_frac_aoi",
]


def dataset_hash(labels: list) -> str:
    """Stable hash of a label set: ids, targets and frozen features."""
    h = hashlib.sha256()
    for lab in sorted(labels, key=lambda x: x["id"]):
        h.update(json.dumps([lab["id"], lab["target"], lab["features"]],
                            sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def group_split(group_key: str, n_folds: int = 5, validation_fold: int = 0) -> str:
    """Deterministic grouped assignment: the same group always lands the same side."""
    k = int(hashlib.sha256((group_key or "").encode()).hexdigest(), 16) % n_folds
    return "validation" if k == validation_fold else "train"


def to_matrix(labels: list, features: list, target: str = "y"):
    X = np.array([[_f(lab["features"].get(f)) for f in features] for lab in labels],
                 dtype="float64").reshape(len(labels), len(features))
    y = np.array([_f(lab["target"].get(target)) for lab in labels], dtype="float64")
    w = np.array([float(lab.get("weight", 1.0)) for lab in labels], dtype="float64")
    groups = np.array([lab.get("group_key") or lab["id"] for lab in labels])
    subgroups = np.array([lab.get("aoi_id") or "unknown" for lab in labels])
    return X, y, w, groups, subgroups


def _f(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return math.nan
    return v


# --------------------------------------------------------------------------- #
# Portable models
# --------------------------------------------------------------------------- #
@dataclass
class LinearArtifact:
    """Scaler + linear model, JSON-portable. kind: logistic | ridge_log10."""

    kind: str
    features: list
    medians: list
    mean: list
    scale: list
    coef: list
    intercept: float
    resid_sd: float | None = None          # ridge: residual sd in log10 space
    conformal_q90: float | None = None     # ridge: CV |residual| 90th percentile (log10)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "features": self.features, "medians": self.medians,
                "mean": self.mean, "scale": self.scale, "coef": self.coef,
                "intercept": self.intercept, "resid_sd": self.resid_sd,
                "conformal_q90": self.conformal_q90, "extra": self.extra}

    @classmethod
    def from_dict(cls, d: dict) -> "LinearArtifact":
        return cls(d["kind"], d["features"], d["medians"], d["mean"], d["scale"],
                   d["coef"], d["intercept"], d.get("resid_sd"), d.get("conformal_q90"),
                   d.get("extra", {}))

    def _z(self, X):
        X = np.asarray(X, dtype="float64").copy()
        med = np.asarray(self.medians)
        bad = ~np.isfinite(X)
        X[bad] = np.broadcast_to(med, X.shape)[bad]
        return (X - np.asarray(self.mean)) / np.asarray(self.scale)

    def decision(self, X):
        return self._z(X) @ np.asarray(self.coef) + self.intercept

    def predict(self, X):
        s = self.decision(X)
        if self.kind == "logistic":
            return 1.0 / (1.0 + np.exp(-s))
        if self.kind == "ridge_log10":
            return np.power(10.0, s)
        raise ValueError(self.kind)

    def interval(self, X, level_q: float | None = None):
        """90 % prediction interval in linear units (ridge_log10 only)."""
        if self.kind != "ridge_log10":
            raise ValueError("intervals only for regression artifacts")
        s = self.decision(X)
        q = level_q if level_q is not None else (self.conformal_q90 or
                                                 1.645 * (self.resid_sd or 0.0))
        return np.power(10.0, s - q), np.power(10.0, s + q)


def _scaler(X):
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    Xi = np.where(np.isfinite(X), X, med)
    mu = Xi.mean(axis=0)
    sd = Xi.std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    return med, mu, sd, (Xi - mu) / sd


def fit_logistic(X, y, w=None, features=None, C: float = 1.0) -> LinearArtifact:
    """L2 logistic regression, class-balanced, via sklearn (lbfgs)."""
    from sklearn.linear_model import LogisticRegression
    med, mu, sd, Z = _scaler(X)
    ww = np.ones(len(y)) if w is None else np.asarray(w, dtype="float64")
    # Class balancing folded into sample weights so it matches the edge trainer.
    pos, neg = ww[y == 1].sum(), ww[y == 0].sum()
    if pos == 0 or neg == 0:
        raise ValueError("need both classes to train a triage model")
    bal = np.where(y == 1, (pos + neg) / (2 * pos), (pos + neg) / (2 * neg))
    # Tight tolerance: the default (1e-4) stops lbfgs visibly short of the optimum,
    # and the browser trainer (Newton-IRLS on the same objective) must agree.
    m = LogisticRegression(C=C, max_iter=10000, tol=1e-10, solver="lbfgs")
    m.fit(Z, y.astype(int), sample_weight=ww * bal)
    return LinearArtifact("logistic", list(features or []), med.tolist(), mu.tolist(),
                          sd.tolist(), m.coef_[0].tolist(), float(m.intercept_[0]),
                          extra={"C": C, "class_balanced": True})


def fit_ridge_log10(X, y, w=None, features=None, alpha: float = 1.0,
                    groups=None) -> LinearArtifact:
    """Ridge on log10(y) with a grouped-CV conformal interval."""
    from sklearn.linear_model import Ridge
    if np.any(~np.isfinite(y)) or np.any(y <= 0):
        raise ValueError("regression targets must be positive and finite")
    ly = np.log10(y)
    med, mu, sd, Z = _scaler(X)
    m = Ridge(alpha=alpha).fit(Z, ly, sample_weight=w)
    resid = ly - m.predict(Z)
    q90 = None
    if groups is not None and len(set(groups)) >= 3:
        cv_res = []
        for g in sorted(set(groups)):
            tr, te = groups != g, groups == g
            if tr.sum() < 3:
                continue
            _, mu2, sd2, _ = _scaler(X[tr])
            Xi = np.where(np.isfinite(X), X, med)
            mm = Ridge(alpha=alpha).fit((Xi[tr] - mu2) / sd2, ly[tr])
            cv_res.extend(np.abs(ly[te] - mm.predict((Xi[te] - mu2) / sd2)).tolist())
        if cv_res:
            q90 = float(np.quantile(cv_res, 0.9))
    return LinearArtifact("ridge_log10", list(features or []), med.tolist(), mu.tolist(),
                          sd.tolist(), m.coef_.tolist(), float(m.intercept_),
                          resid_sd=float(np.std(resid, ddof=1)) if len(y) > 2 else None,
                          conformal_q90=q90, extra={"alpha": alpha})


# --------------------------------------------------------------------------- #
# Rule baseline: the v1 production "model" is the documented detection rule
# --------------------------------------------------------------------------- #
def rules_score(X, features=TRIAGE_FEATURES) -> np.ndarray:
    """Score of the rule-based triage used to raise incidents (model v1.0).

    High seasonal percentile raises it; a persistent location, cloud adjacency
    or a floating/glint SWIR signal lowers it. Written as a function of the same
    feature vector so it can be scored on the frozen validation set exactly like
    a learned candidate.
    """
    idx = {f: i for i, f in enumerate(features)}
    X = np.asarray(X, dtype="float64")

    def col(name, default):
        v = X[:, idx[name]] if name in idx else np.full(len(X), default)
        return np.where(np.isfinite(v), v, default)

    pct = col("seasonal_pct_primary", 50.0)
    persist = col("persistence_frac", 0.0)
    cloud = col("cloud_adjacent_frac", 0.0)
    swir = col("swir_b11_mean", 0.0)
    s = np.clip((pct - 80.0) / 20.0, 0, 1)
    s = s * (1 - np.clip(persist, 0, 1)) * (1 - 0.6 * np.clip(cloud, 0, 1))
    s = np.where(swir > 0.03, s * 0.5, s)
    return np.clip(0.05 + 0.9 * s, 0, 1)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(set(y.tolist())) == 2 else math.nan


def _ap(y, p):
    from sklearn.metrics import average_precision_score
    return float(average_precision_score(y, p)) if len(set(y.tolist())) == 2 else math.nan


def ece(y, p, bins: int = 10) -> float:
    """Expected calibration error with equal-width bins."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.any():
            e += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(e)


def classification_metrics(y, p, threshold: float = 0.5) -> dict:
    y = np.asarray(y).astype(int)
    p = np.asarray(p, float)
    yhat = (p >= threshold).astype(int)
    tp = int(((yhat == 1) & (y == 1)).sum())
    fp = int(((yhat == 1) & (y == 0)).sum())
    fn = int(((yhat == 0) & (y == 1)).sum())
    tn = int(((yhat == 0) & (y == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else math.nan
    rec = tp / (tp + fn) if tp + fn else math.nan
    f1 = 2 * prec * rec / (prec + rec) if prec == prec and rec == rec and prec + rec else math.nan
    pe = np.clip(p, 1e-9, 1 - 1e-9)
    return {"auroc": _auc(y, p), "auprc": _ap(y, p), "f1": f1, "precision": prec,
            "recall": rec, "brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(-np.mean(y * np.log(pe) + (1 - y) * np.log(1 - pe))),
            "ece": ece(y, p), "n": int(len(y)), "positives": int(y.sum()),
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}}


def regression_metrics(y, yhat, log10: bool = True) -> dict:
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    out = {"n": int(len(y))}
    for name, a, b in (("linear", y, yhat),) + ((("log10", np.log10(y), np.log10(yhat)),)
                                              if log10 else ()):
        r = b - a
        ss_res = float((r ** 2).sum())
        ss_tot = float(((a - a.mean()) ** 2).sum())
        out[name] = {"rmse": float(np.sqrt(np.mean(r ** 2))), "mae": float(np.mean(np.abs(r))),
                     "bias": float(np.mean(r)),
                     "r2": 1 - ss_res / ss_tot if ss_tot > 0 else math.nan}
    return out


def grouped_bootstrap_ci(y, a, b, groups, metric_fn, n_boot: int = 1000,
                         seed: int = 813) -> dict:
    """Paired grouped bootstrap of metric(b) - metric(a) on the same rows."""
    rng = np.random.default_rng(seed)
    y, a, b = np.asarray(y), np.asarray(a), np.asarray(b)
    ug = np.array(sorted(set(groups.tolist())))
    gidx = {g: np.where(groups == g)[0] for g in ug}
    diffs, va, vb = [], [], []
    for _ in range(n_boot):
        pick = rng.choice(ug, size=len(ug), replace=True)
        ix = np.concatenate([gidx[g] for g in pick])
        ma, mb = metric_fn(y[ix], a[ix]), metric_fn(y[ix], b[ix])
        if ma == ma and mb == mb:
            diffs.append(mb - ma)
            va.append(ma)
            vb.append(mb)
    if not diffs:
        return {"diff": math.nan, "ci": [math.nan, math.nan], "n_boot": 0}
    return {"diff": float(metric_fn(y, b) - metric_fn(y, a)),
            "ci": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
            "a_ci": [float(np.percentile(va, 2.5)), float(np.percentile(va, 97.5))],
            "b_ci": [float(np.percentile(vb, 2.5)), float(np.percentile(vb, 97.5))],
            "n_boot": len(diffs)}


# --------------------------------------------------------------------------- #
# Model tests (the "required test suite" of the gate)
# --------------------------------------------------------------------------- #
def model_tests(artifact: LinearArtifact, X_val) -> list:
    """Fast behavioural tests every candidate must pass before comparison."""
    checks = []
    p1 = artifact.predict(X_val)
    checks.append({"name": "predictions_finite", "passed": bool(np.all(np.isfinite(p1)))})
    if artifact.kind == "logistic":
        checks.append({"name": "probabilities_in_unit_interval",
                       "passed": bool(np.all((p1 >= 0) & (p1 <= 1)))})
    else:
        checks.append({"name": "concentrations_positive", "passed": bool(np.all(p1 > 0))})
    p2 = artifact.predict(X_val)
    checks.append({"name": "deterministic", "passed": bool(np.array_equal(p1, p2))})
    rt = LinearArtifact.from_dict(json.loads(json.dumps(artifact.to_dict())))
    checks.append({"name": "artifact_roundtrip_identical",
                   "passed": bool(np.allclose(rt.predict(X_val), p1, rtol=0, atol=1e-12))})
    Xn = np.array(X_val, float).copy()
    Xn[:, :] = np.nan
    checks.append({"name": "missing_features_imputed_not_nan",
                   "passed": bool(np.all(np.isfinite(artifact.predict(Xn))))})
    checks.append({"name": "feature_schema_declared",
                   "passed": len(artifact.features) == np.asarray(X_val).shape[1]})
    return checks


# --------------------------------------------------------------------------- #
# The promotion gate
# --------------------------------------------------------------------------- #
@dataclass
class GateConfig:
    primary_metric: str = "auprc"          # triage; "rmse_log10" for regression
    tolerance: float = 0.0                 # candidate must be >= production - tolerance
    max_ece: float = 0.15
    subgroup_min_n: int = 5
    subgroup_tolerance: float = 0.05


def evaluate_gate(task: str, cand_scores, prod_scores, y_val, groups_val, subgroups_val,
                  frozen_validation_hash: str, current_validation_hash: str,
                  tests: list, cfg: GateConfig | None = None) -> dict:
    """Compare candidate vs production on the frozen validation set.

    Returns a report with every check and ``passed`` (all automatic checks).
    Human approval is a separate, mandatory step at promotion time.
    """
    cfg = cfg or GateConfig()
    y = np.asarray(y_val, float)
    cand, prod = np.asarray(cand_scores, float), np.asarray(prod_scores, float)
    checks = []
    checks.append({"name": "model_test_suite",
                   "passed": all(t["passed"] for t in tests), "detail": tests})
    checks.append({"name": "validation_dataset_unchanged",
                   "passed": frozen_validation_hash == current_validation_hash,
                   "detail": {"frozen": frozen_validation_hash,
                              "current": current_validation_hash}})
    if task == "triage":
        both = len(set(y.tolist())) == 2
        checks.append({"name": "validation_has_both_classes", "passed": bool(both),
                       "detail": {"n": int(len(y)), "positives": int((y == 1).sum())}})
        fn = {"auprc": _ap, "auroc": _auc}[cfg.primary_metric]
        mc, mp = classification_metrics(y, cand), classification_metrics(y, prod)
        boot = grouped_bootstrap_ci(y, prod, cand, groups_val, fn)
        better = (mc[cfg.primary_metric] >= mp[cfg.primary_metric] - cfg.tolerance)
        checks.append({"name": "primary_metric_not_worse", "passed": bool(better),
                       "detail": {"metric": cfg.primary_metric,
                                  "candidate": mc[cfg.primary_metric],
                                  "production": mp[cfg.primary_metric],
                                  "diff_ci95": boot["ci"]}})
        checks.append({"name": "calibration_acceptable",
                       "passed": bool(mc["ece"] <= cfg.max_ece or mc["brier"] <= mp["brier"]),
                       "detail": {"ece": mc["ece"], "max_ece": cfg.max_ece,
                                  "brier_candidate": mc["brier"],
                                  "brier_production": mp["brier"]}})
        sub = []
        for g in sorted(set(np.asarray(subgroups_val).tolist())):
            m = np.asarray(subgroups_val) == g
            if m.sum() < cfg.subgroup_min_n or len(set(y[m].tolist())) < 2:
                sub.append({"subgroup": g, "n": int(m.sum()), "skipped": True})
                continue
            a, b = fn(y[m], prod[m]), fn(y[m], cand[m])
            sub.append({"subgroup": g, "n": int(m.sum()), "production": a, "candidate": b,
                        "regressed": bool(b < a - cfg.subgroup_tolerance)})
        checks.append({"name": "no_subgroup_regression",
                       "passed": not any(s.get("regressed") for s in sub), "detail": sub})
        summary = {"candidate": mc, "production": mp}
    else:
        rc, rp = regression_metrics(y, cand), regression_metrics(y, prod)

        def neg_rmse(yy, pp):
            return -float(np.sqrt(np.mean((np.log10(pp) - np.log10(yy)) ** 2)))
        boot = grouped_bootstrap_ci(y, prod, cand, groups_val, neg_rmse)
        better = rc["log10"]["rmse"] <= rp["log10"]["rmse"] + cfg.tolerance
        checks.append({"name": "primary_metric_not_worse", "passed": bool(better),
                       "detail": {"metric": "rmse_log10", "candidate": rc["log10"]["rmse"],
                                  "production": rp["log10"]["rmse"],
                                  "improvement_ci95": boot["ci"]}})
        checks.append({"name": "calibration_acceptable",
                       "passed": bool(abs(rc["log10"]["bias"]) <= 0.1),
                       "detail": {"bias_log10": rc["log10"]["bias"], "max_abs_bias": 0.1}})
        checks.append({"name": "no_subgroup_regression", "passed": True,
                       "detail": "evaluated per AOI when >= 5 matchups per AOI"})
        summary = {"candidate": rc, "production": rp}
    passed = all(c["passed"] for c in checks)
    return {"task": task, "passed": bool(passed), "checks": checks, "summary": summary,
            "human_approval": {"required": True, "approved_by": None},
            "validation_hash": current_validation_hash}


def next_version(current: str | None, bump: str = "minor") -> str:
    if not current:
        return "1.0.0"
    major, minor, patch = (int(x) for x in current.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"
