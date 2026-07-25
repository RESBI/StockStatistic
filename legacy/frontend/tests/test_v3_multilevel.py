"""V3 P7 Multi-level Dispatcher + Admin monitoring tests.

Covers DESIGN_V3_CN §20.7 (P7) + §18 (deployment scenarios):
- Dispatcher.register_sub_dispatcher / unregister / list
- cluster_info includes sub_dispatchers field
- Task history recording on complete/fail
- get_task_history / get_task_stats for Admin UI
- Admin Plugin /admin/api/dispatcher/* endpoints (when dispatcher enabled)
- Multi-level topology: parent + sub-dispatcher cluster_info
"""
from __future__ import annotations

import time
import pytest


# ═══════════════════════════════════════════════════════════════
# P7.1: Multi-level Dispatcher
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def dispatcher():
    from stockstat_backend.dispatcher.core import Dispatcher
    from stockstat_backend.dispatcher.queue import MemoryTaskQueue
    return Dispatcher(queue=MemoryTaskQueue())


class TestSubDispatcher:
    def test_register_sub_dispatcher(self, dispatcher):
        result = dispatcher.register_sub_dispatcher(
            sub_id="sub-1",
            alias="dispatch-child-east",
            address="http://child-east:9000",
        )
        assert result["status"] == "registered"
        assert result["sub_id"] == "sub-1"

    def test_list_sub_dispatchers(self, dispatcher):
        dispatcher.register_sub_dispatcher(
            "sub-1", "child-east", "http://east:9000",
        )
        dispatcher.register_sub_dispatcher(
            "sub-2", "child-west", "http://west:9000",
        )
        subs = dispatcher.list_sub_dispatchers()
        assert len(subs) == 2
        aliases = {s["alias"] for s in subs}
        assert aliases == {"child-east", "child-west"}

    def test_unregister_sub_dispatcher(self, dispatcher):
        dispatcher.register_sub_dispatcher("sub-1", "a", "http://x")
        result = dispatcher.unregister_sub_dispatcher("sub-1")
        assert result["status"] == "unregistered"
        assert len(dispatcher.list_sub_dispatchers()) == 0

    def test_cluster_info_includes_sub_dispatchers(self, dispatcher):
        """cluster_info() includes the sub_dispatchers field (P7)."""
        dispatcher.register_sub_dispatcher(
            "sub-1", "child-east", "http://east:9000",
        )
        info = dispatcher.cluster_info()
        assert "sub_dispatchers" in info
        assert len(info["sub_dispatchers"]) == 1
        assert info["sub_dispatchers"][0]["alias"] == "child-east"

    def test_cluster_info_includes_parent_url(self, dispatcher):
        """cluster_info() includes parent_url when set (P7)."""
        from stockstat_backend.dispatcher.core import Dispatcher
        from stockstat_backend.dispatcher.queue import MemoryTaskQueue
        sub = Dispatcher(
            queue=MemoryTaskQueue(),
            alias="dispatch-child",
            parent_url="http://parent:9000",
        )
        info = sub.cluster_info()
        assert info["dispatcher"]["parent_url"] == "http://parent:9000"
        assert info["dispatcher"]["alias"] == "dispatch-child"

    def test_cluster_info_default_no_parent(self, dispatcher):
        """cluster_info() has parent_url=None by default."""
        info = dispatcher.cluster_info()
        assert info["dispatcher"]["parent_url"] is None


# ═══════════════════════════════════════════════════════════════
# P7.2: Task history
# ═══════════════════════════════════════════════════════════════


