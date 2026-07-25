"""hypothesis_test handler — 假设检验。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("hypothesis_test")
def handle_hypothesis_test(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    from scipy import stats
    cs = spec.compute_spec
    test = cs.params.get("test", "t_test")
    alpha = cs.params.get("alpha", 0.05)
    if test == "t_test":
        x = cs.params.get("x", data)
        y = cs.params.get("y")
        if y is None:
            stat, p = stats.ttest_1samp(x, cs.params.get("popmean", 0))
        else:
            stat, p = stats.ttest_ind(x, y)
        return {"test": test, "statistic": float(stat), "p_value": float(p), "alpha": alpha}
    if test == "chi2_independence":
        table = np.array(cs.params.get("table", data))
        stat, p, dof, expected = stats.chi2_contingency(table)
        n = table.sum()
        v = np.sqrt(stat / (n * (min(table.shape) - 1))) if n > 0 else 0
        return {"test": test, "statistic": float(stat), "p_value": float(p),
                "dof": int(dof), "cramers_v": float(v)}
    if test == "ks_test":
        x = cs.params.get("x", data)
        y = cs.params.get("y")
        if y is not None:
            stat, p = stats.ks_2samp(x, y)
        else:
            stat, p = stats.kstest(x, "norm")
        return {"test": test, "statistic": float(stat), "p_value": float(p)}
    if test == "shapiro":
        x = cs.params.get("x", data)
        stat, p = stats.shapiro(x)
        return {"test": test, "statistic": float(stat), "p_value": float(p)}
    if test == "mannwhitney":
        x, y = cs.params.get("x", data), cs.params.get("y")
        stat, p = stats.mannwhitneyu(x, y)
        return {"test": test, "statistic": float(stat), "p_value": float(p)}
    if test == "wilcoxon":
        x, y = cs.params.get("x", data), cs.params.get("y")
        stat, p = stats.wilcoxon(x, y)
        return {"test": test, "statistic": float(stat), "p_value": float(p)}
    raise ValueError(f"Unknown test: {test}")
