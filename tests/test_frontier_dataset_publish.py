"""Publication projection must preserve review status and omit candidate text."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "publish_frontier_dataset", ROOT / "scripts" / "publish_frontier_dataset.py"
)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


def source() -> dict[str, bytes]:
    # Windows checkouts may use CRLF; the publisher reads immutable Git blobs.
    return {path: publisher.committed_bytes("HEAD", path) for path in publisher.SOURCE_PATHS}


def render(data: dict[str, bytes]) -> dict[str, bytes]:
    template = (ROOT / publisher.CARD_TEMPLATE).read_bytes()
    with patch.object(publisher, "committed_bytes", return_value=template):
        return publisher.projection("a" * 40, data)


def test_publication_is_handle_only_and_binds_exact_source_bytes() -> None:
    data = source()
    output = render(data)
    assert set(output) == {
        "frontier-handles.public.jsonl", "frontier-state.v1.json",
        "README.md", "publication.json",
    }
    handles = [json.loads(line) for line in output["frontier-handles.public.jsonl"].splitlines()]
    assert len(handles) == 137
    assert all(row["candidate_state"] == "DISCOVERED_REVIEW_REQUIRED" for row in handles)
    assert all(row["contentAccess"] == "HANDLES_ONLY" for row in handles)
    assert all("content" not in row and "provenance" not in row for row in handles)
    assert output["frontier-state.v1.json"] == data["data/frontier-state.v1.json"]
    manifest = json.loads(output["publication.json"])
    assert manifest["source_revision"] == "a" * 40
    assert manifest["content_projection"] == "HANDLES_ONLY"
    assert manifest["source_files"]["data/frontier-candidates.public.jsonl"]["sha256"] == publisher.sha256(
        data["data/frontier-candidates.public.jsonl"]
    )
    assert all(manifest[key] == "NONE" for key in (
        "training_authority", "promotion_authority", "execution_authority"
    ))


def test_candidate_tamper_fails_before_provider_write() -> None:
    data = source()
    path = "data/frontier-candidates.public.jsonl"
    data[path] = data[path].replace(b"Governed Kernel Suite", b"Ungoverned Kernel Suite", 1)
    with pytest.raises((ValueError, publisher.PublicationError)):
        render(data)


def test_authority_drift_fails_before_provider_write() -> None:
    data = source()
    path = "data/frontier-state.v1.json"
    data[path] = data[path].replace(b'"training_authority": "NONE"', b'"training_authority": "YES"')
    with pytest.raises((ValueError, publisher.PublicationError)):
        render(data)
