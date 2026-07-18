"""Dispatcher FastAPI routes — REST endpoints for Client and Worker."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional


def create_dispatcher_router(dispatcher) -> APIRouter:
    """Create the FastAPI router with all dispatch endpoints."""
    router = APIRouter(prefix="/dispatch", tags=["dispatcher"])

    # ── Client-facing endpoints ───────────────────────────────

    @router.post("/submit")
    async def submit_task(request: Request):
        """Client submits a TaskSpec."""
        body = await request.json()
        from stockstat._core.contracts.task import TaskSpec
        spec = TaskSpec.from_dict(body)
        result = dispatcher.submit(spec)
        return result

    @router.get("/status/{task_id}")
    async def get_status(task_id: str):
        """Client queries task status."""
        try:
            return dispatcher.get_status(task_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/result/{task_id}")
    async def get_result(task_id: str):
        """Client fetches task result."""
        try:
            return dispatcher.get_result(task_id)
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.post("/cancel/{task_id}")
    async def cancel_task(task_id: str):
        """Client cancels a task."""
        ok = dispatcher.cancel(task_id)
        return {"cancelled": ok}

    @router.get("/cluster")
    async def cluster_info(include_offline: bool = False):
        """Client queries cluster topology."""
        return dispatcher.cluster_info(include_offline=include_offline)

    # ── Worker-facing endpoints ───────────────────────────────

    @router.post("/register")
    async def register_worker(request: Request):
        """Worker registers on startup."""
        body = await request.json()
        return dispatcher.register_worker(body)

    @router.post("/heartbeat")
    async def heartbeat(request: Request):
        """Worker sends periodic heartbeat."""
        body = await request.json()
        return dispatcher.heartbeat(body)

    @router.post("/unregister/{worker_id}")
    async def unregister_worker(worker_id: str):
        """Worker graceful shutdown."""
        return dispatcher.unregister_worker(worker_id)

    @router.post("/assign")
    async def assign_task(request: Request):
        """Worker pulls a task assignment."""
        body = await request.json()
        worker_id = body.get("worker_id", "")
        capabilities = body.get("capabilities", [])
        result = dispatcher.assign_task(worker_id, capabilities=capabilities)
        if result is None:
            return JSONResponse(status_code=204, content=None)
        return result

    @router.post("/complete")
    async def complete_task(request: Request):
        """Worker posts completed result."""
        body = await request.json()
        worker_id = body.get("worker_id", "")
        slice_id = body.get("slice_id", "")
        result = body.get("result")
        result_codec = body.get("result_codec", "cloudpickle")
        return dispatcher.on_complete(worker_id, slice_id, result, result_codec)

    @router.post("/fail")
    async def fail_task(request: Request):
        """Worker reports failure."""
        body = await request.json()
        return dispatcher.on_fail(
            body.get("worker_id", ""),
            body.get("slice_id", ""),
            body.get("error", "unknown"),
            body.get("traceback", ""),
            body.get("retryable", True),
        )

    @router.post("/partial")
    async def partial_result(request: Request):
        """Worker sends partial result (V2 §13.2)."""
        body = await request.json()
        return dispatcher.on_partial(
            body.get("worker_id", ""),
            body.get("slice_id", ""),
            body.get("partial"),
        )

    # ── Also expose via /api/v1/tasks/* for compatibility ─────

    return router


def create_tasks_router(dispatcher) -> APIRouter:
    """Create /api/v1/tasks/* router for V2 §10.2 compatibility."""
    router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

    @router.post("")
    async def submit_task_api(request: Request):
        body = await request.json()
        from stockstat._core.contracts.task import TaskSpec
        spec = TaskSpec.from_dict(body)
        return dispatcher.submit(spec)

    @router.get("/{task_id}")
    async def get_status_api(task_id: str):
        try:
            return dispatcher.get_status(task_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/{task_id}/result")
    async def get_result_api(task_id: str):
        try:
            return dispatcher.get_result(task_id)
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.delete("/{task_id}")
    async def cancel_task_api(task_id: str):
        ok = dispatcher.cancel(task_id)
        return {"cancelled": ok}

    @router.get("")
    async def list_tasks():
        """List all tasks (simplified — no pagination)."""
        return {"tasks": [tid for tid in dispatcher._tasks.keys()]}

    return router
