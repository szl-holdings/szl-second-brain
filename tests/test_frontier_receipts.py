"""Source receipts must describe exactly the candidates exposed by the frontier."""

from __future__ import annotations

import json

import pytest

from second_brain._data import data_file
from second_brain.frontier import FrontierIndex


@pytest.fixture
def snapshot():
    state = json.loads(data_file("frontier-state.v1.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in data_file("frontier-candidates.public.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    FrontierIndex._validate(state, rows)
    return state, rows


def _receipt(state, kind):
    return next(
        source for source in state["sources"]
        if source.get("revision_kind", "git-sha1") == kind
    )


def test_committed_git_and_metadata_receipts_are_admitted(snapshot):
    state, _rows = snapshot
    assert len(_receipt(state, "git-sha1")["revision"]) == 40
    assert len(_receipt(state, "metadata-capture-sha256")["revision"]) == 64


@pytest.mark.parametrize("field,replacement", [
    ("revision", "0" * 40),
    ("repository", "szl-holdings/unlisted-source"),
    ("path", "unlisted/path.json"),
])
def test_git_receipt_cannot_claim_different_source(snapshot, field, replacement):
    state, rows = snapshot
    _receipt(state, "git-sha1")[field] = replacement

    with pytest.raises(ValueError, match="source receipt binding mismatch"):
        FrontierIndex._validate(state, rows)


@pytest.mark.parametrize("kind", ["git-sha1", "metadata-capture-sha256"])
def test_receipt_count_must_match_candidates(snapshot, kind):
    state, rows = snapshot
    _receipt(state, kind)["candidate_count"] += 1

    with pytest.raises(ValueError, match="source receipt binding mismatch"):
        FrontierIndex._validate(state, rows)


@pytest.mark.parametrize("kind", ["git-sha1", "metadata-capture-sha256"])
def test_candidates_cannot_be_left_without_a_receipt(snapshot, kind):
    state, rows = snapshot
    state["sources"].remove(_receipt(state, kind))
    state["source_count"] -= 1

    with pytest.raises(ValueError, match="candidates lack source receipts"):
        FrontierIndex._validate(state, rows)


@pytest.mark.parametrize("kind", ["git-sha1", "metadata-capture-sha256"])
def test_second_receipt_cannot_claim_the_same_candidates(snapshot, kind):
    state, rows = snapshot
    duplicate = dict(_receipt(state, kind))
    duplicate["source_id"] = "another_source_id"
    state["sources"].append(duplicate)
    state["source_count"] += 1

    with pytest.raises(ValueError, match="source receipt is not unique"):
        FrontierIndex._validate(state, rows)
