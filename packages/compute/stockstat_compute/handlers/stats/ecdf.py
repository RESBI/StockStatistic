"""ecdf handler — 经验累积分布。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("ecdf")
def handle_ecdf(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    groups = cs.params.get("groups")
    if groups is None and isinstance(data, dict):
        groups = data
    if groups is not None:
        result = {}
        for name, values in groups.items():
            v = np.sort(np.asarray(values, dtype=float))
            ecdf = np.arange(1, len(v) + 1) / len(v)
            result[name] = {"x": v.tolist(), "ecdf": ecdf.tolist()}
        return result
    x = np.sort(np.asarray(data if data is not None else cs.params.get("x"), dtype=float))
    ecdf = np.arange(1, len(x) + 1) / len(x)
    return {"x": x.tolist(), "ecdf": ecdf.tolist()}
