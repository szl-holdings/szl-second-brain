"""One public retrieval transaction shared by the Python UI and JSON API."""
from __future__ import annotations

from typing import Any
from pathlib import Path

from second_brain._data import data_file
from second_brain.frontier import FrontierBoundaryError, frontier_search, frontier_status
from second_brain.hybrid import hybrid_context
from second_brain.plan import plan_from_handles
from second_brain.retrieve import canonical_sha256, rag_status
from second_brain.refinement_memory import load_public_state


def _state_path() -> Path:
    return data_file("refinement-patterns.public.json")


def readiness() -> dict[str, Any]:
    """Readiness covers the public services, not model/provider qualification."""
    corpus = rag_status()
    frontier = frontier_status()
    try:
        memory = load_public_state(_state_path())
        refinement = {"ready": True, "state": memory["state"],
                      "pattern_count": memory["pattern_count"]}
    except (OSError, ValueError, RuntimeError) as exc:
        refinement = {"ready": False, "state": "UNAVAILABLE", "reason": type(exc).__name__}
    components = {
        "corpus": {"ready": bool(corpus.get("built")),
                   "chunk_count": corpus.get("chunk_count", 0)},
        "frontier": {"ready": bool(frontier.get("ready")),
                     "state": frontier.get("state", "UNAVAILABLE"),
                     "candidate_count": frontier.get("candidate_count", 0)},
        "refinement": refinement,
    }
    ready = all(item["ready"] for item in components.values())
    return {"schema": "szl.second-brain.readiness/v1", "ready": ready,
            "state": "READY" if ready else "UNAVAILABLE", "components": components,
            "scope": "PUBLIC_RETRIEVAL_AND_REVIEW", "runtime_mode": "BM25_ONLY",
            "model_generation": "NOT_CONFIGURED", "execution_authority": "NONE"}


def query_bundle(query: str, k: int = 6) -> dict[str, Any]:
    retrieval = hybrid_context(query, k=k)
    plan = plan_from_handles(query, retrieval["handles"] if retrieval["ready"] else [])
    # The planner consumes the same immutable retrieval result sent to the UI.
    plan["retrieval_generation_sha256"] = retrieval["generation_sha256"]
    plan["retrieval_evidence_set_sha256"] = retrieval["evidence_set_sha256"]
    if not query.strip():
        frontier = {"state": "NOT_RUN", "ready": False, "handles": [], "scores": []}
    else:
        try:
            frontier = frontier_search(query, k=k)
        except FrontierBoundaryError as exc:
            frontier = {"state": "BLOCKED", "ready": False, "handles": [],
                        "scores": [], "reason": type(exc).__name__}
    receipt = {
        "query_sha256": retrieval["query_sha256"],
        "generation_sha256": retrieval["generation_sha256"],
        "evidence_set_sha256": retrieval["evidence_set_sha256"],
        "handles_sha256": canonical_sha256(retrieval["handles"]),
        "frontier_handles_sha256": canonical_sha256(frontier["handles"]),
        "ranking_receipt_sha256": canonical_sha256(retrieval["ranking_receipt"]),
        "plan_sha256": canonical_sha256(plan),
        "signature": "UNSIGNED_CONTENT_DIGEST",
    }
    state = retrieval["state"]
    if retrieval["ready"] and not frontier["ready"]:
        state = "PARTIAL_FRONTIER_UNAVAILABLE"
    return {"schema": "szl.second-brain.query/v1", "state": state,
            "ready": bool(retrieval["ready"] and frontier["ready"]),
            "retrieve": retrieval, "plan": plan, "frontier": frontier,
            "receipt": {**receipt, "sha256": canonical_sha256(receipt)},
            "content_access": "HANDLES_ONLY", "execution_authority": "NONE"}
