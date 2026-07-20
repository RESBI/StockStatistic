from __future__ import annotations

import httpx
from stockstat_contracts import WorkLease


class HttpDispatcherClient:
    def __init__(self, base_url: str, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=120.0)

    def register_worker(self, worker_id, session_id, capabilities, resources):
        response = self.client.post(
            "/internal/v31/workers/register",
            json={
                "worker_id": worker_id,
                "worker_session_id": session_id,
                "capabilities": capabilities,
                "resources": resources,
            },
        )
        response.raise_for_status()
        return response.json()

    def claim(
        self, worker_id, session_id, capabilities, max_items=1, lease_ttl_seconds=60, wait_seconds=0
    ):
        response = self.client.post(
            "/internal/v31/work/claim",
            json={
                "worker_id": worker_id,
                "worker_session_id": session_id,
                "capabilities": capabilities,
                "max_items": max_items,
                "lease_ttl_seconds": lease_ttl_seconds,
                "wait_seconds": wait_seconds,
            },
        )
        response.raise_for_status()
        return [WorkLease.model_validate(item) for item in response.json()["leases"]]

    def start(self, attempt_id, lease_token, worker_session_id):
        self._post(attempt_id, "start", lease_token, worker_session_id)

    def renew(
        self, attempt_id, lease_token, worker_session_id, lease_ttl_seconds=60, progress=None
    ):
        return self._post(
            attempt_id,
            "renew",
            lease_token,
            worker_session_id,
            {"lease_ttl_seconds": lease_ttl_seconds, "progress": progress},
        )

    def complete(self, attempt_id, lease_token, worker_session_id, completion_id, result):
        return self._post(
            attempt_id,
            "complete",
            lease_token,
            worker_session_id,
            {"completion_id": completion_id, "result": result},
        )

    def fail(self, attempt_id, lease_token, worker_session_id, failure_id, error):
        return self._post(
            attempt_id,
            "fail",
            lease_token,
            worker_session_id,
            {"failure_id": failure_id, "error": error},
        )

    def _post(self, attempt_id, action, token, session_id, extra=None):
        payload = {"lease_token": token, "worker_session_id": session_id, **(extra or {})}
        response = self.client.post(f"/internal/v31/attempts/{attempt_id}/{action}", json=payload)
        response.raise_for_status()
        return response.json()

    def close(self):
        self.client.close()
