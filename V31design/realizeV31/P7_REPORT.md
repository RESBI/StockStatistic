# P7 Implementation Report

## Result

P7 added compound financial Jobs using Planner fan-out/fan-in and typed Worker reducers while retaining one atomic backtest implementation.

## Implemented

- Added `finance.experiment.search@1.0` with canonical candidate IDs, candidate batching, backtest shard execution, stable ranking, and a reducer Artifact.
- Added `finance.experiment.batch@1.0` with explicit run IDs, batched atomic backtests, and summary reduction.
- Added `finance.simulation.resample@1.0` with deterministic per-simulation seed streams independent of shard count and retry order.
- Added `finance.validation.walk_forward@1.0` with explicit half-open windows and cross-window reduction.
- Dispatcher persists downstream Reducer WorkUnits as blocked, unlocks them only after every upstream WorkUnit succeeds, and injects only upstream ArtifactRefs.
- Worker selects `execute` or `reduce` by the internal WorkLease role. Reducers load Arrow shard tables; Dispatcher never imports pandas or Kernel.
- Added public experiment, simulation, and validation facades.

## Verification

```powershell
.venv-v31\Scripts\python.exe -m pytest tests_v31/e2e/test_compound_finance.py -q
```
