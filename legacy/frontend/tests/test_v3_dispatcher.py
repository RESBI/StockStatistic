"""V3 P2 Dispatcher unit tests.

Covers DESIGN_V3_CN §9 (Dispatcher design) — tests the Dispatcher
component in isolation, without spawning a real Worker process:

- DispatcherPlugin.mount() wires /dispatch/* + /api/v1/tasks/* routes
- Dispatcher.submit() / get_status() / get_result() / cancel()
- MemoryTaskQueue enqueue / dequeue / priority / size
- WorkerRegistry register / heartbeat / timeout / stats
- DataCache make_key / put / get / get_ref / LRU eviction / hit_rate
- shard_task: param_wise / symbol_wise / time_wise / none / auto
- Result merging: single slice / multi-slice grid_search / batch_backtest
- Cluster info structure with worker hardware / labels
- Error paths: unknown task_id / not-ready result
"""
from __future__ import annotations

import time
import pytest


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def dispatcher():
    """Build a fresh Dispatcher with in-memory queue."""
    from stockstat_backend.dispatcher.core import Dispatcher
    from stockstat_backend.dispatcher.queue import MemoryTaskQueue
    return Dispatcher(queue=MemoryTaskQueue(), storage_app=None,
                      offline_timeout=30.0)


@pytest.fixture
def sample_spec():
    """Build a simple custom TaskSpec."""
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
    )
    return TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="custom",
                                  params={"test": "dispatcher"}),
        dispatch_spec=DispatchSpec(),
    )


# ═══════════════════════════════════════════════════════════════
# P2.1: MemoryTaskQueue
# ═══════════════════════════════════════════════════════════════


class TestMemoryTaskQueue:
    def test_enqueue_dequeue_fifo(self):
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        q = MemoryTaskQueue()
        spec_a = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                          compute_spec=ComputeSpec(task_type="custom"))
        spec_b = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                          compute_spec=ComputeSpec(task_type="custom"))
        q.enqueue(spec_a)
        q.enqueue(spec_b)
        assert q.size() == 2
        out = q.dequeue(block=False)
        # Same priority -> order between spec_a/spec_b is not strictly FIFO
        # because PriorityQueue breaks ties by task_id (UUID)
        assert out is not None
        assert out.task_id in (spec_a.task_id, spec_b.task_id)
        out2 = q.dequeue(block=False)
        assert out2 is not None
        assert out2.task_id in (spec_a.task_id, spec_b.task_id)
        assert out.task_id != out2.task_id
        assert q.size() == 0

    def test_priority_ordering(self):
        """High-priority (lower number) dequeued first."""
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        q = MemoryTaskQueue()
        low = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                       compute_spec=ComputeSpec(task_type="custom"),
                       dispatch_spec=DispatchSpec(priority=1))
        high = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                        compute_spec=ComputeSpec(task_type="custom"),
                        dispatch_spec=DispatchSpec(priority=-1))
        normal = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                          compute_spec=ComputeSpec(task_type="custom"),
                          dispatch_spec=DispatchSpec(priority=0))
        q.enqueue(low)
        q.enqueue(normal)
        q.enqueue(high)
        assert q.dequeue(block=False).task_id == high.task_id
        assert q.dequeue(block=False).task_id == normal.task_id
        assert q.dequeue(block=False).task_id == low.task_id

    def test_dequeue_empty_returns_none(self):
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        q = MemoryTaskQueue()
        assert q.dequeue(block=False) is None

    def test_clear(self):
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        q = MemoryTaskQueue()
        q.enqueue(TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                            compute_spec=ComputeSpec(task_type="custom")))
        q.enqueue(TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                            compute_spec=ComputeSpec(task_type="custom")))
        q.clear()
        assert q.size() == 0

    def test_build_queue_factory(self):
        from stockstat_backend.dispatcher.queue import build_queue, MemoryTaskQueue
        q = build_queue("memory")
        assert isinstance(q, MemoryTaskQueue)
        with pytest.raises(ValueError):
            build_queue("redis", redis_url=None)
        with pytest.raises(ValueError):
            build_queue("unknown")


