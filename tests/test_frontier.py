from __future__ import annotations

import hashlib
import json
import re

import pytest
from fastapi.testclient import TestClient

from app_operational import app
from scripts.refresh_frontier_memory import (
    RefreshError,
    SOURCES,
    candidate_id,
    forum_pilot_candidates,
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
    assert len(SOURCES) == 8
    assert state["source_count"] == len(SOURCES) + 2
    assert state["source_kind_counts"]["research-metadata"] == 6
    assert state["source_kind_counts"]["forum-insight"] == 2
    forum = next(source for source in state["sources"] if source["source_id"] == "science_forum_pilot")
    assert forum["candidate_count"] == 2
    spec = next(source for source in SOURCES if source.source_id == "science_forum_pilot")
    assert forum["repository"] == spec.repository
    assert forum["path"] == spec.path
    assert forum["parser"] == spec.parser
    assert re.fullmatch(r"[0-9a-f]{40}", forum["revision"])
    assert re.fullmatch(r"[0-9a-f]{64}", forum["content_sha256"])
    # Scheduled discovery resolves a new exact path revision before running
    # this suite. Bind the loaded rows to that receipt, not a historical SHA.
    # The immutable producer bytes are tested in test_forum_public_projection.
    from second_brain._data import data_file

    forum_rows = [
        row for line in data_file("frontier-candidates.public.jsonl").read_bytes().splitlines()
        if (row := json.loads(line))["source_kind"] == "forum-insight"
    ]
    assert len(forum_rows) == forum["candidate_count"] == 2
    assert {row["source_repository"] for row in forum_rows} == {spec.repository}
    assert {row["source_path"] for row in forum_rows} == {spec.path}
    assert {row["source_revision"] for row in forum_rows} == {forum["revision"]}
    assert len(state["candidate_set_sha256"]) == 64
    assert state["public_content_access"] == "HANDLES_ONLY"
    assert state["controller_content_access"] == "AUTHORIZED_CONTROLLER_ONLY"
    assert state["training_authority"] == "NONE"
    assert state["promotion_authority"] == "NONE"
    assert state["execution_authority"] == "NONE"
    assert state["private_graph_present"] is False
    assert state["raw_graph_nodes_admitted_to_gradients"] == 0
    assert state["lambda"] == "CONJECTURE_1"
    assert all(len(source["revision"]) == (64 if source.get("revision_kind") == "metadata-capture-sha256" else 40) for source in state["sources"])


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
        assert len(handle["revision"]) == (64 if handle.get("revisionKind") == "metadata-capture-sha256" else 40)


def test_forum_pilot_is_a_review_required_cited_handle() -> None:
    result = frontier_search("provenance-aware GitHub skill imports", k=24)
    forum = [handle for handle in result["handles"] if handle["kind"] == "forum-insight"]
    assert len(forum) == 2
    assert any("easier skill sharing" in handle["title"] for handle in forum)
    assert any("Three testable science skills" in handle["title"] for handle in forum)
    for handle in forum:
        assert handle["repository"] == "szl-holdings/szl-science-forum-corpus"
        assert handle["path"] == "dataset/sources.public.jsonl"
        assert handle["candidate_state"] == "DISCOVERED_REVIEW_REQUIRED"
        assert handle["contentAccess"] == "HANDLES_ONLY"
        assert '"content"' not in json.dumps(handle)


def forum_rows() -> list[dict]:
    row = {
        "source_id": "ai4science:426:1",
        "source_url": "https://ai4science.discourse.group/t/three-testable-science-skills-and-provenance-aware-github-imports/426",
        "topic_id": 426, "post_number": 1,
        "title": "Three testable science skills and provenance-aware GitHub imports",
        "summary": "Operator-authored research-workflow summary.",
        "need_ids": ["artifact_replay", "blocked_allocation", "measurement_harmonization", "skill_import_provenance"],
        "review_state": "operator_labeled",
        "observed_at": "2026-10-02", "posted_at": None,
        "publication_rights": "operator_authorized", "rights_evidence": "Operator-authored summary",
    }
    sharing = {
        **row,
        "source_id": "ai4science:396:1", "topic_id": 396,
        "source_url": "https://ai4science.discourse.group/t/feature-request-easier-skill-sharing-in-claude-science-from-a-real-attempt/396/1",
        "title": "Feature request: easier skill sharing in Claude Science (from a real attempt)",
        "need_ids": ["skill_import_provenance", "skill_import_slice", "skill_name_collision",
                     "skill_service_disclosure", "skill_share_action", "skill_update_notice"],
    }
    return [sharing, row]


def encode_forum(rows: list[dict]) -> bytes:
    return "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")


def test_forum_pilot_parser_accepts_two_reviewed_topics_in_either_order() -> None:
    spec = next(source for source in SOURCES if source.source_id == "science_forum_pilot")
    rows = forum_rows()
    candidates = forum_pilot_candidates(spec, "a" * 40, encode_forum(rows))
    assert len(candidates) == 2
    assert candidates == forum_pilot_candidates(spec, "a" * 40, encode_forum(rows[::-1]))
    assert len({row["id"] for row in candidates}) == 2


@pytest.mark.parametrize("field,value,match", [
    ("publication_rights", "unknown", "rights or source binding"),
    ("review_state", "unreviewed", "rights or source binding"),
    ("source_id", "ai4science:999:1", "rights or source binding"),
    ("source_url", "https://example.com", "rights or source binding"),
    ("topic_id", True, "rights or source binding"),
    ("body", "unapproved text", "metadata fields"),
    ("raw", "unapproved text", "metadata fields"),
    ("cooked", "unapproved text", "metadata fields"),
    ("attribution", "private reviewer", "metadata fields"),
    ("summary", "x" * 1001, "annotation is invalid"),
])
def test_forum_pilot_parser_rejects_drift_in_either_topic(field, value, match) -> None:
    spec = next(source for source in SOURCES if source.source_id == "science_forum_pilot")
    for position in (0, 1):
        rows = forum_rows()
        rows[position][field] = value
        with pytest.raises(RefreshError, match=match):
            forum_pilot_candidates(spec, "a" * 40, encode_forum(rows))


def test_forum_pilot_parser_rejects_duplicates_and_source_count_drift() -> None:
    spec = next(source for source in SOURCES if source.source_id == "science_forum_pilot")
    rows = forum_rows()
    for invalid in (rows[:1], rows + [rows[0]], [rows[0], rows[0]]):
        with pytest.raises(RefreshError):
            forum_pilot_candidates(spec, "a" * 40, encode_forum(invalid))
    duplicate_key = encode_forum(rows).replace(b'{', b'{"topic_id":396,', 1)
    with pytest.raises(RefreshError, match="duplicate forum metadata key"):
        forum_pilot_candidates(spec, "a" * 40, duplicate_key)


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
    from second_brain._data import data_file

    lines = data_file("frontier-candidates.public.jsonl").read_bytes()
    rows = [json.loads(line) for line in lines.splitlines() if line.strip()]
    canonical = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
        for row in rows
    )
    assert hashlib.sha256(canonical).hexdigest() == state["candidate_set_sha256"]
