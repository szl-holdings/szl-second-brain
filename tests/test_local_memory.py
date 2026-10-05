"""Synthetic, offline checks for the controller-owned SQLite memory adapter."""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from second_brain.local_memory import (
    MAX_DB_BYTES,
    MAX_IMPORT_BYTES,
    MAX_TEXT_BYTES,
    LocalMemory,
    MemoryLimitError,
    MemoryRecord,
)


def _process_peak_bytes() -> int:
    if sys.platform == "win32":
        import ctypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        value = Counters()
        value.cb = ctypes.sizeof(value)
        ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong
        )
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
            process, ctypes.byref(value), value.cb
        ):
            raise OSError("GetProcessMemoryInfo failed")
        return value.PeakWorkingSetSize
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def fixture(number: int, *, rights: str = "cleared", text: str | None = None) -> MemoryRecord:
    return MemoryRecord(
        record_id=f"synthetic-{number:03}",
        source_uri=f"synthetic://fixture/{number}",
        source_revision=f"revision-{number}",
        title=f"Microscopy sample {number}",
        observed_at="2026-10-03T00:00:00Z",
        rights_status=rights,
        rights_basis="synthetic CC0 fixture" if rights == "cleared" else None,
        text=(text if text is not None else f"fluorescence sample {number} " * 12)
        if rights == "cleared" else None,
    )


