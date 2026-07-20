# P8 Implementation Report

## Result

P8 completed the V3.1 user-facing SDK toolchain and migrated the representative PAXG research workflow.

## Implemented

- One `StockStat` Session supports `local()` and `connect()` with the same namespace APIs.
- Added data, indicator, time-series, backtest, experiment, simulation, validation, strategy, and Job result views.
- Added a single DSL compiler for the SQL-like OHLCV/indicator subset. It compiles to a typed DatasetSelector and indicator operations.
- Added an AST migration scanner for legacy clients, TaskRef/storage classes, weak remote calls, DSL calls, render calls, and dynamic lambda strategies.
- Added Ed25519-signed strategy source packages with SHA-256 verification and archive path validation.
- Added CLI commands for version, migration scanning, DSL explanation, strategy packaging, and strategy verification.
- Added Arrow-backed table result views and local/remote lazy Artifact materialization.
- Migrated PAXG research code into `working/PAXG-Weekend-Monday-Law-v5-v31` without legacy Python imports.

## PAXG Run

- Completed against the existing real Binance Parquet inputs.
- Produced 307 research rows and a full 52-strategy migration matrix.
- Marked 45 strategies V3.1-native and 7 exact time/cross-session strategies analysis-only.
- Completed 180/180 V3.1-native Kernel backtests (45 strategies x 4 fee models), 5 search trials, 200 Monte Carlo samples, and 3 walk-forward windows.
- Reproduced representative redo total returns and the prior selection-bias/path-order conclusions while proving every strategy marked V3.1-native executes successfully.
- `stockstat migrate-scan` reported zero legacy findings in the new directory.

## Verification

```powershell
.venv-v31\Scripts\python.exe -m pytest tests_v31/sdk tests_v31/migration -q
```
