from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app_operational import app
from scripts.refresh_frontier_memory import (
    RefreshError,
    SOURCES,
    candidate_id,
    reject_secrets,
)
from second_brain.frontier import (
    AuthorizedFrontierHydrator,
    FrontierBoundaryError,
    anatomy_feed,
    frontier_index,
    frontier_search,
    frontier_status,
)


client = TestClient(app)


def test_frontier_state_is_exact_and_review_required() -> None:
    state = frontier_status()
    assert state["ready"] is True
    assert state["state"] == "REVIEW_REQUIRED"
    assert state["candidate_count"] >= 70
    assert state["source_count"] == len(SOURCES) == 6
    assert len(state["candidate_set_sha256"]) == 64
    assert state["public_content_access"] == "HANDLES_ONLY"
    assert state["controller_content_access"] == "AUTHORIZED_CONTROLLER_ONLY"
    assert state["training_authority"] == "NONE"
    assert state["promotion_authority"] == "NONE"
    assert state["execution_authority"] == "NONE"
    assert state["private_graph_present"] is False
    assert state["raw_graph_nodes_admitted_to_gradients"] == 0
    assert state["lambda"] == "CONJECTURE_1"
    assert all(len(source["revision"]) == 40 for source in state["sources"])


def test_public_frontier_search_is_handles_only() -> None:
    result = frontier_search("formula quant anatomy ouroboros", k=20)
    assert result["ready"] is True
    assert result["state"] == "REVIEW_REQUIRED"
    assert result["content_access"] == "HANDLES_ONLY"
    assert result["handles"]
    assert result["training_authority"] == "NONE"
    assert result["promotion_authority"] == "NONE"
    assert result["execution_authority"] == "NONE"
    serialized = json.dumps(result, sort_keys=True).lower()
    assert '"content"' not in serialized
    assert '"text"' not in serialized
    for handle in result["handles"]:
        assert handle["candidate_state"] == "DISCOVERED_REVIEW_REQUIRED"
        assert handle["contentAccess"] == "HANDLES_ONLY"
        assert len(handle["sha256"]) == 64
        assert len(handle["revision"]) == 40


def test_anatomy_feed_is_read_only_and_contains_formula_or_quant_handles() -> None:
    result = anatomy_feed(k=24)
    assert result["schema"] == "szl.second-brain.anatomy-feed/v1"
    assert result["purpose"] == "READ_ONLY_LIVING_ANATOMY_OBSERVATION"
    assert result["content_access"] == "HANDLES_ONLY"
    assert result["execution_authority"] == "NONE"
    assert any(
        handle["kind"] in {"attributed-formula", "executable-formula", "quant-domain"}
        for handle in result["handles"]
    )


def test_controller_hydration_requires_identity_policy_and_positive_authorization() -> None:
    handles = frontier_search("Lambda quant domain", k=3)["handles"]
    denied = AuthorizedFrontierHydrator(lambda *_args: False)
    with pytest.raises(FrontierBoundaryError):
        denied.hydrate(
            handles,
            principal_id="review-controller",
            tenant_id="szl",
            policy_revision="policy-v1",
        )

    allowed = AuthorizedFrontierHydrator(
        lambda principal, tenant, policy, _node, _source: (
            principal == "review-controller"
            and tenant == "szl"
            and policy == "policy-v1"
        )
    )
    hydrated = allowed.hydrate(
        handles,
        principal_id="review-controller",
        tenant_id="szl",
        policy_revision="policy-v1",
    )
    assert hydrated["state"] == "AUTHORIZED_REVIEW_CONTENT_READY"
    assert hydrated["content_access"] == "CONTROLLER_ONLY"
    assert hydrated["documents"]
    assert all(document["content"] for document in hydrated["documents"])
    assert all(document["authority"] == "NONE" for document in hydrated["documents"])
    assert hydrated["training_authority"] == "NONE"
    assert hydrated["promotion_authority"] == "NONE"
    assert hydrated["execution_authority"] == "NONE"
    assert hydrated["raw_graph_nodes_admitted_to_gradients"] == 0


def test_api_never_returns_candidate_content() -> None:
    status = client.get("/api/v1/frontier-status")
    assert status.status_code == 200
    assert status.json()["state"] == "REVIEW_REQUIRED"

    handles = client.get(
        "/api/v1/frontier-handles",
        params={"q": "living anatomy formulas", "k": 12},
    )
    assert handles.status_code == 200
    assert handles.json()["handles"]

    feed = client.get("/api/v1/anatomy-feed", params={"k": 24})
    assert feed.status_code == 200
    assert feed.json()["purpose"] == "READ_ONLY_LIVING_ANATOMY_OBSERVATION"

    for response in (status, handles, feed):
        serialized = response.text.lower()
        assert '"content"' not in serialized
        assert '"text"' not in serialized
        assert "private_graph" not in serialized or '"private_graph_present":false' in serialized


def test_empty_frontier_query_fails_closed() -> None:
    response = client.get("/api/v1/frontier-handles", params={"q": "", "k": 3})
    assert response.status_code == 422
    body = response.json()
    assert body["state"] == "BLOCKED"
    assert body["handles"] == []
    assert body["content_access"] == "HANDLES_ONLY"


def test_candidate_ids_are_stable_and_source_owned() -> None:
    spec = SOURCES[0]
    first = candidate_id(spec, "attributed-formula", "F1-euler-khipu-chi")
    second = candidate_id(spec, "attributed-formula", "F1-euler-khipu-chi")
    assert first == second
    assert first.startswith("frontier:")
    assert len(first) == len("frontier:") + 32
    changed = candidate_id(spec, "attributed-formula", "F12-kuramoto-additive")
    assert changed != first


def test_secret_like_material_is_rejected_without_echoing_it() -> None:
    secret = "sk-" + "A" * 32
    with pytest.raises(RefreshError, match="secret-like material rejected") as error:
        reject_secrets(f"credential={secret}", source_id="fixture")
    assert secret not in str(error.value)


def test_candidate_set_digest_matches_committed_canonical_lines() -> None:
    index = frontier_index()
    state = index.status()
    from importlib.resources import files

    lines = files("data").joinpath("frontier-candidates.public.jsonl").read_bytes()
    rows = [json.loads(line) for line in lines.splitlines() if line.strip()]
    canonical = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
        for row in rows
    )
    assert hashlib.sha256(canonical).hexdigest() == state["candidate_set_sha256"]
