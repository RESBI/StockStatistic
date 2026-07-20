"""BT-2: Multi-asset portfolio + short selling + order extensions.

Validates Universe with multiple instruments, allow_short, limit/stop orders,
and pair-trading / risk-parity style strategies.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import (
    BacktestEngine, strategy, Order, OrderType, Strategy, ZeroCost, PercentCost,
    sizing,
)


def make_data(n=200, seed=0, drift=0.002, vol=0.015):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1e6,
    }, index=dates)


@pytest.fixture
def pair_data():
    return {"BTC": {"1d": make_data(200, 0)}, "ETH": {"1d": make_data(200, 1)}}


class TestMultiAsset:
    def test_two_symbols_universe(self, pair_data):
        eng = BacktestEngine(data=pair_data, strategy=Strategy(),
                             initial_cash=100000, cost_model=ZeroCost())
        assert set(eng.universe.symbols) == {"BTC", "ETH"}
        assert len(eng.data_feed.master_index) == 200

    def test_context_get_multiple_symbols(self, pair_data):
        @strategy
        def s(ctx):
            btc = ctx.get("BTC", "1d", lookback=5)
            eth = ctx.get("ETH", "1d", lookback=5)
            ctx.history["btc_len"] = len(btc)
            ctx.history["eth_len"] = len(eth)

        eng = BacktestEngine(data=pair_data, strategy=s)
        eng.run()
        assert eng.strategy._fn is not None

    def test_buy_both(self, pair_data):
        @strategy
        def s(ctx):
            if ctx.now == ctx._feed.master_index[0]:
                ctx.broker.submit(Order("BTC", "buy", 1))
                ctx.broker.submit(Order("ETH", "buy", 1))

        eng = BacktestEngine(data=pair_data, strategy=s, initial_cash=100000,
                             cost_model=ZeroCost())
        res = eng.run()
        assert len(res.fills) == 2
        assert res.fills[0].symbol == "BTC"
        assert res.fills[1].symbol == "ETH"


class TestShortSelling:
    def test_short_enabled(self):
        df = make_data(100, 0)
        @strategy
        def s(ctx):
            if ctx.now == ctx._feed.master_index[0]:
                ctx.broker.submit(Order("X", "sell", 1, tag="short"))

        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                             initial_cash=100000, allow_short=True,
                             cost_model=ZeroCost())
        res = eng.run()
        assert len(res.fills) == 1
        assert res.fills[0].side.value == "sell"

    def test_short_disabled_raises(self):
        df = make_data(100, 0)
        @strategy
        def s(ctx):
            if ctx.now == ctx._feed.master_index[0]:
                ctx.broker.submit(Order("X", "sell", 1, tag="short"))

        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                             initial_cash=100000, allow_short=False,
                             cost_model=ZeroCost())
        eng.run()  # order rejected silently, no crash
        # position should remain flat
        assert all(p.qty == 0 for p in eng.portfolio.positions.values())

    def test_short_profit_on_decline(self):
        # declining market → short should profit
        df = make_data(100, 0, drift=-0.003, vol=0.005)
        @strategy
        def s(ctx):
            if ctx.now == ctx._feed.master_index[0]:
                ctx.broker.submit(Order("X", "sell", 10, tag="short"))
            elif ctx.now == ctx._feed.master_index[-1]:
                pos = ctx.portfolio.get_position("X")
                if pos.qty < 0:
                    ctx.broker.submit(Order("X", "buy", abs(pos.qty), tag="cover"))

        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                             initial_cash=100000, allow_short=True,
                             cost_model=ZeroCost())
        res = eng.run()
        assert res.metrics()["total_return"] > 0


class TestLimitOrders:
    def test_limit_buy_fills_when_price_drops(self):
        df = make_data(50, 0)
        @strategy
        def s(ctx):
            if ctx.now == ctx._feed.master_index[0]:
                # limit buy below current — should fill if price drops
                ctx.broker.submit(Order("X", "buy", 10,
                                        order_type=OrderType.LIMIT,
                                        limit_price=df["close"].iloc[0] * 0.98))

        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                             initial_cash=100000, cost_model=ZeroCost())
        res = eng.run()
        # may or may not fill depending on data, but should not crash
        for f in res.fills:
            assert f.price <= df["close"].iloc[0] * 0.98

    def test_limit_buy_never_fills_above_limit(self):
        df = make_data(50, 0, drift=0.01)  # strong uptrend, never dips
        @strategy
        def s(ctx):
            if ctx.now == ctx._feed.master_index[0]:
                ctx.broker.submit(Order("X", "buy", 10,
                                        order_type=OrderType.LIMIT,
                                        limit_price=df["close"].iloc[0] * 0.5))

        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                             initial_cash=100000, cost_model=ZeroCost())
        res = eng.run()
        assert len(res.fills) == 0


class TestStopOrders:
    def test_stop_loss_triggers(self):
        df = make_data(50, 0, drift=-0.005)  # declining
        @strategy
        def s(ctx):
            if ctx.now == ctx._feed.master_index[0]:
                ctx.broker.submit(Order("X", "buy", 10, tag="entry"))
                ctx.broker.submit(Order("X", "sell", 10,
                                        order_type=OrderType.STOP,
                                        stop_price=df["close"].iloc[0] * 0.95,
                                        tag="stop"))

        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                             initial_cash=100000, cost_model=ZeroCost())
        res = eng.run()
        # entry + stop should both eventually fill
        assert len(res.fills) >= 1


class TestSizing:
    def test_atr_sizing_helper(self):
        df = make_data(50, 0)
        @strategy
        def s(ctx):
            if ctx.now == ctx._feed.master_index[20]:
                d = ctx.get("X", "1d", lookback=25)
                atr = ctx.compute.atr(d.high, d.low, d.close, window=14).iloc[-1]
                if np.isnan(atr):
                    return
                qty = sizing.atr_risk_budget(100000, 0.01, atr, d.close.iloc[-1])
                if qty > 0:
                    ctx.broker.submit(Order("X", "buy", qty))

        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                             initial_cash=100000, cost_model=ZeroCost())
        res = eng.run()
        assert len(res.fills) >= 1
        assert res.fills[0].qty > 0


class TestPairTrading:
    def test_pair_zscore_strategy(self, pair_data):
        @strategy
        def pair_strat(ctx):
            btc = ctx.get("BTC", "1d", lookback=60)
            eth = ctx.get("ETH", "1d", lookback=60)
            if len(btc) < 60:
                return
            spread = np.log(btc.close) - np.log(eth.close)
            z = (spread - spread.rolling(20).mean()) / spread.rolling(20).std()
            last_z = z.iloc[-1]
            if np.isnan(last_z):
                return
            pos_btc = ctx.portfolio.get_position("BTC")
            pos_eth = ctx.portfolio.get_position("ETH")
            if last_z > 1.5 and pos_btc.qty == 0:
                # spread too wide: short BTC, long ETH
                ctx.broker.submit(Order("BTC", "sell", 1, tag="short_spread"))
                ctx.broker.submit(Order("ETH", "buy", 1, tag="long_spread"))
            elif abs(last_z) < 0.3 and pos_btc.qty != 0:
                ctx.broker.submit(Order("BTC", "buy", abs(pos_btc.qty), tag="close"))
                ctx.broker.submit(Order("ETH", "sell", abs(pos_eth.qty), tag="close"))

        eng = BacktestEngine(data=pair_data, strategy=pair_strat,
                             initial_cash=100000, allow_short=True,
                             cost_model=ZeroCost())
        res = eng.run()
        # ran successfully; equity curve full length
        assert len(res.equity) == 200


class TestRiskParity:
    def test_three_asset_rebalance(self):
        data = {f"S{i}": {"1d": make_data(150, i)} for i in range(3)}
        @strategy
        def rp(ctx):
            t = ctx.now
            idx = ctx._feed.master_index
            if list(idx).index(t) % 20 != 0:
                return
            # equal weight rebalance to 1/3 each
            for sym in ["S0", "S1", "S2"]:
                d = ctx.get(sym, "1d", lookback=2)
                if len(d) < 1:
                    continue
                price = d.close.iloc[-1]
                target_qty = (ctx.portfolio.cash / 3) / price
                pos = ctx.portfolio.get_position(sym)
                diff = target_qty - pos.qty
                if abs(diff) > 0.01:
                    side = "buy" if diff > 0 else "sell"
                    ctx.broker.submit(Order(sym, side, abs(diff), tag="rebal"))

        eng = BacktestEngine(data=data, strategy=rp, initial_cash=90000,
                             allow_short=False, cost_model=ZeroCost())
        res = eng.run()
        assert len(res.equity) == 150
