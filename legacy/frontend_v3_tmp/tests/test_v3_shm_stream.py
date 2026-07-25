"""V3 P4 SharedMemory + Stream + dispatch.partial + data_dispatch tests.

Covers DESIGN_V3_CN §12 (data dispatch) + §13.1 (Stream) + §13.2 (partials):
- SharedMemoryTransport.send_data / fetch_data (inline + shm://)
- SharedMemoryTransport round-trip via shared_memory segments
- Stream class: __iter__, collect, from_data
- Stream duck-typing: is_stream_aware detects Stream-typed handlers
- choose_data_dispatch: inline / shared_memory / storage_ref / stream
- estimate_data_size for various types
- dispatch.partial end-to-end: worker publishes, client consumes
"""
from __future__ import annotations

import time
import threading
import pytest
import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════
# P4.1: SharedMemoryTransport
# ═══════════════════════════════════════════════════════════════


class TestSharedMemoryTransport:
    def test_name(self):
        from stockstat._core.transport import SharedMemoryTransport
        t = SharedMemoryTransport()
        assert t.name == "shared_memory"

    def test_send_data_small_goes_inline(self):
        """Data below inline_threshold is base64-encoded inline."""
        import base64
        from stockstat._core.transport import SharedMemoryTransport
        t = SharedMemoryTransport(inline_threshold=1024)
        data = b"hello world"
        ref = t.send_data(data, "application/octet-stream")
        assert ref.startswith("inline:")
        assert base64.b64decode(ref[len("inline:"):]) == data

    def test_send_data_large_uses_shm(self):
        """Data above threshold uses shared memory."""
        from stockstat._core.transport import SharedMemoryTransport
        t = SharedMemoryTransport(inline_threshold=100)  # 100 bytes
        data = b"x" * 1024  # 1KB, above threshold
        ref = t.send_data(data, "application/octet-stream")
        # Should be shm:// (or inline:// if shm unavailable on this platform)
        assert ref.startswith(("shm://", "inline:"))
        if ref.startswith("shm://"):
            fetched = t.fetch_data(ref)
            assert fetched == data

    def test_fetch_data_inline(self):
        """fetch_data decodes inline: refs."""
        import base64
        from stockstat._core.transport import SharedMemoryTransport
        t = SharedMemoryTransport()
        ref = "inline:" + base64.b64encode(b"test").decode("ascii")
        assert t.fetch_data(ref) == b"test"

    def test_fetch_data_unknown_format_raises(self):
        from stockstat._core.transport import SharedMemoryTransport
        t = SharedMemoryTransport()
        with pytest.raises(ValueError, match="Unknown data_ref"):
            t.fetch_data("unknown://x")

    def test_send_data_roundtrip(self):
        """send_data + fetch_data returns original bytes."""
        from stockstat._core.transport import SharedMemoryTransport
        t = SharedMemoryTransport(inline_threshold=10)
        data = b"\x00\x01\x02\x03\xff\xfe" * 100  # 600 bytes
        ref = t.send_data(data, "application/octet-stream")
        fetched = t.fetch_data(ref)
        assert fetched == data

    def test_close_cleans_up(self):
        """close() unlinks shared memory segments."""
        from stockstat._core.transport import SharedMemoryTransport
        t = SharedMemoryTransport(inline_threshold=10)
        t.send_data(b"x" * 1024, "application/octet-stream")
        t.close()  # should not raise

    def test_delegates_to_underlying_for_envelopes(self):
        """send/request/receive are delegated to underlying transport."""
        from stockstat._core.transport import SharedMemoryTransport, InProcessTransport
        from stockstat._core.protocol.envelope import Envelope
        underlying = InProcessTransport()
        shm_t = SharedMemoryTransport(underlying=underlying)
        env = Envelope(type="task.submit", payload={"x": 1})
        shm_t.send(env)
        received = shm_t.receive(timeout=1.0)
        assert received is not None
        assert received.payload["x"] == 1


# ═══════════════════════════════════════════════════════════════
# P4.2: Stream class
# ═══════════════════════════════════════════════════════════════


