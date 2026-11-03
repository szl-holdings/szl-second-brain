"""Regression against the corpus producer's reviewed, attribution-free output."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.refresh_frontier_memory import RefreshError, SOURCES, forum_pilot_candidates


FIXTURES = Path(__file__).parent / "fixtures"
PUBLIC_REVISION = "e56e65e426bbd11246e9d0b344d3ac9ee5d7ffb2"
PUBLIC_SHA256 = "57a6f8daff59b92a1d22f1724e11e936955d3269446a494dfd2e00a9a6a324ce"


def public_fixture() -> bytes:
    payload = (FIXTURES / "forum-public-e56e65e4.jsonl").read_bytes()
    source = json.loads((FIXTURES / "forum-public-e56e65e4.source.json").read_text())
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
        assert "source_content_license" not in row


def test_private_attribution_is_rejected_instead_of_reintroduced() -> None:
    spec = next(item for item in SOURCES if item.source_id == "science_forum_pilot")
    rows = [json.loads(line) for line in public_fixture().splitlines()]
    for row in rows:
        row["attribution"] = "betterwithage"
    payload = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
    with pytest.raises(RefreshError, match="metadata fields"):
        forum_pilot_candidates(spec, PUBLIC_REVISION, payload)


def test_record_v2_source_content_license_is_required_and_null() -> None:
    # record-v2 makes source_content_license a required public field that is
    # null for operator-authorized rows; only operator-authorized rows are
    # admitted here, so a missing or non-null licence is contract drift.
    spec = next(item for item in SOURCES if item.source_id == "science_forum_pilot")
    published = [json.loads(line) for line in public_fixture().splitlines()]
    assert [row["source_content_license"] for row in published] == [None, None]

    def encode(rows: list[dict]) -> bytes:
        return b"".join(json.dumps(row).encode() + b"\n" for row in rows)

    for position in (0, 1):
        rows = [dict(row) for row in published]
        del rows[position]["source_content_license"]
        with pytest.raises(RefreshError, match="metadata fields"):
            forum_pilot_candidates(spec, PUBLIC_REVISION, encode(rows))
        for licence in ("CC-BY-4.0", "Apache-2.0", "", False):
            rows = [dict(row) for row in published]
            rows[position]["source_content_license"] = licence
            with pytest.raises(RefreshError, match="rights or source binding"):
                forum_pilot_candidates(spec, PUBLIC_REVISION, encode(rows))
        rows = [dict(row) for row in published]
        rows[position].update(publication_rights="licensed", source_content_license="CC-BY-4.0")
        with pytest.raises(RefreshError, match="rights or source binding"):
            forum_pilot_candidates(spec, PUBLIC_REVISION, encode(rows))
