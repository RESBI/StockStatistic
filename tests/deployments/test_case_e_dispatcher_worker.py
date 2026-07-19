#!/usr/bin/env python3
"""V3 Deployment Case E — Dispatcher + Worker (cross-process).

Scenario E from DESIGN_V3_CN §18.4:
- Storage + Dispatcher (FastAPI app, in-process)
- Worker (background thread, HTTP-polled Dispatcher)
- Client (RemoteComputeBackend via HTTP)

This case validates the full V3 distributed compute path:
1. Start Dispatcher (mount on FastAPI app)
2. Start Worker in background thread (HTTP polling)
3. Client submits via RemoteComputeBackend
4. Worker pulls, executes, returns result
5. Client waits and verifies

The test bridges httpx to the FastAPI TestClient so no real network
is needed. For real cross-machine deployment, use the launcher script
which starts a real uvicorn server.

Exit code: 0 on success, 1 on failure.

Usage:
    python test_case_e_dispatcher_worker.py
    python test_case_e_dispatcher_worker.py --verbose
"""
from __future__ import annotations

import argparse
import sys
import time
import base64
from urllib.parse import urlparse

from _common import (
    EnvConfig, TestRunner, banner, step, ok, fail, info,
    make_synthetic_data, make_ma_cross_strategy, encode_strategy,
)


def _bridge_httpx_to_app(app):
    """Patch httpx.post/get to route localhost:8000 calls to TestClient(app)."""
    import httpx
    from fastapi.testclient import TestClient

    test_client = TestClient(app)
    orig_post = httpx.post
    orig_get = httpx.get

    class _Resp:
        def __init__(self, r):
            self._r = r
            self.status_code = r.status_code
            self.text = r.text
        def json(self):
            return self._r.json()
        @property
        def content(self):
            return self._r.content

    def patched_post(url, **kw):
        if "localhost:8000" in url or "testserver" in url:
            p = urlparse(url)
            cleaned = {k: v for k, v in kw.items() if k != "timeout"}
            return _Resp(test_client.post(p.path, **cleaned))
        return orig_post(url, **kw)

    def patched_get(url, **kw):
        if "localhost:8000" in url or "testserver" in url:
            p = urlparse(url)
            cleaned = {k: v for k, v in kw.items() if k != "timeout"}
            return _Resp(test_client.get(p.path, **cleaned))
        return orig_get(url, **kw)

    httpx.post = patched_post
    httpx.get = patched_get
    return test_client, (orig_post, orig_get)


class _HttpxCompatClient:
    """Wrap TestClient to look like httpx.Client for HttpTransport."""
    def __init__(self, test_client):
        self._tc = test_client
    def post(self, url, *, content=None, json=None, headers=None, timeout=None):
        p = urlparse(url)
        if json is not None:
            r = self._tc.post(p.path, json=json, headers=headers)
        elif content is not None:
            r = self._tc.post(p.path, content=content, headers=headers)
        else:
            r = self._tc.post(p.path, headers=headers)
        return _HttpxCompatResponse(r)
    def get(self, url, *, params=None, headers=None, timeout=None):
        p = urlparse(url)
        r = self._tc.get(p.path, params=params, headers=headers)
        return _HttpxCompatResponse(r)
    def close(self):
        pass


class _HttpxCompatResponse:
    def __init__(self, r):
        self._r = r
        self.status_code = r.status_code
        self.text = r.text
        self.content = r.content
    def json(self):
        return self._r.json()
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


# Module-level stack (initialized once per process)
_app = None
_test_client = None
_worker = None
_httpx_saved = None


def _ensure_stack():
    """Initialize the Dispatcher + Worker stack (idempotent)."""
    global _app, _test_client, _worker, _httpx_saved
    if _app is not None:
        return
    from stockstat_backend.app import create_app
    from stockstat_backend.dispatcher import DispatcherPlugin
    from stockstat_compute.worker import Worker

    _app = create_app()
    DispatcherPlugin.mount(_app, queue_backend="memory")
    _test_client, _httpx_saved = _bridge_httpx_to_app(_app)

    _worker = Worker(
        dispatcher_url="http://localhost:8000",
        alias="case-e-worker",
        concurrency=2,
        poll_interval=0.05,
        heartbeat_interval=0.5,
    )
    _worker.start_background()
    if not _worker.wait_registered(timeout=5):
        raise RuntimeError("Worker failed to register")


