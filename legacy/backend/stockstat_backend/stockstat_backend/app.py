from __future__ import annotations

from fastapi import FastAPI

from .api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="StockStat Storage Backend",
        version="0.1.0",
        description="Unified OHLCV storage and query service",
    )
    app.include_router(router)

    # Conditionally mount admin plugin
    from .config import settings
    if settings.admin_enabled:
        from .plugins.admin import AdminPlugin
        AdminPlugin.mount(app)

    # V3: Conditionally mount Dispatcher plugin
    if settings.dispatcher_enabled:
        from .dispatcher import DispatcherPlugin
        DispatcherPlugin.mount(
            app,
            queue_backend=settings.dispatcher_queue_backend,
            redis_url=settings.redis_url or None,
            cache_size_mb=settings.dispatcher_cache_size_mb,
        )
        # P7: wire the dispatcher into Admin UI for monitoring
        if settings.admin_enabled:
            from .plugins.admin.router import set_dispatcher_ref
            set_dispatcher_ref(app.state.dispatcher)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("stockstat_backend.app:app", host="0.0.0.0", port=8000, reload=True)
