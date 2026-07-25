"""Admin REST API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException


def create_admin_router(backend, dispatcher_state_getter=None) -> APIRouter:
    """创建 Admin 路由。

    Args:
        backend: StorageBackendImpl 实例
        dispatcher_state_getter: 可选，返回 Dispatcher 状态的回调
    """
    router = APIRouter(prefix="/admin/api")

    @router.get("/symbols")
    async def list_symbols():
        return {"symbols": backend.list_symbols()}

    @router.get("/symbols/{symbol}")
    async def symbol_detail(symbol: str):
        meta = backend.get_metadata(symbol)
        if not meta:
            raise HTTPException(404, f"Symbol not found: {symbol}")
        return meta

    @router.get("/ohlcv/stats")
    async def ohlcv_stats():
        return backend.stats()

    @router.get("/health")
    async def health():
        return {
            "status": "ok",
            "storage": backend.stats(),
        }

    @router.get("/dispatcher/cluster")
    async def dispatcher_cluster():
        if dispatcher_state_getter is None:
            return {"enabled": False}
        return dispatcher_state_getter()

    @router.get("/dispatcher/tasks")
    async def dispatcher_tasks(limit: int = 100, state: str = None):
        if dispatcher_state_getter is None:
            return {"history": [], "total": 0}
        state_info = dispatcher_state_getter()
        history = state_info.get("history", [])
        if state:
            history = [h for h in history if h.get("state") == state]
        return {"history": history[:limit], "total": len(history)}

    return router


__all__ = ["create_admin_router"]
