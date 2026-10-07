"""A real autocrlf checkout must preserve the retained source fixture bytes."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "tests/fixtures/forum-public-edf05833.jsonl"
DIGEST = "85c196628b64b21dab5f3ecffb466201bc57784dc4c6485c1a86cf45542b87f8"


@pytest.mark.parametrize("preserve_bytes", [False, True])
def test_real_autocrlf_checkout_has_a_byte_preserving_policy(
    tmp_path: Path, preserve_bytes: bool
) -> None:
    source = subprocess.run(
        ["git", "show", f"HEAD:{FIXTURE}"], cwd=ROOT, check=True,
        capture_output=True, timeout=15,
    ).stdout
    assert hashlib.sha256(source).hexdigest() == DIGEST
    repo = tmp_path / "repo"
    repo.mkdir()
    export = tmp_path / "checkout"
    export.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "core.autocrlf=true", "-c", "core.safecrlf=false",
             "-c", f"core.attributesFile={os.devnull}", *args],
            cwd=repo, check=True, capture_output=True, timeout=15,
        )

    git("init", "-q")
    if preserve_bytes:
        (repo / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    fixture = repo / FIXTURE
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(source)
    git("add", "--all")
    git("checkout-index", "--all", "--prefix=" + export.as_posix() + "/")
    actual = (export / FIXTURE).read_bytes()
    assert (actual == source) is preserve_bytes
    assert (hashlib.sha256(actual).hexdigest() == DIGEST) is preserve_bytes
