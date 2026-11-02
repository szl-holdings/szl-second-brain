"""Persisted frontier state must not bypass the public handles-only boundary."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app_operational import app
from second_brain import frontier
from second_brain._data import data_dir


SENTINEL = "SYNTHETIC_PRIVATE_CONTENT_MUST_NOT_BE_PUBLIC"


def _digest(state):
    body = {key: value for key, value in state.items() if key != "state_sha256"}
    state["state_sha256"] = hashlib.sha256(json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    package = data_dir()
    state = json.loads((package / "frontier-state.v1.json").read_text())
    (tmp_path / "frontier-candidates.public.jsonl").write_bytes(
        (package / "frontier-candidates.public.jsonl").read_bytes()
    )
    monkeypatch.setattr(frontier, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(frontier, "_INDEX", frontier.FrontierIndex())
    return state, tmp_path / "frontier-state.v1.json"


def test_valid_frontier_snapshot_remains_ready(snapshot):
    state, path = snapshot
    path.write_text(json.dumps(state))
    client = TestClient(app)
    response = client.get("/api/v1/frontier-status")
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["state_sha256"] == state["state_sha256"]
    capabilities = client.get("/api/v1/retrieval-capabilities").json()
    assert capabilities["frontier_memory"]["ready"] is True


@pytest.mark.parametrize("case", [
    "wrong_digest", "missing_digest", "extra_state_content", "extra_source_content",
    "source_id_content", "known_wrong_parser", "metadata_source_path",
    "merge_authority", "controller_access", "private_graph", "gradient_authority",
    "unbound_counts", "nested_learning_definition", "changed_learning_definition",
    "nested_parser", "unknown_parser",
])
def test_invalid_state_is_withheld_by_public_routes(snapshot, case):
    state, path = snapshot
    if case == "wrong_digest":
        state["state_sha256"] = "0" * 64
    elif case == "missing_digest":
        state.pop("state_sha256")
    elif case == "extra_state_content":
        state["raw_reasoning"] = SENTINEL
    elif case == "extra_source_content":
        state["sources"][0]["content"] = SENTINEL
    elif case == "source_id_content":
        state["sources"][0]["source_id"] = SENTINEL
    elif case == "known_wrong_parser":
        source = next(
            row
            for row in state["sources"]
            if row["source_id"] == "a11oy_public_estate"
        )
        source["parser"] = "python_contract"
    elif case == "metadata_source_path":
        source = next(
            row
            for row in state["sources"]
            if row.get("revision_kind") == "metadata-capture-sha256"
        )
        source["path"] = SENTINEL
    elif case == "merge_authority":
        state["merge_authority"] = "AUTO_MERGE"
    elif case == "controller_access":
        state["controller_content_access"] = "PUBLIC"
    elif case == "private_graph":
        state["private_graph_nodes_loaded"] = 1
    elif case == "gradient_authority":
        state["raw_graph_nodes_admitted_to_gradients"] = 1
    elif case == "unbound_counts":
        state["source_kind_counts"][SENTINEL] = 1
    elif case == "nested_learning_definition":
        state["learning_definition"] = {"content": SENTINEL}
    elif case == "changed_learning_definition":
        state["learning_definition"] = SENTINEL
    elif case == "nested_parser":
        state["sources"][0]["parser"] = {"content": SENTINEL}
    elif case == "unknown_parser":
        state["sources"][0]["parser"] = SENTINEL
    if case not in {"wrong_digest", "missing_digest"}:
        # A self-consistent digest is not permission to expose arbitrary data.
        _digest(state)
    path.write_text(json.dumps(state))

    client = TestClient(app)
    response = client.get("/api/v1/frontier-status")
    body = response.json()
    assert body["ready"] is False
    assert body["state"] == "UNAVAILABLE"
    assert SENTINEL not in response.text
    assert "AUTO_MERGE" not in response.text
    capabilities = client.get("/api/v1/retrieval-capabilities").json()
    assert capabilities["frontier_memory"]["ready"] is False
    search = client.get("/api/v1/frontier-handles?q=formula")
    assert search.json()["ready"] is False
    assert search.json()["handles"] == []
    feed = client.get("/api/v1/anatomy-feed").json()
    assert feed["ready"] is False
    assert feed["handles"] == []
    assert SENTINEL not in json.dumps(feed)


@pytest.mark.parametrize("count,expected_ready", [(1, True), (True, False)])
def test_single_candidate_source_count_is_an_integer_not_a_boolean(snapshot, count, expected_ready):
    state, path = snapshot
    candidates_path = path.parent / "frontier-candidates.public.jsonl"
    rows = [json.loads(line) for line in candidates_path.read_text().splitlines() if line.strip()]
    source = state["sources"][0]
    row = next(row for row in rows if row["source_repository"] == source["repository"]
               and row["source_path"] == source["path"])
    candidate_bytes = (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    candidates_path.write_bytes(candidate_bytes)
    state["candidate_count"] = 1
    state["source_count"] = 1
    source["candidate_count"] = count
    state["sources"] = [source]
    state["source_kind_counts"] = {row["source_kind"]: 1}
    state["quant_domain_counts"] = {row["quant_domain"]: 1} if row.get("quant_domain") else {}
    state["candidate_set_sha256"] = hashlib.sha256(candidate_bytes).hexdigest()
    _digest(state)
    path.write_text(json.dumps(state))

    client = TestClient(app)
    body = client.get("/api/v1/frontier-status").json()
    assert body["ready"] is expected_ready
    capabilities = client.get("/api/v1/retrieval-capabilities").json()
    assert capabilities["frontier_memory"]["ready"] is expected_ready
