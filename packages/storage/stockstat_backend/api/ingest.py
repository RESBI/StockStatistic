"""Ingest REST API — /api/v1/ingest 从数据源采集并写入。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from ..storage.backend import StorageBackendImpl
from ..adapters.base import get_adapter


def create_ingest_router(backend: StorageBackendImpl) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/ingest")
    async def ingest(
        symbol: str,
        timeframe: str = "1d",
        source: str = "binance",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ):
        """从数据源采集并写入 Storage。"""
        try:
            adapter_cls = get_adapter(source)
        except KeyError:
            raise HTTPException(400, f"Unknown data source: {source}")
        adapter = adapter_cls()
        try:
            df = adapter.fetch_ohlcv(symbol, timeframe, start, end)
        except Exception as e:
            raise HTTPException(502, f"Adapter fetch failed: {e}")
        rows = backend.ingest_ohlcv(symbol, timeframe, df)
        backend.upsert_metadata(symbol, exchange=source, asset_class="crypto" if source == "binance" else "stock")
        return {
            "rows_written": rows,
            "symbol": symbol,
            "timeframe": timeframe,
            "source": source,
        }

    return router
