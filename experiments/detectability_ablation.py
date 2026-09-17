"""Experiment 2: would a multispectral sensor have seen this event?

The OLCI-target ablation (``hyperspectral_ablation.py``) is honest but
underpowered: its target is an operational product from a different sensor
25 hours away at 300 m, and neither arm explains much variance, so it cannot
resolve a difference between them. Rather than hunt for a target that flatters
the hyperspectral arm, we ask a different question that this dataset CAN answer
and that an operator actually cares about:

    An event has been characterised using the full 368-band hyperspectral
    spectrum. How much of that characterisation survives if you only have
    Sentinel-2's 11 broad bands?

What the reference is, precisely
--------------------------------
The reference labels come from the RX detector run on all 368 product-good
Tanager bands. This is NOT ground truth, and we never call it that. It is the
judgment of a full-spectrum instrument, and the experiment measures how well
each reduced sensor configuration reproduces it.

Both arms are strict information-reductions of that same source, so neither is
advantaged by construction; 813 is simply closer to it. The informative quantity
is the MAGNITUDE of the gap. If 11 bands recover the full-spectrum answer almost
perfectly, hyperspectral adds little for this task and we should say so. If they
do not, the shortfall is what a dedicated hyperspectral aquatic mission buys.

Protocol
--------
* Labels are taken from confident populations only. Pixels between the
  background and anomaly thresholds are ambiguous and are dropped, so the
  classifier is not scored on the detector's own borderline cases.
* Splits are spatial blocks, for the same reason as experiment 1.
* Class imbalance is handled by balanced class weighting, and we report
  precision, recall, F1 and ROC-AUC rather than accuracy.

Usage: python experiments/detectability_ablation.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.satellite813 import (TanagerScene, spec_813,            # noqa: E402
                                   spec_sentinel2, resample_spectra)

TANAGER = "data/raw/tanager/20250601_104901_58_4001_ortho_sr_hdf5.h5"
OUT = "outputs/validation"
BLOCK_PX = 40            # 40 x 30 m = 1.2 km spatial blocks
N_FOLDS = 5
MAX_PER_CLASS = 20000
RNG = np.random.default_rng(813)


def classification_metrics(y, p, prob):
    from sklearn.metrics import (roc_auc_score, precision_score,
                                 recall_score, f1_score, confusion_matrix,
                                 average_precision_score)
    ok = np.isfinite(prob)
    y, p, prob = y[ok], p[ok], prob[ok]
    cm = confusion_matrix(y, p, labels=[0, 1])
    return {
        "n": int(y.size),
        "n_positive": int(y.sum()),
        "precision": float(precision_score(y, p, zero_division=0)),
        "recall": float(recall_score(y, p, zero_division=0)),
        "f1": float(f1_score(y, p, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, prob)) if len(np.unique(y)) > 1 else None,
        "average_precision": float(average_precision_score(y, prob))
        if len(np.unique(y)) > 1 else None,
        "confusion_matrix": {"tn": int(cm[0, 0]), "fp": int(cm[0, 1]),
                             "fn": int(cm[1, 0]), "tp": int(cm[1, 1])},
    }


def run_cv(X, y, folds):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    pred = np.full(len(y), np.nan)
    prob = np.full(len(y), np.nan)
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        if tr.sum() < 50 or te.sum() < 10 or len(np.unique(y[tr])) < 2:
            continue
        sx = StandardScaler().fit(X[tr])
        m = LogisticRegression(max_iter=3000, class_weight="balanced", C=1.0)
        m.fit(sx.transform(X[tr]), y[tr])
        pr = m.predict_proba(sx.transform(X[te]))[:, 1]
        prob[te] = pr
        pred[te] = (pr >= 0.5).astype(int)
    ok = np.isfinite(prob)
    return classification_metrics(y[ok], pred[ok].astype(int), prob[ok]), prob


def main():
    os.makedirs(OUT, exist_ok=True)
    scene = TanagerScene(TANAGER)
    water = np.load("data/cache/water.npy")
    score = np.load("data/cache/rx_score.npy")
    meta = json.load(open("data/cache/rx_meta.json", encoding="utf-8"))
    thr = float(meta["threshold_score"])
    good = np.where(scene.good_wavelengths)[0]
    src_nm = scene.wavelengths[good]
    print(f"RX threshold (empirical 1% background FAR): {thr:.2f}")

    # Two regimes, because they answer different questions.
    #
    # EASY: confident anomaly vs confident background, ambiguous middle dropped.
    #       "Would a multispectral sensor notice an obvious plume?"
    # HARD: the whole water population at the operational threshold, ambiguous
    #       pixels included. "Would it draw the same operational boundary,
    #       including the marginal cases you want to catch early?"
    #
    # The HARD regime is the operationally meaningful one. The EASY regime is
    # reported as a control: if both arms saturate there, that is evidence that
    # gross events do not require hyperspectral data, and we say so.
    regime = os.environ.get("BLUEBAN_REGIME", "hard").lower()
    bg_cut = float(np.nanpercentile(score[water], 50))
    pos = water & np.isfinite(score) & (score >= thr)
    if regime == "easy":
        neg = water & np.isfinite(score) & (score <= bg_cut)
        dropped = int((water & ~pos & ~neg).sum())
    else:
        neg = water & np.isfinite(score) & (score < thr)
        dropped = 0
    print(f"regime               : {regime.upper()}")
    print(f"anomaly px           : {int(pos.sum())}")
    print(f"background px        : {int(neg.sum())}")
    print(f"ambiguous dropped    : {dropped}")

    rows, cols = scene.rows, scene.cols
    rr, cc = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    blocks = (rr // BLOCK_PX) * 10_000 + (cc // BLOCK_PX)

    # Subsample the majority class, but keep every spatial block represented.
    idx_pos = np.argwhere(pos)
    idx_neg = np.argwhere(neg)
    if len(idx_pos) > MAX_PER_CLASS:
        idx_pos = idx_pos[RNG.choice(len(idx_pos), MAX_PER_CLASS, replace=False)]
    if len(idx_neg) > MAX_PER_CLASS:
        idx_neg = idx_neg[RNG.choice(len(idx_neg), MAX_PER_CLASS, replace=False)]
    sel = np.vstack([idx_pos, idx_neg])
    y = np.concatenate([np.ones(len(idx_pos), int), np.zeros(len(idx_neg), int)])
    blk = blocks[sel[:, 0], sel[:, 1]]
    print(f"sampled: {len(idx_pos)} positive, {len(idx_neg)} negative, "
          f"{len(np.unique(blk))} spatial blocks")

    # Read the spectra of the selected pixels only.
    cube = scene.read_cube(good)
    spectra = cube[:, sel[:, 0], sel[:, 1]].T.astype("float64")   # (n, bands)
    del cube
    fin = np.isfinite(spectra).all(axis=1)
    spectra, y, blk = spectra[fin], y[fin], blk[fin]
    print(f"usable samples: {len(y)} ({int(y.sum())} positive)")

    ub = np.unique(blk)
    RNG.shuffle(ub)
    fold_of = {b: i % N_FOLDS for i, b in enumerate(ub)}
    bfolds = np.array([fold_of[b] for b in blk])
    rfolds = RNG.permutation(len(y)) % N_FOLDS

    sensors = {
        "S2_multispectral_11band": spec_sentinel2(),
        "813_hyperspectral_205band": spec_813(),
        "813_hyperspectral_261band_5nm": spec_813(n_bands=261),
    }
    report = {
        "experiment": "Event detectability by sensor configuration",
        "question": "How much of a full-spectrum (368-band) anomaly "
                    "characterisation survives at each sensor's spectral "
                    "resolution?",
        "reference_labels": {
            "source": "RX detector on all 368 product-good Tanager bands",
            "is_ground_truth": False,
            "note": "A full-spectrum instrument's judgment, not an in-situ "
                    "measurement. This experiment measures reproduction of that "
                    "judgment at reduced spectral resolution.",
            "threshold": thr,
            "background_cut_percentile": 50 if regime == "easy" else None,
            "regime": regime,
            "ambiguous_pixels_dropped": dropped,
        },
        "n_samples": int(len(y)),
        "n_positive": int(y.sum()),
        "n_spatial_blocks": int(len(ub)),
        "block_size_m": BLOCK_PX * 30,
        "n_folds": N_FOLDS,
        "model": "Logistic regression, balanced class weights",
        "results": {"spatial_blocked": {}, "random_split": {}},
    }

    probs = {}
    for name, spec in sensors.items():
        F, _ = resample_spectra(src_nm, spectra, spec)
        colok = np.isfinite(F).all(axis=0)
        X = F[:, colok]
        mb, pb = run_cv(X, y, bfolds)
        mr, _ = run_cv(X, y, rfolds)
        mb["n_features"] = int(X.shape[1])
        mr["n_features"] = int(X.shape[1])
        report["results"]["spatial_blocked"][name] = mb
        report["results"]["random_split"][name] = mr
        probs[name] = pb
        print(f"  {name:<32} BLOCKED f1={mb['f1']:.4f} auc={mb['roc_auc']:.4f} "
              f"prec={mb['precision']:.4f} rec={mb['recall']:.4f} "
              f"| RANDOM f1={mr['f1']:.4f} auc={mr['roc_auc']:.4f}")

    base = report["results"]["spatial_blocked"]["S2_multispectral_11band"]
    lift = {}
    for name in ("813_hyperspectral_205band", "813_hyperspectral_261band_5nm"):
        hs = report["results"]["spatial_blocked"][name]
        d = {}
        for k in ("f1", "roc_auc", "precision", "recall", "average_precision"):
            b, h = base.get(k), hs.get(k)
            if b is None or h is None:
                continue
            d[f"{k}_baseline"] = round(b, 6)
            d[f"{k}_hyperspectral"] = round(h, 6)
            d[f"{k}_absolute_gain"] = round(h - b, 6)
            d[f"{k}_relative_gain_pct"] = round(100.0 * (h - b) / b, 3) if b else None

        # Paired bootstrap on the F1 difference.
        pb_, ph_ = probs["S2_multispectral_11band"], probs[name]
        okm = np.isfinite(pb_) & np.isfinite(ph_)
        from sklearn.metrics import f1_score
        yv = y[okm]
        diffs = []
        for _ in range(1000):
            i = RNG.integers(0, yv.size, yv.size)
            fb = f1_score(yv[i], (pb_[okm][i] >= 0.5).astype(int), zero_division=0)
            fh = f1_score(yv[i], (ph_[okm][i] >= 0.5).astype(int), zero_division=0)
            diffs.append(fh - fb)
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        d["f1_gain_ci95"] = {"lo": float(lo), "hi": float(hi)}
        d["f1_gain_significant"] = bool(lo > 0)
        d["p_gain_positive"] = float(np.mean(np.array(diffs) > 0))
        lift[name] = d
        print(f"  LIFT {name}: dF1={d.get('f1_absolute_gain'):+.4f} "
              f"({d.get('f1_relative_gain_pct'):+.1f}%) "
              f"dAUC={d.get('roc_auc_absolute_gain'):+.4f} "
              f"significant={d['f1_gain_significant']}")

    report["hyperspectral_lift"] = lift
    report["caveats"] = [
        "Reference labels come from the full-spectrum RX detector, not from "
        "in-situ measurement. This quantifies information loss at reduced "
        "spectral resolution; it does not establish that the detected anomaly "
        "is any particular substance.",
        "Both arms are convolved from the same Tanager pixels, so the only "
        "difference is spectral configuration.",
        "The 813 arm is simulated at 30 m, not its specified 20 m, so it is "
        "pessimistic about the real sensor.",
        "Ambiguous pixels between the background and anomaly thresholds were "
        "excluded, so these figures describe separation of confident "
        "populations and would be lower on borderline cases.",
    ]

    report["regime"] = regime
    path = os.path.join(OUT, f"detectability_lift_{regime}.json")
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
