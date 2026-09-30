"""Rebuild everything downstream of WATCH, in order, only where needed.

    python scripts/rebuild_downstream.py [--skip-detect] [--skip-labels]

1. DETECT for every AOI whose WATCH output is newer than its DETECT output.
2. OLCI cross-sensor labels for every AOI with a DETECT output (cached extracts
   make re-runs cheap).
3. Workspace seed, validation summary (+ generated report section), static
   bundle, research paper and the AOI tournament.

Deployment and commits stay manual on purpose: someone looks at the result first.
"""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*args):
    t0 = time.time()
    print("$", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
    print(f"  ({time.time() - t0:.0f}s)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-detect", action="store_true")
    ap.add_argument("--skip-labels", action="store_true")
    a = ap.parse_args()
    watch = {os.path.basename(p)[:-5]: os.path.getmtime(p)
             for p in glob.glob(os.path.join(ROOT, "outputs", "watch", "*.json"))}
    if not a.skip_detect:
        stale = [aoi for aoi, t in sorted(watch.items())
                 if not os.path.exists(os.path.join(ROOT, "outputs", "detect", f"{aoi}.json"))
                 or os.path.getmtime(os.path.join(ROOT, "outputs", "detect", f"{aoi}.json")) < t]
        if stale:
            run("scripts/build_detect.py", *sum((["--aoi", s] for s in stale), []))
    detected = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, "outputs", "detect", "*.json")))
    if not a.skip_labels and detected:
        run("scripts/build_labels.py", *sum((["--aoi", s] for s in detected), []), "--workers", "3")
    for script in ("build_workspace_seed.py", "build_validation.py", "build_static_site.py",
                   "build_paper.py", "build_tournament.py"):
        run(f"scripts/{script}")
    print("downstream rebuilt: review, then deploy (scripts/deploy_cloudflare.sh) and commit")


if __name__ == "__main__":
    main()
