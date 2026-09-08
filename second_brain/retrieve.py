"""SOFTWARE lexical retrieval over a strictly admitted public projection.

Public handles only; raw content stays in the controller. Private graph counts
are historical declarations, not loaded data. Indexes never imply weights.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping

from second_brain.corpus import CorpusIntegrityError, load_corpus

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "brain-corpus.public.jsonl"
TOKEN = re.compile(r"[a-z0-9λ]+", re.I)
STOP = {
    "the", "is", "a", "an", "of", "and", "or", "to", "in", "for", "on", "at",
    "by", "as", "what", "which", "who", "how", "why", "does", "did", "are",
    "was", "be", "it", "this", "that", "with", "from", "into", "over", "not",
}
PUBLIC_CHUNK_COUNT = 575
PRIVATE_GRAPH_NODES = 9464
SCHEMA_RETRIEVE = "szl.second-brain.retrieve/v1"
SCHEMA_INDEX = "szl.second-brain.index/v1"
SCHEMA_NAV = "szl.brain.navigator-context/v1"


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text or "") if len(t) > 1 and t.lower() not in STOP]


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def bounded_int(value: Any, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError("integer outside permitted range")
    return value


def corpus_path(path: Path | None = None) -> Path:
    env = (os.environ.get("SECOND_BRAIN_CORPUS") or os.environ.get("AYLLU_BRAIN_CORPUS") or "").strip()
    return Path(path) if path is not None else Path(env) if env else CORPUS


@dataclass(frozen=True)
class _Generation:
    rows: tuple[Mapping[str, Any], ...]
    df: Mapping[str, int]
    sha256: str


class SecondBrainIndex:
    """Atomic in-process generations. Activation and durable storage remain external.

    Reload stages the full candidate, checks every row, then compare-and-swaps a
    single immutable state. A rejected candidate leaves the prior state usable
    and explicitly reports rejection; it is never a partial or empty success.
    """
    def __init__(self, path: Path | None = None, *, expected_sha256: str | None = None) -> None:
        self.path = corpus_path(path)
        self._state: _Generation | None = None
        self._lock = RLock()
        self._serial = 0
        self._read_only = False
        self.load_error: str | None = None
        self.last_reload_error: str | None = None
        self.reload(expected_sha256=expected_sha256)

    @property
    def rows(self) -> list[dict[str, Any]]:
        state = self._state
        return [{**row, "_toks": list(row["_toks"]), "_tf": Counter(row["_tf"])}
                for row in state.rows] if state else []

    @property
    def df(self) -> Counter[str]:
        return Counter(self._state.df) if self._state else Counter()

    @property
    def n(self) -> int:
        return len(self._state.rows) if self._state else 0

    @property
    def generation_sha256(self) -> str | None:
        return self._state.sha256 if self._state else None

    @property
    def built(self) -> bool:
        return self._state is not None

    def snapshot(self) -> SecondBrainIndex:
        with self._lock:
            view = copy.copy(self)
            view._read_only = True
            return view

    def reload(self, path: Path | None = None, *, expected_sha256: str | None = None) -> bool:
        if self._read_only:
            raise CorpusIntegrityError("captured generation cannot be reloaded")
        with self._lock:
            serial = self._serial
            candidate_path = self.path if path is None else Path(path)
        try:
            corpus = load_corpus(candidate_path, expected_sha256)
            rows, frequencies = [], Counter()
            for row in corpus.rows:
                tokens = tuple(tokenize(row.title + " " + row.text))
                rows.append(MappingProxyType({
                    "id": row.node_id, "title": row.title, "source": row.source,
                    "sourceId": row.source_id, "sha256": row.sha256,
                    "_toks": tokens, "_tf": MappingProxyType(dict(Counter(tokens))),
                }))
                frequencies.update(set(tokens))
            staged = _Generation(tuple(rows), MappingProxyType(dict(frequencies)), corpus.file_sha256)
        except (OSError, CorpusIntegrityError) as exc:
            with self._lock:
                if self._serial == serial:
                    self.last_reload_error = type(exc).__name__
                    if self._state is None:
                        self.load_error = self.last_reload_error
            return False
        with self._lock:
            if self._serial != serial:
                raise CorpusIntegrityError("concurrent generation change; retry admission")
            self._state, self.path = staged, candidate_path
            self._serial += 1
            self.load_error = self.last_reload_error = None
        return True

    def handle(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {"nodeId": row["id"], "nodeKind": "INDEX", "label": "DECLARED",
                "note": (row.get("title") or "")[:160], "source": row.get("source"),
                "sha256": row.get("sha256")}

    def model_handle(self, row: Mapping[str, Any]) -> dict[str, Any]:
        handle = self.handle(row)
        return {key: handle[key] for key in ("nodeId", "nodeKind", "label", "note")}

    def search(self, query: str, k: int = 6) -> dict[str, Any]:
        return self.search_candidates(query, limit=bounded_int(k, 12))

    def search_candidates(self, query: str, *, limit: int = 24) -> dict[str, Any]:
        """Internal recall pool; NOT another public route or final-result limit."""
        bounded_int(limit, 128)
        if not isinstance(query, str) or len(query) > 2000:
            raise ValueError("query must be a bounded string")
        state = self._state  # one immutable generation throughout this operation
        base = {"schema": SCHEMA_RETRIEVE, "query": query, "kind": "SOFTWARE",
                "content_access": "HANDLES_ONLY", "index_is_model_weights": False,
                "raw_graph_nodes_admitted_to_gradients": 0,
                "corpus_n": len(state.rows) if state else 0,
                "generation_sha256": state.sha256 if state else None}
        if state is None:
            return {**base, "ready": False, "handles": [], "scores": [], "k": 0,
                    "honesty": "Index UNAVAILABLE. No retrieval fabricated; private graph not substituted."}
        qset = Counter(tokenize(query))
        scored = []
        for row in state.rows:
            score = 0.0
            for term, query_frequency in qset.items():
                tf = row["_tf"].get(term, 0)
                if tf:
                    idf = math.log((len(state.rows) + 1) / (1 + state.df.get(term, 0))) + 1.0
                    score += (tf / (tf + 1.2)) * idf * query_frequency
            if score > 0:
                scored.append((score, row))
        # Preserve the v1 stable corpus-order tie break and BM25-like score.
        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:limit]
        return {**base, "k": len(top), "handles": [self.handle(row) for _, row in top],
                "scores": [round(score, 4) for score, _ in top], "ready": bool(top),
                "honesty": "Lexical rank over the admitted public projection. Score is overlap, never correctness. Content stays in the controller."}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            state, error, rejected, path = self._state, self.load_error, self.last_reload_error, self.path
        by = dict(Counter(row["source"] for row in state.rows)) if state else {}
        return {"schema": SCHEMA_INDEX, "chunk_count": len(state.rows) if state else 0,
                "public_chunk_count_declared": PUBLIC_CHUNK_COUNT, "by_source": by,
                "path": str(path), "built": state is not None, "load_error": error,
                "last_reload_error": rejected,
                "generation_sha256": state.sha256 if state else None,
                "admission_state": "ACTIVE_PREVIOUS_RELOAD_REJECTED" if state and rejected else "ACTIVE" if state else "UNAVAILABLE",
                "index_is_model_weights": False, "raw_graph_nodes_observed_private": PRIVATE_GRAPH_NODES,
                "raw_graph_nodes_admitted_to_gradients": 0, "kind": "SOFTWARE",
                "honesty": "Public projection only. Private 9464-node graph is not here. Index is DATA, never weights."}

    def rag_status(self) -> dict[str, Any]:
        st = self.stats()
        ready, count = st["built"], st["chunk_count"]
        return {"built": ready, "state": "PUBLIC_PROJECTION_LOADED" if ready else "UNAVAILABLE",
                "document_count": count, "files": count, "chunk_count": count, "chunks": count,
                "corpus_chunk_count": count, "brain_handle_count": count,
                "brain_handle_plane": {"kind": "PUBLIC_JSONL_HANDLES", "count": count,
                                       "private_graph_nodes": 0, "gradient_authority_rows": 0, "training_authority": "NONE"},
                "training_authority_rows": 0, "node_count": count, "edge_count": 0,
                "mode": "SOFTWARE_BM25", "kind": "SOFTWARE",
                "integrity_state": "PUBLIC_PROJECTION_LOADED" if ready else "UNAVAILABLE",
                "rehydration_state": "IN_PROCESS" if ready else "UNAVAILABLE",
                "corpus": {"path": st["path"], "public": True, "private_graph_nodes": 0,
                           "declared_public_chunks": PUBLIC_CHUNK_COUNT},
                "index_is_model_weights": False, "raw_graph_nodes_admitted_to_gradients": 0,
                "by_source": st["by_source"], "load_error": st["load_error"], "honesty": st["honesty"],
                "generation_sha256": st["generation_sha256"], "admission_state": st["admission_state"],
                "last_reload_error": st["last_reload_error"]}

    def navigator_context(self, query: str, k: int = 6) -> dict[str, Any]:
        hit = self.search(query, k=k)
        handles = hit.get("handles") or []
        model_handles = [{key: h[key] for key in ("nodeId", "nodeKind", "label", "note")} for h in handles]
        evidence = [{"node_id": h["nodeId"], "sha256": h["sha256"], "source": h["source"]} for h in handles]
        ready = bool(hit.get("ready") and model_handles)
        return {"schema": SCHEMA_NAV, "state": "GROUNDED_HANDLES_READY" if ready else "ABSTAIN_NO_GROUNDED_HANDLES",
                "ready": ready, "content_access": "HANDLES_ONLY", "query": query,
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(), "handles": model_handles,
                "evidence": evidence, "evidence_set_sha256": canonical_sha256(evidence),
                "handles_sha256": canonical_sha256(model_handles),
                "handle_evidence_set_equivalent": len(model_handles) == len(evidence),
                "grounded_count": len(model_handles), "corpus_n": hit["corpus_n"], "kind": "SOFTWARE",
                "index_is_model_weights": False, "raw_graph_nodes_admitted_to_gradients": 0,
                "generation_sha256": hit["generation_sha256"], "honesty": hit["honesty"]}


_INDEX: SecondBrainIndex | None = None


def index() -> SecondBrainIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = SecondBrainIndex()
    return _INDEX


def reset_index() -> None:
    global _INDEX
    _INDEX = None


def retrieve(query: str, k: int = 6) -> dict[str, Any]:
    return index().search(query, k=k)


def rag_status() -> dict[str, Any]:
    return index().rag_status()


def navigator_context(query: str, k: int = 6) -> dict[str, Any]:
    return index().navigator_context(query, k=k)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    q = " ".join(args).strip() or "Lambda uniqueness conjecture 1"
    hit = retrieve(q, k=6)
    print(json.dumps(hit, indent=2, ensure_ascii=False))
    return 0 if hit.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
