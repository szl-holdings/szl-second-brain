"""Regression against the corpus producer's reviewed, attribution-free output."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.refresh_frontier_memory import RefreshError, SOURCES, forum_pilot_candidates


FIXTURES = Path(__file__).parent / "fixtures"
PUBLIC_REVISION = "edf05833d34b9cb84383bb8cf7b86b0f9b48f1dc"
PUBLIC_SHA256 = "85c196628b64b21dab5f3ecffb466201bc57784dc4c6485c1a86cf45542b87f8"


def public_fixture() -> bytes:
    payload = (FIXTURES / "forum-public-edf05833.jsonl").read_bytes()
    source = json.loads((FIXTURES / "forum-public-edf05833.source.json").read_text())
    assert source["source_repository"] == "szl-holdings/szl-science-forum-corpus"
    assert source["source_path"] == "dataset/sources.public.jsonl"
    assert source["source_revision"] == PUBLIC_REVISION
    assert hashlib.sha256(payload).hexdigest() == source["sha256"] == PUBLIC_SHA256
    return payload


def test_current_public_projection_produces_two_review_required_candidates() -> None:
    spec = next(item for item in SOURCES if item.source_id == "science_forum_pilot")
    rows = forum_pilot_candidates(spec, PUBLIC_REVISION, public_fixture())
    assert len(rows) == 2
    for row in rows:
        assert row["source_repository"] == spec.repository
        assert row["source_path"] == spec.path
        assert row["source_revision"] == PUBLIC_REVISION
        assert row["candidate_state"] == "DISCOVERED_REVIEW_REQUIRED"
        assert row["admission"] == "DISCOVERED_REVIEW_REQUIRED"
        assert row["content_access"] == "CONTROLLER_ONLY"
        assert row["source_kind"] == "forum-insight"
        assert "attribution" not in row


def test_private_attribution_is_rejected_instead_of_reintroduced() -> None:
    spec = next(item for item in SOURCES if item.source_id == "science_forum_pilot")
    rows = [json.loads(line) for line in public_fixture().splitlines()]
    for row in rows:
        row["attribution"] = "betterwithage"
    payload = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
    with pytest.raises(RefreshError, match="metadata fields"):
        forum_pilot_candidates(spec, PUBLIC_REVISION, payload)
