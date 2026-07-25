"""Serialization utils — 数据大小估算 + 数据分发策略选择。"""
from __future__ import annotations

from typing import Any

SMALL_DATA_THRESHOLD = 10 * 1024 * 1024   # 10 MB
LARGE_DATA_THRESHOLD = 100 * 1024 * 1024  # 100 MB


def estimate_data_size(data: Any) -> int:
    """估算数据大小（bytes）。"""
    if data is None:
        return 0
    if isinstance(data, (bytes, bytearray)):
        return len(data)
    if isinstance(data, str):
        return len(data.encode("utf-8"))
    if isinstance(data, dict):
        total = 0
        for v in data.values():
            if isinstance(v, dict):
                for df in v.values():
                    total += _estimate_df_size(df)
            else:
                total += _estimate_df_size(v)
        return total or 1024
    if isinstance(data, (list, tuple)):
        total = 0
        for item in data:
            total += _estimate_df_size(item)
        return total or 1024
    return _estimate_df_size(data)


def _estimate_df_size(df: Any) -> int:
    if df is None:
        return 0
    try:
        import pandas as pd
        if isinstance(df, pd.DataFrame):
            return int(df.memory_usage(deep=True).sum())
        if isinstance(df, pd.Series):
            return int(df.memory_usage(deep=True))
    except ImportError:
        pass
    if isinstance(df, (bytes, bytearray)):
        return len(df)
    if hasattr(df, "__sizeof__"):
        return sys_getsizeof(df)
    return 1024


def sys_getsizeof(obj: Any) -> int:
    import sys
    try:
        return sys.getsizeof(obj)
    except TypeError:
        return 1024


def choose_data_dispatch(data_size: int, workers_same_host: bool = False,
                         workers_can_reach_storage: bool = False) -> str:
    """根据数据大小自动选择分发策略。"""
    if data_size < SMALL_DATA_THRESHOLD:
        return "inline"
    if workers_same_host:
        return "shared_memory"
    if data_size > LARGE_DATA_THRESHOLD and workers_can_reach_storage:
        return "storage_ref"
    return "stream"


def resolve_data_dispatch(spec_dispatch: str, data_size: int,
                          workers_same_host: bool = False,
                          workers_can_reach_storage: bool = False) -> str:
    """如果 spec 显式指定（非 'auto'），原样返回；否则用 choose_data_dispatch。"""
    if spec_dispatch in ("auto", "", None):
        return choose_data_dispatch(data_size, workers_same_host, workers_can_reach_storage)
    return spec_dispatch


__all__ = [
    "SMALL_DATA_THRESHOLD", "LARGE_DATA_THRESHOLD",
    "estimate_data_size", "choose_data_dispatch", "resolve_data_dispatch",
]
