"""test_worker.py — Worker 生命周期测试 (25 项)。"""
from __future__ import annotations

import base64
import threading
import time

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec, DispatchSpec
from stockstat_foundation.codec import CloudpickleCodec
from stockstat_compute.worker import Worker
from stockstat_dispatcher import Dispatcher, MemoryTaskQueue, create_dispatcher_router


@pytest.fixture
def e2e_env():
    """完整 E2E 环境：Dispatcher + FastAPI + Worker。"""
    d = Dispatcher(queue=MemoryTaskQueue(), offline_timeout=60.0)
    app = FastAPI()
    app.include_router(create_dispatcher_router(d))
    client = TestClient(app)
    # Worker 使用 TestClient 作为 HTTP 客户端
    worker = Worker(
        dispatcher_url="http://testserver",
        concurrency=2,
        alias="test-worker",
        capabilities=["indicator", "backtest", "batch_backtest"],
        poll_interval=0.1,
        heartbeat_interval=0.5,
        http_client=client,
    )
    worker.start_background()
    # 等待注册
    registered = worker.wait_registered(timeout=5.0)
    return d, client, worker, registered


class TestWorkerRegistration:
    def test_worker_registers(self, e2e_env):
        d, c, worker, registered = e2e_env
        assert registered is True
        assert worker.worker_id is not None

    def test_worker_appears_in_cluster(self, e2e_env):
        d, c, worker, registered = e2e_env
        if not registered:
            pytest.skip("Worker not registered")
        info = d.cluster_info()
        assert len(info["workers"]) >= 1
        assert info["workers"][0]["alias"] == "test-worker"

    def test_worker_capabilities(self, e2e_env):
        d, c, worker, registered = e2e_env
        if not registered:
            pytest.skip("Worker not registered")
        info = d.cluster_info()
        w = info["workers"][0]
        assert "indicator" in w["capabilities"]
        assert "backtest" in w["capabilities"]


class TestWorkerHeartbeat:
    def test_heartbeat_updates(self, e2e_env):
        d, c, worker, registered = e2e_env
        if not registered:
            pytest.skip("Worker not registered")
        time.sleep(1.0)  # 等待心跳
        info = d.cluster_info()
        if info["workers"]:
            assert info["workers"][0]["status"] in ("online", "busy")


class TestWorkerExecution:
    def test_indicator_execution(self, e2e_env):
        d, c, worker, registered = e2e_env
        if not registered:
            pytest.skip("Worker not registered")
        import numpy as np
        data = pd.Series(np.random.default_rng(42).normal(0, 1, 50).cumsum() + 100)
        spec = TaskSpec(
            task_id=f"worker-ind-{time.time_ns()}",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "ma", "window": 10, "_inline_data": data},
            ),
        )
        d.submit(spec)
        # 等待 Worker 拉取并完成
        deadline = time.time() + 5.0
        while time.time() < deadline:
            status = d.get_status(spec.task_id)
            if status["state"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        status = d.get_status(spec.task_id)
        assert status["state"] == "completed"

    def test_backtest_execution(self, e2e_env):
        d, c, worker, registered = e2e_env
        if not registered:
            pytest.skip("Worker not registered")
        import numpy as np
        n = 30
        close = 100 * np.exp(np.cumsum(np.random.default_rng(42).normal(0.001, 0.02, n)))
        data = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": 1000.0,
        })
        from stockstat_foundation import cloudpickle_dumps
        def strat(i, bar, d, ctx):
            if i == 0:
                from stockstat_compute import Signal
                return Signal(timestamp=bar["timestamp"], symbol="T", side="buy")
            return None
        spec = TaskSpec(
            task_id=f"worker-bt-{time.time_ns()}",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=f"cloudpickle:{cloudpickle_dumps(strat)}",
                initial_cash=10000,
                params={"_inline_data": data},
            ),
        )
        d.submit(spec)
        deadline = time.time() + 10.0
        while time.time() < deadline:
            status = d.get_status(spec.task_id)
            if status["state"] in ("completed", "failed"):
                break
            time.sleep(0.2)
        status = d.get_status(spec.task_id)
        assert status["state"] == "completed"
        result = d.get_result(spec.task_id)
        bt_result = CloudpickleCodec().decode(result)
        assert bt_result.error is None


class TestWorkerLifecycle:
    def test_stop(self, e2e_env):
        d, c, worker, registered = e2e_env
        worker.stop()
        # 不抛异常即可

    def test_drain(self, e2e_env):
        d, c, worker, registered = e2e_env
        worker.drain()
        assert worker._draining is True

    def test_preempt(self, e2e_env):
        d, c, worker, registered = e2e_env
        assert worker.preempt("slice-1") is True
        assert "slice-1" in worker._preempted

    def test_resume(self, e2e_env):
        d, c, worker, registered = e2e_env
        worker.preempt("slice-1")
        assert worker.resume("slice-1") is True
        assert "slice-1" not in worker._preempted


class TestWorkerProperties:
    def test_alias(self, e2e_env):
        d, c, worker, registered = e2e_env
        assert worker.alias == "test-worker"

    def test_worker_id_after_register(self, e2e_env):
        d, c, worker, registered = e2e_env
        if registered:
            assert worker.worker_id is not None

    def test_concurrency(self, e2e_env):
        d, c, worker, registered = e2e_env
        assert worker._concurrency == 2


class TestWorkerConsistency:
    """本地/远程结果一致性验证。"""

    def test_local_remote_consistency(self):
        """同一 TaskSpec，Local 与 Remote 结果应一致。"""
        import numpy as np
        # 本地后端
        from stockstat_compute import LocalComputeBackend
        local = LocalComputeBackend()
        # 远程后端（通过 Dispatcher + Worker）
        d = Dispatcher(queue=MemoryTaskQueue(), offline_timeout=60.0)
        app = FastAPI()
        app.include_router(create_dispatcher_router(d))
        client = TestClient(app)
        worker = Worker(
            dispatcher_url="http://testserver",
            concurrency=1,
            capabilities=["indicator"],
            poll_interval=0.1,
            heartbeat_interval=1.0,
            http_client=client,
        )
        worker.start_background()
        assert worker.wait_registered(timeout=5.0)

        from stockstat_compute.backend.remote import RemoteComputeBackend
        remote = RemoteComputeBackend("http://testserver", http_client=client)

        data = pd.Series(np.random.default_rng(42).normal(0, 1, 50).cumsum() + 100)
        # 本地提交
        local_spec = TaskSpec(
            task_id=f"local-{time.time_ns()}",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "ma", "window": 10, "_inline_data": data},
            ),
        )
        local_result = local.submit(local_spec).wait(timeout=5)

        # 远程提交
        remote_spec = TaskSpec(
            task_id=f"remote-{time.time_ns()}",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "ma", "window": 10, "_inline_data": data},
            ),
        )
        remote_ref = remote.submit(remote_spec)
        remote_result = remote_ref.wait(timeout=10)

        # 结果应一致（最后一个非 NaN 值）
        local_last = local_result.dropna().iloc[-1] if hasattr(local_result, "dropna") else local_result
        remote_last = remote_result.dropna().iloc[-1] if hasattr(remote_result, "dropna") else remote_result
        assert abs(local_last - remote_last) < 1e-10

        worker.stop()
