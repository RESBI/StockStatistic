"""StorageBackend Protocol — OHLCV 数据访问抽象。"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """存储后端协议 — OHLCV 数据访问抽象。"""
    name: str

    def fetch_ohlcv(self, symbols: list, timeframe: str,
                    start: Optional[str] = None, end: Optional[str] = None,
                    source: Optional[str] = None) -> Any: ...
    def ingest_ohlcv(self, symbol: str, timeframe: str, data: Any) -> int: ...
    def list_symbols(self) -> list: ...
    def get_metadata(self, symbol: str) -> dict: ...


__all__ = ["StorageBackend"]