# ═══════════════════════════════════════════════════════════════
# P2.2: WorkerRegistry
# ═══════════════════════════════════════════════════════════════


class TestWorkerRegistry:
    def test_register_and_list(self):
        from stockstat_backend.dispatcher.workers import WorkerRegistry
        reg = WorkerRegistry()
        wid = reg.register({
            "worker_id": "w1", "alias": "alpha",
            "concurrency": 4, "capabilities": ["backtest"],
            "hardware": {"cpu": {"cores_logical": 4}},
            "labels": {"rack": "A"},
        })
        assert wid == "w1"
        online = reg.list_online()
        assert len(online) == 1
        assert online[0].alias == "alpha"
        assert online[0].concurrency == 4

    def test_capability_filter(self):
        from stockstat_backend.dispatcher.workers import WorkerRegistry
        reg = WorkerRegistry()
        reg.register({"worker_id": "w1", "alias": "a",
                      "capabilities": ["backtest"]})
        reg.register({"worker_id": "w2", "alias": "b",
                      "capabilities": ["indicator"]})
        bt_workers = reg.list_online(capability="backtest")
        assert len(bt_workers) == 1
        assert bt_workers[0].worker_id == "w1"

    def test_heartbeat_updates_load(self):
        from stockstat_backend.dispatcher.workers import WorkerRegistry
        reg = WorkerRegistry()
        reg.register({"worker_id": "w1", "alias": "a", "concurrency": 2})
        reg.heartbeat({
            "worker_id": "w1", "load": {"cpu_percent": 50.0},
            "active_tasks": 2, "completed_tasks": 10,
        })
        w = reg.get("w1")
        assert w.load["cpu_percent"] == 50.0
        assert w.active_tasks == 2
        assert w.completed_tasks == 10
        assert w.status == "busy"  # active == concurrency

    def test_unregister_marks_offline(self):
        from stockstat_backend.dispatcher.workers import WorkerRegistry
        reg = WorkerRegistry()
        reg.register({"worker_id": "w1", "alias": "a"})
        reg.unregister("w1")
        w = reg.get("w1")
        assert w.status == "offline"
        assert len(reg.list_online()) == 0

    def test_timeout_detection(self):
        from stockstat_backend.dispatcher.workers import WorkerRegistry
        reg = WorkerRegistry(offline_timeout=0.1)  # 100ms
        reg.register({"worker_id": "w1", "alias": "a"})
        time.sleep(0.2)  # exceed timeout
        timed_out = reg.check_timeouts()
        assert "w1" in timed_out
        assert reg.get("w1").status == "offline"

    def test_stats(self):
        from stockstat_backend.dispatcher.workers import WorkerRegistry
        reg = WorkerRegistry()
        reg.register({"worker_id": "w1", "alias": "a", "concurrency": 4})
        reg.register({"worker_id": "w2", "alias": "b", "concurrency": 8})
        stats = reg.stats()
        assert stats["total_workers"] == 2
        assert stats["online_workers"] == 2
        assert stats["total_concurrency"] == 12


# ═══════════════════════════════════════════════════════════════
# P2.3: DataCache
# ═══════════════════════════════════════════════════════════════


