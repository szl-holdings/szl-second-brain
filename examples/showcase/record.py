"""Explicitly regenerate the two local review artifacts; never publishes them."""
from __future__ import annotations

import json
from pathlib import Path

from .__main__ import render
from .engine import HERE, Showcase, digest
from .evaluate import evaluate

SOURCE_BASE = "a477d550276f63fdcdafca6efa05e655fcca0ba9"


def snapshot() -> dict:
    # Normalize Python source newlines so the binding survives platform checkout
    # conventions. Fixture bindings always hash raw bytes, not normalized text.
    sources = {p.name: digest(p.read_text(encoding="utf-8").encode())
               for p in sorted(HERE.glob("*.py"))}
    reused = {"second_brain/" + name: digest(
        (HERE.parents[1] / "second_brain" / name).read_text(encoding="utf-8").encode())
        for name in ("corpus.py", "retrieve.py", "hybrid.py")}
    return {"evidence_kind": "MEASURED_SYNTHETIC_SOFTWARE", "source_base": SOURCE_BASE,
            "lf_normalized_source_sha256": sources, "reused_source_sha256": reused,
            "report": evaluate(Showcase.bundled())}


def write_artifacts(destination: Path = HERE) -> dict:
    result = snapshot()
    # The default writes only the named example artifacts. A caller-selected
    # destination is a trusted local test seam, not a CLI file-input mechanism.
    (destination / "baseline.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (destination / "index.html").write_text(render(result["report"]) + "\n",
                                            encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    result = write_artifacts()
    print(json.dumps(result["report"]["splits"], indent=2))
