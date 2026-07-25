"""permutation_entropy handler — 排列熵。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("permutation_entropy")
def handle_permutation_entropy(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    m = cs.params.get("m", 4)
    tau = cs.params.get("tau", 1)
    x = np.asarray(data if data is not None else cs.params.get("x"), dtype=float)
    from ...indicators.nonlinear import permutation_entropy
    value = permutation_entropy(x, m=m, tau=tau)
    return {"permutation_entropy": float(value), "m": m, "tau": tau}
