"""Dispatcher core — task scheduling, state management, and result merging.

The Dispatcher is the central coordinator:
1. Receives TaskSpec submissions from Clients
2. Prefetches data from Storage (once, cached)
3. Shards tasks for parallel execution
4. Distributes slices to Workers (pull model)
5. Merges results from completed slices
6. Returns final results to Clients
"""
from __future__ import annotations

import base64
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .queue import MemoryTaskQueue, TaskQueue, build_queue
from .workers import WorkerRegistry
from .prefetch import DataCache
from .dispatch import shard_task


@dataclass
class _TaskState:
    """Internal state for a submitted task."""
    spec: Any  # TaskSpec
    info: Any  # TaskInfo
    slices: list = field(default_factory=list)  # sharded TaskSpec list
    assigned: dict = field(default_factory=dict)  # slice_id -> worker_id
    partial_results: dict = field(default_factory=dict)  # slice_id -> result
    merged_result: Any = None
    data_ref: str = ""
    data_cache_key: str = ""
    error: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class Dispatcher:
    """Central task dispatcher — V2 §2.1 core component.

    Thread-safe; designed to run inside a FastAPI app. Workers pull
    tasks via ``assign_task()``; results are posted back via
    ``on_complete()`` / ``on_fail()``.

    P7: supports multi-level Dispatcher topology — sub-Dispatchers
    can register themselves, and ``cluster_info`` includes the full
    hierarchy.
    """

    def __init__(self, *, queue: TaskQueue = None, storage_url: str = None,
                 cache_dir: str = None, cache_size_mb: int = 512,
                 offline_timeout: float = 30.0,
                 storage_app=None,
                 alias: str = "dispatch-primary",
                 parent_url: str = None):
        self._queue = queue or MemoryTaskQueue()
        self._storage_url = storage_url or "http://localhost:8000"
        self._storage_app = storage_app  # FastAPI app for same-process data access
        self._cache = DataCache(max_size_mb=cache_size_mb, cache_dir=cache_dir)
        self._workers = WorkerRegistry(offline_timeout=offline_timeout)
        self._tasks: dict[str, _TaskState] = {}
        self._lock = threading.Lock()
        self._started_at = time.time()
        # P7: multi-level Dispatcher state
        self._alias = alias
        self._parent_url = parent_url  # if set, this is a sub-dispatcher
        self._sub_dispatchers: dict[str, dict] = {}  # sub_id -> {alias, address, status}
        self._task_history: list[dict] = []  # P7: task history for Admin UI
        self._history_max = 1000  # keep last 1000 completed tasks
        # Start background heartbeat checker
        self._checker = threading.Thread(target=self._check_loop, daemon=True)
        self._checker.start()

    # ── Client-facing API (called by routes.py) ───────────────

    def submit(self, spec) -> dict:
        """Accept a task submission. Returns {task_id, status}."""
        from stockstat._core.contracts.compute import TaskInfo, TaskState
        state = _TaskState(
            spec=spec,
            info=TaskInfo(
                task_id=spec.task_id,
                state=TaskState.PENDING,
                created_at=spec.created_at,
            ),
        )
        with self._lock:
            self._tasks[spec.task_id] = state
        # Shard the task
        max_workers = spec.dispatch_spec.max_workers or 4
        slices = shard_task(spec, max_workers=max_workers)
        state.slices = slices
        # Enqueue all slices
        for s in slices:
            self._queue.enqueue(s)
        return {"task_id": spec.task_id, "status": "pending",
                "n_slices": len(slices)}

    def get_status(self, task_id: str) -> dict:
        state = self._get_task(task_id)
        return state.info.to_dict()

    def get_result(self, task_id: str) -> dict:
        """Return the merged result. Raises if not ready."""
        from stockstat._core.errors import TaskNotReadyError
        from stockstat._core.contracts.compute import TaskState
        import base64
        state = self._get_task(task_id)
        if state.info.state != TaskState.COMPLETED:
            raise TaskNotReadyError(
                f"Task {task_id} is {state.info.state.value}",
                context={"task_id": task_id, "state": state.info.state.value},
            )
        # merged_result may be either a Python object (decoded) or a
        # base64 string (single-slice pass-through). Normalise to base64
        # so the wire format is consistent.
        merged = state.merged_result
        if isinstance(merged, str) and merged.startswith("cloudpickle:"):
            # Already encoded (uncommon path)
            return {
                "task_id": task_id, "state": "completed",
                "result_codec": "cloudpickle", "result": merged,
            }
        if isinstance(merged, (bytes, bytearray)):
            b64 = base64.b64encode(merged).decode("ascii")
        elif isinstance(merged, str):
            # Heuristic: assume already-base64 if it decodes cleanly
            try:
                base64.b64decode(merged, validate=True)
                b64 = merged
            except Exception:
                # Plain string — cloudpickle-encode then base64
                from stockstat._core.codec import CloudpickleCodec
                b64 = base64.b64encode(CloudpickleCodec().encode(merged)).decode("ascii")
        else:
            # Python object — cloudpickle-encode then base64
            from stockstat._core.codec import CloudpickleCodec
            b64 = base64.b64encode(CloudpickleCodec().encode(merged)).decode("ascii")
        return {
            "task_id": task_id,
            "state": "completed",
            "result_codec": "cloudpickle",
            "result": b64,
        }

    def cancel(self, task_id: str) -> bool:
        state = self._tasks.get(task_id)
        if state is None:
            return False
        from stockstat._core.contracts.compute import TaskState
        if state.info.state in (TaskState.PENDING, TaskState.RUNNING):
            state.info.state = TaskState.CANCELLED
            state.info.finished_at = datetime.utcnow()
            return True
        return False

    def cluster_info(self, include_offline: bool = False,
                     filter_labels: dict = None) -> dict:
        """Return cluster topology — V2 §12.13.4.

        P7: includes ``sub_dispatchers`` field for multi-level topology.
        """
        all_workers = self._workers.list_all() if include_offline else self._workers.list_online()
        if filter_labels:
            all_workers = [w for w in all_workers
                           if all(w.labels.get(k) == v for k, v in filter_labels.items())]
        workers_list = []
        for w in all_workers:
            workers_list.append({
                "worker_id": w.worker_id,
                "alias": w.alias,
                "address": f"{w.address}:{w.port}" if w.port else w.address,
                "status": w.status,
                "concurrency": w.concurrency,
                "active_tasks": w.active_tasks,
                "completed_tasks": w.completed_tasks,
                "failed_tasks": w.failed_tasks,
                "avg_task_duration_s": w.avg_task_duration_s,
                "last_heartbeat": datetime.utcfromtimestamp(w.last_heartbeat).isoformat() + "Z",
                "capabilities": w.capabilities,
                "stockstat_version": w.stockstat_version,
                "hardware": w.hardware,
                "load": w.load,
                "labels": w.labels,
            })
        return {
            "dispatcher": {
                "id": "dispatcher-01",
                "alias": self._alias,
                "address": self._storage_url,
                "status": "online",
                "uptime_s": int(time.time() - self._started_at),
                "queue_depth": self._queue.size(),
                "cache_size_mb": round(self._cache.size_mb, 2),
                "cache_hit_rate": round(self._cache.hit_rate, 4),
                "parent_url": self._parent_url,  # P7: parent Dispatcher URL
            },
            "workers": workers_list,
            "sub_dispatchers": list(self._sub_dispatchers.values()),  # P7
            "stats": self._workers.stats(),
        }

    # ── P7: Multi-level Dispatcher ────────────────────────────

    def register_sub_dispatcher(self, sub_id: str, alias: str,
                                  address: str, parent_url: str = None) -> dict:
        """P7: a sub-Dispatcher registers itself with the parent.

        Sub-Dispatchers forward tasks they can't handle locally to
        their parent. The parent includes them in cluster_info so
        Clients can see the full topology.
        """
        with self._lock:
            self._sub_dispatchers[sub_id] = {
                "id": sub_id,
                "alias": alias,
                "address": address,
                "status": "online",
                "registered_at": datetime.utcnow().isoformat() + "Z",
            }
        return {"status": "registered", "sub_id": sub_id}

    def unregister_sub_dispatcher(self, sub_id: str) -> dict:
        """P7: sub-Dispatcher graceful removal."""
        with self._lock:
            self._sub_dispatchers.pop(sub_id, None)
        return {"status": "unregistered"}

    def list_sub_dispatchers(self) -> list:
        """P7: return list of registered sub-Dispatchers."""
        return list(self._sub_dispatchers.values())

    # ── P7: Task history for Admin UI ─────────────────────────

    def _record_history(self, state: _TaskState) -> None:
        """Record a completed/failed task in history (for Admin UI)."""
        try:
            entry = {
                "task_id": state.spec.task_id,
                "task_type": state.spec.compute_spec.task_type,
                "state": state.info.state.value,
                "created_at": state.info.created_at.isoformat() if state.info.created_at else None,
                "started_at": state.info.started_at.isoformat() if state.info.started_at else None,
                "finished_at": state.info.finished_at.isoformat() if state.info.finished_at else None,
                "worker_id": state.info.worker_id,
                "error": state.info.error,
                "trace_id": state.spec.trace_id,
            }
            self._task_history.append(entry)
            # Trim to max size
            if len(self._task_history) > self._history_max:
                self._task_history = self._task_history[-self._history_max:]
        except Exception:
            pass

    def get_task_history(self, limit: int = 100,
                          state_filter: str = None) -> list:
        """P7: return recent task history for Admin UI."""
        history = list(self._task_history[-limit:])
        if state_filter:
            history = [h for h in history if h["state"] == state_filter]
        return history

    def get_task_stats(self) -> dict:
        """P7: aggregate task statistics for Admin UI dashboard."""
        from collections import Counter
        history = self._task_history
        total = len(history)
        state_counts = Counter(h["state"] for h in history)
        type_counts = Counter(h["task_type"] for h in history)
        # Compute avg duration for completed tasks
        durations = []
        for h in history:
            if (h["state"] == "completed" and h["started_at"]
                    and h["finished_at"]):
                try:
                    from datetime import datetime
                    started = datetime.fromisoformat(h["started_at"])
                    finished = datetime.fromisoformat(h["finished_at"])
                    durations.append((finished - started).total_seconds())
                except Exception:
                    pass
        avg_duration = sum(durations) / len(durations) if durations else 0
        return {
            "total_tasks": total,
            "by_state": dict(state_counts),
            "by_type": dict(type_counts),
            "avg_duration_s": round(avg_duration, 3),
            "history_size": total,
        }

    # ── Worker-facing API ─────────────────────────────────────

    def register_worker(self, msg: dict) -> dict:
        wid = self._workers.register(msg)
        return {"worker_id": wid, "status": "registered"}

    def heartbeat(self, msg: dict) -> dict:
        self._workers.heartbeat(msg)
        return {"status": "ok"}

    def unregister_worker(self, worker_id: str) -> dict:
        self._workers.unregister(worker_id)
        return {"status": "unregistered"}

    def assign_task(self, worker_id: str, capabilities: list = None) -> Optional[dict]:
        """Worker pulls a task. Returns assignment dict or None."""
        from stockstat._core.contracts.compute import TaskState
        # Try to dequeue a task the worker can handle
        for _ in range(self._queue.size()):
            spec = self._queue.dequeue(block=False)
            if spec is None:
                break
            # Check capability match
            task_type = spec.compute_spec.task_type
            if capabilities and task_type not in capabilities and task_type != "custom":
                # Re-enqueue for another worker
                self._queue.enqueue(spec)
                continue
            # Found a matching task
            parent_id = spec.task_id.split("-s")[0] if "-s" in spec.task_id else spec.task_id
            parent_state = self._tasks.get(parent_id)
            if parent_state is None:
                # Orphan slice — skip
                continue
            # Prefetch data (if not already cached)
            data_ref = self._prefetch_data(spec, parent_state)
            # Update task state
            with parent_state.lock:
                parent_state.info.state = TaskState.RUNNING
                parent_state.info.started_at = parent_state.info.started_at or datetime.utcnow()
                parent_state.assigned[spec.task_id] = worker_id
                parent_state.info.worker_id = worker_id
                parent_state.info.slice_id = spec.task_id
            self._workers.increment_active(worker_id)
            # Build assignment payload — data is base64-encoded for JSON transport
            import base64
            data_bytes = self._cache.fetch_ref(data_ref) if data_ref else None
            data_b64 = None
            if data_bytes is not None:
                data_b64 = base64.b64encode(data_bytes).decode("ascii")
            return {
                "task_spec": spec.to_dict(),
                "data_ref": data_ref,
                "data": data_b64,
                "data_codec": "cloudpickle" if data_b64 else None,
            }
        return None

    def on_complete(self, worker_id: str, slice_id: str, result: Any,
                    result_codec: str = "cloudpickle") -> dict:
        """Worker completed a slice. Merge into parent task."""
        from stockstat._core.contracts.compute import TaskState
        parent_id = slice_id.split("-s")[0] if "-s" in slice_id else slice_id
        state = self._tasks.get(parent_id)
        if state is None:
            return {"status": "unknown_task"}
        self._workers.decrement_active(worker_id, completed=True)
        # Decode the result if it arrived as base64-encoded cloudpickle bytes
        decoded = result
        if isinstance(result, str) and result_codec == "cloudpickle":
            import base64
            try:
                raw = base64.b64decode(result)
                from stockstat._core.codec import CloudpickleCodec
                decoded = CloudpickleCodec().decode(raw)
            except Exception:
                decoded = result  # keep as-is on decode failure
        with state.lock:
            state.partial_results[slice_id] = decoded
            # Check if all slices are done
            if len(state.partial_results) >= len(state.slices):
                state.merged_result = self._merge_results(state)
                state.info.state = TaskState.COMPLETED
                state.info.progress = 1.0
                state.info.finished_at = datetime.utcnow()
                self._record_history(state)  # P7: record for Admin UI
        return {"status": "ok", "completed": state.info.state == TaskState.COMPLETED}

    def on_fail(self, worker_id: str, slice_id: str, error: str,
                traceback_str: str = "", retryable: bool = True) -> dict:
        """Worker failed a slice."""
        from stockstat._core.contracts.compute import TaskState
        parent_id = slice_id.split("-s")[0] if "-s" in slice_id else slice_id
        state = self._tasks.get(parent_id)
        if state is None:
            return {"status": "unknown_task"}
        self._workers.decrement_active(worker_id, failed=True)
        with state.lock:
            # For now, mark the whole task as failed
            # TODO: retry the slice if retryable and retry_count > 0
            state.info.state = TaskState.FAILED
            state.info.error = error
            state.info.error_code = "WORKER_FAILED"
            state.info.finished_at = datetime.utcnow()
            self._record_history(state)  # P7: record for Admin UI
        return {"status": "failed_recorded"}

    def on_partial(self, worker_id: str, slice_id: str, partial: Any) -> dict:
        """Worker sent a partial result (V2 §13.2)."""
        parent_id = slice_id.split("-s")[0] if "-s" in slice_id else slice_id
        state = self._tasks.get(parent_id)
        if state is None:
            return {"status": "unknown_task"}
        # Store partial for streaming clients
        if not hasattr(state, "stream_partials"):
            state.stream_partials = []
        state.stream_partials.append(partial)
        return {"status": "ok"}

    # ── P6: Preemption / Drain / Discovery ────────────────────

    def preempt(self, slice_id: str, worker_id: str = "") -> dict:
        """V2 §13.3: preempt a running task on a Worker.

        The Worker saves a checkpoint and stops the task. Dispatcher
        marks the slice as 'preempted' so it can be resumed later.

        Note: actual preemption requires the Worker to cooperatively
        check the preempt flag. Dispatcher cannot forcibly stop a
        thread on a remote Worker.
        """
        from stockstat._core.contracts.compute import TaskState
        parent_id = slice_id.split("-s")[0] if "-s" in slice_id else slice_id
        state = self._tasks.get(parent_id)
        if state is None:
            return {"status": "unknown_task"}
        # Mark slice as preempted
        with state.lock:
            state.info.state = TaskState.PENDING  # back to pending
            state.info.worker_id = None
            state.assigned.pop(slice_id, None)
        # In a real deployment, Dispatcher would forward the preempt
        # message to the Worker via HTTP. For now, just acknowledge.
        return {"status": "preempted", "slice_id": slice_id}

    def resume(self, slice_id: str, worker_id: str = "") -> dict:
        """V2 §13.3: resume a preempted task from checkpoint."""
        parent_id = slice_id.split("-s")[0] if "-s" in slice_id else slice_id
        state = self._tasks.get(parent_id)
        if state is None:
            return {"status": "unknown_task"}
        # Re-enqueue the slice for any Worker to pick up
        # (the Worker that has the checkpoint should ideally pick it up)
        for slice_spec in state.slices:
            if slice_spec.task_id == slice_id:
                self._queue.enqueue(slice_spec)
                return {"status": "resumed", "slice_id": slice_id}
        return {"status": "slice_not_found"}

    def drain_worker(self, worker_id: str) -> dict:
        """V2 §13.4: tell a Worker to gracefully stop accepting tasks.

        Worker will finish active tasks, then unregister.
        """
        w = self._workers.get(worker_id)
        if w is None:
            return {"status": "unknown_worker"}
        w.status = "draining"
        return {"status": "draining", "worker_id": worker_id}

    def discover(self) -> dict:
        """V2 §13.4: service discovery — return available Dispatchers.

        For single-Dispatcher deployments, returns just self. P7
        (multi-level Dispatcher) will return parent + children.
        """
        return {
            "dispatchers": [{
                "id": "dispatcher-01",
                "alias": "dispatch-primary",
                "address": self._storage_url,
                "status": "online",
            }],
            "count": 1,
        }

    # ── Autoscaler hooks (P6) ─────────────────────────────────

    def get_autoscaler_metrics(self) -> dict:
        """Return metrics for an external Autoscaler to consume.

        The Autoscaler (K8s / Docker Swarm / custom script) reads
        these metrics to decide whether to scale Workers up or down.

        Scale-up signals:
        - ``queue_depth`` > threshold (e.g. 10)
        - ``available_concurrency`` == 0 (and there are workers)

        Scale-down signals:
        - ``queue_depth`` == 0
        - ``available_concurrency`` > 2 * active_tasks (over-provisioned)
        """
        stats = self._workers.stats()
        has_workers = stats["online_workers"] > 0
        return {
            "queue_depth": self._queue.size(),
            "active_tasks": stats["active_tasks"],
            "total_concurrency": stats["total_concurrency"],
            "available_concurrency": stats["available_concurrency"],
            "online_workers": stats["online_workers"],
            "scale_up_recommended": (
                # Deep queue — need more workers
                self._queue.size() > 10
                # All workers busy (only relevant if there are workers)
                or (has_workers and stats["available_concurrency"] == 0)
            ),
            "scale_down_recommended": (
                # No queued tasks
                self._queue.size() == 0
                # Over-provisioned: 2x more capacity than active
                and stats["available_concurrency"] > 2 * max(1, stats["active_tasks"])
                # More than 1 worker (don't scale to zero)
                and stats["online_workers"] > 1
            ),
        }

    # ── Data prefetch ─────────────────────────────────────────

    def _prefetch_data(self, spec, parent_state) -> str:
        """Prefetch data from Storage, return data_ref."""
        cache_key = DataCache.make_key(spec.data_spec)
        parent_state.data_cache_key = cache_key
        # Check cache
        ref = self._cache.get_ref(cache_key)
        if ref:
            return ref
        # Fetch from Storage
        try:
            data = self._fetch_from_storage(spec.data_spec)
            from stockstat._core.codec import CloudpickleCodec
            data_bytes = CloudpickleCodec().encode(data)
            return self._cache.put(cache_key, data_bytes)
        except Exception:
            return ""

    def _fetch_from_storage(self, data_spec) -> dict:
        """Fetch OHLCV data from Storage (HTTP or same-process)."""
        import pandas as pd
        result = {}
        for sym in data_spec.symbols:
            df = None
            # Try same-process access first (if mounted on Storage app)
            if self._storage_app is not None:
                try:
                    from ..storage.repository import ohlcv_repo
                    rows = ohlcv_repo.query(
                        symbol=sym, timeframe=data_spec.timeframe,
                        start=data_spec.start, end=data_spec.end,
                        source=data_spec.source,
                    )
                    if rows:
                        df = pd.DataFrame([r.to_dict() for r in rows])
                        if "ts" in df.columns:
                            df["ts"] = pd.to_datetime(df["ts"], utc=True)
                            df = df.set_index("ts")
                except Exception:
                    pass
            # Fallback: HTTP
            if df is None and self._storage_url:
                try:
                    import httpx
                    params = {"symbol": sym, "timeframe": data_spec.timeframe}
                    if data_spec.start:
                        params["start"] = data_spec.start
                    if data_spec.end:
                        params["end"] = data_spec.end
                    if data_spec.source:
                        params["source"] = data_spec.source
                    resp = httpx.get(f"{self._storage_url}/api/v1/ohlcv",
                                     params=params, timeout=30)
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])
                        if data:
                            df = pd.DataFrame(data)
                            df["ts"] = pd.to_datetime(df["ts"], utc=True)
                            df = df.set_index("ts")
                            for c in ["open", "high", "low", "close", "volume"]:
                                if c in df.columns:
                                    df[c] = df[c].astype(float)
                except Exception:
                    pass
            if df is None:
                df = pd.DataFrame()
            result[sym] = {data_spec.timeframe: df}
        return result

    # ── Result merging ────────────────────────────────────────

    def _merge_results(self, state: _TaskState) -> Any:
        """Merge slice results into a single result."""
        results = list(state.partial_results.values())
        if len(results) == 1:
            return results[0]
        # For grid_search: concatenate and re-sort
        task_type = state.spec.compute_spec.task_type
        if task_type == "grid_search":
            merged = []
            for r in results:
                if isinstance(r, list):
                    merged.extend(r)
            metric = state.spec.compute_spec.metric
            maximize = state.spec.compute_spec.maximize
            merged.sort(key=lambda x: x.get(metric, float("-inf")), reverse=maximize)
            return merged
        # For batch_backtest: concatenate DataFrames
        if task_type == "batch_backtest":
            import pandas as pd
            return pd.concat([r for r in results if isinstance(r, pd.DataFrame)])
        # Default: return first result
        return results[0]

    # ── Internal ──────────────────────────────────────────────

    def _get_task(self, task_id: str) -> _TaskState:
        state = self._tasks.get(task_id)
        if state is None:
            from stockstat._core.errors import TaskNotFoundError
            raise TaskNotFoundError(
                f"Unknown task_id: {task_id}",
                context={"task_id": task_id},
            )
        return state

    def _check_loop(self) -> None:
        """Background thread: check worker heartbeat timeouts."""
        while True:
            time.sleep(10)
            try:
                self._workers.check_timeouts()
            except Exception:
                pass
