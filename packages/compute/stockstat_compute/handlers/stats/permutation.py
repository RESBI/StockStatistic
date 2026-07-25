"""permutation_test handler — 排列检验。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("permutation_test")
def handle_permutation_test(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    n_perm = cs.params.get("n_permutations", 1000)
    x = np.asarray(data.get("x") if isinstance(data, dict) else cs.params.get("x"), dtype=float)
    y = np.asarray(data.get("y") if isinstance(data, dict) else cs.params.get("y"), dtype=float)
    rng = np.random.default_rng(cs.params.get("seed", 42))
    observed = abs(np.mean(x) - np.mean(y))
    combined = np.concatenate([x, y])
    n_x = len(x)
    null_dist = []
    for i in range(n_perm):
        perm = rng.permutation(combined)
        stat = abs(np.mean(perm[:n_x]) - np.mean(perm[n_x:]))
        null_dist.append(stat)
        if on_progress and (i + 1) % 100 == 0:
            on_progress(i + 1, n_perm)
    null_dist = np.array(null_dist)
    p_value = np.mean(null_dist >= observed)
    return {"observed_stat": float(observed), "p_value": float(p_value),
            "null_distribution": null_dist.tolist(), "n_permutations": n_perm}
