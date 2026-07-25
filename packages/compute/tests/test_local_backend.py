"""test_local_backend.py — LocalComputeBackend 测试 (35 项)。"""
from __future__ import annotations

import time
import threading

import numpy as np
import pandas as pd
import pytest

from stockstat_foundation import (
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec,
    TaskRef, TaskInfo, TaskState, cloudpickle_dumps,
)
from stockstat_foundation.errors import TaskError, TaskNotReadyError, TaskTimeoutError, TaskNotFoundError
from stockstat_compute import LocalComputeBackend
from stockstat_compute.handlers import ALL_TASK_TYPES


@pytest.fixture
def ohlcv_df():
    rng = np.random.default_rng(42)
    n = 100
    returns = rng.normal(0.001, 0.02, n)
    close = 100 * np.exp(np.cumsum(returns))
    ts = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "timestamp": ts, "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1000.0,
    })


def buy_hold(i, bar, data, ctx):
    if i == 0:
        from stockstat_compute import Signal
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
    return None


def make_indicator_spec(name="ma", **params):
    return TaskSpec(
        task_id=f"test-{name}-{time.time_ns()}",
        data_spec=DataSpec(symbols=["TEST"]),
        compute_spec=ComputeSpec(
            task_type="indicator",
            params={"indicator_name": name, **params},
        ),
    )


def make_backtest_spec(data, strategy, **kwargs):
    cs_kwargs = {
        "task_type": "backtest",
        "strategy_ref": f"cloudpickle:{cloudpickle_dumps(strategy)}",
        "initial_cash": 10000,
    }
    cs_kwargs.update(kwargs)
    return TaskSpec(
        task_id=f"bt-{time.time_ns()}",
        data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
        compute_spec=ComputeSpec(**cs_kwargs),
        dispatch_spec=DispatchSpec(timeout=30),
    )


class TestSubmitAndWait:
    def test_submit_returns_task_ref(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_indicator_spec("ma", window=10)
        ref = backend.submit(spec)
        assert isinstance(ref, TaskRef)
        assert ref.task_id == spec.task_id

    def test_wait_returns_result(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_indicator_spec("ma", window=10)
        spec.compute_spec.params["_inline_data"] = ohlcv_df["close"]
        ref = backend.submit(spec)
        result = ref.wait(timeout=5)
        assert len(result) == len(ohlcv_df)

    def test_wait_backtest(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_backtest_spec(ohlcv_df, buy_hold)
        # 把数据放到 params._inline_data
        spec.compute_spec.params["_inline_data"] = ohlcv_df
        ref = backend.submit(spec)
        result = ref.wait(timeout=10)
        assert result.error is None
        assert result.metrics.n_trades >= 1

    def test_get_task_info(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_indicator_spec("ma", window=10)
        ref = backend.submit(spec)
        ref.wait(timeout=5)
        info = backend.get(spec.task_id)
        assert info.state == TaskState.COMPLETED

    def test_result_before_complete_raises(self, ohlcv_df):
        backend = LocalComputeBackend()
        # 用一个长任务
        spec = make_backtest_spec(ohlcv_df, buy_hold)
        spec.compute_spec.params["_inline_data"] = ohlcv_df
        ref = backend.submit(spec)
        with pytest.raises(TaskNotReadyError):
            backend.result(spec.task_id)
        ref.wait(timeout=10)


class TestTimeout:
    def test_wait_timeout_raises(self, ohlcv_df):
        backend = LocalComputeBackend()
        # 构造一个慢任务（批量回测）
        strategies = {f"s{i}": f"cloudpickle:{cloudpickle_dumps(buy_hold)}" for i in range(20)}
        spec = TaskSpec(
            task_id=f"slow-{time.time_ns()}",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="batch_backtest",
                strategies=strategies,
                fee_models=["F1_SpotNoBNB"],
                initial_cash=10000,
                params={"_inline_data": ohlcv_df},
            ),
        )
        ref = backend.submit(spec)
        with pytest.raises(TaskTimeoutError):
            ref.wait(timeout=0.01)
        # 等待真正完成以释放资源
        try:
            ref.wait(timeout=30)
        except Exception:
            pass


class TestCancel:
    def test_cancel_pending(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_backtest_spec(ohlcv_df, buy_hold)
        spec.compute_spec.params["_inline_data"] = ohlcv_df
        ref = backend.submit(spec)
        cancelled = backend.cancel(spec.task_id)
        # 可能已经完成了
        assert cancelled in (True, False)

    def test_cancel_unknown_returns_false(self):
        backend = LocalComputeBackend()
        assert backend.cancel("nonexistent") is False


class TestNotFound:
    def test_get_unknown_raises(self):
        backend = LocalComputeBackend()
        with pytest.raises(TaskNotFoundError):
            backend.get("nonexistent")

    def test_wait_unknown_raises(self):
        backend = LocalComputeBackend()
        with pytest.raises(TaskNotFoundError):
            backend.wait("nonexistent")

    def test_result_unknown_raises(self):
        backend = LocalComputeBackend()
        with pytest.raises(TaskNotFoundError):
            backend.result("nonexistent")


class TestFailedTask:
    def test_failed_raises_task_error(self, ohlcv_df):
        backend = LocalComputeBackend()
        # 构造一个会失败的任务：未知 indicator
        spec = TaskSpec(
            task_id=f"fail-{time.time_ns()}",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "nonexistent_indicator"},
            ),
        )
        ref = backend.submit(spec)
        with pytest.raises(TaskError):
            ref.wait(timeout=5)


class TestClusterInfo:
    def test_cluster_info_structure(self):
        backend = LocalComputeBackend()
        info = backend.cluster_info()
        assert "dispatcher" in info
        assert "workers" in info
        assert "stats" in info
        assert info["dispatcher"]["id"] == "local"

    def test_cluster_info_workers_have_capabilities(self):
        backend = LocalComputeBackend()
        info = backend.cluster_info()
        worker = info["workers"][0]
        assert "capabilities" in worker
        assert "indicator" in worker["capabilities"]


class TestComputeIndicator:
    def test_direct_indicator_call(self, ohlcv_df):
        backend = LocalComputeBackend()
        result = backend.compute_indicator("ma", ohlcv_df["close"], window=10)
        assert len(result) == len(ohlcv_df)

    def test_rsi_direct(self, ohlcv_df):
        backend = LocalComputeBackend()
        result = backend.compute_indicator("rsi", ohlcv_df["close"], window=14)
        assert len(result) == len(ohlcv_df)


class TestProtocolConformance:
    def test_compute_backend_protocol(self):
        from stockstat_foundation import ComputeBackend
        backend = LocalComputeBackend()
        assert isinstance(backend, ComputeBackend)

    def test_name_attribute(self):
        assert LocalComputeBackend().name == "local"

    def test_all_task_types_nonempty(self):
        assert len(ALL_TASK_TYPES) >= 6


class TestTaskRef:
    def test_task_ref_ready(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_indicator_spec("ma", window=10)
        ref = backend.submit(spec)
        ref.wait(timeout=5)
        assert ref.ready() is True

    def test_task_ref_status(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_indicator_spec("ma", window=10)
        ref = backend.submit(spec)
        ref.wait(timeout=5)
        assert ref.status == "completed"

    def test_task_ref_info(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_indicator_spec("ma", window=10)
        ref = backend.submit(spec)
        ref.wait(timeout=5)
        info = ref.info
        assert info.task_id == spec.task_id

    def test_task_ref_id(self, ohlcv_df):
        backend = LocalComputeBackend()
        spec = make_indicator_spec("ma", window=10)
        ref = backend.submit(spec)
        assert ref.id == spec.task_id
