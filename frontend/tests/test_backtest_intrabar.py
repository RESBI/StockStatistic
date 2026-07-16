"""Tests for BT-11/BT-12: ExecutionModel + IntrabarExecution.

Test categories:
1. Compatibility: existing API unchanged (Fill/Order new fields, default engine)
2. IntrabarFillModel: sub-bar scanning with timing
3. DataFeed.intrabar_slice: correct sub-bar extraction
4. IntrabarExecution: same-bar entry+exit, define_exits, OCO mutual, priority
5. Context: intrabar_submit degradation in default mode
"""
import warnings
import numpy as np
import pandas as pd
import pytest

from stockstat.backtest import (
    BacktestEngine, Strategy, IntrabarMixin, Order, Fill,
    IntrabarFillModel, IntrabarFillResult,
    ExecutionModel, NextBarExecution, IntrabarExecution,
    PercentCost, BinanceCost, BINANCE_SPOT,
)


# ── Fixtures ──────────────────────────────────────────────────

def make_1d_data(n=30, start_price=100.0):
    """Simple 1d OHLCV data."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    np.random.seed(42)
    returns = np.random.randn(n) * 0.02
    close = start_price * np.cumprod(1 + returns)
    df = pd.DataFrame({
        "open": close * (1 + np.random.randn(n) * 0.005),
        "high": close * (1 + np.abs(np.random.randn(n)) * 0.01),
        "low": close * (1 - np.abs(np.random.randn(n)) * 0.01),
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
    }, index=dates)
    df.index.name = "ts"
    return df


def make_1h_data_for_day(day, base_price=100.0):
    """24 hours of 1h data for a given day."""
    hours = pd.date_range(day + pd.Timedelta(hours=0),
                          day + pd.Timedelta(hours=23), freq="1h")
    np.random.seed(hash(str(day)) % 2**31)
    returns = np.random.randn(24) * 0.005
    close = base_price * np.cumprod(1 + returns)
    df = pd.DataFrame({
        "open": close * (1 + np.random.randn(24) * 0.002),
        "high": np.maximum(close, close * (1 + np.abs(np.random.randn(24)) * 0.003)),
        "low": np.minimum(close, close * (1 - np.abs(np.random.randn(24)) * 0.003)),
        "close": close,
        "volume": np.random.randint(100, 1000, 24),
    }, index=hours)
    df.index.name = "ts"
    return df


def make_multitf_data(n_days=30):
    """1d + 1h multi-timeframe data."""
    daily = make_1d_data(n_days)
    hourly_list = []
    for day in daily.index:
        h = make_1h_data_for_day(day, daily.loc[day, "close"])
        hourly_list.append(h)
    hourly = pd.concat(hourly_list)
    return {"TEST/USDT": {"1d": daily, "1h": hourly}}


# ── 1. Compatibility Tests ────────────────────────────────────

class TestCompatibility:
    """Verify existing API is unchanged."""

    def test_fill_new_fields_default(self):
        f = Fill(order_id="x", symbol="TEST", side="buy", qty=1.0, price=100.0)
        assert f.sub_bar_ts is None
        assert f.sub_bar_index == -1

    def test_order_new_field_default(self):
        o = Order(symbol="TEST", side="buy", qty=1.0)
        assert o.priority == 99

    def test_order_priority_in_init(self):
        o = Order(symbol="TEST", side="buy", qty=1.0, priority=0)
        assert o.priority == 0

    def test_default_engine_unchanged(self):
        """BacktestEngine without execution_model works as before."""
        data = make_multitf_data(10)

        @staticmethod
        def simple(ctx):
            d = ctx.get("TEST/USDT", "1d", lookback=5)
            if len(d) < 3:
                return
            pos = ctx.portfolio.get_position("TEST/USDT")
            if d["close"].iloc[-1] > d["close"].iloc[-2] and pos.qty == 0:
                from stockstat.backtest import Order as O
                ctx.broker.submit(O("TEST/USDT", "buy", 1.0))

        from stockstat.backtest import strategy
        strat = strategy(simple)
        res = BacktestEngine(data=data, strategy=strat,
                            initial_cash=10000).run()
        assert len(res.equity) > 0

    def test_nextbar_execution_is_not_intrabar(self):
        m = NextBarExecution()
        assert m.is_intrabar is False

    def test_intrabar_execution_is_intrabar(self):
        m = IntrabarExecution(intrabar_tf="1h")
        assert m.is_intrabar is True


# ── 2. IntrabarFillModel Tests ────────────────────────────────

class TestIntrabarFillModel:

    def setup_method(self):
        self.filler = IntrabarFillModel()
        dates = pd.date_range("2024-01-01", periods=5, freq="1h")
        self.sub_bars = pd.DataFrame({
            "open": [100, 101, 102, 101, 100],
            "high": [101, 102, 103, 102, 101],
            "low":  [99, 100, 101, 100, 99],
            "close":[101, 102, 102, 101, 100],
            "volume":[100]*5,
        }, index=dates)

    def test_limit_buy_fills(self):
        order = Order("TEST", "buy", 1.0, order_type="limit", limit_price=100.0)
        result = self.filler.fill_with_timing(order, self.sub_bars)
        assert result is not None
        assert result.fill_price == 100.0
        assert result.sub_bar_index == 0  # First bar low=99 <= 100

    def test_limit_sell_fills(self):
        order = Order("TEST", "sell", 1.0, order_type="limit", limit_price=102.0)
        result = self.filler.fill_with_timing(order, self.sub_bars)
        assert result is not None
        assert result.fill_price == 102.0
        assert result.sub_bar_index == 1  # Second bar high=102 >= 102

    def test_market_fills_at_first_open(self):
        order = Order("TEST", "buy", 1.0, order_type="market")
        result = self.filler.fill_with_timing(order, self.sub_bars)
        assert result is not None
        assert result.fill_price == 100.0  # First bar open
        assert result.sub_bar_index == 0

    def test_no_fill_returns_none(self):
        order = Order("TEST", "buy", 1.0, order_type="limit", limit_price=95.0)
        result = self.filler.fill_with_timing(order, self.sub_bars)
        assert result is None

    def test_empty_sub_bars(self):
        order = Order("TEST", "buy", 1.0, order_type="limit", limit_price=100.0)
        assert self.filler.fill_with_timing(order, pd.DataFrame()) is None
        assert self.filler.fill_with_timing(order, None) is None

    def test_stop_buy_fills(self):
        order = Order("TEST", "buy", 1.0, order_type="stop", stop_price=102.0)
        result = self.filler.fill_with_timing(order, self.sub_bars)
        assert result is not None
        assert result.fill_price == 102.0
        assert result.sub_bar_index == 1  # high=102 >= 102


# ── 3. DataFeed.intrabar_slice Tests ──────────────────────────

class TestIntrabarSlice:

    def test_slice_returns_correct_range(self):
        data = make_multitf_data(5)
        from stockstat.backtest import Universe, DataFeed
        uni = Universe(data)
        feed = DataFeed(uni)

        day = uni.raw("TEST/USDT", "1d").index[2]
        sub = feed.intrabar_slice("TEST/USDT", "1d", "1h", day)

        assert len(sub) == 24
        assert sub.index[0] >= day
        assert sub.index[-1] < day + pd.Timedelta(days=1)

    def test_slice_nonexistent_symbol(self):
        data = make_multitf_data(3)
        from stockstat.backtest import Universe, DataFeed
        feed = DataFeed(Universe(data))
        day = data["TEST/USDT"]["1d"].index[0]
        sub = feed.intrabar_slice("NONEXIST", "1d", "1h", day)
        assert len(sub) == 0


# ── 4. IntrabarExecution Tests ────────────────────────────────

class TestIntrabarExecution:
    """Test Gap-1 through Gap-5 solutions."""

    def test_same_bar_entry_exit(self):
        """Gap-2: order fills and exits within the same parent bar."""
        data = make_multitf_data(10)
        first_day = data["TEST/USDT"]["1d"].index[0]
        open_price = data["TEST/USDT"]["1d"].loc[first_day, "open"]

        class TestStrategy(Strategy, IntrabarMixin):
            def __init__(self):
                self.entry_filled = False
                self.exit_filled = False

            def on_bar(self, ctx):
                if ctx.now != first_day:
                    return
                ctx.intrabar_submit(
                    Order("TEST/USDT", "buy", 1.0, tag="entry")
                )

            def define_exits(self, entry_fill, ctx):
                self.entry_filled = True
                return [
                    Order("TEST/USDT", "sell", 1.0,
                          order_type="market", tag="close",
                          exit_reason="close", priority=99)
                ]

            def on_fill(self, fill, ctx):
                if fill.tag == "close":
                    self.exit_filled = True

        strat = TestStrategy()
        engine = BacktestEngine(
            data=data, strategy=strat, initial_cash=10000,
            execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
        )
        res = engine.run()

        assert strat.entry_filled, "Entry should have filled"
        assert strat.exit_filled, "Exit should have filled"
        assert len(res.fills) >= 2  # entry + exit

    def test_define_exits_called(self):
        """Gap-3: define_exits is called after entry fill."""
        data = make_multitf_data(5)
        first_day = data["TEST/USDT"]["1d"].index[0]

        class TestStrategy(Strategy, IntrabarMixin):
            def __init__(self):
                self.exits_called = 0

            def on_bar(self, ctx):
                if ctx.now != first_day:
                    return
                ctx.intrabar_submit(Order("TEST/USDT", "buy", 1.0, tag="entry"))

            def define_exits(self, entry_fill, ctx):
                self.exits_called += 1
                return [Order("TEST/USDT", "sell", 1.0,
                              order_type="market", tag="close",
                              exit_reason="close")]

        strat = TestStrategy()
        engine = BacktestEngine(
            data=data, strategy=strat, initial_cash=10000,
            execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
        )
        engine.run()
        assert strat.exits_called >= 1

    def test_no_define_exits_works(self):
        """Duck typing: strategy without define_exits works."""
        data = make_multitf_data(5)
        first_day = data["TEST/USDT"]["1d"].index[0]

        class SimpleStrategy(Strategy):
            def on_bar(self, ctx):
                if ctx.now != first_day:
                    return
                ctx.intrabar_submit(Order("TEST/USDT", "buy", 1.0, tag="entry"))

        strat = SimpleStrategy()
        engine = BacktestEngine(
            data=data, strategy=strat, initial_cash=10000,
            execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
        )
        res = engine.run()
        assert len(res.fills) >= 1  # At least the entry fill

    def test_priority_sl_before_tp(self):
        """Gap-5: When SL and TP both trigger in same sub-bar, SL wins (priority 0 < 1)."""
        day = pd.Timestamp("2024-01-01")
        hours = pd.date_range(day, periods=3, freq="1h")
        # Bar 0: both SL (low=97<=98) and TP (high=102>=101) trigger
        sub_bars = pd.DataFrame({
            "open":  [100, 101, 100],
            "high":  [102, 101, 100],
            "low":   [ 97, 100,  99],
            "close": [101, 101, 100],
            "volume":[100, 100, 100],
        }, index=hours)

        daily = pd.DataFrame({
            "open": [100], "high": [102], "low": [97], "close": [100],
            "volume": [300],
        }, index=pd.DatetimeIndex([day]))

        data = {"TEST/USDT": {"1d": daily, "1h": sub_bars}}

        class TestStrategy(Strategy, IntrabarMixin):
            def __init__(self):
                self.exit_reason = None

            def on_bar(self, ctx):
                if ctx.now != day:
                    return
                ctx.intrabar_submit(Order("TEST/USDT", "buy", 1.0, tag="entry"))

            def define_exits(self, entry_fill, ctx):
                return [
                    Order("TEST/USDT", "sell", 1.0,
                          order_type="stop", stop_price=98.0,
                          tag="sl", exit_reason="sl", priority=0),
                    Order("TEST/USDT", "sell", 1.0,
                          order_type="limit", limit_price=101.0,
                          tag="tp", exit_reason="tp", priority=1),
                ]

            def on_fill(self, fill, ctx):
                if fill.exit_reason in ("sl", "tp"):
                    self.exit_reason = fill.exit_reason

        strat = TestStrategy()
        engine = BacktestEngine(
            data=data, strategy=strat, initial_cash=10000,
            execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
        )
        engine.run()

        # In bar 0, both SL (low=97<=98) and TP (high=102>=101) trigger.
        # SL has priority=0, so it should be checked first → SL fills.
        assert strat.exit_reason == "sl"

    def test_priority_sl_and_tp_same_bar(self):
        """Gap-5: When SL and TP both trigger in same sub-bar, SL wins."""
        day = pd.Timestamp("2024-01-01")
        hours = pd.date_range(day, periods=3, freq="1h")
        # Bar 0: both SL (low=97<=98) and TP (high=102>=101) trigger
        sub_bars = pd.DataFrame({
            "open":  [100, 101, 100],
            "high":  [102, 101, 100],
            "low":   [ 97, 100,  99],
            "close": [101, 101, 100],
            "volume":[100, 100, 100],
        }, index=hours)

        daily = pd.DataFrame({
            "open": [100], "high": [102], "low": [97], "close": [100],
            "volume": [300],
        }, index=pd.DatetimeIndex([day]))

        data = {"TEST/USDT": {"1d": daily, "1h": sub_bars}}

        class TestStrategy(Strategy, IntrabarMixin):
            def __init__(self):
                self.exit_reason = None

            def on_bar(self, ctx):
                if ctx.now != day:
                    return
                ctx.intrabar_submit(Order("TEST/USDT", "buy", 1.0, tag="entry"))

            def define_exits(self, entry_fill, ctx):
                return [
                    Order("TEST/USDT", "sell", 1.0,
                          order_type="stop", stop_price=98.0,
                          tag="sl", exit_reason="sl", priority=0),
                    Order("TEST/USDT", "sell", 1.0,
                          order_type="limit", limit_price=101.0,
                          tag="tp", exit_reason="tp", priority=1),
                ]

            def on_fill(self, fill, ctx):
                if fill.exit_reason in ("sl", "tp"):
                    self.exit_reason = fill.exit_reason

        strat = TestStrategy()
        engine = BacktestEngine(
            data=data, strategy=strat, initial_cash=10000,
            execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
        )
        engine.run()

        # In bar 0, both SL (low=97<=98) and TP (high=102>=101) trigger.
        # SL has priority=0, so it should be checked first → SL fills.
        assert strat.exit_reason == "sl"

    def test_oco_mutual_both_cancel(self):
        """Gap-4: If both OCO mutual orders fill, both are cancelled."""
        day = pd.Timestamp("2024-01-01")
        hours = pd.date_range(day, periods=5, freq="1h")
        # Price hits buy limit (low=95) then sell limit (high=105)
        sub_bars = pd.DataFrame({
            "open":  [100,  98,  95, 100, 105],
            "high":  [101,  99,  96, 101, 106],
            "low":   [ 99,  97,  95,  99, 104],
            "close": [100,  98,  96, 100, 105],
            "volume":[100]*5,
        }, index=hours)

        daily = pd.DataFrame({
            "open": [100], "high": [106], "low": [95], "close": [105],
            "volume": [500],
        }, index=pd.DatetimeIndex([day]))

        data = {"TEST/USDT": {"1d": daily, "1h": sub_bars}}

        class TestStrategy(Strategy, IntrabarMixin):
            def __init__(self):
                self.entry_fills = 0

            def on_bar(self, ctx):
                if ctx.now != day:
                    return
                buy = Order("TEST/USDT", "buy", 1.0,
                            order_type="limit", limit_price=96.0, tag="buy")
                sell = Order("TEST/USDT", "sell", 1.0,
                             order_type="limit", limit_price=104.0, tag="sell")
                ctx.intrabar_submit_oco_mutual(buy, sell)

            def on_fill(self, fill, ctx):
                if fill.tag in ("buy", "sell"):
                    self.entry_fills += 1

        strat = TestStrategy()
        engine = BacktestEngine(
            data=data, strategy=strat, initial_cash=10000,
            execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
        )
        res = engine.run()

        # Both buy limit (96.0, hit at hour 2 low=95) and
        # sell limit (104.0, hit at hour 4 high=106) fill → mutual cancel
        assert strat.entry_fills == 0, "Both fills should be cancelled"

    def test_oco_mutual_one_fills(self):
        """Gap-4: If only one OCO mutual order fills, it's kept."""
        day = pd.Timestamp("2024-01-01")
        hours = pd.date_range(day, periods=5, freq="1h")
        # Price only hits buy limit (low=95), never hits sell limit (high<105)
        sub_bars = pd.DataFrame({
            "open":  [100,  98,  95,  97,  99],
            "high":  [101,  99,  96,  98, 100],
            "low":   [ 99,  97,  94,  96,  98],
            "close": [100,  98,  95,  97,  99],
            "volume":[100]*5,
        }, index=hours)

        daily = pd.DataFrame({
            "open": [100], "high": [101], "low": [94], "close": [99],
            "volume": [500],
        }, index=pd.DatetimeIndex([day]))

        data = {"TEST/USDT": {"1d": daily, "1h": sub_bars}}

        class TestStrategy(Strategy, IntrabarMixin):
            def __init__(self):
                self.entry_fills = 0

            def on_bar(self, ctx):
                if ctx.now != day:
                    return
                buy = Order("TEST/USDT", "buy", 1.0,
                            order_type="limit", limit_price=96.0, tag="buy")
                sell = Order("TEST/USDT", "sell", 1.0,
                             order_type="limit", limit_price=105.0, tag="sell")
                ctx.intrabar_submit_oco_mutual(buy, sell)

            def on_fill(self, fill, ctx):
                if fill.tag == "buy":
                    self.entry_fills += 1

        strat = TestStrategy()
        engine = BacktestEngine(
            data=data, strategy=strat, initial_cash=10000,
            execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
        )
        engine.run()

        # Only buy limit fills → kept
        assert strat.entry_fills == 1

    def test_fill_has_intrabar_timing(self):
        """Gap-1: Fill records sub_bar_ts and sub_bar_index."""
        data = make_multitf_data(5)
        first_day = data["TEST/USDT"]["1d"].index[0]

        class TestStrategy(Strategy, IntrabarMixin):
            def __init__(self):
                self.entry_fill = None

            def on_bar(self, ctx):
                if ctx.now != first_day:
                    return
                ctx.intrabar_submit(Order("TEST/USDT", "buy", 1.0, tag="entry"))

            def define_exits(self, entry_fill, ctx):
                self.entry_fill = entry_fill
                return [Order("TEST/USDT", "sell", 1.0,
                              order_type="market", tag="close",
                              exit_reason="close")]

        strat = TestStrategy()
        engine = BacktestEngine(
            data=data, strategy=strat, initial_cash=10000,
            execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
        )
        engine.run()

        assert strat.entry_fill is not None
        assert strat.entry_fill.sub_bar_index >= 0
        assert strat.entry_fill.sub_bar_ts is not None


# ── 5. Context Degradation Tests ──────────────────────────────

class TestContextDegradation:

    def test_intrabar_submit_degrades_with_warning(self):
        """C1: intrabar_submit in default mode warns and degrades to broker.submit."""
        data = make_multitf_data(5)

        class TestStrategy(Strategy):
            def __init__(self):
                self.warned = False

            def on_bar(self, ctx):
                try:
                    with warnings.catch_warnings(record=True) as w:
                        warnings.simplefilter("always")
                        ctx.intrabar_submit(Order("TEST/USDT", "buy", 1.0))
                        if len(w) > 0:
                            self.warned = True
                except Exception:
                    pass

        strat = TestStrategy()
        engine = BacktestEngine(data=data, strategy=strat, initial_cash=10000)
        engine.run()
        assert strat.warned, "Should have warned about non-intrabar mode"
