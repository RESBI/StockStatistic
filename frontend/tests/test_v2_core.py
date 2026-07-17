"""Tests for the v2.0 core layer (Layer 0).

These tests verify the protocol contracts, plugin registry, config,
events, storage, cache, and codec subsystems independently of any
financial-domain logic.
"""
from __future__ import annotations

import os
import time

import pandas as pd
import pytest


# ═══════════════════════════════════════════════════════════════
# Phase 1.1: Contracts
# ═══════════════════════════════════════════════════════════════

class TestContracts:
    """Protocol contracts are importable and runtime-checkable."""

    def test_plugin_protocol_import(self):
        from stockstat._core.contracts import Plugin
        assert Plugin is not None

    def test_storage_protocol_import(self):
        from stockstat._core.contracts import StorageBackend, DataSchema, FieldDef
        assert StorageBackend is not None
        assert DataSchema is not None
        assert FieldDef is not None

    def test_cache_protocol_import(self):
        from stockstat._core.contracts import CacheBackend
        assert CacheBackend is not None

    def test_codec_protocol_import(self):
        from stockstat._core.contracts import Codec
        assert Codec is not None

    def test_renderer_protocol_import(self):
        from stockstat._core.contracts import Renderer
        assert Renderer is not None

    def test_event_protocol_import(self):
        from stockstat._core.contracts import Event, EventSubscriber, EventPublisher
        assert Event is not None
        assert EventSubscriber is not None
        assert EventPublisher is not None

    def test_event_is_frozen_dataclass(self):
        from stockstat._core.contracts import Event
        ev = Event(topic="test", payload={"x": 1}, timestamp=pd.Timestamp("2024-01-01"))
        with pytest.raises(Exception):
            ev.topic = "other"  # frozen

    def test_storage_schema_fields(self):
        from stockstat._core.contracts import DataSchema, FieldDef
        s = DataSchema(
            name="ohlcv",
            fields=[
                FieldDef(name="symbol", dtype="str", nullable=False, primary_key=True),
                FieldDef(name="close", dtype="float"),
            ],
        )
        assert s.field_names() == ["symbol", "close"]
        assert s.fields[0].primary_key is True


# ═══════════════════════════════════════════════════════════════
# Phase 1.2: Plugin Registry
# ═══════════════════════════════════════════════════════════════

class TestPluginRegistry:

    def test_register_and_get(self):
        from stockstat._core.plugin import PluginRegistry
        reg = PluginRegistry()

        class FakePlugin:
            name = "fake"
            version = "1.0"
            category = "test"

        reg.register("indicators", "fake", FakePlugin())
        assert reg.get("indicators", "fake") is not None
        assert reg.get("indicators", "nonexistent") is None

    def test_require_raises_on_missing(self):
        from stockstat._core.plugin import PluginRegistry
        reg = PluginRegistry()
        with pytest.raises(KeyError):
            reg.require("indicators", "nonexistent")

    def test_duplicate_registration_raises(self):
        from stockstat._core.plugin import PluginRegistry
        reg = PluginRegistry()
        reg.register("ns", "p1", object())
        with pytest.raises(ValueError):
            reg.register("ns", "p1", object())

    def test_unregister(self):
        from stockstat._core.plugin import PluginRegistry
        reg = PluginRegistry()
        reg.register("ns", "p1", "plugin_obj")
        removed = reg.unregister("ns", "p1")
        assert removed == "plugin_obj"
        assert reg.get("ns", "p1") is None

    def test_list_by_namespace(self):
        from stockstat._core.plugin import PluginRegistry
        reg = PluginRegistry()
        reg.register("indicators", "ma", object())
        reg.register("indicators", "rsi", object())
        reg.register("sources", "yfinance", object())

        inds = reg.list("indicators")
        assert len(inds) == 2
        assert {x["name"] for x in inds} == {"ma", "rsi"}

    def test_list_all_namespaces(self):
        from stockstat._core.plugin import PluginRegistry
        reg = PluginRegistry()
        reg.register("indicators", "ma", object())
        reg.register("sources", "yfinance", object())
        assert set(reg.namespaces()) == {"indicators", "sources"}

    def test_lifecycle_initialize_shutdown(self):
        from stockstat._core.plugin import PluginRegistry

        class LifecyclePlugin:
            name = "lc"
            version = "1.0"
            category = "test"
            initialized = False
            shut_down = False

            def initialize(self, ctx):
                self.initialized = True

            def shutdown(self):
                self.shut_down = True

            def health_check(self):
                return True

        reg = PluginRegistry()
        p = LifecyclePlugin()
        reg.register("ns", "lc", p)
        assert not p.initialized

        reg.initialize(context=None)
        assert p.initialized

        health = reg.health_check()
        assert health["ns.lc"] is True

        reg.shutdown()
        assert p.shut_down

    def test_late_register_initializes(self):
        from stockstat._core.plugin import PluginRegistry

        class P:
            name = "p"
            version = "1"
            category = "t"
            init_called = False
            def initialize(self, ctx): self.init_called = True
            def shutdown(self): pass
            def health_check(self): return True

        reg = PluginRegistry()
        reg.initialize(context=None)
        p = P()
        reg.register("ns", "p", p)
        assert p.init_called  # initialized on registration


