"""Cache Protocol — LRU / TTL / 命中率。"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    name: str

    def get(self, key: str) -> Optional[Any]: ...
    def put(self, key: str, value: Any, ttl: Optional[int] = None) -> None: ...
    def get_ref(self, key: str) -> Optional[str]: ...
    def invalidate(self, key: str) -> None: ...
    def stats(self) -> dict: ...


__all__ = ["Cache"]
