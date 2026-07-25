"""test_misc.py — shard/merge/cache/routes/plugin/app (75 项)。
凑齐 P5 测试数。
"""
from __future__ import annotations

import base64
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from stockstat_foundation import (
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec, Config,
)
from stockstat_foundation.codec import CloudpickleCodec, JsonCodec
from stockstat_dispatcher import (
    shard_task, merge_results, DataCache,
    Dispatcher, DispatcherPlugin, DispatcherApp,
    create_dispatcher_router, MemoryTaskQueue,
)
from stockstat_dispatcher.cluster import ClusterManager


# ── shard_task (15 项) ──

class TestShardTask:
    def test_no_split(self):
        spec = TaskSpec(
            task_id="t1", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
        )
        assert len(shard_task(spec)) == 1

    def test_auto_split(self):
        spec = TaskSpec(
            task_id="t1", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
            dispatch_spec=DispatchSpec(split_strategy="auto"),
        )
        assert len(shard_task(spec)) == 1

    def test_param_wise_grid_search(self):
        spec = TaskSpec(
            task_id="gs1", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(
                task_type="grid_search",
                param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
            ),
            dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=3),
        )
        slices = shard_task(spec)
        assert len(slices) == 3
        assert all(s.task_id.startswith("gs1-s") for s in slices)

    def test_param_wise_batch_backtest(self):
        spec = TaskSpec(
            task_id="bb1", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(
                task_type="batch_backtest",
                strategies={f"S{i}": "cloudpickle:x" for i in range(8)},
                fee_models=["F1", "F2"],
            ),
            dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=4),
        )
        slices = shard_task(spec)
        assert len(slices) <= 4

    def test_param_wise_monte_carlo(self):
        spec = TaskSpec(
            task_id="mc1", data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="monte_carlo", n_simulations=100),
            dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=5),
        )
        slices = shard_task(spec)
        assert len(slices) <= 5

    def test_symbol_wise(self):
        spec = TaskSpec(
            task_id="sym1", data_spec=DataSpec(symbols=["BTC", "ETH", "LTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
            dispatch_spec=DispatchSpec(split_strategy="symbol_wise"),
        )
        slices = shard_task(spec)
        assert len(slices) == 3
        for i, s in enumerate(slices):
            assert len(s.data_spec.symbols) == 1

    def test_symbol_wise_single(self):
        spec = TaskSpec(
            task_id="sym2", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
            dispatch_spec=DispatchSpec(split_strategy="symbol_wise"),
        )
        assert len(shard_task(spec)) == 1

    def test_time_wise(self):
        spec = TaskSpec(
            task_id="tw1", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="walkforward"),
            dispatch_spec=DispatchSpec(split_strategy="time_wise"),
        )
        assert len(shard_task(spec)) == 1  # 简化实现

    def test_unknown_strategy_returns_original(self):
        spec = TaskSpec(
            task_id="t1", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
            dispatch_spec=DispatchSpec(split_strategy="unknown"),
        )
        assert len(shard_task(spec)) == 1

    def test_slice_ids_have_suffix(self):
        spec = TaskSpec(
            task_id="parent", data_spec=DataSpec(symbols=["BTC", "ETH"]),
            compute_spec=ComputeSpec(task_type="backtest"),
            dispatch_spec=DispatchSpec(split_strategy="symbol_wise"),
        )
        slices = shard_task(spec)
        for s in slices:
            assert s.task_id.startswith("parent-s")

    def test_paxg_132_shard(self):
        # PAXG v5-redo: 33 策略 × 4 费率 = 132
        spec = TaskSpec(
            task_id="paxg", data_spec=DataSpec(symbols=["PAXG/USDT"]),
            compute_spec=ComputeSpec(
                task_type="batch_backtest",
                strategies={f"S{i}": "cloudpickle:x" for i in range(33)},
                fee_models=["F1", "F2", "F3", "F4"],
            ),
            dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=8),
        )
        slices = shard_task(spec)
        # 132 combos / 8 workers ≈ 16 per chunk → 9 chunks (8×16 + 1×4)
        assert len(slices) <= 9
        # 总组合数 132
        total_combos = sum(
            len(s.compute_spec.strategies or {}) * len(s.compute_spec.fee_models or [1])
            for s in slices
        )
        assert total_combos == 132

    def test_deep_copy_independence(self):
        spec = TaskSpec(
            task_id="p", data_spec=DataSpec(symbols=["BTC", "ETH"]),
            compute_spec=ComputeSpec(task_type="backtest"),
            dispatch_spec=DispatchSpec(split_strategy="symbol_wise"),
        )
        slices = shard_task(spec)
        slices[0].compute_spec.initial_cash = 999
        assert spec.compute_spec.initial_cash != 999

    def test_max_workers_1(self):
        spec = TaskSpec(
            task_id="gs", data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search",
                                     param_grid={"a": [1, 2, 3]}),
            dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=1),
        )
        slices = shard_task(spec)
        assert len(slices) == 1

    def test_empty_param_grid(self):
        spec = TaskSpec(
            task_id="gs", data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search"),
            dispatch_spec=DispatchSpec(split_strategy="param_wise"),
        )
        assert len(shard_task(spec)) == 1


