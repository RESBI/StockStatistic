"""test_dispatcher.py — Dispatcher 主体测试 (40 项)。"""
from __future__ import annotations

import base64
import time

import pytest

from stockstat_foundation import (
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec,
    cloudpickle_dumps,
)
from stockstat_foundation.codec import CloudpickleCodec
from stockstat_dispatcher import Dispatcher, MemoryTaskQueue


def make_backtest_spec(task_id="t1", strategy=None, **kwargs):
    if strategy is None:
        def strategy(i, bar, data, ctx):
            if i == 0:
                from stockstat_compute import Signal
                return Signal(timestamp=bar["timestamp"], symbol="T", side="buy")
            return None
    cs = ComputeSpec(
        task_type="backtest",
        strategy_ref=f"cloudpickle:{cloudpickle_dumps(strategy)}",
        initial_cash=kwargs.get("initial_cash", 10000),
    )
    return TaskSpec(
        task_id=task_id,
        data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
        compute_spec=cs,
        dispatch_spec=DispatchSpec(**{k: v for k, v in kwargs.items()
                                       if k in ("split_strategy", "max_workers", "priority", "timeout")}),
    )


class TestSubmit:
    def test_submit_returns_dict(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = make_backtest_spec()
        result = d.submit(spec)
        assert "task_id" in result
        assert result["status"] == "pending"
        assert result["n_slices"] >= 1

    def test_submit_no_split(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = make_backtest_spec()
        result = d.submit(spec)
        assert result["n_slices"] == 1

    def test_submit_param_wise_batch(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = TaskSpec(
            task_id="batch1",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="batch_backtest",
                strategies={f"S{i}": f"cloudpickle:{cloudpickle_dumps(lambda i,b,d,c: None)}"
                            for i in range(10)},
                fee_models=["F1", "F2"],
            ),
            dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=4),
        )
        result = d.submit(spec)
        assert result["n_slices"] <= 4

    def test_submit_symbol_wise(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = TaskSpec(
            task_id="sym1",
            data_spec=DataSpec(symbols=["BTC", "ETH", "LTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
            dispatch_spec=DispatchSpec(split_strategy="symbol_wise"),
        )
        result = d.submit(spec)
        assert result["n_slices"] == 3


class TestStatus:
    def test_get_status_pending(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = make_backtest_spec()
        d.submit(spec)
        status = d.get_status(spec.task_id)
        assert status["task_id"] == spec.task_id
        assert status["state"] in ("pending", "running")

    def test_get_status_not_found(self):
        from stockstat_foundation.errors import TaskNotFoundError
        d = Dispatcher(queue=MemoryTaskQueue())
        with pytest.raises(TaskNotFoundError):
            d.get_status("nonexistent")

    def test_get_status_has_progress(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = make_backtest_spec()
        d.submit(spec)
        status = d.get_status(spec.task_id)
        assert "progress" in status
        assert "n_slices" in status


class TestAssignTask:
    def test_assign_returns_none_when_empty(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 1, "capabilities": ["backtest"]})
        result = d.assign_task("w1", ["backtest"])
        assert result is None

    def test_assign_returns_assignment(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 1, "capabilities": ["backtest"]})
        spec = make_backtest_spec()
        # 内联数据
        import pandas as pd
        import numpy as np
        data = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=20, freq="D"),
            "open": np.arange(20), "high": np.arange(1, 21),
            "low": np.arange(20), "close": np.arange(2, 22),
            "volume": 100,
        })
        spec.compute_spec.params["_inline_data"] = data
        d.submit(spec)
        result = d.assign_task("w1", ["backtest"])
        assert result is not None
        assert "task_spec" in result
        assert "data" in result

    def test_assign_capability_filter(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 1, "capabilities": ["indicator"]})
        spec = make_backtest_spec()
        d.submit(spec)
        # Worker 只支持 indicator，不支持 backtest
        result = d.assign_task("w1", ["indicator"])
        assert result is None  # 被跳过

    def test_assign_custom_capability_matches_all(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 1, "capabilities": ["custom"]})
        spec = make_backtest_spec()
        d.submit(spec)
        result = d.assign_task("w1", ["custom"])
        # custom 应匹配所有 task_type
        assert result is not None


