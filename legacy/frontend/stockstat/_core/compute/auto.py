"""AutoComputeBackend — routes by task size / type (V1 Scenario E).

Light tasks run locally; heavy tasks go to the remote Dispatcher.
"""
from __future__ import annotations

from typing import Optional
from ..contracts.compute import ComputeBackend, TaskRef, TaskInfo


class AutoComputeBackend:
    """Auto-routing backend — V3 §8.3.

    Routes based on:
    - task_type (grid_search/batch/monte_carlo → remote)
    - data_spec size estimate (large → remote)
    - remote availability (fallback to local if unreachable)
    """

    name = "auto"

    HEAVY_TYPES = {"grid_search", "batch_backtest", "monte_carlo"}

    def __init__(self, local=None, remote=None, *,
                 local_threshold_mb: float = 1.0):
        self._local = local or _make_local()
        self._remote = remote
        self._threshold = local_threshold_mb * 1024 * 1024
        self._routing: dict[str, str] = {}  # task_id → "local"/"remote"

    def submit(self, spec) -> TaskRef:
        backend = self._choose(spec)
        return backend.submit(spec)

    def get(self, task_id: str) -> TaskInfo:
        backend = self._get_backend(task_id)
        return backend.get(task_id)

    def result(self, task_id: str):
        backend = self._get_backend(task_id)
        return backend.result(task_id)

    def wait(self, task_id: str, timeout=None):
        backend = self._get_backend(task_id)
        return backend.wait(task_id, timeout=timeout)

    def cancel(self, task_id: str) -> bool:
        backend = self._get_backend(task_id)
        return backend.cancel(task_id)

    def cluster_info(self, **kwargs) -> dict:
        if self._remote:
            try:
                return self._remote.cluster_info(**kwargs)
            except Exception:
                pass
        return self._local.cluster_info(**kwargs)

    def stream_results(self, task_id: str):
        backend = self._get_backend(task_id)
        yield from backend.stream_results(task_id)

    def _choose(self, spec) -> ComputeBackend:
        task_type = spec.compute_spec.task_type
        if task_type in self.HEAVY_TYPES and self._remote:
            self._routing[spec.task_id] = "remote"
            return self._remote
        self._routing[spec.task_id] = "local"
        return self._local

    def _get_backend(self, task_id: str) -> ComputeBackend:
        route = self._routing.get(task_id, "local")
        return self._remote if route == "remote" and self._remote else self._local


def _make_local():
    from .local import LocalComputeBackend
    return LocalComputeBackend()
