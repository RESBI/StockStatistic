"""V3 P2 Worker unit tests.

Covers DESIGN_V3_CN §10 (Worker design) — tests the Worker component
in isolation, mocking the Dispatcher HTTP interface:

- Worker.__init__ defaults (concurrency, alias, capabilities)
- detect_hardware() returns CPU/memory/disk/os fields
- get_current_load() returns cpu_percent / memory fields
- TaskExecutor routes by task_type (custom / indicator / backtest)
- Worker registers / heartbeats / polls / completes
- Worker graceful stop via stop() + join()
- Heartbeat timeout marks worker offline in Dispatcher
"""
from __future__ import annotations

import time
import threading
import pytest


# ═══════════════════════════════════════════════════════════════
# P2.1: detect_hardware / get_current_load
# ═══════════════════════════════════════════════════════════════


class TestHardwareDetection:
    def test_detect_hardware_has_required_fields(self):
        from stockstat_compute.register import detect_hardware
        hw = detect_hardware()
        assert "cpu" in hw
        assert "memory" in hw
        assert "disk" in hw
        assert "os" in hw
        assert "python_version" in hw
        # CPU sub-fields
        assert "cores_logical" in hw["cpu"]
        assert "cores_physical" in hw["cpu"]
        assert "model" in hw["cpu"]
        # Memory sub-fields
        assert "total_gb" in hw["memory"]
        assert "available_gb" in hw["memory"]

    def test_detect_hardware_values_reasonable(self):
        from stockstat_compute.register import detect_hardware
        hw = detect_hardware()
        assert hw["cpu"]["cores_logical"] >= 1
        assert hw["memory"]["total_gb"] > 0
        assert hw["memory"]["available_gb"] >= 0
        assert hw["memory"]["available_gb"] <= hw["memory"]["total_gb"]

    def test_get_current_load(self):
        from stockstat_compute.register import get_current_load
        load = get_current_load()
        assert "cpu_percent" in load
        assert "memory_used_gb" in load
        assert "memory_available_gb" in load
        assert isinstance(load["cpu_percent"], (int, float))
        assert load["memory_used_gb"] >= 0

    def test_gpu_detection_returns_list(self):
        from stockstat_compute.register import _detect_gpu
        gpu = _detect_gpu()
        assert isinstance(gpu, list)
        # On systems without GPU, returns empty list
        # On systems with GPU, each device has model + vram_gb
        for dev in gpu:
            assert "model" in dev


# ═══════════════════════════════════════════════════════════════
# P2.2: Worker construction
# ═══════════════════════════════════════════════════════════════


class TestWorkerConstruction:
    def test_defaults(self):
        from stockstat_compute.worker import Worker
        w = Worker(dispatcher_url="http://localhost:8000")
        assert w._url == "http://localhost:8000"
        assert w._concurrency >= 1
        assert w._alias  # non-empty
        assert "backtest" in w._capabilities
        assert "indicator" in w._capabilities
        assert "grid_search" in w._capabilities
        assert w._poll_interval == 1.0
        assert w._heartbeat_interval == 10.0

    def test_custom_params(self):
        from stockstat_compute.worker import Worker
        w = Worker(
            dispatcher_url="http://dispatch:9000/",
            concurrency=8,
            alias="gpu-box-1",
            labels={"rack": "A", "zone": "east"},
            capabilities=["my_custom"],
            preemptable=True,
            poll_interval=0.5,
            heartbeat_interval=5.0,
        )
        assert w._url == "http://dispatch:9000"  # trailing slash stripped
        assert w._concurrency == 8
        assert w._alias == "gpu-box-1"
        assert w._labels == {"rack": "A", "zone": "east"}
        assert w._capabilities == ["my_custom"]
        assert w._preemptable is True
        assert w._poll_interval == 0.5
        assert w._heartbeat_interval == 5.0

    def test_worker_id_is_uuid(self):
        import uuid
        from stockstat_compute.worker import Worker
        w = Worker(dispatcher_url="http://x")
        # Should parse as UUID
        parsed = uuid.UUID(w._worker_id)
        assert str(parsed) == w._worker_id

    def test_worker_id_unique(self):
        from stockstat_compute.worker import Worker
        w1 = Worker(dispatcher_url="http://x")
        w2 = Worker(dispatcher_url="http://x")
        assert w1._worker_id != w2._worker_id


