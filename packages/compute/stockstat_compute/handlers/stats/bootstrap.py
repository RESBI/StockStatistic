"""bootstrap handler — 自助法。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("bootstrap")
def handle_bootstrap(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    n_resamples = cs.params.get("n_resamples", 1000)
    ci_method = cs.params.get("ci_method", "percentile")
    alpha = cs.params.get("alpha", 0.05)
    x = np.asarray(data if data is not None else cs.params.get("x"), dtype=float)
    n = len(x)
    rng = np.random.default_rng(cs.params.get("seed", 42))
    estimates = []
    for i in range(n_resamples):
        sample = rng.choice(x, size=n, replace=True)
        estimates.append(np.mean(sample))
        if on_progress and (i + 1) % 100 == 0:
            on_progress(i + 1, n_resamples)
    estimates = np.array(estimates)
    point = np.mean(x)
    if ci_method == "percentile":
        ci_lower = np.percentile(estimates, 100 * alpha / 2)
        ci_upper = np.percentile(estimates, 100 * (1 - alpha / 2))
    else:
        ci_lower = np.percentile(estimates, 100 * alpha / 2)
        ci_upper = np.percentile(estimates, 100 * (1 - alpha / 2))
    return {"estimate": float(point), "ci_lower": float(ci_lower),
            "ci_upper": float(ci_upper), "bias": float(np.mean(estimates) - point),
            "se": float(np.std(estimates)), "n_resamples": n_resamples}