class TestDataCache:
    def test_make_key_stable(self):
        from stockstat_backend.dispatcher.prefetch import DataCache
        from stockstat._core.contracts.task import DataSpec
        ds = DataSpec(symbols=["BTC/USDT"], timeframe="1d",
                       start="2024-01-01", end="2024-12-31")
        k1 = DataCache.make_key(ds)
        k2 = DataCache.make_key(ds)
        assert k1 == k2

    def test_make_key_differs_for_different_specs(self):
        from stockstat_backend.dispatcher.prefetch import DataCache
        from stockstat._core.contracts.task import DataSpec
        ds1 = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
        ds2 = DataSpec(symbols=["ETH/USDT"], timeframe="1d")
        assert DataCache.make_key(ds1) != DataCache.make_key(ds2)

    def test_put_and_get_ref(self):
        from stockstat_backend.dispatcher.prefetch import DataCache
        cache = DataCache(max_size_mb=1)
        key = "test-key"
        data = b"hello world"
        ref = cache.put(key, data)
        assert ref == f"cache://{key}"
        fetched = cache.fetch_ref(ref)
        assert fetched == data

    def test_has_and_get(self):
        from stockstat_backend.dispatcher.prefetch import DataCache
        cache = DataCache()
        cache.put("k1", b"data1")
        assert cache.has("k1")
        assert not cache.has("k2")
        assert cache.get("k1") == b"data1"
        assert cache.get("k2") is None

    def test_hit_rate(self):
        from stockstat_backend.dispatcher.prefetch import DataCache
        cache = DataCache()
        cache.put("k1", b"data")
        cache.get("k1")  # hit
        cache.get("k1")  # hit
        cache.get("missing")  # miss
        assert cache.hit_rate == 2 / 3

    def test_lru_eviction(self):
        from stockstat_backend.dispatcher.prefetch import DataCache
        cache = DataCache(max_size_mb=1)  # 1MB
        # Fill to capacity
        cache.put("a", b"x" * (300 * 1024))
        cache.put("b", b"x" * (300 * 1024))
        cache.put("c", b"x" * (300 * 1024))
        cache.put("d", b"x" * (300 * 1024))  # should evict "a"
        assert not cache.has("a")
        assert cache.has("d")

    def test_fetch_ref_invalid_format(self):
        from stockstat_backend.dispatcher.prefetch import DataCache
        cache = DataCache()
        assert cache.fetch_ref("invalid://x") is None

    def test_stats(self):
        from stockstat_backend.dispatcher.prefetch import DataCache
        cache = DataCache()
        cache.put("k1", b"abcd")
        stats = cache.stats()
        assert "size_mb" in stats
        assert "hit_rate" in stats
        assert stats["entries"] == 1


# ═══════════════════════════════════════════════════════════════
# P2.4: shard_task
# ═══════════════════════════════════════════════════════════════


class TestShardTask:
    def _make_spec(self, **kw):
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        return TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT", "ETH/USDT"]),
            compute_spec=ComputeSpec(task_type="grid_search", **kw),
            dispatch_spec=DispatchSpec(),
        )

    def test_shard_none_returns_single(self):
        from stockstat_backend.dispatcher.dispatch import shard_task
        spec = self._make_spec()
        slices = shard_task(spec)
        assert len(slices) == 1
        assert slices[0].task_id == spec.task_id

    def test_shard_auto_returns_single(self):
        from stockstat_backend.dispatcher.dispatch import shard_task
        spec = self._make_spec()
        spec.dispatch_spec.split_strategy = "auto"
        assert len(shard_task(spec)) == 1

    def test_shard_param_wise(self):
        from stockstat_backend.dispatcher.dispatch import shard_task
        spec = self._make_spec(param_grid={"short": [3, 5, 8, 10],
                                            "long": [20, 30, 40]})
        spec.dispatch_spec.split_strategy = "param_wise"
        spec.dispatch_spec.max_workers = 4
        slices = shard_task(spec, max_workers=4)
        assert len(slices) == 4
        # Each slice has a unique task_id
        ids = {s.task_id for s in slices}
        assert len(ids) == 4
        # Each slice has param_slice set
        for s in slices:
            assert "param_slice" in s.compute_spec.params
        # Slices carry parent id prefix
        for s in slices:
            assert s.task_id.startswith(f"{spec.task_id}-s")

    def test_shard_param_wise_single_worker(self):
        from stockstat_backend.dispatcher.dispatch import shard_task
        spec = self._make_spec(param_grid={"x": [1, 2, 3]})
        spec.dispatch_spec.split_strategy = "param_wise"
        spec.dispatch_spec.max_workers = 1
        slices = shard_task(spec, max_workers=1)
        assert len(slices) == 1

    def test_shard_symbol_wise(self):
        from stockstat_backend.dispatcher.dispatch import shard_task
        spec = self._make_spec()
        spec.dispatch_spec.split_strategy = "symbol_wise"
        spec.dispatch_spec.max_workers = 2
        slices = shard_task(spec, max_workers=2)
        assert len(slices) == 2
        symbols_per_slice = [s.data_spec.symbols[0] for s in slices]
        assert set(symbols_per_slice) == {"BTC/USDT", "ETH/USDT"}

    def test_shard_time_wise(self):
        from stockstat_backend.dispatcher.dispatch import shard_task
        spec = self._make_spec()
        spec.data_spec.start = "2024-01-01"
        spec.data_spec.end = "2024-12-31"
        spec.dispatch_spec.split_strategy = "time_wise"
        spec.dispatch_spec.max_workers = 4
        slices = shard_task(spec, max_workers=4)
        assert len(slices) == 4

    def test_slice_inherits_strategy_none(self):
        from stockstat_backend.dispatcher.dispatch import shard_task
        spec = self._make_spec(param_grid={"x": [1, 2, 3, 4]})
        spec.dispatch_spec.split_strategy = "param_wise"
        spec.dispatch_spec.max_workers = 2
        slices = shard_task(spec, max_workers=2)
        for s in slices:
            assert s.dispatch_spec.split_strategy == "none"


