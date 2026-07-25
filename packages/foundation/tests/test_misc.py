"""test_misc.py — PluginRegistry / RetryPolicy / utils / logging (35 项)。
凑齐 147 项验收点。
"""
from __future__ import annotations

import time

import pytest

from stockstat_foundation.plugin import PluginRegistry
from stockstat_foundation.protocol.retry import RetryPolicy
from stockstat_foundation.utils import (
    estimate_data_size, choose_data_dispatch, resolve_data_dispatch,
    Timeout, now_iso,
)
from stockstat_foundation.logging import (
    get_logger, set_trace_id, get_trace_id, reset_trace_id,
)
from stockstat_foundation import (
    Config, StorageBackend, Cache, Renderer, Event, EventSubscriber,
)


class TestPluginRegistry:
    def test_register_and_get(self):
        reg = PluginRegistry()
        class P:
            name = "x"
            version = "1.0"
            def mount(self, app, **kw): pass
            def unmount(self, app): pass
        p = P()
        reg.register(p)
        assert reg.get("x") is p
        assert "x" in reg
        assert len(reg) == 1

    def test_list(self):
        reg = PluginRegistry()
        class P1:
            name = "p1"
            version = "1.0"
            def mount(self, app, **kw): pass
            def unmount(self, app): pass
        class P2:
            name = "p2"
            version = "1.0"
            def mount(self, app, **kw): pass
            def unmount(self, app): pass
        reg.register(P1())
        reg.register(P2())
        assert set(reg.list()) == {"p1", "p2"}

    def test_unregister(self):
        reg = PluginRegistry()
        class P:
            name = "x"
            version = "1.0"
            def mount(self, app, **kw): pass
            def unmount(self, app): pass
        reg.register(P())
        reg.unregister("x")
        assert reg.get("x") is None
        assert len(reg) == 0

    def test_mount_all(self):
        reg = PluginRegistry()
        calls = []
        class P:
            name = "x"
            version = "1.0"
            def mount(self, app, **kw):
                calls.append(("mount", app, kw))
            def unmount(self, app):
                calls.append(("unmount", app))
        reg.register(P())
        reg.mount_all("app", k="v")
        assert calls[0] == ("mount", "app", {"k": "v"})

    def test_unmount_all(self):
        reg = PluginRegistry()
        calls = []
        class P:
            name = "x"
            version = "1.0"
            def mount(self, app, **kw): pass
            def unmount(self, app): calls.append(app)
        reg.register(P())
        reg.unmount_all("app")
        assert calls == ["app"]


class TestRetryPolicy:
    def test_defaults(self):
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.backoff_base == 1.0
        assert p.backoff_factor == 2.0
        assert p.max_backoff == 60.0

    def test_next_delay(self):
        p = RetryPolicy(backoff_base=1.0, backoff_factor=2.0, max_backoff=10.0)
        assert p.next_delay(0) == 1.0
        assert p.next_delay(1) == 2.0
        assert p.next_delay(2) == 4.0
        assert p.next_delay(3) == 8.0
        assert p.next_delay(10) == 10.0  # capped

    def test_should_retry_retryable(self):
        p = RetryPolicy(max_retries=3)
        assert p.should_retry({"retryable": True}, attempt=0) is True
        assert p.should_retry({"retryable": True}, attempt=2) is True
        assert p.should_retry({"retryable": True}, attempt=3) is False

    def test_should_retry_non_retryable(self):
        p = RetryPolicy()
        assert p.should_retry({"retryable": False}, attempt=0) is False

    def test_should_retry_no_field(self):
        p = RetryPolicy()
        assert p.should_retry({}, attempt=0) is False


class TestEstimateDataSize:
    def test_none(self):
        assert estimate_data_size(None) == 0

    def test_bytes(self):
        assert estimate_data_size(b"hello") == 5

    def test_str(self):
        assert estimate_data_size("hello") == 5

    def test_dataframe(self):
        import pandas as pd
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        size = estimate_data_size(df)
        assert size > 0

    def test_dict_of_dataframes(self):
        import pandas as pd
        df = pd.DataFrame({"a": [1, 2, 3]})
        size = estimate_data_size({"BTC": df, "ETH": df})
        assert size > 0

    def test_list(self):
        size = estimate_data_size([b"abc", b"def"])
        assert size >= 6