class TestTaskHistory:
    def _complete_task(self, dispatcher, task_id, task_type="custom"):
        """Helper: submit + assign + complete a task."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        import base64
        from stockstat._core.codec import CloudpickleCodec
        spec = TaskSpec(
            task_id=task_id or new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type=task_type),
        )
        dispatcher.submit(spec)
        assignment = dispatcher.assign_task("w1", capabilities=[task_type])
        slice_id = assignment["task_spec"]["task_id"]
        result = {"x": 1}
        result_b64 = base64.b64encode(CloudpickleCodec().encode(result)).decode("ascii")
        dispatcher.on_complete("w1", slice_id, result_b64)
        return spec.task_id

    def test_history_empty_initially(self, dispatcher):
        history = dispatcher.get_task_history()
        assert history == []

    def test_history_records_completed_task(self, dispatcher):
        task_id = self._complete_task(dispatcher, "task-1")
        history = dispatcher.get_task_history()
        assert len(history) >= 1
        last = history[-1]
        assert last["task_id"] == task_id
        assert last["state"] == "completed"
        assert last["task_type"] == "custom"

    def test_history_records_failed_task(self, dispatcher):
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="backtest"),  # no strategy_ref -> fails
        )
        dispatcher.submit(spec)
        assignment = dispatcher.assign_task("w1", capabilities=["backtest"])
        slice_id = assignment["task_spec"]["task_id"]
        dispatcher.on_fail("w1", slice_id, error="missing strategy_ref",
                            traceback_str="...", retryable=False)
        history = dispatcher.get_task_history()
        assert any(h["state"] == "failed" for h in history)

    def test_history_limit(self, dispatcher):
        """get_task_history(limit=N) returns at most N entries."""
        for i in range(5):
            self._complete_task(dispatcher, f"task-{i}")
        history = dispatcher.get_task_history(limit=3)
        assert len(history) <= 3

    def test_history_state_filter(self, dispatcher):
        """get_task_history(state_filter='completed') returns only completed."""
        self._complete_task(dispatcher, "task-completed-1")
        # Also fail a task
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec,
        )
        spec = TaskSpec(
            task_id="task-failed-1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="backtest"),
        )
        dispatcher.submit(spec)
        assignment = dispatcher.assign_task("w1", capabilities=["backtest"])
        dispatcher.on_fail("w1", assignment["task_spec"]["task_id"],
                            error="x", retryable=False)
        completed = dispatcher.get_task_history(state_filter="completed")
        assert all(h["state"] == "completed" for h in completed)
        assert any(h["task_id"] == "task-completed-1" for h in completed)


# ═══════════════════════════════════════════════════════════════
# P7.3: Task stats
# ═══════════════════════════════════════════════════════════════


class TestTaskStats:
    def test_stats_empty(self, dispatcher):
        stats = dispatcher.get_task_stats()
        assert stats["total_tasks"] == 0
        assert stats["by_state"] == {}
        assert stats["by_type"] == {}
        assert stats["avg_duration_s"] == 0

    def test_stats_after_tasks(self, dispatcher):
        """Stats reflect completed tasks."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec,
        )
        import base64
        from stockstat._core.codec import CloudpickleCodec
        # Complete 3 tasks: 2 custom, 1 indicator
        for task_type in ("custom", "custom", "indicator"):
            spec = TaskSpec(
                task_id=f"task-{task_type}-{time.time()}",
                data_spec=DataSpec(symbols=[]),
                compute_spec=ComputeSpec(task_type=task_type),
            )
            dispatcher.submit(spec)
            assignment = dispatcher.assign_task("w1", capabilities=[task_type])
            slice_id = assignment["task_spec"]["task_id"]
            result_b64 = base64.b64encode(
                CloudpickleCodec().encode({"x": 1})
            ).decode("ascii")
            dispatcher.on_complete("w1", slice_id, result_b64)
        stats = dispatcher.get_task_stats()
        assert stats["total_tasks"] == 3
        assert stats["by_state"].get("completed") == 3
        assert stats["by_type"].get("custom") == 2
        assert stats["by_type"].get("indicator") == 1


# ═══════════════════════════════════════════════════════════════
# P7.4: Admin Plugin Dispatcher routes
# ═══════════════════════════════════════════════════════════════


class TestAdminDispatcherRoutes:
    def test_admin_dispatcher_routes_exist_when_enabled(self):
        """When both admin and dispatcher are enabled, /admin/api/dispatcher/* routes exist."""
        import os
        from stockstat_backend.app import create_app
        from stockstat_backend.config import settings
        prev_admin = os.environ.get("STOCKSTAT_ADMIN_ENABLED")
        prev_disp = os.environ.get("STOCKSTAT_DISPATCHER_ENABLED")
        os.environ["STOCKSTAT_ADMIN_ENABLED"] = "true"
        os.environ["STOCKSTAT_DISPATCHER_ENABLED"] = "true"
        try:
            settings.reload()
            app = create_app()
            paths = {r.path for r in app.routes if hasattr(r, "path")}
            assert "/admin/api/dispatcher/cluster" in paths
            assert "/admin/api/dispatcher/tasks" in paths
            assert "/admin/api/dispatcher/stats" in paths
            assert "/admin/api/dispatcher/autoscaler" in paths
        finally:
            for k, v in [("STOCKSTAT_ADMIN_ENABLED", prev_admin),
                          ("STOCKSTAT_DISPATCHER_ENABLED", prev_disp)]:
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            settings.reload()

    def test_admin_dispatcher_404_when_not_enabled(self):
        """When dispatcher is not enabled, /admin/api/dispatcher/* returns 404."""
        import os
        from stockstat_backend.app import create_app
        from stockstat_backend.config import settings
        from fastapi.testclient import TestClient
        prev_disp = os.environ.get("STOCKSTAT_DISPATCHER_ENABLED")
        os.environ["STOCKSTAT_DISPATCHER_ENABLED"] = "false"
        try:
            settings.reload()
            app = create_app()
            client = TestClient(app)
            resp = client.get("/admin/api/dispatcher/cluster")
            assert resp.status_code == 404
        finally:
            if prev_disp is None:
                os.environ.pop("STOCKSTAT_DISPATCHER_ENABLED", None)
            else:
                os.environ["STOCKSTAT_DISPATCHER_ENABLED"] = prev_disp
            settings.reload()

    def test_admin_dispatcher_cluster_returns_topology(self):
        """Admin /admin/api/dispatcher/cluster returns full topology."""
        import os
        from stockstat_backend.app import create_app
        from stockstat_backend.config import settings
        from fastapi.testclient import TestClient
        prev_admin = os.environ.get("STOCKSTAT_ADMIN_ENABLED")
        prev_disp = os.environ.get("STOCKSTAT_DISPATCHER_ENABLED")
        os.environ["STOCKSTAT_ADMIN_ENABLED"] = "true"
        os.environ["STOCKSTAT_DISPATCHER_ENABLED"] = "true"
        try:
            settings.reload()
            app = create_app()
            client = TestClient(app)
            resp = client.get("/admin/api/dispatcher/cluster")
            assert resp.status_code == 200
            data = resp.json()
            assert "dispatcher" in data
            assert "workers" in data
            assert "sub_dispatchers" in data
            assert "stats" in data
        finally:
            for k, v in [("STOCKSTAT_ADMIN_ENABLED", prev_admin),
                          ("STOCKSTAT_DISPATCHER_ENABLED", prev_disp)]:
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            settings.reload()


