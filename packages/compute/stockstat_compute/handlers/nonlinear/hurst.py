"""hurst_exponent handler — Hurst 指数。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("hurst_exponent")
def handle_hurst_exponent(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    method = cs.params.get("method", "dfa")
    x = np.asarray(data if data is not None else cs.params.get("x"), dtype=float)
    if method == "dfa":
        return _dfa(x)
    elif method == "rs":
        from ...indicators.nonlinear import hurst_rs
        return hurst_rs(x)
    raise ValueError(f"Unknown method: {method}")


def _dfa(x):
    """去趋势波动分析。"""
    n = len(x)
    if n < 20:
        return {"hurst": 0.5, "log_F": [], "log_n": [], "fit_r2": 0, "method": "dfa"}
    y = np.cumsum(x - np.mean(x))
    max_k = int(np.floor(np.log2(n)))
    log_n, log_F = [], []
    for k in range(4, max_k + 1):
        size = 2 ** k
        n_chunks = n // size
        if n_chunks < 1:
            continue
        F_values = []
        for i in range(n_chunks):
            chunk = y[i * size:(i + 1) * size]
            t = np.arange(size)
            coeffs = np.polyfit(t, chunk, 1)
            trend = np.polyval(coeffs, t)
            F_values.append(np.sqrt(np.mean((chunk - trend) ** 2)))
        if F_values:
            log_n.append(np.log(size))
            log_F.append(np.log(np.mean(F_values)))
    if len(log_n) < 3:
        return {"hurst": 0.5, "log_F": log_F, "log_n": log_n, "fit_r2": 0, "method": "dfa"}
    log_n_arr = np.array(log_n)
    log_F_arr = np.array(log_F)
    coeffs = np.polyfit(log_n_arr, log_F_arr, 1)
    hurst = coeffs[0]
    pred = np.polyval(coeffs, log_n_arr)
    ss_res = np.sum((log_F_arr - pred) ** 2)
    ss_tot = np.sum((log_F_arr - log_F_arr.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    return {"hurst": float(hurst), "log_F": log_F, "log_n": log_n,
            "fit_r2": float(r2), "method": "dfa"}
