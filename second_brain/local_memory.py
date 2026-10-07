# SPDX-License-Identifier: Apache-2.0
"""Controller-owned, bounded SQLite memory. No network or model calls.

This is separate from the admitted public corpus and review frontier. Search
returns metadata handles; reading stored text requires an explicit authorizer.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

SCHEMA = "szl.second-brain.local-memory/v1"
MAX_DB_BYTES = 16 * 1024 * 1024
MAX_IMPORT_BYTES = 1024 * 1024
MAX_RECORDS = 1000
MAX_TEXT_BYTES = 64 * 1024


class MemoryLimitError(ValueError):
    """A caller input or database exceeded the prototype budget."""


@dataclass(frozen=True)
class MemoryRecord:
    record_id: str
    source_uri: str
    source_revision: str
    title: str
    observed_at: str
    rights_status: str
    rights_basis: str | None = None
    text: str | None = None


def _field(value: str, name: str, maximum: int) -> str:
    if (type(value) is not str or not value.strip() or "\x00" in value
            or len(value.encode("utf-8")) > maximum):
        raise ValueError("invalid " + name)
    return value


def _validated(record: MemoryRecord) -> tuple[str | None, str | None]:
    if not isinstance(record, MemoryRecord):
        raise TypeError("expected MemoryRecord")
    for name, maximum in (("record_id", 128), ("source_uri", 2048),
                          ("source_revision", 256), ("title", 512),
                          ("observed_at", 48)):
        _field(getattr(record, name), name, maximum)
    try:
        observed = datetime.fromisoformat(record.observed_at)
    except ValueError as exc:
        raise ValueError("observed_at must be an aware ISO 8601 timestamp") from exc
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must include a time zone")
    if record.rights_status not in ("cleared", "unknown"):
        raise ValueError("rights_status must be cleared or unknown")
    if record.rights_status == "unknown":
        if record.text is not None or record.rights_basis is not None:
            raise ValueError("unknown rights permit metadata only")
        return None, None
    _field(record.rights_basis, "rights_basis", 2048)
    text = _field(record.text, "text", MAX_TEXT_BYTES)
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strict_json(raw: str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject(_value):
        raise ValueError("non-finite JSON value")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError("export row must be an object")
    return value


class LocalMemory:
    """Small local store for a trusted controller, never a public retrieval route.

    The 16 MiB limit applies to the main database. SQLite's short-lived rollback
    journal is measured separately; a crash can leave it until recovery.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).absolute()
        if str(path) == ":memory:" or self.path.is_symlink():
            raise ValueError("a regular on-disk database path is required")
        if not self.path.parent.is_dir():
            raise ValueError("database parent directory must already exist")
        if self.path.exists() and self.path.stat().st_size > MAX_DB_BYTES:
            raise MemoryLimitError("database exceeds 16 MiB")
        new = not self.path.exists() or self.path.stat().st_size == 0
        self._db = sqlite3.connect(self.path, timeout=1)
        try:
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA page_size=4096")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA secure_delete=ON")
            self._db.execute("PRAGMA temp_store=MEMORY")
            page_size = self._db.execute("PRAGMA page_size").fetchone()[0]
            page_limit = MAX_DB_BYTES // page_size
            self._db.execute(f"PRAGMA max_page_count={page_limit}")
            if self._db.execute("PRAGMA page_count").fetchone()[0] * page_size > MAX_DB_BYTES:
                raise MemoryLimitError("database exceeds 16 MiB")
            if new:
                self._create_schema()
            elif self._db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("unsupported local-memory database schema")
            # Fail clearly when the installed SQLite lacks FTS5 or the index.
            self._db.execute("SELECT rowid FROM memory_fts LIMIT 0")
            self.peak_storage_bytes = self.storage_bytes()
        except Exception:
            self._db.close()
            raise

    def _create_schema(self) -> None:
        self._db.executescript("""
            CREATE TABLE memory_record (
                record_id TEXT PRIMARY KEY,
                source_uri TEXT NOT NULL,
                source_revision TEXT NOT NULL,
                title TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                rights_status TEXT NOT NULL CHECK (rights_status IN ('cleared', 'unknown')),
                rights_basis TEXT,
                body TEXT,
                content_sha256 TEXT,
                training_allowed INTEGER NOT NULL DEFAULT 0 CHECK (training_allowed = 0),
                CHECK ((rights_status = 'unknown' AND rights_basis IS NULL AND body IS NULL
                        AND content_sha256 IS NULL) OR
                       (rights_status = 'cleared' AND rights_basis IS NOT NULL
                        AND body IS NOT NULL AND content_sha256 IS NOT NULL))
            );
            CREATE VIRTUAL TABLE memory_fts USING fts5(
                title, body, content='memory_record', content_rowid='rowid', tokenize='unicode61'
            );
            CREATE TRIGGER memory_ai AFTER INSERT ON memory_record BEGIN
                INSERT INTO memory_fts(rowid, title, body)
                VALUES (new.rowid, new.title, new.body);
            END;
            CREATE TRIGGER memory_ad AFTER DELETE ON memory_record BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, title, body)
                VALUES ('delete', old.rowid, old.title, old.body);
            END;
            CREATE TRIGGER memory_au AFTER UPDATE ON memory_record BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, title, body)
                VALUES ('delete', old.rowid, old.title, old.body);
                INSERT INTO memory_fts(rowid, title, body)
                VALUES (new.rowid, new.title, new.body);
            END;
            PRAGMA user_version=1;
        """)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> LocalMemory:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _upsert(self, record: MemoryRecord) -> str:
        body, digest = _validated(record)
        values = (record.record_id, record.source_uri, record.source_revision,
                  record.title, record.observed_at, record.rights_status,
                  record.rights_basis, body, digest)
        previous = self._db.execute("""
            SELECT record_id, source_uri, source_revision, title, observed_at,
                   rights_status, rights_basis, body, content_sha256
            FROM memory_record WHERE record_id = ?
        """, (record.record_id,)).fetchone()
        if previous is not None and tuple(previous) == values:
            return "unchanged"
        if previous is None:
            if self.count() >= MAX_RECORDS:
                raise MemoryLimitError("record limit reached")
            self._db.execute("""
                INSERT INTO memory_record
                (record_id, source_uri, source_revision, title, observed_at,
                 rights_status, rights_basis, body, content_sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values)
            return "inserted"
        self._db.execute("""
            UPDATE memory_record SET source_uri=?, source_revision=?, title=?,
                observed_at=?, rights_status=?, rights_basis=?, body=?, content_sha256=?
            WHERE record_id=?
        """, values[1:] + values[:1])
        return "updated"

    def upsert(self, record: MemoryRecord) -> str:
        try:
            with self._db:
                # Bind the capacity read and write under one SQLite writer lock.
                if not self._db.in_transaction:
                    self._db.execute("BEGIN IMMEDIATE")
                outcome = self._upsert(record)
                self._sample_storage()
            self._sample_storage()
            return outcome
        except sqlite3.Error as exc:
            if "full" in str(exc).lower():
                # A rights downgrade must not need spare FTS tombstone pages.
                if (record.rights_status == "unknown" and self._db.execute(
                        "SELECT 1 FROM memory_record WHERE record_id=?", (record.record_id,)
                ).fetchone() is not None):
                    return self._cleanup_rebuild(lambda: self._upsert(record))
                raise MemoryLimitError("database reached 16 MiB") from exc
            raise

    def _cleanup_rebuild(self, operation):
        """Free the old FTS pages before cleanup, atomically rebuilding survivors.

        Never increase max_page_count or expose a partial index. Any failure,
        including rebuilding the surviving rows, rolls back the whole retry.
        """
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            for trigger in ("memory_ai", "memory_ad", "memory_au"):
                self._db.execute("DROP TRIGGER " + trigger)
            self._db.execute("DROP TABLE memory_fts")
            result = operation()
            self._db.execute("""CREATE VIRTUAL TABLE memory_fts USING fts5(
                title, body, content='memory_record', content_rowid='rowid', tokenize='unicode61'
            )""")
            self._db.execute("INSERT INTO memory_fts(memory_fts) VALUES ('rebuild')")
            self._db.execute("""CREATE TRIGGER memory_ai AFTER INSERT ON memory_record BEGIN
                INSERT INTO memory_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
            END""")
            self._db.execute("""CREATE TRIGGER memory_ad AFTER DELETE ON memory_record BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, title, body)
                VALUES ('delete', old.rowid, old.title, old.body);
            END""")
            self._db.execute("""CREATE TRIGGER memory_au AFTER UPDATE ON memory_record BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, title, body)
                VALUES ('delete', old.rowid, old.title, old.body);
                INSERT INTO memory_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
            END""")
            self._sample_storage()
        self._sample_storage()
        return result

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM memory_record").fetchone()[0]

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        if type(query) is not str or len(query.encode("utf-8")) > 256:
            raise ValueError("query must fit in 256 UTF-8 bytes")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("limit must be 1..20")
        # Use the same tokenizer as the stored index, including its handling
        # of combining marks and private-use characters. The helper contains
        # only the bounded query and never writes to the persistent store.
        with closing(sqlite3.connect(":memory:")) as tokenizer:
            tokenizer.execute("CREATE VIRTUAL TABLE query_fts USING fts5(body, tokenize='unicode61')")
            tokenizer.execute("CREATE VIRTUAL TABLE query_vocab USING fts5vocab(query_fts, 'instance')")
            tokenizer.execute("INSERT INTO query_fts(body) VALUES (?)", (query,))
            tokens = [row[0] for row in tokenizer.execute(
                "SELECT term FROM query_vocab ORDER BY offset LIMIT 13"
            )]
        if len(tokens) > 12 or any(len(token.encode("utf-8")) > 64 for token in tokens):
            raise ValueError("query has too many or oversized terms")
        if not tokens:
            return []
        # Every term is a quoted literal. MATCH operators from the caller never
        # become FTS syntax, and the resulting expression is bound as a value.
        expression = " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        rows = self._db.execute("""
            SELECT r.record_id, r.source_uri, r.source_revision, r.title,
                   r.observed_at, r.rights_status, r.rights_basis,
                   r.content_sha256, r.training_allowed
            FROM memory_fts AS f JOIN memory_record AS r ON r.rowid = f.rowid
            WHERE memory_fts MATCH ?
            ORDER BY bm25(memory_fts), r.record_id LIMIT ?
        """, (expression, limit)).fetchall()
        return [{**dict(row), "schema": SCHEMA, "training_allowed": False,
                 "content_access": "METADATA_ONLY" if row["rights_status"] == "unknown"
                 else "AUTHORIZATION_REQUIRED"} for row in rows]

    def hydrate(self, record_id: str, *, authorizer: Callable[[str, str, str, str, str], bool],
                principal_id: str, tenant_id: str, policy_revision: str) -> dict:
        _field(record_id, "record_id", 128)
        for name, value in (("principal_id", principal_id), ("tenant_id", tenant_id),
                            ("policy_revision", policy_revision)):
            _field(value, name, 256)
        if not callable(authorizer):
            raise ValueError("authorizer is required")
        with self._db:
            # Hold other SQLite writers while this record is authorized. The
            # callback must not commit or mutate this store during the read.
            self._db.execute("BEGIN IMMEDIATE")
            row = self._db.execute("SELECT * FROM memory_record WHERE record_id=?", (record_id,)).fetchone()
            if row is None:
                raise KeyError(record_id)
            if row["rights_status"] != "cleared":
                raise PermissionError("content rights are unknown")
            try:
                allowed = authorizer(principal_id, tenant_id, policy_revision,
                                     record_id, row["source_uri"])
            except Exception as exc:
                raise PermissionError("authorization unavailable") from exc
            if allowed is not True:
                raise PermissionError("content access denied")
            current = self._db.execute("SELECT * FROM memory_record WHERE record_id=?", (record_id,)).fetchone()
            if not self._db.in_transaction or current is None or tuple(current) != tuple(row):
                raise PermissionError("record changed during authorization")
            return {"schema": SCHEMA, "record_id": record_id, "source_uri": row["source_uri"],
                    "source_revision": row["source_revision"], "title": row["title"],
                    "observed_at": row["observed_at"], "rights_status": row["rights_status"],
                    "rights_basis": row["rights_basis"], "content_sha256": row["content_sha256"],
                    "training_allowed": False, "content_access": "CONTROLLER_ONLY", "text": row["body"]}

    def delete(self, record_id: str) -> bool:
        _field(record_id, "record_id", 128)
        def remove():
            return self._db.execute("DELETE FROM memory_record WHERE record_id=?",
                                    (record_id,)).rowcount == 1
        try:
            with self._db:
                deleted = remove()
                self._sample_storage()
            self._sample_storage()
            return deleted
        except sqlite3.Error as exc:
            if "full" not in str(exc).lower():
                raise
            return self._cleanup_rebuild(remove)

    def export_jsonl(self, output: TextIO) -> int:
        """Write a complete exchange only if it fits the import byte/row caps.

        Preflight validation and limit failures leave the output untouched.
        A destination write failure can still leave partial output.
        """
        lines, total = [], 0
        with closing(self._db.execute("SELECT * FROM memory_record ORDER BY record_id")) as rows:
            for row in rows:
                record = MemoryRecord(row["record_id"], row["source_uri"], row["source_revision"],
                                      row["title"], row["observed_at"], row["rights_status"],
                                      row["rights_basis"], row["body"])
                _, digest = _validated(record)
                if digest != row["content_sha256"] or row["training_allowed"] != 0:
                    raise ValueError("invalid stored digest or training authority")
                exported = {"schema": SCHEMA, "record_id": row["record_id"],
                            "source_uri": row["source_uri"], "source_revision": row["source_revision"],
                            "title": row["title"], "observed_at": row["observed_at"],
                            "rights_status": row["rights_status"], "rights_basis": row["rights_basis"],
                            "content_sha256": digest, "training_allowed": False}
                if row["body"] is not None:
                    exported["text"] = row["body"]
                line = json.dumps(exported, sort_keys=True, ensure_ascii=False) + "\n"
                total += len(line.encode("utf-8"))
                if total > MAX_IMPORT_BYTES or len(lines) >= MAX_RECORDS:
                    raise MemoryLimitError("export exceeds the import byte or record budget")
                lines.append(line)
        for line in lines:
            output.write(line)
        return len(lines)

    def import_jsonl(self, source: TextIO) -> dict[str, int]:
        records, total, seen = [], 0, set()
        # JSON escaping can expand a valid 64 KiB body well past 128 KiB.
        # Bound the read by the remaining total budget, then count UTF-8 bytes.
        while True:
            chunks = []
            while True:
                # A Unicode character needs at most four UTF-8 bytes. Read in
                # small chunks; only the final one-character overflow probe can
                # exceed the remaining allowance, by at most four bytes.
                remaining = MAX_IMPORT_BYTES - total
                chunk = source.readline(max(1, min(4096, remaining // 4)))
                if type(chunk) is not str:
                    raise ValueError("import must be UTF-8 text")
                total += len(chunk.encode("utf-8"))
                if total > MAX_IMPORT_BYTES:
                    raise MemoryLimitError("import exceeds 1 MiB or 1000 records")
                chunks.append(chunk)
                if not chunk or chunk.endswith("\n"):
                    break
            line = "".join(chunks)
            if not line:
                break
            if len(records) >= MAX_RECORDS:
                raise MemoryLimitError("import exceeds 1 MiB or 1000 records")
            value = _strict_json(line)
            if value.pop("schema", None) != SCHEMA or value.pop("training_allowed", None) is not False:
                raise ValueError("invalid export schema or training authority")
            digest = value.pop("content_sha256", None)
            if set(value) != {"record_id", "source_uri", "source_revision", "title",
                              "observed_at", "rights_status", "rights_basis"} | ({"text"} if "text" in value else set()):
                raise ValueError("invalid export fields")
            record = MemoryRecord(**value)
            _, actual = _validated(record)
            if digest != actual or record.record_id in seen:
                raise ValueError("import digest mismatch or duplicate record")
            records.append(record)
            seen.add(record.record_id)
        counts = {"inserted": 0, "updated": 0, "unchanged": 0}
        if not records:
            return counts
        try:
            with self._db:
                # A second connection must observe our committed capacity use.
                if not self._db.in_transaction:
                    self._db.execute("BEGIN IMMEDIATE")
                for record in records:
                    counts[self._upsert(record)] += 1
                self._sample_storage()
        except sqlite3.Error as exc:
            if "full" in str(exc).lower():
                raise MemoryLimitError("database reached 16 MiB") from exc
            raise
        self._sample_storage()
        return counts

    def storage_bytes(self) -> int:
        return sum(path.stat().st_size for path in
                   (self.path, Path(str(self.path) + "-journal"),
                    Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm"))
                   if path.exists())

    def _sample_storage(self) -> None:
        self.peak_storage_bytes = max(self.peak_storage_bytes, self.storage_bytes())


__all__ = ["LocalMemory", "MemoryRecord", "MemoryLimitError", "SCHEMA"]
