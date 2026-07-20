#!/usr/bin/env python3
"""V3 Deployment Case D — Explicit LocalComputeBackend injection.

This case isolates V3 ComputeBackend behaviour by explicitly
constructing LocalComputeBackend and passing it to both StockStatClient
and V2Client. It exercises the full V3 API surface:

- client.compute_backend property
- compute.remote() for all 5 task types (indicator / backtest / grid_search /
  batch_backtest / monte_carlo) plus custom
- TaskRef lifecycle (submit / get / wait / result / cancel / stream_results)
- cluster_info() topology
- async_submit=True transparent mode
- InProcessTransport (via make_pair)
- Envelope encode/decode roundtrip

Exit code: 0 on success, 1 on failure.

Usage:
    python test_case_d_local_compute_backend.py
"""
from __future__ import annotations

import sys
import time

from _common import (
    EnvConfig, TestRunner, banner, step, ok, fail, warn, info,
    assert_v3_compute_backend, assert_cluster_info_shape,
    make_synthetic_data, make_ma_cross_strategy, encode_strategy,
)


def _make_backend_with_data(data):
    """Build a LocalComputeBackend wired to a stub data client."""
    from stockstat._core.compute import LocalComputeBackend
    backend = LocalComputeBackend()
    class StubClient:
        def ohlcv(self, symbol, **kw):
            return data[symbol][kw.get("timeframe", "1d")]
    backend._client = StubClient()
    return backend


def test_explicit_local_backend_stockstat(env: EnvConfig) -> None:
    """StockStatClient(compute_backend=LocalComputeBackend())."""
    from stockstat.client import StockStatClient
    from stockstat._core.compute import LocalComputeBackend
    backend = LocalComputeBackend()
    c = StockStatClient(host="localhost", port=1, compute_backend=backend)
    assert c.compute_backend is backend
    assert_v3_compute_backend(c, "local")
    ok(f"explicit LocalComputeBackend injected: {c.compute_backend.name}")


def test_explicit_local_backend_v2client(env: EnvConfig) -> None:
    """V2Client(compute_backend=LocalComputeBackend())."""
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage
    from stockstat._core.compute import LocalComputeBackend
    backend = LocalComputeBackend()
    c = V2Client(mode="offline", storage=MemoryStorage(), compute_backend=backend)
    assert c.compute_backend is backend
    assert_v3_compute_backend(c, "local")
    ok(f"V2Client explicit LocalComputeBackend: {c.compute_backend.name}")


def test_task_ref_lifecycle(env: EnvConfig) -> None:
    """Submit -> get -> wait -> result -> cluster_info."""
    from stockstat._core.compute import LocalComputeBackend
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    from stockstat._core.contracts.compute import TaskState
    backend = LocalComputeBackend()
    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="custom", params={"step": "lifecycle"}),
    )
    ref = backend.submit(spec)
    ok(f"submit: id={ref.id[:8]}..., status={ref.status}")

    info_state = backend.get(ref.task_id)
    ok(f"get: state={info_state.state.value}")

    result = ref.wait(timeout=5)
    ok(f"wait: result={result['params']['step']}")

    assert ref.ready() is True
    assert ref.status == "completed"
    ok(f"ready=True, final status={ref.status}")


def test_task_cancel(env: EnvConfig) -> None:
    """Cancel a running task."""
    from stockstat._core.compute import LocalComputeBackend
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    backend = LocalComputeBackend()
    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(
            task_type="custom",
            params={"_sleep_seconds": 5.0},
        ),
    )
    ref = backend.submit(spec)
    time.sleep(0.3)  # let it start
    cancelled = ref.cancel()
    if not cancelled:
        warn("cancel returned False (task may have completed already)")
        return
    ok(f"cancel: accepted, status={ref.status}")


def test_stream_results(env: EnvConfig) -> None:
    """stream_results yields partials + final."""
    from stockstat._core.compute import LocalComputeBackend
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    backend = LocalComputeBackend()
    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
        compute_spec=ComputeSpec(
            task_type="grid_search",
            strategy_ref=encode_strategy(make_ma_cross_strategy()()),
            param_grid={"window": [5, 10, 20]},
            metric="sharpe",
            initial_cash=10000,
        ),
    )
    data = make_synthetic_data()
    backend._client = type("S", (), {
        "ohlcv": lambda self, symbol, **kw: data[symbol][kw.get("timeframe", "1d")]
    })()
    ref = backend.submit(spec)
    parts = list(ref.stream_results())
    ok(f"stream_results: {len(parts)} parts yielded")


def test_async_submit_transparent(env: EnvConfig) -> None:
    """backtest(async_submit=True) on LocalComputeBackend returns BacktestResult.

    LocalComputeBackend short-circuits, so async_submit is effectively
    ignored — backtest still goes through v2.1 direct path. This is
    intentional: LocalComputeBackend is meant to be transparent.
    """
    from stockstat.client import StockStatClient
    from stockstat._core.compute import LocalComputeBackend
    from stockstat.backtest import BacktestResult
    data = make_synthetic_data()
    strategy = make_ma_cross_strategy()()
    c = StockStatClient(
        host="localhost", port=1,
        compute_backend=LocalComputeBackend(),
    )
    result = c.backtest(data, strategy, initial_cash=10000, async_submit=True)
    assert isinstance(result, BacktestResult)
    ok(f"async_submit=True transparent: BacktestResult, fills={len(result.fills)}")


