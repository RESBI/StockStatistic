"""BT-6: Parameter optimization, walk-forward, and Monte Carlo tests."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost
from stockstat.backtest.optimizer import grid_search
from stockstat.backtest.walkforward import walk_forward
from stockstat.backtest.montecarlo import bootstrap_returns, monte_carlo_equity, shuffle_orders
from stockstat.backtest.orders import Fill, OrderSide


def make_data(n=200, seed=0):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1e6,
    }, index=dates)


def make_engine(params):
    short = params["short"]
    long = params["long"]

    @strategy
    def ma(ctx):
        d = ctx.get("X", "1d", lookback=long + 5)
        if len(d) < long + 1:
            return
        ma_s = d.close.rolling(short).mean().iloc[-1]
        ma_l = d.close.rolling(long).mean().iloc[-1]
        pos = ctx.portfolio.get_position("X")
        if ma_s > ma_l and pos.qty == 0:
            ctx.broker.submit(Order("X", "buy", 10))
        elif ma_s < ma_l and pos.qty > 0:
            ctx.broker.submit(Order("X", "sell", pos.qty))

    df = make_data(150)
    return BacktestEngine(data={"X": {"1d": df}}, strategy=ma,
                          initial_cash=100000, cost_model=ZeroCost())


class TestGridSearch:
    def test_grid_search_returns_sorted(self):
        results = grid_search(make_engine, {"short": [3, 5], "long": [10, 20]},
                              metric="sharpe")
        assert len(results) == 4
        # sorted descending by sharpe
        vals = [v for _, v, _ in results]
        assert vals == sorted(vals, reverse=True)

    def test_grid_search_best_is_first(self):
        results = grid_search(make_engine, {"short": [5], "long": [20]},
                              metric="total_return")
        params, val, res = results[0]
        assert params == {"short": 5, "long": 20}
        assert val == pytest.approx(res.metrics()["total_return"])

    def test_grid_search_all_combinations(self):
        results = grid_search(make_engine, {"short": [3, 5, 8], "long": [10, 20]})
        assert len(results) == 6


class TestWalkForward:
    def test_walk_forward_produces_segments(self):
        df = make_data(200)
        index = df.index

        def make_eng(start, end):
            sub = df.loc[start:end]
            @strategy
            def ma(ctx):
                d = ctx.get("X", "1d", lookback=25)
                if len(d) < 21:
                    return
                ma_s = d.close.rolling(5).mean().iloc[-1]
                ma_l = d.close.rolling(20).mean().iloc[-1]
                pos = ctx.portfolio.get_position("X")
                if ma_s > ma_l and pos.qty == 0:
                    ctx.broker.submit(Order("X", "buy", 5))
                elif ma_s < ma_l and pos.qty > 0:
                    ctx.broker.submit(Order("X", "sell", pos.qty))
            return BacktestEngine(data={"X": {"1d": sub}}, strategy=ma,
                                  initial_cash=100000, cost_model=ZeroCost())

        segments = walk_forward(make_eng, index, train_size=100, test_size=50, step=50)
        assert len(segments) >= 1
        for start, end, res in segments:
            assert start < end
            assert len(res.equity) > 0


class TestMonteCarlo:
    def test_bootstrap_returns_length(self):
        rets = pd.Series(np.random.RandomState(0).normal(0.001, 0.02, 100))
        samples = bootstrap_returns(rets, n_samples=10, seed=0)
        assert len(samples) == 10
        assert all(len(s) == 100 for s in samples)

    def test_monte_carlo_equity_dataframe(self):
        rets = pd.Series(np.random.RandomState(0).normal(0.001, 0.02, 100))
        curves = monte_carlo_equity(rets, initial=100000, n_samples=5, seed=0)
        assert curves.shape[1] == 5
        assert curves.shape[0] == 100
        # all positive (compounding from initial capital)
        assert (curves > 0).all().all()
        # mean of first values near initial * (1 + ~0)
        assert curves.iloc[0].mean() == pytest.approx(100000, rel=0.05)

    def test_shuffle_orders_preserves_count(self):
        fills = [
            Fill("o1", "X", OrderSide.BUY, 10, 100, ts=pd.Timestamp("2024-01-01")),
            Fill("o2", "X", OrderSide.SELL, 10, 105, ts=pd.Timestamp("2024-01-02")),
        ]
        shuffled = shuffle_orders(fills, seed=0)
        assert len(shuffled) == 2
        assert {f.ts for f in shuffled} == {pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")}


class TestOptunaOptional:
    def test_optuna_import_error_message(self):
        from stockstat.backtest.optimizer import optuna_search
        try:
            import optuna  # noqa
            pytest.skip("optuna installed; skip import-error test")
        except ImportError:
            with pytest.raises(ImportError, match="optuna"):
                optuna_search(lambda p: make_engine(p), lambda t: {}, n_trials=1)
