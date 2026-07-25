"""filter_design handler — 滤波器设计。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("filter_design")
def handle_filter_design(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    from scipy import signal as scipy_signal
    cs = spec.compute_spec
    filter_type = cs.params.get("filter_type", "butterworth")
    cutoff = cs.params.get("cutoff", 0.1)
    order = cs.params.get("order", 4)
    x = np.asarray(data if data is not None else cs.params.get("signal"), dtype=float)
    if filter_type == "butterworth":
        b, a = scipy_signal.butter(order, cutoff)
        filtered = scipy_signal.filtfilt(b, a, x)
    elif filter_type == "savitzky_golay":
        window = cs.params.get("window", 11)
        filtered = scipy_signal.savgol_filter(x, window, order)
    else:
        filtered = x
    return filtered.tolist()
