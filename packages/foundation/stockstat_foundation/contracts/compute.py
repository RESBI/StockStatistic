"""ComputeBackend Protocol — Invocation 与 Compute 的唯一桥梁。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocol.task import TaskSpec


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    HIGH = -1
    NORMAL = 0
    LOW = 1


@dataclass
class TaskInfo:
    """任务状态快照。"""
    task_id: str
    state: TaskState = TaskState.PENDING
    progress: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    worker_id: Optional[str] = None
    slice_id: Optional[str] = None
    n_slices: int = 1
    completed_slices: int = 0
    retry_count: int = 0

    def to_dict(self) -> dict:
        def _iso(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None
        return {
            "task_id": self.task_id,
            "state": self.state.value if isinstance(self.state, TaskState) else str(self.state),
            "progress": self.progress,
            "created_at": _iso(self.created_at),
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "error": self.error,
            "worker_id": self.worker_id,
            "slice_id": self.slice_id,
            "n_slices": self.n_slices,
            "completed_slices": self.completed_slices,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskInfo":
        def _dt(s: Optional[str]) -> Optional[datetime]:
            if not s:
                return None
            try:
                return datetime.fromisoformat(s)
            except (ValueError, TypeError):
                return None
        state = d.get("state", "pending")
        if isinstance(state, str):
            try:
                state = TaskState(state)
            except ValueError:
                state = TaskState.PENDING
        return cls(
            task_id=d["task_id"],
            state=state,
            progress=float(d.get("progress", 0.0)),
            created_at=_dt(d.get("created_at")) or datetime.utcnow(),
            started_at=_dt(d.get("started_at")),
            finished_at=_dt(d.get("finished_at")),
            error=d.get("error"),
            worker_id=d.get("worker_id"),
            slice_id=d.get("slice_id"),
            n_slices=int(d.get("n_slices", 1)),
            completed_slices=int(d.get("completed_slices", 0)),
            retry_count=int(d.get("retry_count", 0)),
        )


@dataclass
class TaskRef:
    """客户端持有的任务句柄。"""
    task_id: str
    backend: Any  # ComputeBackend

    @property
    def id(self) -> str:
        return self.task_id

    @property
    def info(self) -> TaskInfo:
        return self.backend.get(self.task_id)

    @property
    def state(self) -> TaskState:
        return self.backend.get(self.task_id).state

    @property
    def status(self) -> str:
        return self.state.value if isinstance(self.state, TaskState) else str(self.state)

    def ready(self) -> bool:
        s = self.backend.get(self.task_id).state
        return s in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)

    def wait(self, timeout: Optional[float] = None) -> Any:
        return self.backend.wait(self.task_id, timeout=timeout)

    def result(self) -> Any:
        return self.backend.result(self.task_id)

    def cancel(self) -> bool:
        return self.backend.cancel(self.task_id)

    def stream_results(self):
        yield from self.backend.stream_results(self.task_id)


@runtime_checkable
class ComputeBackend(Protocol):
    """统一计算后端协议。"""
    name: str

    def submit(self, spec: "TaskSpec") -> TaskRef: ...
    def get(self, task_id: str) -> TaskInfo: ...
    def result(self, task_id: str) -> Any: ...
    def wait(self, task_id: str, timeout: Optional[float] = None) -> Any: ...
    def cancel(self, task_id: str) -> bool: ...
    def cluster_info(self, **kwargs) -> dict: ...
    def stream_results(self, task_id: str): ...


__all__ = ["ComputeBackend", "TaskRef", "TaskInfo", "TaskState", "TaskPriority"]
