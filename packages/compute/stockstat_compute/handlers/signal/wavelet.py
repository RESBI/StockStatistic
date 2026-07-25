"""wavelet handler — 小波分析。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("wavelet")
def handle_wavelet(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    method = cs.params.get("method", "cwt")
    wavelet = cs.params.get("wavelet", "morl")
    scales = cs.params.get("scales", list(range(1, 25)))
    signal = np.asarray(data if data is not None else cs.params.get("signal"), dtype=float)
    if method == "cwt":
        try:
            import pywt
            coeffs, freqs = pywt.cwt(signal, scales, wavelet)
            power = np.abs(coeffs) ** 2
            return {"coefficients": coeffs.tolist(), "power": power.tolist(),
                    "scales": list(scales), "method": "cwt",
                    "spectral_centroid": float(np.mean(power))}
        except ImportError:
            coeffs = _morlet_cwt(signal, scales)
            power = np.abs(coeffs) ** 2
            return {"coefficients": coeffs.tolist(), "power": power.tolist(),
                    "scales": list(scales), "method": "cwt_fallback",
                    "spectral_centroid": float(np.mean(power))}
    raise ValueError(f"Unknown method: {method}")


def _morlet_cwt(signal, scales, w0=5.0):
    N = len(signal)
    coeffs = np.zeros((len(scales), N), dtype=complex)
    for i, s in enumerate(scales):
        t = np.arange(-s * 4, s * 4 + 1) / s
        wavelet = np.exp(1j * w0 * t) * np.exp(-0.5 * t ** 2)
        wavelet /= np.sqrt(s)
        coeffs[i] = np.convolve(signal, wavelet.conj(), mode="same")
    return coeffs
