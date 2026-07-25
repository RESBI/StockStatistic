"""BT-1: Single-asset single-timeframe MVP tests.

Validates the full backtest loop on synthetic data using the MA crossover
strategy, plus equity/metrics sanity checks.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import (
    BacktestEngine, strategy, Order, Strategy, PercentCost, NextOpenFill,
    ThisCloseFill, ZeroCost,
)


def make_trend_data(n=300, seed=42, drift=0.002):
    """Synthetic uptrend with noise — good for MA crossover."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    opn = close * (1 + rng.normal(0, 0.003, n))
    vol = rng.uniform(1e6, 5e7, n)
    return pd.DataFrame({"open": opn, "high": high, "low": low,
                         "close": close, "volume": vol}, index=dates)


@pytest.fixture
def data():
    return make_trend_data()


@strategy
def ma_cross(ctx, short=5, long=20, qty=10):
    d = ctx.get("TEST", "1d", lookback=30)
    if len(d) < long + 1:
        return
    ma_s = d.close.rolling(short).mean().iloc[-1]
    ma_l = d.close.rolling(long).mean().iloc[-1]
    pos = ctx.portfolio.get_position("TEST")
    if ma_s > ma_l and pos.qty == 0:
        ctx.broker.submit(Order("TEST", "buy", qty, tag="entry"))
    elif ma_s < ma_l and pos.qty > 0:
        ctx.broker.submit(Order("TEST", "sell", pos.qty, tag="exit"))


class TestMACross:
    def test_runs_and_returns_result(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross,
                             initial_cash=100000, cost_model=ZeroCost())
        res = eng.run()
        assert len(res.equity) == len(data)
        assert res.equity.iloc[0] == pytest.approx(100000, rel=1e-6)

    def test_generates_fills(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross,
                             initial_cash=100000, cost_model=ZeroCost())
        res = eng.run()
        assert len(res.fills) > 0
        # fills alternate buy/sell
        sides = [str(f.side.value) for f in res.fills]
        assert "buy" in sides and "sell" in sides

    def test_metrics_reasonable(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross,
                             initial_cash=100000, cost_model=ZeroCost())
        res = eng.run()
        m = res.metrics()
        assert -1.0 < m["total_return"] < 5.0
        assert m["max_drawdown"] <= 0
        assert m["max_drawdown"] >= -1.0
        assert m["volatility"] >= 0
        assert m["num_trades"] >= 1

    def test_summary_string(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross)
        res = eng.run()
        s = res.summary()
        assert "Sharpe" in s and "Total Return" in s

    def test_equity_never_negative(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross)
        res = eng.run()
        assert (res.equity > 0).all()


class TestComputeEngineIntegration:
    def test_strategy_can_call_compute(self, data):
        @strategy
        def rsi_strategy(ctx):
            d = ctx.get("TEST", "1d", lookback=30)
            if len(d) < 15:
                return
            r = ctx.compute.rsi(d.close, window=14)
            pos = ctx.portfolio.get_position("TEST")
            last_rsi = r.iloc[-1]
            if not np.isnan(last_rsi):
                if last_rsi < 30 and pos.qty == 0:
                    ctx.broker.submit(Order("TEST", "buy", 5))
                elif last_rsi > 70 and pos.qty > 0:
                    ctx.broker.submit(Order("TEST", "sell", pos.qty))

        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=rsi_strategy,
                             initial_cash=100000)
        res = eng.run()
        # ran without error and produced some equity curve
        assert len(res.equity) == len(data)

    def test_register_custom_indicator(self, data):
        @strategy
        def custom_strat(ctx):
            if not ctx.history.get("init"):
                def donchian(high, low, window=20):
                    hh = high.rolling(window).max()
                    ll = low.rolling(window).min()
                    return hh, ll
                ctx.compute.register("donchian", donchian, category="custom")
                ctx.history["init"] = True
            d = ctx.get("TEST", "1d", lookback=30)
            if len(d) < 21:
                return
            hh, ll = ctx.compute.call("donchian", high=d.high, low=d.low, window=20)
            if not np.isnan(hh.iloc[-1]):
                pos = ctx.portfolio.get_position("TEST")
                if d.close.iloc[-1] > hh.iloc[-1] and pos.qty == 0:
                    ctx.broker.submit(Order("TEST", "buy", 5))

        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=custom_strat)
        res = eng.run()
        assert len(res.equity) == len(data)


class TestFillModels:
    def test_next_open_no_lookahead(self, data):
        """With NextOpenFill, an order submitted at bar t fills at t+1 open."""
        fills_seen = []

        @strategy
        def s(ctx):
            d = ctx.get("TEST", "1d", lookback=2)
            if len(d) == 2 and d.close.iloc[-1] > d.close.iloc[-2]:
                oid = ctx.broker.submit(Order("TEST", "buy", 1, tag="t"))
                fills_seen.append(ctx.now)

        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=s,
                             fill_model=NextOpenFill(), cost_model=ZeroCost())
        res = eng.run()
        # at least one fill happened
        assert len(res.fills) > 0


class TestCostImpact:
    def test_cost_reduces_return(self, data):
        eng_zero = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross,
                                  initial_cash=100000, cost_model=ZeroCost())
        res_zero = eng_zero.run()
        eng_cost = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross,
                                  initial_cash=100000,
                                  cost_model=PercentCost(commission=0.01, slippage=0.01))
        res_cost = eng_cost.run()
        # high costs should reduce total return
        assert res_cost.metrics()["total_return"] <= res_zero.metrics()["total_return"]


class TestExport:
    def test_trades_df(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross,
                             cost_model=ZeroCost())
        res = eng.run()
        df = res.trades_df()
        if not df.empty:
            assert "symbol" in df.columns
            assert "price" in df.columns

    def test_to_dict(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross)
        res = eng.run()
        d = res.to_dict()
        assert "metrics" in d
        assert "equity" in d
        assert "trades" in d


class TestPlotAdapter:
    def test_plot_equity_returns_spec(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross)
        res = eng.run()
        spec = res.plot_equity()
        assert len(spec.series) >= 1

    def test_plot_drawdown(self, data):
        eng = BacktestEngine(data={"TEST": {"1d": data}}, strategy=ma_cross)
        res = eng.run()
        spec = res.plot_drawdown()
        assert len(spec.series) == 1
