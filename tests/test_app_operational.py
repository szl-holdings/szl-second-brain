from __future__ import annotations

from fastapi.testclient import TestClient

from app_operational import app


client = TestClient(app)


def test_retrieval_capabilities_are_honest():
    response = client.get("/api/v1/retrieval-capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "1.1.0"
    assert body["public_content_access"] == "HANDLES_ONLY"
    assert body["controller_hydration"] == "AUTHORIZED_LIBRARY_ONLY"
    assert body["public_runtime_mode"] == "BM25_ONLY"
    assert body["dense_provider"] == "NOT_CONFIGURED"
    assert body["private_graph_present"] is False
    assert body["lambda"] == "CONJECTURE_1"


def test_hybrid_get_returns_handles_and_ranking_receipt_only():
    response = client.get("/api/v1/hybrid", params={"q": "governed receipts", "k": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "szl.second-brain.hybrid-context/v1"
    assert body["content_access"] == "HANDLES_ONLY"
    assert body["ranking_receipt"]["mode"] == "BM25_ONLY"
    assert all("content" not in handle for handle in body["handles"])
    assert all("content" not in evidence for evidence in body["evidence"])


def test_hybrid_post_rejects_invalid_k():
    response = client.post(
        "/api/v1/hybrid", json={"query": "formula authority", "k": "many"}
    )
    assert response.status_code == 400
    assert response.json()["state"] == "UNAVAILABLE"


def test_hybrid_empty_query_abstains():
    response = client.post("/api/v1/hybrid", json={"query": "", "k": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "ABSTAIN_NO_QUERY"
    assert body["ready"] is False
    assert body["handles"] == []