# ═══════════════════════════════════════════════════════════════
# P2.5: Dispatcher core
# ═══════════════════════════════════════════════════════════════


class TestDispatcher:
    def test_submit_returns_pending(self, dispatcher, sample_spec):
        result = dispatcher.submit(sample_spec)
        assert result["task_id"] == sample_spec.task_id
        assert result["status"] == "pending"
        assert result["n_slices"] >= 1

    def test_get_status_unknown_raises(self, dispatcher):
        from stockstat._core.errors import TaskNotFoundError
        with pytest.raises(TaskNotFoundError):
            dispatcher.get_status("nonexistent")

    def test_get_status_pending(self, dispatcher, sample_spec):
        dispatcher.submit(sample_spec)
        status = dispatcher.get_status(sample_spec.task_id)
        assert status["task_id"] == sample_spec.task_id
        assert status["state"] == "pending"

    def test_get_result_not_ready(self, dispatcher, sample_spec):
        from stockstat._core.errors import TaskNotReadyError
        dispatcher.submit(sample_spec)
        with pytest.raises(TaskNotReadyError):
            dispatcher.get_result(sample_spec.task_id)

    def test_cancel_pending(self, dispatcher, sample_spec):
        dispatcher.submit(sample_spec)
        ok = dispatcher.cancel(sample_spec.task_id)
        assert ok is True
        status = dispatcher.get_status(sample_spec.task_id)
        assert status["state"] == "cancelled"

    def test_cancel_unknown_returns_false(self, dispatcher):
        assert dispatcher.cancel("nonexistent") is False

    def test_register_worker(self, dispatcher):
        result = dispatcher.register_worker({
            "worker_id": "w1", "alias": "alpha",
            "concurrency": 4, "capabilities": ["backtest"],
            "hardware": {"cpu": {"cores_logical": 4}},
            "labels": {"zone": "east"},
        })
        assert result["worker_id"] == "w1"
        assert result["status"] == "registered"

    def test_heartbeat_updates_worker(self, dispatcher):
        dispatcher.register_worker({"worker_id": "w1", "alias": "a",
                                     "concurrency": 2})
        dispatcher.heartbeat({
            "worker_id": "w1", "load": {"cpu_percent": 75.0},
            "active_tasks": 1, "completed_tasks": 5,
        })
        info = dispatcher.cluster_info()
        assert info["workers"][0]["load"]["cpu_percent"] == 75.0

    def test_assign_task_no_workers(self, dispatcher, sample_spec):
        """assign_task with empty queue returns None."""
        assert dispatcher.assign_task("w1", capabilities=[]) is None

    def test_assign_task_with_capability(self, dispatcher, sample_spec):
        """assign_task returns the task if capability matches."""
        dispatcher.submit(sample_spec)
        result = dispatcher.assign_task("w1", capabilities=["custom"])
        assert result is not None
        assert result["task_spec"]["task_id"] == sample_spec.task_id

    def test_assign_task_capability_mismatch_reenqueue(self, dispatcher):
        """If worker can't handle task_type, task is re-enqueued."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        # Use "backtest" task_type (not "custom", which is universal)
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="backtest"),
        )
        dispatcher.submit(spec)
        # Worker doesn't have "backtest" capability
        result = dispatcher.assign_task("w1", capabilities=["indicator"])
        # Task should be re-enqueued, result None (no matching task)
        assert result is None
        # Queue should still have the task
        assert dispatcher._queue.size() == 1

    def test_on_complete_marks_completed(self, dispatcher, sample_spec):
        """When all slices complete, task is marked completed."""
        import base64
        from stockstat._core.codec import CloudpickleCodec
        dispatcher.submit(sample_spec)
        # Assign to a worker
        assignment = dispatcher.assign_task("w1", capabilities=["custom"])
        slice_id = assignment["task_spec"]["task_id"]
        # Worker completes — send base64-encoded cloudpickle result
        result = {"task_type": "custom", "params": {"test": "dispatcher"}}
        result_b64 = base64.b64encode(CloudpickleCodec().encode(result)).decode("ascii")
        dispatcher.on_complete("w1", slice_id, result_b64)
        status = dispatcher.get_status(sample_spec.task_id)
        assert status["state"] == "completed"

    def test_on_complete_with_result(self, dispatcher, sample_spec):
        """get_result returns base64-encoded cloudpickle of the merged result."""
        import base64
        from stockstat._core.codec import CloudpickleCodec
        dispatcher.submit(sample_spec)
        assignment = dispatcher.assign_task("w1", capabilities=["custom"])
        slice_id = assignment["task_spec"]["task_id"]
        result = {"answer": 42}
        # Worker sends base64-encoded cloudpickle bytes
        result_b64 = base64.b64encode(CloudpickleCodec().encode(result)).decode("ascii")
        dispatcher.on_complete("w1", slice_id, result_b64)
        fetched = dispatcher.get_result(sample_spec.task_id)
        # Dispatcher returns base64 string on the wire
        assert fetched["result_codec"] == "cloudpickle"
        decoded = CloudpickleCodec().decode(base64.b64decode(fetched["result"]))
        assert decoded == result

    def test_on_fail_marks_failed(self, dispatcher, sample_spec):
        dispatcher.submit(sample_spec)
        assignment = dispatcher.assign_task("w1", capabilities=["custom"])
        slice_id = assignment["task_spec"]["task_id"]
        dispatcher.on_fail("w1", slice_id, error="something broke",
                            traceback_str="...", retryable=True)
        status = dispatcher.get_status(sample_spec.task_id)
        assert status["state"] == "failed"
        assert "something broke" in status["error"]

    def test_on_partial_stores(self, dispatcher, sample_spec):
        dispatcher.submit(sample_spec)
        dispatcher.on_partial("w1", sample_spec.task_id,
                               {"completed": 5, "total": 10})
        # No direct getter, but verify no exception

    def test_cluster_info_shape(self, dispatcher):
        dispatcher.register_worker({
            "worker_id": "w1", "alias": "alpha",
            "concurrency": 4, "capabilities": ["backtest"],
            "hardware": {"cpu": {"cores_logical": 4}},
            "labels": {"zone": "east"},
        })
        info = dispatcher.cluster_info()
        assert "dispatcher" in info
        assert "workers" in info
        assert "stats" in info
        assert info["stats"]["total_workers"] == 1
        assert info["workers"][0]["alias"] == "alpha"

    def test_cluster_info_filter_labels(self, dispatcher):
        dispatcher.register_worker({"worker_id": "w1", "alias": "a",
                                     "labels": {"zone": "east"}})
        dispatcher.register_worker({"worker_id": "w2", "alias": "b",
                                     "labels": {"zone": "west"}})
        info = dispatcher.cluster_info(filter_labels={"zone": "east"})
        assert len(info["workers"]) == 1
        assert info["workers"][0]["alias"] == "a"

    def test_unregister_worker(self, dispatcher):
        dispatcher.register_worker({"worker_id": "w1", "alias": "a"})
        result = dispatcher.unregister_worker("w1")
        assert result["status"] == "unregistered"
        # Worker should be offline
        info = dispatcher.cluster_info()
        assert info["stats"]["online_workers"] == 0


# ═══════════════════════════════════════════════════════════════
# P2.6: DispatcherPlugin mounting
# ═══════════════════════════════════════════════════════════════


class TestDispatcherPlugin:
    def test_mount_adds_routes(self):
        from fastapi import FastAPI
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/dispatch/submit" in paths
        assert "/dispatch/status/{task_id}" in paths
        assert "/dispatch/result/{task_id}" in paths
        assert "/dispatch/cancel/{task_id}" in paths
        assert "/dispatch/cluster" in paths
        assert "/dispatch/register" in paths
        assert "/dispatch/heartbeat" in paths
        assert "/dispatch/assign" in paths
        assert "/dispatch/complete" in paths
        assert "/dispatch/fail" in paths
        assert "/dispatch/partial" in paths
        # /api/v1/tasks/* compatibility
        assert "/api/v1/tasks" in paths
        assert "/api/v1/tasks/{task_id}" in paths
        # State stored on app
        assert hasattr(app.state, "dispatcher")

    def test_mount_via_app_factory(self):
        """create_app() with STOCKSTAT_DISPATCHER_ENABLED mounts plugin."""
        import os
        from stockstat_backend.app import create_app
        from stockstat_backend.config import settings
        # Save & set env
        prev = os.environ.get("STOCKSTAT_DISPATCHER_ENABLED")
        os.environ["STOCKSTAT_DISPATCHER_ENABLED"] = "true"
        try:
            settings.reload()
            app = create_app()
            paths = {r.path for r in app.routes if hasattr(r, "path")}
            assert "/dispatch/submit" in paths
        finally:
            if prev is None:
                os.environ.pop("STOCKSTAT_DISPATCHER_ENABLED", None)
            else:
                os.environ["STOCKSTAT_DISPATCHER_ENABLED"] = prev
            settings.reload()


# ═══════════════════════════════════════════════════════════════
# P2.7: Result merging
# ═══════════════════════════════════════════════════════════════


class TestResultMerge:
    def test_merge_single_slice(self, dispatcher, sample_spec):
        """Single-slice task returns the slice result (decoded)."""
        import base64
        from stockstat._core.codec import CloudpickleCodec
        dispatcher.submit(sample_spec)
        assignment = dispatcher.assign_task("w1", capabilities=["custom"])
        slice_id = assignment["task_spec"]["task_id"]
        # Worker sends base64-encoded cloudpickle bytes
        result_obj = {"single": True}
        result_b64 = base64.b64encode(CloudpickleCodec().encode(result_obj)).decode("ascii")
        dispatcher.on_complete("w1", slice_id, result_b64)
        result = dispatcher.get_result(sample_spec.task_id)
        # Decode the base64 wire payload
        decoded = CloudpickleCodec().decode(base64.b64decode(result["result"]))
        assert decoded == {"single": True}

    def test_merge_grid_search_sorted(self):
        """Multi-slice grid_search: results concatenated and sorted by metric."""
        from stockstat_backend.dispatcher.core import Dispatcher, _TaskState
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        from stockstat._core.contracts.compute import TaskInfo, TaskState
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search",
                                      metric="sharpe", maximize=True),
            dispatch_spec=DispatchSpec(),
        )
        state = _TaskState(spec=spec, info=TaskInfo(task_id=spec.task_id,
                                                      state=TaskState.RUNNING))
        state.slices = [spec, spec]
        d._tasks[spec.task_id] = state
        # Two partial results, sharpe values out of order
        slice1 = f"{spec.task_id}-s0"
        slice2 = f"{spec.task_id}-s1"
        state.partial_results[slice1] = [
            {"params": {"a": 1}, "sharpe": 1.2},
            {"params": {"a": 2}, "sharpe": 0.8},
        ]
        state.partial_results[slice2] = [
            {"params": {"a": 3}, "sharpe": 2.5},
        ]
        merged = d._merge_results(state)
        # Sorted desc by sharpe
        assert merged[0]["sharpe"] == 2.5
        assert merged[1]["sharpe"] == 1.2
        assert merged[2]["sharpe"] == 0.8