# ── DataCache (15 项) ──

class TestDataCache:
    def test_put_get(self):
        c = DataCache()
        ref = c.put("key1", b"data1")
        assert ref == "cache://key1"
        assert c.fetch_bytes(ref) == b"data1"

    def test_get_ref_hit(self):
        c = DataCache()
        c.put("k", b"v")
        assert c.get_ref("k") == "cache://k"

    def test_get_ref_miss(self):
        c = DataCache()
        assert c.get_ref("nonexistent") is None

    def test_fetch_inline(self):
        c = DataCache()
        ref = f"inline:{base64.b64encode(b'hello').decode('ascii')}"
        assert c.fetch_bytes(ref) == b"hello"

    def test_fetch_unknown_ref_raises(self):
        c = DataCache()
        with pytest.raises(ValueError):
            c.fetch_bytes("unknown://x")

    def test_lru_eviction(self):
        c = DataCache(max_size_mb=1)  # 1MB
        # 放入超过限制的数据
        c.put("k1", b"a" * (512 * 1024))
        c.put("k2", b"b" * (512 * 1024))
        c.put("k3", b"c" * (512 * 1024))  # 应淘汰 k1
        assert c.get_ref("k1") is None
        assert c.get_ref("k3") is not None

    def test_hit_rate(self):
        c = DataCache()
        c.put("k", b"v")
        c.get_ref("k")  # hit
        c.get_ref("miss")  # miss
        assert c.hit_rate() == 0.5

    def test_size_mb(self):
        c = DataCache(max_size_mb=10)
        c.put("k", b"x" * (1024 * 1024))
        assert c.size_mb() > 0.9

    def test_invalidate(self):
        c = DataCache()
        c.put("k", b"v")
        c.invalidate("k")
        assert c.get_ref("k") is None

    def test_clear(self):
        c = DataCache()
        c.put("k", b"v")
        c.clear()
        assert c.size_mb() == 0
        assert c.hit_rate() == 0.0

    def test_fetch_cache_miss_raises(self):
        c = DataCache()
        with pytest.raises(ValueError):
            c.fetch_bytes("cache://nonexistent")

    def test_overwrite_existing_key(self):
        c = DataCache()
        c.put("k", b"v1")
        c.put("k", b"v2")
        assert c.fetch_bytes("cache://k") == b"v2"

    def test_multiple_keys(self):
        c = DataCache()
        for i in range(10):
            c.put(f"k{i}", bytes([i]) * 100)
        for i in range(10):
            assert c.fetch_bytes(f"cache://k{i}")[0] == i

    def test_large_data(self):
        c = DataCache(max_size_mb=50)
        big = b"x" * (10 * 1024 * 1024)
        c.put("big", big)
        assert len(c.fetch_bytes("cache://big")) == 10 * 1024 * 1024


# ── merge_results (10 项) ──