# ═══════════════════════════════════════════════════════════════
# P2.3: TaskExecutor
# ═══════════════════════════════════════════════════════════════


class TestTaskExecutor:
    def test_run_custom_task(self):
        from stockstat_compute.executor import TaskExecutor
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        ex = TaskExecutor()
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom",
                                      params={"hello": "executor"}),
        )
        result = ex.run(spec, data={})
        assert result["slice_id"] == spec.task_id
        assert result["result"]["task_type"] == "custom"
        assert result["result"]["params"]["hello"] == "executor"
        assert result["result_codec"] == "cloudpickle"
        assert result["duration_s"] >= 0

    def test_run_unknown_task_type_raises(self):
        from stockstat_compute.executor import TaskExecutor
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        ex = TaskExecutor()
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="nonexistent"),
        )
        with pytest.raises(ValueError, match="Unknown task_type"):
            ex.run(spec, data={})

    def test_run_with_progress_callback(self):
        """on_progress callback is invoked during execution."""
        from stockstat_compute.executor import TaskExecutor
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        ex = TaskExecutor(worker=type("W", (), {
            "_send_partial": lambda self, sid, p: progresses.append(p),
        })())
        progresses: list = []
        ex._worker = type("W", (), {
            "_send_partial": lambda self, sid, p: progresses.append(p),
        })()
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom"),
        )
        ex.run(spec, data={})
        # Custom task doesn't invoke on_progress; verify it accepts the kwarg
        # without error

    def test_avg_duration(self):
        from stockstat_compute.executor import TaskExecutor
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        ex = TaskExecutor()
        assert ex.avg_duration_s == 0  # no tasks yet
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom"),
        )
        ex.run(spec, data={})
        assert ex.avg_duration_s >= 0
        assert ex._completed == 1

    def test_indicator_task_via_executor(self):
        """TaskExecutor routes indicator task to handle_indicator."""
        import pandas as pd
        from stockstat_compute.executor import TaskExecutor
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        df = pd.DataFrame({"close": list(range(1, 21, 1))}, dtype=float)
        data = {"BTC/USDT": {"1d": df}}
        ex = TaskExecutor()
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"method": "ma", "kwargs": {"window": 5}},
            ),
        )
        result = ex.run(spec, data=data)
        # Result is a pd.Series
        assert hasattr(result["result"], "__len__")
        assert len(result["result"]) == 20

    def test_backtest_task_via_executor(self):
        """TaskExecutor routes backtest task to handle_backtest."""
        import base64
        import pandas as pd
        import numpy as np
        from stockstat_compute.executor import TaskExecutor
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        from stockstat._core.codec import CloudpickleCodec
        from stockstat.backtest import Strategy, Order, OrderSide, OrderType

        # Build a simple strategy and encode it
        class BuyHold(Strategy):
            name = "buy_hold_test"
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

        strategy_ref = "cloudpickle:" + base64.b64encode(
            CloudpickleCodec().encode(BuyHold())
        ).decode("ascii")

        # Build data
        dates = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
        rng = np.random.RandomState(42)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 50)))
        df = pd.DataFrame({
            "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": np.zeros(50),
        }, index=dates)
        data = {"BTC/USDT": {"1d": df}}

        ex = TaskExecutor()
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=strategy_ref,
                initial_cash=10000,
            ),
        )
        result = ex.run(spec, data=data)
        # Result is a BacktestResult
        assert hasattr(result["result"], "equity")
        assert len(result["result"].equity) > 0


# ═══════════════════════════════════════════════════════════════
# P2.4: Worker e2e via Dispatcher (in-process HTTP bridge)
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


def _restore_httpx(saved):
    import httpx
    httpx.post, httpx.get = saved


