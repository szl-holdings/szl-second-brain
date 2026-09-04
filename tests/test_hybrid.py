from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from second_brain.hybrid import (
    AuthorizedHydrator,
    HybridSecondBrain,
    RetrievalBoundaryError,
)
from second_brain.retrieve import SecondBrainIndex, canonical_sha256


def _write_corpus(path: Path) -> dict[str, str]:
    texts = {
        "n1": "locked eight formula authority and Lean proof",
        "n2": "second brain evidence retrieval and hydration",
        "n3": "A11oy action admission and signed receipt",
        "n4": "living anatomy observer and inference graph",
    }
    sources = {"n1": "lean", "n2": "brain", "n3": "a11oy", "n4": "anatomy"}
    rows = []
    for node_id, text in texts.items():
        rows.append(
            {
                "id": node_id,
                "source": sources[node_id],
                "title": text.title(),
                "text": text,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return texts


@pytest.fixture()
def corpus(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    path = tmp_path / "brain.jsonl"
    return path, _write_corpus(path)


def test_bm25_only_mode_is_honest_and_handles_only(corpus):
    path, _texts = corpus
    brain = SecondBrainIndex(path)
    result = HybridSecondBrain(brain).context("formula authority", k=2)
    assert result["ready"] is True
    assert result["content_access"] == "HANDLES_ONLY"
    assert result["ranking_receipt"]["mode"] == "BM25_ONLY"
    assert result["ranking_receipt"]["dense"] == "NOT_CONFIGURED"
    assert result["raw_graph_nodes_admitted_to_gradients"] == 0
    assert all(
        set(handle) == {"nodeId", "nodeKind", "label", "note"}
        for handle in result["handles"]
    )
    assert all("content" not in item for item in result["evidence"])
    assert result["evidence_set_sha256"] == canonical_sha256(result["evidence"])


def test_sparse_dense_rrf_and_reranker_are_bound_to_known_nodes(corpus):
    path, _texts = corpus
    brain = SecondBrainIndex(path)

    def dense(query: str, k: int):
        assert query and k >= 2
        return [
            {"node_id": "n4", "score": 0.99},
            {"node_id": "n1", "score": 0.80},
        ]

    def rerank(query: str, candidates, k: int):
        assert query
        assert all("content" not in item for item in candidates)
        return ["n1", "n4"]

    result = HybridSecondBrain(
        brain,
        dense_provider=dense,
        reranker=rerank,
        per_source_limit=3,
    ).context("formula authority anatomy", k=2)
    assert result["ranking_receipt"]["mode"] == "HYBRID_SPARSE_DENSE+RERANKER"
    assert result["ranking_receipt"]["dense"] == "OK"
    assert result["ranking_receipt"]["reranker"] == "OK"
    assert [item["nodeId"] for item in result["handles"]] == ["n1", "n4"]


def test_unknown_dense_node_fails_closed_when_fallback_disabled(corpus):
    path, _texts = corpus
    brain = SecondBrainIndex(path)

    def poisoned_dense(query: str, k: int):
        return [{"node_id": "private:9464", "score": 1.0}]

    with pytest.raises(RetrievalBoundaryError, match="dense provider unavailable"):
        HybridSecondBrain(
            brain,
            dense_provider=poisoned_dense,
            allow_sparse_fallback=False,
        ).context("formula", k=2)


def test_dense_failure_falls_back_with_explicit_label(corpus):
    path, _texts = corpus
    brain = SecondBrainIndex(path)

    def failed_dense(query: str, k: int):
        raise RuntimeError("provider offline")

    result = HybridSecondBrain(
        brain,
        dense_provider=failed_dense,
        allow_sparse_fallback=True,
    ).context("formula", k=2)
    assert result["ready"] is True
    assert result["ranking_receipt"]["mode"] == "BM25_FALLBACK_DENSE_UNAVAILABLE"
    assert result["ranking_receipt"]["dense"] == "UNAVAILABLE"
    assert result["ranking_receipt"]["dense_error_type"] == "RuntimeError"


def test_reranker_cannot_introduce_nodes(corpus):
    path, _texts = corpus
    brain = SecondBrainIndex(path)

    def rerank(query: str, candidates, k: int):
        return ["private:node"]

    result = HybridSecondBrain(brain, reranker=rerank).context("formula", k=2)
    assert result["ranking_receipt"]["reranker"] == "UNAVAILABLE"
    assert (
        result["ranking_receipt"]["reranker_error_type"]
        == "RetrievalBoundaryError"
    )
    assert result["ready"] is True


def test_empty_query_abstains_without_providers(corpus):
    path, _texts = corpus
    brain = SecondBrainIndex(path)
    result = HybridSecondBrain(brain).context("", k=2)
    assert result["state"] == "ABSTAIN_NO_QUERY"
    assert result["ready"] is False
    assert result["handles"] == []


def test_authorized_hydration_verifies_scope_and_content_digest(corpus):
    path, texts = corpus
    calls = []

    def authorize(principal, tenant, policy, node_id, source):
        calls.append((principal, tenant, policy, node_id, source))
        return tenant == "tenant-1"

    hydrator = AuthorizedHydrator(authorize, path=path)
    digest = hashlib.sha256(texts["n1"].encode("utf-8")).hexdigest()
    result = hydrator.hydrate(
        [{"nodeId": "n1", "source": "lean", "sha256": digest}],
        principal_id="principal-1",
        tenant_id="tenant-1",
        policy_revision="a" * 40,
    )
    assert result["state"] == "AUTHORIZED_CONTENT_READY"
    assert result["content_access"] == "CONTROLLER_ONLY"
    assert result["documents"][0]["content"] == texts["n1"]
    assert result["documents"][0]["sha256"] == digest
    assert len(calls) == 1
    assert result["raw_graph_nodes_admitted_to_gradients"] == 0


def test_hydration_denial_is_batch_fail_closed(corpus):
    path, texts = corpus

    def authorize(principal, tenant, policy, node_id, source):
        return node_id != "n2"

    hydrator = AuthorizedHydrator(authorize, path=path)
    handles = []
    for node_id, source in (("n1", "lean"), ("n2", "brain")):
        handles.append(
            {
                "nodeId": node_id,
                "source": source,
                "sha256": hashlib.sha256(texts[node_id].encode("utf-8")).hexdigest(),
            }
        )
    with pytest.raises(RetrievalBoundaryError, match="access denied"):
        hydrator.hydrate(
            handles,
            principal_id="principal-1",
            tenant_id="tenant-1",
            policy_revision="sha256:" + "b" * 64,
        )


def test_hydration_rejects_tampered_handle_digest(corpus):
    path, _texts = corpus
    hydrator = AuthorizedHydrator(lambda *args: True, path=path)
    with pytest.raises(RetrievalBoundaryError, match="digest mismatch"):
        hydrator.hydrate(
            [{"nodeId": "n1", "source": "lean", "sha256": "0" * 64}],
            principal_id="principal-1",
            tenant_id="tenant-1",
            policy_revision="c" * 40,
        )


def test_hydrator_refuses_corrupt_corpus(tmp_path: Path):
    path = tmp_path / "corrupt.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "n1",
                "source": "lean",
                "title": "bad",
                "text": "actual",
                "sha256": "0" * 64,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RetrievalBoundaryError, match="integrity failure"):
        AuthorizedHydrator(lambda *args: True, path=path)