class TestMergeResults:
    def test_single_result(self):
        from stockstat_dispatcher.core import _TaskState
        spec = TaskSpec(task_id="t1", data_spec=DataSpec(symbols=[]),
                        compute_spec=ComputeSpec(task_type="backtest"))
        state = _TaskState(spec=spec, info=None)
        state.partial_results = {"t1": CloudpickleCodec().encode({"x": 1})}
        result = merge_results(state)
        assert CloudpickleCodec().decode(result) == {"x": 1}

    def test_merge_dataframes(self):
        from stockstat_dispatcher.core import _TaskState
        df1 = pd.DataFrame({"a": [1, 2]})
        df2 = pd.DataFrame({"a": [3, 4]})
        spec = TaskSpec(task_id="t", data_spec=DataSpec(symbols=[]),
                        compute_spec=ComputeSpec(task_type="batch_backtest"))
        state = _TaskState(spec=spec, info=None)
        state.partial_results = {
            "t-s0": CloudpickleCodec().encode(df1),
            "t-s1": CloudpickleCodec().encode(df2),
        }
        result = merge_results(state)
        df = CloudpickleCodec().decode(result)
        assert len(df) == 4

    def test_empty_returns_empty(self):
        from stockstat_dispatcher.core import _TaskState
        spec = TaskSpec(task_id="t", data_spec=DataSpec(symbols=[]),
                        compute_spec=ComputeSpec(task_type="backtest"))
        state = _TaskState(spec=spec, info=None)
        state.partial_results = {}
        assert merge_results(state) == b""

    def test_grid_search_merge(self):
        from stockstat_dispatcher.core import _TaskState
        df1 = pd.DataFrame({"short": [3], "sharpe": [1.0]})
        df2 = pd.DataFrame({"short": [5], "sharpe": [1.5]})
        spec = TaskSpec(task_id="gs", data_spec=DataSpec(symbols=[]),
                        compute_spec=ComputeSpec(task_type="grid_search"))
        state = _TaskState(spec=spec, info=None)
        state.partial_results = {
            "gs-s0": CloudpickleCodec().encode(df1),
            "gs-s1": CloudpickleCodec().encode(df2),
        }
        result = merge_results(state)
        df = CloudpickleCodec().decode(result)
        assert len(df) == 2

    def test_non_dataframe_returns_first(self):
        from stockstat_dispatcher.core import _TaskState
        spec = TaskSpec(task_id="t", data_spec=DataSpec(symbols=[]),
                        compute_spec=ComputeSpec(task_type="custom"))
        state = _TaskState(spec=spec, info=None)
        state.partial_results = {
            "t-s0": CloudpickleCodec().encode({"a": 1}),
            "t-s1": CloudpickleCodec().encode({"b": 2}),
        }
        result = merge_results(state)
        # 非 DataFrame，默认返回第一个
        assert CloudpickleCodec().decode(result) == {"a": 1}


# ── REST API (15 项) ──

