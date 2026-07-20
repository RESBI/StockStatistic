# P5 Implementation Report

## Result

P5 connected the Finance Kernel, Storage, Dispatcher, spawn Worker, Artifact cache, and public `StockStat.local()` entry into one complete embedded Job path.

## Implemented

- Added persistent Worker identity and per-start Worker session identity.
- Added capability allowlist registration and capacity metadata.
- Added digest-addressed Worker Artifact cache with size/hash verification.
- Added a mandatory `multiprocessing` spawn supervisor. Child processes receive only typed WorkLease JSON, input file paths, and an output directory.
- Added BLAS/OpenMP thread controls, timeout termination, child-crash classification, and scratch cleanup.
- Added Kernel execution for indicator, time-series, and backtest WorkUnits.
- Worker publishes output Artifacts before calling Dispatcher complete.
- Added Embedded Control Channel, Local runtime composition, JobHandle, lazy Indicator/Backtest result views, and `StockStat.local()`.
- Added built-in strategy factories that are imported in the child process through StrategyRef rather than serialized Python closures.

## Invariant

`StockStat.local()` does not call Kernel directly. Synchronous methods call `submit().wait()` and produce persisted Job, WorkUnit, Attempt, Event, Snapshot, and Artifact records.

## Verification

```powershell
.venv-v31\Scripts\python.exe -m pytest tests_v31/services/worker tests_v31/e2e/test_embedded_recovery.py -q
```
