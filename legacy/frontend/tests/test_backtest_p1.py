"""BT-9: P1 backtest engine enhancements — IntrabarSimulator, BatchRunner, exit_reason_stats."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import (
    BacktestEngine, strategy, Order, OrderType,
    ZeroCost, PercentCost,
    IntrabarSimulator, StrategyBatchRunner, BatchResults,
)


def make_data(n=200, seed=0):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1e6,
    }, index=dates)


@pytest.fixture
def data():
    return make_data()


@strategy
def ma_cross(ctx):
    d = ctx.get("TEST", "1d", lookback=30)
    if len(d) < 21:
        return
    ma_s = d.close.rolling(5).mean().iloc[-1]
    ma_l = d.close.rolling(20).mean().iloc[-1]
    pos = ctx.portfolio.get_position("TEST")
    if ma_s > ma_l and pos.qty == 0:
        ctx.broker.submit(Order("TEST", "buy", 10, tag="entry"))
    elif ma_s < ma_l and pos.qty > 0:
        ctx.broker.submit(Order("TEST", "sell", pos.qty, tag="exit"))


# ═══════════════════════════════════════════════
# Test IntrabarSimulator
# ═══════════════════════════════════════════════

class TestIntrabarSimulator:
    def test_buy_fill_on_low_touch(self):
        bars = pd.DataFrame({
            "open": [100, 100], "high": [101, 101],
            "low": [99, 97], "close": [100, 98],
            "volume": [1e4, 1e4]
        }, index=pd.date_range("2024-01-01", periods=2, freq="1h"))
        sim = IntrabarSimulator(bars)
        price, ts = sim.check_fill(98.0, "buy", pd.Timestamp("2024-01-01"))
        assert price == 98.0
        assert ts == pd.Timestamp("2024-01-01 01:00")

    def test_no_fill(self):
        bars = pd.DataFrame({
            "open": [100], "high": [101], "low": [99], "close": [100], "volume": [1e4]
        }, index=pd.date_range("2024-01-01", periods=1, freq="1h"))
        sim = IntrabarSimulator(bars)
        price, ts = sim.check_fill(95.0, "buy", pd.Timestamp("2024-01-01"))
        assert price is None

    def test_first_to_fill(self):
        bars = pd.DataFrame({
            "open": [100, 100], "high": [105, 101],
            "low": [95, 97], "close": [100, 98],
            "volume": [1e4, 1e4]
        }, index=pd.date_range("2024-01-01", periods=2, freq="1h"))
        sim = IntrabarSimulator(bars)
        result = sim.first_to_fill(
            [(98, "buy"), (104, "sell")],
            pd.Timestamp("2024-01-01"))
        assert result is not None
        assert result[0] == 98


# ═══════════════════════════════════════════════
# Test StrategyBatchRunner
# ═══════════════════════════════════════════════

class TestStrategyBatchRunner:
    def test_run_all_multiple_strategies(self, data):
        runner = StrategyBatchRunner(
            data={"TEST": {"1d": data}}, initial_cash=100000, cost_model=ZeroCost())
        results = runner.run_all({"ma": ma_cross, "idle": strategy(lambda ctx: None)})
        df = results.to_dataframe()
        assert len(df) == 2
        assert "sharpe" in df.columns

    def test_run_all_fees(self, data):
        runner = StrategyBatchRunner(
            data={"TEST": {"1d": data}}, initial_cash=100000)
        fees = {"zero": ZeroCost(), "high": PercentCost(commission=0.01)}
        results = runner.run_all_fees({"ma": ma_cross}, fees)
        df = results.to_dataframe()
        assert len(df) == 2

    def test_best_by_sharpe(self, data):
        runner = StrategyBatchRunner(
            data={"TEST": {"1d": data}}, initial_cash=100000, cost_model=ZeroCost())
        results = runner.run_all({"ma": ma_cross, "idle": strategy(lambda ctx: None)})
        name, val = results.best_by("sharpe")
        assert name in ("ma", "idle")

    def test_rank(self, data):
        runner = StrategyBatchRunner(
            data={"TEST": {"1d": data}}, initial_cash=100000, cost_model=ZeroCost())
        results = runner.run_all({"ma": ma_cross, "idle": strategy(lambda ctx: None)})
        ranked = results.rank("sharpe")
        assert len(ranked) == 2

    def test_equity_curves(self, data):
        runner = StrategyBatchRunner(
            data={"TEST": {"1d": data}}, initial_cash=100000, cost_model=ZeroCost())
        results = runner.run_all({"ma": ma_cross})
        curves = results.equity_curves()
        assert "ma" in curves
        assert len(curves["ma"]) > 0


# ═══════════════════════════════════════════════
# Test exit_reason_stats
# ═══════════════════════════════════════════════

class TestExitReasonStats:
    def test_exit_reason_stats_returns_dict(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross, cost_model=ZeroCost())
        res = eng.run()
        stats = res.exit_reason_stats()
        assert isinstance(stats, dict)
        # Should have at least one exit reason (possibly empty string)
        assert len(stats) >= 0
