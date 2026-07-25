from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional


class InMemoryCache:
    def __init__(self, ttl: int = 300):
        self._store: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl

    def _key(self, *args) -> str:
        raw = json.dumps(args, default=str, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, *args) -> Optional[Any]:
        k = self._key(*args)
        if k in self._store:
            val, expiry = self._store[k]
            if time.time() < expiry:
                return val
            del self._store[k]
        return None

    def set(self, value: Any, *args):
        k = self._key(*args)
        self._store[k] = (value, time.time() + self._ttl)

    def clear(self):
        self._store.clear()


cache = InMemoryCache(ttl=300)