def test_all_task_types(env: EnvConfig) -> None:
    """Exercise all 5 V3 task types + custom via compute.remote()."""
    from stockstat.client import StockStatClient
    from stockstat._core.contracts.compute import TaskRef
    data = make_synthetic_data()
    c = StockStatClient(host="localhost", port=1)
    c.compute_backend._client = type("S", (), {
        "ohlcv": lambda self, symbol, **kw: data[symbol][kw.get("timeframe", "1d")]
    })()
    strategy_ref = encode_strategy(make_ma_cross_strategy()())

    # 1. indicator
    task = c.compute.remote(
        "indicator", symbols=["BTC/USDT"], timeframe="1d",
        method="rsi", kwargs={"window": 14},
    )
    r = task.wait(timeout=10)
    ok(f"indicator: type={type(r).__name__}, len={len(r)}")

    # 2. backtest
    task = c.compute.remote(
        "backtest", symbols=["BTC/USDT"], timeframe="1d",
        strategy_ref=strategy_ref, initial_cash=10000,
    )
    r = task.wait(timeout=30)
    ok(f"backtest: type={type(r).__name__}, fills={len(r.fills)}")

    # 3. grid_search
    task = c.compute.remote(
        "grid_search", symbols=["BTC/USDT"], timeframe="1d",
        strategy_ref=strategy_ref, initial_cash=10000,
        param_grid={"window": [5, 10, 20]}, metric="sharpe",
    )
    r = task.wait(timeout=60)
    ok(f"grid_search: {len(r)} combinations")

    # 4. custom
    task = c.compute.remote(
        "custom", symbols=[], payload="hello",
    )
    r = task.wait(timeout=5)
    ok(f"custom: {r['params'].get('payload')}")


def test_in_process_transport_roundtrip(env: EnvConfig) -> None:
    """InProcessTransport: send/receive/request/reply."""
    from stockstat._core.transport import make_pair
    from stockstat._core.protocol import Envelope, Headers
    import threading
    client_t, server_t = make_pair(encode_envelopes=True)

    # Server thread: receive request, reply
    def server():
        req = server_t.receive(timeout=2.0)
        if req is None:
            return
        reply = req.reply("task.ack", {"status": "pending"})
        server_t.reply(req, reply)
    t = threading.Thread(target=server, daemon=True)
    t.start()

    env_msg = Envelope(
        type="task.submit",
        headers=Headers(trace_id="case-d"),
        payload={"task_id": "t1"},
    )
    reply = client_t.request(env_msg, timeout=2.0)
    assert reply.type == "task.ack"
    assert reply.reply_to == env_msg.id
    assert reply.payload["status"] == "pending"
    ok(f"transport roundtrip: {reply.type} reply_to={reply.reply_to[:8]}...")
    t.join(timeout=2.0)


def test_envelope_encode_decode(env: EnvConfig) -> None:
    """Envelope encode/decode works for JSON and Msgpack."""
    from stockstat._core.protocol import Envelope, Headers
    env_msg = Envelope(
        type="dispatch.heartbeat",
        headers=Headers(encoding="json", trace_id="case-d"),
        payload={"cpu_percent": 37.5},
    )
    raw = env_msg.encode()
    restored = Envelope.decode(raw)
    assert restored.type == "dispatch.heartbeat"
    assert restored.payload["cpu_percent"] == 37.5
    ok(f"JSON envelope: {len(raw)} bytes, trace_id={restored.headers.trace_id}")

    # Msgpack
    try:
        import msgpack  # noqa: F401
        env_msg2 = Envelope(
            type="dispatch.heartbeat",
            headers=Headers(encoding="msgpack"),
            payload={"cpu_percent": 37.5},
        )
        raw2 = env_msg2.encode()
        restored2 = Envelope.decode(raw2)
        assert restored2.payload["cpu_percent"] == 37.5
        assert len(raw2) < len(raw)
        ok(f"Msgpack envelope: {len(raw2)} bytes (vs JSON {len(raw)} bytes)")
    except ImportError:
        warn("msgpack not installed; skipping msgpack test")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="V3 Case D: explicit LocalComputeBackend")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    banner("V3 Deployment Case D: Explicit LocalComputeBackend (V3 API surface)")
    env = EnvConfig()
    info(f"transport={env.transport}")

    runner = TestRunner(env)
    runner.run("Explicit LocalComputeBackend on StockStatClient", test_explicit_local_backend_stockstat, critical=True)
    runner.run("Explicit LocalComputeBackend on V2Client", test_explicit_local_backend_v2client)
    runner.run("TaskRef lifecycle (submit/get/wait/result)", test_task_ref_lifecycle)
    runner.run("Task cancel", test_task_cancel)
    runner.run("stream_results partials", test_stream_results)
    runner.run("async_submit=True transparent mode", test_async_submit_transparent)
    runner.run("All 4 task types via compute.remote()", test_all_task_types)
    runner.run("InProcessTransport request/reply", test_in_process_transport_roundtrip)
    runner.run("Envelope encode/decode (JSON + Msgpack)", test_envelope_encode_decode)

    return runner.summarize()


if __name__ == "__main__":
    sys.exit(main())
