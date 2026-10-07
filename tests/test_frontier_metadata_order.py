# SPDX-License-Identifier: Apache-2.0
"""Valid research permutations must generate loadable receipts without weakening rights."""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
from itertools import permutations

import pytest

from scripts import refresh_frontier_memory as refresh
from second_brain.frontier import FrontierIndex
from second_brain.public_research import (
    PublicMetadataClient,
    ResearchBoundaryError,
    canonical_bytes,
    digest,
    merge_captures,
)


@pytest.fixture
def research_snapshot(monkeypatch):
    # No Git fetch or external provider request is needed for aggregate receipts.
    monkeypatch.setattr(refresh, "SOURCES", ())
    observed = datetime.now(timezone.utc).isoformat()
    records = []
    for identifier, title in (
        ("10.1000/alpha", "Synthetic first capture"),
        ("10.1000/alpha", "Synthetic changed capture"),
        ("10.1000/beta", "Synthetic second identifier"),
    ):
        payload = canonical_bytes({
            "status": "ok", "message-type": "work",
            "message": {"DOI": identifier, "title": [title]},
        })
        client = PublicMetadataClient(transport=lambda _url, raw=payload: raw)
        records.append(client.capture("crossref", identifier, observed_at=observed))
    payload = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <id>http://arxiv.org/abs/2401.00001v1</id><title>Synthetic arXiv capture</title>
        <published>2024-01-01T00:00:00Z</published><updated>2024-01-01T00:00:00Z</updated>
        <author><name>Synthetic Author</name></author><category term="cs.AI"/>
        </entry></feed>'''
    client = PublicMetadataClient(transport=lambda _url: payload)
    records.append(client.capture("arxiv", "2401.00001v1", observed_at=observed))
    return merge_captures(None, records)


def _build(snapshot):
    def no_git_fetch(_spec):
        pytest.fail("metadata-only refresh attempted a Git fetch")

    return refresh.build_snapshot(no_git_fetch, research_snapshot=snapshot)


@pytest.mark.parametrize("order", list(permutations(range(4))))
def test_research_permutations_generate_identical_loadable_snapshots(research_snapshot, order):
    expected_rows, expected_state = _build(research_snapshot)
    value = copy.deepcopy(research_snapshot)
    value["records"] = [value["records"][index] for index in order]
    original = canonical_bytes(value)

    rows, state = _build(value)

    FrontierIndex._validate(state, rows)
    assert canonical_bytes(rows) == canonical_bytes(expected_rows)
    assert canonical_bytes(state) == canonical_bytes(expected_state)
    assert canonical_bytes(value) == original
    assert {row["provenance"]["capture_sha256"]: row["provenance"]["metadata"] for row in rows} == {
        record["capture_sha256"]: record["metadata"] for record in value["records"]
    }
    assert {row["provenance"]["metadata"]["full_text_licence"] for row in rows} == {"NOT_INFERRED"}
    assert {row["provenance"]["metadata"]["metadata_licence"] for row in rows} == {
        "CC0-1.0", "NOT_DECLARED_BY_RESPONSE",
    }
    assert state["candidate_count"] == 4 and state["source_count"] == 2
    assert all(state[key] == "NONE" for key in (
        "training_authority", "promotion_authority", "execution_authority", "merge_authority",
    ))
    assert state["raw_graph_nodes_admitted_to_gradients"] == 0


@pytest.mark.parametrize("record_index", range(4))
def test_aggregate_generation_rejects_duplicate_captures(research_snapshot, record_index):
    research_snapshot["records"].append(copy.deepcopy(research_snapshot["records"][record_index]))

    with pytest.raises(ResearchBoundaryError, match="digest mismatch or duplicate"):
        _build(research_snapshot)


@pytest.mark.parametrize("provider,field,replacement,message", [
    ("arxiv", "metadata_licence", "CC-BY-4.0", "arXiv metadata licence changed"),
    ("crossref", "metadata_licence", "CC0-1.0", "Crossref metadata licence or revision inferred"),
    ("arxiv", "full_text_licence", "CC0-1.0", "unsupported metadata projection"),
    ("crossref", "full_text_licence", "CC-BY-4.0", "unsupported metadata projection"),
])
def test_aggregate_generation_rejects_forged_rights_with_matching_digest(
    research_snapshot, provider, field, replacement, message,
):
    record = next(record for record in research_snapshot["records"] if record["provider"] == provider)
    record["metadata"][field] = replacement
    captured = canonical_bytes(record["metadata"])
    record["capture_sha256"] = digest(captured)
    record["capture_base64"] = base64.b64encode(captured).decode("ascii")

    with pytest.raises(ResearchBoundaryError, match=message):
        _build(research_snapshot)
