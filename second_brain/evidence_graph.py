"""Bounded typed projection of one existing Brain transaction and Lutar references.

No provider access, private graph, model call, action execution or proof replay.
A content digest binds this projection; it is not an authenticated attestation.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from second_brain.lutar_reference import lutar_reference
from second_brain.web_contracts import QueryRequest
from second_brain.workbench import query_bundle

SCHEMA = "szl.second-brain.evidence-graph/v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceGraphError(ValueError):
    """A local transaction violates its projection contract."""


class EvidenceNode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ordinal: int = Field(ge=0, le=127)
    node_id: str = Field(min_length=1, max_length=600)
    kind: Literal["CORPUS_HANDLE", "REVIEW_CANDIDATE", "LUTAR_REFERENCE", "CITATION_PLAN", "VIEW_RECEIPT"]
    title: str = Field(max_length=500)
    evidence_level: Literal["HANDLE_ONLY", "REVIEW_REQUIRED", "SOURCE_BOUND_NOT_REPLAYED", "SOFTWARE_PROPOSAL", "UNSIGNED_CONTENT_DIGEST"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: str = Field(max_length=1200)
    revision: str = Field(max_length=160)
    revision_kind: str = Field(max_length=100)
    execution_authority: Literal["NONE"] = "NONE"


class EvidenceEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: int = Field(ge=0, le=127)
    target: int = Field(ge=0, le=127)
    relation: Literal["CITES_HANDLE", "BINDS_QUERY_RESULT", "INCLUDES_REFERENCE"]


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _hex(value: Any) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise EvidenceGraphError("invalid evidence digest")
    return value


def check_backward_edges(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bool:
    """Runtime property of this view only; no Lean-to-Python refinement claim."""
    if not nodes or len(nodes) > 128 or len(edges) > 256:
        return False
    try:
        ns = [EvidenceNode.model_validate(n) for n in nodes]
        es = [EvidenceEdge.model_validate(e) for e in edges]
    except ValueError:
        return False
    if [n.ordinal for n in ns] != list(range(len(ns))):
        return False
    if len({n.node_id for n in ns}) != len(ns):
        return False
    pairs = [(e.source, e.target, e.relation) for e in es]
    return len(set(pairs)) == len(pairs) and all(0 <= e.target < e.source < len(ns) for e in es)


def _verify_transaction(bundle: dict[str, Any]) -> None:
    receipt = dict(bundle["receipt"])
    expected = receipt.pop("sha256")
    if digest(receipt) != _hex(expected) or receipt["signature"] != "UNSIGNED_CONTENT_DIGEST":
        raise EvidenceGraphError("transaction checksum mismatch")
    retrieval = bundle["retrieve"]
    for key in ("query_sha256", "generation_sha256", "evidence_set_sha256"):
        if retrieval[key] != receipt[key]:
            raise EvidenceGraphError("retrieval identity differs from receipt")
    # The existing abstention/unavailable contract omits its redundant handle
    # digest. The receipt always binds the actual handle list below.
    if "handles_sha256" in retrieval and retrieval["handles_sha256"] != receipt["handles_sha256"]:
        raise EvidenceGraphError("retrieval handle digest differs from receipt")
    if (bundle["plan"]["retrieval_generation_sha256"] != receipt["generation_sha256"]
            or bundle["plan"]["retrieval_evidence_set_sha256"] != receipt["evidence_set_sha256"]):
        raise EvidenceGraphError("plan source binding mismatch")
    checks = {
        "evidence_set_sha256": retrieval["evidence"],
        "handles_sha256": bundle["retrieve"]["handles"],
        "frontier_handles_sha256": bundle["frontier"]["handles"],
        "ranking_receipt_sha256": bundle["retrieve"]["ranking_receipt"],
        "plan_sha256": bundle["plan"],
    }
    if any(digest(value) != receipt[key] for key, value in checks.items()):
        raise EvidenceGraphError("transaction object binding mismatch")
    if bundle["content_access"] != "HANDLES_ONLY" or bundle["execution_authority"] != "NONE":
        raise EvidenceGraphError("transaction authority boundary mismatch")


def evidence_snapshot(query: str = "", k: int = 6) -> dict[str, Any]:
    """Rebuild from local source functions once; never accept caller-provided handles."""
    request = QueryRequest(query=query, k=k)
    bundle = query_bundle(request.query, request.k)
    reference = lutar_reference()
    try:
        _verify_transaction(bundle)
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        def node(kind, identity, title, level, sha, source="", revision="", revision_kind="NOT_ASSERTED"):
            item = EvidenceNode(ordinal=len(nodes), node_id=kind + ":" + identity,
                                kind=kind, title=title, evidence_level=level, sha256=_hex(sha),
                                source=source, revision=revision, revision_kind=revision_kind)
            nodes.append(item.model_dump())
            return item.ordinal

        evidence = {e["node_id"]: e for e in bundle["retrieve"]["evidence"]}
        handles = bundle["retrieve"]["handles"]
        if len(evidence) != len(bundle["retrieve"]["evidence"]) or len({h["nodeId"] for h in handles}) != len(handles):
            raise EvidenceGraphError("duplicate source identity")
        corpus = {}
        for h in handles:
            e = evidence[h["nodeId"]]
            corpus[h["nodeId"]] = node("CORPUS_HANDLE", h["nodeId"], h["note"], "HANDLE_ONLY", e["sha256"],
                                          e["source"], bundle["retrieve"]["generation_sha256"], "CORPUS_CONTENT_SHA256")
        for h in bundle["frontier"]["handles"]:
            node("REVIEW_CANDIDATE", h["nodeId"], h["title"], "REVIEW_REQUIRED", h["sha256"],
                 h["repository"] + "/" + h["path"], h["revision"], h.get("revisionKind", "SOURCE_DECLARED"))
        for h in reference["handles"]:
            node("LUTAR_REFERENCE", h["nodeId"], h["claimId"] + " · " + h["title"],
                 "SOURCE_BOUND_NOT_REPLAYED", h["sha256"], h["repository"] + "/" + h["path"], h["revision"], "GIT_COMMIT")
        plan = bundle["plan"]
        plan_index = node("CITATION_PLAN", bundle["receipt"]["plan_sha256"], plan["decision"],
                          "SOFTWARE_PROPOSAL", bundle["receipt"]["plan_sha256"])
        cited = plan["citedNodeIds"]
        if len(set(cited)) != len(cited) or any(identity not in corpus for identity in cited):
            raise EvidenceGraphError("citation not bound to offered handle")
        edges.extend(EvidenceEdge(source=plan_index, target=corpus[identity], relation="CITES_HANDLE").model_dump() for identity in cited)
        # The original query receipt does not contain the separately observed
        # Lutar references. Bind the augmented view with a NEW manifest instead
        # of attaching new claims to the older checksum's asserted scope.
        view_manifest = {
            "schema": "szl.second-brain.evidence-view-binding/v1",
            "query_receipt_sha256": bundle["receipt"]["sha256"],
            "lutar_source_sha256": reference["source_sha256"],
            "lutar_state": reference["state"],
            "nodes_sha256": digest(nodes), "edges_sha256": digest(edges),
            "signature": "UNSIGNED_CONTENT_DIGEST",
        }
        view_sha = digest(view_manifest)
        root = node("VIEW_RECEIPT", view_sha, "Bound evidence view", "UNSIGNED_CONTENT_DIGEST", view_sha)
        edges.extend(EvidenceEdge(source=root, target=i,
                                 relation="INCLUDES_REFERENCE" if n["kind"] == "LUTAR_REFERENCE" else "BINDS_QUERY_RESULT").model_dump()
                     for i, n in enumerate(nodes[:root]))
        if not check_backward_edges(nodes, edges):
            raise EvidenceGraphError("invalid bounded dependency graph")
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceGraphError("local evidence projection unavailable") from exc
    components = {
        "retrieval": {"ready": bool(bundle["retrieve"]["ready"]), "state": bundle["retrieve"]["state"]},
        "frontier": {"ready": bool(bundle["frontier"]["ready"]), "state": bundle["frontier"]["state"]},
        "lutar": {"ready": bool(reference["ready"]), "state": reference["state"]},
    }
    ready = bool(request.query) and all(c["ready"] for c in components.values())
    result = {
        "schema": SCHEMA, "state": "READY_FOR_INSPECTION" if ready else "PARTIAL_OR_UNAVAILABLE",
        "ready": ready, "query_sha256": bundle["receipt"]["query_sha256"],
        "components": components, "nodes": nodes, "edges": edges,
        "node_count": len(nodes), "edge_count": len(edges),
        "query_receipt_sha256": bundle["receipt"]["sha256"],
        "view_manifest": view_manifest,
        "lutar_source_sha256": reference["source_sha256"],
        "content_access": "HANDLES_ONLY", "execution_authority": "NONE",
        "training_authority": "NONE", "provider_requests": 0,
        "provider_runtime": "NOT_PROBED", "model_generation": "NOT_CONFIGURED",
        "freshness_basis": "LOCAL_RETRIEVAL_SNAPSHOT_AND_RECHECKED_LUTAR_BYTES_NOT_LIVE_ESTATE",
        "graph_condition": {"name": "STRICTLY_BACKWARD_INTEGER_EDGES", "runtime_checked": True,
                            "formal_reference": "F4", "refinement_proved": False,
                            "scope": "THIS_BOUNDED_VIEW_NOT_THE_PRIVATE_BRAIN_OR_PROVIDER_WORKFLOW"},
        "edge_semantics": "REFERENCE_AND_CITATION_ONLY_NOT_PROOF_OR_AUTHORIZATION",
        "signature": "UNSIGNED_CONTENT_DIGEST",
    }
    return {**result, "content_sha256": digest(result)}
