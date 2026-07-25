"""test_adapters.py — Binance / YFinance / Synthetic 适配器 (15 项)。"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from stockstat_backend import (
    BinanceAdapter, YFinanceAdapter, SyntheticAdapter,
    get_adapter, list_adapters, ADAPTERS,
)


class TestAdapterRegistry:
    def test_list_adapters_includes_builtin(self):
        names = set(list_adapters())
        assert "binance" in names
        assert "yfinance" in names
        assert "synthetic" in names

    def test_get_adapter(self):
        assert get_adapter("synthetic") is SyntheticAdapter
        assert get_adapter("binance") is BinanceAdapter

    def test_get_unknown_adapter(self):
        with pytest.raises(KeyError):
            get_adapter("nonexistent")


class TestSyntheticAdapter:
    def test_fetch_returns_dataframe(self):
        adapter = SyntheticAdapter(seed=42)
        df = adapter.fetch_ohlcv("TEST", "1d")
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_fetch_with_date_range(self):
        adapter = SyntheticAdapter(seed=42)
        df = adapter.fetch_ohlcv("TEST", "1d",
                                 start="2024-01-01", end="2024-01-31")
        assert len(df) == 31

    def test_columns(self):
        df = SyntheticAdapter().fetch_ohlcv("X", "1d")
        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            assert col in df.columns

    def test_reproducible(self):
        df1 = SyntheticAdapter(seed=42).fetch_ohlcv("X", "1d", "2024-01-01", "2024-01-10")
        df2 = SyntheticAdapter(seed=42).fetch_ohlcv("X", "1d", "2024-01-01", "2024-01-10")
        pd.testing.assert_frame_equal(df1, df2)

    def test_different_seed_differs(self):
        df1 = SyntheticAdapter(seed=1).fetch_ohlcv("X", "1d", "2024-01-01", "2024-01-10")
        df2 = SyntheticAdapter(seed=2).fetch_ohlcv("X", "1d", "2024-01-01", "2024-01-10")
        assert not df1.equals(df2)


class TestBinanceAdapter:
    def test_construction(self):
        adapter = BinanceAdapter()
        assert adapter.name == "binance"
        assert "binance.com" in adapter._base_url

    def test_testnet_construction(self):
        adapter = BinanceAdapter(testnet=True)
        assert "testnet" in adapter._base_url

    def test_fetch_with_mock(self):
        adapter = BinanceAdapter()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            [1700000000000, "100", "110", "95", "105", "1000",
             1700001000000, "105000", 50, "500", "52500", "0"],
        ]
        mock_response.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_response):
            df = adapter.fetch_ohlcv("BTCUSDT", "1d")
        assert len(df) == 1
        assert df["close"].iloc[0] == 105.0
        assert isinstance(df["timestamp"].iloc[0], pd.Timestamp)


class TestYFinanceAdapter:
    def test_construction(self):
        adapter = YFinanceAdapter()
        assert adapter.name == "yfinance"

    def test_fetch_without_yfinance_raises(self):
        adapter = YFinanceAdapter()
        # 如果 yfinance 已安装，跳过；否则应抛 ImportError
        try:
            import yfinance  # noqa: F401
            pytest.skip("yfinance installed")
        except ImportError:
            with pytest.raises(ImportError, match="yfinance"):
                adapter.fetch_ohlcv("AAPL", "1d")


class TestProtocolConformance:
    def test_synthetic_is_data_source(self):
        from stockstat_backend import DataSource
        assert isinstance(SyntheticAdapter(), DataSource)

    def test_binance_is_data_source(self):
        from stockstat_backend import DataSource
        assert isinstance(BinanceAdapter(), DataSource)
