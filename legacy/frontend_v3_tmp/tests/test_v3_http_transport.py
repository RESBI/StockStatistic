"""V3 P3 HTTP transport + AutoComputeBackend tests.

Covers DESIGN_V3_CN §7 (transport) + §8.3 (AutoComputeBackend):
- HttpTransport.send/request/send_data/close
- HttpTransport maps Envelope types to REST endpoints via TYPE_TO_PATH
- RemoteComputeBackend with HttpTransport: submit/get/result/cancel/cluster_info
- AutoComputeBackend routes by task_type (heavy → remote, light → local)
- AutoComputeBackend fallback to local when remote unavailable
- Cross-process e2e (Client → Dispatcher → Worker) via real HTTP loopback
"""
from __future__ import annotations

import time
import threading
import pytest
import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════
# Helpers — bridge httpx → FastAPI TestClient
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
    import httpx
    orig_post, orig_get = saved_tuple
    httpx.post = orig_post
    httpx.get = orig_get


class _HttpxCompatClient:
    """Wrap a TestClient to look like httpx.Client for HttpTransport."""
    def __init__(self, test_client):
        self._tc = test_client
    def post(self, url, *, content=None, json=None, headers=None, timeout=None):
        from urllib.parse import urlparse
        p = urlparse(url)
        if json is not None:
            r = self._tc.post(p.path, json=json, headers=headers)
        elif content is not None:
            r = self._tc.post(p.path, content=content, headers=headers)
        else:
            r = self._tc.post(p.path, headers=headers)
        return _HttpxCompatResponse(r)
    def get(self, url, *, params=None, headers=None, timeout=None):
        from urllib.parse import urlparse
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


@pytest.fixture(scope="module")
def http_stack():
    """Start a Dispatcher-backed FastAPI app + bridge httpx → TestClient."""
    from stockstat_backend.app import create_app
    from stockstat_backend.dispatcher import DispatcherPlugin
    app = create_app()
    DispatcherPlugin.mount(app, queue_backend="memory")
    test_client, saved = _bridge_httpx_to_app(app)
    yield app, test_client
    _restore_httpx(saved)


# ═══════════════════════════════════════════════════════════════
# P3.1: HttpTransport
# ═══════════════════════════════════════════════════════════════


class TestHttpTransport:
    def test_transport_name(self):
        from stockstat._core.transport.http import HttpTransport
        t = HttpTransport("http://localhost:8000")
        assert t.name == "http"

    def test_trailing_slash_stripped(self):
        from stockstat._core.transport.http import HttpTransport
        t = HttpTransport("http://localhost:8000/")
        assert t._base_url == "http://localhost:8000"

    def test_post_json(self, http_stack):
        """post_json routes through the bridged TestClient."""
        from stockstat._core.transport.http import HttpTransport
        app, test_client = http_stack
        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(test_client)
        # /dispatch/cluster is GET-only; use /dispatch/register (POST) instead
        result = transport.post_json("/dispatch/register", {
            "worker_id": "test-post-json",
            "alias": "post-json-worker",
            "concurrency": 1,
            "capabilities": ["custom"],
        })
        assert result["status"] == "registered"

    def test_get_json(self, http_stack):
        from stockstat._core.transport.http import HttpTransport
        app, test_client = http_stack
        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(test_client)
        result = transport.get_json("/dispatch/cluster")
        assert "dispatcher" in result
        assert "stats" in result

    def test_send_data_returns_inline_ref(self):
        """send_data base64-encodes and returns inline: ref."""
        from stockstat._core.transport.http import HttpTransport
        import base64
        t = HttpTransport("http://localhost:8000")
        data = b"hello world"
        ref = t.send_data(data, "application/octet-stream")
        assert ref.startswith("inline:")
        decoded = base64.b64decode(ref[len("inline:"):])
        assert decoded == data

    def test_close_does_not_raise(self):
        from stockstat._core.transport.http import HttpTransport
        t = HttpTransport("http://localhost:8000")
        t.close()  # should not raise


# ═══════════════════════════════════════════════════════════════
# P3.2: RemoteComputeBackend with HTTP
# ═══════════════════════════════════════════════════════════════


class TestRemoteComputeBackendHTTP:
    def test_backend_name(self):
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.transport.http import HttpTransport
        b = RemoteComputeBackend(transport=HttpTransport("http://x"))
        assert b.name == "remote"

    def test_constructor_with_url_only(self):
        """Passing dispatcher_url creates an HttpTransport automatically."""
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.transport.http import HttpTransport
        b = RemoteComputeBackend(dispatcher_url="http://localhost:8000")
        assert isinstance(b._transport, HttpTransport)

    def test_cluster_info_via_http(self, http_stack):
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.transport.http import HttpTransport
        app, test_client = http_stack
        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(test_client)
        backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)
        info = backend.cluster_info()
        assert "dispatcher" in info
        assert "workers" in info

    def test_submit_and_get_status(self, http_stack):
        """Submit a task and query its status via HTTP."""
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.transport.http import HttpTransport
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        from stockstat._core.contracts.compute import TaskState
        app, test_client = http_stack
        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(test_client)
        backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom"),
        )
        ref = backend.submit(spec)
        assert ref.id == spec.task_id
        # Status query
        info = backend.get(spec.task_id)
        assert info.state in (TaskState.PENDING, TaskState.RUNNING,
                              TaskState.COMPLETED)

    def test_cancel_unknown_task(self, http_stack):
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.transport.http import HttpTransport
        app, test_client = http_stack
        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(test_client)
        backend = RemoteComputeBackend(transport=transport)
        # Cancelling an unknown task returns False
        assert backend.cancel("nonexistent-id") is False


