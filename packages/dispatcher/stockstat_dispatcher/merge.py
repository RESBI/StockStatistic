"""merge_results — 结果合并。"""
from __future__ import annotations

from typing import Any


def merge_results(state) -> bytes:
    """合并 N 个 slice 的部分结果为完整结果。"""
    from stockstat_foundation import CloudpickleCodec
    task_type = state.spec.compute_spec.task_type
    partials = list(state.partial_results.values())

    if len(partials) == 0:
        return b""
    if len(partials) == 1:
        return partials[0]

    codec = CloudpickleCodec()
    decoded = [codec.decode(p) for p in partials]

    if task_type in ("grid_search", "batch_backtest", "monte_carlo",
                      "bootstrap", "permutation_test"):
        import pandas as pd
        if all(isinstance(d, pd.DataFrame) for d in decoded):
            merged = pd.concat(decoded, ignore_index=True)
            return codec.encode(merged)
        # 混合类型：返回列表
        return codec.encode(decoded)
    # 默认：返回第一个
    return partials[0]


__all__ = ["merge_results"]
