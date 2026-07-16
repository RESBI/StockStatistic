# BT-6: Optimization + Walk-Forward + Monte Carlo

> **Phase**: BT-6 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_optimize.py` (8 passed)
> **Dependencies**: core has no extra deps; `optuna` via `[optimize]` extras

## Deliverables

### Grid search (`optimizer.py`)

```python
from stockstat.backtest.optimizer import grid_search

results = grid_search(make_engine, {"short": [3, 5, 8], "long": [10, 20]},
                      metric="sharpe")
best_params, best_val, best_result = results[0]
```

- Exhaustive over all parameter combinations, sorted by the chosen metric (maximized by default)
- Returns list of `(params, metric_value, BacktestResult)`

### optuna search (optional extras)

```python
from stockstat.backtest.optimizer import optuna_search

def param_space(trial):
    return {"short": trial.suggest_int("short", 2, 10),
            "long": trial.suggest_int("long", 15, 40)}

study = optuna_search(make_engine, param_space, n_trials=50, metric="sharpe")
```

- Raises a clear `ImportError` if optuna is missing, suggesting `pip install stockstat[optimize]`

### Walk-forward (`walkforward.py`)

```python
from stockstat.backtest.walkforward import walk_forward

segments = walk_forward(make_engine, index, train_size=100, test_size=50, step=50)
for test_start, test_end, result in segments:
    print(test_start, test_end, result.metrics()["sharpe"])
```

- Rolling train → test windows to avoid overfitting

### Monte Carlo (`montecarlo.py`)

- `bootstrap_returns(returns, n_samples)`: resample returns with replacement
- `monte_carlo_equity(returns, initial, n_samples)`: generate alternative equity curves DataFrame
- `shuffle_orders(fills, seed)`: shuffle order timing to assess sequence robustness

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_optimize.py -v
# 8 passed
```

Covers: grid search sorting / best-first / all combinations, walk-forward segments, bootstrap length, Monte Carlo equity DataFrame, order shuffle preserves count, optuna import-error message.

## Next phase

BT-7: DSL integration + full 12-strategy test suite + documentation.
