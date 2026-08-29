"""SOFTWARE retrieval over the public second-brain projection.

575 in-repo chunks. BM25-like lexical rank. NEVER correctness.
Handles only — content stays in the controller.
The private 9464-node graph is not here and never enters gradients.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

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
    return [
        t.lower()
        for t in TOKEN.findall(text or "")
        if len(t) > 1 and t.lower() not in STOP
    ]


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def corpus_path(path: Path | None = None) -> Path:
    env = (os.environ.get("SECOND_BRAIN_CORPUS") or os.environ.get("AYLLU_BRAIN_CORPUS") or "").strip()
    if path is not None:
        return Path(path)
    if env:
        return Path(env)
    return CORPUS


class SecondBrainIndex:
    def __init__(self, path: Path | None = None) -> None:
        self.rows: list[dict[str, Any]] = []
        self.df: Counter[str] = Counter()
        self.path = corpus_path(path)
        self.load_error: str | None = None
        self._load()
        self.n = len(self.rows)

    def _load(self) -> None:
        if not self.path.is_file():
            self.load_error = f"public corpus missing at {self.path}"
            return
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            self.load_error = f"public corpus unreadable ({type(exc).__name__})"
            return
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not row.get("id"):
                continue
            text = f"{row.get('title', '')} {row.get('text', '')}"
            toks = tokenize(text)
            digest = row.get("sha256")
            if not (isinstance(digest, str) and len(digest) == 64):
                digest = hashlib.sha256((row.get("text") or "").encode("utf-8")).hexdigest()
            self.rows.append({
                "id": str(row["id"]),
                "title": str(row.get("title") or ""),
                "source": str(row.get("source") or "unknown"),
                "sourceId": row.get("sourceId"),
                "sha256": digest,
                "_toks": toks,
                "_tf": Counter(toks),
            })
            self.df.update(set(toks))

    @property
    def built(self) -> bool:
        return self.load_error is None and self.n > 0

    def handle(self, row: dict[str, Any]) -> dict[str, Any]:
        """Controller handle. No node text. Never a private-graph row."""
        return {
            "nodeId": row["id"],
            "nodeKind": "INDEX",
            "label": "DECLARED",
            "note": (row.get("title") or "")[:160],
            "source": row.get("source"),
            "sha256": row.get("sha256"),
        }

    def model_handle(self, row: dict[str, Any]) -> dict[str, Any]:
        """Khipu candidate offered to the model. HANDLES_ONLY four-field shape."""
        return {
            "nodeId": row["id"],
            "nodeKind": "INDEX",
            "label": "DECLARED",
            "note": (row.get("title") or "")[:160],
        }

    def search(self, query: str, k: int = 6) -> dict[str, Any]:
        if not self.built:
            return {
                "schema": SCHEMA_RETRIEVE,
                "query": query,
                "handles": [],
                "ready": False,
                "kind": "SOFTWARE",
                "content_access": "HANDLES_ONLY",
                "corpus_n": 0,
                "honesty": (
                    f"Index UNAVAILABLE ({self.load_error or 'empty'}). "
                    "No LIVE retrieval fabricated. Private 9464-node graph is not here."
                ),
            }
        q = tokenize(query)
        if not q:
            return {
                "schema": SCHEMA_RETRIEVE,
                "query": query,
                "handles": [],
                "ready": False,
                "kind": "SOFTWARE",
                "content_access": "HANDLES_ONLY",
                "corpus_n": self.n,
                "honesty": "empty query — no ranking fabricated",
            }
        scored: list[tuple[float, dict[str, Any]]] = []
        qset = Counter(q)
        idf_n = max(1, self.n)
        for row in self.rows:
            score = 0.0
            for term, qf in qset.items():
                tf = row["_tf"].get(term, 0)
                if not tf:
                    continue
                idf = math.log((idf_n + 1) / (1 + self.df.get(term, 0))) + 1.0
                score += (tf / (tf + 1.2)) * idf * qf
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: max(1, min(int(k), 12))]
        handles = [self.handle(r) for _, r in top]
        return {
            "schema": SCHEMA_RETRIEVE,
            "query": query,
            "k": len(handles),
            "handles": handles,
            "scores": [round(s, 4) for s, _ in top],
            "corpus_n": self.n,
            "ready": bool(handles),
            "kind": "SOFTWARE",
            "content_access": "HANDLES_ONLY",
            "index_is_model_weights": False,
            "raw_graph_nodes_admitted_to_gradients": 0,
            "honesty": (
                "Lexical rank over the PUBLIC in-repo projection (575 chunks). "
                "Score is overlap, never correctness. Content stays in the controller. "
                "Not LIVE retrieval. Private 9464-node graph is not here."
            ),
        }

    def stats(self) -> dict[str, Any]:
        by: dict[str, int] = {}
        for r in self.rows:
            src = str(r.get("source") or "unknown")
            by[src] = by.get(src, 0) + 1
        return {
            "schema": SCHEMA_INDEX,
            "chunk_count": self.n,
            "public_chunk_count_declared": PUBLIC_CHUNK_COUNT,
            "by_source": by,
            "path": str(self.path),
            "built": self.built,
            "load_error": self.load_error,
            "index_is_model_weights": False,
            "raw_graph_nodes_observed_private": PRIVATE_GRAPH_NODES,
            "raw_graph_nodes_admitted_to_gradients": 0,
            "kind": "SOFTWARE",
            "honesty": (
                "Public projection only. Private 9464-node graph is not here. "
                "Index is DATA, never weights."
            ),
        }

    def rag_status(self) -> dict[str, Any]:
        st = self.stats()
        return {
            "built": self.built,
            "state": "PUBLIC_PROJECTION_LOADED" if self.built else "UNAVAILABLE",
            "document_count": self.n,
            "files": self.n,
            "chunk_count": self.n,
            "chunks": self.n,
            "corpus_chunk_count": self.n,
            "brain_handle_count": self.n if self.built else 0,
            "brain_handle_plane": {
                "kind": "PUBLIC_JSONL_HANDLES",
                "count": self.n if self.built else 0,
                "private_graph_nodes": 0,
                "gradient_authority_rows": 0,
                "training_authority": "NONE",
            },
            "training_authority_rows": 0,
            "node_count": self.n if self.built else 0,
            "edge_count": 0,
            "mode": "SOFTWARE_BM25",
            "kind": "SOFTWARE",
            "integrity_state": "PUBLIC_PROJECTION_LOADED" if self.built else "UNAVAILABLE",
            "rehydration_state": "IN_PROCESS" if self.built else "UNAVAILABLE",
            "corpus": {
                "path": str(self.path),
                "public": True,
                "private_graph_nodes": 0,
                "declared_public_chunks": PUBLIC_CHUNK_COUNT,
            },
            "index_is_model_weights": False,
            "raw_graph_nodes_admitted_to_gradients": 0,
            "by_source": st["by_source"],
            "load_error": self.load_error,
            "honesty": st["honesty"],
        }

    def navigator_context(self, query: str, k: int = 6) -> dict[str, Any]:
        hit = self.search(query, k=k)
        handles = hit.get("handles") or []
        model_handles = [
            {key: h[key] for key in ("nodeId", "nodeKind", "label", "note") if key in h}
            for h in handles
            if isinstance(h, dict) and h.get("nodeId")
        ]
        evidence = [
            {
                "node_id": h.get("nodeId"),
                "sha256": h.get("sha256"),
                "source": h.get("source"),
            }
            for h in handles
            if isinstance(h, dict)
        ]
        ready = bool(hit.get("ready") and model_handles)
        handles_sha = canonical_sha256(model_handles)
        evidence_sha = canonical_sha256(evidence)
        return {
            "schema": SCHEMA_NAV,
            "state": "GROUNDED_HANDLES_READY" if ready else "ABSTAIN_NO_GROUNDED_HANDLES",
            "ready": ready,
            "content_access": "HANDLES_ONLY",
            "query": query,
            "query_sha256": hashlib.sha256((query or "").encode("utf-8")).hexdigest(),
            "handles": model_handles,
            "evidence": evidence,
            "evidence_set_sha256": evidence_sha,
            "handles_sha256": handles_sha,
            "handle_evidence_set_equivalent": len(model_handles) == len(evidence),
            "grounded_count": len(model_handles),
            "corpus_n": hit.get("corpus_n", self.n),
            "kind": "SOFTWARE",
            "index_is_model_weights": False,
            "raw_graph_nodes_admitted_to_gradients": 0,
            "honesty": hit.get("honesty"),
        }


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
