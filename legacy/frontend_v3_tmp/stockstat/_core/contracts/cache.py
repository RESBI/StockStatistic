"""Cache backend protocol."""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """Abstract cache backend.

    Implementations: NullCache, MemoryCache, RedisCache.
    """
    name: str

    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def clear(self) -> None: ...
    def health_check(self) -> bool: ...
