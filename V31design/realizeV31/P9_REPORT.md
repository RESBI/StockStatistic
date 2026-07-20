# P9 Production Hardening And Cutover Report

## Result

The V3.1 repository cutover and all locally executable hardening gates are complete. The codebase is V3.1-only at the default entry points, but the production release decision is **No-Go** because Redis/MinIO and Docker deployment drills could not be executed in the available environment.

## Implemented

### Reliability And HA

- Persistent PostgreSQL/SQLite Job, WorkUnit, Attempt, event, and idempotency state.
- Attempt fencing by current Attempt ID, generation, Worker session, token hash, expiry, and terminal state.
- Lease renewal thread in Worker Agent and periodic lease reaper in embedded runtime.
- Lease expiry respects `max_attempts` and becomes terminal when the retry budget is exhausted.
- Multi-replica event sequence serialization and duplicate-safe completion/failure IDs.
- Worker drain state, capability role matching, and CPU/memory/scratch/GPU resource matching.
- Executor crash isolation; Agent remains alive and can execute the next Job.
- Executor crash/OOM/disk-full error classification.
- SSE `Last-Event-ID` resume and JSON event polling.

### PostgreSQL And Storage

- Separate `stockstat_v31_storage` and `stockstat_v31_dispatcher` schemas.
- Bounded `psycopg_pool` pools, connection timeout, and statement timeout.
- SQLite WAL for local Dispatcher.
- Atomic LocalFS publish with temporary cleanup.
- S3-compatible multipart upload, server-side encryption configuration, one-hour maximum presigned URL, and digest-prefix layout.
- Artifact expected-digest validation, read/download digest verification, metadata rollback on publish failure, and orphan reconciliation/GC.
- Streaming Artifact HTTP responses and upload size limits.

### Security

- Optional enforced bearer scopes: `jobs`, `cluster`, `data`, and `artifacts`.
- Separate Worker internal token for internal control and Artifact routes.
- Constant-time token comparison and SHA-256-derived persisted principal IDs.
- Job ownership checks across status/result/events/cancel and tenant-scoped idempotency.
- Artifact ownership metadata and cross-tenant content hiding.
- Lease token removed from spawn executor payload; child receives only `WorkUnitSpec`.
- No pickle/cloudpickle import in V3.1 runtime or migrated PAXG code.
- Ed25519 strategy package signatures, trust store, scanner hook, digest check, zip-slip check, and unpacked-size limit.
- One MiB Dispatcher control-message limit and Storage upload limit.

### Operations

- Liveness/readiness endpoints.
- Low-cardinality Prometheus text metrics and autoscaling demand endpoint.
- Non-root, read-only, cap-dropped Docker image/profile with tmpfs Worker scratch.
- PostgreSQL + MinIO + Storage + multi-Dispatcher + multi-Worker Compose profile.
- Deployment, backup/restore, Artifact GC, Worker drain/upgrade, incident, capacity, and Windows Worker runbooks.
- Clean Python 3.12 installation drill from an empty virtual environment.
- Old runtime and old tests/docs moved under `legacy/`; root package imports resolve only to V3.1.

## Verification

Final V3.1 suite with real PostgreSQL configured:

```text
51 passed, 1 warning
```

Additional completed runs:

- Ruff: all V3.1 source and tests passed.
- Real PostgreSQL 18.4 connection: passed.
- PostgreSQL Storage round-trip: passed.
- PostgreSQL Dispatcher round-trip: passed.
- Two Dispatcher instances concurrently claiming one WorkUnit: exactly one lease accepted.
- Unauthenticated real-process network E2E: passed.
- Authenticated Storage/Dispatcher/Worker/Client process E2E: passed.
- Executor crash followed by successful Job on the same Agent: passed.
- PAXG: 180/180 native backtests, 5/5 search trials, 200 Monte Carlo samples, and 3/3 walk-forward windows.
- Clean install: `stockstat` resolved to `packages/sdk`, SDK and CLI reported `3.1.0`.

## Environment Gaps

The following required production drills were not executable:

- Redis on localhost timed out; `192.168.0.114:6379` refused the connection.
- MinIO on `192.168.0.114:9000/9001` refused the connection.
- Docker CLI was not installed.
- Therefore no real MinIO multipart/presign/credential-rotation/lifecycle drill, Compose rolling restart, full load-balancer HA, Redis flush/rebuild, or container escape profile test was performed.
- PostgreSQL backup/restore was documented but not executed against a disposable restored copy.
- Large 500 MB/3 GB Artifact, 10,000-trial, 10,000+ Monte Carlo, 100 Worker, and 100,000 WorkUnit macro tests were not run on this machine.

The S3 adapter has automated fake-client tests, and Redis is deliberately absent from the correctness path, but P9 explicitly requires real external-service testing before production certification.

## Go/No-Go

### Repository Cutover

**Go.** The root SDK, documentation, tests, Compose file, and install scripts are V3.1-only. Legacy runtime code remains read-only under `legacy/` and is not imported.

### Production Release

**No-Go.** MinIO/Docker, backup/restore, and macro capacity/chaos gates remain unverified. Do not claim production completion or route production writes until these drills pass in CI or a staging environment.
