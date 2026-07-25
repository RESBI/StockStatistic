#!/usr/bin/env python3
"""V3 Deployment Case F — Multi-level Dispatcher (parent + sub).

Scenario F from DESIGN_V3_CN §18:
- Parent Dispatcher with sub-Dispatcher(s) registered
- cluster_info includes sub_dispatchers topology
- Task history + stats accessible via Admin API

This case validates the P7 multi-level Dispatcher features:
1. Start parent Dispatcher
2. Register a sub-Dispatcher (simulated)
3. cluster_info returns full topology with sub_dispatchers
4. Submit tasks → record history → query stats
5. Autoscaler metrics accessible

Exit code: 0 on success, 1 on failure.

Usage:
    python test_case_f_multilevel.py
"""
from __future__ import annotations

import argparse
import sys
import time
import base64
from urllib.parse import urlparse

from _common import (
    EnvConfig, TestRunner, banner, step, ok, fail, info,
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


_app = None
_test_client = None
_httpx_saved = None


def _ensure_stack():
    """Initialize the Dispatcher stack with admin enabled."""
    global _app, _test_client, _httpx_saved
    if _app is not None:
        return
    import os
    os.environ["STOCKSTAT_DISPATCHER_ENABLED"] = "true"
    os.environ["STOCKSTAT_ADMIN_ENABLED"] = "true"
    from stockstat_backend.app import create_app
    from stockstat_backend.config import settings
    settings.reload()
    _app = create_app()
    _test_client, _httpx_saved = _bridge_httpx_to_app(_app)


def _cleanup_stack():
    global _httpx_saved
    if _httpx_saved is not None:
        import httpx
        httpx.post, httpx.get = _httpx_saved
        _httpx_saved = None


# ═══════════════════════════════════════════════════════════════
# Test steps
# ═══════════════════════════════════════════════════════════════


def test_stack_starts(env: EnvConfig) -> None:
    """Start parent Dispatcher with admin enabled."""
    _ensure_stack()
    import httpx
    info = httpx.get("http://localhost:8000/dispatch/cluster").json()
    assert info["dispatcher"]["status"] == "online"
    ok(f"parent dispatcher online: {info['dispatcher']['alias']}")


def test_register_sub_dispatcher(env: EnvConfig) -> None:
    """Register a sub-Dispatcher."""
    _ensure_stack()
    import httpx
    resp = httpx.post("http://localhost:8000/dispatch/sub/register", json={
        "sub_id": "sub-east-1",
        "alias": "dispatch-east",
        "address": "http://east-dispatcher:9000",
        "parent_url": "http://localhost:8000",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "registered"
    ok(f"registered sub: {resp.json()['sub_id']}")


def test_cluster_info_includes_subs(env: EnvConfig) -> None:
    """cluster_info() includes sub_dispatchers field."""
    _ensure_stack()
    import httpx
    # Register another sub
    httpx.post("http://localhost:8000/dispatch/sub/register", json={
        "sub_id": "sub-west-1", "alias": "dispatch-west",
        "address": "http://west-dispatcher:9000",
    })
    info = httpx.get("http://localhost:8000/dispatch/cluster").json()
    assert "sub_dispatchers" in info
    assert len(info["sub_dispatchers"]) >= 2
    aliases = {s["alias"] for s in info["sub_dispatchers"]}
    assert "dispatch-east" in aliases
    assert "dispatch-west" in aliases
    ok(f"cluster has {len(info['sub_dispatchers'])} sub-dispatchers")


def test_list_sub_dispatchers(env: EnvConfig) -> None:
    """GET /dispatch/sub returns the sub list."""
    _ensure_stack()
    import httpx
    resp = httpx.get("http://localhost:8000/dispatch/sub")
    assert resp.status_code == 200
    data = resp.json()
    assert "sub_dispatchers" in data
    assert len(data["sub_dispatchers"]) >= 1
    ok(f"listed {len(data['sub_dispatchers'])} sub-dispatchers")


def test_unregister_sub(env: EnvConfig) -> None:
    """Unregister a sub-Dispatcher."""
    _ensure_stack()
    import httpx
    # Register a temp sub
    httpx.post("http://localhost:8000/dispatch/sub/register", json={
        "sub_id": "temp-sub", "alias": "temp", "address": "http://temp:9000",
    })
    resp = httpx.post("http://localhost:8000/dispatch/sub/unregister/temp-sub")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unregistered"
    ok("unregistered temp-sub")


def test_task_history(env: EnvConfig) -> None:
    """Submit a task, then verify it appears in history."""
    _ensure_stack()
    import httpx
    import base64
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    from stockstat._core.codec import CloudpickleCodec

    # Submit a custom task (no worker — task stays pending, but that's OK)
    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type="custom",
                                  params={"history_test": True}),
    )
    httpx.post("http://localhost:8000/dispatch/submit",
                json=spec.to_dict())

    # Manually mark complete by calling on_complete with the slice_id
    result_b64 = base64.b64encode(
        CloudpickleCodec().encode({"done": True})
    ).decode("ascii")
    httpx.post("http://localhost:8000/dispatch/complete", json={
        "worker_id": "test-worker",
        "slice_id": spec.task_id,
        "result": result_b64,
        "result_codec": "cloudpickle",
    })

    # Query history
    resp = httpx.get("http://localhost:8000/dispatch/tasks/history")
    assert resp.status_code == 200
    history = resp.json()["history"]
    assert any(h["task_id"] == spec.task_id for h in history)
    ok(f"history has {len(history)} entries; latest task recorded")


def test_task_stats(env: EnvConfig) -> None:
    """GET /dispatch/tasks/stats returns aggregate stats."""
    _ensure_stack()
    import httpx
    resp = httpx.get("http://localhost:8000/dispatch/tasks/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert "total_tasks" in stats
    assert "by_state" in stats
    assert "by_type" in stats
    ok(f"stats: total={stats['total_tasks']}, "
       f"states={stats['by_state']}, types={stats['by_type']}")


def test_autoscaler_metrics(env: EnvConfig) -> None:
    """GET /dispatch/autoscaler returns Autoscaler metrics."""
    _ensure_stack()
    import httpx
    resp = httpx.get("http://localhost:8000/dispatch/autoscaler")
    assert resp.status_code == 200
    metrics = resp.json()
    assert "queue_depth" in metrics
    assert "scale_up_recommended" in metrics
    assert "scale_down_recommended" in metrics
    ok(f"autoscaler: queue={metrics['queue_depth']}, "
       f"scale_up={metrics['scale_up_recommended']}")


def test_admin_dispatcher_routes(env: EnvConfig) -> None:
    """P7: /admin/api/dispatcher/* routes return cluster info."""
    _ensure_stack()
    import httpx
    for endpoint in ["/admin/api/dispatcher/cluster",
                      "/admin/api/dispatcher/tasks",
                      "/admin/api/dispatcher/stats",
                      "/admin/api/dispatcher/autoscaler"]:
        resp = httpx.get(f"http://localhost:8000{endpoint}")
        assert resp.status_code == 200, f"{endpoint} returned {resp.status_code}"
    ok("all /admin/api/dispatcher/* routes accessible")


def test_discover_endpoint(env: EnvConfig) -> None:
    """P6: /dispatch/discover returns dispatcher list."""
    _ensure_stack()
    import httpx
    resp = httpx.get("http://localhost:8000/dispatch/discover")
    assert resp.status_code == 200
    data = resp.json()
    assert "dispatchers" in data
    assert data["count"] >= 1
    ok(f"discover returned {data['count']} dispatcher(s)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="V3 Case F: Multi-level Dispatcher"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    banner("V3 Deployment Case F: Multi-level Dispatcher + Monitoring")
    env = EnvConfig()
    info(f"transport={env.transport}, dispatcher_url={env.dispatcher_url}")

    runner = TestRunner(env)
    try:
        runner.run("Start parent Dispatcher (admin enabled)", test_stack_starts, critical=True)
        runner.run("Register sub-Dispatcher", test_register_sub_dispatcher)
        runner.run("cluster_info includes sub_dispatchers", test_cluster_info_includes_subs)
        runner.run("List sub-dispatchers", test_list_sub_dispatchers)
        runner.run("Unregister sub-dispatcher", test_unregister_sub)
        runner.run("Task history records completed task", test_task_history)
        runner.run("Task stats endpoint", test_task_stats)
        runner.run("Autoscaler metrics endpoint", test_autoscaler_metrics)
        runner.run("Admin /dispatch/* routes accessible", test_admin_dispatcher_routes)
        runner.run("Discover endpoint", test_discover_endpoint)
    finally:
        _cleanup_stack()

    return runner.summarize()


if __name__ == "__main__":
    sys.exit(main())
