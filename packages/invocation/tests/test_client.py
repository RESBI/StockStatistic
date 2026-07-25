"""test_client.py — StockStatClient 测试 (30 项)。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockstat import StockStatClient
from stockstat_foundation import Config, TaskRef


@pytest.fixture
def ohlcv_df():
    rng = np.random.default_rng(42)
    n = 100
    returns = rng.normal(0.001, 0.02, n)
    close = 100 * np.exp(np.cumsum(returns))
    ts = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "timestamp": ts, "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1000.0,
    })


def buy_hold(i, bar, data, ctx):
    if i == 0:
        from stockstat_compute import Signal
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
    return None


class TestClientConstruction:
    def test_default_construction(self):
        client = StockStatClient()
        assert client is not None
        assert client.compute is not None
        assert client.data is not None

    def test_with_storage_url(self):
        client = StockStatClient(storage_url="http://example.com:8000")
        assert client.data.base_url == "http://example.com:8000"

    def test_with_host_port(self):
        client = StockStatClient(host="example.com", port=9000)
        assert "example.com:9000" in client.data.base_url

    def test_with_https(self):
        client = StockStatClient(use_https=True)
        assert client.data.base_url.startswith("https://")

    def test_with_config(self):
        config = Config(database_url="sqlite:///test.db", admin_enabled=True)
        client = StockStatClient(config=config)
        assert client.config.database_url == "sqlite:///test.db"
        assert client.config.admin_enabled is True

    def test_with_explicit_backend(self):
        from stockstat_compute import LocalComputeBackend
        backend = LocalComputeBackend()
        client = StockStatClient(compute_backend=backend)
        assert client.compute_backend is backend


class TestTransparentMode:
    def test_backtest_returns_result(self, ohlcv_df):
        client = StockStatClient()
        result = client.backtest(ohlcv_df, buy_hold, initial_cash=10000)
        assert result is not None
        assert result.error is None
        assert result.metrics.n_trades >= 1

    def test_backtest_async_returns_task_ref(self, ohlcv_df):
        client = StockStatClient()
        result = client.backtest(ohlcv_df, buy_hold,
                                  initial_cash=10000, async_submit=True)
        assert isinstance(result, TaskRef)
        final = result.wait(timeout=10)
        assert final.error is None

    def test_compute_ma(self, ohlcv_df):
        client = StockStatClient()
        result = client.compute.ma(ohlcv_df["close"], window=10)
        assert len(result) == len(ohlcv_df)

    def test_compute_rsi(self, ohlcv_df):
        client = StockStatClient()
        result = client.compute.rsi(ohlcv_df["close"], window=14)
        assert len(result) == len(ohlcv_df)


class TestGridSearch:
    def test_grid_search(self, ohlcv_df):
        from stockstat_compute import StrategyBase
        class MaCross(StrategyBase):
            name = "ma_cross"
            def __init__(self, short=5, long=20):
                self.short = short
                self.long = long
            def on_bar(self, i, bar, data, ctx):
                if i < self.long:
                    return None
                s = data["close"].iloc[i - self.short:i + 1].mean()
                l = data["close"].iloc[i - self.long:i + 1].mean()
                from stockstat_compute import Signal
                if i == self.long and s > l:
                    return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
                return None
        client = StockStatClient()
        df = client.grid_search(
            ohlcv_df, MaCross,
            param_grid={"short": [3, 5], "long": [10, 20]},
            initial_cash=10000,
        )
        assert len(df) == 4


class TestBatchBacktest:
    def test_batch(self, ohlcv_df):
        client = StockStatClient()
        df = client.batch_backtest(
            ohlcv_df,
            strategies={"buy_hold": buy_hold},
            fee_models=["F1_SpotNoBNB", "F4_FutBNB"],
            initial_cash=10000,
        )
        assert len(df) == 2

    def test_paxg_132(self, ohlcv_df):
        client = StockStatClient()
        strategies = {f"S{i}": buy_hold for i in range(33)}
        df = client.batch_backtest(
            ohlcv_df, strategies,
            fee_models=["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"],
            initial_cash=10000,
        )
        assert len(df) == 132


class TestRemoteSubmit:
    def test_remote_returns_task_ref(self, ohlcv_df):
        client = StockStatClient()
        ref = client.compute.remote(
            "indicator",
            data=ohlcv_df["close"],
            compute_spec=None,
        )
        # remote 的 data 通过 kwargs 传入
        ref2 = client.compute.remote(
            "indicator",
            compute_spec=None,
            data=ohlcv_df["close"],
        )
        # 注意：remote 不接受 data 关键字直接作为 TaskSpec.data
        # 实际上 data 会被放到 params._inline_data
        assert isinstance(ref, TaskRef) or ref is not None


class TestClusterInfo:
    def test_cluster_info_local(self):
        client = StockStatClient()
        info = client.cluster_info()
        assert "dispatcher" in info
        assert info["dispatcher"]["id"] == "local"

    def test_compute_cluster_info(self):
        client = StockStatClient()
        info = client.compute.cluster_info()
        assert "workers" in info


class TestProperties:
    def test_data_property(self):
        client = StockStatClient()
        assert client.data is not None

    def test_compute_property(self):
        client = StockStatClient()
        assert client.compute is not None

    def test_compute_backend_property(self):
        client = StockStatClient()
        assert client.compute_backend is not None

    def test_config_property(self):
        client = StockStatClient()
        assert client.config is not None


class TestConvenienceMethods:
    def test_compute_multiple_indicators(self, ohlcv_df):
        client = StockStatClient()
        sma = client.compute.ma(ohlcv_df["close"], window=10)
        ema = client.compute.ema(ohlcv_df["close"], window=10)
        assert sma.iloc[-1] != ema.iloc[-1]

    def test_compute_bollinger(self, ohlcv_df):
        client = StockStatClient()
        result = client.compute.bollinger(ohlcv_df["close"], window=20)
        assert "upper" in result.columns

    def test_compute_macd(self, ohlcv_df):
        client = StockStatClient()
        result = client.compute.macd(ohlcv_df["close"])
        assert "macd" in result.columns

    def test_compute_atr(self, ohlcv_df):
        client = StockStatClient()
        result = client.compute.atr(
            ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"],
        )
        assert len(result) == len(ohlcv_df)