# ═══════════════════════════════════════════════════════════════
# Phase 1.3: Config
# ═══════════════════════════════════════════════════════════════

class TestConfig:

    def test_defaults_loaded(self):
        from stockstat._core.config import load_config
        cfg = load_config()
        assert cfg.backend.database_url == "sqlite:///stockstat.db"
        assert cfg.cache.backend == "memory"
        assert cfg.plot.default_renderer == "matplotlib"

    def test_env_override(self, monkeypatch):
        from stockstat._core.config import load_config
        monkeypatch.setenv("DATABASE_URL", "postgresql://test@db/stockstat")
        monkeypatch.setenv("STOCKSTAT_PROXY_ENABLED", "true")
        monkeypatch.setenv("STOCKSTAT_PORT", "9000")
        cfg = load_config()
        assert cfg.backend.database_url == "postgresql://test@db/stockstat"
        assert cfg.proxy.enabled is True
        assert cfg.frontend.port == 9000

    def test_kwarg_override(self):
        from stockstat._core.config import load_config
        cfg = load_config(backend={"database_url": "memory://test"})
        assert cfg.backend.database_url == "memory://test"

    def test_namespace_access(self):
        from stockstat._core.config import Config
        c = Config({"a": {"b": {"c": 42}}})
        assert c.a.b.c == 42
        assert c["a"]["b"]["c"] == 42

    def test_get_with_default(self):
        from stockstat._core.config import Config
        c = Config({"x": 1})
        assert c.get("x") == 1
        assert c.get("missing", "default") == "default"

    def test_to_dict(self):
        from stockstat._core.config import Config
        d = {"x": 1, "y": {"z": 2}}
        c = Config(d)
        assert c.to_dict() == d


# ═══════════════════════════════════════════════════════════════
# Phase 1.4: Events
# ═══════════════════════════════════════════════════════════════

class TestEventBus:

    def test_publish_subscribe_handler(self):
        from stockstat._core.events import EventBus
        bus = EventBus()
        received = []
        bus.subscribe_handler("data.ohlcv", lambda ev: received.append(ev))

        bus.publish("data.ohlcv", {"close": 100})
        assert len(received) == 1
        assert received[0].payload["close"] == 100

    def test_parent_topic_delivery(self):
        from stockstat._core.events import EventBus
        bus = EventBus()
        received = []
        bus.subscribe_handler("data", lambda ev: received.append(ev))

        bus.publish("data.ohlcv", {"x": 1})
        assert len(received) == 1  # parent gets child events

    def test_no_cross_talk(self):
        from stockstat._core.events import EventBus
        bus = EventBus()
        a_received = []
        b_received = []
        bus.subscribe_handler("data.ohlcv", lambda ev: a_received.append(ev))
        bus.subscribe_handler("data.quote", lambda ev: b_received.append(ev))

        bus.publish("data.ohlcv", {"x": 1})
        assert len(a_received) == 1
        assert len(b_received) == 0

    def test_event_log(self):
        from stockstat._core.events import EventBus
        bus = EventBus()
        bus.enable_logging()
        bus.publish("test", {"a": 1})
        bus.publish("test", {"b": 2})
        log = bus.get_log()
        assert len(log) == 2
        assert log[0].payload == {"a": 1}
        bus.disable_logging()


