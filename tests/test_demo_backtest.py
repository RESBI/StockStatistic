"""test_demo_backtest.py — 回测演示测试（含图表生成）。

覆盖：单次回测 / 批量回测 / 网格搜索 / 蒙特卡洛 / 前向验证。
图表输出：docs/images/backtest_equity_drawdown.png / backtest_batch_sharpe.png
"""
from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from stockstat_compute import (
    BacktestEngine, BacktestResult, Signal, StrategyBase,
    batch_backtest, grid_search, MonteCarloEngine, WalkForward,
    FEE_MODELS, get_cost_model, get_fill_model,
)
from stockstat import StockStatClient
from stockstat_foundation import cloudpickle_dumps

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(_ROOT, "docs", "images")


@pytest.fixture
def ohlcv():
    rng = np.random.default_rng(42)
    n = 500
    returns = rng.normal(0.0008, 0.02, n)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    volume = rng.integers(10000, 500000, n).astype(float)
    ts = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "timestamp": ts, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


def buy_hold(i, bar, data, ctx):
    if i == 0:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy", strength=1.0)
    return None


def ma_cross(i, bar, data, ctx, short=5, long=20):
    if i < long:
        return None
    s = data["close"].iloc[i - short:i + 1].mean()
    l = data["close"].iloc[i - long:i + 1].mean()
    ps = data["close"].iloc[i - short - 1:i].mean()
    pl = data["close"].iloc[i - long - 1:i].mean()
    if ps <= pl and s > l:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy", strength=0.9)
    if ps >= pl and s < l:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="sell", strength=0.9)
    return None


class TestBacktestEngine:
    """单次回测。"""

    def test_buy_and_hold(self, ohlcv):
        engine = BacktestEngine(
            data=ohlcv, strategy=buy_hold,
            initial_cash=10000, symbol="TEST", timeframe="1d",
        )
        result = engine.run()
        assert result.error is None
        assert result.metrics.n_trades >= 1
        assert result.final_equity > 0

    def test_ma_cross(self, ohlcv):
        def strat(i, bar, data, ctx):
            return ma_cross(i, bar, data, ctx, 5, 20)
        engine = BacktestEngine(ohlcv, strat, initial_cash=10000)
        result = engine.run()
        assert result.error is None

    def test_with_fee_models(self, ohlcv):
        for fee_name in ["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"]:
            engine = BacktestEngine(
                ohlcv, buy_hold, initial_cash=10000,
                cost_model=fee_name, symbol="TEST",
            )
            result = engine.run()
            assert result.error is None

    def test_equity_curve(self, ohlcv):
        engine = BacktestEngine(ohlcv, buy_hold, initial_cash=10000)
        result = engine.run()
        assert result.equity_curve is not None
        assert len(result.equity_curve) == len(ohlcv)
        assert "equity" in result.equity_curve.columns

    def test_metrics_completeness(self, ohlcv):
        engine = BacktestEngine(ohlcv, buy_hold, initial_cash=10000)
        result = engine.run()
        m = result.metrics
        for field in ["total_return", "sharpe", "max_drawdown", "n_trades",
                       "win_rate", "volatility", "sortino", "calmar"]:
            assert hasattr(m, field)

    def test_result_summary(self, ohlcv):
        engine = BacktestEngine(ohlcv, buy_hold, initial_cash=10000)
        result = engine.run()
        s = result.summary()
        assert "BacktestResult" in s


class TestFeeModels:
    """费率模型。"""

    def test_all_fee_models_exist(self):
        for name in ["default", "zero", "F1_SpotNoBNB", "F2_SpotBNB",
                     "F3_FutNoBNB", "F4_FutBNB", "binance_spot",
                     "binance_futures_bnb", "binance_futures", "stock"]:
            cm = get_cost_model(name)
            assert cm is not None

    def test_fee_ordering(self):
        f1 = get_cost_model("F1_SpotNoBNB")
        f4 = get_cost_model("F4_FutBNB")
        assert f4.fee_rate < f1.fee_rate

    def test_fee_calculation(self):
        cm = get_cost_model("F1_SpotNoBNB")
        fee = cm.calculate(100, 100)
        assert fee == 10.0  # 0.1% * 10000


class TestFillModels:
    """成交模型。"""

    def test_next_open(self, ohlcv):
        fm = get_fill_model("next_open")
        price = fm.get_fill_price(0, ohlcv, "buy")
        assert price == ohlcv.iloc[1]["open"]

    def test_this_close(self, ohlcv):
        fm = get_fill_model("this_close")
        price = fm.get_fill_price(0, ohlcv, "buy")
        assert price == ohlcv.iloc[0]["close"]

    def test_slippage(self, ohlcv):
        from stockstat_compute import FillModel
        fm = FillModel(name="next_open", slippage_bps=10)
        base = ohlcv.iloc[1]["open"]
        assert fm.get_fill_price(0, ohlcv, "buy") > base
        assert fm.get_fill_price(0, ohlcv, "sell") < base


