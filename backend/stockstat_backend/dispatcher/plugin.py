"""DispatcherPlugin — mountable FastAPI plugin for the V3 Dispatcher.

Like AdminPlugin, this can be mounted on any FastAPI app:

    from stockstat_backend.dispatcher import DispatcherPlugin
    DispatcherPlugin.mount(app)

Controlled by ``STOCKSTAT_DISPATCHER_ENABLED`` (default: false).
When enabled, the Storage server also serves as a Dispatcher.
"""
from __future__ import annotations


class DispatcherPlugin:
    """Mountable Dispatcher plugin for FastAPI apps.

    Phase 1 (P2): runs in the same process as Storage, sharing the
    SQLAlchemy engine for data prefetch.
    Phase 3+ (P3): can run standalone via ``stockstat-dispatcher`` CLI.
    """

    name = "dispatcher"
    version = "1.0"

    @staticmethod
    def mount(app, *, queue_backend: str = "memory",
              redis_url: str = None, data_cache_dir: str = None,
              cache_size_mb: int = 512, offline_timeout: float = 30.0,
              storage_url: str = None) -> None:
        """Mount Dispatcher routes and state on the app.

        Args:
            app: FastAPI application
            queue_backend: "memory" (default) or "redis"
            redis_url: Redis connection URL (required if queue_backend="redis")
            data_cache_dir: directory for data cache (None = in-memory only)
            cache_size_mb: max data cache size in MB
            offline_timeout: seconds before a worker is marked offline
            storage_url: Storage server URL for data prefetch (defaults to
                         same-app, i.e. localhost)
        """
        from .core import Dispatcher
        from .queue import build_queue
        from .routes import create_dispatcher_router, create_tasks_router

        queue = build_queue(backend=queue_backend, redis_url=redis_url)
        dispatcher = Dispatcher(
            queue=queue,
            storage_url=storage_url,
            cache_dir=data_cache_dir,
            cache_size_mb=cache_size_mb,
            offline_timeout=offline_timeout,
            storage_app=app,
        )
        # Mount routes
        router = create_dispatcher_router(dispatcher)
        app.include_router(router)
        tasks_router = create_tasks_router(dispatcher)
        app.include_router(tasks_router)
        # Store on app.state for access from other plugins
        app.state.dispatcher = dispatcher

    @staticmethod
    def unmount(app) -> None:
        """No-op (FastAPI doesn't support route removal)."""
        pass
