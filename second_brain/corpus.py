# SPDX-License-Identifier: Apache-2.0
"""Strict all-or-nothing corpus admission. No network, model or release authority."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100_000
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CorpusIntegrityError(ValueError):
    """An entire candidate generation is invalid; never skip a malformed row."""


def strict_json(raw: str | bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CorpusIntegrityError("duplicate JSON key")
            result[key] = value
        return result

    def reject(_value):
        raise CorpusIntegrityError("non-finite JSON constant")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CorpusIntegrityError("invalid corpus JSON") from exc


@dataclass(frozen=True)
class CorpusRow:
    node_id: str
    title: str
    source: str
    source_id: str | None
    text: str
    sha256: str


@dataclass(frozen=True)
class Corpus:
    rows: tuple[CorpusRow, ...]
    file_sha256: str


def load_corpus(path: Path, expected_sha256: str | None = None) -> Corpus:
    """A digest supplied by the trusted controller pins the entire source file.

    Per-row text checks alone prove consistency, not authorship or release
    approval. The resulting file digest also binds titles, source IDs and order.
    """
    if expected_sha256 is not None and (
        not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256)
    ):
        raise CorpusIntegrityError("invalid expected corpus digest")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise CorpusIntegrityError("corpus exceeds byte budget")
    checksum = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and expected_sha256 != checksum:
        raise CorpusIntegrityError("corpus file digest mismatch")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise CorpusIntegrityError("invalid corpus encoding") from exc
    rows, seen = [], set()
    for line in text.splitlines():
        if not line.strip():
            continue
        value = strict_json(line)
        if not isinstance(value, dict):
            raise CorpusIntegrityError("corpus row must be an object")
        for key, maximum in (("id", 512), ("source", 4096), ("title", 8192), ("text", 128000)):
            field = value.get(key)
            if not isinstance(field, str) or not field.strip() or len(field) > maximum:
                raise CorpusIntegrityError("invalid corpus field: " + key)
        node_id = value["id"]
        if node_id in seen:
            raise CorpusIntegrityError("duplicate corpus node")
        source_id = value.get("sourceId")
        if source_id is not None and (not isinstance(source_id, str) or len(source_id) > 4096):
            raise CorpusIntegrityError("invalid source ID")
        declared = value.get("sha256")
        if (not isinstance(declared, str) or not SHA256.fullmatch(declared)
                or hashlib.sha256(value["text"].encode("utf-8")).hexdigest() != declared):
            raise CorpusIntegrityError("corpus content integrity failure")
        rows.append(CorpusRow(node_id, value["title"], value["source"], source_id, value["text"], declared))
        seen.add(node_id)
        if len(rows) > MAX_ROWS:
            raise CorpusIntegrityError("corpus exceeds row budget")
    if not rows:
        raise CorpusIntegrityError("empty corpus")
    return Corpus(tuple(rows), checksum)
