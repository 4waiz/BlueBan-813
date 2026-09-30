"""Seed the self-hosted API database from the same seed as the hosted workspace.

The hosted demo initialises each visitor's in-browser workspace from
outputs/workspace/seed.json. This loads that file into the FastAPI store
(SQLite by default; DATABASE_URL for another database) so both modes start
from identical incidents, AOIs, assets, models and labels.

Usage: python scripts/seed_db.py [--reset]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.api.store import Store, _db_path  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete the SQLite file first")
    a = ap.parse_args()
    seed_p = os.path.join(ROOT, "outputs", "workspace", "seed.json")
    if not os.path.exists(seed_p):
        raise SystemExit("outputs/workspace/seed.json missing: run scripts/build_workspace_seed.py")
    seed = json.load(open(seed_p, encoding="utf-8"))
    if a.reset:
        path = _db_path(os.environ.get("DATABASE_URL"))
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
    st = Store()
    st.init_schema()
    for aoi in seed.get("aois", []):
        st.upsert_aoi(aoi, actor="seed")
    for inc in seed.get("incidents", []):
        st.upsert_incident(inc, actor="seed")
    for asset in seed.get("assets", []):
        st.add_asset({**asset, "source": asset.get("source") or "seed"}, actor="seed")
    have = {m["id"] for m in st.list_models()}
    for m in seed.get("models", []):
        if m["id"] not in have:
            st.add_model(m, metrics=m.get("metrics"), actor="seed")
    existing = {(l.get("source_ref") or l["id"]) for l in st.labels("triage", active_only=False)}
    n = 0
    for lab in seed.get("labels", []):
        ref = lab.get("source_ref") or lab["id"]
        if ref in existing:
            continue
        st.add_label(lab["task"], lab["target"], lab["features"], lab["source"], actor="seed",
                     incident_id=lab.get("incident_id"), aoi_id=lab.get("aoi_id"), source_ref=ref,
                     group_key=lab.get("group_key"), split=lab.get("split", "train"))
        n += 1
    print(f"seeded: {len(seed.get('aois', []))} AOIs, {len(seed.get('incidents', []))} incidents, "
          f"{len(seed.get('assets', []))} assets, {len(seed.get('models', []))} models, {n} new labels "
          f"-> {_db_path(os.environ.get('DATABASE_URL'))}")


if __name__ == "__main__":
    main()
