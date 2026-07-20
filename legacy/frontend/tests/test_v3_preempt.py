"""V3 P6 Preemption / Drain / Discovery / Autoscaler tests.

Covers DESIGN_V3_CN §13.3 (preempt) + §13.4 (drain + discover) +
Autoscaler hooks:
- Worker.preempt() / Worker.resume() / Worker.drain()
- Dispatcher.preempt() / resume() / drain_worker() / discover()
- Checkpoint + CheckpointStore (save / load / delete / list)
- Autoscaler metrics (queue_depth / scale_up_recommended / scale_down)
- HTTP endpoints: /dispatch/preempt / /dispatch/resume / /dispatch/drain / /dispatch/discover
- Worker graceful drain lifecycle
"""
from __future__ import annotations

import time
import pytest


# ═══════════════════════════════════════════════════════════════
# P6.1: Checkpoint + CheckpointStore
# ═══════════════════════════════════════════════════════════════


class TestCheckpoint:
    def test_checkpoint_construction(self):
        from stockstat_compute.checkpoint import Checkpoint
        ckpt = Checkpoint(
            task_id="slice-1",
            task_type="grid_search",
            progress=0.5,
            completed_items=[{"params": {"a": 1}}],
            remaining_items=[{"params": {"a": 2}}, {"params": {"a": 3}}],
        )
        assert ckpt.task_id == "slice-1"
        assert ckpt.progress == 0.5
        assert len(ckpt.completed_items) == 1
        assert len(ckpt.remaining_items) == 2

    def test_checkpoint_to_dict_roundtrip(self):
        from stockstat_compute.checkpoint import Checkpoint
        ckpt = Checkpoint(
            task_id="slice-2",
            task_type="grid_search",
            progress=0.75,
            completed_items=[{"x": 1}],
            remaining_items=[{"x": 2}],
            params={"param_slice_size": 4},
        )
        d = ckpt.to_dict()
        restored = Checkpoint.from_dict(d)
        assert restored.task_id == "slice-2"
        assert restored.progress == 0.75
        assert restored.completed_items == [{"x": 1}]
        assert restored.remaining_items == [{"x": 2}]
        assert restored.params == {"param_slice_size": 4}

    def test_checkpoint_default_empty(self):
        from stockstat_compute.checkpoint import Checkpoint
        ckpt = Checkpoint(task_id="t", task_type="custom")
        assert ckpt.completed_items == []
        assert ckpt.remaining_items == []
        assert ckpt.params == {}


class TestCheckpointStore:
    def test_save_load(self):
        from stockstat_compute.checkpoint import Checkpoint, CheckpointStore
        store = CheckpointStore()
        ckpt = Checkpoint(task_id="t1", task_type="grid_search")
        store.save(ckpt)
        loaded = store.load("t1")
        assert loaded is not None
        assert loaded.task_id == "t1"

    def test_load_nonexistent_returns_none(self):
        from stockstat_compute.checkpoint import CheckpointStore
        store = CheckpointStore()
        assert store.load("nonexistent") is None

    def test_delete(self):
        from stockstat_compute.checkpoint import Checkpoint, CheckpointStore
        store = CheckpointStore()
        store.save(Checkpoint(task_id="t1", task_type="custom"))
        store.delete("t1")
        assert store.load("t1") is None

    def test_list(self):
        from stockstat_compute.checkpoint import Checkpoint, CheckpointStore
        store = CheckpointStore()
        store.save(Checkpoint(task_id="t1", task_type="custom"))
        store.save(Checkpoint(task_id="t2", task_type="custom"))
        ids = store.list()
        assert set(ids) == {"t1", "t2"}

    def test_global_store_singleton(self):
        from stockstat_compute.checkpoint import get_checkpoint_store
        s1 = get_checkpoint_store()
        s2 = get_checkpoint_store()
        assert s1 is s2


# ═══════════════════════════════════════════════════════════════
# P6.2: Worker preempt / resume / drain
# ═══════════════════════════════════════════════════════════════


