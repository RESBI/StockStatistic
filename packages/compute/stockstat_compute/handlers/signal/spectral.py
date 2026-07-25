"""spectral_analysis handler — 频谱分析。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("spectral_analysis")
def handle_spectral_analysis(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    from scipy import signal as scipy_signal
    cs = spec.compute_spec
    method = cs.params.get("method", "welch")
    nperseg = cs.params.get("nperseg", 256)
    noverlap = cs.params.get("noverlap")
    x = np.asarray(data if data is not None else cs.params.get("signal"), dtype=float)
    if noverlap is None:
        noverlap = nperseg // 2
    if method == "welch":
        freqs, psd = scipy_signal.welch(x, nperseg=min(nperseg, len(x)),
                                         noverlap=min(noverlap, len(x) - 1))
    elif method == "fft":
        psd = np.abs(np.fft.fft(x)) ** 2
        freqs = np.fft.fftfreq(len(x))
    elif method == "periodogram":
        freqs, psd = scipy_signal.periodogram(x)
    else:
        raise ValueError(f"Unknown method: {method}")
    total_energy = float(np.sum(psd))
    spectral_centroid = float(np.sum(freqs * psd) / np.sum(psd)) if np.sum(psd) > 0 else 0.0
    peak_freq = float(freqs[np.argmax(psd)]) if len(psd) > 0 else 0.0
    return {"frequencies": freqs.tolist(), "psd": psd.tolist(),
            "total_energy": total_energy, "spectral_centroid": spectral_centroid,
            "peak_freq": peak_freq, "method": method}
