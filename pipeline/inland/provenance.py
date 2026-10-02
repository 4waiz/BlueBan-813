"""Provenance tracking.

Carried over from DesalGuard-main's `pipeline/provenance.py` unmodified: this
module is sensor- and AOI-agnostic (SourceRecord/AlgorithmRecord/Provenance are
generic dataclasses), so there was nothing inland-specific to adapt. Keeping it
byte-for-byte identical is deliberate — it is what makes folding this project
into DesalGuard-main later a copy-and-namespace operation rather than a rewrite.

Every derived layer, metric and event in this project should carry a record of
where its inputs came from and how it was produced, the same standard
DesalGuard-main holds itself to. Nothing should reach a UI or a report without
one.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any

SCHEMA_VERSION = "1.0"


def _git_revision() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "uncommitted"


def file_sha256(path: str, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


@dataclass
class SourceRecord:
    """One input dataset used to produce a result."""
    satellite: str
    sensor: str
    scene_id: str
    acquisition_utc: str
    product: str
    processing_level: str
    provider: str
    licence: str
    native_resolution_m: float | list | None = None
    bands_used: list = field(default_factory=list)
    wavelengths_nm: list = field(default_factory=list)
    units: str = ""
    quality_mask: str = ""
    access_url: str = ""
    local_path: str = ""
    sha256: str = ""
    notes: str = ""


@dataclass
class AlgorithmRecord:
    """How a result was computed."""
    name: str
    description: str
    reference: str = ""
    parameters: dict = field(default_factory=dict)
    inputs: list = field(default_factory=list)
    units_out: str = ""
    assumptions: list = field(default_factory=list)
    limitations: list = field(default_factory=list)


@dataclass
class Provenance:
    """Complete traceability record for one derived product."""
    result_id: str
    result_kind: str
    sources: list = field(default_factory=list)
    algorithm: AlgorithmRecord | None = None
    code_version: str = field(default_factory=_git_revision)
    schema_version: str = SCHEMA_VERSION
    processed_utc: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    environment: dict = field(
        default_factory=lambda: {
            "python": platform.python_version(),
            "platform": platform.system(),
        }
    )
    extra: dict = field(default_factory=dict)

    def add_source(self, src: SourceRecord) -> "Provenance":
        self.sources.append(src)
        return self

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.algorithm is not None:
            d["algorithm"] = asdict(self.algorithm)
        return d

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1)
        return path

    def completeness(self) -> tuple[float, list[str]]:
        """Fraction of required provenance fields present, plus what is missing.

        Used by tests and by any future UI to show an honest completeness
        badge rather than implying a record is richer than it is.
        """
        missing: list[str] = []
        required_src = [
            "satellite", "sensor", "scene_id", "acquisition_utc", "product",
            "processing_level", "provider", "licence", "units",
        ]
        total = 0
        have = 0
        if not self.sources:
            missing.append("sources (none recorded)")
        for i, s in enumerate(self.sources):
            sd = s if isinstance(s, dict) else asdict(s)
            for k in required_src:
                total += 1
                if sd.get(k):
                    have += 1
                else:
                    missing.append(f"sources[{i}].{k}")
        for k in ("name", "description"):
            total += 1
            a = self.algorithm
            ad = a if isinstance(a, dict) else (asdict(a) if a else {})
            if ad.get(k):
                have += 1
            else:
                missing.append(f"algorithm.{k}")
        return (have / total if total else 0.0), missing
