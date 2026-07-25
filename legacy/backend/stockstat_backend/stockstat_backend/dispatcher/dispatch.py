"""Task sharding — split a TaskSpec into worker-parallel slices.

V2 §12.5 dispatch_spec.split_strategy controls how a task is sharded:
- ``none`` / ``auto``: single slice (no parallelism)
- ``param_wise``: grid_search param_grid → N slices
- ``symbol_wise``: multi-symbol → one slice per symbol
- ``time_wise``: time range → N time windows
"""
from __future__ import annotations

import uuid
from typing import List


def shard_task(spec, max_workers: int = None) -> List:
    """Split a TaskSpec into parallel slices.

    Returns a list of TaskSpec objects, each with:
    - A unique task_id (suffixed with slice index)
    - compute_spec.params['param_slice'] for param_wise
    - dispatch_spec.split_strategy set to 'none' (no further sharding)
    """
    strategy = spec.dispatch_spec.split_strategy
    if strategy in ("none", "auto", ""):
        return [spec]

    if strategy == "param_wise":
        return _shard_param_wise(spec, max_workers)
    if strategy == "symbol_wise":
        return _shard_symbol_wise(spec, max_workers)
    if strategy == "time_wise":
        return _shard_time_wise(spec, max_workers)
    # Unknown strategy → no sharding
    return [spec]


def _shard_param_wise(spec, max_workers=None) -> List:
    """Shard grid_search param_grid across workers."""
    from itertools import product
    cs = spec.compute_spec
    if not cs.param_grid:
        return [spec]
    keys = list(cs.param_grid.keys())
    all_combos = [dict(zip(keys, vals)) for vals in product(*[cs.param_grid[k] for k in keys])]
    n = max_workers or min(len(all_combos), 4)
    n = min(n, len(all_combos))
    if n <= 1:
        return [spec]
    # Split combos into n chunks
    chunk_size = (len(all_combos) + n - 1) // n
    slices = []
    for i in range(n):
        chunk = all_combos[i * chunk_size:(i + 1) * chunk_size]
        if not chunk:
            break
        slice_spec = _make_slice(spec, i, n)
        slice_spec.compute_spec.params["param_slice"] = chunk
        slices.append(slice_spec)
    return slices


def _shard_symbol_wise(spec, max_workers=None) -> List:
    """Shard multi-symbol tasks — one slice per symbol."""
    symbols = spec.data_spec.symbols
    if len(symbols) <= 1:
        return [spec]
    n = max_workers or len(symbols)
    n = min(n, len(symbols))
    slices = []
    for i in range(n):
        slice_spec = _make_slice(spec, i, n)
        slice_spec.data_spec.symbols = [symbols[i]]
        slices.append(slice_spec)
    return slices


def _shard_time_wise(spec, max_workers=None) -> List:
    """Shard by time range — split [start, end] into N windows."""
    import pandas as pd
    ds = spec.data_spec
    if not ds.start or not ds.end:
        return [spec]
    start = pd.Timestamp(ds.start, tz="UTC")
    end = pd.Timestamp(ds.end, tz="UTC")
    n = max_workers or 4
    total_seconds = (end - start).total_seconds()
    window = total_seconds / n
    slices = []
    for i in range(n):
        slice_spec = _make_slice(spec, i, n)
        w_start = start + pd.Timedelta(seconds=window * i)
        w_end = start + pd.Timedelta(seconds=window * (i + 1))
        slice_spec.data_spec.start = w_start.isoformat()
        slice_spec.data_spec.end = w_end.isoformat()
        slices.append(slice_spec)
    return slices


def _make_slice(spec, index: int, total: int):
    """Create a slice of the original TaskSpec with a new task_id."""
    import copy
    slice_spec = copy.deepcopy(spec)
    slice_spec.task_id = f"{spec.task_id}-s{index}"
    slice_spec.dispatch_spec.split_strategy = "none"
    slice_spec.dispatch_spec.max_workers = None
    return slice_spec