class TestChooseDataDispatch:
    def test_small_returns_inline(self):
        assert choose_data_dispatch(1024) == "inline"

    def test_medium_same_host_returns_shm(self):
        assert choose_data_dispatch(20 * 1024 * 1024, workers_same_host=True) == "shared_memory"

    def test_large_can_reach_storage_returns_storage_ref(self):
        size = 200 * 1024 * 1024
        assert choose_data_dispatch(size, workers_can_reach_storage=True) == "storage_ref"

    def test_medium_remote_returns_stream(self):
        assert choose_data_dispatch(20 * 1024 * 1024,
                                    workers_same_host=False,
                                    workers_can_reach_storage=False) == "stream"

    def test_resolve_data_dispatch_explicit(self):
        assert resolve_data_dispatch("inline", 100 * 1024 * 1024) == "inline"

    def test_resolve_data_dispatch_auto(self):
        assert resolve_data_dispatch("auto", 1024) == "inline"


class TestTimeout:
    def test_not_expired(self):
        t = Timeout(1.0)
        assert not t.expired()

    def test_expired(self):
        t = Timeout(0.01)
        time.sleep(0.02)
        assert t.expired()

    def test_no_timeout(self):
        t = Timeout(None)
        assert not t.expired()
        assert t.remaining() is None

    def test_remaining(self):
        t = Timeout(1.0)
        r = t.remaining()
        assert r is not None and 0 < r <= 1.0


class TestNowIso:
    def test_returns_iso_string(self):
        s = now_iso()
        assert "T" in s
        assert s.endswith("Z")


class TestLogging:
    def test_set_get_trace_id(self):
        token = set_trace_id("trace-123")
        assert get_trace_id() == "trace-123"
        reset_trace_id(token)
        assert get_trace_id() == ""

    def test_get_logger(self):
        logger = get_logger("test")
        assert logger.name == "test"
        logger2 = get_logger("test")
        assert logger is logger2


class TestProtocols:
    def test_storage_backend_protocol(self):
        class MyStorage:
            name = "test"
            def fetch_ohlcv(self, symbols, timeframe, start=None, end=None, source=None): return None
            def ingest_ohlcv(self, symbol, timeframe, data): return 0
            def list_symbols(self): return []
            def get_metadata(self, symbol): return {}
        assert isinstance(MyStorage(), StorageBackend)

    def test_cache_protocol(self):
        class MyCache:
            name = "test"
            def get(self, key): return None
            def put(self, key, value, ttl=None): pass
            def get_ref(self, key): return None
            def invalidate(self, key): pass
            def stats(self): return {}
        assert isinstance(MyCache(), Cache)

    def test_renderer_protocol(self):
        class MyRenderer:
            name = "mpl"
            def render(self, spec): return b""
        assert isinstance(MyRenderer(), Renderer)

    def test_event_dataclass(self):
        e = Event(type="task.progress", payload={"x": 1})
        assert e.type == "task.progress"
        assert e.payload == {"x": 1}
        assert e.timestamp is not None

    def test_config_dataclass(self):
        c = Config()
        assert c.protocol_version == "1.0"


class TestConvenienceImports:
    def test_top_level_exports(self):
        import stockstat_foundation as f
        assert hasattr(f, "Envelope")
        assert hasattr(f, "TaskSpec")
        assert hasattr(f, "Config")
        assert hasattr(f, "ComputeBackend")
        assert hasattr(f, "Transport")
        assert hasattr(f, "StorageBackend")
        assert hasattr(f, "JsonCodec")
        assert hasattr(f, "ArrowCodec")
        assert hasattr(f, "make_pair")
        assert hasattr(f, "build_transport")
        assert hasattr(f, "PluginRegistry")
        assert hasattr(f, "AppError")
        assert hasattr(f, "TaskError")
        assert hasattr(f, "estimate_data_size")

    def test_cloudpickle_helpers(self):
        from stockstat_foundation import cloudpickle_dumps, cloudpickle_loads
        def f(x): return x + 1
        ref = cloudpickle_dumps(f)
        restored = cloudpickle_loads(f"cloudpickle:{ref}")
        assert restored(5) == 6

    def test_version(self):
        import stockstat_foundation as f
        assert f.__version__ == "3.1.0"

    def test_make_pair_returns_two(self):
        from stockstat_foundation import make_pair
        a, b = make_pair()
        assert a is not b
        assert a._peer is b

    def test_build_transport_default(self):
        from stockstat_foundation import build_transport, InProcessTransport
        assert isinstance(build_transport(), InProcessTransport)