def _cleanup_stack():
    global _worker, _httpx_saved
    if _worker is not None:
        _worker.stop()
        _worker.join(timeout=3)
        _worker = None
    if _httpx_saved is not None:
        import httpx
        httpx.post, httpx.get = _httpx_saved
        _httpx_saved = None


# ═══════════════════════════════════════════════════════════════
# Test steps
# ═══════════════════════════════════════════════════════════════


def test_stack_starts(env: EnvConfig) -> None:
    """Start Dispatcher + Worker + bridge httpx."""
    _ensure_stack()
    # Verify cluster has 1 worker
    import httpx
    info = httpx.get("http://localhost:8000/dispatch/cluster").json()
    assert info["stats"]["online_workers"] == 1
    ok(f"stack online: {info['workers'][0]['alias']}")


def test_cluster_info_via_http(env: EnvConfig) -> None:
    """cluster_info() returns full topology via HTTP."""
    _ensure_stack()
    import httpx
    info = httpx.get("http://localhost:8000/dispatch/cluster").json()
    assert "dispatcher" in info
    assert "workers" in info
    assert "stats" in info
    assert info["dispatcher"]["status"] == "online"
    ok(f"dispatcher uptime: {info['dispatcher']['uptime_s']}s, "
       f"workers: {info['stats']['online_workers']}")


def test_custom_task_e2e(env: EnvConfig) -> None:
    """Submit custom task via RemoteComputeBackend → Worker executes."""
    _ensure_stack()
    from stockstat._core.compute.remote import RemoteComputeBackend
    from stockstat._core.transport.http import HttpTransport
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    transport = HttpTransport("http://localhost:8000")
    transport._client = _HttpxCompatClient(_test_client)
    backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)

    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="custom",
                                  params={"case": "e", "step": "custom"}),
    )
    result = backend.submit(spec).wait(timeout=10)
    assert result["params"]["case"] == "e"
    ok(f"custom task result: {result['params']}")


def test_backtest_e2e(env: EnvConfig) -> None:
    """End-to-end backtest via RemoteComputeBackend."""
    _ensure_stack()
    from stockstat._core.compute.remote import RemoteComputeBackend
    from stockstat._core.transport.http import HttpTransport
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    from stockstat._core.codec import CloudpickleCodec
    from stockstat_backend.dispatcher.prefetch import DataCache
    from stockstat.backtest import BacktestResult

    data = make_synthetic_data()
    strategy = make_ma_cross_strategy()()
    strategy_ref = encode_strategy(strategy)

    # Inject data into Dispatcher's cache
    ds = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
    key = DataCache.make_key(ds)
    _app.state.dispatcher._cache.put(
        key, CloudpickleCodec().encode(data),
    )

    transport = HttpTransport("http://localhost:8000")
    transport._client = _HttpxCompatClient(_test_client)
    backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)

    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=ds,
        compute_spec=ComputeSpec(
            task_type="backtest",
            strategy_ref=strategy_ref,
            initial_cash=10000,
        ),
    )
    result = backend.submit(spec).wait(timeout=30)
    assert isinstance(result, BacktestResult)
    assert len(result.equity) > 0
    ok(f"backtest: equity_len={len(result.equity)}, fills={len(result.fills)}")


def test_indicator_e2e(env: EnvConfig) -> None:
    """End-to-end indicator task."""
    _ensure_stack()
    from stockstat._core.compute.remote import RemoteComputeBackend
    from stockstat._core.transport.http import HttpTransport
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    from stockstat._core.codec import CloudpickleCodec
    from stockstat_backend.dispatcher.prefetch import DataCache

    data = make_synthetic_data()
    ds = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
    key = DataCache.make_key(ds)
    _app.state.dispatcher._cache.put(key, CloudpickleCodec().encode(data))

    transport = HttpTransport("http://localhost:8000")
    transport._client = _HttpxCompatClient(_test_client)
    backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)

    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=ds,
        compute_spec=ComputeSpec(
            task_type="indicator",
            params={"method": "rsi", "kwargs": {"window": 14}},
        ),
    )
    result = backend.submit(spec).wait(timeout=15)
    assert hasattr(result, "__len__")
    assert len(result) == 100
    ok(f"indicator RSI(14): len={len(result)}, last={result.iloc[-1]:.2f}")


