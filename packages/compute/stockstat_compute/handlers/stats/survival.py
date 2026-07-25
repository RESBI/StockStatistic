"""survival_analysis handler — 生存分析。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("survival_analysis")
def handle_survival_analysis(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    method = cs.params.get("method", "kaplan_meier")
    if isinstance(data, dict):
        durations = np.asarray(data.get("duration", data.get("durations", [])), dtype=float)
        events = np.asarray(data.get("event", data.get("events", [])), dtype=float)
    else:
        durations = np.asarray(data, dtype=float)
        events = np.ones_like(durations)
    if method == "kaplan_meier":
        return _kaplan_meier(durations, events)
    raise ValueError(f"Unknown method: {method}")


def _kaplan_meier(durations, events):
    order = np.argsort(durations)
    durations = durations[order]
    events = events[order]
    unique_times = np.unique(durations)
    n_at_risk = len(durations)
    survival = 1.0
    curve = [(0.0, 1.0)]
    for t in unique_times:
        mask = durations == t
        d = np.sum(events[mask])
        n = n_at_risk
        if n > 0:
            survival *= (1 - d / n)
        curve.append((float(t), float(survival)))
        n_at_risk -= np.sum(mask)
    times = [p[0] for p in curve]
    surv = [p[1] for p in curve]
    median = None
    for i, s in enumerate(surv):
        if s <= 0.5:
            median = times[i]
            break
    return {"survival_curve": {"time": times, "survival": surv},
            "median_survival": median, "n": len(durations), "n_events": int(np.sum(events))}
