"""Public UI/API contracts, exact evidence binding and failure behavior."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from second_brain import workbench
from second_brain.retrieve import canonical_sha256
from second_brain.web import app

client = TestClient(app)


@pytest.mark.parametrize("module", ["app", "app_operational", "app_refinement", "second_brain.web"])
def test_each_fresh_entrypoint_has_complete_routes(module):
    code = (
        f"from {module} import app; "
        "paths = app.openapi()['paths']; "
        "assert {'/', '/hologram', '/api/v1/query', '/api/v1/hybrid', "
        "'/api/v1/frontier-handles', '/api/v1/refinement-memory', '/readyz'} <= set(paths); "
        "from fastapi.testclient import TestClient; "
        "assert TestClient(app).get('/api/v1/query?q=formula').status_code == 200"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=20)


@pytest.mark.parametrize("route", ["retrieve", "plan", "hybrid", "query"])
@pytest.mark.parametrize("body", [[], None, "string", 5, {"query": []},
    {"query": 42}, {"query": "x" * 2001}, {"query": "a", "q": "b"},
    {"query": "a", "k": True}, {"query": "a", "k": 1.5},
    {"query": "a", "k": "2"}, {"query": "a", "k": None},
    {"query": "a", "k": 0}, {"query": "a", "k": 13}, {"unknown": "value"}])
def test_malformed_body_never_reaches_retrieval(route, body):
    response = client.post("/api/v1/" + route, content=json.dumps(body),
                           headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert response.json()["state"] == "UNAVAILABLE"


def test_plan_cannot_accept_fabricated_or_mutated_grounding():
    query = "Lambda uniqueness conjecture"
    handles = client.get("/retrieve", params={"q": query}).json()["handles"]
    assert handles
    valid = client.post("/api/v1/plan", json={"query": query, "handles": handles[:1]})
    assert valid.status_code == 200
    forged = copy.deepcopy(handles[:1])
    forged[0]["note"] = "invented grounding"
    for offered in ([{"nodeId": "made-up", "note": query}], forged, [handles[0], handles[0]]):
        assert client.post("/api/v1/plan", json={"query": query, "handles": offered}).status_code == 422


def test_query_api_uses_one_retrieval_and_binds_complete_receipt():
    with patch.object(workbench, "hybrid_context", wraps=workbench.hybrid_context) as retrieve:
        response = client.post("/api/v1/query", json={"q": "formula authority", "k": 4})
    assert response.status_code == 200
    retrieve.assert_called_once_with("formula authority", k=4)
    body = response.json()
    assert body["frontier"]["state"] == "REVIEW_REQUIRED"
    hit, plan, receipt = body["retrieve"], body["plan"], body["receipt"]
    assert set(plan["citedNodeIds"]) <= {h["nodeId"] for h in hit["handles"]}
    assert plan["retrieval_generation_sha256"] == hit["generation_sha256"]
    assert plan["retrieval_evidence_set_sha256"] == hit["evidence_set_sha256"]
    assert receipt["plan_sha256"] == canonical_sha256(plan)
    assert receipt["handles_sha256"] == canonical_sha256(hit["handles"])
    assert receipt["frontier_handles_sha256"] == canonical_sha256(body["frontier"]["handles"])
    checksum = receipt.pop("sha256")
    assert checksum == canonical_sha256(receipt)
    assert receipt["signature"] == "UNSIGNED_CONTENT_DIGEST"
    assert '"text":' not in response.text and '"content":' not in response.text


def test_python_console_uses_real_backend_and_escapes_untrusted_input():
    query = 'formula <script>alert("bad")</script>'
    response = client.get("/", params={"q": query, "k": 3})
    assert response.status_code == 200
    assert '<script>' not in response.text
    assert '&lt;script&gt;' in response.text
    assert 'name="q"' in response.text and 'method="get"' in response.text
    assert 'Research &amp; formula review' in response.text
    bundle = client.get("/api/v1/query", params={"q": query, "k": 3}).json()
    assert bundle["receipt"]["sha256"] in response.text
    assert bundle["retrieve"]["handles"][0]["nodeId"] in response.text
    assert 'UNSIGNED_CONTENT_DIGEST' in response.text
    assert response.headers["cache-control"] == "no-store"


def test_readiness_returns_503_when_any_public_service_is_unavailable():
    assert client.get("/readyz").json()["ready"] is True
    with patch.object(workbench, "frontier_status", return_value={"ready": False}):
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["components"]["corpus"]["ready"] is True
        assert response.json()["components"]["frontier"]["ready"] is False
    with patch.object(workbench, "_state_path", return_value=Path("/missing/refinement.json")):
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["components"]["refinement"]["ready"] is False


def test_frontier_failure_remains_visible_without_relabeling_corpus():
    with patch.object(workbench, "frontier_search", return_value={
        "ready": False, "state": "UNAVAILABLE", "handles": [], "scores": []
    }):
        response = client.get("/api/v1/query?q=formula")
    body = response.json()
    assert body["state"] == "PARTIAL_FRONTIER_UNAVAILABLE"
    assert body["ready"] is False
    assert body["retrieve"]["ready"] is True
    assert body["frontier"]["ready"] is False


def test_empty_query_abstains_and_does_not_search_frontier():
    with patch.object(workbench, "frontier_search") as frontier:
        body = client.get("/api/v1/query").json()
    frontier.assert_not_called()
    assert body["state"] == "ABSTAIN_NO_QUERY"
    assert body["plan"]["decision"] == "ABSTAIN"
    assert body["frontier"]["state"] == "NOT_RUN"
