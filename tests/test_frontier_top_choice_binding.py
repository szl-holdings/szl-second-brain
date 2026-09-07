from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "frontier" / "neomme-funes-2026-09-07.json"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_second_brain_frontier_binding_is_non_mutating_and_fail_closed() -> None:
    contract = _contract()
    assert contract["schema"] == "szl.frontier.second-brain-binding.v1"
    assert contract["default_effect"] == "HOLD"
    assert contract["canonical_frontier_revision"] == "94a039d086d1343d1fcfe5bca617f601006ca05b"
    assert contract["corpus_mutation_authority"] is False
    assert contract["training_authority"] is False
    assert contract["execution_authority"] is False
    assert contract["production_promotion"] is False
    assert "full deterministic refresh" in contract["content_addressed_corpus_policy"]


def test_neomme_requires_retrieval_and_provenance_proof() -> None:
    candidates = {row["id"]: row for row in _contract()["candidates"]}
    neomme = candidates["neomme-2026-09-03"]
    assert neomme["license"] == "Apache-2.0"
    assert neomme["status"] == "QUALIFY_RETRIEVAL_SHADOW"
    assert "exact upstream Hugging Face revision" in neomme["model_identity_policy"]
    metrics = set(neomme["required_metrics"])
    assert {"nDCG@10", "Recall@100", "page_and_span_provenance_exact_match"}.issubset(metrics)
    invariants = " ".join(neomme["required_invariants"]).lower()
    assert "identical checksum-pinned qrels" in invariants
    assert "disposable derived state" in invariants
    assert "never gains execution authority" in invariants
    assert neomme["promotion_effect"] == "NONE"


def test_funes_pattern_preserves_raw_evidence_and_deletion_semantics() -> None:
    candidates = {row["id"]: row for row in _contract()["candidates"]}
    funes = candidates["funes-agent-memory-2026-09-03"]
    assert funes["status"] == "ADOPT_PATTERN_IN_SHADOW"
    assert "do not relabel Funes as SZL-originated software" in funes["adoption_policy"]
    metrics = set(funes["required_metrics"])
    assert {
        "provenance_exact_match",
        "secret_exposure_rate",
        "cross_tenant_leakage_rate",
        "deleted_memory_return_rate",
    }.issubset(metrics)
    invariants = " ".join(funes["required_invariants"]).lower()
    assert "system-of-record evidence" in invariants
    assert "secret scanning" in invariants
    assert "tombstones and deletions" in invariants
    assert "cannot authorize tools" in invariants
    assert funes["promotion_effect"] == "NONE"
