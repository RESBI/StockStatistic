"""Dispatcher 主体 — 状态管理 + 调度循环。"""
from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

from stockstat_foundation import (
    TaskSpec, TaskInfo, TaskState, Config, StorageBackend,
)
from stockstat_foundation.errors import TaskNotFoundError, TaskNotReadyError
from stockstat_foundation.codec import CloudpickleCodec

from .queue import MemoryTaskQueue, build_queue
from .workers import WorkerRegistry
from .prefetch import DataCache
from .shard import shard_task
from .merge import merge_results


@dataclass
class _TaskState:
    spec: TaskSpec
    info: TaskInfo
    slices: list = field(default_factory=list)
    slices_by_id: dict = field(default_factory=dict)
    assigned_slices: dict = field(default_factory=dict)
    partial_results: dict = field(default_factory=dict)
    merged_result_bytes: bytes = b""
    stream_partials: list = field(default_factory=list)


class Dispatcher:
    """Central task dispatcher — V3.1 核心。"""

    def __init__(
        self,
        *,
        queue=None,
        storage_url: Optional[str] = None,
        storage_backend: Optional[StorageBackend] = None,
        cache_dir: Optional[str] = None,
        cache_size_mb: int = 512,
        offline_timeout: float = 30.0,
        alias: str = "dispatch-primary",
        parent_url: Optional[str] = None,
        config: Optional[Config] = None,
    ):
        self._config = config or Config.from_env()
        self._queue = queue or self._build_queue()
        self._storage_url = storage_url
        self._storage_backend = storage_backend
        self._cache = DataCache(cache_dir, max_size_mb=cache_size_mb)
        self._workers = WorkerRegistry(offline_timeout=offline_timeout)
        self._tasks: dict = {}
        self._lock = threading.Lock()
        self._alias = alias
        self._parent_url = parent_url
        self._sub_dispatchers: dict = {}
        self._task_history: list = []
        self._history_max = 1000
        self._started_at = datetime.utcnow()
        self._checker = threading.Thread(target=self._check_loop, daemon=True)
        self._checker.start()

    def _build_queue(self):
        if self._config.dispatcher_queue == "redis":
            if not self._config.redis_url:
                raise ValueError("redis_url required for redis queue")
            return build_queue("redis", self._config.redis_url)
        return MemoryTaskQueue()

    # ── Client 接口 ──

    def submit(self, spec: TaskSpec) -> dict:
        with self._lock:
            self._tasks[spec.task_id] = _TaskState(
                spec=spec,
                info=TaskInfo(task_id=spec.task_id, state=TaskState.PENDING),
            )
        slices = shard_task(spec)
        with self._lock:
            state = self._tasks[spec.task_id]
            state.slices = slices
            state.info.n_slices = len(slices)
            state.slices_by_id = {s.task_id: s for s in slices}
        for slice_spec in slices:
            self._queue.enqueue(slice_spec)
        return {
            "task_id": spec.task_id,
            "status": "pending",
            "n_slices": len(slices),
        }

    def get_status(self, task_id: str) -> dict:
        with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        info = state.info
        return {
            "task_id": info.task_id,
            "state": info.state.value if isinstance(info.state, TaskState) else str(info.state),
            "progress": info.progress,
            "n_slices": info.n_slices,
            "completed_slices": info.completed_slices,
            "worker_id": info.worker_id,
            "error": info.error,
            "created_at": info.created_at.isoformat() if info.created_at else None,
            "started_at": info.started_at.isoformat() if info.started_at else None,
            "finished_at": info.finished_at.isoformat() if info.finished_at else None,
        }

    def get_result(self, task_id: str) -> bytes:
        with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if state.info.state != TaskState.COMPLETED:
            raise TaskNotReadyError(state.info.state.value if isinstance(state.info.state, TaskState) else str(state.info.state))
        return state.merged_result_bytes

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            state = self._tasks.get(task_id)
        if state is None:
            return False
        state.info.state = TaskState.CANCELLED
        state.info.finished_at = datetime.utcnow()
        self._record_history(state)
        return True

    # ── Worker 接口 ──

    def register_worker(self, msg: dict) -> dict:
        wid = self._workers.register(msg)
        return {"worker_id": wid, "status": "registered"}

    def heartbeat(self, msg: dict) -> None:
        self._workers.update_heartbeat(msg)

    def unregister_worker(self, worker_id: str) -> None:
        self._workers.unregister(worker_id)

    def assign_task(self, worker_id: str, capabilities: list) -> Optional[dict]:
        skipped = []
        while True:
            spec = self._queue.dequeue(block=False)
            if spec is None:
                for s in skipped:
                    self._queue.enqueue(s)
                return None
            task_type = spec.compute_spec.task_type
            if task_type in capabilities or "custom" in capabilities:
                return self._prepare_assignment(spec, worker_id)
            skipped.append(spec)

    def _prepare_assignment(self, spec: TaskSpec, worker_id: str) -> dict:
        # 数据预取
        data_ref = self._prefetch_data(spec)
        # 更新任务状态
        parent_id = spec.task_id.rsplit("-s", 1)[0] if "-s" in spec.task_id else spec.task_id
        with self._lock:
            parent_state = self._tasks.get(parent_id)
            if parent_state:
                parent_state.assigned_slices[spec.task_id] = worker_id
                if parent_state.info.state == TaskState.PENDING:
                    parent_state.info.state = TaskState.RUNNING
                    parent_state.info.started_at = datetime.utcnow()
                parent_state.info.worker_id = worker_id
        self._workers.increment_active(worker_id)
        # 编码数据
        data_bytes = self._cache.fetch_bytes(data_ref)
        data_b64 = base64.b64encode(data_bytes).decode("ascii")
        # 构造 task_spec dict，移除内联数据（已通过 data 字段传输）
        spec_dict = spec.to_dict()
        spec_dict.get("compute_spec", {}).get("params", {}).pop("_inline_data", None)
        spec_dict.get("compute_spec", {}).get("params", {}).pop("_inline_data_b64", None)
        return {
            "task_spec": spec_dict,
            "data_ref": data_ref,
            "data": data_b64,
            "data_codec": "cloudpickle",
        }

    def on_complete(self, worker_id: str, slice_id: str, result_b64: str) -> None:
        result_bytes = base64.b64decode(result_b64)
        parent_id = slice_id.rsplit("-s", 1)[0] if "-s" in slice_id else slice_id
        with self._lock:
            state = self._tasks.get(parent_id)
            if state is None:
                return
            state.partial_results[slice_id] = result_bytes
            state.info.completed_slices += 1
            state.info.progress = state.info.completed_slices / state.info.n_slices if state.info.n_slices > 0 else 1.0
        self._workers.decrement_active(worker_id, completed=True)
        with self._lock:
            state = self._tasks.get(parent_id)
            if state and state.info.completed_slices == state.info.n_slices:
                state.merged_result_bytes = merge_results(state)
                state.info.state = TaskState.COMPLETED
                state.info.finished_at = datetime.utcnow()
                state.info.progress = 1.0
                self._record_history(state)

    def on_fail(self, worker_id: str, slice_id: str, error: dict) -> None:
        parent_id = slice_id.rsplit("-s", 1)[0] if "-s" in slice_id else slice_id
        with self._lock:
            state = self._tasks.get(parent_id)
            if state is None:
                return
            state.info.state = TaskState.FAILED
            state.info.error = error.get("error_message", "Unknown error")
            state.info.finished_at = datetime.utcnow()
        self._workers.decrement_active(worker_id, completed=False, failed=True)
        with self._lock:
            state = self._tasks.get(parent_id)
            if error.get("retryable", False) and state and state.info.retry_count < 3:
                state.info.retry_count += 1
                state.info.state = TaskState.PENDING
                self._queue.enqueue(state.spec)
            elif state:
                self._record_history(state)

    def on_partial(self, slice_id: str, partial: dict) -> None:
        parent_id = slice_id.rsplit("-s", 1)[0] if "-s" in slice_id else slice_id
        with self._lock:
            state = self._tasks.get(parent_id)
            if state is None:
                return
            state.stream_partials.append(partial)

    # ── 数据预取 ──

    def _prefetch_data(self, spec: TaskSpec) -> str:
        cache_key = spec.data_spec.cache_key()
        ref = self._cache.get_ref(cache_key)
        if ref:
            return ref
        # 检查内联数据（_inline_data 或 _inline_data_b64）
        inline = spec.compute_spec.params.get("_inline_data")
        if inline is None:
            inline_b64 = spec.compute_spec.params.get("_inline_data_b64")
            if inline_b64 is not None:
                inline = CloudpickleCodec().decode(base64.b64decode(inline_b64))
                spec.compute_spec.params["_inline_data"] = inline
        if inline is not None:
            data_bytes = CloudpickleCodec().encode(inline)
            return self._cache.put(cache_key, data_bytes)
        # 从 Storage 拉取
        if spec.data_spec.symbols:
            data = self._fetch_from_storage(spec.data_spec)
            data_bytes = CloudpickleCodec().encode(data)
            return self._cache.put(cache_key, data_bytes)
        # 无数据
        return self._cache.put(cache_key, CloudpickleCodec().encode(None))

    def _fetch_from_storage(self, data_spec):
        if self._storage_backend is not None:
            return self._storage_backend.fetch_ohlcv(
                symbols=data_spec.symbols, timeframe=data_spec.timeframe,
                start=data_spec.start, end=data_spec.end, source=data_spec.source,
            )
        if self._storage_url:
            import httpx
            from stockstat_foundation.codec import ArrowCodec
            params = {
                "symbol": ",".join(data_spec.symbols),
                "timeframe": data_spec.timeframe,
            }
            if data_spec.start:
                params["start"] = data_spec.start
            if data_spec.end:
                params["end"] = data_spec.end
            resp = httpx.get(f"{self._storage_url}/api/v1/ohlcv", params=params, timeout=30)
            return ArrowCodec().decode(resp.content)
        return None

    # ── 集群信息 ──

    def cluster_info(self, **kwargs) -> dict:
        return {
            "dispatcher": {
                "id": self._alias,
                "alias": self._alias,
                "address": self._storage_url or "in-process",
                "status": "online",
                "uptime_s": (datetime.utcnow() - self._started_at).total_seconds(),
                "queue_depth": self._queue.size(),
                "cache_size_mb": self._cache.size_mb(),
                "cache_hit_rate": self._cache.hit_rate(),
            },
            "workers": self._workers.list_workers(**kwargs),
            "sub_dispatchers": list(self._sub_dispatchers.values()),
            "stats": self._workers.stats(),
        }

    def autoscaler_metrics(self) -> dict:
        stats = self._workers.stats()
        return {
            "queue_depth": self._queue.size(),
            "active_tasks": stats["active_tasks"],
            "total_concurrency": stats["total_concurrency"],
            "available_concurrency": stats["available_concurrency"],
            "online_workers": stats["online_workers"],
            "scale_up_recommended": (
                self._queue.size() > 20 and stats["available_concurrency"] == 0
            ),
            "scale_down_recommended": (
                self._queue.size() == 0 and stats["available_concurrency"] > 0
                and stats["active_tasks"] == 0
            ),
        }

    def task_history(self, limit: int = 100, state: str = None) -> dict:
        with self._lock:
            history = list(self._task_history[-limit:])
        if state:
            history = [h for h in history if h.get("state") == state]
        return {"history": history, "total": len(self._task_history)}

    # ── 后台线程 ──

    def _check_loop(self) -> None:
        while True:
            time.sleep(10)
            timed_out = self._workers.check_timeouts()
            for worker_id in timed_out:
                self._reassign_worker_tasks(worker_id)

    def _reassign_worker_tasks(self, worker_id: str) -> None:
        with self._lock:
            for state in self._tasks.values():
                for slice_id, wid in list(state.assigned_slices.items()):
                    if wid == worker_id:
                        del state.assigned_slices[slice_id]
                        slice_spec = state.slices_by_id.get(slice_id)
                        if slice_spec:
                            self._queue.enqueue(slice_spec)

    def _record_history(self, state: _TaskState) -> None:
        self._task_history.append({
            "task_id": state.info.task_id,
            "task_type": state.spec.compute_spec.task_type,
            "state": state.info.state.value if isinstance(state.info.state, TaskState) else str(state.info.state),
            "created_at": state.info.created_at.isoformat() if state.info.created_at else None,
            "started_at": state.info.started_at.isoformat() if state.info.started_at else None,
            "finished_at": state.info.finished_at.isoformat() if state.info.finished_at else None,
            "duration_s": (state.info.finished_at - state.info.started_at).total_seconds()
                          if state.info.started_at and state.info.finished_at else None,
            "worker_id": state.info.worker_id,
            "error": state.info.error,
            "trace_id": state.spec.trace_id,
        })
        if len(self._task_history) > self._history_max:
            self._task_history = self._task_history[-self._history_max:]


__all__ = ["Dispatcher"]
