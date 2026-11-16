"""Byte-bound reference and API tests; not Lean-kernel replay tests."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from second_brain.frontier import anatomy_feed, frontier_status
from second_brain.web import app

lr = importlib.import_module("second_brain.lutar_reference")
ROOT = Path(__file__).resolve().parents[1]


def test_exact_canonical_source_and_eight_handles():
    raw = (ROOT / "data" / lr.SOURCE_FILE).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == lr.SOURCE_SHA256
    value = lr.lutar_reference()
    assert value["ready"] is True
    assert value["declared_locked_count"] == 8
    assert value["declared_carrier_count"] == 24
    assert [h["claimId"] for h in value["handles"]] == list(lr.LOCKED_IDS)
    assert len({n for h in value["handles"] for n in h["declarationNames"]}) == 24
    assert value["proof_replayed_here"] is False
    assert value["source_head_freshness"] == "NOT_CHECKED_PINNED_SNAPSHOT"


def test_public_payload_is_handles_only_and_has_no_authority():
    value = lr.lutar_reference()
    for key in ("training_authority", "promotion_authority", "execution_authority", "merge_authority"):
        assert value[key] == "NONE"
    assert value["raw_graph_nodes_admitted_to_gradients"] == 0
    assert value["runtime_refinement"] == "UNVERIFIED"
    assert value["independent_checker"] == "NOT_RUN"
    text = json.dumps(value)
    for forbidden in ('"content"', '"text"', '"source_declared_answer"', '"hypotheses"'):
        assert forbidden not in text
    assert "F23" not in [h["claimId"] for h in value["handles"]]


@pytest.mark.parametrize("raw", [b"{}", b"not-json", b"x" * (lr.MAX_SOURCE_BYTES + 1),
                                b'{"locked_ids":[],"locked_ids":["F23"]}'])
def test_modified_or_oversized_source_is_unavailable(tmp_path, raw):
    source = tmp_path / "source.json"
    source.write_bytes(raw)
    value = lr.lutar_reference(path=source)
    assert value["ready"] is False
    assert value["handles"] == []
    assert value["state"] == "UNAVAILABLE"
    with pytest.raises(lr.LutarReferenceError):
        lr.curriculum_candidates(path=source)


def test_missing_source_does_not_reuse_a_cached_pass(tmp_path):
    source = tmp_path / "source.json"
    source.write_bytes((ROOT / "data" / lr.SOURCE_FILE).read_bytes())
    assert lr.lutar_reference(path=source)["ready"] is True
    source.unlink()
    assert lr.lutar_reference(path=source)["ready"] is False


def test_route_success_and_missing_source_failure(monkeypatch, tmp_path):
    client = TestClient(app)
    response = client.get("/api/v1/lutar-invariants")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    monkeypatch.setattr(lr, "data_file", lambda _: tmp_path / "missing")
    response = client.get("/api/v1/lutar-invariants")
    assert response.status_code == 503
    assert response.json()["handles"] == []


def test_anatomy_feed_adds_reference_without_changing_frontier():
    before = frontier_status()
    result = anatomy_feed(k=24)
    after = frontier_status()
    assert before == after
    assert result["lutar_invariants"]["declared_locked_count"] == 8
    assert result["lutar_invariants"]["execution_authority"] == "NONE"
    assert result["candidate_count"] == before["candidate_count"]


def test_context_candidates_preserve_exact_hypotheses_and_limits():
    source = json.loads((ROOT / "data" / lr.SOURCE_FILE).read_bytes())
    claims = {row["claim_id"]: row for row in source["claims"]}
    value = lr.curriculum_candidates()
    assert value["count"] == len(value["rows"]) == 16
    assert value["training_authority"] == "NONE"
    assert value["proof_completions"] == 0
    for row in value["rows"]:
        assert row["review_state"] == "REVIEW_REQUIRED"
        assert row["role"] == "STATEMENT_AND_LIMIT_CONTEXT_NOT_PROOF_COMPLETION"
        for key, answer in row["source_declared_answer"].items():
            assert answer == claims[row["claim_id"]][key]
    assert value == lr.curriculum_candidates()


def test_context_export_requires_new_explicit_output(tmp_path):
    output = tmp_path / "candidates.json"
    args = [sys.executable, "-B", str(ROOT / "train/build_lutar_context_candidates.py"),
            "--output", str(output)]
    first = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=20)
    assert first.returncode == 0, first.stderr
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    second = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=20)
    assert second.returncode != 0
    assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
    assert json.loads(output.read_bytes())["training_authority"] == "NONE"
