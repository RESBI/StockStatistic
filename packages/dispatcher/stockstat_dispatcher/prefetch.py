"""DataCache — 数据预取缓存（LRU + 命中率）。"""
from __future__ import annotations

import base64
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class _CacheEntry:
    data: bytes
    size: int
    last_access: float


class DataCache:
    """数据预取缓存 — LRU + 命中率统计。"""

    def __init__(self, cache_dir: Optional[str] = None, *, max_size_mb: int = 512):
        self._cache_dir = cache_dir
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._cache: dict = {}
        self._total_size = 0
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def get_ref(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            self._hits += 1
            entry.last_access = time.time()
            return f"cache://{key}"

    def fetch_bytes(self, ref: str) -> bytes:
        if ref.startswith("cache://"):
            key = ref[len("cache://"):]
            with self._lock:
                entry = self._cache.get(key)
                if entry is None:
                    raise ValueError(f"Cache miss for key: {key}")
                return entry.data
        if ref.startswith("inline:"):
            return base64.b64decode(ref[len("inline:"):])
        raise ValueError(f"Unknown data_ref: {ref}")

    def put(self, key: str, data: bytes) -> str:
        with self._lock:
            while self._total_size + len(data) > self._max_size_bytes and self._cache:
                self._evict_lru()
            self._cache[key] = _CacheEntry(data=data, size=len(data),
                                            last_access=time.time())
            self._total_size += len(data)
            return f"cache://{key}"

    def _evict_lru(self) -> None:
        if not self._cache:
            return
        oldest_key = min(self._cache, key=lambda k: self._cache[k].last_access)
        entry = self._cache.pop(oldest_key)
        self._total_size -= entry.size

    def size_mb(self) -> float:
        return self._total_size / (1024 * 1024)

    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def invalidate(self, key: str) -> None:
        with self._lock:
            entry = self._cache.pop(key, None)
            if entry:
                self._total_size -= entry.size

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._total_size = 0
            self._hits = 0
            self._misses = 0


__all__ = ["DataCache"]