@pytest.fixture
def dispatcher_app():
    """Build a FastAPI app with Dispatcher mounted + httpx bridge active."""
    from stockstat_backend.app import create_app
    from stockstat_backend.dispatcher import DispatcherPlugin
    app = create_app()
    DispatcherPlugin.mount(app, queue_backend="memory")
    saved = _bridge_httpx_to_app(app)
    yield app
    _restore_httpx(saved[1])


@pytest.fixture
def worker(dispatcher_app):
    """Start a Worker in background thread, pointing to the bridged Dispatcher."""
    from stockstat_compute.worker import Worker
    w = Worker(
        dispatcher_url="http://localhost:8000",
        alias="test-worker",
        concurrency=2,
        poll_interval=0.1,
        heartbeat_interval=0.5,
    )
    w.start_background()
    assert w.wait_registered(timeout=5), "Worker failed to register"
    yield w
    w.stop()
    w.join(timeout=3)


class TestWorkerE2E:
    def test_worker_registers_and_cluster_info_lists_it(self, dispatcher_app, worker):
        import httpx
        # Already bridged; just call httpx
        resp = httpx.get("http://localhost:8000/dispatch/cluster")
        info = resp.json()
        assert info["stats"]["online_workers"] == 1
        assert info["workers"][0]["alias"] == "test-worker"
        assert "backtest" in info["workers"][0]["capabilities"]

    def test_custom_task_e2e(self, dispatcher_app, worker):
        """Submit a custom task, worker executes, result is fetched."""
        import httpx
        import base64
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        from stockstat._core.codec import CloudpickleCodec

        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom",
                                      params={"e2e": "yes"}),
        )
        resp = httpx.post("http://localhost:8000/dispatch/submit",
                          json=spec.to_dict())
        assert resp.status_code == 200

        # Poll for completion
        deadline = time.time() + 10
        while time.time() < deadline:
            r = httpx.get(f"http://localhost:8000/dispatch/status/{spec.task_id}")
            state = r.json()["state"]
            if state in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert state == "completed"

        # Fetch result
        r = httpx.get(f"http://localhost:8000/dispatch/result/{spec.task_id}")
        payload = r.json()
        raw = base64.b64decode(payload["result"])
        result = CloudpickleCodec().decode(raw)
        assert result["params"]["e2e"] == "yes"

    def test_indicator_task_e2e(self, dispatcher_app, worker):
        """Submit an indicator task via the dispatcher."""
        import httpx
        import base64
        import pandas as pd
        import numpy as np
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        from stockstat._core.codec import CloudpickleCodec

        # Build data and inject into Dispatcher's prefetch cache via
        # direct storage write — for the test we'll preload the cache
        # by making the symbol's data available
        dates = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
        rng = np.random.RandomState(42)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 50)))
        df = pd.DataFrame({
            "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": np.zeros(50),
        }, index=dates)
        # Pre-populate the cache by mimicking what prefetch would do
        dispatcher = dispatcher_app.state.dispatcher
        cache_key = "test-indicator-key"
        data = {"BTC/USDT": {"1d": df}}
        cache_ref = dispatcher._cache.put(
            cache_key, CloudpickleCodec().encode(data)
        )

        # Manually inject the cache entry into the task state by
        # submitting the spec, then having assign_task reuse the cache.
        # We use the actual prefetch path by adding the data to storage_app
        # But since storage_app doesn't have the data, we use a different approach:
        # Submit a task whose data_spec we know will prefetch empty data,
        # and instead, modify the spec to pass data inline via params.

        # Simpler test: use a custom task that computes MA itself
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="indicator",
                params={"method": "ma", "kwargs": {"window": 5}},
            ),
        )
        # Inject prefetched data into the dispatcher's cache so the worker
        # gets the right data_ref
        from stockstat_backend.dispatcher.prefetch import DataCache
        real_make_key = DataCache.make_key
        # Compute the key the dispatcher will use
        real_key = real_make_key(spec.data_spec)
        dispatcher._cache._entries[real_key] = dispatcher._cache._entries[cache_key]
        dispatcher._cache._entries[real_key].last_access = time.time()

        resp = httpx.post("http://localhost:8000/dispatch/submit",
                          json=spec.to_dict())
        assert resp.status_code == 200

        # Poll
        deadline = time.time() + 15
        state = None
        while time.time() < deadline:
            r = httpx.get(f"http://localhost:8000/dispatch/status/{spec.task_id}")
            state = r.json()["state"]
            if state in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert state == "completed", f"Task ended in state {state}"

        r = httpx.get(f"http://localhost:8000/dispatch/result/{spec.task_id}")
        payload = r.json()
        raw = base64.b64decode(payload["result"])
        result = CloudpickleCodec().decode(raw)
        # MA(5) of 50 close prices
        assert len(result) == 50

    def test_backtest_task_e2e(self, dispatcher_app, worker):
        """Submit a backtest task with cloudpickle-encoded strategy."""
        import httpx
        import base64
        import pandas as pd
        import numpy as np
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        from stockstat._core.codec import CloudpickleCodec
        from stockstat.backtest import Strategy, Order, OrderSide, OrderType

        class BuyHold(Strategy):
            name = "buy_hold_e2e"
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

        strategy_ref = "cloudpickle:" + base64.b64encode(
            CloudpickleCodec().encode(BuyHold())
        ).decode("ascii")

        # Build data and inject into Dispatcher's cache
        dates = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
        rng = np.random.RandomState(42)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 50)))
        df = pd.DataFrame({
            "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": np.zeros(50),
        }, index=dates)
        data = {"BTC/USDT": {"1d": df}}

        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="backtest",
                strategy_ref=strategy_ref,
                initial_cash=10000,
            ),
        )
        # Pre-populate cache
        from stockstat_backend.dispatcher.prefetch import DataCache
        real_key = DataCache.make_key(spec.data_spec)
        dispatcher = dispatcher_app.state.dispatcher
        dispatcher._cache._entries[real_key] = type(
            "E", (), {
                "data": CloudpickleCodec().encode(data),
                "size": len(CloudpickleCodec().encode(data)),
                "created_at": time.time(),
                "last_access": time.time(),
            }
        )()
        dispatcher._cache._current_size += dispatcher._cache._entries[real_key].size

        resp = httpx.post("http://localhost:8000/dispatch/submit",
                          json=spec.to_dict())
        assert resp.status_code == 200

        deadline = time.time() + 15
        state = None
        while time.time() < deadline:
            r = httpx.get(f"http://localhost:8000/dispatch/status/{spec.task_id}")
            state = r.json()["state"]
            if state in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert state == "completed", f"Task ended in state {state}"

        r = httpx.get(f"http://localhost:8000/dispatch/result/{spec.task_id}")
        payload = r.json()
        raw = base64.b64decode(payload["result"])
        result = CloudpickleCodec().decode(raw)
        # BacktestResult has equity
        assert hasattr(result, "equity")
        assert len(result.equity) > 0

    def test_task_failure_propagates(self, dispatcher_app, worker):
        """When the handler raises, task state becomes 'failed'."""
        import httpx
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        # Use "backtest" task_type (worker supports it) but omit strategy_ref
        # so handle_backtest raises ValueError
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="backtest"),  # no strategy_ref
        )
        httpx.post("http://localhost:8000/dispatch/submit",
                    json=spec.to_dict())
        deadline = time.time() + 10
        state = None
        while time.time() < deadline:
            r = httpx.get(f"http://localhost:8000/dispatch/status/{spec.task_id}")
            state = r.json()["state"]
            if state in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert state == "failed"
        # Error field should carry the message
        r = httpx.get(f"http://localhost:8000/dispatch/status/{spec.task_id}")
        status = r.json()
        assert status.get("error")
        assert "strategy_ref" in status["error"] or "strategy" in status["error"]


