"""recurrence_plot handler — 递归图。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("recurrence_plot")
def handle_recurrence_plot(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    m = cs.params.get("m", 3)
    tau = cs.params.get("tau", 1)
    epsilon = cs.params.get("epsilon")
    x = np.asarray(data if data is not None else cs.params.get("x"), dtype=float)
    n = len(x)
    embed_len = n - (m - 1) * tau
    if embed_len <= 0:
        return {"recurrence_plot": [], "m": m, "tau": tau}
    embedded = np.zeros((embed_len, m))
    for i in range(m):
        embedded[:, i] = x[i * tau:i * tau + embed_len]
    dist = np.zeros((embed_len, embed_len))
    for i in range(embed_len):
        dist[i] = np.max(np.abs(embedded - embedded[i]), axis=1)
    if epsilon is None:
        epsilon = 0.1 * np.std(x)
    R = (dist < epsilon).astype(int)
    return {"recurrence_plot": R.tolist(), "m": m, "tau": tau, "epsilon": float(epsilon),
            "shape": list(R.shape)}
