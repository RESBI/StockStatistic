"""Storage REST API 路由。"""
from __future__ import annotations

from .ohlcv import create_ohlcv_router
from .symbols import create_symbols_router
from .health import create_health_router
from .ingest import create_ingest_router

__all__ = [
    "create_ohlcv_router",
    "create_symbols_router",
    "create_health_router",
    "create_ingest_router",
]