class TestCompleteAndFail:
    def test_complete_single_slice(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 1, "capabilities": ["backtest"]})
        spec = make_backtest_spec()
        d.submit(spec)
        assignment = d.assign_task("w1", ["backtest"])
        slice_id = assignment["task_spec"]["task_id"]
        # 模拟 Worker 完成
        result_bytes = CloudpickleCodec().encode({"result": "ok"})
        d.on_complete("w1", slice_id, base64.b64encode(result_bytes).decode("ascii"))
        status = d.get_status(spec.task_id)
        assert status["state"] == "completed"

    def test_complete_multiple_slices(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 1, "capabilities": ["backtest"]})
        spec = TaskSpec(
            task_id="multi",
            data_spec=DataSpec(symbols=["BTC", "ETH"]),
            compute_spec=ComputeSpec(task_type="backtest"),
            dispatch_spec=DispatchSpec(split_strategy="symbol_wise"),
        )
        d.submit(spec)
        # 分成 2 个 slice
        status = d.get_status("multi")
        assert status["n_slices"] == 2
        # 完成 2 个 slice
        for _ in range(2):
            assignment = d.assign_task("w1", ["backtest"])
            if assignment is None:
                break
            slice_id = assignment["task_spec"]["task_id"]
            d.on_complete("w1", slice_id,
                          base64.b64encode(CloudpickleCodec().encode({"r": 1})).decode("ascii"))
        status = d.get_status("multi")
        assert status["state"] == "completed"

    def test_fail_marks_failed(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 1, "capabilities": ["backtest"]})
        spec = make_backtest_spec()
        d.submit(spec)
        assignment = d.assign_task("w1", ["backtest"])
        slice_id = assignment["task_spec"]["task_id"]
        d.on_fail("w1", slice_id, {"error_message": "test error", "retryable": False})
        status = d.get_status(spec.task_id)
        assert status["state"] == "failed"


class TestCancel:
    def test_cancel_pending(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = make_backtest_spec()
        d.submit(spec)
        assert d.cancel(spec.task_id) is True
        status = d.get_status(spec.task_id)
        assert status["state"] == "cancelled"

    def test_cancel_unknown_returns_false(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        assert d.cancel("nonexistent") is False


class TestResult:
    def test_get_result_completed(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 1, "capabilities": ["backtest"]})
        spec = make_backtest_spec()
        d.submit(spec)
        assignment = d.assign_task("w1", ["backtest"])
        slice_id = assignment["task_spec"]["task_id"]
        result_bytes = CloudpickleCodec().encode({"x": 1})
        d.on_complete("w1", slice_id, base64.b64encode(result_bytes).decode("ascii"))
        result = d.get_result(spec.task_id)
        assert CloudpickleCodec().decode(result) == {"x": 1}

    def test_get_result_not_ready(self):
        from stockstat_foundation.errors import TaskNotReadyError
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = make_backtest_spec()
        d.submit(spec)
        with pytest.raises(TaskNotReadyError):
            d.get_result(spec.task_id)


class TestClusterInfo:
    def test_cluster_info_structure(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        info = d.cluster_info()
        assert "dispatcher" in info
        assert "workers" in info
        assert "stats" in info
        assert info["dispatcher"]["id"] == "dispatch-primary"

    def test_cluster_info_with_workers(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1", "concurrency": 4, "capabilities": []})
        info = d.cluster_info()
        assert len(info["workers"]) == 1

    def test_autoscaler_metrics(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        m = d.autoscaler_metrics()
        assert "queue_depth" in m
        assert "scale_up_recommended" in m

    def test_task_history(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        h = d.task_history()
        assert "history" in h
        assert h["total"] == 0


class TestWorkerManagement:
    def test_register_worker(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        result = d.register_worker({"worker_id": "w1", "alias": "alpha"})
        assert result["worker_id"] == "w1"
        assert result["status"] == "registered"

    def test_heartbeat(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1"})
        d.heartbeat({"worker_id": "w1", "active_tasks": 1})
        info = d.cluster_info()
        assert info["workers"][0]["active_tasks"] == 1

    def test_unregister(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        d.register_worker({"worker_id": "w1"})
        d.unregister_worker("w1")
        info = d.cluster_info()
        assert len(info["workers"]) == 0  # offline 默认不显示


class TestPartialResults:
    def test_on_partial(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = make_backtest_spec()
        d.submit(spec)
        d.on_partial(spec.task_id, {"progress": 0.5})
        # 不抛异常即可