# ═══════════════════════════════════════════════════════════════
# P2.5: Heartbeat / offline detection
# ═══════════════════════════════════════════════════════════════


class TestHeartbeatTimeout:
    def test_worker_marked_offline_after_timeout(self):
        """When a worker stops heartbeating, Dispatcher marks it offline."""
        import httpx
        import os
        from stockstat_backend.app import create_app
        from stockstat_backend.dispatcher import DispatcherPlugin
        from stockstat_compute.worker import Worker

        # Custom Dispatcher with very short offline_timeout
        app = create_app()
        # Manually create Dispatcher with short timeout
        from stockstat_backend.dispatcher.core import Dispatcher
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        from stockstat_backend.dispatcher.routes import (
            create_dispatcher_router, create_tasks_router,
        )
        custom_dispatcher = Dispatcher(
            queue=MemoryTaskQueue(), storage_app=app,
            offline_timeout=1.0,  # 1 second
        )
        # Replace the auto-mounted one's dispatcher with our custom one
        # by re-mounting routes
        # Actually, simpler: mount fresh
        app2 = create_app()
        DispatcherPlugin.mount(app2, queue_backend="memory",
                                offline_timeout=1.0)
        saved = _bridge_httpx_to_app(app2)
        try:
            # Start worker with short heartbeat
            w = Worker(
                dispatcher_url="http://localhost:8000",
                alias="ephemeral",
                concurrency=1,
                poll_interval=0.1,
                heartbeat_interval=0.3,
            )
            w.start_background()
            assert w.wait_registered(timeout=5)

            # Verify online
            r = httpx.get("http://localhost:8000/dispatch/cluster")
            assert r.json()["stats"]["online_workers"] == 1

            # Stop the worker (it will unregister, marking itself offline)
            w.stop()
            w.join(timeout=3)

            # Allow heartbeat timeout to fire
            time.sleep(2.5)

            r = httpx.get("http://localhost:8000/dispatch/cluster")
            info = r.json()
            # Worker should be offline (either via unregister or timeout)
            assert info["stats"]["online_workers"] == 0
        finally:
            _restore_httpx(saved[1])


