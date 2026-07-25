"""multiple_testing handler — 多重检验校正。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("multiple_testing")
def handle_multiple_testing(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    p_values = np.asarray(cs.params.get("p_values", data), dtype=float)
    method = cs.params.get("method", "bh_fdr")
    alpha = cs.params.get("alpha", 0.05)
    n = len(p_values)
    order = np.argsort(p_values)
    if method == "bonferroni":
        adjusted = np.minimum(p_values * n, 1.0)
    elif method in ("bh_fdr", "benjamini_hochberg"):
        adjusted = np.empty(n)
        prev = 1.0
        for i in range(n - 1, -1, -1):
            idx = order[i]
            val = p_values[idx] * n / (i + 1)
            prev = min(prev, val)
            adjusted[idx] = min(prev, 1.0)
    elif method == "holm":
        adjusted = np.empty(n)
        prev = 0.0
        for i in range(n):
            idx = order[i]
            val = p_values[idx] * (n - i)
            prev = max(prev, val)
            adjusted[idx] = min(prev, 1.0)
    else:
        adjusted = p_values
    import pandas as pd
    return pd.DataFrame({
        "index": range(n),
        "p_value": p_values,
        "adjusted_p": adjusted,
        "reject": adjusted < alpha,
    })
