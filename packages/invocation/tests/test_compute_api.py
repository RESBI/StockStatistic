"""test_compute_api.py — ComputeAPI 测试 (40 项)。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockstat import StockStatClient, ComputeAPI
from stockstat_foundation import TaskRef, TaskSpec


@pytest.fixture
def client():
    return StockStatClient()


@pytest.fixture
def price_series():
    rng = np.random.default_rng(42)
    returns = rng.normal(0.001, 0.02, 200)
    return pd.Series(100 * np.exp(np.cumsum(returns)))


@pytest.fixture
def ohlcv_df():
    rng = np.random.default_rng(42)
    n = 100
    returns = rng.normal(0.001, 0.02, n)
    close = 100 * np.exp(np.cumsum(returns))
    return pd.DataFrame({
        "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1000.0,
    })


class TestIndicatorMethods:
    def test_ma(self, client, price_series):
        r = client.compute.ma(price_series, window=20)
        assert len(r) == 200

    def test_ema(self, client, price_series):
        r = client.compute.ema(price_series, window=12)
        assert len(r) == 200

    def test_wma(self, client, price_series):
        r = client.compute.wma(price_series, window=20)
        assert len(r) == 200

    def test_dema(self, client, price_series):
        r = client.compute.dema(price_series, window=20)
        assert len(r) == 200

    def test_tema(self, client, price_series):
        r = client.compute.tema(price_series, window=20)
        assert len(r) == 200

    def test_hma(self, client, price_series):
        r = client.compute.hma(price_series, window=20)
        assert len(r) == 200

    def test_rsi(self, client, price_series):
        r = client.compute.rsi(price_series, window=14)
        assert len(r) == 200

    def test_macd(self, client, price_series):
        r = client.compute.macd(price_series)
        assert "macd" in r.columns

    def test_bollinger(self, client, price_series):
        r = client.compute.bollinger(price_series, window=20, std=2.0)
        assert "upper" in r.columns

    def test_atr(self, client, ohlcv_df):
        r = client.compute.atr(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert len(r) == 100

    def test_adx(self, client, ohlcv_df):
        r = client.compute.adx(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert len(r) == 100

    def test_kd(self, client, ohlcv_df):
        r = client.compute.kd(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert "K" in r.columns

    def test_cci(self, client, ohlcv_df):
        r = client.compute.cci(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert len(r) == 100

    def test_williams_r(self, client, ohlcv_df):
        r = client.compute.williams_r(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert len(r) == 100

    def test_donchian(self, client, ohlcv_df):
        r = client.compute.donchian(ohlcv_df["high"], ohlcv_df["low"])
        assert "upper" in r.columns

    def test_keltner(self, client, ohlcv_df):
        r = client.compute.keltner(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"])
        assert "upper" in r.columns

    def test_stddev(self, client, price_series):
        r = client.compute.stddev(price_series, window=20)
        assert len(r) == 200

    def test_zscore(self, client, price_series):
        r = client.compute.zscore(price_series, window=20)
        assert len(r) == 200

    def test_rolling_corr(self, client, price_series):
        r = client.compute.rolling_corr(price_series, price_series.shift(1), window=20)
        assert len(r) == 200

    def test_rolling_beta(self, client, price_series):
        r = client.compute.rolling_beta(price_series, price_series, window=20)
        assert len(r) == 200

    def test_hurst_rs(self, client, price_series):
        r = client.compute.hurst_rs(price_series)
        assert "hurst" in r

    def test_sample_entropy(self, client, price_series):
        r = client.compute.sample_entropy(price_series[:50])
        assert r > 0

    def test_permutation_entropy(self, client, price_series):
        r = client.compute.permutation_entropy(price_series[:50])
        assert r >= 0


class TestRemoteSubmit:
    def test_remote_indicator(self, client, price_series):
        ref = client.compute.remote(
            "indicator",
            data=price_series,
            compute_spec=None,
        )
        assert ref is not None

    def test_remote_backtest(self, client, ohlcv_df):
        def strat(i, bar, d, ctx):
            return None
        ref = client.compute.remote(
            "backtest",
            data=ohlcv_df,
            compute_spec=None,
        )
        assert ref is not None


class TestStatsConvenience:
    def test_correlation(self, client, price_series):
        # correlation handler 在 P7 实现，这里测试便捷方法存在
        assert hasattr(client.compute, "correlation")

    def test_hypothesis_test(self, client, price_series):
        assert hasattr(client.compute, "hypothesis_test")

    def test_spectral_analysis(self, client, price_series):
        assert hasattr(client.compute, "spectral_analysis")

    def test_transfer_entropy(self, client, price_series):
        assert hasattr(client.compute, "transfer_entropy")

    def test_mutual_information(self, client, price_series):
        assert hasattr(client.compute, "mutual_information")

    def test_hurst_exponent(self, client, price_series):
        assert hasattr(client.compute, "hurst_exponent")


class TestBuildBacktestTaskSpec:
    def test_build_spec(self, client, ohlcv_df):
        def strat(i, bar, d, ctx): return None
        spec = client.compute.build_backtest_task_spec(
            data=ohlcv_df, strategy=strat, initial_cash=5000,
        )
        assert spec.compute_spec.task_type == "backtest"
        assert spec.compute_spec.initial_cash == 5000
        assert spec.compute_spec.strategy_ref.startswith("cloudpickle:")

    def test_build_spec_with_cost_model(self, client, ohlcv_df):
        def strat(i, bar, d, ctx): return None
        spec = client.compute.build_backtest_task_spec(
            data=ohlcv_df, strategy=strat,
            initial_cash=10000, cost_model="F4_FutBNB",
        )
        assert spec.compute_spec.cost_model == "F4_FutBNB"


class TestProtocolConformance:
    def test_compute_backend_protocol(self, client):
        from stockstat_foundation import ComputeBackend
        assert isinstance(client.compute_backend, ComputeBackend)

    def test_compute_api_has_methods(self, client):
        for m in ["ma", "ema", "rsi", "macd", "bollinger",
                  "remote", "cluster_info"]:
            assert hasattr(client.compute, m)
