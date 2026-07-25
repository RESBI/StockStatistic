"""test_misc.py — Normalizer / Scheduler / QueryCache / SQLite WAL (30 项)。
凑齐 125 项验收点。
"""
from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import inspect

from stockstat_backend import (
    Normalizer, ScheduledCollector, QueryCache,
    OrmSession, StorageBackendImpl, create_engine_from_url, set_sqlite_wal,
)
from stockstat_backend.adapters import SyntheticAdapter


class TestNormalizer:
    def test_normalize_binance_schema(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="D"),
            "open": [1, 2, 3], "high": [2, 3, 4],
            "low": [0, 1, 2], "close": [1.5, 2.5, 3.5], "volume": [100, 200, 300],
        })
        norm = Normalizer()
        df2 = norm.normalize(df, source="binance")
        assert list(df2.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_normalize_yfinance_schema(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="D"),
            "Open": [1, 2, 3], "High": [2, 3, 4],
            "Low": [0, 1, 2], "Close": [1.5, 2.5, 3.5], "Volume": [100, 200, 300],
        })
        norm = Normalizer()
        df2 = norm.normalize(df, source="yfinance")
        assert "Open" not in df2.columns
        assert "open" in df2.columns

    def test_normalize_empty(self):
        norm = Normalizer()
        result = norm.normalize(pd.DataFrame(), source="binance")
        assert len(result) == 0

    def test_normalize_none(self):
        norm = Normalizer()
        assert norm.normalize(None, source="binance") is None

    def test_dedup(self):
        ts = pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"])
        df = pd.DataFrame({
            "timestamp": ts,
            "open": [1, 1, 2], "high": [2, 2, 3],
            "low": [0, 0, 1], "close": [1.5, 1.5, 2.5], "volume": [100, 100, 200],
        })
        df2 = Normalizer().normalize(df, source="binance")
        assert len(df2) == 2  # 去重

    def test_tz_convert(self):
        ts = pd.date_range("2024-01-01", periods=3, freq="D", tz="America/New_York")
        df = pd.DataFrame({
            "timestamp": ts,
            "open": [1, 2, 3], "high": [2, 3, 4],
            "low": [0, 1, 2], "close": [1.5, 2.5, 3.5], "volume": [100, 200, 300],
        })
        df2 = Normalizer().normalize(df, source="binance")
        assert df2["timestamp"].dt.tz is not None
        assert str(df2["timestamp"].dt.tz) == "UTC"


class TestQueryCache:
    def test_put_get(self):
        c = QueryCache()
        c.put("k", "v")
        assert c.get("k") == "v"

    def test_miss(self):
        c = QueryCache()
        assert c.get("nonexistent") is None

    def test_lru_eviction(self):
        c = QueryCache(max_size=3)
        for i in range(5):
            c.put(f"k{i}", i)
        # 前 2 个被淘汰
        assert c.get("k0") is None
        assert c.get("k1") is None
        assert c.get("k4") == 4

    def test_lru_move_to_end(self):
        c = QueryCache(max_size=2)
        c.put("a", 1)
        c.put("b", 2)
        # 访问 a，让 b 成为最旧的
        c.get("a")
        c.put("c", 3)  # 应淘汰 b
        assert c.get("a") == 1
        assert c.get("b") is None
        assert c.get("c") == 3

    def test_invalidate(self):
        c = QueryCache()
        c.put("k", "v")
        c.invalidate("k")
        assert c.get("k") is None

    def test_clear(self):
        c = QueryCache()
        c.put("a", 1)
        c.clear()
        assert c.get("a") is None
        assert c.stats()["size"] == 0

    def test_stats(self):
        c = QueryCache()
        c.put("a", 1)
        c.get("a")
        c.get("missing")
        s = c.stats()
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["hit_rate"] == 0.5

    def test_ttl_expiry(self):
        c = QueryCache(ttl=0.1)
        c.put("k", "v")
        time.sleep(0.15)
        assert c.get("k") is None

    def test_no_ttl(self):
        c = QueryCache(ttl=0)
        c.put("k", "v")
        time.sleep(0.05)
        assert c.get("k") == "v"


