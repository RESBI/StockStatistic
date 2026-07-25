"""spectral_entropy handler — 谱熵。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("spectral_entropy")
def handle_spectral_entropy(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    from scipy import signal as scipy_signal
    cs = spec.compute_spec
    nperseg = cs.params.get("nperseg", 256)
    normalize = cs.params.get("normalize", True)
    x = np.asarray(data if data is not None else cs.params.get("signal"), dtype=float)
    _, psd = scipy_signal.welch(x, nperseg=min(nperseg, len(x)))
    psd = psd / np.sum(psd) if np.sum(psd) > 0 else psd
    psd = psd[psd > 0]
    entropy = -np.sum(psd * np.log2(psd))
    if normalize and len(psd) > 0:
        entropy = entropy / np.log2(len(psd))
    return {"spectral_entropy": float(entropy), "normalized": bool(normalize)}