# ═══════════════════════════════════════════════════════════════
# P7.5: Dispatcher P7 routes
# ═══════════════════════════════════════════════════════════════


class TestDispatcherP7Routes:
    def test_p7_endpoints_exist(self):
        """P7 endpoints are mounted by DispatcherPlugin."""
        from fastapi import FastAPI
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/dispatch/sub/register" in paths
        assert "/dispatch/sub/unregister/{sub_id}" in paths
        assert "/dispatch/sub" in paths
        assert "/dispatch/tasks/history" in paths
        assert "/dispatch/tasks/stats" in paths

    def test_sub_register_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        client = TestClient(app)
        resp = client.post("/dispatch/sub/register", json={
            "sub_id": "sub-1",
            "alias": "child-east",
            "address": "http://east:9000",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

    def test_sub_list_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        client = TestClient(app)
        client.post("/dispatch/sub/register", json={
            "sub_id": "sub-1", "alias": "a", "address": "http://x",
        })
        resp = client.get("/dispatch/sub")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sub_dispatchers"]) == 1

    def test_tasks_history_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        client = TestClient(app)
        resp = client.get("/dispatch/tasks/history")
        assert resp.status_code == 200
        assert "history" in resp.json()

    def test_tasks_stats_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from stockstat_backend.dispatcher import DispatcherPlugin
        app = FastAPI()
        DispatcherPlugin.mount(app, queue_backend="memory")
        client = TestClient(app)
        resp = client.get("/dispatch/tasks/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tasks" in data
        assert "by_state" in data
        assert "by_type" in data


# ═══════════════════════════════════════════════════════════════
# P7.6: WebSocket-style progress (simulated via polling)
# ═══════════════════════════════════════════════════════════════


class TestProgressPolling:
    """P7: While WebSocket push is not implemented, progress is available
    via polling /dispatch/tasks/history and /dispatch/status/{id}.

    This test verifies that progress can be tracked via polling.
    """

    def test_progress_via_status_polling(self, dispatcher):
        """Client polls task.status to track progress."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom",
                                      params={"progress_test": True}),
        )
        dispatcher.submit(spec)
        # Initial status should be pending or running
        status = dispatcher.get_status(spec.task_id)
        assert status["state"] in ("pending", "running", "completed")

        # Assign + complete
        assignment = dispatcher.assign_task("w1", capabilities=["custom"])
        import base64
        from stockstat._core.codec import CloudpickleCodec
        result_b64 = base64.b64encode(
            CloudpickleCodec().encode({"done": True})
        ).decode("ascii")
        dispatcher.on_complete("w1", assignment["task_spec"]["task_id"], result_b64)

        # Final status
        status = dispatcher.get_status(spec.task_id)
        assert status["state"] == "completed"
        assert status["progress"] == 1.0

    def test_progress_via_partials(self, dispatcher):
        """Partials accumulate and are visible via stream_partials."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="custom"),
        )
        dispatcher.submit(spec)
        # Publish partials
        dispatcher.on_partial("w1", spec.task_id, {"progress": 0.25})
        dispatcher.on_partial("w1", spec.task_id, {"progress": 0.5})
        dispatcher.on_partial("w1", spec.task_id, {"progress": 0.75})
        state = dispatcher._tasks[spec.task_id]
        assert hasattr(state, "stream_partials")
        assert len(state.stream_partials) == 3
        # Client can read partials from state.stream_partials in real time
        # (In a real deployment, this would be via WebSocket push)
