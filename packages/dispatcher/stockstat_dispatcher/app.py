"""DispatcherApp — 独立 FastAPI 应用。"""
from __future__ import annotations

from typing import Optional


class DispatcherApp:
    """独立 Dispatcher FastAPI 应用。"""

    @staticmethod
    def create(*, storage_url: Optional[str] = None,
               queue_backend: str = "memory",
               redis_url: Optional[str] = None,
               listen: str = "0.0.0.0:9000",
               alias: str = "dispatch-primary",
               parent_url: Optional[str] = None,
               storage_backend=None):
        from fastapi import FastAPI
        from .core import Dispatcher
        from .queue import build_queue
        from .routes import create_dispatcher_router

        app = FastAPI(
            title="StockStat Dispatcher",
            version="3.1.0",
            description="StockStat V3.1 分发端",
        )
        queue = build_queue(backend=queue_backend, redis_url=redis_url)
        dispatcher = Dispatcher(
            queue=queue,
            storage_url=storage_url,
            storage_backend=storage_backend,
            alias=alias,
            parent_url=parent_url,
        )
        router = create_dispatcher_router(dispatcher)
        app.include_router(router)
        app.state.dispatcher = dispatcher
        return app


__all__ = ["DispatcherApp"]
