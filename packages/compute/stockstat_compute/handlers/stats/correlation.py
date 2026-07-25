"""correlation handler — 相关分析。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("correlation")
def handle_correlation(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    method = cs.params.get("method", "pearson")
    x = cs.params.get("x", data.get("x") if isinstance(data, dict) else data)
    y = cs.params.get("y", data.get("y") if isinstance(data, dict) else None)
    if x is None or y is None:
        raise ValueError("correlation requires x and y")
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if method == "pearson":
        r = np.corrcoef(x, y)[0, 1]
        from scipy import stats
        _, p = stats.pearsonr(x, y)
    elif method == "spearman":
        from scipy import stats
        r, p = stats.spearmanr(x, y)
    elif method == "kendall":
        from scipy import stats
        r, p = stats.kendalltau(x, y)
    else:
        raise ValueError(f"Unknown method: {method}")
    n = len(x)
    z = np.arctanh(r) if abs(r) < 1 else 0
    se = 1 / np.sqrt(max(n - 3, 1))
    ci_lower = np.tanh(z - 1.96 * se)
    ci_upper = np.tanh(z + 1.96 * se)
    return {"method": method, "r": float(r), "p_value": float(p), "n": int(n),
            "ci_lower": float(ci_lower), "ci_upper": float(ci_upper)}