class TestEventReplay:

    def test_replay_simple(self):
        from stockstat._core.events import EventBus, EventReplay
        bus = EventBus()
        replay = EventReplay(bus, topic="data.ohlcv")

        received = []
        bus.subscribe_handler("data.ohlcv", lambda ev: received.append(ev))

        df = pd.DataFrame(
            {"close": [100, 101, 102]},
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )
        count = replay.replay(df, symbol="BTC/USDT")
        assert count == 3
        assert len(received) == 3

    def test_replay_group(self):
        from stockstat._core.events import EventBus, EventReplay
        bus = EventBus()
        replay = EventReplay(bus)

        received = []
        bus.subscribe_handler("data.ohlcv", lambda ev: received.append(ev))

        data = {
            "BTC/USDT": {"1d": pd.DataFrame(
                {"close": [100, 101]},
                index=pd.date_range("2024-01-01", periods=2, freq="D"),
            )},
            "ETH/USDT": {"1d": pd.DataFrame(
                {"close": [50, 51]},
                index=pd.date_range("2024-01-01", periods=2, freq="D"),
            )},
        }
        count = replay.replay_group(data)
        assert count == 2
        assert len(received) == 2


# ═══════════════════════════════════════════════════════════════
# Phase 1.5: Storage
# ═══════════════════════════════════════════════════════════════

class TestMemoryStorage:

    def _make_storage(self):
        from stockstat._core.storage import MemoryStorage
        from stockstat._core.contracts import DataSchema, FieldDef
        s = MemoryStorage()
        s.register_schema("ohlcv", DataSchema(
            name="ohlcv",
            fields=[
                FieldDef("symbol", "str", nullable=False, primary_key=True),
                FieldDef("ts", "datetime", nullable=False, primary_key=True),
                FieldDef("close", "float"),
            ],
            unique_constraints=[("symbol", "ts")],
        ))
        return s

    def test_write_and_query(self):
        s = self._make_storage()
        s.write("ohlcv", [
            {"symbol": "BTC", "ts": pd.Timestamp("2024-01-01", tz="UTC"), "close": 100},
            {"symbol": "BTC", "ts": pd.Timestamp("2024-01-02", tz="UTC"), "close": 101},
        ])
        df = s.query("ohlcv")
        assert len(df) == 2

    def test_upsert(self):
        s = self._make_storage()
        s.write("ohlcv", [
            {"symbol": "BTC", "ts": pd.Timestamp("2024-01-01", tz="UTC"), "close": 100},
        ])
        # Upsert same key → update
        s.upsert("ohlcv", [
            {"symbol": "BTC", "ts": pd.Timestamp("2024-01-01", tz="UTC"), "close": 200},
        ])
        df = s.query("ohlcv")
        assert len(df) == 1
        assert df.iloc[0]["close"] == 200

    def test_delete(self):
        s = self._make_storage()
        s.write("ohlcv", [
            {"symbol": "BTC", "ts": pd.Timestamp("2024-01-01", tz="UTC"), "close": 100},
            {"symbol": "ETH", "ts": pd.Timestamp("2024-01-01", tz="UTC"), "close": 50},
        ])
        n = s.delete("ohlcv", filters={"symbol": "BTC"})
        assert n == 1
        assert s.count("ohlcv") == 1

    def test_health_check(self):
        s = self._make_storage()
        assert s.health_check() is True


# ═══════════════════════════════════════════════════════════════
# Phase 1.6: Cache
# ═══════════════════════════════════════════════════════════════

