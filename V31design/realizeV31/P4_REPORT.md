# P4 Implementation Report

## Result

P4 implemented the persistent Dispatcher state model, typed planners, Job idempotency, worker sessions, Lease/fencing, events, retry, cancellation, and restart recovery.

## Implemented

- Added SQLite and PostgreSQL Task Store adapters. PostgreSQL state is isolated in `stockstat_v31_dispatcher`.
- Persisted Jobs, Stages, WorkUnits, Attempts, Workers, JobEvents, idempotency keys, and ingestion schedule records.
- Added typed planners for indicator, time-series analysis, and single backtest Jobs.
- Planners resolve Dataset inputs to immutable Snapshot Artifacts before WorkUnits become ready.
- Added worker registration/session replacement, capability matching, priority/FIFO claim, start, renew, complete, fail, cancellation, lease expiry reaping, retry backoff, and terminal result publication.
- Lease secrets are stored as SHA-256 token hashes. Completion requires the current Attempt, generation ownership, session, token, and unexpired lease.
- Job state changes and events are written in one database transaction.
- Dispatcher source has no pandas or Finance Kernel import.

## Verification

```powershell
.venv-v31\Scripts\python.exe -m pytest tests_v31/services/dispatcher -q -m "not postgres"
$env:STOCKSTAT_V31_POSTGRES_URL="postgresql://user:password@host:5432/stockstat"
.venv-v31\Scripts\python.exe -m pytest tests_v31/services/dispatcher/test_postgres.py -q
```
