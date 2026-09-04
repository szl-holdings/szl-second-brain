"""Review-gated continuous frontier memory for SZL Second Brain.

The committed candidate corpus contains only bounded public-source material. Public
functions return handles and digests; raw candidate content is available only through
an explicitly authorized controller hydrator. Discovery never promotes candidates,
trains weights, executes tools, or mutates a production system.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.:/+-]{1,63}")
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

FRONTIER_STATE_SCHEMA = "szl.second-brain.frontier-state/v1"
FRONTIER_CANDIDATE_SCHEMA = "szl.second-brain.frontier-candidate/v1"
FRONTIER_HANDLE_SCHEMA = "szl.second-brain.frontier-handle/v1"
FRONTIER_POLICY_REVISION = "sha256:" + hashlib.sha256(
    json.dumps(
        {
            "schema": "szl.second-brain.frontier-policy/v1",
            "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
            "public_content_access": "HANDLES_ONLY",
            "controller_content_access": "AUTHORIZED_CONTROLLER_ONLY",
            "training_authority": "NONE",
            "promotion_authority": "NONE",
            "execution_authority": "NONE",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


class FrontierBoundaryError(RuntimeError):
    """Raised when a caller crosses the review or content boundary."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _tokenize(value: str) -> list[str]:
    return _TOKEN_RE.findall(value.lower())


@dataclass(frozen=True)
class FrontierCandidate:
    candidate_id: str
    title: str
    content: str
    content_sha256: str
    source_repository: str
    source_revision: str
    source_path: str
    source_kind: str
    quant_domain: str | None
    admission: str

    def handle(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": FRONTIER_HANDLE_SCHEMA,
            "nodeId": self.candidate_id,
            "title": self.title,
            "sha256": self.content_sha256,
            "repository": self.source_repository,
            "revision": self.source_revision,
            "path": self.source_path,
            "kind": self.source_kind,
            "admission": self.admission,
            "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
            "contentAccess": "HANDLES_ONLY",
        }
        if self.quant_domain:
            payload["quantDomain"] = self.quant_domain
        return payload


