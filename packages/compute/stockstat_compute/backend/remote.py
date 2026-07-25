"""RemoteComputeBackend — 通过 HTTP 提交到 Dispatcher。"""
from __future__ import annotations

import base64
import time
from typing import Any, Optional

from stockstat_foundation import (
    ComputeBackend, TaskRef, TaskInfo, TaskState, TaskSpec,
)
from stockstat_foundation.errors import (
    TaskError, TaskCancelledError, TaskTimeoutError,
)
from stockstat_foundation.codec import CloudpickleCodec


class RemoteComputeBackend:
    """远程计算后端 — 通过 HTTP 直接调用 Dispatcher REST API。"""
    name = "remote"

    def __init__(self, dispatcher_url: str = None, *,
                 transport=None,
                 storage_url: Optional[str] = None,
                 codec: str = "cloudpickle",
                 poll_interval: float = 0.5,
                 http_client=None):
        self._dispatcher_url = (dispatcher_url or "").rstrip("/")
        self._storage_url = storage_url
        self._codec = codec
        self._poll_interval = poll_interval
        # 优先使用传入的 http_client（方便测试用 TestClient）
        if http_client is not None:
            self._http = http_client
        elif self._dispatcher_url:
            import httpx
            self._http = httpx.Client(timeout=30)
        elif transport is not None:
            # 兼容 transport 参数（但不常用）
            self._transport = transport
            self._http = None
        else:
            raise ValueError("dispatcher_url or http_client required")
        self._cache: dict = {}

    @property
    def base_url(self) -> str:
        return self._dispatcher_url

    def submit(self, spec: TaskSpec) -> TaskRef:
        # 提取不可 JSON 序列化的 _inline_data，编码为 base64 cloudpickle
        spec_dict = spec.to_dict()
        inline = spec.compute_spec.params.get("_inline_data")
        if inline is not None and not isinstance(inline, (int, float, str, bool, list, dict, type(None))):
            import base64 as _b64
            encoded = CloudpickleCodec().encode(inline)
            spec_dict["compute_spec"]["params"]["_inline_data_b64"] = _b64.b64encode(encoded).decode("ascii")
            spec_dict["compute_spec"]["params"].pop("_inline_data", None)
        resp = self._http.post(
            f"{self._dispatcher_url}/dispatch/submit",
            json=spec_dict,
        )
        ack = resp.json()
        task_id = ack.get("task_id", spec.task_id)
        return TaskRef(task_id=task_id, backend=self)

    def get(self, task_id: str) -> TaskInfo:
        resp = self._http.get(f"{self._dispatcher_url}/dispatch/status/{task_id}")
        payload = resp.json()
        if "task_id" not in payload:
            payload["task_id"] = task_id
        info = TaskInfo.from_dict(payload)
        self._cache[task_id] = info
        return info

    def result(self, task_id: str) -> Any:
        resp = self._http.get(f"{self._dispatcher_url}/dispatch/result/{task_id}")
        payload = resp.json()
        if "result" in payload:
            result_b64 = payload["result"]
            result_bytes = base64.b64decode(result_b64)
            return CloudpickleCodec().decode(result_bytes)
        return payload

    def wait(self, task_id: str, timeout: Optional[float] = None) -> Any:
        deadline = time.time() + (timeout or 3600)
        while time.time() < deadline:
            info = self.get(task_id)
            if info.state == TaskState.COMPLETED:
                return self.result(task_id)
            if info.state == TaskState.FAILED:
                raise TaskError(info.error or "Task failed")
            if info.state == TaskState.CANCELLED:
                raise TaskCancelledError(task_id)
            time.sleep(self._poll_interval)
        raise TaskTimeoutError(f"Task {task_id} not finished in {timeout}s")

    def cancel(self, task_id: str) -> bool:
        resp = self._http.post(f"{self._dispatcher_url}/dispatch/cancel/{task_id}")
        return resp.json().get("cancelled", False)

    def cluster_info(self, **kwargs) -> dict:
        try:
            params = {}
            if kwargs.get("include_offline"):
                params["include_offline"] = "true"
            resp = self._http.get(f"{self._dispatcher_url}/dispatch/cluster",
                                   params=params, timeout=5)
            return resp.json()
        except Exception:
            return {"status": "unavailable"}

    def stream_results(self, task_id: str):
        while True:
            info = self.get(task_id)
            if info.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                if info.state == TaskState.COMPLETED:
                    yield self.result(task_id)
                break
            time.sleep(self._poll_interval)


__all__ = ["RemoteComputeBackend"]
