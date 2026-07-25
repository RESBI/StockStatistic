"""rqa handler — 递归定量分析。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("rqa")
def handle_rqa(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    m = cs.params.get("m", 3)
    tau = cs.params.get("tau", 1)
    epsilon = cs.params.get("epsilon")
    x = np.asarray(data if data is not None else cs.params.get("x"), dtype=float)
    # 相空间重构
    n = len(x)
    embed_len = n - (m - 1) * tau
    if embed_len <= 0:
        return {"RR": 0.0, "DET": 0.0, "LAM": 0.0, "L_max": 0, "ENTR": 0.0}
    embedded = np.zeros((embed_len, m))
    for i in range(m):
        embedded[:, i] = x[i * tau:i * tau + embed_len]
    # 递归矩阵
    dist = np.zeros((embed_len, embed_len))
    for i in range(embed_len):
        dist[i] = np.max(np.abs(embedded - embedded[i]), axis=1)
    if epsilon is None:
        epsilon = 0.1 * np.std(x)
    R = (dist < epsilon).astype(int)
    # RQA 指标
    RR = np.mean(R)
    # DET：对角线长度
    diag_lengths = []
    for offset in range(-embed_len + 1, embed_len):
        diag = np.diagonal(R, offset=offset)
        current = 0
        for val in diag:
            if val == 1:
                current += 1
            else:
                if current >= 2:
                    diag_lengths.append(current)
                current = 0
        if current >= 2:
            diag_lengths.append(current)
    DET = sum(diag_lengths) / max(np.sum(R), 1)
    L_max = max(diag_lengths) if diag_lengths else 0
    # LAM：垂直线长度
    vert_lengths = []
    for j in range(embed_len):
        col = R[:, j]
        current = 0
        for val in col:
            if val == 1:
                current += 1
            else:
                if current >= 2:
                    vert_lengths.append(current)
                current = 0
    LAM = sum(vert_lengths) / max(np.sum(R), 1)
    # ENTR：对角线长度的熵
    if diag_lengths:
        from collections import Counter
        counts = Counter(diag_lengths)
        probs = np.array(list(counts.values())) / len(diag_lengths)
        ENTR = -np.sum(probs * np.log2(probs))
    else:
        ENTR = 0.0
    return {"RR": float(RR), "DET": float(DET), "LAM": float(LAM),
            "L_max": int(L_max), "ENTR": float(ENTR),
            "m": m, "tau": tau, "epsilon": float(epsilon)}
