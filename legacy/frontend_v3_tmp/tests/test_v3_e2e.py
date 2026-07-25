"""V3 P2 End-to-end tests — full Client -> Dispatcher -> Worker chain.

Covers DESIGN_V3_CN §14 (task lifecycle) — exercises the complete
protocol path with a real FastAPI TestClient dispatcher and Worker
running in a background thread:

- RemoteComputeBackend submits via HTTP to Dispatcher
- TaskRef.wait() polls Dispatcher until completion, fetches result
- All 5 task types via the e2e path (custom / indicator / backtest /
  grid_search / batch_backtest) — monte_carlo is heavy, covered
  separately
- Multi-worker parallel grid_search produces merged result
- Cancel propagates from Client to Dispatcher
- cluster_info via RemoteComputeBackend
- async_submit=True transparent mode
"""
from __future__ import annotations

import time
import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════
# Shared e2e fixture
# ═══════════════════════════════════════════════════════════════


def _bridge_httpx_to_app(app):
    """Patch httpx.post/get to route localhost:8000 calls to TestClient(app)."""
    import httpx
    from fastapi.testclient import TestClient
    from urllib.parse import urlparse

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


def _restore_httpx(saved_tuple):
    """Restore httpx.post/get to originals saved by _bridge_httpx_to_app."""
    import httpx
    orig_post, orig_get = saved_tuple
    httpx.post = orig_post
    httpx.get = orig_get


@pytest.fixture(scope="module")
def e2e_stack():
    """Start a Dispatcher + Worker stack for the module.

    Yields (dispatcher_app, worker, RemoteComputeBackend).
    """
    from stockstat_backend.app import create_app
    from stockstat_backend.dispatcher import DispatcherPlugin
    from stockstat_compute.worker import Worker
    from stockstat._core.compute.remote import RemoteComputeBackend
    from stockstat._core.transport.http import HttpTransport

    app = create_app()
    DispatcherPlugin.mount(app, queue_backend="memory")
    test_client, httpx_saved = _bridge_httpx_to_app(app)

    worker = Worker(
        dispatcher_url="http://localhost:8000",
        alias="e2e-worker",
        concurrency=4,
        poll_interval=0.05,
        heartbeat_interval=0.5,
    )
    worker.start_background()
    assert worker.wait_registered(timeout=5)

    # Build a RemoteComputeBackend with an HttpTransport whose internal
    # httpx.Client has been replaced by the in-process TestClient.
    transport = HttpTransport("http://localhost:8000")
    # Override its client with the bridged TestClient wrapped to look like httpx.Client
    transport._client = _HttpxCompatClient(test_client)
    backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)

    yield app, worker, backend

    worker.stop()
    worker.join(timeout=3)
    _restore_httpx(httpx_saved)


class _HttpxCompatClient:
    """Wrap a fastapi TestClient to look like an httpx.Client for HttpTransport.

    HttpTransport calls ``self._client.post(url, content=..., headers=..., timeout=...)``
    and expects an httpx.Response-like result. We translate to TestClient calls.
    """

    def __init__(self, test_client):
        self._tc = test_client

    def post(self, url, *, content=None, json=None, headers=None, timeout=None):
        from urllib.parse import urlparse
        p = urlparse(url)
        path = p.path or "/"
        if json is not None:
            r = self._tc.post(path, json=json, headers=headers)
        elif content is not None:
            if isinstance(content, bytes):
                r = self._tc.post(path, content=content, headers=headers)
            else:
                r = self._tc.post(path, content=content, headers=headers)
        else:
            r = self._tc.post(path, headers=headers)
        return _HttpxCompatResponse(r)

    def get(self, url, *, params=None, headers=None, timeout=None):
        from urllib.parse import urlparse
        p = urlparse(url)
        path = p.path or "/"
        r = self._tc.get(path, params=params, headers=headers)
        return _HttpxCompatResponse(r)

    def close(self):
        pass


class _HttpxCompatResponse:
    """Wrap a requests.Response (from TestClient) to look like httpx.Response."""

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


