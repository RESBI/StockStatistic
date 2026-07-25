"""test_handlers.py — Tier 1 handler 测试 (40 项)。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec, DispatchSpec, cloudpickle_dumps
from stockstat_compute.handlers import dispatch, HANDLERS, list_task_types
from stockstat_compute.handlers._base import register
from stockstat_foundation.errors import WorkerCapabilityError


@pytest.fixture
def ohlcv_df():
    rng = np.random.default_rng(42)
    n = 100
    returns = rng.normal(0.001, 0.02, n)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    volume = rng.integers(1000, 100000, n).astype(float)
    ts = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "timestamp": ts, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


def buy_hold(i, bar, data, ctx):
    if i == 0:
        from stockstat_compute import Signal
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy", strength=1.0)
    return None


class TestHandlerRegistry:
    def test_tier1_handlers_registered(self):
        types = set(list_task_types())
        assert {"indicator", "backtest", "grid_search",
                "batch_backtest", "monte_carlo", "walkforward"}.issubset(types)

    def test_register_custom_handler(self):
        @register("test_custom_handler")
        def handler(spec, data, on_progress=None):
            return {"custom": True}
        assert "test_custom_handler" in HANDLERS
        spec = TaskSpec(
            task_id="t1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="test_custom_handler"),
        )
        result = dispatch(spec, None)
        assert result == {"custom": True}
        # 清理
        HANDLERS.pop("test_custom_handler", None)

    def test_unknown_task_type_raises(self):
        spec = TaskSpec(
            task_id="t1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="nonexistent_task"),
        )
        with pytest.raises(WorkerCapabilityError):
            dispatch(spec, None)


class TestIndicatorHandler:
    def test_ma(self, ohlcv_df):
        spec = TaskSpec(
            task_id="t1",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "ma", "window": 10},
            ),
        )
        result = dispatch(spec, ohlcv_df["close"])
        assert len(result) == len(ohlcv_df)

    def test_rsi(self, ohlcv_df):
        spec = TaskSpec(
            task_id="t2",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "rsi", "window": 14},
            ),
        )
        result = dispatch(spec, ohlcv_df["close"])
        assert len(result) == len(ohlcv_df)

    def test_bollinger(self, ohlcv_df):
        spec = TaskSpec(
            task_id="t3",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"indicator_name": "bollinger", "window": 20, "std": 2.0},
            ),
        )
        result = dispatch(spec, ohlcv_df["close"])
        assert "upper" in result.columns

    def test_missing_indicator_name_raises(self, ohlcv_df):
        spec = TaskSpec(
            task_id="t4",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="indicator", params={}),
        )
        with pytest.raises(ValueError):
            dispatch(spec, ohlcv_df["close"])


class TestBacktestHandler:
    def test_basic_backtest(self, ohlcv_df):
        strat_ref = f"cloudpickle:{cloudpickle_dumps(buy_hold)}"
        spec = TaskSpec(
            task_id="bt1",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=strat_ref,
                initial_cash=10000,
            ),
        )
        result = dispatch(spec, ohlcv_df)
        assert result.error is None
        assert result.metrics.n_trades >= 1
        assert result.final_equity > 0

    def test_backtest_with_cost_model(self, ohlcv_df):
        strat_ref = f"cloudpickle:{cloudpickle_dumps(buy_hold)}"
        spec = TaskSpec(
            task_id="bt2",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=strat_ref,
                initial_cash=10000,
                cost_model="F4_FutBNB",
            ),
        )
        result = dispatch(spec, ohlcv_df)
        assert result.error is None


class TestGridSearchHandler:
    def test_grid_search(self, ohlcv_df):
        # 包装策略为接受参数的类
        from stockstat_compute import StrategyBase
        class MaCross(StrategyBase):
            name = "ma_cross"
            def __init__(self, short=5, long=20):
                self.short = short
                self.long = long
            def on_bar(self, i, bar, data, ctx):
                if i < self.long:
                    return None
                s = data["close"].iloc[i - self.short:i + 1].mean()
                l = data["close"].iloc[i - self.long:i + 1].mean()
                ps = data["close"].iloc[i - self.short - 1:i].mean()
                pl = data["close"].iloc[i - self.long - 1:i].mean()
                from stockstat_compute import Signal
                if ps <= pl and s > l:
                    return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
                if ps >= pl and s < l:
                    return Signal(timestamp=bar["timestamp"], symbol="TEST", side="sell")
                return None
        strat_ref = f"cloudpickle:{cloudpickle_dumps(MaCross)}"
        spec = TaskSpec(
            task_id="gs1",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="grid_search",
                strategy_ref=strat_ref,
                param_grid={"short": [3, 5], "long": [10, 20]},
                metric="sharpe",
                initial_cash=10000,
            ),
        )
        result = dispatch(spec, ohlcv_df)
        assert len(result) == 4  # 2 × 2
        assert "short" in result.columns


class TestBatchBacktestHandler:
    def test_batch(self, ohlcv_df):
        strategies = {
            "buy_hold": f"cloudpickle:{cloudpickle_dumps(buy_hold)}",
        }
        spec = TaskSpec(
            task_id="bb1",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="batch_backtest",
                strategies=strategies,
                fee_models=["F1_SpotNoBNB", "F4_FutBNB"],
                initial_cash=10000,
            ),
        )
        result = dispatch(spec, ohlcv_df)
        assert len(result) == 2  # 1 strategy × 2 fees

    def test_paxg_132(self, ohlcv_df):
        # 模拟 PAXG v5-redo: 33 × 4 = 132
        strategies = {f"S{i}": f"cloudpickle:{cloudpickle_dumps(buy_hold)}" for i in range(33)}
        spec = TaskSpec(
            task_id="paxg_redo",
            data_spec=DataSpec(symbols=["PAXG/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="batch_backtest",
                strategies=strategies,
                fee_models=["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"],
                initial_cash=10000,
            ),
        )
        result = dispatch(spec, ohlcv_df)
        assert len(result) == 132


class TestMonteCarloHandler:
    def test_run(self, ohlcv_df):
        strat_ref = f"cloudpickle:{cloudpickle_dumps(buy_hold)}"
        spec = TaskSpec(
            task_id="mc1",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="monte_carlo",
                strategy_ref=strat_ref,
                initial_cash=10000,
                n_simulations=10,
                seed=42,
            ),
        )
        result = dispatch(spec, ohlcv_df)
        assert len(result) == 10


class TestWalkforwardHandler:
    def test_run(self, ohlcv_df):
        strat_ref = f"cloudpickle:{cloudpickle_dumps(buy_hold)}"
        spec = TaskSpec(
            task_id="wf1",
            data_spec=DataSpec(symbols=["TEST"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="walkforward",
                strategy_ref=strat_ref,
                initial_cash=10000,
                params={"train_window": 30, "test_window": 20, "step": 20},
            ),
        )
        result = dispatch(spec, ohlcv_df)
        assert len(result) > 0


class TestProgressCallback:
    def test_progress_called(self, ohlcv_df):
        strategies = {
            "s1": f"cloudpickle:{cloudpickle_dumps(buy_hold)}",
        }
        spec = TaskSpec(
            task_id="p1",
            data_spec=DataSpec(symbols=["TEST"]),
            compute_spec=ComputeSpec(
                task_type="batch_backtest",
                strategies=strategies,
                fee_models=["F1_SpotNoBNB", "F4_FutBNB"],
                initial_cash=10000,
            ),
        )
        calls = []
        def on_progress(completed, total):
            calls.append((completed, total))
        dispatch(spec, ohlcv_df, on_progress=on_progress)
        assert len(calls) >= 2
        assert calls[-1] == (2, 2)
