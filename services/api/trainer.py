"""Training jobs, the promotion gate and human promotion, over the Store.

Nothing here ever promotes a model on its own. ``run_training_job`` produces a
CANDIDATE with a gate report; ``promote`` requires both a passing gate and a
named human approver who is not a system account.
"""
from __future__ import annotations

import numpy as np

from pipeline import learning as L
from pipeline import incidents as inc_mod

SYSTEM_ACTORS = {"", "system", "pipeline", "trainer", "gate", "auto"}
MIN_TRAIN = {"triage": 12, "quantify": 8}
MIN_PER_CLASS = 3


def _task_family(task: str) -> str:
    return "triage" if task == "triage" else "quantify"


def _features_for(task: str) -> list:
    if task == "triage":
        return list(L.TRIAGE_FEATURES)
    from pipeline import quantify
    return list(quantify.QUANT_FEATURES)


def _score(model: dict | None, X, task: str, features: list):
    """Scores of an existing model on X (rules or linear artifact)."""
    if model is None:
        return None
    if model["model_type"] == "rules":
        return L.rules_score(X, features)
    art = L.LinearArtifact.from_dict(model["artifact"])
    if art.features != features:
        idx = [features.index(f) if f in features else None for f in art.features]
        X = np.column_stack([X[:, i] if i is not None else np.full(len(X), np.nan)
                             for i in idx])
    return art.predict(X)


def run_training_job(store, task: str, requested_by: str) -> dict:
    job = store.create_job(task, requested_by)
    jid = job["id"]
    log = []

    def step(msg, **kw):
        log.append({"at": inc_mod.now_utc(), "msg": msg, **kw})

    store.update_job(jid, status="RUNNING", started_at=inc_mod.now_utc(), log=log)
    try:
        fam = _task_family(task)
        feats = _features_for(task)
        train = store.labels(task, "train")
        val = store.labels(task, "validation")
        if fam == "triage":
            train = [l for l in train if l["target"].get("y") in (0, 1)]
            val = [l for l in val if l["target"].get("y") in (0, 1)]
        step("labels loaded", n_train=len(train), n_validation=len(val))

        frozen_key = f"validation_hash:{task}"
        frozen = store.meta_get(frozen_key)
        current = L.dataset_hash(val)
        if frozen is None:
            store.meta_set(frozen_key, current)
            frozen = current
            step("validation set frozen for the first time", hash=current)
        if len(val) == 0:
            raise ValueError("no validation labels: freeze a validation set before training")

        Xtr, ytr, wtr, gtr, _ = L.to_matrix(train, feats)
        Xva, yva, _, gva, sva = L.to_matrix(val, feats)
        if len(train) < MIN_TRAIN[fam]:
            raise ValueError(f"insufficient verified labels: {len(train)} in train, "
                             f"need >= {MIN_TRAIN[fam]}")
        if fam == "triage":
            npos, nneg = int((ytr == 1).sum()), int((ytr == 0).sum())
            if npos < MIN_PER_CLASS or nneg < MIN_PER_CLASS:
                raise ValueError(f"need >= {MIN_PER_CLASS} labels of each class "
                                 f"(have {npos} confirmed, {nneg} false positive)")
            art = L.fit_logistic(Xtr, ytr, wtr, feats)
            model_type = "logistic_l2"
        else:
            art = L.fit_ridge_log10(Xtr, ytr, wtr, feats, groups=gtr)
            model_type = "ridge_log10"
        step("candidate fitted", model_type=model_type)

        prod = store.production_model(task)
        cand_scores = art.predict(Xva)
        prod_scores = _score(prod, Xva, task, feats)
        if prod_scores is None:
            if fam == "triage":
                prod_scores = L.rules_score(Xva, feats)
                step("no production model: comparing against the rule baseline")
            else:
                prod_scores = np.full(len(yva), np.nanmedian(ytr))
                step("no production model: comparing against the training median")
        tests = L.model_tests(art, Xva)
        gate = L.evaluate_gate("triage" if fam == "triage" else "quantify",
                               cand_scores, prod_scores, yva, gva, sva,
                               frozen, current, tests,
                               L.GateConfig(primary_metric="auprc" if fam == "triage"
                                            else "rmse_log10"))
        step("gate evaluated", passed=gate["passed"])

        prev_versions = [m["version"] for m in store.list_models(task)]
        base = max(prev_versions, key=lambda v: tuple(int(x) for x in v.split("."))) \
            if prev_versions else None
        version = L.next_version(base)
        mid = f"{task.replace(':', '-')}-{version}"
        metrics = []
        if fam == "triage":
            mc = gate["summary"]["candidate"]
            for k in ("auroc", "auprc", "f1", "precision", "recall", "brier", "ece"):
                metrics.append({"split": "validation", "metric": k, "value": mc[k],
                                "n": mc["n"]})
        else:
            rc = gate["summary"]["candidate"]
            for space in ("log10", "linear"):
                for k in ("rmse", "mae", "r2", "bias"):
                    metrics.append({"split": "validation", "metric": f"{k}_{space}",
                                    "value": rc[space][k], "n": rc["n"]})
        model = store.add_model({
            "id": mid, "task": task, "version": version, "model_type": model_type,
            "training_dataset_version": L.dataset_hash(train),
            "validation_dataset_hash": current, "feature_set": feats,
            "params": art.extra, "artifact": art.to_dict(), "status": "CANDIDATE",
            "parent_model": prod["id"] if prod else None,
            "notes": f"Trained by job {jid} on {len(train)} labels "
                     f"({', '.join(sorted({l['source'] for l in train}))}).",
            "gate": gate}, metrics, actor="trainer")
        step("candidate registered", model_id=mid)
        store.update_job(jid, status="SUCCEEDED", finished_at=inc_mod.now_utc(),
                         dataset_version=L.dataset_hash(train), n_train=len(train),
                         n_validation=len(val), candidate_model_id=mid, log=log)
    except Exception as e:                                   # the job records why
        step("failed", error=str(e))
        store.update_job(jid, status="FAILED", finished_at=inc_mod.now_utc(),
                         error=str(e), log=log)
    return store.get_job(jid)


