"""非线性指标（自实现，可选依赖 nolds/antropy 验证）。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _to_array(data) -> np.ndarray:
    if isinstance(data, pd.Series):
        return data.values.astype(float)
    if isinstance(data, pd.DataFrame):
        return data.iloc[:, 0].values.astype(float)
    return np.asarray(data, dtype=float)


def hurst_rs(data) -> dict:
    """Hurst 指数（R/S 法）。"""
    x = _to_array(data)
    n = len(x)
    if n < 20:
        return {"hurst": 0.5, "log_R": [], "log_n": [], "fit_r2": 0, "method": "rs"}

    max_k = int(np.floor(np.log2(n)))
    log_n = []
    log_R = []
    for k in range(2, max_k + 1):
        size = 2 ** k
        n_chunks = n // size
        if n_chunks < 1:
            continue
        Rs = []
        for i in range(n_chunks):
            chunk = x[i * size:(i + 1) * size]
            mean = chunk.mean()
            cumdev = np.cumsum(chunk - mean)
            R = cumdev.max() - cumdev.min()
            S = chunk.std()
            if S > 0:
                Rs.append(R / S)
        if Rs:
            log_n.append(np.log(size))
            log_R.append(np.log(np.mean(Rs)))

    if len(log_n) < 3:
        return {"hurst": 0.5, "log_R": log_R, "log_n": log_n,
                "fit_r2": 0, "method": "rs"}

    log_n_arr = np.array(log_n)
    log_R_arr = np.array(log_R)
    coeffs = np.polyfit(log_n_arr, log_R_arr, 1)
    hurst = coeffs[0]
    pred = np.polyval(coeffs, log_n_arr)
    ss_res = np.sum((log_R_arr - pred) ** 2)
    ss_tot = np.sum((log_R_arr - log_R_arr.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    return {
        "hurst": float(hurst),
        "log_R": log_R,
        "log_n": log_n,
        "fit_r2": float(r2),
        "method": "rs",
    }


def sample_entropy(data, m: int = 2, r: float = None) -> float:
    """样本熵。"""
    x = _to_array(data)
    n = len(x)
    if r is None:
        r = 0.2 * np.std(x)
    if r == 0:
        return float("inf")

    def _count_matches(template_len):
        count = 0
        for i in range(n - template_len):
            for j in range(i + 1, n - template_len):
                dist = np.max(np.abs(x[i:i + template_len] - x[j:j + template_len]))
                if dist < r:
                    count += 1
        return count

    A = _count_matches(m + 1)
    B = _count_matches(m)
    if B == 0:
        return float("inf")
    return float(-np.log(A / B))


def permutation_entropy(data, m: int = 4, tau: int = 1) -> float:
    """排列熵。"""
    from itertools import permutations
    x = _to_array(data)
    n = len(x)
    if n < m * tau:
        return 0.0

    perms = list(permutations(range(m)))
    perm_idx = {p: i for i, p in enumerate(perms)}
    counts = np.zeros(len(perms))

    for i in range(n - (m - 1) * tau):
        window = x[i:i + m * tau:tau]
        ordinal = np.argsort(window)
        pattern = tuple(ordinal)
        counts[perm_idx.get(pattern, -1)] += 1

    total = counts.sum()
    if total == 0:
        return 0.0
    p = counts / total
    p = p[p > 0]
    return float(-np.sum(p * np.log(p)))


__all__ = ["hurst_rs", "sample_entropy", "permutation_entropy"]