class TestWorkerPreemption:
    def test_preempt_unknown_task_returns_false(self):
        from stockstat_compute.worker import Worker
        w = Worker(dispatcher_url="http://x")
        assert w.preempt("nonexistent-slice") is False

    def test_preempt_active_task_returns_true(self):
        """preempt() on a tracked slice returns True."""
        import time
        from stockstat_compute.worker import Worker
        from concurrent.futures import Future
        w = Worker(dispatcher_url="http://x")
        # Manually inject a fake future
        fut = Future()
        w._active_futures["slice-1"] = fut
        assert w.preempt("slice-1") is True
        assert "slice-1" in w._preempted

    def test_resume_known_preempted(self):
        from stockstat_compute.worker import Worker
        from concurrent.futures import Future
        w = Worker(dispatcher_url="http://x")
        w._active_futures["slice-1"] = Future()
        w.preempt("slice-1")
        assert w.resume("slice-1") is True

    def test_resume_unknown_returns_false(self):
        from stockstat_compute.worker import Worker
        w = Worker(dispatcher_url="http://x")
        assert w.resume("nonexistent") is False

    def test_drain_marks_stopping(self):
        from stockstat_compute.worker import Worker
        w = Worker(dispatcher_url="http://x")
        assert not w._draining
        w.drain()
        assert w._draining
        assert w._stopping.is_set()

    def test_stop_also_drains(self):
        from stockstat_compute.worker import Worker
        w = Worker(dispatcher_url="http://x")
        w.stop()
        assert w._draining
        assert w._stopping.is_set()


# ═══════════════════════════════════════════════════════════════
# P6.3: Dispatcher preempt / resume / drain / discover
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def dispatcher():
    from stockstat_backend.dispatcher.core import Dispatcher
    from stockstat_backend.dispatcher.queue import MemoryTaskQueue
    return Dispatcher(queue=MemoryTaskQueue())


@pytest.fixture
def sample_spec():
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    return TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="custom"),
    )


