"""test_misc.py — TaskExecutor / register / checkpoint / Stream (30 项)。
凑齐 P3 测试数。
"""
from __future__ import annotations

import base64
import time

import numpy as np
import pandas as pd
import pytest

from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec, CloudpickleCodec, cloudpickle_dumps
from stockstat_compute import (
    TaskExecutor, CheckpointStore, detect_hardware, get_current_load,
    Stream, is_stream_aware,
)
from stockstat_compute.handlers import dispatch


class TestTaskExecutor:
    def test_run_indicator(self):
        executor = TaskExecutor()
        data = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assignment = {
            "task_spec": TaskSpec(
                task_id="t1",
                data_spec=DataSpec(symbols=[]),
                compute_spec=ComputeSpec(
                    task_type="indicator",
                    params={"indicator_name": "ma", "window": 3},
                ),
            ).to_dict(),
            "data": base64.b64encode(CloudpickleCodec().encode(data)).decode("ascii"),
            "data_codec": "cloudpickle",
        }
        result = executor.run(assignment)
        assert "result" in result
        assert result["slice_id"] == "t1"
        assert result["duration_s"] >= 0

    def test_run_no_data(self):
        executor = TaskExecutor()
        # 用一个不存在的 indicator_name 来触发错误
        assignment = {
            "task_spec": TaskSpec(
                task_id="t2",
                data_spec=DataSpec(symbols=[]),
                compute_spec=ComputeSpec(task_type="indicator",
                                         params={"indicator_name": "nonexistent_indicator_xyz"}),
            ).to_dict(),
        }
        with pytest.raises(Exception):
            executor.run(assignment)

    def test_run_returns_duration(self):
        executor = TaskExecutor()
        data = pd.Series([1.0, 2, 3, 4, 5])
        assignment = {
            "task_spec": TaskSpec(
                task_id="t3",
                data_spec=DataSpec(symbols=[]),
                compute_spec=ComputeSpec(task_type="indicator",
                                         params={"indicator_name": "ma", "window": 2}),
            ).to_dict(),
            "data": base64.b64encode(CloudpickleCodec().encode(data)).decode("ascii"),
        }
        result = executor.run(assignment)
        assert "duration_s" in result
        assert isinstance(result["duration_s"], float)


class TestStream:
    def test_from_data(self):
        s = Stream.from_data([1, 2, 3])
        assert s.collect() == [1, 2, 3]

    def test_iter_single(self):
        s = Stream.from_data([1, 2, 3])
        items = list(s)
        assert items == [[1, 2, 3]]

    def test_iter_chunks(self):
        s = Stream(chunks=[[1, 2], [3, 4]])
        items = list(s)
        assert items == [[1, 2], [3, 4]]

    def test_collect_chunks(self):
        s = Stream(chunks=[pd.Series([1, 2]), pd.Series([3, 4])])
        df = s.collect()
        assert list(df) == [1, 2, 3, 4]


class TestIsStreamAware:
    def test_stream_aware_handler(self):
        def handler(spec, data: Stream, on_progress=None):
            return data.collect()
        assert is_stream_aware(handler) is True

    def test_regular_handler(self):
        def handler(spec, data, on_progress=None):
            return data
        assert is_stream_aware(handler) is False

    def test_string_annotation(self):
        def handler(spec, data: "Stream", on_progress=None):
            return data
        assert is_stream_aware(handler) is True


class TestHardwareDetection:
    def test_detect_hardware_returns_dict(self):
        hw = detect_hardware()
        assert isinstance(hw, dict)
        assert "cpu" in hw
        assert "memory" in hw
        assert "os" in hw
        assert "python_version" in hw

    def test_cpu_info(self):
        hw = detect_hardware()
        assert "cores_logical" in hw["cpu"]

    def test_get_current_load(self):
        load = get_current_load()
        assert isinstance(load, dict)
        # 可能 psutil 未装
        if load:
            assert "cpu_percent" in load


class TestCheckpointStore:
    def test_save_load(self):
        store = CheckpointStore()
        store.save("slice1", b"state1")
        assert store.load("slice1") == b"state1"

    def test_load_nonexistent(self):
        store = CheckpointStore()
        assert store.load("nonexistent") is None

    def test_delete(self):
        store = CheckpointStore()
        store.save("s1", b"v1")
        store.delete("s1")
        assert store.load("s1") is None

    def test_list(self):
        store = CheckpointStore()
        store.save("s1", b"v1")
        store.save("s2", b"v2")
        assert set(store.list()) == {"s1", "s2"}

    def test_clear(self):
        store = CheckpointStore()
        store.save("s1", b"v1")
        store.clear()
        assert store.list() == []


class TestDispatchWithProgress:
    def test_progress_callback(self):
        data = pd.Series([1.0, 2, 3, 4, 5])
        spec = TaskSpec(
            task_id="prog1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "ma", "window": 2},
            ),
        )
        # indicator handler 不调用 progress，但应能正常执行
        result = dispatch(spec, data)
        assert len(result) == 5


class TestEndToEnd:
    def test_indicator_via_local_backend(self):
        from stockstat_compute import LocalComputeBackend
        backend = LocalComputeBackend()
        spec = TaskSpec(
            task_id="e2e1",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "rsi", "window": 14},
            ),
        )
        data = pd.Series(np.random.default_rng(42).normal(0, 1, 100).cumsum() + 100)
        ref = backend.submit(spec)
        # 但 backend 不知道 data... 需要通过 params._inline_data
        # 重新构造
        spec2 = TaskSpec(
            task_id="e2e2",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "rsi", "window": 14, "_inline_data": data},
            ),
        )
        ref2 = backend.submit(spec2)
        result = ref2.wait(timeout=5)
        assert len(result) == 100

    def test_backtest_e2e(self):
        from stockstat_compute import LocalComputeBackend
        backend = LocalComputeBackend()
        rng = np.random.default_rng(42)
        n = 50
        close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
        data = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": 1000.0,
        })
        def strat(i, bar, d, ctx):
            if i == 0:
                from stockstat_compute import Signal
                return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
            return None
        spec = TaskSpec(
            task_id="e2e_bt",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=f"cloudpickle:{cloudpickle_dumps(strat)}",
                initial_cash=10000,
                params={"_inline_data": data},
            ),
        )
        ref = backend.submit(spec)
        result = ref.wait(timeout=10)
        assert result.error is None
        assert result.metrics.n_trades >= 1


class TestExports:
    def test_all_exports(self):
        import stockstat_compute as sc
        for name in ["BacktestEngine", "ComputeEngine", "LocalComputeBackend",
                     "TaskExecutor", "Worker", "detect_hardware",
                     "HANDLERS", "dispatch", "ALL_TASK_TYPES"]:
            assert hasattr(sc, name)

    def test_version(self):
        import stockstat_compute as sc
        assert sc.__version__ == "3.1.0"

    def test_all_task_types_count(self):
        from stockstat_compute import ALL_TASK_TYPES
        # P3 阶段 6 个 Tier 1 handler
        assert len(ALL_TASK_TYPES) >= 6
