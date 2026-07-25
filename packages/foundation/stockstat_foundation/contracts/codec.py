"""Codec Protocol — 字节 ↔ Python 对象。"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Codec(Protocol):
    name: str
    media_type: str

    def encode(self, data: Any) -> bytes: ...
    def decode(self, raw: bytes) -> Any: ...


__all__ = ["Codec"]
