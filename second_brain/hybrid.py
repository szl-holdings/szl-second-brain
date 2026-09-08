"""Governed hybrid retrieval and controller-only hydration.

Only a classified ProviderUnavailable may fall back. Malformed results, corpus
identity drift and access failures must never be disguised as a healthy fallback.
"""
from __future__ import annotations

import copy
import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from second_brain.corpus import CorpusIntegrityError, load_corpus
from second_brain.retrieve import CORPUS, SecondBrainIndex, canonical_sha256, index

PIN_RE = re.compile(r"^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SCHEMA_HYBRID = "szl.second-brain.hybrid-context/v1"
SCHEMA_HYDRATION = "szl.second-brain.authorized-hydration/v1"


class DenseProvider(Protocol):
    def __call__(self, query: str, k: int) -> Sequence[Mapping[str, Any]]: ...


class Reranker(Protocol):
    def __call__(self, query: str, candidates: Sequence[Mapping[str, Any]], k: int) -> Sequence[str]: ...


class AccessAuthorizer(Protocol):
    def __call__(self, principal_id: str, tenant_id: str, policy_revision: str, node_id: str, source: str) -> bool: ...


class RetrievalBoundaryError(ValueError):
    """Integrity or invalid request; not an outage and not fallback-eligible."""


class ProviderUnavailable(RuntimeError):
    """A trusted adapter classified an actual dependency outage (not bad data)."""


def _finite_score(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise RetrievalBoundaryError("candidate score must be finite and numeric")
    return float(value)


def _bounded_k(value: Any, *, maximum: int = 50) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise RetrievalBoundaryError("integer outside permitted range")
    return value


def _authoritative_rows(brain: SecondBrainIndex) -> dict[str, dict[str, Any]]:
    rows = {}
    for row in brain.rows:
        node_id, checksum = row.get("id"), row.get("sha256")
        if not isinstance(node_id, str) or not node_id or not isinstance(checksum, str) or not HEX64_RE.fullmatch(checksum):
            raise RetrievalBoundaryError("index contains malformed node identity")
        if node_id in rows:
            raise RetrievalBoundaryError("duplicate index node")
        rows[node_id] = {"id": node_id, "title": row["title"], "source": row["source"], "sha256": checksum}
    return rows


def _rrf(rankings, *, rrf_k: int):
    fused, ranks = {}, {}
    for name, node_ids, weight in rankings:
        for rank, node_id in enumerate(dict.fromkeys(node_ids), 1):
            fused[node_id] = fused.get(node_id, 0.0) + weight / (rrf_k + rank)
            ranks.setdefault(node_id, {})[name] = rank
    return fused, ranks


class HybridSecondBrain:
    def __init__(self, brain: SecondBrainIndex | None = None, *,
                 dense_provider: DenseProvider | None = None, reranker: Reranker | None = None,
                 sparse_weight: float = 1.0, dense_weight: float = 1.0, rrf_k: int = 60,
                 candidate_multiplier: int = 4, per_source_limit: int = 3,
                 allow_sparse_fallback: bool = True, allow_reranker_fallback: bool = True) -> None:
        self.brain = brain if brain is not None else index()
        self.dense_provider, self.reranker = dense_provider, reranker
        self.sparse_weight, self.dense_weight = _finite_score(sparse_weight), _finite_score(dense_weight)
        if self.sparse_weight <= 0 or self.dense_weight <= 0:
            raise RetrievalBoundaryError("fusion weights must be positive")
        self.rrf_k = _bounded_k(rrf_k, maximum=10000)
        self.candidate_multiplier = _bounded_k(candidate_multiplier, maximum=20)
        self.per_source_limit = _bounded_k(per_source_limit, maximum=20)
        if type(allow_sparse_fallback) is not bool or type(allow_reranker_fallback) is not bool:
            raise RetrievalBoundaryError("fallback settings must be Boolean")
        self.allow_sparse_fallback, self.allow_reranker_fallback = allow_sparse_fallback, allow_reranker_fallback

    def _sparse(self, query: str, candidate_k: int) -> tuple[list[str], list[float]]:
        hit = self.brain.search_candidates(query, limit=candidate_k)
        handles, scores = hit.get("handles", []), hit.get("scores", [])
        if len(handles) != len(scores) or len(handles) > candidate_k:
            raise RetrievalBoundaryError("sparse candidate shape mismatch")
        node_ids = [h["nodeId"] for h in handles]
        if len(set(node_ids)) != len(node_ids):
            raise RetrievalBoundaryError("duplicate sparse candidate")
        return node_ids, [_finite_score(score) for score in scores]

    def _dense(self, query, candidate_k, authoritative):
        if self.dense_provider is None:
            return [], []
        bound_generation = getattr(self.dense_provider, "generation_sha256", None)
        if bound_generation is not None and bound_generation != self.brain.generation_sha256:
            raise RetrievalBoundaryError("dense corpus generation mismatch")
        raw = self.dense_provider(query, candidate_k)
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)) or len(raw) > candidate_k:
            raise RetrievalBoundaryError("dense provider returned invalid candidate sequence")
        seen, scored = set(), []
        for position, candidate in enumerate(raw):
            if not isinstance(candidate, Mapping):
                raise RetrievalBoundaryError("dense provider returned malformed candidate")
            node_id = candidate.get("node_id") or candidate.get("nodeId")
            if not isinstance(node_id, str) or node_id not in authoritative or node_id in seen:
                raise RetrievalBoundaryError("dense provider unavailable: unknown or duplicate node")
            for key in ("source", "sha256"):
                if key in candidate and candidate[key] != authoritative[node_id][key]:
                    raise RetrievalBoundaryError("dense candidate identity mismatch")
            seen.add(node_id)
            scored.append((_finite_score(candidate.get("score")), position, node_id))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [item[2] for item in scored], [item[0] for item in scored]

    def context(self, query: str, k: int = 6) -> dict[str, Any]:
        # Per-request shallow coordinator copy holds one immutable sparse view;
        # concurrent reload cannot mix corpus counts, IDs, scores or evidence.
        request = copy.copy(self)
        request.brain = self.brain.snapshot()
        return request._context(query, k)

    def _context(self, query: str, k: int) -> dict[str, Any]:
        if not isinstance(query, str) or len(query) > 2000:
            raise RetrievalBoundaryError("query must be a bounded string")
        query = query.strip()
        requested_k = _bounded_k(k, maximum=12)
        base = {"schema": SCHEMA_HYBRID, "content_access": "HANDLES_ONLY",
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "generation_sha256": self.brain.generation_sha256,
                "index_is_model_weights": False, "raw_graph_nodes_admitted_to_gradients": 0}
        if not query or not self.brain.built:
            return {**base, "state": "ABSTAIN_NO_QUERY" if not query else "UNAVAILABLE", "ready": False,
                    "handles": [], "evidence": [], "evidence_set_sha256": canonical_sha256([]),
                    "ranking_receipt": {"mode": "UNAVAILABLE", "sparse": "NOT_RUN" if not query else "UNAVAILABLE",
                                        "dense": "NOT_RUN", "reranker": "NOT_RUN"},
                    "honesty": "No ranking fabricated and no private graph substituted."}
        dense_binding = copy.deepcopy(getattr(self.dense_provider, "binding", None))
        authoritative = _authoritative_rows(self.brain)
        candidate_k = min(128, requested_k * self.candidate_multiplier)
        sparse_ids, sparse_scores = self._sparse(query, candidate_k)
        if not set(sparse_ids).issubset(authoritative):
            raise RetrievalBoundaryError("sparse provider introduced an unknown node")
        dense_ids, dense_scores = [], []
        dense_state, dense_error = "NOT_CONFIGURED", None
        if self.dense_provider is not None:
            try:
                dense_ids, dense_scores = self._dense(query, candidate_k, authoritative)
                dense_state = "OK"
            except ProviderUnavailable as exc:
                if not self.allow_sparse_fallback:
                    raise RetrievalBoundaryError("dense provider unavailable") from exc
                dense_state, dense_error = "UNAVAILABLE", type(exc).__name__
        rankings = [("sparse", sparse_ids, self.sparse_weight)]
        if dense_state == "OK":
            rankings.append(("dense", dense_ids, self.dense_weight))
        fused, component_ranks = _rrf(rankings, rrf_k=self.rrf_k)
        ordered = sorted(fused, key=lambda node_id: (-fused[node_id], node_id))
        reranker_state, reranker_error, reranked_count = "NOT_CONFIGURED", None, 0
        if self.reranker is not None and ordered:
            bound_generation = getattr(self.reranker, "generation_sha256", None)
            if bound_generation is not None and bound_generation != self.brain.generation_sha256:
                raise RetrievalBoundaryError("reranker corpus generation mismatch")
            candidates = [{"node_id": node_id, "title": authoritative[node_id]["title"],
                           "source": authoritative[node_id]["source"], "sha256": authoritative[node_id]["sha256"],
                           "fusion_score": fused[node_id]} for node_id in ordered[:candidate_k]]
            offered = {row["node_id"] for row in candidates}
            try:
                reranked = self.reranker(query, candidates, candidate_k)
                if (not isinstance(reranked, Sequence) or isinstance(reranked, (str, bytes))
                        or not reranked or len(reranked) > len(candidates)
                        or any(not isinstance(node_id, str) for node_id in reranked)
                        or len(set(reranked)) != len(reranked) or not set(reranked).issubset(offered)):
                    raise RetrievalBoundaryError("reranker returned empty, duplicate or unknown node IDs")
                ordered = list(reranked) + [node_id for node_id in ordered if node_id not in reranked]
                reranker_state, reranked_count = "OK", len(reranked)
            except ProviderUnavailable as exc:
                if not self.allow_reranker_fallback:
                    raise RetrievalBoundaryError("reranker unavailable") from exc
                reranker_state, reranker_error = "UNAVAILABLE", type(exc).__name__
        selected, counts = [], {}
        for node_id in ordered:
            source = authoritative[node_id]["source"]
            if counts.get(source, 0) < self.per_source_limit:
                selected.append(node_id)
                counts[source] = counts.get(source, 0) + 1
                if len(selected) >= requested_k:
                    break
        handles = [{"nodeId": node_id, "nodeKind": "INDEX", "label": "DECLARED",
                    "note": authoritative[node_id]["title"][:160]} for node_id in selected]
        evidence = [{"node_id": node_id, "source": authoritative[node_id]["source"],
                     "sha256": authoritative[node_id]["sha256"]} for node_id in selected]
        mode = "HYBRID_SPARSE_DENSE" if dense_state == "OK" else "BM25_FALLBACK_DENSE_UNAVAILABLE" if dense_state == "UNAVAILABLE" else "BM25_ONLY"
        if reranker_state == "OK":
            mode += "+RERANKER"
        elif reranker_state == "UNAVAILABLE":
            mode += "+RERANKER_UNAVAILABLE"
        if dense_binding != getattr(self.dense_provider, "binding", None):
            raise RetrievalBoundaryError("provider identity changed during retrieval")
        receipt = {"dense_binding": dense_binding, "mode": mode, "sparse": "OK", "dense": dense_state, "dense_error_type": dense_error,
                   "reranker": reranker_state, "reranker_error_type": reranker_error,
                   "reranked_count": reranked_count, "fusion": "RECIPROCAL_RANK_FUSION", "rrf_k": self.rrf_k,
                   "sparse_weight": self.sparse_weight, "dense_weight": self.dense_weight,
                   "candidate_k": candidate_k, "sparse_candidate_count": len(sparse_ids),
                   "dense_candidate_count": len(dense_ids), "selected_count": len(selected),
                   "per_source_limit": self.per_source_limit, "generation_sha256": self.brain.generation_sha256,
                   "component_ranks": {node_id: component_ranks[node_id] for node_id in selected},
                   "sparse_scores": {node_id: sparse_scores[i] for i, node_id in enumerate(sparse_ids) if node_id in selected},
                   "dense_scores": {node_id: dense_scores[i] for i, node_id in enumerate(dense_ids) if node_id in selected}}
        return {**base, "state": "GROUNDED_HANDLES_READY" if selected else "ABSTAIN_NO_GROUNDED_HANDLES",
                "ready": bool(selected), "handles": handles, "evidence": evidence,
                "evidence_set_sha256": canonical_sha256(evidence), "handles_sha256": canonical_sha256(handles),
                "ranking_receipt": receipt, "corpus_n": self.brain.n,
                "honesty": "Public projection only. Ranking mode is reported exactly; similarity is never correctness. Content remains controller-only."}