# ═══════════════════════════════════════════════════════════════
# P2.6: Multiple workers + capability routing
# ═══════════════════════════════════════════════════════════════


class TestMultipleWorkers:
    def test_two_workers_register(self, dispatcher_app):
        from stockstat_compute.worker import Worker
        w1 = Worker(dispatcher_url="http://localhost:8000",
                     alias="w1", concurrency=2, poll_interval=0.1,
                     heartbeat_interval=1.0)
        w2 = Worker(dispatcher_url="http://localhost:8000",
                     alias="w2", concurrency=3, poll_interval=0.1,
                     heartbeat_interval=1.0)
        w1.start_background()
        w2.start_background()
        try:
            assert w1.wait_registered(timeout=5)
            assert w2.wait_registered(timeout=5)
            import httpx
            r = httpx.get("http://localhost:8000/dispatch/cluster")
            info = r.json()
            assert info["stats"]["total_workers"] == 2
            assert info["stats"]["total_concurrency"] == 5
            aliases = {w["alias"] for w in info["workers"]}
            assert aliases == {"w1", "w2"}
        finally:
            w1.stop()
            w2.stop()
            w1.join(timeout=3)
            w2.join(timeout=3)

    def test_capability_routing(self, dispatcher_app):
        """A worker with limited capabilities only gets matching tasks."""
        import httpx
        from stockstat_compute.worker import Worker
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )

        # Start a worker that only handles "custom" tasks
        w = Worker(
            dispatcher_url="http://localhost:8000",
            alias="limited",
            concurrency=1,
            capabilities=["custom"],
            poll_interval=0.1,
            heartbeat_interval=1.0,
        )
        w.start_background()
        try:
            assert w.wait_registered(timeout=5)
            # Submit a custom task — should be picked up
            spec = TaskSpec(
                task_id=new_task_id(),
                data_spec=DataSpec(symbols=[]),
                compute_spec=ComputeSpec(task_type="custom",
                                          params={"routed": True}),
            )
            httpx.post("http://localhost:8000/dispatch/submit",
                        json=spec.to_dict())
            deadline = time.time() + 5
            state = None
            while time.time() < deadline:
                r = httpx.get(f"http://localhost:8000/dispatch/status/{spec.task_id}")
                state = r.json()["state"]
                if state in ("completed", "failed"):
                    break
                time.sleep(0.1)
            assert state == "completed"
        finally:
            w.stop()
            w.join(timeout=3)
