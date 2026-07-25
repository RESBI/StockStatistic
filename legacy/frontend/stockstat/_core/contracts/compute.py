"""Compute backend protocol — abstracts where computation happens.

V3 introduces distributed compute offload. This protocol decouples
"what to compute" (business logic in backtest/indicators/etc.) from
"where to compute" (in-process vs. remote dispatcher vs. auto-routed).

Implementations:
- LocalComputeBackend: in-process, directly calls BacktestEngine etc.
- RemoteComputeBackend: submits TaskSpec to a Dispatcher via Transport
- AutoComputeBackend: routes by task size / type

The v1.7 ``StockStatClient`` and v2 ``V2Client`` both accept an optional
``compute_backend`` parameter. When omitted (default), a
``LocalComputeBackend`` is used and behavior is identical to v2.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class TaskState(str, Enum):
    """Lifecycle state of a task.

    String values are stable for protocol serialization (V2 §12.4).
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """Task status snapshot — V2 §12.4 ``task.status.reply`` payload.

    Serializable to JSON for protocol transmission.
    """

    task_id: str
    state: TaskState = TaskState.PENDING
    progress: float = 0.0  # 0.0 ~ 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    worker_id: Optional[str] = None  # which worker is running/ran this task
    slice_id: Optional[str] = None  # slice identifier for sharded tasks
    retry_count: int = 0

    def to_dict(self) -> dict:
        """JSON-serializable representation for protocol transmission."""
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "progress": self.progress,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "error_code": self.error_code,
            "worker_id": self.worker_id,
            "slice_id": self.slice_id,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskInfo":
        def _parse_ts(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(s)
            except (ValueError, TypeError):
                return None

        state_val = d.get("state", "pending")
        if isinstance(state_val, str):
            try:
                state = TaskState(state_val)
            except ValueError:
                state = TaskState.PENDING
        elif isinstance(state_val, TaskState):
            state = state_val
        else:
            state = TaskState.PENDING

        return cls(
            task_id=d["task_id"],
            state=state,
            progress=float(d.get("progress", 0.0)),
            created_at=_parse_ts(d.get("created_at")) or datetime.utcnow(),
            started_at=_parse_ts(d.get("started_at")),
            finished_at=_parse_ts(d.get("finished_at")),
            error=d.get("error"),
            error_code=d.get("error_code"),
            worker_id=d.get("worker_id"),
            slice_id=d.get("slice_id"),
            retry_count=int(d.get("retry_count", 0)),
        )


@dataclass
class TaskRef:
    """Client-side handle to a submitted task.

    Holds a back-reference to the ComputeBackend so callers can use
    ``task.wait()`` / ``task.result()`` / ``task.cancel()`` directly
    without managing task IDs manually.

    Mirrors V1 §5.2 ``task.id`` / ``task.status`` / ``task.wait()``
    / ``task.ready()`` / ``task.result()`` user API.
    """

    task_id: str
    backend: "ComputeBackend"

    @property
    def id(self) -> str:
        return self.task_id

    @property
    def state(self) -> TaskState:
        return self.backend.get(self.task_id).state

    @property
    def status(self) -> str:
        """String state for V1 API compatibility."""
        return self.state.value

    def ready(self) -> bool:
        """True if task is in a terminal state (completed/failed/cancelled)."""
        info = self.backend.get(self.task_id)
        return info.state in (
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        )

    def wait(self, timeout: Optional[float] = None) -> Any:
        """Block until task completes; return result (raise on failure)."""
        return self.backend.wait(self.task_id, timeout=timeout)

    def result(self) -> Any:
        """Non-blocking result fetch; raises TaskNotReadyError if not done."""
        return self.backend.result(self.task_id)

    def cancel(self) -> bool:
        """Request cancellation. Returns True if request was accepted."""
        return self.backend.cancel(self.task_id)

    def stream_results(self):
        """Iterate over partial results (V2 §13.2).

        For backends that don't support streaming, yields a single
        final result after completion.
        """
        yield from self.backend.stream_results(self.task_id)


@runtime_checkable
class ComputeBackend(Protocol):
    """Unified compute backend protocol — V3 compatibility layer core.

    Three implementations share this protocol:
    - LocalComputeBackend: in-process direct call to BacktestEngine etc.
    - RemoteComputeBackend: submits via Transport to a Dispatcher
    - AutoComputeBackend: routes by data size / task type

    The v1.7 StockStatClient and v2 V2Client both depend on this
    protocol (not on any concrete implementation), keeping them
    decoupled from the actual compute location.
    """

    name: str

    def submit(self, spec: "TaskSpec") -> TaskRef: ...
    def get(self, task_id: str) -> TaskInfo: ...
    def result(self, task_id: str) -> Any: ...
    def wait(self, task_id: str, timeout: Optional[float] = None) -> Any: ...
    def cancel(self, task_id: str) -> bool: ...
    def cluster_info(self, **kwargs) -> dict: ...
    def stream_results(self, task_id: str): ...