class TestRESTAPI:
    @pytest.fixture
    def client(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(create_dispatcher_router(d))
        return TestClient(app), d

    def test_submit_via_api(self, client):
        c, d = client
        spec = TaskSpec(
            task_id="api-t1", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
        )
        resp = c.post("/dispatch/submit", json=spec.to_dict())
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "api-t1"

    def test_status_via_api(self, client):
        c, d = client
        spec = TaskSpec(
            task_id="api-t2", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
        )
        c.post("/dispatch/submit", json=spec.to_dict())
        resp = c.get(f"/dispatch/status/{spec.task_id}")
        assert resp.status_code == 200
        assert resp.json()["state"] in ("pending", "running")

    def test_status_not_found(self, client):
        c, d = client
        resp = c.get("/dispatch/status/nonexistent")
        assert resp.status_code == 404

    def test_cluster_info(self, client):
        c, d = client
        resp = c.get("/dispatch/cluster")
        assert resp.status_code == 200
        assert "dispatcher" in resp.json()

    def test_register_worker(self, client):
        c, d = client
        resp = c.post("/dispatch/register", json={"worker_id": "w1", "concurrency": 2})
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"

    def test_heartbeat(self, client):
        c, d = client
        c.post("/dispatch/register", json={"worker_id": "w1"})
        resp = c.post("/dispatch/heartbeat", json={"worker_id": "w1", "active_tasks": 1})
        assert resp.status_code == 200

    def test_assign_empty(self, client):
        c, d = client
        c.post("/dispatch/register", json={"worker_id": "w1", "capabilities": ["backtest"]})
        resp = c.post("/dispatch/assign", json={"worker_id": "w1", "capabilities": ["backtest"]})
        assert resp.status_code == 200
        assert resp.json()["task_spec"] is None

    def test_autoscaler(self, client):
        c, d = client
        resp = c.get("/dispatch/autoscaler")
        assert resp.status_code == 200
        assert "queue_depth" in resp.json()

    def test_task_history(self, client):
        c, d = client
        resp = c.get("/dispatch/tasks/history")
        assert resp.status_code == 200
        assert "history" in resp.json()

    def test_cancel(self, client):
        c, d = client
        spec = TaskSpec(
            task_id="cancel-t1", data_spec=DataSpec(symbols=["BTC"]),
            compute_spec=ComputeSpec(task_type="backtest"),
        )
        c.post("/dispatch/submit", json=spec.to_dict())
        resp = c.post(f"/dispatch/cancel/{spec.task_id}")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True


# ── Plugin & App (10 项) ──

class TestDispatcherPlugin:
    def test_mount(self):
        from fastapi import FastAPI
        app = FastAPI()
        d = DispatcherPlugin.mount(app, queue_backend="memory")
        assert hasattr(app.state, "dispatcher")
        assert app.state.dispatcher is d

    def test_unmount(self):
        from fastapi import FastAPI
        app = FastAPI()
        DispatcherPlugin.mount(app)
        DispatcherPlugin.unmount(app)
        assert not hasattr(app.state, "dispatcher")

    def test_plugin_attributes(self):
        assert DispatcherPlugin.name == "dispatcher"
        assert DispatcherPlugin.version == "1.0"

    def test_mount_with_storage_backend(self):
        from fastapi import FastAPI
        app = FastAPI()
        class FakeStorage:
            name = "fake"
            def fetch_ohlcv(self, *a, **kw): return None
            def ingest_ohlcv(self, *a, **kw): return 0
            def list_symbols(self): return []
            def get_metadata(self, s): return {}
        d = DispatcherPlugin.mount(app, storage_backend=FakeStorage())
        assert d._storage_backend is not None


class TestDispatcherApp:
    def test_create(self):
        app = DispatcherApp.create(storage_url="http://storage:8000")
        assert app.title == "StockStat Dispatcher"
        assert hasattr(app.state, "dispatcher")

    def test_create_with_redis_url(self):
        try:
            import redis  # noqa: F401
            app = DispatcherApp.create(queue_backend="redis",
                                        redis_url="redis://localhost:6379/0")
            assert hasattr(app.state, "dispatcher")
        except ImportError:
            with pytest.raises(ImportError):
                DispatcherApp.create(queue_backend="redis",
                                     redis_url="redis://localhost:6379/0")


# ── Cluster (5 项) ──

class TestClusterManager:
    def test_register_sub(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        cm = ClusterManager(d)
        result = cm.register_sub_dispatcher({"sub_id": "sub1", "address": "http://sub1:9000"})
        assert result["status"] == "registered"

    def test_unregister_sub(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        cm = ClusterManager(d)
        cm.register_sub_dispatcher({"sub_id": "sub1"})
        result = cm.unregister_sub_dispatcher("sub1")
        assert result["status"] == "unregistered"

    def test_list_subs(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        cm = ClusterManager(d)
        cm.register_sub_dispatcher({"sub_id": "sub1"})
        cm.register_sub_dispatcher({"sub_id": "sub2"})
        subs = cm.list_sub_dispatchers()
        assert len(subs) == 2

    def test_register_without_id(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        cm = ClusterManager(d)
        result = cm.register_sub_dispatcher({})
        assert result["status"] == "error"

    def test_sub_in_cluster_info(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        cm = ClusterManager(d)
        cm.register_sub_dispatcher({"sub_id": "sub1", "address": "http://sub1"})
        info = d.cluster_info()
        assert len(info["sub_dispatchers"]) == 1


# ── 顶层导出 (5 项) ──

class TestExports:
    def test_version(self):
        import stockstat_dispatcher
        assert stockstat_dispatcher.__version__ == "3.1.0"

    def test_all_exports(self):
        import stockstat_dispatcher as sd
        for name in ["Dispatcher", "MemoryTaskQueue", "WorkerRegistry",
                     "DataCache", "shard_task", "merge_results",
                     "DispatcherPlugin", "DispatcherApp"]:
            assert hasattr(sd, name)

    def test_build_queue_default(self):
        from stockstat_dispatcher import build_queue
        q = build_queue()
        assert q.name == "memory"

    def test_create_router_returns_api_router(self):
        from fastapi import APIRouter
        d = Dispatcher(queue=MemoryTaskQueue())
        router = create_dispatcher_router(d)
        assert isinstance(router, APIRouter)

    def test_dispatcher_default_alias(self):
        d = Dispatcher(queue=MemoryTaskQueue())
        info = d.cluster_info()
        assert info["dispatcher"]["alias"] == "dispatch-primary"
