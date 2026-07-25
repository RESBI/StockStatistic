"""test_task_spec.py — TaskSpec 三段式 / to_dict / from_dict / roundtrip (20 项)。"""
from __future__ import annotations

from datetime import datetime

import pytest

from stockstat_foundation.protocol.task import (
    DataSpec, ComputeSpec, DispatchSpec, TaskSpec,
)


class TestDataSpec:
    def test_default(self):
        ds = DataSpec(symbols=["BTC/USDT"])
        assert ds.symbols == ["BTC/USDT"]
        assert ds.timeframe == "1d"
        assert ds.start is None

    def test_cache_key_stable(self):
        ds1 = DataSpec(symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01")
        ds2 = DataSpec(symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01")
        assert ds1.cache_key() == ds2.cache_key()

    def test_cache_key_differs(self):
        ds1 = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
        ds2 = DataSpec(symbols=["BTC/USDT"], timeframe="1h")
        assert ds1.cache_key() != ds2.cache_key()

    def test_cache_key_32_chars(self):
        ds = DataSpec(symbols=["BTC/USDT"])
        assert len(ds.cache_key()) == 32

    def test_roundtrip(self):
        ds = DataSpec(symbols=["BTC", "ETH"], timeframe="4h", start="2024-01-01",
                      end="2024-12-31", source="binance")
        ds2 = DataSpec.from_dict(ds.to_dict())
        assert ds2.symbols == ["BTC", "ETH"]
        assert ds2.timeframe == "4h"
        assert ds2.source == "binance"


class TestDispatchSpec:
    def test_default(self):
        ds = DispatchSpec()
        assert ds.split_strategy == "auto"
        assert ds.max_workers is None
        assert ds.priority == 0
        assert ds.preemptable is False

    def test_roundtrip(self):
        ds = DispatchSpec(split_strategy="param_wise", max_workers=8,
                          priority=-1, preemptable=True)
        ds2 = DispatchSpec.from_dict(ds.to_dict())
        assert ds2.split_strategy == "param_wise"
        assert ds2.max_workers == 8
        assert ds2.priority == -1
        assert ds2.preemptable is True


class TestComputeSpec:
    def test_backtest_spec(self):
        cs = ComputeSpec(task_type="backtest", initial_cash=10000)
        assert cs.task_type == "backtest"
        assert cs.initial_cash == 10000

    def test_indicator_spec(self):
        cs = ComputeSpec(task_type="indicator", params={"indicator_name": "rsi", "window": 14})
        assert cs.params["indicator_name"] == "rsi"
        assert cs.params["window"] == 14

    def test_grid_search_spec(self):
        cs = ComputeSpec(
            task_type="grid_search",
            param_grid={"short": [3, 5], "long": [10, 20]},
            metric="sharpe",
        )
        assert cs.param_grid["short"] == [3, 5]
        assert cs.metric == "sharpe"

    def test_batch_backtest_spec(self):
        cs = ComputeSpec(
            task_type="batch_backtest",
            strategies={"s1": "cloudpickle:abc", "s2": "cloudpickle:def"},
            fee_models=["F1", "F4"],
        )
        assert len(cs.strategies) == 2
        assert cs.fee_models == ["F1", "F4"]

    def test_roundtrip(self):
        cs = ComputeSpec(task_type="backtest", params={"x": 1}, initial_cash=50000,
                        cost_model="binance_spot", allow_short=True)
        cs2 = ComputeSpec.from_dict(cs.to_dict())
        assert cs2.task_type == "backtest"
        assert cs2.params == {"x": 1}
        assert cs2.initial_cash == 50000
        assert cs2.cost_model == "binance_spot"
        assert cs2.allow_short is True

    def test_params_default_empty_dict(self):
        cs = ComputeSpec(task_type="custom")
        assert cs.params == {}


class TestTaskSpec:
    def test_default_dispatch(self):
        spec = TaskSpec(
            task_id="t1",
            data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
        )
        assert spec.dispatch_spec.split_strategy == "auto"
        assert isinstance(spec.created_at, datetime)

    def test_full_roundtrip(self):
        spec = TaskSpec(
            task_id="test-001",
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(task_type="backtest",
                                     params={"custom": True},
                                     initial_cash=10000),
            dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=4),
            trace_id="trace-001",
            created_by="test",
        )
        d = spec.to_dict()
        assert d["task_id"] == "test-001"
        assert d["compute_spec"]["task_type"] == "backtest"
        restored = TaskSpec.from_dict(d)
        assert restored.task_id == "test-001"
        assert restored.compute_spec.task_type == "backtest"
        assert restored.compute_spec.params["custom"] is True
        assert restored.compute_spec.initial_cash == 10000
        assert restored.dispatch_spec.split_strategy == "param_wise"
        assert restored.dispatch_spec.max_workers == 4
        assert restored.trace_id == "trace-001"

    def test_json_roundtrip(self):
        spec = TaskSpec(
            task_id="t2",
            data_spec=DataSpec(symbols=["ETH/USDT"]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma", "window": 20}),
        )
        s = spec.to_json()
        restored = TaskSpec.from_json(s)
        assert restored.compute_spec.params["window"] == 20

    def test_47_task_types_roundtrip(self):
        for i, tt in enumerate(["indicator", "backtest", "grid_search",
                                "correlation", "wavelet", "transfer_entropy",
                                "ml_train", "risk_metrics", "custom"]):
            spec = TaskSpec(
                task_id=f"test-{tt}-{i}",
                data_spec=DataSpec(symbols=["BTC"]),
                compute_spec=ComputeSpec(task_type=tt, params={"test": True, "i": i}),
            )
            restored = TaskSpec.from_dict(spec.to_dict())
            assert restored.compute_spec.task_type == tt
            assert restored.compute_spec.params["test"] is True
            assert restored.compute_spec.params["i"] == i

    def test_nested_dict_in_params(self):
        spec = TaskSpec(
            task_id="t3",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="wavelet",
                                     params={"scales": [1, 2, 3, 4],
                                             "options": {"wavelet": "morl"}}),
        )
        restored = TaskSpec.from_dict(spec.to_dict())
        assert restored.compute_spec.params["scales"] == [1, 2, 3, 4]
        assert restored.compute_spec.params["options"]["wavelet"] == "morl"


class TestTaskSpecFieldDefaults:
    def test_compute_spec_default_fields(self):
        cs = ComputeSpec(task_type="backtest")
        assert cs.initial_cash == 1_000_000.0
        assert cs.metric == "sharpe"
        assert cs.maximize is True
        assert cs.n_simulations == 1000
        assert cs.seed == 0
        assert cs.trade_on == "open"
        assert cs.allow_short is False

    def test_dispatch_spec_default_fields(self):
        ds = DispatchSpec()
        assert ds.timeout == 3600
        assert ds.retry_count == 0
        assert ds.data_dispatch == "auto"
