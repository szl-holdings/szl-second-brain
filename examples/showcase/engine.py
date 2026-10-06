"""Bounded, deterministic retrieval and explicit-edge navigation over synthetic fixtures."""
from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType

from second_brain.corpus import strict_json
from second_brain.hybrid import AuthorizedHydrator
from second_brain.retrieve import SecondBrainIndex

HERE = Path(__file__).resolve().parent
SCHEMA = "szl.synthetic-showcase.result/v1"
POLICY = {"synthetic": True, "private": False, "retrieval": True,
          "display": True, "training": False, "basis": "authored-for-demo"}
MAX_RECORDS, MAX_BYTES, MAX_HOPS = 64, 128 * 1024, 3
TOKEN = r"[a-z][a-z0-9 -]{0,59}"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fixture_revision(values: object) -> str:
    """Canonical fixture-authoring encoding, also used by in-memory test variants."""
    raw = (json.dumps(values, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("fixture exceeds byte budget")
    return digest(raw)


def read_fixture(name: str) -> tuple[object, str]:
    """Only two fixed bundle inputs; no caller-supplied file or environment path."""
    if name not in {"records.json", "queries.json"}:
        raise ValueError("unknown fixture")
    with (HERE / "fixtures" / "manifest.json").open("rb") as stream:
        manifest_raw = stream.read(4097)
    if len(manifest_raw) > 4096:
        raise ValueError("fixture manifest exceeds byte budget")
    manifest = strict_json(manifest_raw)
    with (HERE / "fixtures" / name).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or digest(raw) != manifest["sha256"][name]:
        raise ValueError("fixture bytes differ from frozen manifest")
    return strict_json(raw), digest(raw)


@dataclass(frozen=True)
class Claim:
    kind: str
    subject: str
    predicate: str
    object: str

    @property
    def quote(self) -> str:
        return f"{self.subject} | {self.predicate} | {self.object}."


@dataclass(frozen=True)
class Record:
    id: str
    source_id: str
    source_family: str
    entity_group: str
    split: str
    date: str
    title: str
    text: str
    claims: tuple[Claim, ...]

    @property
    def sha256(self) -> str:
        return digest(self.text.encode())


def admit(values: object) -> tuple[Record, ...]:
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_RECORDS:
        raise ValueError("invalid fixture record count")
    records, seen = [], set()
    fields = {"id", "source_id", "source_family", "entity_group", "split",
              "date", "title", "text", "claims", "rights"}
    for row in values:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("invalid fixture record fields")
        for field in fields - {"claims", "rights"}:
            if not isinstance(row[field], str) or not row[field] or len(row[field]) > 4000:
                raise ValueError("invalid fixture string")
        if row["id"] in seen or not re.fullmatch(r"syn-[a-z0-9-]{1,60}", row["id"]):
            raise ValueError("duplicate or invalid fixture ID")
        seen.add(row["id"])
        if (not row["source_id"].startswith("synthetic:")
                or row["split"] not in {"development", "evaluation"}
                or date.fromisoformat(row["date"]).isoformat() != row["date"]):
            raise ValueError("invalid fixture provenance")
        if not isinstance(row["claims"], list) or not 1 <= len(row["claims"]) <= 8:
            raise ValueError("invalid claims")
        claims = []
        for raw in row["claims"]:
            if not isinstance(raw, dict) or set(raw) != {"kind", "subject", "predicate", "object"}:
                raise ValueError("invalid claim fields")
            if raw["kind"] not in {"fact", "edge"} or any(
                not isinstance(raw[k], str) or not re.fullmatch(TOKEN, raw[k])
                for k in ("subject", "predicate", "object")
            ):
                raise ValueError("invalid claim")
            claim = Claim(**raw)
            if claim.quote not in row["text"]:
                raise ValueError("claim lacks exact fixture evidence")
            claims.append(claim)
        rights = row["rights"]
        # Literal booleans: 0/1, strings, omitted fields and extra grants fail closed.
        if not isinstance(rights, dict) or set(rights) != set(POLICY) or any(
            type(rights[k]) is not type(v) or rights[k] != v for k, v in POLICY.items()
        ):
            continue
        records.append(Record(**{k: row[k] for k in fields - {"claims", "rights"}},
                              claims=tuple(claims)))
    return tuple(records)


def parse(query: str) -> tuple[str, str, str] | None:
    """Small documented grammar, not general language understanding."""
    patterns = (
        ("fact", rf"fact ({TOKEN}) / ({TOKEN})"),
        ("fact", rf"what is ({TOKEN})'s ({TOKEN})\?"),
        ("path", rf"path ({TOKEN}) -> ({TOKEN})"),
        ("path", rf"how is ({TOKEN}) connected to ({TOKEN})\?"),
    )
    for kind, pattern in patterns:
        match = re.fullmatch(pattern, query.lower().strip())
        if match:
            return kind, match[1].strip(), match[2].strip()
    return None


class Showcase:
    def __init__(self, values: object, revision: str):
        self.records = admit(values)
        if not isinstance(revision, str) or revision != fixture_revision(values):
            raise ValueError("fixture revision does not bind these records")
        self.revision = revision
        self.by_id = MappingProxyType({row.id: row for row in self.records})
        self.brain = self.hydrator = None
        if not self.records:
            return
        rows = [{"id": r.id, "source": r.source_family, "sourceId": r.source_id,
                 "title": r.title, "text": r.text, "sha256": r.sha256} for r in self.records]
        raw = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
        # Existing public APIs load only this explicitly supplied, admitted projection.
        # Both capture immutable in-memory generations before temporary files disappear.
        with TemporaryDirectory(prefix="szl-synthetic-") as directory:
            path = Path(directory) / "corpus.jsonl"
            path.write_bytes(raw)
            self.brain = SecondBrainIndex(path, expected_sha256=digest(raw)).snapshot()
            allowed = frozenset(self.by_id)
            self.hydrator = AuthorizedHydrator(
                lambda principal, tenant, policy, node, source: (
                    principal == "synthetic-demo" and tenant == "synthetic-demo"
                    and policy == "sha256:" + revision and node in allowed
                    and source == self.by_id[node].source_family
                ), path=path, expected_sha256=digest(raw))
        if not self.brain.built:
            raise ValueError("synthetic index failed admission")

    @classmethod
    def bundled(cls) -> Showcase:
        values, revision = read_fixture("records.json")
        return cls(values, revision)

    def citation(self, row: Record, claim: Claim) -> dict:
        documents = self.hydrator.hydrate(
            [{"nodeId": row.id, "source": row.source_family, "sha256": row.sha256}],
            principal_id="synthetic-demo", tenant_id="synthetic-demo",
            policy_revision="sha256:" + self.revision)["documents"]
        if claim.quote not in documents[0]["content"]:
            raise ValueError("citation evidence mismatch")
        return {"record_id": row.id, "source_id": row.source_id, "date": row.date,
                "source_family": row.source_family, "text_sha256": row.sha256,
                "fixture_revision": self.revision, "quote": claim.quote}

    def search(self, query: str, k: int = 3) -> list[str]:
        if not isinstance(query, str) or len(query) > 300:
            raise ValueError("query must be at most 300 characters")
        if type(k) is not int or not 1 <= k <= 12:
            raise ValueError("k outside 1..12")
        return [h["nodeId"] for h in self.brain.search(query, k=k)["handles"]] if self.brain else []

    def query(self, query: str, k: int = 3) -> dict:
        retrieved = self.search(query, k)
        result = {"schema": SCHEMA, "synthetic": True, "query": query,
                  "state": "ABSTAIN", "reason": "UNSUPPORTED_QUERY", "answer": None,
                  "retrieved_ids": retrieved, "citations": [], "steps": [],
                  "fixture_revision": self.revision, "authority": "NONE"}
        intent = parse(query)
        if intent is None:
            return result
        kind, subject, target = intent
        if kind == "fact":
            matches = [(r, c) for r in self.records for c in r.claims
                       if c.kind == "fact" and (c.subject, c.predicate) == (subject, target)]
            if not matches:
                return {**result, "reason": "UNKNOWN_FACT"}
            # Check the whole bounded admitted set, never only the top-k window.
            if len({c.object for _, c in matches}) != 1:
                return {**result, "reason": "CONFLICTING_EVIDENCE"}
            offered = [(r, c) for r, c in matches if r.id in retrieved]
            if not offered:
                return {**result, "reason": "EVIDENCE_NOT_RETRIEVED"}
            row, claim = min(offered, key=lambda rc: retrieved.index(rc[0].id))
            return {**result, "state": "ANSWERED", "reason": "SUPPORTED_FACT",
                    "answer": claim.object, "citations": [self.citation(row, claim)]}
        if subject == target:
            return {**result, "reason": "NO_SUPPORTED_PATH"}
        edges = sorted(((r, c) for r in self.records for c in r.claims if c.kind == "edge"),
                       key=lambda rc: (rc[1].subject, rc[1].object, rc[0].id))
        queue, visited = deque([(subject, [])]), {subject}
        while queue:
            node, path = queue.popleft()
            if len(path) >= MAX_HOPS:
                continue
            for row, claim in edges:
                if claim.subject != node or claim.object in visited:
                    continue
                extended = path + [(row, claim)]
                if claim.object == target:
                    steps = [{"subject": c.subject, "predicate": c.predicate,
                              "object": c.object, "record_id": r.id} for r, c in extended]
                    return {**result, "state": "ANSWERED", "reason": "SUPPORTED_PATH",
                            "answer": " -> ".join([subject] + [c.object for _, c in extended]),
                            "citations": [self.citation(r, c) for r, c in extended], "steps": steps}
                visited.add(claim.object)
                queue.append((claim.object, extended))
        return {**result, "reason": "NO_SUPPORTED_PATH"}
