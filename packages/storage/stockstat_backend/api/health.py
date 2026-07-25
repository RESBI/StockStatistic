"""Health REST API — /health。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from ..storage.backend import StorageBackendImpl


def create_health_router(backend: StorageBackendImpl) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health():
        try:
            stats = backend.stats()
            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "storage": stats,
            }
        except Exception as e:
            return {
                "status": "degraded",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

    return router