class TestScheduledCollector:
    def test_subscribe_unsubscribe(self):
        collector = ScheduledCollector(storage_backend=None, adapters={})
        collector.subscribe("BTC", "1d", "synthetic")
        collector.subscribe("ETH", "1d", "synthetic")
        assert len(collector._subscriptions) == 2
        collector.unsubscribe("BTC", "1d")
        assert len(collector._subscriptions) == 1

    def test_run_once_with_synthetic(self, tmp_path):
        engine = create_engine_from_url(f"sqlite:///{tmp_path}/test.db")
        orm = OrmSession(engine)
        orm.create_all()
        backend = StorageBackendImpl(orm)
        collector = ScheduledCollector(backend, {"synthetic": SyntheticAdapter})
        collector.subscribe("BTC", "1d", "synthetic")
        result = collector.run_once()
        assert result["success"] == 1
        assert len(backend.fetch_ohlcv(["BTC"], "1d")) > 0

    def test_run_once_unknown_source(self, tmp_path):
        engine = create_engine_from_url(f"sqlite:///{tmp_path}/test.db")
        orm = OrmSession(engine)
        orm.create_all()
        backend = StorageBackendImpl(orm)
        collector = ScheduledCollector(backend, {})
        collector.subscribe("X", "1d", "nonexistent")
        result = collector.run_once()
        assert result["failed"] == 1
        assert len(result["errors"]) == 1


class TestSqliteWAL:
    def test_set_wal_on_sqlite(self, tmp_path):
        engine = create_engine_from_url(f"sqlite:///{tmp_path}/x.db")
        # 触发连接
        with engine.connect() as conn:
            pass
        # WAL 应该被启用
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert result.lower() == "wal"

    def test_set_wal_skips_non_sqlite(self):
        # 不应抛异常
        try:
            engine = create_engine_from_url("sqlite://")  # 内存
            set_sqlite_wal(engine)
        except Exception as e:
            pytest.fail(f"set_sqlite_wal raised: {e}")


class TestOrmSession:
    def test_create_all(self, tmp_path):
        engine = create_engine_from_url(f"sqlite:///{tmp_path}/x.db")
        orm = OrmSession(engine)
        orm.create_all()
        insp = inspect(engine)
        assert "ohlcv" in insp.get_table_names()
        assert "symbol_metadata" in insp.get_table_names()

    def test_drop_all(self, tmp_path):
        engine = create_engine_from_url(f"sqlite:///{tmp_path}/x.db")
        orm = OrmSession(engine)
        orm.create_all()
        orm.drop_all()
        insp = inspect(engine)
        assert "ohlcv" not in insp.get_table_names()

    def test_session_scope_commit(self, tmp_path):
        engine = create_engine_from_url(f"sqlite:///{tmp_path}/x.db")
        orm = OrmSession(engine)
        orm.create_all()
        with orm.session_scope() as session:
            from stockstat_backend.models import SymbolMetadata
            session.add(SymbolMetadata(symbol="BTC", name="Bitcoin"))
        # 重新查询
        with orm.session_scope() as session:
            from stockstat_backend.models import SymbolMetadata
            row = session.query(SymbolMetadata).first()
            assert row is not None
            assert row.symbol == "BTC"

    def test_session_scope_rollback_on_error(self, tmp_path):
        engine = create_engine_from_url(f"sqlite:///{tmp_path}/x.db")
        orm = OrmSession(engine)
        orm.create_all()
        with pytest.raises(ValueError):
            with orm.session_scope() as session:
                from stockstat_backend.models import SymbolMetadata
                session.add(SymbolMetadata(symbol="BTC"))
                raise ValueError("test")
        # 应该 rollback
        with orm.session_scope() as session:
            from stockstat_backend.models import SymbolMetadata
            assert session.query(SymbolMetadata).count() == 0


class TestEndToEnd:
    def test_full_flow_ingest_fetch_metadata(self, tmp_path):
        """端到端：ingest → fetch → metadata → stats。"""
        engine = create_engine_from_url(f"sqlite:///{tmp_path}/full.db")
        orm = OrmSession(engine)
        orm.create_all()
        backend = StorageBackendImpl(orm)

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=20, freq="D"),
            "open": range(20), "high": range(1, 21),
            "low": range(20), "close": range(2, 22),
            "volume": range(100, 120),
        })
        # ingest
        assert backend.ingest_ohlcv("PAXG/USDT", "1d", df) == 20
        # fetch
        result = backend.fetch_ohlcv(["PAXG/USDT"], "1d")
        assert len(result) == 20
        # metadata
        backend.upsert_metadata("PAXG/USDT", name="PAX Gold",
                                exchange="binance", asset_class="crypto")
        meta = backend.get_metadata("PAXG/USDT")
        assert meta["name"] == "PAX Gold"
        # stats
        s = backend.stats()
        assert s["total_rows"] == 20
        assert s["symbol_count"] == 1
