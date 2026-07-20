"""DataCache — Dispatcher-side data prefetch and LRU cache.

V2 §2.2: Dispatcher prefetches data from Storage once (not N times
for N workers). Subsequent tasks with the same data_spec hit the
cache (cache_hit_rate metric).
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Optional


class DataCache:
    """LRU cache for prefetched OHLCV data.

    Stores data as serialized Arrow bytes (or raw bytes). Returns
    data_ref identifiers that Workers use to fetch the data.

    Phase 1 (P2): in-memory dict
    Phase 4 (P4): shared memory for same-host workers
    """

    def __init__(self, max_size_mb: int = 512, cache_dir: str = None):
        self._max_size = max_size_mb * 1024 * 1024
        self._cache_dir = cache_dir
        self._entries: dict[str, _CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()
        self._current_size = 0

    @staticmethod
    def make_key(data_spec) -> str:
        """Stable cache key from a DataSpec."""
        h = hashlib.sha256()
        h.update("|".join(data_spec.symbols).encode("utf-8"))
        h.update(b"|" + data_spec.timeframe.encode("utf-8"))
        h.update(b"|" + (data_spec.start or "").encode("utf-8"))
        h.update(b"|" + (data_spec.end or "").encode("utf-8"))
        h.update(b"|" + (data_spec.source or "").encode("utf-8"))
        return h.hexdigest()[:32]

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._entries

    def get(self, key: str) -> Optional[bytes]:
        """Return cached data bytes, or None on miss."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            entry.last_access = time.time()
            self._hits += 1
            return entry.data

    def put(self, key: str, data: bytes) -> str:
        """Store data and return a data_ref string."""
        with self._lock:
            # Evict if over size limit
            while self._current_size + len(data) > self._max_size and self._entries:
                self._evict_oldest()
            self._entries[key] = _CacheEntry(
                data=data,
                size=len(data),
                created_at=time.time(),
                last_access=time.time(),
            )
            self._current_size += len(data)
        return f"cache://{key}"

    def get_ref(self, key: str) -> Optional[str]:
        """Return the data_ref for a cached key, or None."""
        with self._lock:
            if key in self._entries:
                self._entries[key].last_access = time.time()
                self._hits += 1
                return f"cache://{key}"
            self._misses += 1
            return None

    def fetch_ref(self, data_ref: str) -> Optional[bytes]:
        """Fetch data by its data_ref string."""
        if not data_ref.startswith("cache://"):
            return None
        key = data_ref[len("cache://"):]
        return self.get(key)

    def _evict_oldest(self) -> None:
        """LRU eviction — remove the entry with oldest last_access."""
        if not self._entries:
            return
        oldest_key = min(self._entries, key=lambda k: self._entries[k].last_access)
        entry = self._entries.pop(oldest_key)
        self._current_size -= entry.size

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    @property
    def size_mb(self) -> float:
        return self._current_size / (1024 * 1024)

    def stats(self) -> dict:
        return {
            "size_mb": round(self.size_mb, 2),
            "hit_rate": round(self.hit_rate, 4),
            "hits": self._hits,
            "misses": self._misses,
            "entries": len(self._entries),
        }


from dataclasses import dataclass

@dataclass
class _CacheEntry:
    data: bytes
    size: int
    created_at: float
    last_access: float
