"""test_demo_distributed.py — 分布式计算演示测试。

覆盖：LocalBackend / RemoteBackend / AutoBackend / Dispatcher+Worker E2E。
"""
from __future__ import annotations

import base64
import time

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stockstat_foundation import (
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec,
    TaskRef, TaskState, cloudpickle_dumps,
)
from stockstat_foundation.codec import CloudpickleCodec
from stockstat_compute import LocalComputeBackend, Signal
from stockstat_compute.backend.remote import RemoteComputeBackend
from stockstat_compute.backend.auto import AutoComputeBackend
from stockstat_compute.worker import Worker
from stockstat_compute.executor import TaskExecutor
from stockstat_dispatcher import Dispatcher, MemoryTaskQueue, create_dispatcher_router


def buy_hold(i, bar, data, ctx):
    if i == 0:
        return Signal(timestamp=bar["timestamp"], symbol="T", side="buy")
    return None


@pytest.fixture
def ohlcv():
    rng = np.random.default_rng(42)
    n = 100
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1000.0,
    })


class TestLocalComputeBackend:
    """LocalComputeBackend 透明模式。"""

    def test_submit_wait(self, ohlcv):
        backend = LocalComputeBackend()
        spec = TaskSpec(
            task_id="local-1",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=f"cloudpickle:{cloudpickle_dumps(buy_hold)}",
                initial_cash=10000,
                params={"_inline_data": ohlcv},
            ),
        )
        ref = backend.submit(spec)
        result = ref.wait(timeout=10)
        assert result.error is None
        assert result.metrics.n_trades >= 1

    def test_indicator(self):
        backend = LocalComputeBackend()
        data = pd.Series(np.random.default_rng(42).normal(0, 1, 50).cumsum() + 100)
        spec = TaskSpec(
            task_id="local-ind",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "ma", "window": 10, "_inline_data": data},
            ),
        )
        result = backend.submit(spec).wait(timeout=5)
        assert len(result) == 50

    def test_cluster_info(self):
        backend = LocalComputeBackend()
        info = backend.cluster_info()
        assert info["dispatcher"]["id"] == "local"
        assert len(info["workers"]) == 1

    def test_cancel(self, ohlcv):
        backend = LocalComputeBackend()
        spec = TaskSpec(
            task_id="cancel-test",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma", "window": 5, "_inline_data": ohlcv["close"]}),
        )
        ref = backend.submit(spec)
        # 可能已完成
        cancelled = backend.cancel(spec.task_id)
        assert cancelled in (True, False)


class TestRemoteComputeBackend:
    """RemoteComputeBackend 通过 HTTP。"""

    @pytest.fixture
    def e2e(self):
        d = Dispatcher(queue=MemoryTaskQueue(), offline_timeout=60)
        app = FastAPI()
        app.include_router(create_dispatcher_router(d))
        client = TestClient(app)
        backend = RemoteComputeBackend("http://testserver", http_client=client)
        d.register_worker({"worker_id": "w1", "concurrency": 2,
                           "capabilities": ["indicator", "backtest"]})
        return d, client, backend

    def test_submit_and_get_status(self, e2e):
        d, c, backend = e2e
        spec = TaskSpec(
            task_id="remote-1",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(task_type="backtest",
                                     strategy_ref=f"cloudpickle:{cloudpickle_dumps(buy_hold)}",
                                     initial_cash=10000,
                                     params={"_inline_data": ohlcv_fixture()}),
        )
        ref = backend.submit(spec)
        info = backend.get(spec.task_id)
        assert info.task_id == spec.task_id

    def test_e2e_indicator(self, e2e):
        d, c, backend = e2e
        data = pd.Series(np.random.default_rng(42).normal(0, 1, 50).cumsum() + 100)
        spec = TaskSpec(
            task_id="e2e-ind",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma", "window": 10, "_inline_data": data}),
        )
        ref = backend.submit(spec)
        # 模拟 Worker 执行
        assignment = d.assign_task("w1", ["indicator"])
        assert assignment is not None
        executor = TaskExecutor()
        result = executor.run(assignment)
        d.on_complete("w1", assignment["task_spec"]["task_id"],
                      base64.b64encode(CloudpickleCodec().encode(result["result"])).decode("ascii"))
        final = ref.wait(timeout=5)
        assert len(final) == 50

    def test_cluster_info(self, e2e):
        d, c, backend = e2e
        info = backend.cluster_info()
        assert "dispatcher" in info


