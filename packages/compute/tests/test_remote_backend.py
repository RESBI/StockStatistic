"""test_remote_backend.py — RemoteComputeBackend 测试 (25 项)。"""
from __future__ import annotations

import base64
import threading
import time

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stockstat_foundation import (
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec, TaskRef, TaskState,
    cloudpickle_dumps,
)
from stockstat_foundation.codec import CloudpickleCodec
from stockstat_foundation.transport import InProcessTransport, make_pair, HttpTransport
from stockstat_compute.backend.remote import RemoteComputeBackend
from stockstat_dispatcher import Dispatcher, MemoryTaskQueue, create_dispatcher_router


@pytest.fixture
def dispatcher_with_api():
    """创建 Dispatcher + FastAPI + TestClient + RemoteComputeBackend。"""
    d = Dispatcher(queue=MemoryTaskQueue())
    app = FastAPI()
    app.include_router(create_dispatcher_router(d))
    client = TestClient(app)
    backend = RemoteComputeBackend("http://testserver", http_client=client)
    return d, client, backend


def buy_hold(i, bar, data, ctx):
    if i == 0:
        from stockstat_compute import Signal
        return Signal(timestamp=bar["timestamp"], symbol="T", side="buy")
    return None


def make_spec(data=None, task_type="backtest"):
    cs = ComputeSpec(task_type=task_type, initial_cash=10000)
    if data is not None:
        cs.params["_inline_data"] = data
    if task_type == "backtest":
        cs.strategy_ref = f"cloudpickle:{cloudpickle_dumps(buy_hold)}"
    return TaskSpec(
        task_id=f"remote-{time.time_ns()}",
        data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
        compute_spec=cs,
    )


class TestRemoteSubmit:
    def test_submit_returns_task_ref(self, dispatcher_with_api):
        d, c, backend = dispatcher_with_api
        spec = make_spec()
        ref = backend.submit(spec)
        assert isinstance(ref, TaskRef)

    def test_get_status(self, dispatcher_with_api):
        d, c, backend = dispatcher_with_api
        spec = make_spec()
        ref = backend.submit(spec)
        info = backend.get(spec.task_id)
        assert info.task_id == spec.task_id
        assert info.state in (TaskState.PENDING, TaskState.RUNNING)

    def test_cancel(self, dispatcher_with_api):
        d, c, backend = dispatcher_with_api
        spec = make_spec()
        ref = backend.submit(spec)
        result = backend.cancel(spec.task_id)
        assert result is True


class TestRemoteWaitWithWorker:
    @pytest.fixture
    def e2e_setup(self):
        """完整 E2E：Dispatcher + Worker + RemoteBackend。"""
        d = Dispatcher(queue=MemoryTaskQueue())
        app = FastAPI()
        app.include_router(create_dispatcher_router(d))
        client = TestClient(app)
        backend = RemoteComputeBackend("http://testserver", http_client=client)
        # 注册一个 Worker
        d.register_worker({
            "worker_id": "test-w1",
            "concurrency": 2,
            "capabilities": ["backtest", "indicator", "batch_backtest"],
        })
        return d, client, backend

    def test_indicator_e2e(self, e2e_setup):
        d, c, backend = e2e_setup
        import numpy as np
        data = pd.Series(np.random.default_rng(42).normal(0, 1, 50).cumsum() + 100)
        spec = TaskSpec(
            task_id=f"e2e-ind-{time.time_ns()}",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "ma", "window": 10, "_inline_data": data},
            ),
        )
        ref = backend.submit(spec)
        # 模拟 Worker 拉取并执行
        assignment = d.assign_task("test-w1", ["indicator"])
        assert assignment is not None
        from stockstat_compute.executor import TaskExecutor
        executor = TaskExecutor()
        result = executor.run(assignment)
        # 回传结果
        d.on_complete("test-w1", assignment["task_spec"]["task_id"],
                      base64.b64encode(CloudpickleCodec().encode(result["result"])).decode("ascii"))
        # 客户端获取结果
        final = ref.wait(timeout=5)
        assert len(final) == 50

    def test_backtest_e2e(self, e2e_setup):
        d, c, backend = e2e_setup
        import numpy as np
        n = 50
        close = 100 * np.exp(np.cumsum(np.random.default_rng(42).normal(0.001, 0.02, n)))
        data = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": 1000.0,
        })
        spec = make_spec(data=data, task_type="backtest")
        ref = backend.submit(spec)
        # Worker 执行
        assignment = d.assign_task("test-w1", ["backtest"])
        assert assignment is not None
        from stockstat_compute.executor import TaskExecutor
        executor = TaskExecutor()
        result = executor.run(assignment)
        d.on_complete("test-w1", assignment["task_spec"]["task_id"],
                      base64.b64encode(CloudpickleCodec().encode(result["result"])).decode("ascii"))
        final = ref.wait(timeout=5)
        assert final.error is None
        assert final.metrics.n_trades >= 1


class TestRemoteClusterInfo:
    def test_cluster_info(self, dispatcher_with_api):
        d, c, backend = dispatcher_with_api
        info = backend.cluster_info()
        assert "dispatcher" in info

    def test_cluster_info_with_workers(self, dispatcher_with_api):
        d, c, backend = dispatcher_with_api
        d.register_worker({"worker_id": "w1", "concurrency": 4})
        info = backend.cluster_info()
        assert len(info["workers"]) == 1


class TestRemoteProtocolConformance:
    def test_compute_backend_protocol(self, dispatcher_with_api):
        from stockstat_foundation import ComputeBackend
        d, c, backend = dispatcher_with_api
        assert isinstance(backend, ComputeBackend)

    def test_name(self, dispatcher_with_api):
        d, c, backend = dispatcher_with_api
        assert backend.name == "remote"


class TestRemoteErrorHandling:
    def test_wait_failed_raises(self, dispatcher_with_api):
        from stockstat_foundation.errors import TaskError
        d, c, backend = dispatcher_with_api
        d.register_worker({"worker_id": "w1", "capabilities": ["backtest"]})
        spec = make_spec(task_type="backtest")
        # 不提供 _inline_data，backtest 会失败
        ref = backend.submit(spec)
        assignment = d.assign_task("w1", ["backtest"])
        if assignment:
            slice_id = assignment["task_spec"]["task_id"]
            d.on_fail("w1", slice_id, {"error_message": "test fail", "retryable": False})
        with pytest.raises(TaskError):
            ref.wait(timeout=5)

    def test_cancel_returns_true(self, dispatcher_with_api):
        d, c, backend = dispatcher_with_api
        spec = make_spec()
        backend.submit(spec)
        assert backend.cancel(spec.task_id) is True


class TestRemoteWithInProcessTransport:
    """用 InProcessTransport 测试 RemoteComputeBackend（不需要 HTTP）。"""

    @pytest.fixture
    def in_process_setup(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        # 用一个包装 Dispatcher 的 InProcessTransport
        # 实际上 RemoteComputeBackend 需要 HTTP，这里测试构造
        return d

    def test_construction_with_url(self):
        backend = RemoteComputeBackend("http://localhost:9000")
        assert backend.name == "remote"

    def test_construction_requires_url_or_transport(self):
        with pytest.raises(ValueError):
            RemoteComputeBackend()
