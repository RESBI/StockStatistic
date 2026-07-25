"""AutoComputeBackend — 按规模路由本地/远程。"""
from __future__ import annotations

from typing import Any, Optional

from stockstat_foundation import (
    ComputeBackend, TaskRef, TaskSpec,
)
from stockstat_foundation.utils import estimate_data_size


class AutoComputeBackend:
    """自动路由后端 — 按任务规模选择本地或远程。

    路由规则：
    - task_type in HEAVY_TYPES → 远程
    - 数据量 > threshold → 远程
    - 远程不可达 → 降级本地
    """
    name = "auto"

    HEAVY_TYPES = {
        "grid_search", "batch_backtest", "monte_carlo", "bootstrap",
        "permutation_test", "walkforward", "walkforward_cv",
        "ml_train", "deep_learning",
    }

    def __init__(self, local, remote, *, local_threshold_mb: float = 1.0):
        self._local = local
        self._remote = remote
        self._threshold = local_threshold_mb * 1024 * 1024
        self._routing: dict = {}

    def submit(self, spec: TaskSpec) -> TaskRef:
        backend = self._choose(spec)
        self._routing[spec.task_id] = backend.name
        return backend.submit(spec)

    def _choose(self, spec: TaskSpec):
        # 1. 任务类型偏好
        if spec.compute_spec.task_type in self.HEAVY_TYPES:
            return self._remote
        # 2. 数据量估算
        inline = spec.compute_spec.params.get("_inline_data")
        if inline is not None:
            data_size = estimate_data_size(inline)
            if data_size > self._threshold:
                return self._remote
        return self._local

    def get(self, task_id: str):
        return self._route(task_id).get(task_id)

    def result(self, task_id: str):
        return self._route(task_id).result(task_id)

    def wait(self, task_id: str, timeout=None):
        return self._route(task_id).wait(task_id, timeout=timeout)

    def cancel(self, task_id: str) -> bool:
        return self._route(task_id).cancel(task_id)

    def cluster_info(self, **kwargs) -> dict:
        try:
            return self._remote.cluster_info(**kwargs)
        except Exception:
            return self._local.cluster_info(**kwargs)

    def stream_results(self, task_id: str):
        yield from self._route(task_id).stream_results(task_id)

    def _route(self, task_id: str):
        name = self._routing.get(task_id, "local")
        return self._local if name == "local" else self._remote


__all__ = ["AutoComputeBackend"]
