"""Governed hybrid retrieval and controller-only content hydration.

The public API always returns handles and digests, never corpus text. A dense
provider and reranker are optional, injectable components; when absent or
unavailable the result is explicitly labelled ``BM25_ONLY`` rather than being
misrepresented as hybrid.

``AuthorizedHydrator`` is for the trusted Forge controller process. It requires
principal, tenant, policy revision, and an explicit authorization callback,
then verifies the source and SHA-256 of every hydrated row. It is intentionally
not registered on the public FastAPI routes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from second_brain.retrieve import CORPUS, SecondBrainIndex, canonical_sha256, index

PIN_RE = re.compile(r"^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SCHEMA_HYBRID = "szl.second-brain.hybrid-context/v1"
SCHEMA_HYDRATION = "szl.second-brain.authorized-hydration/v1"


class DenseProvider(Protocol):
    """Return ranked ``{'node_id': str, 'score': number}`` candidates."""

    def __call__(self, query: str, k: int) -> Sequence[Mapping[str, Any]]: ...


class Reranker(Protocol):
    """Return existing candidate node IDs in preferred order."""

    def __call__(
        self, query: str, candidates: Sequence[Mapping[str, Any]], k: int
    ) -> Sequence[str]: ...


class AccessAuthorizer(Protocol):
    """Authorize one public-projection node for one principal and tenant."""

    def __call__(
        self,
        principal_id: str,
        tenant_id: str,
        policy_revision: str,
        node_id: str,
        source: str,
    ) -> bool: ...


class RetrievalBoundaryError(ValueError):
    """Raised when a provider or hydration result crosses a trust boundary."""


def _finite_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise RetrievalBoundaryError("candidate score must be numeric") from exc
    if not math.isfinite(score):
        raise RetrievalBoundaryError("candidate score must be finite")
    return score


def _bounded_k(value: Any, *, maximum: int = 50) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RetrievalBoundaryError("k must be an integer") from exc
    return max(1, min(parsed, maximum))


def _authoritative_rows(brain: SecondBrainIndex) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in brain.rows:
        node_id = str(row.get("id") or "")
        digest = str(row.get("sha256") or "").lower()
        if not node_id or not HEX64_RE.fullmatch(digest):
            raise RetrievalBoundaryError("index contains malformed node identity")
        if node_id in rows:
            raise RetrievalBoundaryError(f"duplicate node id in index: {node_id}")
        rows[node_id] = {
            "id": node_id,
            "title": str(row.get("title") or ""),
            "source": str(row.get("source") or "unknown"),
            "sha256": digest,
        }
    return rows


def _rrf(
    rankings: Sequence[tuple[str, Sequence[str], float]],
    *,
    rrf_k: int,
) -> tuple[dict[str, float], dict[str, dict[str, int]]]:
    fused: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for name, node_ids, weight in rankings:
        seen: set[str] = set()
        for rank, node_id in enumerate(node_ids, start=1):
            if node_id in seen:
                continue
            seen.add(node_id)
            fused[node_id] = fused.get(node_id, 0.0) + (
                float(weight) / (rrf_k + rank)
            )
            ranks.setdefault(node_id, {})[name] = rank
    return fused, ranks


class HybridSecondBrain:
    """Fuse sparse and optional dense candidates without exposing content."""

    def __init__(
        self,
        brain: SecondBrainIndex | None = None,
        *,
        dense_provider: DenseProvider | None = None,
        reranker: Reranker | None = None,
        sparse_weight: float = 1.0,
        dense_weight: float = 1.0,
        rrf_k: int = 60,
        candidate_multiplier: int = 4,
        per_source_limit: int = 3,
        allow_sparse_fallback: bool = True,
    ) -> None:
        self.brain = brain or index()
        self.dense_provider = dense_provider
        self.reranker = reranker
        self.sparse_weight = float(sparse_weight)
        self.dense_weight = float(dense_weight)
        self.rrf_k = _bounded_k(rrf_k, maximum=10_000)
        self.candidate_multiplier = _bounded_k(candidate_multiplier, maximum=20)
        self.per_source_limit = _bounded_k(per_source_limit, maximum=20)
        self.allow_sparse_fallback = bool(allow_sparse_fallback)
        if self.sparse_weight <= 0 or self.dense_weight <= 0:
            raise RetrievalBoundaryError("fusion weights must be positive")

    def _sparse(self, query: str, candidate_k: int) -> tuple[list[str], list[float]]:
        hit = self.brain.search(query, k=min(candidate_k, 12))
        handles = hit.get("handles") or []
        scores = hit.get("scores") or []
        node_ids: list[str] = []
        parsed_scores: list[float] = []
        for position, handle in enumerate(handles):
            if not isinstance(handle, Mapping) or not handle.get("nodeId"):
                raise RetrievalBoundaryError("sparse retriever returned malformed handle")
            node_ids.append(str(handle["nodeId"]))
            parsed_scores.append(
                _finite_score(scores[position] if position < len(scores) else 0.0)
            )
        return node_ids, parsed_scores

    def _dense(
        self,
        query: str,
        candidate_k: int,
        authoritative: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[str], list[float]]:
        if self.dense_provider is None:
            return [], []
        raw = self.dense_provider(query, candidate_k)
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            raise RetrievalBoundaryError("dense provider must return a sequence")
        scored: list[tuple[float, int, str]] = []
        seen: set[str] = set()
        for position, candidate in enumerate(raw):
            if not isinstance(candidate, Mapping):
                raise RetrievalBoundaryError("dense provider returned malformed candidate")
            node_id = str(candidate.get("node_id") or candidate.get("nodeId") or "")
            if not node_id or node_id not in authoritative:
                raise RetrievalBoundaryError(
                    "dense provider returned an unknown public-projection node"
                )
            if node_id in seen:
                continue
            seen.add(node_id)
            scored.append((_finite_score(candidate.get("score")), position, node_id))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [item[2] for item in scored], [item[0] for item in scored]

    def context(self, query: str, k: int = 6) -> dict[str, Any]:
        query = str(query or "").strip()
        requested_k = _bounded_k(k, maximum=12)
        query_digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        if not query:
            return {
                "schema": SCHEMA_HYBRID,
                "state": "ABSTAIN_NO_QUERY",
                "ready": False,
                "content_access": "HANDLES_ONLY",
                "query_sha256": query_digest,
                "handles": [],
                "evidence": [],
                "evidence_set_sha256": canonical_sha256([]),
                "ranking_receipt": {
                    "mode": "UNAVAILABLE",
                    "sparse": "NOT_RUN",
                    "dense": "NOT_RUN",
                    "reranker": "NOT_RUN",
                },
                "honesty": "Empty query; no ranking was fabricated.",
            }
        if not self.brain.built:
            return {
                "schema": SCHEMA_HYBRID,
                "state": "UNAVAILABLE",
                "ready": False,
                "content_access": "HANDLES_ONLY",
                "query_sha256": query_digest,
                "handles": [],
                "evidence": [],
                "evidence_set_sha256": canonical_sha256([]),
                "ranking_receipt": {
                    "mode": "UNAVAILABLE",
                    "sparse": "UNAVAILABLE",
                    "dense": "NOT_RUN",
                    "reranker": "NOT_RUN",
                },
                "honesty": (
                    f"Public projection unavailable ({self.brain.load_error or 'empty'}); "
                    "private graph content was not substituted."
                ),
            }

        authoritative = _authoritative_rows(self.brain)
        candidate_k = min(50, max(requested_k, requested_k * self.candidate_multiplier))
        sparse_ids, sparse_scores = self._sparse(query, candidate_k)
        dense_ids: list[str] = []
        dense_scores: list[float] = []
        dense_state = "NOT_CONFIGURED"
        dense_error: str | None = None
        if self.dense_provider is not None:
            try:
                dense_ids, dense_scores = self._dense(
                    query, candidate_k, authoritative
                )
                dense_state = "OK"
            except Exception as exc:
                dense_state = "UNAVAILABLE"
                dense_error = type(exc).__name__
                if not self.allow_sparse_fallback:
                    raise RetrievalBoundaryError(
                        f"dense provider unavailable: {type(exc).__name__}"
                    ) from exc

        rankings: list[tuple[str, Sequence[str], float]] = [
            ("sparse", sparse_ids, self.sparse_weight)
        ]
        if dense_state == "OK":
            rankings.append(("dense", dense_ids, self.dense_weight))
        fused, component_ranks = _rrf(rankings, rrf_k=self.rrf_k)
        ordered = sorted(fused, key=lambda node_id: (-fused[node_id], node_id))

        reranker_state = "NOT_CONFIGURED"
        reranker_error: str | None = None
        if self.reranker is not None and ordered:
            candidates = [
                {
                    "node_id": node_id,
                    "title": authoritative[node_id]["title"],
                    "source": authoritative[node_id]["source"],
                    "sha256": authoritative[node_id]["sha256"],
                    "fusion_score": fused[node_id],
                }
                for node_id in ordered
            ]
            try:
                reranked = list(self.reranker(query, candidates, candidate_k))
                if len(reranked) != len(set(reranked)):
                    raise RetrievalBoundaryError("reranker returned duplicate node IDs")
                if not set(reranked).issubset(set(ordered)):
                    raise RetrievalBoundaryError("reranker introduced unknown node IDs")
                ordered = reranked + [
                    node_id for node_id in ordered if node_id not in reranked
                ]
                reranker_state = "OK"
            except Exception as exc:
                reranker_state = "UNAVAILABLE"
                reranker_error = type(exc).__name__

        selected: list[str] = []
        source_counts: dict[str, int] = {}
        for node_id in ordered:
            source = authoritative[node_id]["source"]
            if source_counts.get(source, 0) >= self.per_source_limit:
                continue
            selected.append(node_id)
            source_counts[source] = source_counts.get(source, 0) + 1
            if len(selected) >= requested_k:
                break

        handles = [
            {
                "nodeId": node_id,
                "nodeKind": "INDEX",
                "label": "DECLARED",
                "note": authoritative[node_id]["title"][:160],
            }
            for node_id in selected
        ]
        evidence = [
            {
                "node_id": node_id,
                "source": authoritative[node_id]["source"],
                "sha256": authoritative[node_id]["sha256"],
            }
            for node_id in selected
        ]
        mode = "HYBRID_SPARSE_DENSE" if dense_state == "OK" else "BM25_ONLY"
        if dense_state == "UNAVAILABLE":
            mode = "BM25_FALLBACK_DENSE_UNAVAILABLE"
        if reranker_state == "OK":
            mode += "+RERANKER"
        elif reranker_state == "UNAVAILABLE":
            mode += "+RERANKER_UNAVAILABLE"

        receipt = {
            "mode": mode,
            "sparse": "OK",
            "dense": dense_state,
            "dense_error_type": dense_error,
            "reranker": reranker_state,
            "reranker_error_type": reranker_error,
            "fusion": "RECIPROCAL_RANK_FUSION",
            "rrf_k": self.rrf_k,
            "sparse_weight": self.sparse_weight,
            "dense_weight": self.dense_weight,
            "candidate_k": candidate_k,
            "sparse_candidate_count": len(sparse_ids),
            "dense_candidate_count": len(dense_ids),
            "selected_count": len(selected),
            "per_source_limit": self.per_source_limit,
            "component_ranks": {
                node_id: component_ranks[node_id] for node_id in selected
            },
            "sparse_scores": {
                node_id: sparse_scores[position]
                for position, node_id in enumerate(sparse_ids)
                if node_id in selected
            },
            "dense_scores": {
                node_id: dense_scores[position]
                for position, node_id in enumerate(dense_ids)
                if node_id in selected
            },
        }
        return {
            "schema": SCHEMA_HYBRID,
            "state": (
                "GROUNDED_HANDLES_READY"
                if selected
                else "ABSTAIN_NO_GROUNDED_HANDLES"
            ),
            "ready": bool(selected),
            "content_access": "HANDLES_ONLY",
            "query_sha256": query_digest,
            "handles": handles,
            "evidence": evidence,
            "evidence_set_sha256": canonical_sha256(evidence),
            "handles_sha256": canonical_sha256(handles),
            "ranking_receipt": receipt,
            "corpus_n": self.brain.n,
            "index_is_model_weights": False,
            "raw_graph_nodes_admitted_to_gradients": 0,
            "honesty": (
                "Public projection only. Ranking mode is reported exactly; lexical or "
                "dense similarity is never correctness. Content remains controller-only."
            ),
        }


class AuthorizedHydrator:
    """Resolve public handles inside a trusted controller after explicit ACLs."""

    def __init__(
        self,
        authorizer: AccessAuthorizer,
        *,
        path: Path | None = None,
    ) -> None:
        self.authorizer = authorizer
        self.path = Path(path or CORPUS)
        self._rows = self._load()

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.is_file():
            raise RetrievalBoundaryError(f"public corpus missing: {self.path}")
        rows: dict[str, dict[str, str]] = {}
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RetrievalBoundaryError(
                    f"invalid public corpus JSON at line {line_number}"
                ) from exc
            if not isinstance(row, dict):
                raise RetrievalBoundaryError(
                    f"public corpus row {line_number} is not an object"
                )
            node_id = str(row.get("id") or "")
            source = str(row.get("source") or "unknown")
            content = str(row.get("text") or "")
            declared = str(row.get("sha256") or "").lower()
            actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if not node_id or not HEX64_RE.fullmatch(declared) or actual != declared:
                raise RetrievalBoundaryError(
                    f"public corpus integrity failure at line {line_number}"
                )
            if node_id in rows:
                raise RetrievalBoundaryError(f"duplicate public corpus node: {node_id}")
            rows[node_id] = {
                "node_id": node_id,
                "source": source,
                "sha256": declared,
                "content": content,
            }
        return rows

    def hydrate(
        self,
        handles: Sequence[Mapping[str, Any]],
        *,
        principal_id: str,
        tenant_id: str,
        policy_revision: str,
    ) -> dict[str, Any]:
        principal_id = str(principal_id or "").strip()
        tenant_id = str(tenant_id or "").strip()
        policy_revision = str(policy_revision or "").strip().lower()
        if not principal_id or not tenant_id:
            raise RetrievalBoundaryError("principal_id and tenant_id are required")
        if not PIN_RE.fullmatch(policy_revision):
            raise RetrievalBoundaryError("policy_revision must be immutable")
        if not isinstance(handles, Sequence) or isinstance(
            handles, (str, bytes, bytearray)
        ):
            raise RetrievalBoundaryError("handles must be a sequence")

        hydrated: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw in handles:
            if not isinstance(raw, Mapping):
                raise RetrievalBoundaryError("malformed handle")
            node_id = str(raw.get("nodeId") or "")
            if not node_id or node_id in seen or node_id not in self._rows:
                raise RetrievalBoundaryError("unknown or duplicate handle")
            row = self._rows[node_id]
            supplied_source = raw.get("source")
            supplied_digest = raw.get("sha256")
            if supplied_source is not None and str(supplied_source) != row["source"]:
                raise RetrievalBoundaryError("handle source mismatch")
            if (
                supplied_digest is not None
                and str(supplied_digest).lower() != row["sha256"]
            ):
                raise RetrievalBoundaryError("handle digest mismatch")
            try:
                allowed = bool(
                    self.authorizer(
                        principal_id,
                        tenant_id,
                        policy_revision,
                        node_id,
                        row["source"],
                    )
                )
            except Exception as exc:
                raise RetrievalBoundaryError(
                    f"authorization unavailable: {type(exc).__name__}"
                ) from exc
            if not allowed:
                raise RetrievalBoundaryError(f"access denied for node: {node_id}")
            hydrated.append(copy.deepcopy(row))
            seen.add(node_id)

        evidence = [
            {
                "node_id": row["node_id"],
                "source": row["source"],
                "sha256": row["sha256"],
            }
            for row in hydrated
        ]
        return {
            "schema": SCHEMA_HYDRATION,
            "state": "AUTHORIZED_CONTENT_READY",
            "ready": bool(hydrated),
            "principal_id_sha256": hashlib.sha256(
                principal_id.encode("utf-8")
            ).hexdigest(),
            "tenant_id_sha256": hashlib.sha256(
                tenant_id.encode("utf-8")
            ).hexdigest(),
            "policy_revision": policy_revision,
            "evidence_set_sha256": canonical_sha256(evidence),
            "documents": hydrated,
            "content_access": "CONTROLLER_ONLY",
            "raw_graph_nodes_admitted_to_gradients": 0,
        }


_DEFAULT_HYBRID: HybridSecondBrain | None = None


def hybrid_index() -> HybridSecondBrain:
    global _DEFAULT_HYBRID
    if _DEFAULT_HYBRID is None:
        _DEFAULT_HYBRID = HybridSecondBrain()
    return _DEFAULT_HYBRID


def reset_hybrid_index() -> None:
    global _DEFAULT_HYBRID
    _DEFAULT_HYBRID = None


def hybrid_context(query: str, k: int = 6) -> dict[str, Any]:
    return hybrid_index().context(query, k=k)


__all__ = [
    "AccessAuthorizer",
    "AuthorizedHydrator",
    "DenseProvider",
    "HybridSecondBrain",
    "Reranker",
    "RetrievalBoundaryError",
    "SCHEMA_HYBRID",
    "SCHEMA_HYDRATION",
    "hybrid_context",
    "hybrid_index",
    "reset_hybrid_index",
]
