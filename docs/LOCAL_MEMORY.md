# Local persistent memory prototype

`second_brain.local_memory` provides a small SQLite/FTS5 store for a trusted
local controller. It uses Python's standard library and needs no API keys,
model, provider, network, or ingestion service. SQLite must include FTS5.

The store has its own records and lifecycle. It does not activate records in
the admitted public corpus or hourly review frontier, and it adds no public
application route. FTS5 provides literal lexical search, not semantic search.

```python
from pathlib import Path
from second_brain.local_memory import LocalMemory, MemoryRecord

with LocalMemory(Path("local-memory.sqlite")) as memory:
    memory.upsert(MemoryRecord(
        record_id="synthetic-note-1",
        source_uri="synthetic://example/1",
        source_revision="example-v1",
        title="Microscopy fixture",
        observed_at="2026-10-03T00:00:00Z",
        rights_status="cleared",
        rights_basis="operator-created synthetic CC0 example",
        text="A synthetic fluorescence microscopy note.",
    ))
    handles = memory.search("fluorescence microscopy")
```

Each record preserves its source URI, source revision, observation timestamp,
rights status and rights basis. Cleared text gets a SHA-256 digest. A record
with `rights_status="unknown"` must omit both text and rights basis; only its
provenance and title metadata are stored and indexed. Rights clearance is a
caller assertion, so the controller must retain real permission evidence.
Every stored, searched and exported record has `training_allowed=false`.

`upsert()` returns `inserted`, `updated`, or `unchanged` for a stable record ID.
Reopening the same database preserves records and search. Search returns
metadata handles without text. `hydrate()` requires an explicit authorizer
with `(principal_id, tenant_id, policy_revision, record_id, source_uri)` and
returns cleared text only when that callback returns exactly `True`.
The callback must leave the store unchanged; hydration refuses a changed
record or transaction and holds other SQLite writers during authorization.

`export_jsonl(text_stream)` writes one complete bounded JSONL exchange with
provenance, rights and any cleared text. It validates and buffers at most 1 MiB
of serialized UTF-8 output before writing. If JSON escaping or the record count
exceeds the import budget, it raises `MemoryLimitError` and leaves the output
untouched. A destination write failure may leave partial output; discard it.

`import_jsonl(text_stream)` verifies the schema, content digests and training flag
before applying the complete bounded import in one transaction. Successful
exports fit the import input limits, and reimport is idempotent when the target
has capacity. Import failure preserves the target records and search index.
An empty store exports zero rows; importing empty output returns zero counts
and leaves existing records intact. Import is additive and does not remove
records absent from its input.

This exchange is not a guaranteed full-store backup: a valid database may hold
more JSONL than the 1 MiB transfer cap. Larger snapshots and chunked export are
unsupported. Exported text needs the same access control as the database.

The prototype limits are:

- 16 MiB main database, enforced through SQLite's page limit;
- 1,000 records and 64 KiB UTF-8 text per cleared record;
- 1 MiB UTF-8 per export/import, including JSON escaping and newlines;
  imports read small UTF-8-aware chunks; the final one-character overflow
  probe uses at most four extra bytes before rejection;
- 256 UTF-8 bytes, 12 literal terms and at most 20 results per search.

SQL values are parameterized. Search terms are quoted literals joined by AND,
so caller-supplied FTS operators do not become query syntax. A bounded in-memory
helper uses the same SQLite `unicode61` tokenizer as the stored index, including
combining marks and separator characters. SQLite uses a
rollback journal; `storage_bytes()` counts the database and journal files,
and `peak_storage_bytes` samples them during adapter writes. The main database
cap does not include a transient journal, a backup, or caller-owned exports.

`delete(record_id)` removes the record and its search entry. Updating a cleared
record to unknown rights removes its stored text and searchable body. These
use a transactional FTS index rebuild when a full index cannot append deletion
tombstones. The old index is freed before rebuilding survivors, without raising
the main-file cap. If any cleanup/rebuild step fails, its whole transaction rolls
back and the error remains visible; no successful revocation is reported. These
are logical deletion guarantees. Old filesystem copies, backups and SQLite
FTS segments are outside a secure-erasure guarantee.

This is a single-controller prototype. It has no encryption, tenant isolation,
external rights verification, broader concurrency testing, or crash
recovery testing. The authorizer is supplied by the owning controller. Keep
database and export files within that controller's trusted storage. The adapter
retains an absolute database path and checks actual file bytes as well as SQLite
page accounting when opening an existing store.

Upsert and nonempty import acquire SQLite's writer lock before checking record
capacity, so separate connections cannot both consume the same remaining slot.
A two-connection regression covers this admission limit for both operations;
it does not qualify broader concurrency or crash recovery.

Run the small offline acceptance suite without extra dependencies:

```text
python -m unittest discover -s tests -p test_local_memory.py -v
```

The 50-record probe uses less than 1 MiB of input and reports observed
database-plus-journal bytes and process peak memory. Limit-rejection regressions
use three 64 KiB control-character bodies to exercise JSON escaping, with less
than 1 MiB of synthetic input. The suite covers reopen/search,
idempotent writes, rights downgrade, authorization denial, literal query
handling, escaped-text export/reimport, tamper rejection, transactional rollback
and deletion. A second SQLite connection verifies that hydration blocks its
writer until authorization finishes; broader concurrency remains untested.
