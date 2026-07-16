"""BT-8: P0 backtest engine improvements — intrabar limit fills, maker/taker cost, OCO orders."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import (
    BacktestEngine, strategy, Order, OrderType, TimeInForce,
    PercentCost, ZeroCost, MakerTakerCost, BinanceCost,
    NextOpenFill, IntrabarLimitFill,
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


# ═══════════════════════════════════════════════
# Test IntrabarLimitFill
# ═══════════════════════════════════════════════

class TestIntrabarLimitFill:
    def test_limit_buy_fills_on_low_touch(self):
        bar = pd.Series({"open": 100, "high": 101, "low": 98, "close": 99, "volume": 1e6})
        next_bar = pd.Series({"open": 100, "high": 101, "low": 97, "close": 98, "volume": 1e6})
        order = Order("X", "buy", 10, order_type=OrderType.LIMIT, limit_price=98.0)
        fill = IntrabarLimitFill().fill_price(order, bar, next_bar)
        assert fill == 98.0

    def test_limit_buy_no_fill_if_low_above_limit(self):
        bar = pd.Series({"open": 100, "high": 101, "low": 98, "close": 99, "volume": 1e6})
        next_bar = pd.Series({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1e6})
        order = Order("X", "buy", 10, order_type=OrderType.LIMIT, limit_price=95.0)
        fill = IntrabarLimitFill().fill_price(order, bar, next_bar)
        assert fill is None

    def test_limit_sell_fills_on_high_touch(self):
        bar = pd.Series({"open": 100, "high": 101, "low": 98, "close": 99, "volume": 1e6})
        next_bar = pd.Series({"open": 100, "high": 105, "low": 99, "close": 104, "volume": 1e6})
        order = Order("X", "sell", 10, order_type=OrderType.LIMIT, limit_price=103.0)
        fill = IntrabarLimitFill().fill_price(order, bar, next_bar)
        assert fill == 103.0

    def test_market_order_uses_open(self):
        bar = pd.Series({"open": 100, "high": 101, "low": 98, "close": 99, "volume": 1e6})
        next_bar = pd.Series({"open": 102, "high": 105, "low": 99, "close": 104, "volume": 1e6})
        order = Order("X", "buy", 10, order_type=OrderType.MARKET)
        fill = IntrabarLimitFill().fill_price(order, bar, next_bar)
        assert fill == 102.0

    def test_next_open_fill_still_works(self):
        bar = pd.Series({"open": 100, "high": 101, "low": 98, "close": 99, "volume": 1e6})
        next_bar = pd.Series({"open": 102, "high": 105, "low": 99, "close": 104, "volume": 1e6})
        order = Order("X", "buy", 10, order_type=OrderType.MARKET)
        fill = NextOpenFill().fill_price(order, bar, next_bar)
        assert fill == 102.0

    def test_stop_buy_fills_on_high(self):
        bar = pd.Series({"open": 100, "high": 101, "low": 98, "close": 99, "volume": 1e6})
        next_bar = pd.Series({"open": 100, "high": 106, "low": 99, "close": 105, "volume": 1e6})
        order = Order("X", "buy", 10, order_type=OrderType.STOP, stop_price=104.0)
        fill = IntrabarLimitFill().fill_price(order, bar, next_bar)
        assert fill == 104.0


# ═══════════════════════════════════════════════
# Test MakerTakerCost
# ═══════════════════════════════════════════════

class TestMakerTakerCost:
    def test_limit_uses_maker_rate(self):
        cost = MakerTakerCost(maker_rate=0.001, taker_rate=0.002, slippage=0.0)
        order = Order("X", "buy", 10, order_type=OrderType.LIMIT, limit_price=100)
        comm, _ = cost.compute(order, 100, 10)
        assert comm == pytest.approx(1000 * 0.001)

    def test_market_uses_taker_rate(self):
        cost = MakerTakerCost(maker_rate=0.001, taker_rate=0.002, slippage=0.0)
        order = Order("X", "buy", 10, order_type=OrderType.MARKET)
        comm, _ = cost.compute(order, 100, 10)
        assert comm == pytest.approx(1000 * 0.002)

    def test_equivalent_to_percent_when_equal(self):
        mt = MakerTakerCost(maker_rate=0.001, taker_rate=0.001, slippage=0.0002)
        pc = PercentCost(commission=0.001, slippage=0.0002)
        order = Order("X", "buy", 10, order_type=OrderType.MARKET)
        assert mt.compute(order, 100, 10) == pc.compute(order, 100, 10)


# ═══════════════════════════════════════════════
# Test BinanceCost
# ═══════════════════════════════════════════════

class TestBinanceCost:
    def test_spot_maker_rate(self):
        c = BinanceCost(venue="spot", bnb_discount=False, slippage=0.0)
        order = Order("X", "buy", 1, order_type=OrderType.LIMIT, limit_price=100)
        comm, _ = c.compute(order, 100, 1)
        assert comm == pytest.approx(100 * 0.001)

    def test_futures_taker_rate(self):
        c = BinanceCost(venue="futures", bnb_discount=False, slippage=0.0)
        order = Order("X", "buy", 1, order_type=OrderType.MARKET)
        comm, _ = c.compute(order, 100, 1)
        assert comm == pytest.approx(100 * 0.0005)

    def test_bnb_discount_spot(self):
        c = BinanceCost(venue="spot", bnb_discount=True, slippage=0.0)
        order = Order("X", "buy", 1, order_type=OrderType.LIMIT, limit_price=100)
        comm, _ = c.compute(order, 100, 1)
        assert comm == pytest.approx(100 * 0.00075)

    def test_bnb_discount_futures(self):
        c = BinanceCost(venue="futures", bnb_discount=True, slippage=0.0)
        order = Order("X", "buy", 1, order_type=OrderType.MARKET)
        comm, _ = c.compute(order, 100, 1)
        assert comm == pytest.approx(100 * 0.00045)


# ═══════════════════════════════════════════════
# Test OCO Orders
# ═══════════════════════════════════════════════

class TestOCOOrders:
    def test_one_fills_other_cancelled(self, data):
        @strategy
        def s(ctx):
            idx = list(ctx._feed.master_index)
            if idx.index(ctx.now) == 0:
                buy = Order("X", "buy", 10, order_type=OrderType.LIMIT, limit_price=90.0)
                sell = Order("X", "sell", 10, order_type=OrderType.LIMIT, limit_price=110.0)
                ctx.broker.submit_oco(buy, sell)

        eng = BacktestEngine(data={"X": {"1d": data}}, strategy=s,
                             fill_model=IntrabarLimitFill(), cost_model=ZeroCost(),
                             allow_short=True)
        res = eng.run()
        assert len(res.fills) <= 1

    def test_cancel_propagation(self, data):
        order_ids = []

        @strategy
        def s(ctx):
            idx = list(ctx._feed.master_index)
            i = idx.index(ctx.now)
            if i == 0:
                buy = Order("X", "buy", 10, order_type=OrderType.LIMIT, limit_price=1.0)
                sell = Order("X", "sell", 10, order_type=OrderType.LIMIT, limit_price=99999.0)
                ctx.broker.submit_oco(buy, sell)
                order_ids.append(buy.order_id)
            elif i == 1 and order_ids:
                ctx.broker.cancel(order_ids[0])

        eng = BacktestEngine(data={"X": {"1d": data}}, strategy=s, cost_model=ZeroCost(),
                             allow_short=True)
        eng.run()
        assert len(eng.broker.pending_orders) == 0


# ═══════════════════════════════════════════════
# Test exit_reason field
# ═══════════════════════════════════════════════

class TestExitReason:
    def test_exit_reason_propagated(self, data):
        @strategy
        def s(ctx):
            idx = list(ctx._feed.master_index)
            i = idx.index(ctx.now)
            if i == 0:
                ctx.broker.submit(Order("X", "buy", 10, tag="entry"))
            elif i == 2:
                pos = ctx.portfolio.get_position("X")
                if pos.qty > 0:
                    ctx.broker.submit(Order("X", "sell", pos.qty, tag="tp", exit_reason="tp"))

        eng = BacktestEngine(data={"X": {"1d": data}}, strategy=s, cost_model=ZeroCost())
        res = eng.run()
        sells = [f for f in res.fills if f.side.value == "sell"]
        assert any(f.exit_reason == "tp" for f in sells)

    def test_default_exit_reason_empty(self, data):
        @strategy
        def s(ctx):
            idx = list(ctx._feed.master_index)
            if idx.index(ctx.now) == 0:
                ctx.broker.submit(Order("X", "buy", 10))

        eng = BacktestEngine(data={"X": {"1d": data}}, strategy=s, cost_model=ZeroCost())
        res = eng.run()
        assert all(f.exit_reason == "" for f in res.fills)
