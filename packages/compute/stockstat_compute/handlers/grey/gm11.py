"""gm11_predict handler — GM(1,1) 灰色预测。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("gm11_predict")
def handle_gm11(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    n_ahead = cs.params.get("n_ahead", 1)
    x0 = np.asarray(data if data is not None else cs.params.get("x"), dtype=float)
    n = len(x0)
    if n < 4:
        return {"predicted": [], "error": "insufficient data (need >= 4)"}
    x1 = np.cumsum(x0)
    B = np.column_stack([-0.5 * (x1[:-1] + x1[1:]), np.ones(n - 1)])
    Y = x0[1:]
    try:
        ab = np.linalg.inv(B.T @ B) @ B.T @ Y
    except np.linalg.LinAlgError:
        return {"predicted": [], "error": "singular matrix"}
    a, b = ab
    x1_pred = np.array([(x0[0] - b / a) * np.exp(-a * k) + b / a
                        for k in range(n + n_ahead)])
    x0_pred = np.diff(np.concatenate([[x0[0]], x1_pred]))
    mape = np.mean(np.abs((x0 - x0_pred[:n]) / np.where(x0 == 0, 1, x0))) * 100
    mae = np.mean(np.abs(x0 - x0_pred[:n]))
    rmse = np.sqrt(np.mean((x0 - x0_pred[:n]) ** 2))
    return {"predicted": x0_pred[n:].tolist(), "params_a_b": [float(a), float(b)],
            "mape": float(mape), "mae": float(mae), "rmse": float(rmse),
            "n_ahead": n_ahead}
