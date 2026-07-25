"""RemoteComputeBackend — submits tasks to a Dispatcher via Transport.

V3 §8.2: When the user passes a RemoteComputeBackend to StockStatClient
or V2Client, all backtest/compute calls are routed through the
Dispatcher instead of executing locally.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from ..contracts.compute import (
    ComputeBackend, TaskInfo, TaskRef, TaskState,
)
from ..contracts.task import TaskSpec
from ..errors import (
    TaskError, TaskNotReadyError, TaskCancelledError,
    TaskTimeoutError, TaskNotFoundError,
)


class RemoteComputeBackend:
    """Remote compute backend — submits via Transport to a Dispatcher.

    All calls are wrapped as Envelopes and sent over the configured
    Transport (HTTP by default; InProcess for testing).
    """

    name = "remote"

    def __init__(self, dispatcher_url: str = None, *,
                 transport=None, storage_url: str = None,
                 poll_interval: float = 0.5):
        if transport is not None:
            self._transport = transport
        elif dispatcher_url:
            from ..transport.http import HttpTransport
            self._transport = HttpTransport(dispatcher_url)
        else:
            from ..transport.in_process import InProcessTransport
            self._transport = InProcessTransport()
        self._dispatcher_url = dispatcher_url
        self._storage_url = storage_url
        self._poll_interval = poll_interval
        self._cache: dict[str, TaskInfo] = {}

    def submit(self, spec: TaskSpec) -> TaskRef:
        """Submit a task to the Dispatcher."""
        # Use direct REST call for simplicity
        if hasattr(self._transport, 'post_json'):
            result = self._transport.post_json("/dispatch/submit", spec.to_dict())
        else:
            # Envelope-based (InProcessTransport)
            from ..protocol.envelope import Envelope, Headers
            from ..protocol.messages import TASK_SUBMIT, CT_TASK_JSON
            env = Envelope(
                type=TASK_SUBMIT,
                headers=Headers(content_type=CT_TASK_JSON, trace_id=spec.trace_id),
                payload=spec.to_dict(),
            )
            reply = self._transport.request(env, timeout=30)
            result = reply.payload if isinstance(reply.payload, dict) else {"task_id": spec.task_id}
        task_id = result.get("task_id", spec.task_id)
        return TaskRef(task_id=task_id, backend=self)

    def get(self, task_id: str) -> TaskInfo:
        if hasattr(self._transport, 'get_json'):
            data = self._transport.get_json(f"/dispatch/status/{task_id}")
        else:
            from ..protocol.envelope import Envelope
            from ..protocol.messages import TASK_STATUS
            env = Envelope(type=TASK_STATUS, payload={"task_id": task_id})
            reply = self._transport.request(env, timeout=10)
            data = reply.payload
        info = TaskInfo.from_dict(data)
        self._cache[task_id] = info
        return info

    def result(self, task_id: str) -> Any:
        info = self.get(task_id)
        if info.state == TaskState.COMPLETED:
            return self._fetch_result(task_id)
        if info.state == TaskState.FAILED:
            raise TaskError(info.error or "task failed",
                            context={"task_id": task_id})
        if info.state == TaskState.CANCELLED:
            raise TaskCancelledError(context={"task_id": task_id})
        raise TaskNotReadyError(context={"task_id": task_id, "state": info.state.value})

    def wait(self, task_id: str, timeout: Optional[float] = None) -> Any:
        deadline = time.time() + (timeout or 3600)
        while time.time() < deadline:
            info = self.get(task_id)
            if info.state == TaskState.COMPLETED:
                return self._fetch_result(task_id)
            if info.state == TaskState.FAILED:
                raise TaskError(info.error or "task failed",
                                context={"task_id": task_id, "error_code": info.error_code})
            if info.state == TaskState.CANCELLED:
                raise TaskCancelledError(context={"task_id": task_id})
            time.sleep(self._poll_interval)
        raise TaskTimeoutError(f"Task {task_id} not finished in {timeout}s",
                               context={"task_id": task_id, "timeout": timeout})

    def cancel(self, task_id: str) -> bool:
        if hasattr(self._transport, 'post_json'):
            result = self._transport.post_json(f"/dispatch/cancel/{task_id}", {})
            return result.get("cancelled", False)
        return False

    def cluster_info(self, **kwargs) -> dict:
        if hasattr(self._transport, 'get_json'):
            return self._transport.get_json("/dispatch/cluster", params=kwargs)
        return {}

    def stream_results(self, task_id: str):
        """Poll for partial results."""
        seen = 0
        while True:
            info = self.get(task_id)
            if info.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                if info.state == TaskState.COMPLETED:
                    yield self._fetch_result(task_id)
                break
            time.sleep(self._poll_interval)

    def _fetch_result(self, task_id: str) -> Any:
        """Fetch and decode the result from the Dispatcher."""
        import base64
        from ..codec import CloudpickleCodec
        if hasattr(self._transport, 'get_json'):
            data = self._transport.get_json(f"/dispatch/result/{task_id}")
            result_b64 = data.get("result")
            if result_b64 and isinstance(result_b64, str):
                raw = base64.b64decode(result_b64)
                return CloudpickleCodec().decode(raw)
            return data.get("result")
        return None
