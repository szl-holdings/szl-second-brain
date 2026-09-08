# SPDX-License-Identifier: Apache-2.0
"""Opt-in native NeoMME providers for the existing public Brain coordinator.

This lane accepts ONLY the exact packaged public corpus; it is not private
memory, release authorization, model training, or a new service. Forge owns
worker/image qualification. There is no network/download path in this module.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import math
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from second_brain.corpus import CorpusIntegrityError, load_corpus, strict_json
from second_brain.hybrid import HybridSecondBrain, RetrievalBoundaryError
from second_brain.embedding_cache import EmbeddingCache
from second_brain.retrieve import CORPUS, SecondBrainIndex, bounded_int

PUBLIC_CORPUS_SHA256 = "387337acbd8fe443637102fe7ea75387fa4c3d9d746d8ab6e2d14d6c138aad8f"
LOCK_PATH = CORPUS.parent / "neomme-260m.lock.json"
SCHEMA = "szl.neomme.public-index/v1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True).encode()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class NeoMME:
    """Native CPU model with verified, fully local checkpoint bytes."""
    def __init__(self, directory: Path, *, max_tokens: int = 4096) -> None:
        bounded_int(max_tokens, 16384)
        self.max_tokens, self._lock = max_tokens, RLock()
        lock = strict_json(LOCK_PATH.read_bytes())
        if directory.is_symlink() or not directory.is_dir():
            raise CorpusIntegrityError("materialized model directory required")
        expected = {item["path"] for item in lock["files"]}
        actual = set()
        for file in directory.rglob("*"):
            if file.is_symlink():
                raise CorpusIntegrityError("model artifact symlinks not admitted")
            if file.is_file():
                actual.add(file.relative_to(directory).as_posix())
        if actual != expected:
            raise CorpusIntegrityError("model inventory differs from the admitted lock")
        for item in lock["files"]:
            file = directory / item["path"]
            if file.stat().st_size != item["bytes"] or file_sha256(file) != item["sha256"]:
                raise CorpusIntegrityError("model artifact digest mismatch")
        config = strict_json((directory / "config.json").read_bytes())
        if config.get("auto_map") or config.get("model_type") != "neomme":
            raise CorpusIntegrityError("unexpected model architecture or custom loader")
        direct = strict_json(metadata.distribution("transformers").read_text("direct_url.json") or "{}")
        if direct.get("vcs_info", {}).get("commit_id") != lock["transformers_source_revision"]:
            raise CorpusIntegrityError("Transformers source mismatch")
        import torch
        from transformers import NeoMMEForRetrieval, NeoMMEProcessor
        self.torch = torch
        self.processor = NeoMMEProcessor.from_pretrained(str(directory), local_files_only=True, trust_remote_code=False)
        model, info = NeoMMEForRetrieval.from_pretrained(str(directory), local_files_only=True,
            trust_remote_code=False, use_safetensors=True, dtype=torch.float32, output_loading_info=True)
        if any(info.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
            raise CorpusIntegrityError("inexact retrieval architecture load")
        self.model = model.to("cpu").eval()
        self.identity = {"model_id": lock["repository_id"], "model_revision": lock["revision"],
                         "model_lock_sha256": hashlib.sha256(canonical(lock)).hexdigest(),
                         "transformers_revision": lock["transformers_source_revision"],
                         "torch_version": torch.__version__, "dtype": "float32", "device": "cpu",
                         "max_tokens": max_tokens, "normalization": "l2", "runtime_qualification": "NOT_IMPLIED"}

    def encode(self, text: str, task: str):
        if task not in {"query", "document"} or not isinstance(text, str) or not text.strip() or len(text) > 128000:
            raise RetrievalBoundaryError("invalid encoding input")
        with self._lock, self.torch.inference_mode():
            inputs = self.processor.apply_chat_template([[{"role": "user", "content": text}]],
                task=task, tokenize=True, return_dict=True, return_tensors="pt",
                processor_kwargs={"padding": "longest"})
            if inputs["input_ids"].shape[-1] > self.max_tokens:
                raise RetrievalBoundaryError("input exceeds measured token budget; no silent truncation")
            outputs = self.model(**inputs)
            dense = outputs.dense_embeddings[0].float()
            tokens = outputs.embeddings[0][inputs["attention_mask"][0].bool()].float()
            if (dense.shape != (1024,) or tokens.ndim != 2 or tokens.shape[0] == 0
                    or not self.torch.isfinite(dense).all() or not self.torch.isfinite(tokens).all()
                    or float(dense.norm()) == 0):
                raise RetrievalBoundaryError("invalid native embedding")
            return (self.torch.nn.functional.normalize(dense, dim=-1).tolist(),
                    self.torch.nn.functional.normalize(tokens, dim=-1))


class PublicNeuralBrain:
    """Shared pinned public index + body-aware reranker. Call build/load explicitly.

    Persisted index digest is supplied by the controller, not read as its own
    authority from the index. Reload never mixes different corpus generations.
    No private path or private content admission is provided by this class.
    """
    def __init__(self, encoder: NeoMME, *, token_cache_bytes: int = 256 * 1024 * 1024) -> None:
        self.corpus = load_corpus(CORPUS, PUBLIC_CORPUS_SHA256)
        self.sparse = SecondBrainIndex(CORPUS, expected_sha256=PUBLIC_CORPUS_SHA256).snapshot()
        if not self.sparse.built:
            raise CorpusIntegrityError("public sparse generation unavailable")
        self.encoder = encoder
        self._encoder_identity = canonical(encoder.identity)
        self._token_cache = EmbeddingCache(token_cache_bytes)
        self.generation_sha256 = self.corpus.file_sha256
        self._rows = {row.node_id: row for row in self.corpus.rows}
        self._vectors: tuple[tuple[float, ...], ...] | None = None
        self.index_sha256: str | None = None

    def _check_encoder(self):
        if canonical(self.encoder.identity) != self._encoder_identity:
            raise CorpusIntegrityError("encoder identity changed; rebuild a separately admitted generation")

    @property
    def binding(self):
        self._check_encoder()
        return {"encoder": json.loads(self._encoder_identity), "index_sha256": self.index_sha256,
                "corpus_sha256": self.generation_sha256, "scope": "EXACT_PACKAGED_PUBLIC_CORPUS_ONLY",
                "body_cache_budget_bytes": self._token_cache.max_bytes}

    def _payload(self, vectors):
        self._check_encoder()
        return {"schema": SCHEMA, "corpus_sha256": self.generation_sha256,
                "encoder": json.loads(self._encoder_identity), "node_ids": list(self._rows), "vectors": vectors}

    def _cache_key(self, row):
        self._check_encoder()
        return (self.generation_sha256, hashlib.sha256(self._encoder_identity).hexdigest(),
                row.node_id, row.sha256, hashlib.sha256(row.title.encode()).hexdigest())

    def _remember(self, row, tokens):
        if tokens is not None:
            self._token_cache.put(self._cache_key(row), tokens,
                                  byte_size=tokens.numel() * tokens.element_size())

    def _document_tokens(self, row):
        tokens = self._token_cache.get(self._cache_key(row))
        if tokens is None:
            _, tokens = self.encoder.encode(row.title + "\n" + row.text, "document")
            if tokens is None:
                raise RetrievalBoundaryError("document token embeddings missing")
            self._remember(row, tokens)
        return tokens

    def cache_stats(self):
        return self._token_cache.stats()

    def build(self, destination: Path, *, progress: Callable[[int, int], None] | None = None) -> str:
        vectors = []
        for position, row in enumerate(self.corpus.rows, 1):
            dense, tokens = self.encoder.encode(row.title + "\n" + row.text, "document")
            vectors.append(dense)
            self._remember(row, tokens)
            if progress is not None:
                progress(position, len(self.corpus.rows))
        self._validate_vectors(vectors)
        raw = canonical(self._payload(vectors)) + b"\n"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return self.load(destination, expected_sha256=hashlib.sha256(raw).hexdigest())

    def load(self, path: Path, *, expected_sha256: str) -> str:
        with path.open("rb") as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise CorpusIntegrityError("persisted index digest mismatch")
        payload = strict_json(raw)
        vectors = payload.get("vectors") if isinstance(payload, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(self._rows) or payload != self._payload(vectors):
            raise CorpusIntegrityError("index corpus, row order, schema or encoder identity mismatch")
        self._validate_vectors(vectors)
        self._vectors = tuple(tuple(v) for v in vectors)
        self.index_sha256 = expected_sha256
        return expected_sha256

    def _validate_vectors(self, vectors):
        if not isinstance(vectors, list) or len(vectors) != len(self._rows):
            raise CorpusIntegrityError("incomplete vector generation")
        for vector in vectors:
            if (not isinstance(vector, list) or len(vector) != 1024
                    or any(type(v) not in (float, int) or not math.isfinite(v) for v in vector)
                    or not math.isclose(math.hypot(*vector), 1.0, rel_tol=1e-5)):
                raise CorpusIntegrityError("invalid stored vector")

    def __call__(self, query: str, k: int):
        bounded_int(k, 128)
        if self._vectors is None:
            raise RetrievalBoundaryError("neural index has not been built or loaded")
        vectors = self._vectors
        self._check_encoder()
        dense, _ = self.encoder.encode(query, "query")
        self._check_encoder()
        if self._vectors is not vectors:
            raise RetrievalBoundaryError("neural index changed during the query")
        scored = [(sum(a * b for a, b in zip(dense, vector)), row)
                  for row, vector in zip(self.corpus.rows, vectors)]
        scored.sort(key=lambda pair: (-pair[0], pair[1].node_id))
        return [{"node_id": row.node_id, "score": score, "source": row.source, "sha256": row.sha256}
                for score, row in scored[:k]]

    def rerank(self, query: str, candidates, k: int):
        bounded_int(k, 128)
        if not candidates or len(candidates) > k:
            raise RetrievalBoundaryError("invalid rerank candidate budget")
        _, query_tokens = self.encoder.encode(query, "query")
        scored = []
        for candidate in candidates:
            row = self._rows.get(candidate.get("node_id"))
            if row is None or candidate.get("sha256") != row.sha256 or candidate.get("source") != row.source:
                raise RetrievalBoundaryError("body hydration identity mismatch")
            document_tokens = self._document_tokens(row)
            score = float((query_tokens @ document_tokens.T).max(dim=1).values.mean())
            if not math.isfinite(score):
                raise RetrievalBoundaryError("non-finite late-interaction score")
            scored.append((score, row.node_id))
        return [node_id for _, node_id in sorted(scored, key=lambda pair: (-pair[0], pair[1]))]

    def coordinator(self, *, rerank: bool = True) -> HybridSecondBrain:
        if self._vectors is None:
            raise RetrievalBoundaryError("neural index has not been built or loaded")
        return HybridSecondBrain(self.sparse, dense_provider=self, reranker=self.rerank if rerank else None,
                                 allow_sparse_fallback=False, allow_reranker_fallback=False)
