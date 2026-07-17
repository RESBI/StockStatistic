"""Cache backend implementations."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional


class NullCache:
    """No-op cache. Satisfies :class:`CacheBackend` protocol."""
    name = "null"

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        pass

    def delete(self, key: str) -> None:
        pass

    def exists(self, key: str) -> bool:
        return False

    def clear(self) -> None:
        pass

    def health_check(self) -> bool:
        return True


class MemoryCache:
    """In-process TTL cache. Satisfies :class:`CacheBackend` protocol.

    This is a drop-in replacement for the v1.7 ``InMemoryCache``,
    exposed behind the :class:`CacheBackend` protocol.
    """
    name = "memory"

    def __init__(self, ttl: int = 300) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = ttl

    @staticmethod
    def make_key(*args: Any) -> str:
        """Build a cache key from arguments (MD5 hash)."""
        raw = json.dumps(args, default=str, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            val, expiry = self._store[key]
            if time.time() < expiry:
                return val
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        actual_ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (value, time.time() + actual_ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._store and time.time() < self._store[key][1]

    def clear(self) -> None:
        self._store.clear()

    def health_check(self) -> bool:
        return True


class RedisCache:
    """Redis-backed cache. Satisfies :class:`CacheBackend` protocol.

    Requires the ``redis`` package (optional extra). If Redis is not
    installed or unreachable, operations silently degrade to no-op.
    """
    name = "redis"

    def __init__(self, redis_url: str = "redis://localhost:6379/0", ttl: int = 300) -> None:
        self._ttl = ttl
        self._client = None
        try:
            import redis
            self._client = redis.from_url(redis_url, decode_responses=False)
        except ImportError:
            pass

    def get(self, key: str) -> Optional[Any]:
        if self._client is None:
            return None
        try:
            import pickle
            raw = self._client.get(key)
            if raw is not None:
                return pickle.loads(raw)
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if self._client is None:
            return
        try:
            import pickle
            actual_ttl = ttl if ttl is not None else self._ttl
            self._client.setex(key, actual_ttl, pickle.dumps(value))
        except Exception:
            pass

    def delete(self, key: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete(key)
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        if self._client is None:
            return False
        try:
            return bool(self._client.exists(key))
        except Exception:
            return False

    def clear(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flushdb()
        except Exception:
            pass

    def health_check(self) -> bool:
        if self._client is None:
            return False
        try:
            return self._client.ping()
        except Exception:
            return False


def create_cache(backend: str = "memory", **kwargs: Any) -> Any:
    """Factory: create a cache by backend name."""
    if backend == "null":
        return NullCache()
    elif backend == "redis":
        return RedisCache(**kwargs)
    else:  # "memory" or default
        return MemoryCache(**kwargs)