class FrontierIndex:
    """Immutable review-candidate index loaded from package data."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._load_error: str | None = None
        self._state: dict[str, Any] = {}
        self._candidates: tuple[FrontierCandidate, ...] = ()
        self._by_id: dict[str, FrontierCandidate] = {}
        self._term_frequencies: tuple[Counter[str], ...] = ()
        self._document_frequency: Counter[str] = Counter()

    def _load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                package = files("data")
                state = json.loads(
                    package.joinpath("frontier-state.v1.json").read_text(
                        encoding="utf-8"
                    )
                )
                rows = [
                    json.loads(line)
                    for line in package.joinpath(
                        "frontier-candidates.public.jsonl"
                    ).read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                self._validate(state, rows)
                candidates = tuple(
                    FrontierCandidate(
                        candidate_id=str(row["id"]),
                        title=str(row["title"]),
                        content=str(row["content"]),
                        content_sha256=str(row["content_sha256"]),
                        source_repository=str(row["source_repository"]),
                        source_revision=str(row["source_revision"]),
                        source_path=str(row["source_path"]),
                        source_kind=str(row["source_kind"]),
                        quant_domain=(
                            str(row["quant_domain"])
                            if row.get("quant_domain")
                            else None
                        ),
                        admission=str(row["admission"]),
                    )
                    for row in rows
                )
                frequencies: list[Counter[str]] = []
                document_frequency: Counter[str] = Counter()
                for candidate in candidates:
                    terms = _tokenize(
                        " ".join(
                            (
                                candidate.title,
                                candidate.source_repository,
                                candidate.source_path,
                                candidate.source_kind,
                                candidate.quant_domain or "",
                                candidate.content,
                            )
                        )
                    )
                    frequency = Counter(terms)
                    frequencies.append(frequency)
                    document_frequency.update(frequency.keys())
                self._state = state
                self._candidates = candidates
                self._by_id = {row.candidate_id: row for row in candidates}
                self._term_frequencies = tuple(frequencies)
                self._document_frequency = document_frequency
            except Exception as exc:  # fail closed with type-only public detail
                self._load_error = type(exc).__name__
            self._loaded = True

    @staticmethod
    def _validate(state: Any, rows: list[Any]) -> None:
        if not isinstance(state, dict) or state.get("schema") != FRONTIER_STATE_SCHEMA:
            raise ValueError("unsupported frontier state")
        if state.get("state") != "REVIEW_REQUIRED":
            raise ValueError("frontier state must remain review-required")
        if state.get("public_content_access") != "HANDLES_ONLY":
            raise ValueError("public frontier access must remain handles-only")
        if state.get("training_authority") != "NONE":
            raise ValueError("frontier state must not grant training authority")
        if state.get("promotion_authority") != "NONE":
            raise ValueError("frontier state must not grant promotion authority")
        if state.get("execution_authority") != "NONE":
            raise ValueError("frontier state must not grant execution authority")
        if int(state.get("candidate_count") or -1) != len(rows):
            raise ValueError("frontier candidate count mismatch")

        seen: set[str] = set()
        canonical_lines: list[bytes] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("schema") != FRONTIER_CANDIDATE_SCHEMA:
                raise ValueError("invalid frontier candidate schema")
            required = {
                "id",
                "title",
                "content",
                "content_sha256",
                "source_repository",
                "source_revision",
                "source_path",
                "source_kind",
                "admission",
                "candidate_state",
                "content_access",
            }
            if required - set(row):
                raise ValueError("frontier candidate fields are incomplete")
            candidate_id = str(row["id"])
            if candidate_id in seen:
                raise ValueError("duplicate frontier candidate id")
            seen.add(candidate_id)
            if not _HEX_40.fullmatch(str(row["source_revision"])):
                raise ValueError("frontier source revision is not exact")
            content = str(row["content"])
            measured = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if measured != row["content_sha256"] or not _HEX_64.fullmatch(measured):
                raise ValueError("frontier candidate content digest mismatch")
            if row["candidate_state"] != "DISCOVERED_REVIEW_REQUIRED":
                raise ValueError("frontier candidate was promoted")
            if row["content_access"] != "CONTROLLER_ONLY":
                raise ValueError("frontier candidate content boundary drifted")
            canonical_lines.append(_canonical_bytes(row) + b"\n")

        measured_set = hashlib.sha256(b"".join(canonical_lines)).hexdigest()
        if state.get("candidate_set_sha256") != measured_set:
            raise ValueError("frontier candidate-set digest mismatch")
        sources = state.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("frontier source receipts are missing")
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("invalid frontier source receipt")
            if not _HEX_40.fullmatch(str(source.get("revision") or "")):
                raise ValueError("frontier source receipt revision is not exact")
            if not _HEX_64.fullmatch(str(source.get("content_sha256") or "")):
                raise ValueError("frontier source receipt digest is malformed")

    @property
    def ready(self) -> bool:
        self._load()
        return self._load_error is None and bool(self._candidates)

    @property
    def load_error(self) -> str | None:
        self._load()
        return self._load_error

    def status(self) -> dict[str, Any]:
        self._load()
        if not self.ready:
            return {
                "schema": FRONTIER_STATE_SCHEMA,
                "state": "UNAVAILABLE",
                "ready": False,
                "load_error": self._load_error,
                "public_content_access": "HANDLES_ONLY",
                "controller_content_access": "AUTHORIZED_CONTROLLER_ONLY",
                "training_authority": "NONE",
                "promotion_authority": "NONE",
                "execution_authority": "NONE",
                "private_graph_present": False,
            }
        return {
            **self._state,
            "ready": True,
            "private_graph_present": False,
            "raw_graph_nodes_admitted_to_gradients": 0,
            "lambda": "CONJECTURE_1",
        }

    def search(self, query: str, *, k: int = 12) -> dict[str, Any]:
        self._load()
        if not self.ready:
            return {
                "schema": "szl.second-brain.frontier-search/v1",
                "state": "UNAVAILABLE",
                "ready": False,
                "content_access": "HANDLES_ONLY",
                "handles": [],
                "scores": [],
                "reason": self._load_error,
            }
        terms = _tokenize(query)
        if not terms:
            raise FrontierBoundaryError("query must contain searchable terms")
        limit = max(1, min(int(k), 24))
        n_documents = len(self._candidates)
        scored: list[tuple[float, int]] = []
        for index, frequency in enumerate(self._term_frequencies):
            length = max(1, sum(frequency.values()))
            score = 0.0
            for term in terms:
                tf = frequency.get(term, 0)
                if not tf:
                    continue
                df = self._document_frequency.get(term, 0)
                inverse = math.log(1.0 + (n_documents - df + 0.5) / (df + 0.5))
                score += inverse * ((tf * 2.2) / (tf + 1.2 + 0.75 * length / 180.0))
            if score > 0:
                scored.append((round(score, 8), index))
        scored.sort(key=lambda item: (-item[0], self._candidates[item[1]].candidate_id))
        selected = scored[:limit]
        handles = [self._candidates[index].handle() for _score, index in selected]
        evidence_digest = hashlib.sha256(_canonical_bytes(handles)).hexdigest()
        return {
            "schema": "szl.second-brain.frontier-search/v1",
            "state": "REVIEW_REQUIRED",
            "ready": True,
            "content_access": "HANDLES_ONLY",
            "candidate_count": len(self._candidates),
            "handles": handles,
            "scores": [score for score, _index in selected],
            "evidence_set_sha256": evidence_digest,
            "ranking": "LEXICAL_RELEVANCE_NOT_CORRECTNESS",
            "training_authority": "NONE",
            "promotion_authority": "NONE",
            "execution_authority": "NONE",
        }

    def candidate(self, candidate_id: str) -> FrontierCandidate:
        self._load()
        if not self.ready:
            raise FrontierBoundaryError("frontier index is unavailable")
        try:
            return self._by_id[candidate_id]
        except KeyError as exc:
            raise FrontierBoundaryError("unknown frontier candidate") from exc


Authorizer = Callable[[str, str, str, str, str], bool]


class AuthorizedFrontierHydrator:
    """Resolve frontier content only after an external controller authorization."""

    def __init__(self, authorizer: Authorizer, *, index: FrontierIndex | None = None) -> None:
        self._authorizer = authorizer
        self._index = index or frontier_index()

    def hydrate(
        self,
        handles: Sequence[Mapping[str, Any]],
        *,
        principal_id: str,
        tenant_id: str,
        policy_revision: str,
    ) -> dict[str, Any]:
        if not principal_id or not tenant_id or not policy_revision:
            raise FrontierBoundaryError("controller identity and policy are required")
        documents: list[dict[str, Any]] = []
        public_handles: list[dict[str, Any]] = []
        for handle in handles:
            candidate_id = str(handle.get("nodeId") or "")
            candidate = self._index.candidate(candidate_id)
            if handle.get("sha256") != candidate.content_sha256:
                raise FrontierBoundaryError("frontier handle digest mismatch")
            allowed = self._authorizer(
                principal_id,
                tenant_id,
                policy_revision,
                candidate.candidate_id,
                candidate.source_repository,
            )
            if allowed is not True:
                raise FrontierBoundaryError("frontier hydration was not authorized")
            public_handles.append(candidate.handle())
            documents.append(
                {
                    "node_id": candidate.candidate_id,
                    "title": candidate.title,
                    "source_repository": candidate.source_repository,
                    "source_revision": candidate.source_revision,
                    "source_path": candidate.source_path,
                    "sha256": candidate.content_sha256,
                    "content": candidate.content,
                    "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
                    "authority": "NONE",
                }
            )
        return {
            "schema": "szl.second-brain.frontier-hydration/v1",
            "state": "AUTHORIZED_REVIEW_CONTENT_READY",
            "content_access": "CONTROLLER_ONLY",
            "policy_revision": policy_revision,
            "handles": public_handles,
            "documents": documents,
            "evidence_set_sha256": hashlib.sha256(
                _canonical_bytes(public_handles)
            ).hexdigest(),
            "training_authority": "NONE",
            "promotion_authority": "NONE",
            "execution_authority": "NONE",
            "raw_graph_nodes_admitted_to_gradients": 0,
        }


_INDEX: FrontierIndex | None = None
_INDEX_LOCK = threading.Lock()


def frontier_index() -> FrontierIndex:
    global _INDEX
    if _INDEX is None:
        with _INDEX_LOCK:
            if _INDEX is None:
                _INDEX = FrontierIndex()
    return _INDEX


def frontier_status() -> dict[str, Any]:
    return frontier_index().status()


def frontier_search(query: str, *, k: int = 12) -> dict[str, Any]:
    return frontier_index().search(query, k=k)


def anatomy_feed(*, k: int = 24) -> dict[str, Any]:
    payload = frontier_search(
        "second brain living anatomy ouroboros loop formula quant inference evidence",
        k=k,
    )
    payload["schema"] = "szl.second-brain.anatomy-feed/v1"
    payload["purpose"] = "READ_ONLY_LIVING_ANATOMY_OBSERVATION"
    return payload