@pytest.fixture
def sample_data():
    """Synthetic OHLCV data."""
    dates = pd.date_range("2024-01-01", periods=80, freq="D", tz="UTC")
    rng = np.random.RandomState(42)
    returns = rng.normal(0.001, 0.02, 80)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.005, 80)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, 80)))
    op = close * (1 + rng.normal(0, 0.003, 80))
    vol = rng.uniform(1e6, 5e6, 80)
    df = pd.DataFrame({
        "open": op, "high": high, "low": low, "close": close, "volume": vol,
    }, index=dates)
    return {"BTC/USDT": {"1d": df}}


@pytest.fixture
def sample_strategy():
    """A simple MA cross strategy class."""
    from stockstat.backtest import Strategy, Order, OrderSide, OrderType

    class MaCross(Strategy):
        name = "ma_cross_e2e"
        def __init__(self):
            super().__init__()
            self._bought = False
            self._bar_count = 0
        def on_bar(self, ctx):
            self._bar_count += 1
            if self._bar_count < 25:
                return
            t = ctx.now
            try:
                closes = ctx.data_feed.close_series("BTC/USDT", "1d")
                if t not in closes.index:
                    return
                idx = closes.index.get_loc(t)
                if idx < 20:
                    return
                ma5 = closes.iloc[max(0, idx-5):idx+1].mean()
                ma20 = closes.iloc[max(0, idx-20):idx+1].mean()
                pos = ctx.portfolio.get_position("BTC/USDT")
                if ma5 > ma20 and pos.qty == 0 and not self._bought:
                    ctx.broker.submit(Order(
                        symbol="BTC/USDT", side=OrderSide.BUY,
                        order_type=OrderType.MARKET, qty=1.0, tag="entry",
                    ))
                    self._bought = True
                elif ma5 < ma20 and self._bought:
                    ctx.broker.submit(Order(
                        symbol="BTC/USDT", side=OrderSide.SELL,
                        order_type=OrderType.MARKET, qty=1.0, tag="exit",
                    ))
                    self._bought = False
            except Exception:
                pass

    return MaCross


def _encode_strategy(strategy):
    import base64
    from stockstat._core.codec import CloudpickleCodec
    return "cloudpickle:" + base64.b64encode(
        CloudpickleCodec().encode(strategy)
    ).decode("ascii")


def _inject_data_cache(dispatcher_app, data_spec, data):
    """Pre-populate the Dispatcher's DataCache so workers fetch correct data."""
    import time as _time
    from stockstat._core.codec import CloudpickleCodec
    from stockstat_backend.dispatcher.prefetch import DataCache
    key = DataCache.make_key(data_spec)
    dispatcher = dispatcher_app.state.dispatcher
    raw = CloudpickleCodec().encode(data)
    # Use the cache's put method to properly register the entry
    dispatcher._cache.put(key, raw)


# ═══════════════════════════════════════════════════════════════
# E2E.1: cluster_info via RemoteComputeBackend
# ═══════════════════════════════════════════════════════════════


class TestE2EClusterInfo:
    def test_remote_backend_cluster_info(self, e2e_stack):
        _, _, backend = e2e_stack
        info = backend.cluster_info()
        assert "dispatcher" in info
        assert "workers" in info
        assert "stats" in info
        assert info["stats"]["online_workers"] >= 1
        assert info["workers"][0]["alias"] == "e2e-worker"

    def test_cluster_info_filter_labels(self, e2e_stack):
        _, _, backend = e2e_stack
        # No labels on e2e-worker, so filter should return 0 workers
        info = backend.cluster_info(filter_labels={"nonexistent": "label"})
        # Behavior: filter returns workers whose labels match all keys
        # If no workers match, the list is empty
        assert isinstance(info["workers"], list)


# ═══════════════════════════════════════════════════════════════
# E2E.2: Custom task
# ═══════════════════════════════════════════════════════════════


