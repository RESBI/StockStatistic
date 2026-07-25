"""BT-10: P2 backtest analysis tools — periods_per_year, DCA, Analyzer, fee_sweep."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import (
    BacktestEngine, strategy, Order, ZeroCost, PercentCost,
    dca_equity, buy_and_hold, BacktestAnalyzer,
    fee_sweep, maker_taker_sweep,
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
# Test periods_per_year parameter
# ═══════════════════════════════════════════════

class TestPeriodsPerYear:
    def test_explicit_periods(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross,
                             periods_per_year=52, cost_model=ZeroCost())
        res = eng.run()
        m = res.metrics()
        assert m["sharpe"] is not None

    def test_auto_inferred(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross,
                             cost_model=ZeroCost())
        res = eng.run()
        m = res.metrics()
        assert m["sharpe"] is not None


# ═══════════════════════════════════════════════
# Test DCA benchmark
# ═══════════════════════════════════════════════

class TestDCA:
    def test_dca_returns_equity(self, data):
        eq = dca_equity(100000, data.close)
        assert len(eq) == len(data)
        assert eq.iloc[-1] > 0

    def test_dca_weekly(self, data):
        eq = dca_equity(100000, data.close, schedule="weekly")
        assert len(eq) == len(data)

    def test_dca_differs_from_buyhold(self, data):
        eq_dca = dca_equity(100000, data.close)
        eq_bh = buy_and_hold(100000, data.close)
        assert eq_dca.iloc[-1] != eq_bh.iloc[-1]


# ═══════════════════════════════════════════════
# Test BacktestAnalyzer
# ═══════════════════════════════════════════════

class TestBacktestAnalyzer:
    def test_subperiod_metrics(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross, cost_model=ZeroCost())
        res = eng.run()
        split = pd.Timestamp("2024-06-01")
        if split.tzinfo is None and res.equity.index.tz is not None:
            split = split.tz_localize("UTC")
        sub = BacktestAnalyzer.subperiod_metrics(res, [split])
        assert len(sub) == 2

    def test_rolling_sharpe(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross, cost_model=ZeroCost())
        res = eng.run()
        rolling = BacktestAnalyzer.rolling_metric(res, metric="sharpe", window=30)
        assert len(rolling) > 0

    def test_rolling_volatility(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross, cost_model=ZeroCost())
        res = eng.run()
        rolling = BacktestAnalyzer.rolling_metric(res, metric="volatility", window=30)
        assert len(rolling) > 0

    def test_trade_analysis_by_exit(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross, cost_model=ZeroCost())
        res = eng.run()
        df = BacktestAnalyzer.trade_analysis_by_exit(res)
        assert isinstance(df, pd.DataFrame)


# ═══════════════════════════════════════════════
# Test fee_sweep
# ═══════════════════════════════════════════════

class TestFeeSweep:
    def test_fee_sweep_returns_df(self, data):
        df = fee_sweep({"TEST": {"1d": data}}, ma_cross,
                       fee_rates=[0.0, 0.001, 0.01], initial_cash=100000)
        assert len(df) == 3
        assert "sharpe" in df.columns
        assert df.loc[0.0, "total_return"] >= df.loc[0.01, "total_return"]

    def test_maker_taker_sweep(self, data):
        df = maker_taker_sweep({"TEST": {"1d": data}}, ma_cross,
                               maker_rates=[0.0, 0.001],
                               taker_rates=[0.0, 0.001],
                               initial_cash=100000)
        assert len(df) == 4
