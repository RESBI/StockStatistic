"""test_storage_backend.py — fetch_ohlcv / ingest / list_symbols / metadata (25 项)。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from stockstat_backend import (
    OrmSession, StorageBackendImpl, create_engine_from_url,
)
from stockstat_backend.models import Base


@pytest.fixture
def backend(tmp_path):
    """创建一个内存 SQLite backend。"""
    db_path = tmp_path / "test.db"
    engine = create_engine_from_url(f"sqlite:///{db_path}")
    orm = OrmSession(engine)
    orm.create_all()
    return StorageBackendImpl(orm)


def _make_df(n=10, start="2024-01-01"):
    ts = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({
        "timestamp": ts,
        "open": range(n), "high": range(1, n + 1),
        "low": range(n), "close": range(2, n + 2),
        "volume": range(100, 100 + n),
    })


class TestIngestFetch:
    def test_ingest_dataframe(self, backend):
        df = _make_df(10)
        rows = backend.ingest_ohlcv("BTC/USDT", "1d", df)
        assert rows == 10

    def test_fetch_single_symbol(self, backend):
        df = _make_df(10)
        backend.ingest_ohlcv("BTC/USDT", "1d", df)
        result = backend.fetch_ohlcv(["BTC/USDT"], "1d")
        assert len(result) == 10
        assert "symbol" not in result.columns
        assert list(result["close"]) == list(range(2, 12))

    def test_fetch_with_string_symbol(self, backend):
        df = _make_df(5)
        backend.ingest_ohlcv("ETH/USDT", "1d", df)
        result = backend.fetch_ohlcv("ETH/USDT", "1d")
        assert len(result) == 5

    def test_fetch_empty(self, backend):
        result = backend.fetch_ohlcv(["NOTEXIST"], "1d")
        assert len(result) == 0

    def test_fetch_empty_multi_symbol(self, backend):
        result = backend.fetch_ohlcv(["A", "B"], "1d")
        assert isinstance(result, dict)
        assert set(result.keys()) == {"A", "B"}

    def test_fetch_multi_symbol_returns_dict(self, backend):
        backend.ingest_ohlcv("BTC", "1d", _make_df(5))
        backend.ingest_ohlcv("ETH", "1d", _make_df(3))
        result = backend.fetch_ohlcv(["BTC", "ETH"], "1d")
        assert isinstance(result, dict)
        assert len(result["BTC"]) == 5
        assert len(result["ETH"]) == 3

    def test_fetch_with_date_range(self, backend):
        df = _make_df(30, start="2024-01-01")
        backend.ingest_ohlcv("BTC", "1d", df)
        result = backend.fetch_ohlcv(["BTC"], "1d",
                                     start="2024-01-10", end="2024-01-20")
        assert 8 <= len(result) <= 11

    def test_ingest_upsert_no_duplicate(self, backend):
        df1 = _make_df(5, start="2024-01-01")
        df2 = _make_df(5, start="2024-01-01")  # 相同 timestamp
        # 第二次写入应该 merge 而不是新增
        backend.ingest_ohlcv("BTC", "1d", df1)
        backend.ingest_ohlcv("BTC", "1d", df2)
        result = backend.fetch_ohlcv(["BTC"], "1d")
        assert len(result) == 5  # 不重复

    def test_ingest_list_of_dicts(self, backend):
        records = [
            {"timestamp": datetime(2024, 1, 1), "open": 100, "high": 110,
             "low": 95, "close": 105, "volume": 1000},
            {"timestamp": datetime(2024, 1, 2), "open": 105, "high": 115,
             "low": 100, "close": 110, "volume": 1200},
        ]
        rows = backend.ingest_ohlcv("BTC", "1d", records)
        assert rows == 2
        result = backend.fetch_ohlcv(["BTC"], "1d")
        assert len(result) == 2

    def test_ingest_empty_dataframe(self, backend):
        empty = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        rows = backend.ingest_ohlcv("BTC", "1d", empty)
        assert rows == 0

    def test_ingest_different_timeframes(self, backend):
        backend.ingest_ohlcv("BTC", "1d", _make_df(5))
        backend.ingest_ohlcv("BTC", "1h", _make_df(24))
        assert len(backend.fetch_ohlcv(["BTC"], "1d")) == 5
        assert len(backend.fetch_ohlcv(["BTC"], "1h")) == 24


class TestListSymbols:
    def test_empty(self, backend):
        assert backend.list_symbols() == []

    def test_after_ingest(self, backend):
        backend.ingest_ohlcv("BTC", "1d", _make_df(3))
        backend.ingest_ohlcv("ETH", "1d", _make_df(3))
        syms = set(backend.list_symbols())
        assert "BTC" in syms
        assert "ETH" in syms

    def test_with_metadata(self, backend):
        backend.upsert_metadata("BTC", name="Bitcoin")
        syms = backend.list_symbols()
        assert "BTC" in syms


class TestMetadata:
    def test_get_metadata_nonexistent(self, backend):
        assert backend.get_metadata("NOTEXIST") == {}

    def test_upsert_metadata(self, backend):
        backend.upsert_metadata("BTC", name="Bitcoin", exchange="binance",
                                asset_class="crypto", metadata={"rank": 1})
        meta = backend.get_metadata("BTC")
        assert meta["name"] == "Bitcoin"
        assert meta["exchange"] == "binance"
        assert meta["asset_class"] == "crypto"
        assert meta["metadata"]["rank"] == 1

    def test_upsert_metadata_updates(self, backend):
        backend.upsert_metadata("BTC", name="Bitcoin")
        backend.upsert_metadata("BTC", name="BTC")  # update
        meta = backend.get_metadata("BTC")
        assert meta["name"] == "BTC"

    def test_metadata_inferred_from_ohlcv(self, backend):
        backend.ingest_ohlcv("ETH", "1d", _make_df(5, start="2024-01-01"))
        meta = backend.get_metadata("ETH")
        assert meta["symbol"] == "ETH"
        assert meta["first_seen"] is not None


class TestStats:
    def test_empty_stats(self, backend):
        s = backend.stats()
        assert s["total_rows"] == 0
        assert s["symbol_count"] == 0

    def test_stats_after_ingest(self, backend):
        backend.ingest_ohlcv("BTC", "1d", _make_df(10))
        backend.ingest_ohlcv("ETH", "1d", _make_df(5))
        s = backend.stats()
        assert s["total_rows"] == 15
        assert s["symbol_count"] == 2


class TestProtocolConformance:
    def test_implements_storage_backend_protocol(self, backend):
        from stockstat_foundation import StorageBackend
        assert isinstance(backend, StorageBackend)

    def test_name_attribute(self, backend):
        assert backend.name == "sqlalchemy"