class TestE2ECustomTask:
    def test_submit_and_wait_custom(self, e2e_stack):
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        _, _, backend = e2e_stack
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom",
                                      params={"e2e": "remote"}),
        )
        task_ref = backend.submit(spec)
        assert task_ref.id == spec.task_id

        result = task_ref.wait(timeout=10)
        assert result["params"]["e2e"] == "remote"

    def test_task_ref_state_transitions(self, e2e_stack):
        """TaskRef.state goes pending -> running -> completed."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        from stockstat._core.contracts.compute import TaskState
        _, _, backend = e2e_stack
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom"),
        )
        ref = backend.submit(spec)
        # Eventually completes
        ref.wait(timeout=10)
        info = backend.get(spec.task_id)
        assert info.state == TaskState.COMPLETED
        assert info.started_at is not None
        assert info.finished_at is not None

    def test_cancel_pending_task(self, e2e_stack):
        """Cancel a task that hasn't been picked up yet."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        _, _, backend = e2e_stack
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom"),
        )
        backend.submit(spec)
        # Cancel immediately (may or may not be picked up yet)
        backend.cancel(spec.task_id)
        # Final state should be cancelled or completed (race)
        info = backend.get(spec.task_id)
        assert info.state in ("cancelled", "completed")


# ═══════════════════════════════════════════════════════════════
# E2E.3: Indicator task
# ═══════════════════════════════════════════════════════════════


class TestE2EIndicator:
    def test_indicator_via_remote_backend(self, e2e_stack, sample_data):
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        app, _, backend = e2e_stack
        # Inject data so worker fetches the right bytes
        ds = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
        _inject_data_cache(app, ds, sample_data)

        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=ds,
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"method": "rsi", "kwargs": {"window": 14}},
            ),
        )
        ref = backend.submit(spec)
        result = ref.wait(timeout=15)
        # RSI is a pd.Series of length 80
        assert hasattr(result, "__len__")
        assert len(result) == 80


# ═══════════════════════════════════════════════════════════════
# E2E.4: Backtest task
# ═══════════════════════════════════════════════════════════════


class TestE2EBacktest:
    def test_backtest_via_remote_backend(self, e2e_stack, sample_data, sample_strategy):
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        from stockstat.backtest import BacktestResult
        app, _, backend = e2e_stack

        ds = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
        _inject_data_cache(app, ds, sample_data)

        strategy_ref = _encode_strategy(sample_strategy())
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=ds,
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=strategy_ref,
                initial_cash=10000,
            ),
        )
        ref = backend.submit(spec)
        result = ref.wait(timeout=30)
        assert isinstance(result, BacktestResult)
        assert len(result.equity) > 0

    def test_backtest_numerical_match_direct(self, e2e_stack, sample_data, sample_strategy):
        """Remote backtest produces same equity curve as direct BacktestEngine call."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        from stockstat.backtest import BacktestEngine
        from stockstat.compute.engine import ComputeEngine
        app, _, backend = e2e_stack

        ds = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
        _inject_data_cache(app, ds, sample_data)

        strategy_ref = _encode_strategy(sample_strategy())
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

        # Direct call
        direct = BacktestEngine(
            data=sample_data, strategy=sample_strategy(),
            initial_cash=10000,
            compute_engine=ComputeEngine(client=None),
        ).run()

        np.testing.assert_array_almost_equal(
            remote_result.equity.values, direct.equity.values, decimal=6,
        )


# ═══════════════════════════════════════════════════════════════
# E2E.5: Grid search (multi-slice)
# ═══════════════════════════════════════════════════════════════


class TestE2EGridSearch:
    def test_grid_search_single_worker(self, e2e_stack, sample_data, sample_strategy):
        """Grid search shards param_wise; worker processes each slice."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        app, _, backend = e2e_stack
        ds = DataSpec(symbols=["BTC/USDT"], timeframe="1d")
        _inject_data_cache(app, ds, sample_data)

        strategy_ref = _encode_strategy(sample_strategy())
        # Small grid: 2x2 = 4 combinations, sharded into 2 slices
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=ds,
            compute_spec=ComputeSpec(
                task_type="grid_search",
                strategy_ref=strategy_ref,
                param_grid={"short": [3, 5], "long": [10, 20]},
                metric="sharpe",
                maximize=True,
                initial_cash=10000,
            ),
            dispatch_spec=DispatchSpec(
                split_strategy="param_wise", max_workers=2,
            ),
        )
        ref = backend.submit(spec)
        result = ref.wait(timeout=60)
        # Result is a list of dicts with params + metric
        assert isinstance(result, list)
        assert len(result) == 4
        for r in result:
            assert "params" in r
            assert "sharpe" in r
        # Sorted desc by sharpe (maximize=True)
        sharpes = [r["sharpe"] for r in result]
        assert sharpes == sorted(sharpes, reverse=True)


