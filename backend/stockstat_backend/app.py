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

    # Mount web admin interface at /admin/
    from .admin import mount_admin
    mount_admin(app)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("stockstat_backend.app:app", host="0.0.0.0", port=8000, reload=True)
