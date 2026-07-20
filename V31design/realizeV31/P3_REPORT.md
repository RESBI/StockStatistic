# P3 Implementation Report

## Result

P3 implemented the Storage role and the mutable-market-data to immutable-Artifact path.

## Implemented

- Added SQLite and PostgreSQL market repository adapters with the same OHLCV upsert/range/watermark contract.
- Isolated PostgreSQL objects in the `stockstat_v31_storage` schema.
- Added deterministic synthetic ingestion and ingest batch identities.
- Added content-addressed LocalFS and S3-compatible blob adapters.
- Added Artifact commit, metadata persistence, SHA-256/size verification, and atomic LocalFS publication.
- Added DatasetSnapshot caching keyed by selector, ingest watermarks, normalization version, and schema version.
- Snapshot creation executes one market query, writes Arrow record batches, publishes the Artifact, then persists the manifest.
- Added Storage FastAPI metadata, ingest, snapshot, Artifact metadata, and Artifact content endpoints.
- Added a Kernel interoperability test that opens the Snapshot Arrow stream directly as a `MarketDataset`.

## PostgreSQL

The required integration URL is provided through `STOCKSTAT_V31_POSTGRES_URL`. The implementation does not embed credentials in source code.

## Verification

```powershell
.venv-v31\Scripts\python.exe -m pytest tests_v31/services/storage tests_v31/e2e/test_snapshot_kernel_interop.py -q
$env:STOCKSTAT_V31_POSTGRES_URL="postgresql://user:password@host:5432/stockstat"
.venv-v31\Scripts\python.exe -m pytest tests_v31/services/storage/test_postgres.py -q
```
