"""test_demo_indicators.py — 指标计算演示测试（含图表生成）。

覆盖：趋势/振荡/波动/统计/非线性 5 大类 40+ 指标。
图表输出：docs/images/indicators_bollinger.png / indicators_rsi.png / indicators_macd.png
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

from stockstat_compute.indicators import (
    ma, ema, wma, dema, tema, hma, macd, adx, dpo, trix, moving_average,
    rsi, kd, williams_r, cci, stoch,
    bollinger, atr, keltner, donchian, stddev,
    rolling_corr, rolling_beta, zscore, percentile, rolling_std, rolling_mean,
    hurst_rs, sample_entropy, permutation_entropy,
)
from stockstat_compute import ComputeEngine

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(_ROOT, "docs", "images")
os.makedirs(IMG_DIR, exist_ok=True)


@pytest.fixture
def ohlcv():
    rng = np.random.default_rng(42)
    n = 300
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


class TestTrendIndicators:
    """趋势指标：MA / EMA / WMA / DEMA / TEMA / HMA / MACD / ADX / DPO / TRIX。"""

    def test_ma(self, ohlcv):
        result = ma(ohlcv["close"], window=20)
        assert len(result) == len(ohlcv)
        assert result.iloc[:19].isna().all()

    def test_ema(self, ohlcv):
        result = ema(ohlcv["close"], window=12)
        assert len(result) == len(ohlcv)

    def test_wma(self, ohlcv):
        result = wma(ohlcv["close"], window=20)
        assert len(result) == len(ohlcv)

    def test_dema(self, ohlcv):
        result = dema(ohlcv["close"], window=20)
        assert len(result) == len(ohlcv)

    def test_tema(self, ohlcv):
        result = tema(ohlcv["close"], window=20)
        assert len(result) == len(ohlcv)

    def test_hma(self, ohlcv):
        result = hma(ohlcv["close"], window=20)
        assert len(result) == len(ohlcv)

    def test_macd(self, ohlcv):
        result = macd(ohlcv["close"], 12, 26, 9)
        assert set(result.columns) == {"macd", "signal", "histogram"}

    def test_adx(self, ohlcv):
        result = adx(ohlcv["high"], ohlcv["low"], ohlcv["close"], window=14)
        assert len(result) == len(ohlcv)

    def test_dpo(self, ohlcv):
        result = dpo(ohlcv["close"], window=20)
        assert len(result) == len(ohlcv)

    def test_trix(self, ohlcv):
        result = trix(ohlcv["close"], window=12)
        assert len(result) == len(ohlcv)

    def test_moving_average_dispatch(self, ohlcv):
        for method in ["sma", "ema", "wma", "dema", "tema", "hma"]:
            r = moving_average(ohlcv["close"], 20, method=method)
            assert len(r) == len(ohlcv)


class TestOscillatorIndicators:
    """振荡指标：RSI / KD / Williams%R / CCI / Stoch。"""

    def test_rsi(self, ohlcv):
        r = rsi(ohlcv["close"], 14)
        assert len(r) == len(ohlcv)
        valid = r.dropna()
        assert valid.between(0, 100).all()

    def test_kd(self, ohlcv):
        result = kd(ohlcv["high"], ohlcv["low"], ohlcv["close"])
        assert set(result.columns) == {"K", "D", "J"}

    def test_williams_r(self, ohlcv):
        r = williams_r(ohlcv["high"], ohlcv["low"], ohlcv["close"], 14)
        valid = r.dropna()
        assert valid.between(-100, 0).all()

    def test_cci(self, ohlcv):
        r = cci(ohlcv["high"], ohlcv["low"], ohlcv["close"], 20)
        assert len(r) == len(ohlcv)

    def test_stoch(self, ohlcv):
        r = stoch(ohlcv["high"], ohlcv["low"], ohlcv["close"])
        assert "K" in r.columns


class TestVolatilityIndicators:
    """波动率指标：Bollinger / ATR / Keltner / Donchian / StdDev。"""

    def test_bollinger(self, ohlcv):
        result = bollinger(ohlcv["close"], 20, 2.0)
        assert set(result.columns) == {"upper", "middle", "lower", "bandwidth"}
        valid = result.dropna()
        assert (valid["upper"] >= valid["lower"]).all()

    def test_atr(self, ohlcv):
        r = atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], 14)
        valid = r.dropna()
        assert (valid >= 0).all()

    def test_keltner(self, ohlcv):
        result = keltner(ohlcv["high"], ohlcv["low"], ohlcv["close"])
        assert "upper" in result.columns

    def test_donchian(self, ohlcv):
        result = donchian(ohlcv["high"], ohlcv["low"])
        assert "upper" in result.columns

    def test_stddev(self, ohlcv):
        r = stddev(ohlcv["close"], 20)
        assert len(r) == len(ohlcv)


class TestStatisticsIndicators:
    """统计指标：rolling_corr / rolling_beta / zscore / percentile / rolling_std / rolling_mean。"""

    def test_rolling_corr(self, ohlcv):
        r = rolling_corr(ohlcv["close"], ohlcv["close"].shift(1), 20)
        valid = r.dropna()
        assert valid.between(-1, 1).all()

    def test_rolling_beta(self, ohlcv):
        r = rolling_beta(ohlcv["close"], ohlcv["close"], 20)
        valid = r.dropna()
        assert (abs(valid - 1.0) < 0.5).all()

    def test_zscore(self, ohlcv):
        r = zscore(ohlcv["close"], 20)
        assert len(r) == len(ohlcv)

    def test_percentile(self, ohlcv):
        r = percentile(ohlcv["close"], 20)
        valid = r.dropna()
        assert valid.between(0, 1).all()

    def test_rolling_std(self, ohlcv):
        r = rolling_std(ohlcv["close"], 20)
        assert len(r) == len(ohlcv)

    def test_rolling_mean(self, ohlcv):
        r = rolling_mean(ohlcv["close"], 20)
        assert len(r) == len(ohlcv)


class TestNonlinearIndicators:
    """非线性指标：Hurst / 样本熵 / 排列熵。"""

    def test_hurst_rs(self, ohlcv):
        r = hurst_rs(ohlcv["close"].values)
        assert "hurst" in r
        assert 0 <= r["hurst"] <= 1.5

    def test_hurst_white_noise(self):
        rng = np.random.default_rng(42)
        r = hurst_rs(pd.Series(rng.normal(0, 1, 2000)))
        assert abs(r["hurst"] - 0.5) < 0.3

    def test_sample_entropy(self, ohlcv):
        r = sample_entropy(ohlcv["close"].values[:100])
        assert r > 0

    def test_permutation_entropy(self, ohlcv):
        r = permutation_entropy(ohlcv["close"].values[:100], m=4, tau=1)
        assert r >= 0


class TestComputeEngine:
    """ComputeEngine 统一入口。"""

    def test_engine_dispatch(self, ohlcv):
        engine = ComputeEngine()
        r = engine.ma(ohlcv["close"], window=10)
        assert len(r) == len(ohlcv)

    def test_engine_list(self):
        engine = ComputeEngine()
        names = engine.list_indicators()
        assert "ma" in names
        assert "rsi" in names
        assert "bollinger" in names

    def test_engine_dynamic_attr(self, ohlcv):
        engine = ComputeEngine()
        r = engine.rsi(ohlcv["close"], window=14)
        assert len(r) == len(ohlcv)


class TestPlotGeneration:
    """生成演示图表。"""

    def test_plot_bollinger(self, ohlcv):
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(ohlcv["timestamp"], ohlcv["close"], label="Close", color="black", linewidth=0.8)
        ax.plot(ohlcv["timestamp"], ma(ohlcv["close"], 20), label="MA20", color="blue")
        bb = bollinger(ohlcv["close"], 20, 2.0)
        ax.fill_between(ohlcv["timestamp"], bb["upper"], bb["lower"],
                        alpha=0.15, color="green", label="Bollinger Band")
        ax.set_title("Close Price + MA + Bollinger Bands")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "indicators_bollinger.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "indicators_bollinger.png"))

    def test_plot_rsi(self, ohlcv):
        r = rsi(ohlcv["close"], 14)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6),
                                        gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
        ax1.plot(ohlcv["timestamp"], ohlcv["close"], color="black", linewidth=0.8)
        ax2.plot(ohlcv["timestamp"], r, color="purple", linewidth=1)
        ax2.axhline(70, color="red", linestyle="--", linewidth=0.8)
        ax2.axhline(30, color="green", linestyle="--", linewidth=0.8)
        ax2.fill_between(ohlcv["timestamp"], 70, 100, alpha=0.1, color="red")
        ax2.fill_between(ohlcv["timestamp"], 0, 30, alpha=0.1, color="green")
        ax2.set_title("RSI(14)")
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "indicators_rsi.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "indicators_rsi.png"))

    def test_plot_macd(self, ohlcv):
        m = macd(ohlcv["close"], 12, 26, 9)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6),
                                        gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
        ax1.plot(ohlcv["timestamp"], ohlcv["close"], color="black", linewidth=0.8)
        colors = ["red" if h > 0 else "green" for h in m["histogram"]]
        ax2.bar(ohlcv["timestamp"], m["histogram"], color=colors, width=1, alpha=0.6)
        ax2.plot(ohlcv["timestamp"], m["macd"], label="MACD", color="blue", linewidth=1)
        ax2.plot(ohlcv["timestamp"], m["signal"], label="Signal", color="orange", linewidth=1)
        ax2.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "indicators_macd.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "indicators_macd.png"))