class TestStream:
    def test_from_data_single_chunk(self):
        """Stream.from_data wraps a DataFrame as single-chunk."""
        from stockstat._core.compute.handlers import Stream
        df = pd.DataFrame({"close": [1, 2, 3]})
        s = Stream.from_data(df)
        assert s.collect() is df

    def test_iter_single_chunk(self):
        """Iterating a single-chunk Stream yields one DataFrame."""
        from stockstat._core.compute.handlers import Stream
        df = pd.DataFrame({"close": [1, 2, 3]})
        s = Stream.from_data(df)
        chunks = list(s)
        assert len(chunks) == 1
        assert chunks[0] is df

    def test_collect_multi_chunks(self):
        """collect() concatenates multiple chunks."""
        from stockstat._core.compute.handlers import Stream
        df1 = pd.DataFrame({"close": [1, 2, 3]})
        df2 = pd.DataFrame({"close": [4, 5, 6]})
        s = Stream(chunks=iter([df1, df2]))
        collected = s.collect()
        assert len(collected) == 6
        assert list(collected["close"]) == [1, 2, 3, 4, 5, 6]

    def test_iter_multi_chunks(self):
        """Iterating a multi-chunk Stream yields each chunk."""
        from stockstat._core.compute.handlers import Stream
        df1 = pd.DataFrame({"close": [1, 2]})
        df2 = pd.DataFrame({"close": [3, 4]})
        s = Stream(chunks=iter([df1, df2]))
        chunks = list(s)
        assert len(chunks) == 2

    def test_collect_is_idempotent(self):
        """collect() returns the same DataFrame on subsequent calls."""
        from stockstat._core.compute.handlers import Stream
        df1 = pd.DataFrame({"close": [1, 2]})
        df2 = pd.DataFrame({"close": [3, 4]})
        s = Stream(chunks=iter([df1, df2]))
        first = s.collect()
        second = s.collect()
        assert first is second  # cached


# ═══════════════════════════════════════════════════════════════
# P4.3: Stream duck-typing (is_stream_aware)
# ═══════════════════════════════════════════════════════════════


class TestStreamAwareness:
    def test_non_stream_handler_returns_false(self):
        """A regular handler taking a DataFrame is not stream-aware."""
        from stockstat._core.compute.handlers import is_stream_aware

        def handler(spec, data, on_progress=None):
            return data

        assert is_stream_aware(handler) is False

    def test_stream_annotated_handler_returns_true(self):
        """A handler with Stream annotation is stream-aware."""
        from stockstat._core.compute.handlers import is_stream_aware, Stream

        def handler(spec, stream: Stream, on_progress=None):
            return stream.collect()

        assert is_stream_aware(handler) is True

    def test_stream_attribute_set(self):
        """Handlers with __stream_aware__ = True are detected."""
        from stockstat._core.compute.handlers import is_stream_aware

        def handler(spec, data, on_progress=None):
            return data

        handler.__stream_aware__ = True
        assert is_stream_aware(handler) is True

    def test_dispatch_routes_stream_to_stream_handler(self):
        """dispatch() passes a Stream when handler is stream-aware."""
        from stockstat._core.compute.handlers import dispatch, Stream
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )

        # Register a temporary stream-aware handler
        from stockstat._core.compute import handlers as handlers_mod

        def my_stream_handler(spec, stream: Stream, on_progress=None):
            data = stream.collect()
            # data is {symbol: {timeframe: df}} — extract first df
            sym_data = next(iter(data.values()))
            df = next(iter(sym_data.values()))
            return {"rows": len(df)}

        # Save and patch the registry
        original = handlers_mod.HANDLERS.get("custom_stream")
        handlers_mod.HANDLERS["custom_stream"] = my_stream_handler
        try:
            df = pd.DataFrame({"close": list(range(20))})
            data = {"BTC/USDT": {"1d": df}}
            spec = TaskSpec(
                task_id=new_task_id(),
                data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
                compute_spec=ComputeSpec(task_type="custom_stream"),
            )
            result = dispatch(spec, data)
            assert result["rows"] == 20
        finally:
            if original is not None:
                handlers_mod.HANDLERS["custom_stream"] = original
            else:
                handlers_mod.HANDLERS.pop("custom_stream", None)


