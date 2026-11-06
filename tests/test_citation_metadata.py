"""CITATION.cff must describe the package that pyproject.toml builds."""
from __future__ import annotations

from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def _top_level_scalar(text: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}:[ \t]*"?([^"\n]*?)"?[ \t]*$', text, re.MULTILINE)
    assert match is not None, f"CITATION.cff has no top-level {key!r} scalar"
    return match.group(1)


def test_citation_names_the_packaged_version_license_and_source() -> None:
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert _top_level_scalar(citation, "cff-version") == "1.2.0"
    assert _top_level_scalar(citation, "version") == project["version"]
    assert _top_level_scalar(citation, "license") == project["license"]
    assert _top_level_scalar(citation, "repository-code") == project["urls"]["Source"]
