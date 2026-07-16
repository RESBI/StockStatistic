from __future__ import annotations

from itertools import product
from typing import Callable, Optional

import pandas as pd

from .engine import BacktestEngine
from .result import BacktestResult


def grid_search(make_engine: Callable[[dict], BacktestEngine],
                param_grid: dict,
                metric: str = "sharpe",
                maximize: bool = True) -> list[tuple[dict, float, BacktestResult]]:
    """Exhaustive grid search over `param_grid`.

    `make_engine(params) -> BacktestEngine` builds an engine from a param dict.
    Returns list of (params, metric_value, result) sorted best-first.
    """
    keys = list(param_grid.keys())
    grids = [dict(zip(keys, vals)) for vals in product(*[param_grid[k] for k in keys])]
    results = []
    for params in grids:
        engine = make_engine(params)
        res = engine.run()
        m = res.metrics()
        val = m.get(metric, float("-inf"))
        results.append((params, val, res))
    results.sort(key=lambda x: x[1], reverse=maximize)
    return results


def optuna_search(make_engine: Callable[[dict], BacktestEngine],
                  param_space: Callable, n_trials: int = 50,
                  metric: str = "sharpe", maximize: bool = True):
    """Optional optuna-based search. Requires `pip install stockstat[optimize]`."""
    try:
        import optuna
    except ImportError as e:
        raise ImportError(
            "optuna is required for optuna_search: pip install stockstat[optimize]"
        ) from e

    direction = "maximize" if maximize else "minimize"
    study = optuna.create_study(direction=direction)

    def objective(trial):
        params = param_space(trial)
        engine = make_engine(params)
        res = engine.run()
        return res.metrics().get(metric, float("-inf"))

    study.optimize(objective, n_trials=n_trials)
    return study
