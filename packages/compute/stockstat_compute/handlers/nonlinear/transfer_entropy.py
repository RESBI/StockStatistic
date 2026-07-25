"""transfer_entropy handler — 传递熵（PAXG v7 N2 关键）。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("transfer_entropy")
def handle_transfer_entropy(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    k = cs.params.get("k", 1)
    l = cs.params.get("l", 1)
    bins = cs.params.get("bins", 4)
    n_perm = cs.params.get("n_permutations", 100)
    x = np.asarray(data.get("x") if isinstance(data, dict) else cs.params.get("x"), dtype=float)
    y = np.asarray(data.get("y") if isinstance(data, dict) else cs.params.get("y"), dtype=float)
    te_forward = _transfer_entropy(x, y, k, l, bins)
    te_backward = _transfer_entropy(y, x, k, l, bins)
    net_te = te_forward - te_backward
    rng = np.random.default_rng(cs.params.get("seed", 42))
    null_dist = []
    for i in range(n_perm):
        x_shuffled = rng.permutation(x)
        null_dist.append(_transfer_entropy(x_shuffled, y, k, l, bins))
        if on_progress and (i + 1) % 10 == 0:
            on_progress(i + 1, n_perm)
    null_dist = np.array(null_dist)
    p_value = float(np.mean(null_dist >= te_forward))
    return {"te_forward": float(te_forward), "te_backward": float(te_backward),
            "net_te": float(net_te), "p_value": p_value,
            "significant": bool(p_value < 0.05), "n_permutations": n_perm}


def _transfer_entropy(x, y, k=1, l=1, bins=4):
    """传递熵 T_{x→y}（分箱估计器）。"""
    def _quantize(v):
        edges = np.linspace(v.min(), v.max() + 1e-10, bins + 1)
        return np.digitize(v, edges[1:-1])

    xq = _quantize(x)
    yq = _quantize(y)
    n = len(xq)
    if n <= k + l:
        return 0.0
    # 联合分布: P(y_{t+1}, y_{t-k+1:t}, x_{t-l+1:t})
    from collections import defaultdict
    counts = defaultdict(int)
    total = 0
    for t in range(max(k, l), n - 1):
        y_future = yq[t + 1]
        y_past = tuple(yq[t - k + 1:t + 1]) if k > 0 else ()
        x_past = tuple(xq[t - l + 1:t + 1]) if l > 0 else ()
        key = (y_future, y_past, x_past)
        counts[key] += 1
        total += 1
    if total == 0:
        return 0.0
    # 计算传递熵
    from collections import defaultdict
    p_yfuture_ypast_xpast = defaultdict(float)
    p_ypast_xpast = defaultdict(float)
    p_yfuture_ypast = defaultdict(float)
    p_ypast = defaultdict(float)
    for (yf, yp, xp), c in counts.items():
        p_yfuture_ypast_xpast[(yf, yp, xp)] = c / total
        p_ypast_xpast[(yp, xp)] += c / total
        p_yfuture_ypast[(yf, yp)] += c / total
        p_ypast[yp] += c / total
    te = 0.0
    for (yf, yp, xp), p_joint in p_yfuture_ypast_xpast.items():
        p_cond1 = p_yfuture_ypast.get((yf, yp), 1e-10)
        p_cond2 = p_ypast.get(yp, 1e-10)
        p_marginal = p_ypast_xpast.get((yp, xp), 1e-10)
        if p_joint > 0 and p_cond1 > 0 and p_marginal > 0:
            te += p_joint * np.log2((p_joint * p_cond2) / (p_cond1 * p_marginal))
    return float(max(te, 0.0))
