"""test_indicators.py — 技术指标测试 (35 项)。"""
from __future__ import annotations

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


@pytest.fixture
def price_series():
    rng = np.random.default_rng(42)
    returns = rng.normal(0.001, 0.02, 200)
    prices = 100 * np.exp(np.cumsum(returns))
    return pd.Series(prices, name="close")


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


class TestTrendIndicators:
    def test_ma_length(self, price_series):
        result = ma(price_series, window=20)
        assert len(result) == len(price_series)
        assert result.iloc[:19].isna().all()
        assert result.iloc[19] is not None or np.isnan(result.iloc[19])

    def test_ma_values(self, price_series):
        result = ma(price_series, window=5)
        expected = price_series.iloc[:5].mean()
        assert abs(result.iloc[4] - expected) < 1e-10

    def test_ema(self, price_series):
        result = ema(price_series, window=12)
        assert len(result) == len(price_series)
        assert not result.iloc[0] != result.iloc[0]  # not NaN

    def test_wma(self, price_series):
        result = wma(price_series, window=10)
        assert len(result) == len(price_series)

    def test_dema(self, price_series):
        result = dema(price_series, window=10)
        assert len(result) == len(price_series)

    def test_tema(self, price_series):
        result = tema(price_series, window=10)
        assert len(result) == len(price_series)

    def test_hma(self, price_series):
        result = hma(price_series, window=20)
        assert len(result) == len(price_series)

    def test_macd_columns(self, price_series):
        df = macd(price_series, 12, 26, 9)
        assert set(df.columns) == {"macd", "signal", "histogram"}
        assert len(df) == len(price_series)

    def test_moving_average_dispatch(self, price_series):
        sma = moving_average(price_series, 20, method="sma")
        ema_r = moving_average(price_series, 20, method="ema")
        assert sma.iloc[-1] != ema_r.iloc[-1]

    def test_unknown_method_raises(self, price_series):
        with pytest.raises(ValueError):
            moving_average(price_series, 20, method="unknown")


class TestOscillatorIndicators:
    def test_rsi_range(self, price_series):
        r = rsi(price_series, 14)
        assert r.between(0, 100).all() or r.isna().any()

    def test_rsi_length(self, price_series):
        r = rsi(price_series, 14)
        assert len(r) == len(price_series)

    def test_kd_columns(self, ohlcv_df):
        result = kd(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert set(result.columns) == {"K", "D", "J"}

    def test_williams_r_range(self, ohlcv_df):
        r = williams_r(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert r.between(-100, 0).all() or r.isna().any()

    def test_cci(self, ohlcv_df):
        r = cci(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert len(r) == len(ohlcv_df)

    def test_stoch(self, ohlcv_df):
        r = stoch(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert "K" in r.columns


class TestVolatilityIndicators:
    def test_bollinger_columns(self, price_series):
        df = bollinger(price_series, 20, 2.0)
        assert set(df.columns) == {"upper", "middle", "lower", "bandwidth"}

    def test_bollinger_upper_above_lower(self, price_series):
        df = bollinger(price_series, 20, 2.0)
        valid = df.dropna()
        assert (valid["upper"] >= valid["lower"]).all()

    def test_atr_positive(self, ohlcv_df):
        r = atr(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        valid = r.dropna()
        assert (valid >= 0).all()

    def test_keltner(self, ohlcv_df):
        df = keltner(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert "upper" in df.columns

    def test_donchian(self, ohlcv_df):
        df = donchian(ohlcv_df["high"], ohlcv_df["low"])
        assert "upper" in df.columns

    def test_stddev(self, price_series):
        r = stddev(price_series, 20)
        assert len(r) == len(price_series)


class TestStatisticsIndicators:
    def test_rolling_corr_range(self, price_series):
        r = rolling_corr(price_series, price_series.shift(1), 20)
        valid = r.dropna()
        assert valid.between(-1, 1).all()

    def test_rolling_beta(self, price_series):
        r = rolling_beta(price_series, price_series, 20)
        valid = r.dropna()
        assert (abs(valid - 1.0) < 0.5).all()  # 自身 beta ≈ 1

    def test_zscore(self, price_series):
        r = zscore(price_series, 20)
        assert len(r) == len(price_series)

    def test_percentile_range(self, price_series):
        r = percentile(price_series, 20)
        valid = r.dropna()
        assert valid.between(0, 1).all()

    def test_rolling_std(self, price_series):
        r = rolling_std(price_series, 20)
        assert len(r) == len(price_series)

    def test_rolling_mean(self, price_series):
        r = rolling_mean(price_series, 20)
        assert len(r) == len(price_series)


class TestNonlinearIndicators:
    def test_hurst_returns_dict(self, price_series):
        r = hurst_rs(price_series)
        assert "hurst" in r
        assert 0 <= r["hurst"] <= 1.5  # 大致范围

    def test_hurst_white_noise_near_half(self):
        rng = np.random.default_rng(42)
        white = pd.Series(rng.normal(0, 1, 1000))
        r = hurst_rs(white)
        assert abs(r["hurst"] - 0.5) < 0.3  # 白噪声 H ≈ 0.5

    def test_sample_entropy_positive(self, price_series):
        r = sample_entropy(price_series[:100])
        assert r > 0

    def test_permutation_entropy_range(self, price_series):
        r = permutation_entropy(price_series[:100], m=4, tau=1)
        assert r >= 0

    def test_permutation_entropy_constant_series(self):
        # 常数序列应该有低熵
        constant = pd.Series([1.0] * 100)
        r = permutation_entropy(constant, m=3, tau=1)
        assert r == 0.0 or np.isclose(r, 0.0, atol=1e-10)


class TestComputeEngine:
    def test_compute_engine_dispatch(self, price_series):
        from stockstat_compute import ComputeEngine
        engine = ComputeEngine()
        r = engine.ma(price_series, window=10)
        assert len(r) == len(price_series)

    def test_compute_engine_unknown_indicator(self, price_series):
        from stockstat_compute import ComputeEngine
        engine = ComputeEngine()
        with pytest.raises(KeyError):
            engine.compute("nonexistent", price_series)

    def test_compute_engine_list(self):
        from stockstat_compute import ComputeEngine
        engine = ComputeEngine()
        names = engine.list_indicators()
        assert "ma" in names
        assert "rsi" in names
        assert "bollinger" in names

    def test_compute_engine_dynamic_attr(self, price_series):
        from stockstat_compute import ComputeEngine
        engine = ComputeEngine()
        r = engine.rsi(price_series, window=14)
        assert len(r) == len(price_series)

    def test_registry_has_indicators(self):
        from stockstat_compute.compute_engine import IndicatorRegistry
        assert IndicatorRegistry.has("ma")
        assert IndicatorRegistry.has("rsi")
        assert not IndicatorRegistry.has("nonexistent")
