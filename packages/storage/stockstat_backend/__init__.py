"""stockstat-backend — StockStat V3.1 存储端。"""
from __future__ import annotations

__version__ = "3.1.0"

from .models import Base, OHLCV, SymbolMetadata
from .storage.orm import OrmSession, create_engine_from_url, set_sqlite_wal
from .storage.backend import StorageBackendImpl
from .storage.cache import QueryCache
from .adapters import (
    DataSource, BinanceAdapter, YFinanceAdapter, SyntheticAdapter,
    get_adapter, list_adapters, ADAPTERS,
)
from .normalizer import Normalizer
from .scheduler import ScheduledCollector
from .app import StorageApp

__all__ = [
    "__version__",
    "Base", "OHLCV", "SymbolMetadata",
    "OrmSession", "create_engine_from_url", "set_sqlite_wal",
    "StorageBackendImpl", "QueryCache",
    "DataSource", "BinanceAdapter", "YFinanceAdapter", "SyntheticAdapter",
    "get_adapter", "list_adapters", "ADAPTERS",
    "Normalizer", "ScheduledCollector",
    "StorageApp",
]