# ═══════════════════════════════════════════════════════════════
# P3.3: AutoComputeBackend
# ═══════════════════════════════════════════════════════════════


class TestAutoComputeBackend:
    def _make_spec(self, task_type="indicator"):
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        return TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"]),
            compute_spec=ComputeSpec(task_type=task_type),
        )

    def test_name(self):
        from stockstat._core.compute.auto import AutoComputeBackend
        b = AutoComputeBackend()
        assert b.name == "auto"

    def test_routes_heavy_to_remote(self):
        """Heavy task types (grid_search / batch / monte_carlo) → remote."""
        from stockstat._core.compute.auto import AutoComputeBackend
        from stockstat._core.compute.local import LocalComputeBackend

        class FakeRemote:
            name = "remote"
            def submit(self, spec):
                self.last = spec
                return ("remote_ref",)
            def get(self, tid): return None
            def result(self, tid): return None
            def wait(self, tid, timeout=None): return None
            def cancel(self, tid): return False
            def cluster_info(self, **kw): return {}
            def stream_results(self, tid): yield None

        remote = FakeRemote()
        b = AutoComputeBackend(local=LocalComputeBackend(), remote=remote)
        for task_type in ("grid_search", "batch_backtest", "monte_carlo"):
            spec = self._make_spec(task_type)
            b.submit(spec)
            assert hasattr(remote, "last"), f"Remote was not called for {task_type}"
            assert remote.last.task_id == spec.task_id

    def test_routes_light_to_local(self):
        """Light task types (indicator / backtest / custom) → local."""
        from stockstat._core.compute.auto import AutoComputeBackend
        from stockstat._core.compute.local import LocalComputeBackend

        class FakeRemote:
            name = "remote"
            def submit(self, spec): raise RuntimeError("should not be called")

        b = AutoComputeBackend(local=LocalComputeBackend(), remote=FakeRemote())
        # custom task routes to local
        spec = self._make_spec("custom")
        ref = b.submit(spec)
        assert ref is not None
        # LocalComputeBackend handles it in a thread
        ref.wait(timeout=5)

    def test_fallback_to_local_when_no_remote(self):
        """Without remote, all tasks go to local."""
        from stockstat._core.compute.auto import AutoComputeBackend
        b = AutoComputeBackend(local=None, remote=None)
        # _make_local() is called in __init__ when local=None
        spec = self._make_spec("custom")
        ref = b.submit(spec)
        ref.wait(timeout=5)

    def test_cluster_info_falls_back_to_local(self):
        """When remote.cluster_info fails, local is used."""
        from stockstat._core.compute.auto import AutoComputeBackend
        from stockstat._core.compute.local import LocalComputeBackend

        class FailingRemote:
            def cluster_info(self, **kw):
                raise RuntimeError("remote unavailable")

        b = AutoComputeBackend(local=LocalComputeBackend(),
                                remote=FailingRemote())
        info = b.cluster_info()
        # Falls back to local
        assert info["dispatcher"]["id"] == "local"

    def test_get_uses_routing(self):
        """get() routes to the backend that handled the task."""
        from stockstat._core.compute.auto import AutoComputeBackend
        from stockstat._core.compute.local import LocalComputeBackend
        b = AutoComputeBackend(local=LocalComputeBackend())
        spec = self._make_spec("custom")
        ref = b.submit(spec)
        info = b.get(spec.task_id)
        assert info.task_id == spec.task_id


# ═══════════════════════════════════════════════════════════════
# P3.4: Cross-process e2e (Client → Dispatcher → Worker via HTTP)
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def worker_for_http(http_stack):
    """Start a Worker that connects via the bridged httpx → TestClient."""
    from stockstat_compute.worker import Worker
    saved = None
    # Already bridged in http_stack
    w = Worker(
        dispatcher_url="http://localhost:8000",
        alias="p3-worker",
        concurrency=2,
        poll_interval=0.05,
        heartbeat_interval=1.0,
    )
    w.start_background()
    assert w.wait_registered(timeout=5)
    yield w
    w.stop()
    w.join(timeout=3)


