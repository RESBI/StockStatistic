# P1 Implementation Report

## Result

P1 established the isolated V3.1 workspace, Contracts package, dependency boundaries, ADRs, and the audited V3.0 baseline.

## Implemented

- Added the V3.1 package/service skeleton under `packages/`, `services/`, and `tests_v31/`.
- Fixed the supported runtime to Python 3.11/3.12 and provided `.venv-v31` installation/test scripts.
- Implemented UUIDv7-compatible IDs, UTC validation, half-open time ranges, canonical JSON, and SHA-256 digests.
- Implemented typed Contracts for control envelopes, jobs, input bindings, execution policies, work leases, resources, datasets, snapshots, artifacts, capabilities, and errors.
- Added architecture tests that prevent V3.1 imports from the V3.0 backend/worker packages and prevent Dispatcher/Storage from importing Kernel.
- Recorded the legacy API surface and legacy test baseline in `tests_v31/fixtures/legacy_api_surface.json`.
- Frozen ADR-01 through ADR-08 in `V31design/realizeV31/ADR.md`.

## Legacy Baseline

- Commit: `8dae0e6ff27f088853709f7195c0cfd5aaede223`.
- Frontend: 814 passed, 6 skipped.
- Backend: 15 passed.
- The root tests are not a valid aggregate pytest suite: `test_connection.py` and `test_perf.py` parse command-line arguments during import; deployment files require their custom script runner and do not define the pytest `env` fixture. These pre-existing limitations were recorded rather than changing the oracle.

## Safety

- No V3.0 runtime file was modified.
- No deletion was performed.
- `recycleBin/` was created as the project-local safety destination for later cutover moves.

## Verification

Run:

```powershell
scripts/install_v31.ps1
.venv-v31\Scripts\python.exe -m pytest tests_v31/contracts tests_v31/architecture -q
```
