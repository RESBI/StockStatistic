"""BT-5: Performance metrics, reporting, and visualization tests.

Validates Sharpe/Sortino/Calmar/drawdown/win-rate/profit-factor, benchmark
comparison, summary string, exports, and PlotSpec generation.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import (
    BacktestEngine, strategy, Order, Strategy, PercentCost, ZeroCost, BacktestResult,
    buy_and_hold,
)
from stockstat.backtest import metrics as M


def make_data(n=300, seed=0, drift=0.002):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1e6,
    }, index=dates)


@pytest.fixture
def data():
    return make_data()


@strategy
def ma_cross(ctx, short=5, long=20, qty=10):
    d = ctx.get("X", "1d", lookback=30)
    if len(d) < long + 1:
        return
    ma_s = d.close.rolling(short).mean().iloc[-1]
    ma_l = d.close.rolling(long).mean().iloc[-1]
    pos = ctx.portfolio.get_position("X")
    if ma_s > ma_l and pos.qty == 0:
        ctx.broker.submit(Order("X", "buy", qty, tag="entry"))
    elif ma_s < ma_l and pos.qty > 0:
        ctx.broker.submit(Order("X", "sell", pos.qty, tag="exit"))


class TestMetricsFunctions:
    def test_total_return(self):
        eq = pd.Series([100, 110, 105])
        assert M.total_return(eq) == pytest.approx(0.05)

    def test_max_drawdown(self):
        eq = pd.Series([100, 120, 90, 100])
        # peak 120, trough 90 → dd = -25%
        assert M.max_drawdown(eq) == pytest.approx(-0.25)

    def test_drawdown_series(self):
        eq = pd.Series([100, 120, 90])
        dd = M.drawdown_series(eq)
        assert dd.iloc[0] == 0
        assert dd.iloc[2] == pytest.approx(-0.25)

    def test_sharpe_zero_volatility(self):
        eq = pd.Series([100, 100, 100])
        assert M.sharpe_ratio(eq) == 0.0

    def test_omega_ratio(self):
        rets = pd.Series([0.1, -0.05, 0.2, -0.1])
        om = M.omega_ratio(rets)
        assert om > 0

    def test_information_ratio(self):
        rets = pd.Series([0.01, 0.02, 0.0, -0.01])
        bench = pd.Series([0.0, 0.0, 0.0, 0.0])
        ir = M.information_ratio(rets, bench)
        assert ir > 0

    def test_trade_stats(self):
        history = [("t1", "X", 100), ("t2", "X", -50), ("t3", "X", 30)]
        ts = M.trade_stats(realized_history=history, fills=[])
        assert ts["num_trades"] == 3
        assert ts["win_rate"] == pytest.approx(2 / 3)
        assert ts["profit_factor"] == pytest.approx(130 / 50)
        assert ts["max_win_streak"] == 1


class TestResultMetrics:
    def test_full_metrics(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross).run()
        m = res.metrics()
        for key in ["total_return", "annualized_return", "sharpe", "sortino",
                    "max_drawdown", "calmar", "volatility", "num_trades",
                    "win_rate", "profit_factor"]:
            assert key in m

    def test_summary(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross).run()
        s = res.summary()
        assert "Sharpe" in s
        assert "Win Rate" in s

    def test_returns_series(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross).run()
        r = res.returns
        assert len(r) == len(res.equity) - 1

    def test_drawdown_property(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross).run()
        dd = res.drawdown
        assert (dd <= 0).all()


class TestBenchmark:
    def test_benchmark_comparison(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross,
                             benchmark="X").run()
        assert res.benchmark is not None
        m = res.metrics()
        assert "information_ratio" in m

    def test_buy_and_hold_helper(self, data):
        bh = buy_and_hold(100000, data.close)
        assert bh.iloc[0] == pytest.approx(100000)
        assert bh.iloc[-1] == pytest.approx(100000 * data.close.iloc[-1] / data.close.iloc[0])


class TestExports:
    def test_to_dict(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross).run()
        d = res.to_dict()
        assert "metrics" in d
        assert "equity" in d
        assert isinstance(d["trades"], list)

    def test_to_csv(self, data, tmp_path):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross).run()
        path = str(tmp_path / "trades.csv")
        res.to_csv(path)
        assert os.path.exists(path)


class TestPlotSpec:
    def test_plot_equity_with_benchmark(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross,
                             benchmark="X").run()
        spec = res.plot_equity()
        assert len(spec.series) == 2  # strategy + benchmark
        assert spec.title == "Equity Curve"

    def test_plot_drawdown_spec(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross).run()
        spec = res.plot_drawdown()
        assert spec.series[0].color == "red"

    def test_plot_trades_spec(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross,
                             cost_model=ZeroCost()).run()
        spec = res.plot_trades()
        assert len(spec.series) >= 1  # at least equity

    def test_render_with_matplotlib_optional(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross).run()
        from stockstat.plot.base import get_renderer
        r = get_renderer("matplotlib")
        if not r.available():
            pytest.skip("matplotlib not available")
        spec = res.plot_equity()
        fig = r.render(spec)
        assert fig is not None


class TestConfigReproducibility:
    def test_config_recorded(self, data):
        res = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross,
                             initial_cash=50000, seed=123).run()
        assert res.config["initial_cash"] == 50000
        assert res.config["seed"] == 123
        assert res.config["symbols"] == ["X"]

    def test_seed_reproducible(self, data):
        r1 = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross, seed=42).run()
        r2 = BacktestEngine(data={"X": {"1d": data}}, strategy=ma_cross, seed=42).run()
        # deterministic strategy → same equity
        assert (r1.equity == r2.equity).all()