class TestBatchBacktest:
    """批量回测。"""

    def test_basic(self, ohlcv):
        df = batch_backtest(
            ohlcv,
            strategies={"buy_hold": buy_hold, "ma_cross": lambda i, b, d, c: ma_cross(i, b, d, c, 5, 20)},
            fee_models=["F1_SpotNoBNB", "F4_FutBNB"],
            initial_cash=10000,
        )
        assert len(df) == 4  # 2×2

    def test_paxg_132(self, ohlcv):
        """PAXG v5-redo：33 策略 × 4 费率 = 132。"""
        strategies = {f"S{i}": buy_hold for i in range(33)}
        df = batch_backtest(
            ohlcv, strategies,
            fee_models=["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"],
            initial_cash=10000,
        )
        assert len(df) == 132

    def test_via_client(self, ohlcv):
        client = StockStatClient()
        df = client.batch_backtest(
            ohlcv,
            strategies={"buy_hold": buy_hold},
            fee_models=["F1_SpotNoBNB", "F4_FutBNB"],
            initial_cash=10000,
        )
        assert len(df) == 2


class TestGridSearch:
    """参数网格搜索。"""

    def test_basic(self, ohlcv):
        class MaCross(StrategyBase):
            name = "ma_cross"
            def __init__(self, short=5, long=20):
                self.short = short
                self.long = long
            def on_bar(self, i, bar, data, ctx):
                return ma_cross(i, bar, data, ctx, self.short, self.long)

        df = grid_search(
            ohlcv, MaCross,
            param_grid={"short": [3, 5, 8], "long": [10, 20]},
            metric="sharpe", initial_cash=10000,
        )
        assert len(df) == 6  # 3×2
        assert "short" in df.columns


class TestMonteCarlo:
    """蒙特卡洛模拟。"""

    def test_run(self, ohlcv):
        engine = MonteCarloEngine(
            ohlcv, buy_hold, initial_cash=10000, n_simulations=50, seed=42,
        )
        df = engine.run()
        assert len(df) == 50
        assert "final_equity" in df.columns

    def test_summary(self, ohlcv):
        engine = MonteCarloEngine(
            ohlcv, buy_hold, initial_cash=10000, n_simulations=20, seed=42,
        )
        s = engine.summary()
        assert s["n_simulations"] == 20
        assert "mean_return" in s


class TestWalkForward:
    """前向验证。"""

    def test_run(self, ohlcv):
        wf = WalkForward(
            ohlcv, buy_hold, train_window=100, test_window=50, step=50,
            initial_cash=10000,
        )
        df = wf.run()
        assert len(df) > 0
        assert "window" in df.columns


class TestPlotGeneration:
    """生成回测图表。"""

    def test_plot_equity_drawdown(self, ohlcv):
        def strat(i, bar, data, ctx):
            return ma_cross(i, bar, data, ctx, 5, 20)
        engine = BacktestEngine(
            ohlcv, strat, initial_cash=10000,
            cost_model="F1_SpotNoBNB", symbol="TEST", timeframe="1d",
            strategy_name="ma_cross_5_20",
        )
        result = engine.run()
        eq = result.equity_curve

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7),
                                        gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
        ax1.plot(eq.index, eq["equity"], color="blue", linewidth=1.2, label="Equity")
        ax1.axhline(10000, color="gray", linestyle="--", linewidth=0.8, label="Initial Cash")
        ax1.set_title("Backtest Equity Curve (MA Cross 5/20)")
        ax1.set_ylabel("Equity ($)")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax2.fill_between(eq.index, eq["drawdown"] * 100, 0, color="red", alpha=0.4)
        ax2.set_title("Drawdown")
        ax2.set_ylabel("Drawdown (%)")
        ax2.set_xlabel("Date")
        ax2.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "backtest_equity_drawdown.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "backtest_equity_drawdown.png"))

    def test_plot_batch_sharpe(self, ohlcv):
        def strat_sell(i, bar, data, ctx):
            if i == 0:
                return Signal(timestamp=bar["timestamp"], symbol="T", side="sell")
            return None

        def strat_hold(i, bar, data, ctx):
            return None

        client = StockStatClient()
        result = client.batch_backtest(
            ohlcv,
            strategies={"buy_hold": buy_hold, "sell_first": strat_sell, "do_nothing": strat_hold},
            fee_models=["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"],
            initial_cash=10000,
        )
        fig, ax = plt.subplots(figsize=(10, 5))
        pivot = result.pivot(index="strategy", columns="fee_model", values="sharpe")
        pivot.plot(kind="bar", ax=ax, width=0.7)
        ax.set_title("Batch Backtest: 3 Strategies x 4 Fee Models (Sharpe)")
        ax.set_xlabel("Strategy")
        ax.set_ylabel("Sharpe Ratio")
        ax.legend(title="Fee Model")
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "backtest_batch_sharpe.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "backtest_batch_sharpe.png"))
