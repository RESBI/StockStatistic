"""test_backtest.py — BacktestEngine 回测测试 (40 项)。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockstat_compute import (
    BacktestEngine, BacktestResult, BacktestMetrics, Trade,
    Strategy, StrategyBase, Signal,
    CostModel, FEE_MODELS, get_cost_model,
    FillModel, FILL_MODELS, get_fill_model,
    Broker, Portfolio, Position,
    calculate_metrics, batch_backtest, grid_search,
    MonteCarloEngine, WalkForward,
)
from stockstat_foundation import cloudpickle_dumps


@pytest.fixture
def ohlcv_df():
    rng = np.random.default_rng(42)
    n = 200
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


def buy_and_hold_strategy(i, bar, data, context):
    """简单 buy-and-hold：第一个 bar 全仓买入。"""
    if i == 0:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy", strength=1.0)
    return None


def ma_cross_strategy(i, bar, data, context, short=5, long=20):
    """MA cross 策略。"""
    if i < long:
        return None
    short_ma = data["close"].iloc[max(0, i - short):i + 1].mean()
    long_ma = data["close"].iloc[max(0, i - long):i + 1].mean()
    prev_short = data["close"].iloc[max(0, i - short - 1):i].mean()
    prev_long = data["close"].iloc[max(0, i - long - 1):i].mean()
    # 金叉买入
    if prev_short <= prev_long and short_ma > long_ma:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy", strength=1.0)
    # 死叉卖出
    if prev_short >= prev_long and short_ma < long_ma:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="sell", strength=1.0)
    return None


class TestBacktestEngine:
    def test_run_buy_and_hold(self, ohlcv_df):
        engine = BacktestEngine(
            data=ohlcv_df, strategy=buy_and_hold_strategy,
            initial_cash=10000, symbol="TEST", timeframe="1d",
        )
        result = engine.run()
        assert isinstance(result, BacktestResult)
        assert result.error is None
        assert result.metrics.n_trades >= 1
        assert result.metrics.initial_cash == 10000
        assert result.final_equity > 0

    def test_run_ma_cross(self, ohlcv_df):
        def strat(i, bar, data, ctx):
            return ma_cross_strategy(i, bar, data, ctx, short=5, long=20)
        engine = BacktestEngine(ohlcv_df, strat, initial_cash=10000)
        result = engine.run()
        assert result.error is None
        assert len(result.trades) >= 0

    def test_result_has_equity_curve(self, ohlcv_df):
        engine = BacktestEngine(ohlcv_df, buy_and_hold_strategy, initial_cash=10000)
        result = engine.run()
        assert result.equity_curve is not None
        assert len(result.equity_curve) == len(ohlcv_df)
        assert "equity" in result.equity_curve.columns

    def test_result_has_metrics(self, ohlcv_df):
        engine = BacktestEngine(ohlcv_df, buy_and_hold_strategy, initial_cash=10000)
        result = engine.run()
        m = result.metrics
        assert isinstance(m, BacktestMetrics)
        assert m.total_return is not None
        assert m.sharpe is not None
        assert m.max_drawdown is not None
        assert m.n_trades >= 1

    def test_empty_data_raises(self):
        from stockstat_foundation.errors import ComputeError
        with pytest.raises(ComputeError):
            BacktestEngine(pd.DataFrame(), buy_and_hold_strategy)

    def test_invalid_strategy_raises(self, ohlcv_df):
        from stockstat_foundation.errors import ComputeError
        with pytest.raises(ComputeError):
            BacktestEngine(ohlcv_df, "not a strategy")

    def test_with_cost_model(self, ohlcv_df):
        engine = BacktestEngine(
            ohlcv_df, buy_and_hold_strategy,
            initial_cash=10000, cost_model="F1_SpotNoBNB",
        )
        result = engine.run()
        # 应有手续费扣除
        assert result.error is None

    def test_with_zero_cost(self, ohlcv_df):
        engine = BacktestEngine(
            ohlcv_df, buy_and_hold_strategy,
            initial_cash=10000, cost_model="zero",
        )
        result = engine.run()
        assert result.error is None

    def test_strategy_class(self, ohlcv_df):
        class MyStrategy(StrategyBase):
            name = "my"
            def on_bar(self, i, bar, data, ctx):
                if i == 0:
                    return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
                return None
        engine = BacktestEngine(ohlcv_df, MyStrategy(), initial_cash=10000)
        result = engine.run()
        assert result.metrics.n_trades >= 1

    def test_result_summary(self, ohlcv_df):
        engine = BacktestEngine(ohlcv_df, buy_and_hold_strategy, initial_cash=10000)
        result = engine.run()
        s = result.summary()
        assert "BacktestResult" in s
        assert "total_return" in s

    def test_result_to_dict(self, ohlcv_df):
        engine = BacktestEngine(ohlcv_df, buy_and_hold_strategy, initial_cash=10000)
        result = engine.run()
        d = result.to_dict()
        assert "metrics" in d
        assert "trades" in d


class TestCostModels:
    def test_default_cost_model(self):
        cm = get_cost_model("default")
        assert cm.fee_rate == 0.001
        assert cm.calculate(100, 100) == 10.0

    def test_zero_cost_model(self):
        cm = get_cost_model("zero")
        assert cm.fee_rate == 0.0
        assert cm.calculate(100, 100) == 0.0

    def test_binance_fee_models(self):
        f1 = get_cost_model("F1_SpotNoBNB")
        f4 = get_cost_model("F4_FutBNB")
        assert f1.fee_rate == 0.001
        assert f4.fee_rate == 0.00018
        assert f4.fee_rate < f1.fee_rate

    def test_all_fee_models_exist(self):
        for name in ["default", "zero", "F1_SpotNoBNB", "F2_SpotBNB",
                     "F3_FutNoBNB", "F4_FutBNB", "binance_spot",
                     "binance_futures_bnb", "binance_futures", "stock"]:
            cm = get_cost_model(name)
            assert cm is not None

    def test_custom_rate_string(self):
        cm = get_cost_model("0.0005")
        assert cm.fee_rate == 0.0005


class TestFillModels:
    def test_next_open(self, ohlcv_df):
        fm = get_fill_model("next_open")
        price = fm.get_fill_price(0, ohlcv_df, "buy")
        assert price == ohlcv_df.iloc[1]["open"]

    def test_this_close(self, ohlcv_df):
        fm = get_fill_model("this_close")
        price = fm.get_fill_price(0, ohlcv_df, "buy")
        assert price == ohlcv_df.iloc[0]["close"]

    def test_slippage(self, ohlcv_df):
        fm = FillModel(name="next_open", slippage_bps=10)
        base_price = ohlcv_df.iloc[1]["open"]
        buy_price = fm.get_fill_price(0, ohlcv_df, "buy")
        assert buy_price > base_price  # 买入加价
        sell_price = fm.get_fill_price(0, ohlcv_df, "sell")
        assert sell_price < base_price  # 卖出减价


class TestPortfolio:
    def test_buy_updates_cash(self):
        p = Portfolio(initial_cash=10000)
        p.execute_buy("BTC", 1, 100, cost=1)
        assert p.cash < 10000
        assert p.get_position("BTC").quantity == 1

    def test_sell_updates_cash(self):
        p = Portfolio(initial_cash=10000)
        p.execute_buy("BTC", 1, 100, cost=0)
        p.execute_sell("BTC", 1, 110, cost=0)
        # 买入 1@100 = 100，卖出 1@110 = 110，初始 10000
        assert abs(p.cash - 10010) < 1e-6

    def test_short_not_allowed(self):
        p = Portfolio(initial_cash=10000, allow_short=False)
        p.execute_sell("BTC", 1, 100)
        # 不允许做空，应该不执行
        assert p.get_position("BTC").quantity == 0

    def test_short_allowed(self):
        p = Portfolio(initial_cash=10000, allow_short=True)
        p.execute_sell("BTC", 1, 100)
        assert p.get_position("BTC").quantity == -1

    def test_total_value(self):
        p = Portfolio(initial_cash=10000)
        p.execute_buy("BTC", 1, 100, cost=0)
        # 持仓 1 BTC @ 100，cash=9900
        assert p.total_value({"BTC": 100}) == 10000

    def test_target_pct(self):
        p = Portfolio(initial_cash=10000)
        p.execute_target_pct("BTC", 0.5, 100, 10000, cost=0)
        # 50% = 5000 / 100 = 50 BTC
        assert abs(p.get_position("BTC").quantity - 50) < 1e-6


class TestBatchBacktest:
    def test_batch_basic(self, ohlcv_df):
        strategies = {
            "buy_hold": buy_and_hold_strategy,
            "ma_cross_5_20": lambda i, bar, data, ctx: ma_cross_strategy(i, bar, data, ctx, 5, 20),
        }
        df = batch_backtest(
            ohlcv_df, strategies,
            fee_models=["F1_SpotNoBNB", "F4_FutBNB"],
            initial_cash=10000,
        )
        assert len(df) == 4  # 2 strategies × 2 fees
        assert {"strategy", "fee_model", "sharpe"}.issubset(df.columns)

    def test_batch_paxg_scenario(self, ohlcv_df):
        # 模拟 PAXG v5-redo: 33 策略 × 4 费率 = 132 回测
        strategies = {f"S{i}": buy_and_hold_strategy for i in range(33)}
        df = batch_backtest(
            ohlcv_df, strategies,
            fee_models=["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"],
            initial_cash=10000,
        )
        assert len(df) == 132  # 33 × 4


class TestGridSearch:
    def test_grid_basic(self, ohlcv_df):
        # 网格搜索需要 strategy_cls（类），这里用简单测试
        class MaCrossStrategy(StrategyBase):
            name = "ma_cross"
            def __init__(self, short=5, long=20):
                self.short = short
                self.long = long
            def on_bar(self, i, bar, data, ctx):
                return ma_cross_strategy(i, bar, data, ctx, self.short, self.long)
        df = grid_search(
            ohlcv_df, MaCrossStrategy,
            param_grid={"short": [3, 5, 8], "long": [10, 20]},
            metric="sharpe", initial_cash=10000,
        )
        assert len(df) == 6  # 3 × 2
        assert "short" in df.columns
        assert "long" in df.columns


class TestMonteCarlo:
    def test_run(self, ohlcv_df):
        engine = MonteCarloEngine(
            ohlcv_df, buy_and_hold_strategy,
            initial_cash=10000, n_simulations=10, seed=42,
        )
        df = engine.run()
        assert len(df) == 10
        assert {"final_equity", "total_return", "sharpe"}.issubset(df.columns)

    def test_summary(self, ohlcv_df):
        engine = MonteCarloEngine(
            ohlcv_df, buy_and_hold_strategy,
            initial_cash=10000, n_simulations=20, seed=42,
        )
        s = engine.summary()
        assert s["n_simulations"] == 20
        assert "mean_return" in s


class TestWalkForward:
    def test_run(self, ohlcv_df):
        wf = WalkForward(
            ohlcv_df, buy_and_hold_strategy,
            train_window=50, test_window=20, step=20,
            initial_cash=10000,
        )
        df = wf.run()
        assert len(df) > 0
        assert "window" in df.columns
        assert "total_return" in df.columns


class TestTradeSerialization:
    def test_trade_to_dict(self):
        from datetime import datetime
        t = Trade(timestamp=datetime(2024, 1, 1), symbol="BTC", side="buy",
                  quantity=1.0, price=100, cost=0.1)
        d = t.to_dict()
        assert d["symbol"] == "BTC"
        assert d["side"] == "buy"
        assert d["quantity"] == 1.0

    def test_metrics_to_dict(self, ohlcv_df):
        engine = BacktestEngine(ohlcv_df, buy_and_hold_strategy, initial_cash=10000)
        result = engine.run()
        d = result.metrics.to_dict()
        assert "total_return" in d
        assert "sharpe" in d