def compare(store, model_id: str) -> dict:
    """Old production vs candidate, for the Learning screen."""
    cand = store.get_model(model_id)
    if not cand:
        raise KeyError(model_id)
    prod = store.production_model(cand["task"])
    return {"candidate": cand, "production": prod, "gate": cand.get("gate")}


def promote(store, model_id: str, approved_by: str, note: str = "") -> dict:
    m = store.get_model(model_id)
    if not m:
        raise KeyError(model_id)
    if (approved_by or "").strip().lower() in SYSTEM_ACTORS:
        raise PermissionError("promotion requires a named human approver")
    if m["status"] not in ("CANDIDATE", "STAGING"):
        raise ValueError(f"only CANDIDATE/STAGING models can be promoted (is {m['status']})")
    gate = m.get("gate") or {}
    if not gate.get("passed"):
        failed = [c["name"] for c in gate.get("checks", []) if not c.get("passed")]
        raise PermissionError(f"gate not passed: {failed or 'no gate report'}")
    gate = dict(gate)
    gate["human_approval"] = {"required": True, "approved_by": approved_by.strip(),
                              "at": inc_mod.now_utc(), "note": note}
    return store.set_model_status(model_id, "PRODUCTION", approved_by.strip(), gate, note)


def reject(store, model_id: str, actor: str, note: str = "") -> dict:
    m = store.get_model(model_id)
    if not m:
        raise KeyError(model_id)
    if m["status"] == "PRODUCTION":
        raise ValueError("cannot reject the production model; roll back instead")
    return store.set_model_status(model_id, "REJECTED", actor, note=note)


def rollback(store, model_id: str, actor: str, note: str = "") -> dict:
    """Restore a previously retired model of the same task to production."""
    m = store.get_model(model_id)
    if not m:
        raise KeyError(model_id)
    if (actor or "").strip().lower() in SYSTEM_ACTORS:
        raise PermissionError("rollback requires a named human")
    if m["status"] not in ("RETIRED", "STAGING"):
        raise ValueError(f"can only roll back to a RETIRED model (is {m['status']})")
    gate = dict(m.get("gate") or {})
    gate["rollback"] = {"by": actor, "at": inc_mod.now_utc(), "note": note}
    gate["passed"] = gate.get("passed", True)
    return store.set_model_status(model_id, "PRODUCTION", actor, gate, f"rollback: {note}")
