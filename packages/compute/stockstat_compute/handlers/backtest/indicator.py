"""indicator handler。"""
from __future__ import annotations

from typing import Any, Optional, Callable

from stockstat_foundation import TaskSpec

from .._base import register  # type: ignore


@register("indicator")
def handle_indicator(spec: TaskSpec, data: Any, *,
                     on_progress: Optional[Callable] = None) -> Any:
    """技术指标计算。"""
    cs = spec.compute_spec
    name = cs.params.get("indicator_name")
    if not name:
        raise ValueError("params.indicator_name required")
    from ...compute_engine import ComputeEngine
    engine = ComputeEngine()
    params = {k: v for k, v in cs.params.items() if k != "indicator_name"}
    return engine.compute(name, data, **params)


__all__ = ["handle_indicator"]
