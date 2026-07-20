"""AdminPlugin — mountable web admin interface for FastAPI apps."""
from __future__ import annotations


class AdminPlugin:
    """Web admin interface plugin.

    Mountable on any FastAPI app. Provides:
    - REST API at /admin/api/*
    - Web UI (SPA) at /admin/

    Controlled by ``settings.admin_enabled`` (default: true).
    Set ``STOCKSTAT_ADMIN_ENABLED=false`` to disable.
    """

    name = "admin"
    version = "1.0"

    @staticmethod
    def mount(app) -> None:
        """Mount admin routes and web UI on the app."""
        from .router import create_admin_router
        from .web import ADMIN_HTML
        from fastapi.responses import HTMLResponse

        router = create_admin_router()
        app.include_router(router)

        @app.get("/admin", response_class=HTMLResponse)
        @app.get("/admin/", response_class=HTMLResponse)
        async def _admin_ui():
            return HTMLResponse(content=ADMIN_HTML)

    @staticmethod
    def unmount(app) -> None:
        """Remove admin routes from the app.

        FastAPI does not natively support route removal.
        In practice, just don't call ``mount()`` if disabled.
        """
        pass
