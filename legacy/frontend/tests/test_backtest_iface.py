"""BT-0: Backtest interface skeleton tests.

Validates that all core dataclasses, abstract base classes, and engine
signatures are importable and behave as documented in the design.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import (
    BacktestEngine, BacktestContext, ContextHistory, DataFeed, Universe,
    Strategy, FunctionStrategy, strategy, Signal,
    Order, Fill, OrderSide, OrderType, TimeInForce, OrderStatus,
    SimulatedBroker, Portfolio, Position,
    CostModel, PercentCost, FixedCost, TieredCost, MinCost, StampDutyCost, ZeroCost,
    FillModel, NextOpenFill, NextCloseFill, ThisCloseFill, VWAPFill, WorstPriceFill,
    LookaheadError, BacktestResult,
    sizing, buy_and_hold, benchmark_equity,
)


# ── Data structures ──

class TestOrders:
    def test_order_defaults(self):
        o = Order(symbol="AAPL", side="buy", qty=100)
        assert o.symbol == "AAPL"
        assert o.side == OrderSide.BUY
        assert o.order_type == OrderType.MARKET
        assert o.time_in_force == TimeInForce.GTC
        assert o.order_id  # auto-generated

    def test_order_signed_qty(self):
        buy = Order("X", "buy", 10)
        sell = Order("X", "sell", 10)
        assert buy.signed_qty == 10
        assert sell.signed_qty == -10

    def test_fill_net_value(self):
        f = Fill("oid", "X", "buy", qty=10, price=100,
                 commission=1.0, slippage_cost=0.5)
        assert f.gross_value == 1000.0
        # buy: cash flow out = -(gross + costs)
        assert f.net_value == pytest.approx(-(1000.0 + 1.0 + 0.5))


class TestPosition:
    def test_apply_fill_long(self):
        p = Position("X")
        p.apply_fill(10, 100.0)
        assert p.qty == 10
        assert p.avg_cost == 100.0
        assert p.is_long

    def test_apply_fill_close_realizes(self):
        p = Position("X")
        p.apply_fill(10, 100.0)
        realized = p.apply_fill(-10, 110.0)
        assert p.is_flat
        assert realized == pytest.approx(100.0)
        assert p.realized_pnl == pytest.approx(100.0)

    def test_unrealized_pnl(self):
        p = Position("X")
        p.apply_fill(10, 100.0)
        assert p.unrealized_pnl(120.0) == pytest.approx(200.0)


# ── Cost models ──

class TestCostModels:
    def test_percent_cost(self):
        c = PercentCost(commission=0.001, slippage=0.0005)
        o = Order("X", "buy", 100)
        comm, slip = c.compute(o, fill_price=100.0, fill_qty=100)
        assert comm == pytest.approx(10.0)
        assert slip == pytest.approx(5.0)

    def test_fixed_cost(self):
        c = FixedCost(fee=5.0, slippage=0.0)
        o = Order("X", "buy", 1)
        comm, slip = c.compute(o, 100.0, 1)
        assert comm == 5.0 and slip == 0.0

    def test_stamp_duty_sell_only(self):
        c = StampDutyCost(commission=0.0003, stamp_duty=0.001, slippage=0.0)
        buy = Order("X", "buy", 100)
        sell = Order("X", "sell", 100)
        comm_buy, _ = c.compute(buy, 100.0, 100)
        comm_sell, _ = c.compute(sell, 100.0, 100)
        assert comm_buy == pytest.approx(3.0)
        assert comm_sell == pytest.approx(3.0 + 10.0)

    def test_tiered_cost(self):
        c = TieredCost(slippage=0.0)
        small = Order("X", "buy", 1)
        comm, _ = c.compute(small, 100.0, 1)  # gross=100
        assert comm == pytest.approx(100 * 0.0005)

    def test_min_cost_floor(self):
        c = MinCost(commission=0.0003, min_fee=5.0, slippage=0.0)
        o = Order("X", "buy", 1)
        comm, _ = c.compute(o, 100.0, 1)  # gross=100 -> 0.03, floored to 5
        assert comm == 5.0

    def test_zero_cost(self):
        c = ZeroCost()
        o = Order("X", "buy", 100)
        comm, slip = c.compute(o, 100.0, 100)
        assert comm == 0.0 and slip == 0.0


# ── Fill models ──

class TestFillModels:
    def _bars(self):
        bar = pd.Series({"open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000})
        nxt = pd.Series({"open": 103, "high": 108, "low": 101, "close": 107, "volume": 1200})
        return bar, nxt

    def test_next_open(self):
        bar, nxt = self._bars()
        m = NextOpenFill()
        assert m.fill_price(Order("X", "buy", 1), bar, nxt) == 103

    def test_next_open_no_next(self):
        bar, _ = self._bars()
        assert NextOpenFill().fill_price(Order("X", "buy", 1), bar, None) is None

    def test_next_close(self):
        bar, nxt = self._bars()
        assert NextCloseFill().fill_price(Order("X", "buy", 1), bar, nxt) == 107

    def test_this_close_warns(self):
        bar, nxt = self._bars()
        with pytest.warns(UserWarning):
            ThisCloseFill().fill_price(Order("X", "buy", 1), bar, nxt)

    def test_vwap(self):
        bar, nxt = self._bars()
        # (103+108+101+107)/4
        assert VWAPFill().fill_price(Order("X", "buy", 1), bar, nxt) == pytest.approx((103 + 108 + 101 + 107) / 4)

    def test_worst_price_buy_uses_high(self):
        bar, nxt = self._bars()
        assert WorstPriceFill().fill_price(Order("X", "buy", 1), bar, nxt) == 108

    def test_worst_price_sell_uses_low(self):
        bar, nxt = self._bars()
        assert WorstPriceFill().fill_price(Order("X", "sell", 1), bar, nxt) == 101


# ── Universe + DataFeed ──

def _make_df(n=50, seed=0):
    import numpy as np
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1e6,
    }, index=dates)


class TestDataFeed:
    def test_universe_symbols(self):
        u = Universe({"A": {"1d": _make_df()}, "B": {"1d": _make_df(seed=1)}})
        assert set(u.symbols) == {"A", "B"}

    def test_master_index_union(self):
        df1 = _make_df(10)
        df2 = _make_df(10).iloc[3:]  # shifted
        u = Universe({"A": {"1d": df1}, "B": {"1d": df2}})
        feed = DataFeed(u)
        assert len(feed.master_index) == 10

    def test_get_slice_lookback(self):
        u = Universe({"A": {"1d": _make_df(50)}})
        feed = DataFeed(u)
        t = feed.master_index[20]
        sl = feed.get_slice("A", "1d", t, lookback=5)
        assert len(sl) == 5
        assert sl.index[-1] <= t

    def test_lookahead_protection(self):
        u = Universe({"A": {"1d": _make_df(50)}})
        feed = DataFeed(u)
        t = feed.master_index[10]
        sl = feed.get_slice("A", "1d", t)
        assert sl.index.max() <= t


# ── Portfolio ──

class TestPortfolio:
    def test_cash_decreases_on_buy(self):
        p = Portfolio(initial_cash=10000)
        from stockstat.backtest.orders import Fill
        p.apply_fill(Fill("o", "X", "buy", 10, 100, commission=1, slippage_cost=0))
        assert p.cash == pytest.approx(10000 - 1000 - 1)

    def test_short_disabled(self):
        p = Portfolio(initial_cash=10000, allow_short=False)
        from stockstat.backtest.orders import Fill
        with pytest.raises(RuntimeError):
            p.apply_fill(Fill("o", "X", "sell", 10, 100))

    def test_mark_to_market(self):
        p = Portfolio(initial_cash=10000)
        from stockstat.backtest.orders import Fill
        p.apply_fill(Fill("o", "X", "buy", 10, 100))
        eq = p.mark_to_market({"X": 110})
        assert eq == pytest.approx(10000 - 1000 + 1100)


# ── Strategy decorator ──

class TestStrategy:
    def test_function_strategy(self):
        @strategy
        def my(ctx):
            pass
        assert isinstance(my, FunctionStrategy)
        assert my.name == "my"

    def test_named_strategy(self):
        @strategy(name="custom")
        def my(ctx):
            pass
        assert my.name == "custom"

    def test_base_class_hooks(self):
        class S(Strategy):
            def on_bar(self, ctx): pass
        s = S()
        # all hooks callable, no-op by default
        s.on_start(None)
        s.on_bar(None)
        s.on_end(None)


# ── Sizing ──

class TestSizing:
    def test_fixed_size(self):
        assert sizing.fixed_size(100) == 100

    def test_fixed_amount(self):
        assert sizing.fixed_amount(1000, 100) == 10

    def test_percent_equity(self):
        assert sizing.percent_equity(0.1, 100000, 100) == 100

    def test_atr_risk_budget(self):
        # equity=100000, risk 1%, atr=2, multiplier=1 -> stop=2 -> 1000/2=500
        assert sizing.atr_risk_budget(100000, 0.01, 2.0, 100) == 500

    def test_kelly(self):
        # win_rate=0.5, ratio=2 -> 0.5 - 0.5/2 = 0.25
        assert sizing.kelly_fraction(0.5, 2.0) == pytest.approx(0.25)


# ── Benchmark ──

class TestBenchmark:
    def test_buy_and_hold(self):
        prices = pd.Series([10, 20, 30])
        eq = buy_and_hold(1000, prices)
        assert eq.iloc[0] == 1000
        assert eq.iloc[-1] == 3000


# ── Engine signature ──

class TestEngineSignature:
    def test_engine_constructs(self):
        df = _make_df(30)
        s = Strategy()
        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s, initial_cash=10000)
        assert eng.portfolio.initial_cash == 10000
        assert eng.universe.symbols == ["X"]

    def test_engine_invalid_trade_on(self):
        with pytest.raises(ValueError):
            BacktestEngine(data={"X": {"1d": _make_df(10)}}, strategy=Strategy(), trade_on="mid")