class LocalMemoryTests(unittest.TestCase):
    def test_fifty_synthetic_records_reopen_search_export_and_reimport(self) -> None:
        before_rss = _process_peak_bytes()
        with TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.sqlite"
            target_path = Path(directory) / "target.sqlite"
            with LocalMemory(source_path) as source:
                for number in range(50):
                    rights = "unknown" if number % 10 == 0 else "cleared"
                    self.assertEqual(source.upsert(fixture(number, rights=rights)), "inserted")
                self.assertEqual(source.upsert(fixture(1)), "unchanged")
                self.assertEqual(source.count(), 50)
                self.assertLessEqual(source.peak_storage_bytes, MAX_DB_BYTES)
                page_size = source._db.execute("PRAGMA page_size").fetchone()[0]
                page_limit = source._db.execute("PRAGMA max_page_count").fetchone()[0]
                self.assertLessEqual(page_size * page_limit, MAX_DB_BYTES)
                self.assertEqual(source.search("fluorescence", limit=20)[0]["training_allowed"], False)
                self.assertEqual(source.search("sample 0", limit=20)[0]["content_access"], "METADATA_ONLY")
                self.assertTrue(all("text" not in handle for handle in source.search("sample")))
                with self.assertRaises(PermissionError):
                    source.hydrate("synthetic-001", authorizer=lambda *_: False,
                                   principal_id="owner", tenant_id="local", policy_revision="v1")
                hydrated = source.hydrate("synthetic-001", authorizer=lambda *_: True,
                                          principal_id="owner", tenant_id="local", policy_revision="v1")
                self.assertIn("fluorescence", hydrated["text"])
                with self.assertRaises(PermissionError):
                    source.hydrate("synthetic-000", authorizer=lambda *_: True,
                                   principal_id="owner", tenant_id="local", policy_revision="v1")
                output = io.StringIO()
                self.assertEqual(source.export_jsonl(output), 50)
                export = output.getvalue()
                self.assertLessEqual(len(export.encode("utf-8")), MAX_IMPORT_BYTES)
                self.assertNotIn('"text": null', export)
                self.assertLessEqual(source.storage_bytes(), MAX_DB_BYTES)
                source_peak_disk = source.peak_storage_bytes
            with LocalMemory(source_path) as reopened:
                self.assertEqual(reopened.count(), 50)
                self.assertEqual(reopened.search("fluorescence")[0]["record_id"], "synthetic-001")
            with LocalMemory(target_path) as target:
                self.assertEqual(target.import_jsonl(io.StringIO(export)),
                                 {"inserted": 50, "updated": 0, "unchanged": 0})
                self.assertEqual(target.import_jsonl(io.StringIO(export)),
                                 {"inserted": 0, "updated": 0, "unchanged": 50})
                copied = io.StringIO()
                target.export_jsonl(copied)
                self.assertEqual(copied.getvalue(), export)
                self.assertTrue(target.delete("synthetic-001"))
                self.assertFalse(target.delete("synthetic-001"))
                self.assertEqual(target.count(), 49)
                self.assertFalse(any(row["record_id"] == "synthetic-001"
                                     for row in target.search("fluorescence", limit=20)))
                self.assertLessEqual(target.peak_storage_bytes, MAX_DB_BYTES)
                target_peak_disk = target.peak_storage_bytes
        after_rss = _process_peak_bytes()
        print(f"local-memory probe: 50 records, input={len(export.encode('utf-8'))} bytes, "
              f"source DB+journal peak={source_peak_disk} bytes, "
              f"target DB+journal peak={target_peak_disk} bytes, "
              f"process peak RSS={after_rss} bytes, delta={max(0, after_rss-before_rss)} bytes")

    def test_rights_downgrade_removes_content_from_search_and_export(self) -> None:
        with TemporaryDirectory() as directory, LocalMemory(Path(directory) / "memory.sqlite") as memory:
            self.assertEqual(memory.upsert(fixture(2, text="privateblueword")), "inserted")
            self.assertEqual(len(memory.search("privateblueword")), 1)
            self.assertEqual(memory.upsert(fixture(2, rights="unknown")), "updated")
            self.assertEqual(memory.search("privateblueword"), [])
            output = io.StringIO()
            memory.export_jsonl(output)
            self.assertNotIn("privateblueword", output.getvalue())
            self.assertNotIn("text", json.loads(output.getvalue()))
            self.assertEqual(memory.search("microscopy")[0]["content_access"], "METADATA_ONLY")
            with self.assertRaises(ValueError):
                memory.upsert(MemoryRecord("unknown", "synthetic://bad", "v1", "Bad",
                                           "2026-10-03T00:00:00Z", "unknown", text="forbidden"))
            with self.assertRaises(ValueError):
                memory.upsert(fixture(6, text="x" * (MAX_TEXT_BYTES + 1)))

    def test_fts_query_operators_and_sql_in_record_id_are_literal(self) -> None:
        with TemporaryDirectory() as directory, LocalMemory(Path(directory) / "memory.sqlite") as memory:
            injected_id = "x'); DROP TABLE memory_record; --"
            row = fixture(3, text="microscopeonly")
            self.assertEqual(memory.upsert(MemoryRecord(injected_id, row.source_uri,
                                                         row.source_revision, row.title,
                                                         row.observed_at, row.rights_status,
                                                         row.rights_basis, row.text)), "inserted")
            self.assertEqual(len(memory.search("microscopeonly")), 1)
            self.assertEqual(memory.search('microscopeonly" OR *'), [])
            self.assertEqual(memory.count(), 1)
            self.assertTrue(memory.delete(injected_id))
            self.assertEqual(memory.count(), 0)
            with self.assertRaises(ValueError):
                memory.search("x" * 257)

    def test_import_rejects_tampering_without_partial_write(self) -> None:
        with TemporaryDirectory() as directory:
            with LocalMemory(Path(directory) / "source.sqlite") as source:
                source.upsert(fixture(4))
                source.upsert(fixture(5))
                exported = io.StringIO()
                source.export_jsonl(exported)
            lines = exported.getvalue().splitlines()
            tampered = json.loads(lines[1])
            tampered["content_sha256"] = "0" * 64
            lines[1] = json.dumps(tampered)
            with LocalMemory(Path(directory) / "target.sqlite") as target:
                with self.assertRaises(ValueError):
                    target.import_jsonl(io.StringIO("\n".join(lines) + "\n"))
                self.assertEqual(target.count(), 0)
                tampered["training_allowed"] = True
                with self.assertRaises(ValueError):
                    target.import_jsonl(io.StringIO(json.dumps(tampered) + "\n"))
                with self.assertRaises(ValueError):
                    target.import_jsonl(io.StringIO('{"schema":"x","schema":"y"}\n'))
                self.assertEqual(target.count(), 0)

    def test_hydration_refuses_a_record_changed_by_its_authorizer(self) -> None:
        with TemporaryDirectory() as directory, LocalMemory(Path(directory) / "memory.sqlite") as memory:
            memory.upsert(fixture(7, text="revokedword"))

            def revoke(*_args):
                memory.upsert(fixture(7, rights="unknown"))
                return True

            with self.assertRaises(PermissionError):
                memory.hydrate("synthetic-007", authorizer=revoke, principal_id="owner",
                               tenant_id="local", policy_revision="v1")
            self.assertEqual(memory.search("revokedword"), [])

    def test_scaled_budgets_reject_without_losing_previous_records(self) -> None:
        with TemporaryDirectory() as directory:
            with patch("second_brain.local_memory.MAX_DB_BYTES", 64 * 1024):
                with LocalMemory(Path(directory) / "limited.sqlite") as memory:
                    memory.upsert(fixture(8, text="retainedword"))
                    with self.assertRaises(MemoryLimitError):
                        memory.upsert(fixture(9, text="floodword " * 5000))
                    self.assertEqual(memory.count(), 1)
                    self.assertEqual(len(memory.search("retainedword")), 1)
                    self.assertEqual(memory.search("floodword"), [])
                    self.assertLessEqual(memory.path.stat().st_size, 64 * 1024)
                    exported = io.StringIO()
                    memory.export_jsonl(exported)
            with LocalMemory(Path(directory) / "rows.sqlite") as memory:
                with patch("second_brain.local_memory.MAX_RECORDS", 2):
                    memory.upsert(fixture(10))
                    memory.upsert(fixture(11))
                    with self.assertRaises(MemoryLimitError):
                        memory.upsert(fixture(12))
                    self.assertEqual(memory.count(), 2)
            with LocalMemory(Path(directory) / "import.sqlite") as memory:
                with patch("second_brain.local_memory.MAX_IMPORT_BYTES", 100):
                    with self.assertRaises(MemoryLimitError):
                        memory.import_jsonl(io.StringIO(exported.getvalue()))
                    self.assertEqual(memory.count(), 0)


if __name__ == "__main__":
    unittest.main()