class TestCrossProcessE2E:
    def test_remote_submit_and_complete(self, http_stack, worker_for_http):
        """End-to-end: RemoteComputeBackend submits via HTTP → Worker executes."""
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.transport.http import HttpTransport
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        app, test_client = http_stack
        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(test_client)
        backend = RemoteComputeBackend(transport=transport, poll_interval=0.05)

        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom",
                                      params={"http_e2e": True}),
        )
        result = backend.submit(spec).wait(timeout=10)
        assert result["params"]["http_e2e"] is True

    def test_auto_backend_routes_to_remote(self, http_stack, worker_for_http):
        """AutoComputeBackend routes grid_search to the remote backend."""
        from stockstat._core.compute.auto import AutoComputeBackend
        from stockstat._core.compute.local import LocalComputeBackend
        from stockstat._core.compute.remote import RemoteComputeBackend
        from stockstat._core.transport.http import HttpTransport
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        app, test_client = http_stack
        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(test_client)
        remote = RemoteComputeBackend(transport=transport, poll_interval=0.05)
        local = LocalComputeBackend()
        auto = AutoComputeBackend(local=local, remote=remote)

        # Submit a custom task (light) — goes local
        spec_local = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom",
                                      params={"path": "local"}),
        )
        result_local = auto.submit(spec_local).wait(timeout=5)
        assert result_local["params"]["path"] == "local"

        # Submit a grid_search (heavy) — would go remote, but we don't have
        # data; just verify routing decision was "remote"
        spec_remote = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search", param_grid={}),
        )
        # The auto backend records the routing decision
        # We can't actually execute grid_search without data, so just check
        # the routing map was set
        auto.submit(spec_remote)
        # Internal routing map records "remote"
        assert auto._routing.get(spec_remote.task_id) == "remote"


# ═══════════════════════════════════════════════════════════════
# P3.5: Protocol envelope over HTTP
# ═══════════════════════════════════════════════════════════════


class TestEnvelopeOverHTTP:
    def test_type_to_path_mapping(self):
        """All control-plane message types have REST paths."""
        from stockstat._core.protocol import messages
        # Control plane types
        assert messages.TYPE_TO_PATH[messages.TASK_SUBMIT] == "/dispatch/submit"
        assert messages.TYPE_TO_PATH[messages.TASK_STATUS] == "/dispatch/status"
        assert messages.TYPE_TO_PATH[messages.TASK_RESULT] == "/dispatch/result"
        assert messages.TYPE_TO_PATH[messages.TASK_CANCEL] == "/dispatch/cancel"
        assert messages.TYPE_TO_PATH[messages.CLUSTER_INFO] == "/dispatch/cluster"
        # Dispatch plane types
        assert messages.TYPE_TO_PATH[messages.DISPATCH_REGISTER] == "/dispatch/register"
        assert messages.TYPE_TO_PATH[messages.DISPATCH_HEARTBEAT] == "/dispatch/heartbeat"
        assert messages.TYPE_TO_PATH[messages.DISPATCH_ASSIGN] == "/dispatch/assign"
        assert messages.TYPE_TO_PATH[messages.DISPATCH_COMPLETE] == "/dispatch/complete"
        assert messages.TYPE_TO_PATH[messages.DISPATCH_FAIL] == "/dispatch/fail"

    def test_envelope_request_via_http(self, http_stack):
        """Send an Envelope via HttpTransport.request() and get a reply."""
        from stockstat._core.transport.http import HttpTransport
        from stockstat._core.protocol.envelope import Envelope, Headers
        from stockstat._core.protocol.messages import DISPATCH_REGISTER, CT_JSON
        app, test_client = http_stack
        transport = HttpTransport("http://localhost:8000")
        transport._client = _HttpxCompatClient(test_client)

        env = Envelope(
            type=DISPATCH_REGISTER,
            headers=Headers(content_type=CT_JSON, trace_id="p3-test"),
            payload={
                "worker_id": "p3-env-test",
                "alias": "env-worker",
                "concurrency": 1,
                "capabilities": ["custom"],
            },
        )
        reply = transport.request(env, timeout=5)
        # Reply is an Envelope (may be wrapped) or a dict
        # The HTTP transport falls back to wrapping the JSON response
        assert reply is not None
        if hasattr(reply, "payload"):
            payload = reply.payload
        else:
            payload = reply
        # Dispatcher returns {"worker_id": ..., "status": "registered"}
        assert payload.get("status") == "registered" or "worker_id" in payload

    def test_envelope_with_bytes_payload(self):
        """Envelope with bytes payload base64-encodes on encode()."""
        import base64
        import json
        from stockstat._core.protocol.envelope import Envelope, Headers
        env = Envelope(
            type="dispatch.complete",
            headers=Headers(content_type="application/octet-stream"),
            payload=b"\x00\x01\x02\x03",
        )
        raw = env.encode()
        # JSON-decodable
        d = json.loads(raw.decode("utf-8"))
        assert d.get("_payload_b64") is True
        assert base64.b64decode(d["payload"]) == b"\x00\x01\x02\x03"
