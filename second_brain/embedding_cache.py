# SPDX-License-Identifier: Apache-2.0
"""Bounded in-process payload cache. It is not a durable or private memory store."""
from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Any


class EmbeddingCache:
    """LRU with explicit tensor-payload accounting, not total-process accounting.

    Callers must key by corpus/model/content identity. This cache is only used
    with the exact public corpus; it provides no private-data ACL or revocation.
    Returned tensors are used read-only by the owning retrieval coordinator.
    """
    def __init__(self, max_bytes: int = 256 * 1024 * 1024) -> None:
        if type(max_bytes) is not int or not 0 <= max_bytes <= 512 * 1024 * 1024:
            raise ValueError("cache budget must be an integer from zero to 512 MiB")
        self._max_bytes = max_bytes
        self._entries: OrderedDict[tuple[str, ...], tuple[Any, int]] = OrderedDict()
        self._bytes = self._hits = self._misses = self._evictions = 0
        self._lock = RLock()

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def get(self, key: tuple[str, ...]):
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is None:
                self._misses += 1
                return None
            self._entries[key] = entry
            self._hits += 1
            return entry[0]

    def put(self, key: tuple[str, ...], value: Any, *, byte_size: int) -> bool:
        if (not isinstance(key, tuple) or not key or len(key) > 8
                or any(not isinstance(part, str) or not part or len(part) > 1024 for part in key)
                or type(byte_size) is not int or byte_size <= 0 or value is None):
            raise ValueError("invalid cache entry")
        with self._lock:
            old = self._entries.pop(key, None)
            if old is not None:
                self._bytes -= old[1]
            if byte_size > self.max_bytes:
                return False
            while self._bytes + byte_size > self.max_bytes:
                _, (_, size) = self._entries.popitem(last=False)
                self._bytes -= size
                self._evictions += 1
            self._entries[key] = (value, byte_size)
            self._bytes += byte_size
            return True

    def stats(self) -> dict[str, int | str]:
        with self._lock:
            return {"scope": "PUBLIC_DOCUMENT_TENSOR_PAYLOAD_ONLY",
                    "max_bytes": self.max_bytes, "payload_bytes": self._bytes,
                    "entries": len(self._entries), "hits": self._hits,
                    "misses": self._misses, "evictions": self._evictions}