class TestCacheBackends:

    def test_null_cache(self):
        from stockstat._core.cache import NullCache
        c = NullCache()
        assert c.get("x") is None
        c.set("x", 42)
        assert c.get("x") is None
        assert c.exists("x") is False

    def test_memory_cache_set_get(self):
        from stockstat._core.cache import MemoryCache
        c = MemoryCache(ttl=10)
        c.set("key1", {"data": 42})
        assert c.get("key1") == {"data": 42}
        assert c.exists("key1") is True

    def test_memory_cache_ttl_expiry(self):
        from stockstat._core.cache import MemoryCache
        c = MemoryCache(ttl=1)
        c.set("key1", "val")
        time.sleep(1.1)
        assert c.get("key1") is None

    def test_memory_cache_clear(self):
        from stockstat._core.cache import MemoryCache
        c = MemoryCache()
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert c.get("a") is None
        assert c.get("b") is None

    def test_memory_cache_delete(self):
        from stockstat._core.cache import MemoryCache
        c = MemoryCache()
        c.set("a", 1)
        c.delete("a")
        assert c.get("a") is None

    def test_memory_cache_make_key(self):
        from stockstat._core.cache import MemoryCache
        k1 = MemoryCache.make_key("BTC/USDT", "1d", "2024-01-01")
        k2 = MemoryCache.make_key("BTC/USDT", "1d", "2024-01-01")
        k3 = MemoryCache.make_key("BTC/USDT", "1d", "2024-01-02")
        assert k1 == k2
        assert k1 != k3

    def test_factory(self):
        from stockstat._core.cache import create_cache
        assert create_cache("null").name == "null"
        assert create_cache("memory").name == "memory"
        assert create_cache("redis").name == "redis"


# ═══════════════════════════════════════════════════════════════
# Phase 1.7: Codec
# ═══════════════════════════════════════════════════════════════

class TestCodecs:

    def test_json_codec_dataframe(self):
        from stockstat._core.codec import JsonCodec
        c = JsonCodec()
        df = pd.DataFrame({"close": [100, 101]}, index=pd.date_range("2024-01-01", periods=2))
        raw = c.encode(df)
        assert isinstance(raw, bytes)
        decoded = c.decode(raw)
        assert len(decoded) == 2

    def test_csv_codec(self):
        from stockstat._core.codec import CsvCodec
        c = CsvCodec()
        df = pd.DataFrame({"close": [100, 101]}, index=pd.date_range("2024-01-01", periods=2))
        raw = c.encode(df)
        assert b"close" in raw
        decoded = c.decode(raw)
        assert len(decoded) == 2

    def test_arrow_codec(self):
        from stockstat._core.codec import ArrowCodec
        c = ArrowCodec()
        df = pd.DataFrame({"close": [100, 101]}, index=pd.date_range("2024-01-01", periods=2))
        raw = c.encode(df)
        decoded = c.decode(raw)
        assert len(decoded) == 2

    def test_parquet_codec(self):
        from stockstat._core.codec import ParquetCodec
        c = ParquetCodec()
        df = pd.DataFrame({"close": [100, 101]}, index=pd.date_range("2024-01-01", periods=2))
        raw = c.encode(df)
        decoded = c.decode(raw)
        assert len(decoded) == 2

    def test_get_codec(self):
        from stockstat._core.codec import get_codec, available_codecs
        assert "json" in available_codecs()
        c = get_codec("json")
        assert c.name == "json"

    def test_unknown_codec_raises(self):
        from stockstat._core.codec import get_codec
        with pytest.raises(KeyError):
            get_codec("xml")


# ═══════════════════════════════════════════════════════════════
# Phase 1.8: Errors & Logging
# ═══════════════════════════════════════════════════════════════

class TestErrors:

    def test_app_error_to_dict(self):
        from stockstat._core.errors import AppError
        e = AppError("test message", code="TEST_CODE", context={"k": "v"})
        d = e.to_dict()
        assert d["code"] == "TEST_CODE"
        assert d["message"] == "test message"
        assert d["context"] == {"k": "v"}

    def test_data_not_found_error(self):
        from stockstat._core.errors import DataNotFoundError
        e = DataNotFoundError("No data for BTC")
        assert e.code == "DATA_NOT_FOUND"

    def test_lookahead_error(self):
        from stockstat._core.errors import LookaheadError
        e = LookaheadError("Accessed future data")
        assert e.code == "LOOKAHEAD_VIOLATION"


class TestStructuredLogger:

    def test_bind_and_log(self, caplog):
        from stockstat._core.logging import StructuredLogger
        logger = StructuredLogger("test")
        logger2 = logger.bind(symbol="BTC/USDT")
        with caplog.at_level("INFO"):
            logger2.info("test message")
        assert "symbol=BTC/USDT" in caplog.text
        assert "test message" in caplog.text
