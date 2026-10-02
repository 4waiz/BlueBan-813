"""Inland complement (Shawka Dam): precomputed results, served read-only.

The site is static: two fixed EnMAP L2A dates plus a 28-observation
Sentinel-2/Landsat baseline, computed separately and integrated as an add-on.
Nothing here runs the inland pipeline.

    GET /api/inland/summary          public summary (outputs/inland/summary.json)
    GET /api/inland/files            the precomputed public files under data/inland/
    GET /api/inland/files/{path}     one public JSON / GeoJSON / CSV file
    GET /api/inland/docs             the inland documents
    GET /api/inland/docs/{path}      one inland document (markdown)

data/inland/restricted/ (per-pixel EnMAP reflectance layers and spectra) is
never served: EnMAP's licence is "proprietary" and its redistribution terms are
not yet confirmed for public submission.
"""
from __future__ import annotations

import hashlib
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data", "inland")
RESTRICTED = os.path.join(DATA, "restricted")
DOCS = os.path.join(ROOT, "docs", "inland")
SUMMARY = os.path.join(ROOT, "outputs", "inland", "summary.json")
SERVABLE = {".json": "application/json", ".geojson": "application/geo+json", ".csv": "text/csv"}

router = APIRouter(prefix="/api/inland", tags=["inland"])


def _inside(base: str, rel: str) -> str:
    p = os.path.realpath(os.path.join(base, rel))
    if not p.startswith(os.path.realpath(base) + os.sep):
        raise HTTPException(404, "Not found")
    return p


@router.get("/summary")
def summary():
    if not os.path.exists(SUMMARY):
        raise HTTPException(404, "outputs/inland/summary.json missing: run scripts/inland/build_inland_bundle.py")
    with open(SUMMARY, encoding="utf-8") as f:
        return json.load(f)


@router.get("/files")
def files():
    out = []
    for dp, dns, fns in os.walk(DATA):
        dns[:] = [d for d in dns if os.path.join(dp, d) != RESTRICTED]
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            with open(p, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            out.append({"path": os.path.relpath(p, DATA).replace(os.sep, "/"), "bytes": os.path.getsize(p),
                        "sha256": digest, "servable": os.path.splitext(fn)[1] in SERVABLE})
    return {"root": "data/inland", "files": sorted(out, key=lambda r: r["path"]),
            "withheld": "data/inland/restricted/ (not served; EnMAP licence terms unconfirmed)"}


@router.get("/files/{path:path}")
def file(path: str):
    p = _inside(DATA, path)
    if p.startswith(os.path.realpath(RESTRICTED) + os.sep) or not os.path.isfile(p):
        raise HTTPException(404, "Not found")
    ext = os.path.splitext(p)[1]
    if ext not in SERVABLE:
        raise HTTPException(415, f"{ext} files are summarised in /api/inland/summary, not served raw")
    return FileResponse(p, media_type=SERVABLE[ext])


@router.get("/docs")
def docs():
    out = []
    for dp, _, fns in os.walk(DOCS):
        for fn in sorted(fns):
            if fn.endswith(".md"):
                p = os.path.join(dp, fn)
                out.append({"path": os.path.relpath(p, DOCS).replace(os.sep, "/"), "bytes": os.path.getsize(p)})
    return {"docs": out}


@router.get("/docs/{path:path}", response_class=PlainTextResponse)
def doc(path: str):
    p = _inside(DOCS, path)
    if not (p.endswith(".md") and os.path.isfile(p)):
        raise HTTPException(404, "Not found")
    with open(p, encoding="utf-8") as f:
        return f.read()
