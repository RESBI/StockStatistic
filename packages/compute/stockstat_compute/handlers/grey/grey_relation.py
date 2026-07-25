"""grey_relation handler — 灰色关联分析。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("grey_relation")
def handle_grey_relation(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    rho = cs.params.get("rho", 0.5)
    x0 = np.asarray(data["reference"] if isinstance(data, dict) else cs.params.get("reference"), dtype=float)
    sequences = data.get("sequences", cs.params.get("sequences")) if isinstance(data, dict) else cs.params.get("sequences")
    if isinstance(sequences, dict):
        sequences = list(sequences.values())
    sequences = [np.asarray(s, dtype=float) for s in sequences]
    x0_norm = x0 / x0[0]
    relation_degrees = []
    for xi in sequences:
        xi_norm = xi / xi[0]
        delta = np.abs(x0_norm - xi_norm)
        d_min, d_max = delta.min(), delta.max()
        xi_coef = (d_min + rho * d_max) / (delta + rho * d_max)
        r = float(xi_coef.mean())
        relation_degrees.append(r)
    rank = np.argsort(relation_degrees)[::-1].tolist()
    return {"relation_degrees": relation_degrees, "rank": rank, "rho": rho,
            "n_sequences": len(sequences)}
