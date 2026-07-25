"""shard_task — 任务分片。"""
from __future__ import annotations

import copy
import itertools

from stockstat_foundation import TaskSpec, DataSpec


def shard_task(spec: TaskSpec) -> list:
    """将 TaskSpec 分片为 N 个 slice。"""
    strategy = spec.dispatch_spec.split_strategy
    if strategy in ("none", "auto", "", None):
        return [spec]
    if strategy == "param_wise":
        return _shard_param_wise(spec)
    if strategy == "symbol_wise":
        return _shard_symbol_wise(spec)
    if strategy == "time_wise":
        return _shard_time_wise(spec)
    return [spec]


def _shard_param_wise(spec: TaskSpec) -> list:
    cs = spec.compute_spec
    if cs.task_type == "grid_search" and cs.param_grid:
        keys = list(cs.param_grid.keys())
        values = list(cs.param_grid.values())
        combos = list(itertools.product(*values))
        max_workers = spec.dispatch_spec.max_workers or 1
        chunk_size = max(1, len(combos) // max_workers)
        if chunk_size == 0:
            chunk_size = 1
        chunks = [combos[i:i + chunk_size] for i in range(0, len(combos), chunk_size)]
        slices = []
        for i, chunk in enumerate(chunks):
            sub_grid = {k: [combo[j] for combo in chunk] for j, k in enumerate(keys)}
            slices.append(_clone_slice(spec, f"-s{i}", param_grid=sub_grid))
        return slices
    if cs.task_type == "batch_backtest" and cs.strategies:
        fee_models = cs.fee_models or [None]
        combos = [(s, f) for s in cs.strategies for f in fee_models]
        max_workers = spec.dispatch_spec.max_workers or 1
        chunk_size = max(1, len(combos) // max_workers)
        if chunk_size == 0:
            chunk_size = 1
        chunks = [combos[i:i + chunk_size] for i in range(0, len(combos), chunk_size)]
        slices = []
        for i, chunk in enumerate(chunks):
            sub_strategies = {name: spec.compute_spec.strategies[name] for (name, _) in chunk}
            sub_fees = list(set(f for _, f in chunk if f is not None))
            slices.append(_clone_slice(spec, f"-s{i}",
                                        strategies=sub_strategies,
                                        fee_models=sub_fees or None))
        return slices
    if cs.task_type == "monte_carlo":
        n = cs.n_simulations
        max_workers = spec.dispatch_spec.max_workers or 1
        chunk_size = max(1, n // max_workers)
        slices = []
        for i in range(max_workers):
            start = i * chunk_size
            end = min(start + chunk_size, n)
            if start >= n:
                break
            sub_spec = _clone_slice(spec, f"-s{i}", n_simulations=end - start,
                                     seed=cs.seed + start)
            slices.append(sub_spec)
        return slices
    return [spec]


def _shard_symbol_wise(spec: TaskSpec) -> list:
    symbols = spec.data_spec.symbols
    if len(symbols) <= 1:
        return [spec]
    slices = []
    for i, sym in enumerate(symbols):
        sub_data = DataSpec(symbols=[sym], timeframe=spec.data_spec.timeframe,
                             start=spec.data_spec.start, end=spec.data_spec.end,
                             source=spec.data_spec.source)
        slices.append(_clone_slice(spec, f"-s{i}", data_spec=sub_data))
    return slices


def _shard_time_wise(spec: TaskSpec) -> list:
    # 简化实现：不分片
    return [spec]


def _clone_slice(spec: TaskSpec, suffix: str, **overrides) -> TaskSpec:
    new_spec = copy.deepcopy(spec)
    new_spec.task_id = f"{spec.task_id}{suffix}"
    for k, v in overrides.items():
        if k == "data_spec":
            new_spec.data_spec = v
        elif k == "param_grid":
            new_spec.compute_spec.param_grid = v
        elif k == "strategies":
            new_spec.compute_spec.strategies = v
        elif k == "fee_models":
            new_spec.compute_spec.fee_models = v
        elif k == "n_simulations":
            new_spec.compute_spec.n_simulations = v
        elif k == "seed":
            new_spec.compute_spec.seed = v
    return new_spec


__all__ = ["shard_task"]
