"""test_auto_backend.py — AutoComputeBackend 测试 (15 项)。"""
from __future__ import annotations

import time

import pandas as pd
import pytest

from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec, DispatchSpec
from stockstat_compute.backend.local import LocalComputeBackend
from stockstat_compute.backend.auto import AutoComputeBackend


class FakeRemoteBackend:
    """假远程后端，记录调用。"""
    name = "remote"

    def __init__(self):
        self.submitted = []
        self._results = {}

    def submit(self, spec):
        self.submitted.append(spec)
        from stockstat_foundation import TaskRef, TaskState, TaskInfo
        self._results[spec.task_id] = {"result": "remote"}
        return TaskRef(task_id=spec.task_id, backend=self)

    def get(self, task_id):
        from stockstat_foundation import TaskInfo, TaskState
        return TaskInfo(task_id=task_id, state=TaskState.COMPLETED)

    def result(self, task_id):
        return self._results.get(task_id, {})

    def wait(self, task_id, timeout=None):
        return self._results.get(task_id, {})

    def cancel(self, task_id):
        return True

    def cluster_info(self, **kwargs):
        return {"status": "remote"}

    def stream_results(self, task_id):
        yield self._results.get(task_id, {})


class TestAutoComputeBackend:
    def test_light_task_goes_local(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="light1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma"}),
        )
        auto.submit(spec)
        assert len(remote.submitted) == 0  # 不走远程

    def test_heavy_task_goes_remote(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="heavy1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search"),
        )
        auto.submit(spec)
        assert len(remote.submitted) == 1

    def test_batch_backtest_goes_remote(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="batch1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="batch_backtest"),
        )
        auto.submit(spec)
        assert len(remote.submitted) == 1

    def test_monte_carlo_goes_remote(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="mc1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="monte_carlo"),
        )
        auto.submit(spec)
        assert len(remote.submitted) == 1

    def test_large_data_goes_remote(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote, local_threshold_mb=1.0)
        # 2MB 数据
        big_data = list(range(500000))
        spec = TaskSpec(
            task_id="big1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="indicator",
                                     params={"indicator_name": "ma",
                                             "_inline_data": big_data}),
        )
        auto.submit(spec)
        assert len(remote.submitted) == 1

    def test_routing_tracks_task_id(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="track1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search"),
        )
        auto.submit(spec)
        assert auto._routing["track1"] == "remote"

    def test_cluster_info_from_remote(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote)
        info = auto.cluster_info()
        assert info["status"] == "remote"

    def test_cluster_info_fallback_on_error(self):
        local = LocalComputeBackend()
        class BrokenRemote(FakeRemoteBackend):
            def cluster_info(self, **kwargs):
                raise Exception("broken")
        auto = AutoComputeBackend(local, BrokenRemote())
        info = auto.cluster_info()
        assert "dispatcher" in info  # 本地 fallback

    def test_name(self):
        auto = AutoComputeBackend(LocalComputeBackend(), FakeRemoteBackend())
        assert auto.name == "auto"

    def test_heavy_types_set(self):
        assert "grid_search" in AutoComputeBackend.HEAVY_TYPES
        assert "batch_backtest" in AutoComputeBackend.HEAVY_TYPES
        assert "monte_carlo" in AutoComputeBackend.HEAVY_TYPES
        assert "indicator" not in AutoComputeBackend.HEAVY_TYPES
        assert "backtest" not in AutoComputeBackend.HEAVY_TYPES

    def test_wait_routes_correctly(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="wait1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search"),
        )
        ref = auto.submit(spec)
        result = ref.wait(timeout=5)
        assert result == {"result": "remote"}

    def test_cancel_routes(self):
        local = LocalComputeBackend()
        remote = FakeRemoteBackend()
        auto = AutoComputeBackend(local, remote)
        spec = TaskSpec(
            task_id="cancel1",
            data_spec=DataSpec(symbols=[]),
            compute_spec=ComputeSpec(task_type="grid_search"),
        )
        auto.submit(spec)
        assert auto.cancel("cancel1") is True

    def test_default_threshold_1mb(self):
        auto = AutoComputeBackend(LocalComputeBackend(), FakeRemoteBackend())
        assert auto._threshold == 1.0 * 1024 * 1024

    def test_custom_threshold(self):
        auto = AutoComputeBackend(LocalComputeBackend(), FakeRemoteBackend(),
                                   local_threshold_mb=10.0)
        assert auto._threshold == 10.0 * 1024 * 1024

    def test_compute_backend_protocol(self):
        from stockstat_foundation import ComputeBackend
        auto = AutoComputeBackend(LocalComputeBackend(), FakeRemoteBackend())
        assert isinstance(auto, ComputeBackend)
