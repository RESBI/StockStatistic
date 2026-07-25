"""Symbols REST API — /api/v1/symbols。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..storage.backend import StorageBackendImpl


def create_symbols_router(backend: StorageBackendImpl) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/symbols")
    async def list_symbols():
        return {"symbols": backend.list_symbols()}

    @router.get("/api/v1/symbols/{symbol}")
    async def get_symbol_metadata(symbol: str):
        meta = backend.get_metadata(symbol)
        if not meta:
            raise HTTPException(404, f"Symbol not found: {symbol}")
        return meta

    return router
