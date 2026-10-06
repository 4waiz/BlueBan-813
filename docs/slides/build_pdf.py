"""Render docs/slides/index.html to docs/slides.pdf (one 1280x720 page per slide).

Uses a local Chrome or Edge in headless mode; fonts load from Google Fonts, so
run it online. Usage: python docs/slides/build_pdf.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "index.html"
OUT = HERE.parent / "slides.pdf"

CANDIDATES = [
    shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chrome"), shutil.which("msedge"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def main() -> int:
    browser = next((c for c in CANDIDATES if c and os.path.exists(c)), None)
    if not browser:
        print("No Chrome/Edge found; open docs/slides/index.html and print to PDF (1280x720, no margins).")
        return 1
    with tempfile.TemporaryDirectory() as profile:
        cmd = [browser, "--headless=new", f"--user-data-dir={profile}", "--no-first-run", "--hide-scrollbars",
               "--no-pdf-header-footer", "--print-to-pdf-no-header", "--virtual-time-budget=20000",
               f"--print-to-pdf={OUT}", SRC.as_uri()]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    print(f"wrote {OUT.relative_to(HERE.parent.parent)} ({OUT.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