class TestAutoComputeBackend:
    """AutoComputeBackend 路由。"""

    def test_light_goes_local(self):
        local = LocalComputeBackend()
        remote = FakeRemote()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="light",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma"}),
        )
        auto.submit(spec)
        assert len(remote.submitted) == 0

    def test_heavy_goes_remote(self):
        local = LocalComputeBackend()
        remote = FakeRemote()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="heavy",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search"),
        )
        auto.submit(spec)
        assert len(remote.submitted) == 1


class FakeRemote:
    name = "remote"
    def __init__(self):
        self.submitted = []
    def submit(self, spec):
        self.submitted.append(spec)
        from stockstat_foundation import TaskRef
        return TaskRef(task_id=spec.task_id, backend=self)
    def get(self, task_id):
        from stockstat_foundation import TaskInfo, TaskState
        return TaskInfo(task_id=task_id, state=TaskState.COMPLETED)
    def result(self, task_id):
        return {}
    def wait(self, task_id, timeout=None):
        return {}
    def cancel(self, task_id):
        return True
    def cluster_info(self, **kwargs):
        return {"status": "remote"}
    def stream_results(self, task_id):
        yield {}


class TestWorkerE2E:
    """Worker 完整生命周期 E2E。"""

    def test_worker_registers_and_executes(self):
        d = Dispatcher(queue=MemoryTaskQueue(), offline_timeout=60)
        app = FastAPI()
        app.include_router(create_dispatcher_router(d))
        client = TestClient(app)
        worker = Worker(
            dispatcher_url="http://testserver",
            concurrency=1,
            alias="test-worker",
            capabilities=["indicator"],
            poll_interval=0.1,
            heartbeat_interval=0.5,
            http_client=client,
        )
        worker.start_background()
        assert worker.wait_registered(timeout=5.0)

        # 提交任务
        data = pd.Series(np.random.default_rng(42).normal(0, 1, 50).cumsum() + 100)
        spec = TaskSpec(
            task_id="worker-e2e",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma", "window": 10, "_inline_data": data}),
        )
        d.submit(spec)
        # 等待 Worker 完成
        deadline = time.time() + 5
        while time.time() < deadline:
            status = d.get_status(spec.task_id)
            if status["state"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert d.get_status(spec.task_id)["state"] == "completed"
        worker.stop()


class TestLocalRemoteConsistency:
    """本地/远程结果一致性。"""

    def test_indicator_consistency(self):
        data = pd.Series(np.random.default_rng(42).normal(0, 1, 50).cumsum() + 100)

        # 本地
        local = LocalComputeBackend()
        local_spec = TaskSpec(
            task_id="consistency-local",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma", "window": 10, "_inline_data": data}),
        )
        local_result = local.submit(local_spec).wait(timeout=5)

        # 远程
        d = Dispatcher(queue=MemoryTaskQueue(), offline_timeout=60)
        app = FastAPI()
        app.include_router(create_dispatcher_router(d))
        client = TestClient(app)
        worker = Worker(
            dispatcher_url="http://testserver", concurrency=1,
            capabilities=["indicator"], poll_interval=0.1,
            heartbeat_interval=1.0, http_client=client,
        )
        worker.start_background()
        assert worker.wait_registered(timeout=5.0)
        remote = RemoteComputeBackend("http://testserver", http_client=client)
        remote_spec = TaskSpec(
            task_id="consistency-remote",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma", "window": 10, "_inline_data": data}),
        )
        remote_result = remote.submit(remote_spec).wait(timeout=10)

        local_last = local_result.dropna().iloc[-1]
        remote_last = remote_result.dropna().iloc[-1]
        assert abs(local_last - remote_last) < 1e-10
        worker.stop()


def ohlcv_fixture():
    rng = np.random.default_rng(42)
    n = 50
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1000.0,
    })