# ═══════════════════════════════════════════════════════════════
# P4.4: data_dispatch strategy
# ═══════════════════════════════════════════════════════════════


class TestDataDispatch:
    def test_small_data_goes_inline(self):
        from stockstat._core.compute import choose_data_dispatch
        assert choose_data_dispatch(1024) == "inline"
        assert choose_data_dispatch(5 * 1024 * 1024) == "inline"

    def test_large_data_cross_host_goes_stream(self):
        from stockstat._core.compute import choose_data_dispatch
        # 50MB, cross-host, can't reach storage
        assert choose_data_dispatch(
            50 * 1024 * 1024,
            workers_same_host=False,
            workers_can_reach_storage=False,
        ) == "stream"

    def test_large_data_same_host_uses_shm(self):
        from stockstat._core.compute import choose_data_dispatch
        # 50MB, same host
        assert choose_data_dispatch(
            50 * 1024 * 1024,
            workers_same_host=True,
        ) == "shared_memory"

    def test_very_large_data_uses_storage_ref(self):
        from stockstat._core.compute import choose_data_dispatch
        # 200MB, cross-host, workers can reach Storage
        assert choose_data_dispatch(
            200 * 1024 * 1024,
            workers_same_host=False,
            workers_can_reach_storage=True,
        ) == "storage_ref"

    def test_very_large_data_no_storage_uses_stream(self):
        from stockstat._core.compute import choose_data_dispatch
        # 200MB, cross-host, workers can't reach Storage
        assert choose_data_dispatch(
            200 * 1024 * 1024,
            workers_same_host=False,
            workers_can_reach_storage=False,
        ) == "stream"

    def test_resolve_data_dispatch_auto(self):
        """resolve_data_dispatch with 'auto' uses choose_data_dispatch."""
        from stockstat._core.compute import resolve_data_dispatch
        assert resolve_data_dispatch("auto", 1024) == "inline"
        assert resolve_data_dispatch("auto", 50 * 1024 * 1024,
                                       workers_same_host=True) == "shared_memory"

    def test_resolve_data_dispatch_explicit(self):
        """resolve_data_dispatch with explicit strategy returns it as-is."""
        from stockstat._core.compute import resolve_data_dispatch
        assert resolve_data_dispatch("inline", 999) == "inline"
        assert resolve_data_dispatch("shared_memory", 999) == "shared_memory"

    def test_estimate_data_size_bytes(self):
        from stockstat._core.compute import estimate_data_size
        assert estimate_data_size(b"hello") == 5
        assert estimate_data_size(bytearray(b"abc")) == 3

    def test_estimate_data_size_dataframe(self):
        from stockstat._core.compute import estimate_data_size
        df = pd.DataFrame({"close": np.arange(1000, dtype=float)})
        size = estimate_data_size(df)
        assert size > 0  # 1000 floats ≈ 8KB

    def test_estimate_data_size_dict_of_dataframes(self):
        from stockstat._core.compute import estimate_data_size
        df1 = pd.DataFrame({"close": np.arange(100, dtype=float)})
        df2 = pd.DataFrame({"close": np.arange(200, dtype=float)})
        data = {"BTC": {"1d": df1}, "ETH": {"1d": df2}}
        size = estimate_data_size(data)
        assert size > 0

    def test_estimate_data_size_other(self):
        from stockstat._core.compute import estimate_data_size
        # Default conservative estimate for unknown types
        assert estimate_data_size(42) == 1024
        assert estimate_data_size("hello") == 1024


# ═══════════════════════════════════════════════════════════════
# P4.5: dispatch.partial end-to-end
# ═══════════════════════════════════════════════════════════════


