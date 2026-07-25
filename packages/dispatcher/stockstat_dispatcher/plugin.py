"""DispatcherPlugin — 挂载到 Storage 的 FastAPI。"""
from __future__ import annotations

from typing import Optional


class DispatcherPlugin:
    """可挂载到 Storage FastAPI 的 Dispatcher 插件。"""
    name = "dispatcher"
    version = "1.0"

    @staticmethod
    def mount(app, *, queue_backend: str = "memory",
              redis_url: Optional[str] = None, cache_dir: Optional[str] = None,
              cache_size_mb: int = 512, storage_backend=None,
              storage_app=None, alias: str = "dispatch-primary",
              offline_timeout: float = 30.0, **kwargs):
        from .core import Dispatcher
        from .queue import build_queue
        from .routes import create_dispatcher_router

        queue = build_queue(backend=queue_backend, redis_url=redis_url)
        dispatcher = Dispatcher(
            queue=queue,
            storage_backend=storage_backend,
            cache_dir=cache_dir,
            cache_size_mb=cache_size_mb,
            alias=alias,
            offline_timeout=offline_timeout,
        )
        router = create_dispatcher_router(dispatcher)
        app.include_router(router)
        app.state.dispatcher = dispatcher
        return dispatcher

    @staticmethod
    def unmount(app):
        if hasattr(app.state, "dispatcher"):
            del app.state.dispatcher


__all__ = ["DispatcherPlugin"]