class AuthorizedHydrator:
    def __init__(self, authorizer: AccessAuthorizer, *, path: Path | None = None,
                 expected_sha256: str | None = None) -> None:
        self.authorizer, self.path = authorizer, Path(path or CORPUS)
        try:
            corpus = load_corpus(self.path, expected_sha256)
        except (OSError, CorpusIntegrityError) as exc:
            raise RetrievalBoundaryError("public corpus integrity failure") from exc
        self.generation_sha256 = corpus.file_sha256
        self._rows = {row.node_id: {"node_id": row.node_id, "source": row.source,
                                   "sha256": row.sha256, "content": row.text} for row in corpus.rows}

    def hydrate(self, handles: Sequence[Mapping[str, Any]], *, principal_id: str,
                tenant_id: str, policy_revision: str) -> dict[str, Any]:
        if any(not isinstance(value, str) or not value.strip() or len(value) > 512 for value in (principal_id, tenant_id)):
            raise RetrievalBoundaryError("principal_id and tenant_id are required")
        if not isinstance(policy_revision, str) or not PIN_RE.fullmatch(policy_revision):
            raise RetrievalBoundaryError("policy_revision must be immutable")
        if not isinstance(handles, Sequence) or isinstance(handles, (str, bytes, bytearray)) or len(handles) > 128:
            raise RetrievalBoundaryError("handles must be a bounded sequence")
        hydrated, seen = [], set()
        for raw in handles:
            if not isinstance(raw, Mapping):
                raise RetrievalBoundaryError("malformed handle")
            node_id = raw.get("nodeId")
            if not isinstance(node_id, str) or node_id in seen or node_id not in self._rows:
                raise RetrievalBoundaryError("unknown or duplicate handle")
            row = self._rows[node_id]
            if raw.get("source") is not None and raw["source"] != row["source"]:
                raise RetrievalBoundaryError("handle source mismatch")
            if raw.get("sha256") is not None and raw["sha256"] != row["sha256"]:
                raise RetrievalBoundaryError("handle digest mismatch")
            try:
                allowed = self.authorizer(principal_id, tenant_id, policy_revision, node_id, row["source"])
            except Exception as exc:
                raise RetrievalBoundaryError("authorization unavailable") from exc
            if allowed is not True:
                raise RetrievalBoundaryError("access denied for node")
            hydrated.append(copy.deepcopy(row))
            seen.add(node_id)
        evidence = [{"node_id": row["node_id"], "source": row["source"], "sha256": row["sha256"]} for row in hydrated]
        return {"schema": SCHEMA_HYDRATION, "state": "AUTHORIZED_CONTENT_READY", "ready": bool(hydrated),
                "principal_id_sha256": hashlib.sha256(principal_id.encode()).hexdigest(),
                "tenant_id_sha256": hashlib.sha256(tenant_id.encode()).hexdigest(), "policy_revision": policy_revision,
                "evidence_set_sha256": canonical_sha256(evidence), "documents": hydrated,
                "content_access": "CONTROLLER_ONLY", "raw_graph_nodes_admitted_to_gradients": 0,
                "generation_sha256": self.generation_sha256}


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


__all__ = ["AccessAuthorizer", "AuthorizedHydrator", "DenseProvider", "HybridSecondBrain", "Reranker",
           "RetrievalBoundaryError", "ProviderUnavailable", "SCHEMA_HYBRID", "SCHEMA_HYDRATION",
           "hybrid_context", "hybrid_index", "reset_hybrid_index"]