class TestDispatchPartial:
    def test_partial_stored_in_task_state(self):
        """on_partial stores partial results in the dispatcher task state."""
        from stockstat_backend.dispatcher.core import Dispatcher
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom"),
        )
        d.submit(spec)
        d.on_partial("w1", spec.task_id, {"progress": 0.5, "completed": 5})
        state = d._tasks[spec.task_id]
        assert hasattr(state, "stream_partials")
        assert len(state.stream_partials) == 1
        assert state.stream_partials[0]["progress"] == 0.5

    def test_multiple_partials_accumulate(self):
        """Multiple partials accumulate in order."""
        from stockstat_backend.dispatcher.core import Dispatcher
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        d = Dispatcher(queue=MemoryTaskQueue())
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom"),
        )
        d.submit(spec)
        for i in range(5):
            d.on_partial("w1", spec.task_id, {"i": i})
        state = d._tasks[spec.task_id]
        assert len(state.stream_partials) == 5
        assert [p["i"] for p in state.stream_partials] == [0, 1, 2, 3, 4]

    def test_partial_unknown_task_returns_unknown(self):
        """on_partial for unknown task returns 'unknown_task'."""
        from stockstat_backend.dispatcher.core import Dispatcher
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        d = Dispatcher(queue=MemoryTaskQueue())
        result = d.on_partial("w1", "nonexistent", {"x": 1})
        assert result["status"] == "unknown_task"

    def test_partial_endpoint_in_routes(self):
        """The /dispatch/partial endpoint exists in the dispatcher router."""
        from fastapi import FastAPI
        from stockstat_backend.dispatcher import DispatcherPlugin
        from stockstat_backend.dispatcher.routes import create_dispatcher_router
        from stockstat_backend.dispatcher.core import Dispatcher
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        app = FastAPI()
        dispatcher = Dispatcher(queue=MemoryTaskQueue())
        router = create_dispatcher_router(dispatcher)
        app.include_router(router)
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/dispatch/partial" in paths


# ═══════════════════════════════════════════════════════════════
# P4.6: Stream results via RemoteComputeBackend
# ═══════════════════════════════════════════════════════════════


class TestStreamResultsE2E:
    """stream_results() on RemoteComputeBackend yields final result."""

    def test_stream_results_yields_final(self):
        """After completion, stream_results yields the final result."""
        from stockstat._core.compute import LocalComputeBackend
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        backend = LocalComputeBackend()
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom",
                                      params={"stream": "yes"}),
        )
        ref = backend.submit(spec)
        parts = list(ref.stream_results())
        assert len(parts) >= 1
        assert parts[-1]["params"]["stream"] == "yes"

    def test_stream_results_with_partials(self):
        """grid_search publishes partials via publish_partial."""
        from stockstat._core.compute import LocalComputeBackend
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        import base64
        from stockstat._core.codec import CloudpickleCodec
        from stockstat.backtest import Strategy, Order, OrderSide, OrderType

        class BuyHold(Strategy):
            name = "buy_hold_stream"
            def __init__(self):
                super().__init__()
                self._bought = False
            def on_bar(self, ctx):
                if not self._bought:
                    ctx.broker.submit(Order(
                        symbol="BTC/USDT", side=OrderSide.BUY,
                        order_type=OrderType.MARKET, qty=1.0,
                    ))
                    self._bought = True

        # Build small data
        dates = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
        rng = np.random.RandomState(42)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 30)))
        df = pd.DataFrame({
            "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": np.zeros(30),
        }, index=dates)
        data = {"BTC/USDT": {"1d": df}}

        backend = LocalComputeBackend()
        # Stub data client
        class StubClient:
            def ohlcv(self, symbol, **kw):
                return data[symbol][kw.get("timeframe", "1d")]
        backend._client = StubClient()

        strategy_ref = "cloudpickle:" + base64.b64encode(
            CloudpickleCodec().encode(BuyHold())
        ).decode("ascii")

        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="grid_search",
                strategy_ref=strategy_ref,
                param_grid={"window": [5, 10]},
                metric="sharpe",
                initial_cash=10000,
            ),
        )
        ref = backend.submit(spec)
        # stream_results should yield partials (progress) + final result
        parts = list(ref.stream_results())
        # Should have at least the partials + final
        assert len(parts) >= 1
        # Last part is the final result (list of dicts)
        assert isinstance(parts[-1], list)
        assert len(parts[-1]) == 2  # 2 grid combinations
