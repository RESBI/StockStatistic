"""Data dispatch strategy — V3 P4 §12.

Chooses how data is transferred from Dispatcher to Worker:

| Strategy       | When to use                                |
|----------------|--------------------------------------------|
| ``inline``     | < 10 MB, cross-host                        |
| ``shared_memory`` | same-host, any size (zero-copy)         |
| ``storage_ref``   | > 100 MB, Worker can reach Storage       |
| ``stream``      | 10-100 MB, cross-host, chunked Arrow IPC  |
| ``auto``        | Dispatcher picks based on size + topology |
"""
from __future__ import annotations

from typing import Optional


# Size thresholds (bytes)
SMALL_DATA_THRESHOLD = 10 * 1024 * 1024   # 10 MB
LARGE_DATA_THRESHOLD = 100 * 1024 * 1024  # 100 MB


def choose_data_dispatch(
    data_size: int,
    workers_same_host: bool = False,
    workers_can_reach_storage: bool = False,
) -> str:
    """Pick a data_dispatch strategy based on size + topology.

    Args:
        data_size: size of the prefetched data in bytes
        workers_same_host: True if all Workers run on the same host as Dispatcher
        workers_can_reach_storage: True if Workers can directly fetch from Storage

    Returns:
        One of ``"inline"`` / ``"shared_memory"`` / ``"storage_ref"`` / ``"stream"``
    """
    if data_size < SMALL_DATA_THRESHOLD:
        return "inline"
    if workers_same_host:
        return "shared_memory"
    if data_size > LARGE_DATA_THRESHOLD and workers_can_reach_storage:
        return "storage_ref"
    return "stream"


def estimate_data_size(data) -> int:
    """Estimate the size of a data payload in bytes.

    Handles common types:
    - ``bytes`` / ``bytearray``: ``len(data)``
    - ``pd.DataFrame``: ``len(df) * 50`` (rough estimate: ~50B per row)
    - ``dict`` of {symbol: {timeframe: DataFrame}}: sum of all frames
    - other: 1024 (default conservative estimate)
    """
    if isinstance(data, (bytes, bytearray)):
        return len(data)
    if isinstance(data, dict):
        total = 0
        for v in data.values():
            if isinstance(v, dict):
                for df in v.values():
                    total += _estimate_df_size(df)
            else:
                total += _estimate_df_size(v)
        return total or 1024
    return _estimate_df_size(data)


def _estimate_df_size(df) -> int:
    """Estimate DataFrame size in bytes."""
    try:
        import pandas as pd
        if isinstance(df, pd.DataFrame):
            # ~8 bytes per cell * rows * cols
            return df.memory_usage(deep=True).sum()
    except Exception:
        pass
    return 1024


def resolve_data_dispatch(
    spec_dispatch: str,
    data_size: int,
    workers_same_host: bool = False,
    workers_can_reach_storage: bool = False,
) -> str:
    """Resolve ``data_spec.data_dispatch`` to a concrete strategy.

    If the spec says ``"auto"``, use ``choose_data_dispatch()``.
    Otherwise return the spec value as-is.
    """
    if spec_dispatch in ("auto", "", None):
        return choose_data_dispatch(
            data_size, workers_same_host, workers_can_reach_storage,
        )
    return spec_dispatch
