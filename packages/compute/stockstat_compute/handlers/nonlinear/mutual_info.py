"""mutual_information handler — 互信息。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("mutual_information")
def handle_mutual_information(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    estimator = cs.params.get("estimator", "binning")
    bins = cs.params.get("bins", 10)
    x = np.asarray(data.get("x") if isinstance(data, dict) else cs.params.get("x"), dtype=float)
    y = np.asarray(data.get("y") if isinstance(data, dict) else cs.params.get("y"), dtype=float)
    if estimator == "binning":
        mi = _mi_binning(x, y, bins)
    elif estimator == "sklearn":
        from sklearn.feature_selection import mutual_info_regression
        mi = float(mutual_info_regression(x.reshape(-1, 1), y)[0])
    else:
        mi = _mi_binning(x, y, bins)
    return {"mutual_information": float(mi), "estimator": estimator, "bins": bins}


def _mi_binning(x, y, bins=10):
    hist_2d, _, _ = np.histogram2d(x, y, bins=bins)
    pxy = hist_2d / hist_2d.sum()
    px = pxy.sum(axis=1, keepdims=True)
    py = pxy.sum(axis=0, keepdims=True)
    mask = pxy > 0
    mi = np.sum(pxy[mask] * np.log2(pxy[mask] / (px @ py)[mask]))
    return float(max(mi, 0.0))