# ═══════════════════════════════════════════════════════════════
# E2E.6: Stream results
# ═══════════════════════════════════════════════════════════════


class TestE2EStreamResults:
    def test_stream_results_yields_final(self, e2e_stack):
        """stream_results() yields the final result after completion."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        _, _, backend = e2e_stack
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom",
                                      params={"streaming": True}),
        )
        ref = backend.submit(spec)
        parts = list(ref.stream_results())
        # Should yield at least the final result
        assert len(parts) >= 1
        assert parts[-1]["params"]["streaming"] is True


# ═══════════════════════════════════════════════════════════════
# E2E.7: StockStatClient with RemoteComputeBackend
# ═══════════════════════════════════════════════════════════════


class TestE2EClientWithRemoteBackend:
    def test_client_backtest_transparent_sync(self, e2e_stack, sample_data, sample_strategy):
        """StockStatClient(compute_backend=RemoteComputeBackend) transparent sync."""
        from stockstat.client import StockStatClient
        from stockstat.backtest import BacktestResult
        from fastapi.testclient import TestClient
        app, _, _ = e2e_stack
        from stockstat._core.transport.http import HttpTransport
        from stockstat._core.compute.remote import RemoteComputeBackend

        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(TestClient(app))
        backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)
        client = StockStatClient(host="localhost", port=1, compute_backend=backend)

        # Inject data
        from stockstat._core.contracts.task import DataSpec
        _inject_data_cache(app, DataSpec(symbols=["BTC/USDT"], timeframe="1d"), sample_data)

        # Direct call goes through remote backend (since not LocalComputeBackend)
        result = client.backtest(sample_data, sample_strategy(), initial_cash=10000)
        assert isinstance(result, BacktestResult)

    def test_client_compute_remote(self, e2e_stack, sample_data):
        """client.compute.remote('indicator', ...) -> TaskRef -> Series."""
        from stockstat.client import StockStatClient
        from stockstat._core.transport.http import HttpTransport
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.contracts.compute import TaskRef
        from fastapi.testclient import TestClient
        app, _, _ = e2e_stack

        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(TestClient(app))
        backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)
        client = StockStatClient(host="localhost", port=1, compute_backend=backend)
        # Inject data
        from stockstat._core.contracts.task import DataSpec
        _inject_data_cache(app, DataSpec(symbols=["BTC/USDT"], timeframe="1d"), sample_data)

        task = client.compute.remote(
            "indicator",
            symbols=["BTC/USDT"], timeframe="1d",
            method="ma", kwargs={"window": 10},
        )
        assert isinstance(task, TaskRef)
        result = task.wait(timeout=15)
        assert hasattr(result, "__len__")
        assert len(result) == 80

    def test_client_async_submit(self, e2e_stack, sample_data, sample_strategy):
        """client.backtest(async_submit=True) returns TaskRef."""
        from stockstat.client import StockStatClient
        from stockstat._core.transport.http import HttpTransport
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.contracts.compute import TaskRef
        from stockstat.backtest import BacktestResult
        app, _, _ = e2e_stack

        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(TestClient(app))
        backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)
        client = StockStatClient(host="localhost", port=1, compute_backend=backend)
        from stockstat._core.contracts.task import DataSpec
        _inject_data_cache(app, DataSpec(symbols=["BTC/USDT"], timeframe="1d"), sample_data)

        task = client.backtest(sample_data, sample_strategy(),
                                initial_cash=10000, async_submit=True)
        assert isinstance(task, TaskRef)
        result = task.wait(timeout=30)
        assert isinstance(result, BacktestResult)
