"""Dispatcher REST API 路由。"""
from __future__ import annotations

import base64

from fastapi import APIRouter, Request, HTTPException

from stockstat_foundation import TaskSpec


def create_dispatcher_router(dispatcher) -> APIRouter:
    router = APIRouter()

    @router.post("/dispatch/submit")
    async def submit_task(req: Request):
        body = await req.json()
        spec = TaskSpec.from_dict(body)
        return dispatcher.submit(spec)

    @router.get("/dispatch/status/{task_id}")
    async def get_status(task_id: str):
        try:
            return dispatcher.get_status(task_id)
        except Exception as e:
            raise HTTPException(404, str(e))

    @router.get("/dispatch/result/{task_id}")
    async def get_result(task_id: str):
        try:
            result_bytes = dispatcher.get_result(task_id)
            return {
                "task_id": task_id,
                "state": "completed",
                "result_codec": "cloudpickle",
                "result": base64.b64encode(result_bytes).decode("ascii"),
            }
        except Exception as e:
            raise HTTPException(409 if "not" in str(e).lower() else 404, str(e))

    @router.post("/dispatch/cancel/{task_id}")
    async def cancel_task(task_id: str):
        return {"cancelled": dispatcher.cancel(task_id)}

    @router.get("/dispatch/cluster")
    async def cluster_info(include_offline: bool = False, include_hardware: bool = True):
        return dispatcher.cluster_info(
            include_offline=include_offline,
            include_hardware=include_hardware,
        )

    @router.post("/dispatch/register")
    async def register_worker(req: Request):
        msg = await req.json()
        return dispatcher.register_worker(msg)

    @router.post("/dispatch/heartbeat")
    async def heartbeat(req: Request):
        msg = await req.json()
        dispatcher.heartbeat(msg)
        return {"status": "ok"}

    @router.post("/dispatch/unregister/{worker_id}")
    async def unregister_worker(worker_id: str):
        dispatcher.unregister_worker(worker_id)
        return {"status": "unregistered"}

    @router.post("/dispatch/assign")
    async def assign_task(req: Request):
        msg = await req.json()
        assignment = dispatcher.assign_task(
            msg.get("worker_id"), msg.get("capabilities", []))
        if assignment is None:
            return {"task_spec": None}
        return assignment

    @router.post("/dispatch/complete")
    async def complete_task(req: Request):
        msg = await req.json()
        dispatcher.on_complete(msg["worker_id"], msg["slice_id"], msg["result"])
        return {"status": "ok"}

    @router.post("/dispatch/fail")
    async def fail_task(req: Request):
        msg = await req.json()
        dispatcher.on_fail(msg["worker_id"], msg["slice_id"], msg.get("error", {}))
        return {"status": "ok"}

    @router.post("/dispatch/partial")
    async def partial_result(req: Request):
        msg = await req.json()
        dispatcher.on_partial(msg["slice_id"], msg.get("partial", {}))
        return {"status": "ok"}

    @router.get("/dispatch/autoscaler")
    async def autoscaler():
        return dispatcher.autoscaler_metrics()

    @router.get("/dispatch/tasks/history")
    async def task_history(limit: int = 100, state: str = None):
        return dispatcher.task_history(limit=limit, state=state)

    return router


__all__ = ["create_dispatcher_router"]
