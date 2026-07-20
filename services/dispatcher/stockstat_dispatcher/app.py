from __future__ import annotations

import json
import time

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from stockstat_contracts import (
    DatasetSnapshotManifest,
    JobSpec,
    token_has_scope,
    token_matches,
    token_principal,
)

from .service import DispatcherService, IdempotencyConflictError, StaleAttemptError
from .store import PostgresTaskStore, SQLiteTaskStore


class HttpSnapshotCoordinator:
    def __init__(self, storage_url: str, internal_token: str | None = None):
        headers = {"Authorization": f"Bearer {internal_token}"} if internal_token else {}
        self.client = httpx.Client(base_url=storage_url.rstrip("/"), headers=headers, timeout=120.0)

    def resolve(self, binding):
        response = self.client.post(
            "/internal/v31/snapshots", json=binding.dataset.model_dump(mode="json")
        )
        response.raise_for_status()
        return DatasetSnapshotManifest.model_validate(response.json())


def create_app(
    database_url: str,
    storage_url: str,
    *,
    token_scopes: dict[str, frozenset[str]] | None = None,
    internal_token: str | None = None,
) -> FastAPI:
    if database_url.startswith("postgresql://"):
        store = PostgresTaskStore(database_url)
    else:
        store = SQLiteTaskStore(database_url.removeprefix("sqlite:///"))
    store.initialize()
    service = DispatcherService(store, HttpSnapshotCoordinator(storage_url, internal_token))
    app = FastAPI(title="StockStat Dispatcher", version="3.1.0")
    app.state.dispatcher = service

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 1_048_576:
            return JSONResponse({"detail": "CONTROL_MESSAGE_TOO_LARGE"}, status_code=413)
        scope = _dispatcher_scope(request.url.path)
        authorization = request.headers.get("authorization")
        if scope == "internal":
            if not token_matches(authorization, internal_token):
                return JSONResponse({"detail": "INVALID_WORKLOAD_TOKEN"}, status_code=401)
        elif scope and not token_has_scope(authorization, scope, token_scopes):
            return JSONResponse({"detail": f"MISSING_SCOPE:{scope}"}, status_code=403)
        return await call_next(request)

    @app.get("/v31/meta")
    def meta():
        return {
            "service": "dispatcher",
            "service_version": "3.1.0",
            "protocol_versions": ["3.1"],
            "event_media_types": ["text/event-stream"],
            "limits": {"max_control_bytes": 1_048_576},
        }

    @app.get("/health/live")
    def live():
        return {"status": "live"}

    @app.get("/health/ready")
    def ready():
        try:
            store.fetchone("SELECT 1 ready")
            return {"status": "ready"}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="DATABASE_UNAVAILABLE") from exc

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics():
        return service.prometheus_metrics()

    @app.post("/v31/jobs", status_code=202)
    def submit(
        request: Request,
        spec: JobSpec,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ):
        try:
            principal = token_principal(request.headers.get("authorization"), token_scopes)
            job_id = service.submit(spec, idempotency_key, principal=principal)
            return {"job_id": job_id, "state": service.get_status(job_id)["state"]}
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v31/jobs/{job_id}")
    def status(request: Request, job_id: str):
        try:
            return service.get_status(
                job_id,
                principal=token_principal(request.headers.get("authorization"), token_scopes),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v31/jobs/{job_id}/result")
    def result(request: Request, job_id: str):
        try:
            return service.result(
                job_id,
                principal=token_principal(request.headers.get("authorization"), token_scopes),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v31/jobs/{job_id}/cancel")
    def cancel(request: Request, job_id: str, payload: dict):
        try:
            return {
                "state": service.cancel(
                    job_id,
                    payload.get("reason", ""),
                    principal=token_principal(request.headers.get("authorization"), token_scopes),
                )
            }
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v31/jobs/{job_id}/events.json")
    def events_json(request: Request, job_id: str, after: int = 0):
        try:
            return {
                "events": service.events(
                    job_id,
                    after,
                    principal=token_principal(request.headers.get("authorization"), token_scopes),
                )
            }
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v31/jobs/{job_id}/events")
    def events(
        request: Request,
        job_id: str,
        after: int = Query(default=0, alias="after"),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        principal = token_principal(request.headers.get("authorization"), token_scopes)
        try:
            service.get_status(job_id, principal=principal)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if last_event_id:
            try:
                after = max(after, int(last_event_id))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="INVALID_LAST_EVENT_ID") from exc

        def stream():
            sequence = after
            idle = 0
            while True:
                items = service.events(job_id, sequence, principal=principal)
                for item in items:
                    sequence = item["sequence"]
                    yield (
                        f"id: {sequence}\n"
                        f"event: {item['event_type']}\n"
                        f"data: {json.dumps(item, separators=(',', ':'))}\n\n"
                    )
                    idle = 0
                state = service.get_status(job_id, principal=principal)["state"]
                if state in {"succeeded", "failed", "cancelled", "expired"}:
                    return
                idle += 1
                if idle % 20 == 0:
                    yield ": heartbeat\n\n"
                time.sleep(0.1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/v31/capabilities")
    def capabilities():
        workers = store.fetchall(
            "SELECT capabilities_json FROM workers WHERE state = ?", ("ready",)
        )
        values = {}
        for worker in workers:
            payload = worker["capabilities_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            for item in payload:
                values.setdefault(item["capability_id"], set()).update(item["versions"])
        return {
            "capabilities": [
                {"id": capability_id, "versions": sorted(versions)}
                for capability_id, versions in sorted(values.items())
            ]
        }

    @app.get("/v31/cluster")
    def cluster():
        workers = store.fetchall("SELECT * FROM workers ORDER BY worker_id")
        for worker in workers:
            for field in ("capabilities_json", "resources_json"):
                if isinstance(worker[field], str):
                    worker[field] = json.loads(worker[field])
        return {
            "workers": workers,
            "queued_work_units": store.fetchone(
                "SELECT COUNT(*) count FROM work_units WHERE state = ?", ("ready",)
            )["count"],
        }

    @app.get("/v31/cluster/autoscaling")
    def autoscaling():
        return service.autoscaling_metrics()

    @app.post("/v31/cluster/workers/{worker_id}/drain")
    def drain(worker_id: str):
        service.set_worker_state(worker_id, "draining")
        return {"worker_id": worker_id, "state": "draining"}

    @app.post("/internal/v31/workers/register")
    def register(payload: dict):
        service.register_worker(
            payload["worker_id"],
            payload["worker_session_id"],
            payload["capabilities"],
            payload["resources"],
        )
        return {"accepted": True, "heartbeat_interval_seconds": 10, "default_lease_ttl_seconds": 60}

    @app.post("/internal/v31/work/claim")
    def claim(payload: dict):
        leases = service.claim(
            payload["worker_id"],
            payload["worker_session_id"],
            payload["capabilities"],
            payload.get("max_items", 1),
            payload.get("lease_ttl_seconds", 60),
            payload.get("wait_seconds", 0),
        )
        return {"leases": [lease.model_dump(mode="json") for lease in leases]}

    @app.post("/internal/v31/attempts/{attempt_id}/start")
    def start(attempt_id: str, payload: dict):
        _attempt(service.start, attempt_id, payload)
        return {"accepted": True}

    @app.post("/internal/v31/attempts/{attempt_id}/renew")
    def renew(attempt_id: str, payload: dict):
        return _attempt(service.renew, attempt_id, payload, progress=payload.get("progress"))

    @app.post("/internal/v31/attempts/{attempt_id}/complete")
    def complete(attempt_id: str, payload: dict):
        return _attempt(
            service.complete,
            attempt_id,
            payload,
            completion_id=payload["completion_id"],
            result=payload["result"],
        )

    @app.post("/internal/v31/attempts/{attempt_id}/fail")
    def fail(attempt_id: str, payload: dict):
        return _attempt(
            service.fail,
            attempt_id,
            payload,
            failure_id=payload["failure_id"],
            error=payload["error"],
        )

    return app


def _attempt(function, attempt_id, payload, **kwargs):
    try:
        return function(attempt_id, payload["lease_token"], payload["worker_session_id"], **kwargs)
    except StaleAttemptError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _dispatcher_scope(path: str) -> str | None:
    if path.startswith("/internal/"):
        return "internal"
    if path.startswith(("/health/", "/metrics")) or path == "/v31/meta":
        return None
    if path.startswith(("/v31/cluster", "/v31/capabilities")):
        return "cluster"
    if path.startswith("/v31/jobs"):
        return "jobs"
    return None
