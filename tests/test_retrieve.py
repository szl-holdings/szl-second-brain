"""SOFTWARE retrieve tests. Handles only. Never LIVE. Never 9464-in-gradients."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import app
from second_brain.retrieve import SecondBrainIndex, navigator_context, rag_status, retrieve


def test_public_corpus_is_575() -> None:
    idx = SecondBrainIndex()
    assert idx.built is True
    assert idx.n == 575
    st = idx.stats()
    assert st["raw_graph_nodes_admitted_to_gradients"] == 0
    assert st["index_is_model_weights"] is False
    assert st["by_source"]["formula"] == 269


def test_search_returns_handles_without_text() -> None:
    hit = retrieve("Lambda uniqueness conjecture", k=5)
    assert hit["kind"] == "SOFTWARE"
    assert hit["content_access"] == "HANDLES_ONLY"
    assert hit["ready"] is True
    assert hit["handles"]
    for h in hit["handles"]:
        assert "text" not in h
        assert "_toks" not in h
        assert h["nodeId"]
        assert h["nodeKind"] == "INDEX"
        assert h["label"] == "DECLARED"


def test_empty_query_abstains() -> None:
    hit = retrieve("", k=4)
    assert hit["ready"] is False
    assert hit["handles"] == []


def test_unknown_tokens_abstain() -> None:
    hit = retrieve("zzqxymplughq", k=4)
    assert hit["ready"] is False
    assert hit["handles"] == []


def test_navigator_handles_only() -> None:
    ctx = navigator_context("Khipu receipt", k=4)
    assert ctx["content_access"] == "HANDLES_ONLY"
    assert ctx["kind"] == "SOFTWARE"
    assert ctx["ready"] is True
    for h in ctx["handles"]:
        assert set(h) <= {"nodeId", "nodeKind", "label", "note"}
        assert "text" not in h


def test_rag_status_never_admits_private_graph() -> None:
    st = rag_status()
    assert st["built"] is True
    assert st["chunk_count"] == 575
    assert st["training_authority_rows"] == 0
    assert st["raw_graph_nodes_admitted_to_gradients"] == 0
    assert st["brain_handle_plane"]["private_graph_nodes"] == 0


def test_get_retrieve_api() -> None:
    c = TestClient(app)
    res = c.get("/api/v1/retrieve", params={"q": "Lambda uniqueness conjecture", "k": 4})
    assert res.status_code == 200
    body = res.json()
    assert body["schema"] == "szl.second-brain.retrieve/v1"
    assert body["kind"] == "SOFTWARE"
    assert body["ready"] is True
    for h in body["handles"]:
        assert "text" not in h
    health = c.get("/health")
    assert health.status_code == 200
    assert health.json()["chunk_count"] == 575
    idx = c.get("/api/v1/index")
    assert idx.json()["chunk_count"] == 575