class TestDispatcherP6:
    def test_preempt_unknown_task(self, dispatcher):
        result = dispatcher.preempt("nonexistent")
        assert result["status"] == "unknown_task"

    def test_preempt_known_task(self, dispatcher, sample_spec):
        dispatcher.submit(sample_spec)
        # Simulate assignment to a worker
        assignment = dispatcher.assign_task("w1", capabilities=["custom"])
        slice_id = assignment["task_spec"]["task_id"]
        result = dispatcher.preempt(slice_id)
        assert result["status"] == "preempted"
        # State should be back to PENDING
        status = dispatcher.get_status(sample_spec.task_id)
        assert status["state"] == "pending"

    def test_resume_unknown_task(self, dispatcher):
        result = dispatcher.resume("nonexistent")
        assert result["status"] == "unknown_task"

    def test_resume_known_slice(self, dispatcher, sample_spec):
        dispatcher.submit(sample_spec)
        # Get the slice spec
        state = dispatcher._tasks[sample_spec.task_id]
        slice_id = state.slices[0].task_id
        result = dispatcher.resume(slice_id)
        assert result["status"] == "resumed"
        # Slice should be re-enqueued
        assert dispatcher._queue.size() >= 1

    def test_resume_unknown_slice(self, dispatcher, sample_spec):
        """resume() with a valid parent but nonexistent slice returns slice_not_found."""
        # Shard the spec so it has slices
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT", "ETH/USDT"]),
            compute_spec=ComputeSpec(task_type="custom"),
            dispatch_spec=DispatchSpec(split_strategy="symbol_wise", max_workers=2),
        )
        dispatcher.submit(spec)
        # Spec was sharded into 2 slices; resume a nonexistent slice
        result = dispatcher.resume(f"{spec.task_id}-s99")
        assert result["status"] == "slice_not_found"

    def test_drain_worker_unknown(self, dispatcher):
        result = dispatcher.drain_worker("nonexistent")
        assert result["status"] == "unknown_worker"

    def test_drain_worker_known(self, dispatcher):
        dispatcher.register_worker({"worker_id": "w1", "alias": "alpha"})
        result = dispatcher.drain_worker("w1")
        assert result["status"] == "draining"
        w = dispatcher._workers.get("w1")
        assert w.status == "draining"

    def test_discover_returns_self(self, dispatcher):
        result = dispatcher.discover()
        assert "dispatchers" in result
        assert result["count"] == 1
        assert result["dispatchers"][0]["status"] == "online"

    def test_autoscaler_metrics_empty(self, dispatcher):
        metrics = dispatcher.get_autoscaler_metrics()
        assert metrics["queue_depth"] == 0
        assert metrics["active_tasks"] == 0
        assert metrics["online_workers"] == 0
        assert metrics["scale_up_recommended"] is False
        # No workers, so scale_down logic doesn't trigger
        assert metrics["scale_down_recommended"] is False

    def test_autoscaler_scale_up_when_queue_deep(self, dispatcher, sample_spec):
        """Scale-up recommended when queue has > 10 tasks."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        # Enqueue 11 tasks
        for _ in range(11):
            s = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                         compute_spec=ComputeSpec(task_type="custom"))
            dispatcher.submit(s)
        metrics = dispatcher.get_autoscaler_metrics()
        assert metrics["queue_depth"] >= 11
        assert metrics["scale_up_recommended"] is True

    def test_autoscaler_scale_up_when_no_capacity(self, dispatcher):
        """Scale-up recommended when available_concurrency == 0."""
        dispatcher.register_worker({"worker_id": "w1", "alias": "a",
                                     "concurrency": 1})
        # Worker has 1 active task (full)
        dispatcher._workers.increment_active("w1")
        metrics = dispatcher.get_autoscaler_metrics()
        assert metrics["available_concurrency"] == 0
        assert metrics["scale_up_recommended"] is True

    def test_autoscaler_scale_down_when_idle(self, dispatcher):
        """Scale-down recommended when over-provisioned."""
        dispatcher.register_worker({"worker_id": "w1", "alias": "a",
                                     "concurrency": 4})
        dispatcher.register_worker({"worker_id": "w2", "alias": "b",
                                     "concurrency": 4})
        # 8 total concurrency, 0 active tasks, 0 queue
        metrics = dispatcher.get_autoscaler_metrics()
        assert metrics["scale_down_recommended"] is True


# ═══════════════════════════════════════════════════════════════
# P6.4: HTTP endpoints for P6
# ═══════════════════════════════════════════════════════════════


class TestP6Routes:
    def test_p6_endpoints_exist(self):
        """All P6 endpoints are mounted by DispatcherPlugin."""
        from fastapi import FastAPI
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/dispatch/preempt/{slice_id}" in paths
        assert "/dispatch/resume/{slice_id}" in paths
        assert "/dispatch/drain/{worker_id}" in paths
        assert "/dispatch/discover" in paths

    def test_discover_endpoint(self):
        """/dispatch/discover returns dispatcher list."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        client = TestClient(app)
        resp = client.get("/dispatch/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert "dispatchers" in data
        assert data["count"] == 1

    def test_drain_endpoint(self):
        """/dispatch/drain/{worker_id} marks worker as draining."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        client = TestClient(app)
        # Register a worker first
        client.post("/dispatch/register", json={
            "worker_id": "w1", "alias": "alpha", "concurrency": 1,
        })
        resp = client.post("/dispatch/drain/w1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "draining"

    def test_preempt_endpoint(self):
        """/dispatch/preempt/{slice_id} on unknown task returns unknown_task."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        client = TestClient(app)
        resp = client.post("/dispatch/preempt/nonexistent?worker_id=w1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unknown_task"

    def test_resume_endpoint(self):
        """/dispatch/resume/{slice_id} on unknown task returns unknown_task."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        client = TestClient(app)
        resp = client.post("/dispatch/resume/nonexistent?worker_id=w1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unknown_task"


# ═══════════════════════════════════════════════════════════════
# P6.5: RetryPolicy (V2 §15.3)
# ═══════════════════════════════════════════════════════════════


class TestRetryPolicy:
    def test_default_policy(self):
        from stockstat._core.protocol.retry import RetryPolicy
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.backoff_base == 1.0
        assert p.backoff_factor == 2.0
        assert p.max_backoff == 60.0

    def test_should_retry_within_max(self):
        from stockstat._core.protocol.retry import RetryPolicy
        p = RetryPolicy(max_retries=3)
        assert p.should_retry({"retryable": True}, attempt=0) is True
        assert p.should_retry({"retryable": True}, attempt=2) is True
        assert p.should_retry({"retryable": True}, attempt=3) is False

    def test_should_retry_non_retryable(self):
        from stockstat._core.protocol.retry import RetryPolicy
        p = RetryPolicy()
        assert p.should_retry({"retryable": False}, attempt=0) is False

    def test_next_delay_exponential(self):
        from stockstat._core.protocol.retry import RetryPolicy
        p = RetryPolicy(backoff_base=1.0, backoff_factor=2.0, max_backoff=60.0)
        assert p.next_delay(0) == 1.0
        assert p.next_delay(1) == 2.0
        assert p.next_delay(2) == 4.0
        assert p.next_delay(3) == 8.0

    def test_next_delay_capped_at_max(self):
        from stockstat._core.protocol.retry import RetryPolicy
        p = RetryPolicy(backoff_base=1.0, backoff_factor=2.0, max_backoff=10.0)
        assert p.next_delay(10) == 10.0  # capped
