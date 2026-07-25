"""chow_test handler — Chow 断点检验。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("chow_test")
def handle_chow_test(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    breakpoint = cs.params.get("breakpoint")
    y = np.asarray(data if isinstance(data, (list, np.ndarray)) else data.get("y", []), dtype=float)
    x = np.arange(len(y)) if breakpoint is not None else np.arange(len(y))
    if isinstance(breakpoint, str):
        breakpoint = int(breakpoint)
    elif isinstance(breakpoint, float):
        breakpoint = int(breakpoint)
    if breakpoint is None or breakpoint >= len(y) - 2:
        breakpoint = len(y) // 2
    y1, y2 = y[:breakpoint], y[breakpoint:]
    x1, x2 = x[:breakpoint], x[breakpoint:]
    def _rss(x, y):
        if len(x) < 2:
            return float("inf")
        coeffs = np.polyfit(x, y, 1)
        pred = np.polyval(coeffs, x)
        return np.sum((y - pred) ** 2)
    rss_full = _rss(x, y)
    rss1 = _rss(x1, y1)
    rss2 = _rss(x2, y2)
    k = 2  # 参数数
    n = len(y)
    if rss_full == 0 or n - 2 * k <= 0:
        return {"F_stat": 0.0, "p_value": 1.0, "rss_before": float(rss1), "rss_after": float(rss2)}
    F = ((rss_full - rss1 - rss2) / k) / ((rss1 + rss2) / (n - 2 * k))
    from scipy import stats
    p = 1 - stats.f.cdf(F, k, n - 2 * k)
    return {"F_stat": float(F), "p_value": float(p),
            "rss_before": float(rss1), "rss_after": float(rss2), "breakpoint": int(breakpoint)}
