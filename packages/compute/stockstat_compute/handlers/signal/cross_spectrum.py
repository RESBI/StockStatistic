"""cross_spectrum handler — 交叉谱分析。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("cross_spectrum")
def handle_cross_spectrum(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    from scipy import signal as scipy_signal
    cs = spec.compute_spec
    nperseg = cs.params.get("nperseg", 256)
    x = np.asarray(data.get("x") if isinstance(data, dict) else cs.params.get("x"), dtype=float)
    y = np.asarray(data.get("y") if isinstance(data, dict) else cs.params.get("y"), dtype=float)
    freqs, csd = scipy_signal.csd(x, y, nperseg=min(nperseg, len(x)))
    _, Pxx = scipy_signal.welch(x, nperseg=min(nperseg, len(x)))
    _, Pyy = scipy_signal.welch(y, nperseg=min(nperseg, len(y)))
    coherence = np.abs(csd) ** 2 / (Pxx * Pyy + 1e-10)
    phase = np.angle(csd)
    return {"frequencies": freqs.tolist(), "csd": csd.tolist(),
            "coherence": coherence.tolist(), "phase": phase.tolist()}