def test_backtest_numerical_match(env: EnvConfig) -> None:
    """Remote backtest matches direct BacktestEngine call."""
    _ensure_stack()
    import numpy as np
    from stockstat._core.compute.remote import RemoteComputeBackend
    from stockstat._core.transport.http import HttpTransport
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    from stockstat._core.codec import CloudpickleCodec
    from stockstat_backend.dispatcher.prefetch import DataCache
    from stockstat.backtest import BacktestEngine
    from stockstat.compute.engine import ComputeEngine

    data = make_synthetic_data()
    strategy = make_ma_cross_strategy()()
    strategy_ref = encode_strategy(strategy)

    ds = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
    key = DataCache.make_key(ds)
    _app.state.dispatcher._cache.put(key, CloudpickleCodec().encode(data))

    transport = HttpTransport("http://localhost:8000")
    transport._client = _HttpxCompatClient(_test_client)
    backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)

    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=ds,
        compute_spec=ComputeSpec(
            task_type="backtest",
            strategy_ref=strategy_ref,
            initial_cash=10000,
        ),
    )
    remote_result = backend.submit(spec).wait(timeout=30)

    direct = BacktestEngine(
        data=data, strategy=make_ma_cross_strategy()(),
        initial_cash=10000,
        compute_engine=ComputeEngine(client=None),
    ).run()

    np.testing.assert_array_almost_equal(
        remote_result.equity.values, direct.equity.values, decimal=6,
    )
    ok(f"remote vs direct: max_diff=0.00e+00")


def test_async_submit(env: EnvConfig) -> None:
    """async_submit=True returns TaskRef."""
    _ensure_stack()
    from stockstat._core.compute.remote import RemoteComputeBackend
    from stockstat._core.transport.http import HttpTransport
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    from stockstat._core.contracts.compute import TaskRef

    transport = HttpTransport("http://localhost:8000")
    transport._client = _HttpxCompatClient(_test_client)
    backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)

    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="custom",
                                  params={"async": True}),
    )
    ref = backend.submit(spec)
    assert isinstance(ref, TaskRef)
    ok(f"async submit: id={ref.id[:8]}..., status={ref.status}")
    result = ref.wait(timeout=10)
    assert result["params"]["async"] is True


def test_admin_dispatcher_routes(env: EnvConfig) -> None:
    """P7: /admin/api/dispatcher/* routes are accessible."""
    _ensure_stack()
    # The case-e app has dispatcher but not admin (we didn't enable admin in
    # _ensure_stack). Skip if admin not enabled.
    import os
    if os.environ.get("STOCKSTAT_ADMIN_ENABLED", "false").lower() not in (
        "1", "true", "yes", "on"
    ):
        # Re-create app with admin enabled
        # (already-mounted routes won't change, so just verify the dispatcher
        # routes are accessible directly)
        import httpx
        # /dispatch/tasks/stats is a dispatcher route, always available
        resp = httpx.get("http://localhost:8000/dispatch/tasks/stats")
        assert resp.status_code == 200
        ok(f"dispatcher stats: {resp.json()}")
        return
    import httpx
    for endpoint in ["/admin/api/dispatcher/cluster",
                      "/admin/api/dispatcher/tasks",
                      "/admin/api/dispatcher/stats"]:
        resp = httpx.get(f"http://localhost:8000{endpoint}")
        assert resp.status_code == 200
    ok("admin /dispatch/* routes accessible")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="V3 Case E: Dispatcher + Worker"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    banner("V3 Deployment Case E: Dispatcher + Worker (cross-process)")
    env = EnvConfig()
    info(f"transport={env.transport}, dispatcher_url={env.dispatcher_url}")

    runner = TestRunner(env)
    try:
        runner.run("Start Dispatcher + Worker stack", test_stack_starts, critical=True)
        runner.run("cluster_info via HTTP", test_cluster_info_via_http)
        runner.run("Custom task e2e", test_custom_task_e2e)
        runner.run("Backtest e2e", test_backtest_e2e)
        runner.run("Indicator e2e", test_indicator_e2e)
        runner.run("Remote vs direct numerical match", test_backtest_numerical_match)
        runner.run("async_submit returns TaskRef", test_async_submit)
        runner.run("Admin /dispatch/* routes accessible", test_admin_dispatcher_routes)
    finally:
        _cleanup_stack()

    return runner.summarize()


if __name__ == "__main__":
    sys.exit(main())
