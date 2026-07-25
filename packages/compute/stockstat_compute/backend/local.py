"""LocalComputeBackend — 进程内直接调用 handler。"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from stockstat_foundation import (
    ComputeBackend, TaskRef, TaskInfo, TaskState, TaskSpec,
)
from stockstat_foundation.errors import TaskError, TaskNotReadyError, TaskTimeoutError

from ..handlers import dispatch as _dispatch
from ..handlers import ALL_TASK_TYPES


@dataclass
class _LocalTaskState:
    spec: TaskSpec
    info: TaskInfo
    result: Any = None
    error: Optional[Exception] = None
    thread: Optional[threading.Thread] = None
    partials: list = field(default_factory=list)
    _done: threading.Event = field(default_factory=threading.Event)


class LocalComputeBackend:
    """本地计算后端 — 进程内直接调用 handler。

    - submit() 在后台线程执行
    - wait() 阻塞等待
    - result() 非阻塞获取
    - 行为等价于直接调用 BacktestEngine
    """
    name = "local"

    def __init__(self, client=None, data_client=None, storage=None, mode: str = "online"):
        self._client = client
        self._data_client = data_client
        self._storage = storage
        self._mode = mode
        self._tasks: dict = {}
        self._lock = threading.Lock()

    def submit(self, spec: TaskSpec) -> TaskRef:
        state = _LocalTaskState(
            spec=spec,
            info=TaskInfo(
                task_id=spec.task_id,
                state=TaskState.PENDING,
            ),
        )
        with self._lock:
            self._tasks[spec.task_id] = state
        t = threading.Thread(target=self._run_local, args=(state,), daemon=True)
        t.start()
        state.thread = t
        return TaskRef(task_id=spec.task_id, backend=self)

    def _run_local(self, state: _LocalTaskState) -> None:
        try:
            state.info.state = TaskState.RUNNING
            state.info.started_at = datetime.utcnow()
            # 提取内联数据（如果有）
            data = None
            cs = state.spec.compute_spec
            if cs.params.get("_inline_data") is not None:
                data = cs.params.pop("_inline_data")
            elif cs.strategies and "_inline_data" in cs.params:
                data = cs.params.pop("_inline_data")
            # 优先用 params 中的 _inline_data
            if data is None and "_inline_data" in cs.params:
                data = cs.params.pop("_inline_data")
            result = _dispatch(
                spec=state.spec,
                data=data,
                worker=None,
            )
            state.result = result
            state.info.state = TaskState.COMPLETED
            state.info.progress = 1.0
        except Exception as e:
            state.error = e
            state.info.state = TaskState.FAILED
            state.info.error = str(e)
        finally:
            state.info.finished_at = datetime.utcnow()
            state._done.set()

    def get(self, task_id: str) -> TaskInfo:
        with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            from stockstat_foundation.errors import TaskNotFoundError
            raise TaskNotFoundError(f"Task not found: {task_id}")
        return state.info

    def result(self, task_id: str) -> Any:
        with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            from stockstat_foundation.errors import TaskNotFoundError
            raise TaskNotFoundError(f"Task not found: {task_id}")
        if state.info.state != TaskState.COMPLETED:
            raise TaskNotReadyError(state.info.state.value if isinstance(state.info.state, TaskState) else str(state.info.state))
        return state.result

    def wait(self, task_id: str, timeout: Optional[float] = None) -> Any:
        with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            from stockstat_foundation.errors import TaskNotFoundError
            raise TaskNotFoundError(f"Task not found: {task_id}")
        if not state._done.wait(timeout=timeout):
            raise TaskTimeoutError(f"Task {task_id} not finished in {timeout}s")
        if state.info.state == TaskState.FAILED:
            raise TaskError(str(state.error) if state.error else "Task failed")
        if state.info.state == TaskState.CANCELLED:
            from stockstat_foundation.errors import TaskCancelledError
            raise TaskCancelledError(task_id)
        return state.result

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            return False
        if state.info.state in (TaskState.PENDING, TaskState.RUNNING):
            state.info.state = TaskState.CANCELLED
            state.info.finished_at = datetime.utcnow()
            state._done.set()
            return True
        return False

    def cluster_info(self, **kwargs) -> dict:
        return {
            "dispatcher": {
                "id": "local",
                "alias": "in-process",
                "status": "online",
                "queue_depth": 0,
            },
            "workers": [{
                "worker_id": "local",
                "alias": "in-process",
                "status": "online",
                "concurrency": 1,
                "active_tasks": sum(
                    1 for s in self._tasks.values()
                    if s.info.state == TaskState.RUNNING
                ),
                "capabilities": list(ALL_TASK_TYPES),
            }],
            "stats": {
                "total_workers": 1,
                "online_workers": 1,
                "total_concurrency": 1,
            },
        }

    def stream_results(self, task_id: str):
        with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            return
        for p in state.partials:
            yield p
        state._done.wait()
        if state.info.state == TaskState.COMPLETED:
            yield state.result

    def compute_indicator(self, name: str, data, **params) -> Any:
        """本地直接计算指标（绕过 TaskSpec，性能优化）。"""
        from ..compute_engine import ComputeEngine
        engine = ComputeEngine()
        return engine.compute(name, data, **params)


__all__ = ["LocalComputeBackend"]
