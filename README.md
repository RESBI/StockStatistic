# StockStat V3.1

StockStat V3.1 is a finance computation platform built around explicit Contracts, a deterministic finance Kernel, immutable Arrow Artifacts, a persistent Dispatcher state machine, spawn-isolated Workers, and one public SDK.

V3.1 is a breaking replacement for the archived V3 runtime. New code must use `StockStat.local()` or `StockStat.connect()` and must not import packages under `legacy/`.

## Architecture

- `packages/contracts`: lightweight Pydantic protocol and domain contracts.
- `packages/kernel`: indicators, time-series analysis, backtesting, and compound experiment execution.
- `packages/sdk`: the public `stockstat` package, local/remote Session APIs, DSL, migration scanner, and strategy package tooling.
- `packages/local`: embedded composition for one-process local use.
- `services/storage`: OHLCV repositories, snapshots, Artifact metadata, LocalFS, and S3-compatible blobs.
- `services/dispatcher`: persistent Job/Stage/Work/Attempt state machine and HTTP/SSE control plane.
- `services/worker`: spawn-isolated compute agent and Artifact cache.
- `tests_v31`: the V3.1 contract, architecture, kernel, service, E2E, fault, security, and performance tests.

Large data never passes through Dispatcher control messages. Storage publishes immutable Arrow Artifacts; Dispatcher persists only metadata and references; Workers materialize inputs directly from Storage.

## Install

Python 3.11 or 3.12 is required.

```powershell
scripts\install_v31.ps1
```

Manual editable installation order:

```powershell
.venv-v31\Scripts\python.exe -m pip install -r requirements-v31.txt
.venv-v31\Scripts\python.exe -m pip install -e packages/contracts -e packages/kernel
.venv-v31\Scripts\python.exe -m pip install -e services/storage -e services/dispatcher
.venv-v31\Scripts\python.exe -m pip install -e packages/sdk -e services/worker -e packages/local
```

## Embedded Use

```python
from stockstat import StockStat

ss = StockStat.local(".stockstat-v31")
try:
    ss.data.ingest(
        "PAXG/USDT",
        source="synthetic",
        venue="synthetic",
        asset_class="crypto",
        timeframe="1d",
        start="2024-01-01",
        end="2024-06-01",
    )
    data = ss.data.selector(
        "PAXG/USDT",
        source="synthetic",
        venue="synthetic",
        asset_class="crypto",
        timeframe="1d",
        start="2024-01-01",
        end="2024-06-01",
    )
    ma20 = ss.indicators.ma(data, window=20)
finally:
    ss.close()
```

## Network Use

Start the services:

```powershell
stockstat-storage --database-url sqlite:///market.db --artifact-root .stockstat-v31/artifacts
stockstat-dispatcher --database-url sqlite:///tasks.db --storage-url http://127.0.0.1:8101
stockstat-worker --dispatcher-url http://127.0.0.1:8100 --storage-url http://127.0.0.1:8101
```

Connect with the same API surface:

```python
from stockstat import StockStat

ss = StockStat.connect(
    "http://127.0.0.1:8100",
    storage_url="http://127.0.0.1:8101",
    token="client-token",
)
```

Production deployments should configure separate client and Worker tokens, PostgreSQL, and S3-compatible Artifact storage. See `docs/DEPLOYMENT.md` and `docs/OPERATIONS.md`.

## Compound Jobs

The Dispatcher plans and persists fan-out/fan-in WorkUnits for:

- `ss.experiments.grid_search(...)`
- `ss.experiments.batch(...)`
- `ss.simulations.bootstrap(...)`
- `ss.validation.walk_forward(...)`

Reducers receive only upstream Artifact references. Fixed random seeds are stable across shard counts and retries.

## DSL And Migration

```powershell
stockstat dsl-explain "SELECT close, ma(close, 20) AS ma20 FROM ohlcv('PAXG/USDT','1d','2024-01-01','2024-02-01')"
stockstat migrate-scan path\to\old_project
stockstat strategy-package strategy.py strategy:build strategy.zip
stockstat strategy-verify strategy.zip --trusted-key PUBLIC_KEY_HEX
```

The network protocol does not deserialize pickle or cloudpickle payloads. Remote Python strategies are importable/signed modules or packages, not arbitrary serialized functions.

## PAXG Migration

`working/PAXG-Weekend-Monday-Law-v5-v31` is the V3.1-native migration of the PAXG research series.

- 307 real Binance Monday/weekend observations.
- 52-strategy migration matrix.
- 45 V3.1-native strategies and 7 explicitly analysis-only cross-session/time-exit strategies.
- 180/180 native strategy x fee backtests succeeded.
- Search, deterministic Monte Carlo, and walk-forward Jobs succeeded.
- No legacy API findings in the migrated directory.

See `working/PAXG-Weekend-Monday-Law-v5-v31/RUN_REPORT.md`.

## Test

```powershell
scripts\run_v31_tests.ps1
```

PostgreSQL contract and HA tests:

```powershell
$env:STOCKSTAT_V31_POSTGRES_URL = "postgresql://user:password@host:5432/stockstat"
.venv-v31\Scripts\python.exe -m pytest tests_v31 -q
```

## Release Status

The repository cutover is V3.1-only. The current machine passed SQLite, authenticated network, fault, security, performance baseline, PAXG, and real PostgreSQL tests. Redis and MinIO were not reachable and Docker was not installed during final verification, so production deployment remains **No-Go** until the external S3/MinIO and deployment/backup drills in `V31design/realizeV31/P9_REPORT.md` are completed.

## License

GNU General Public License v3.0. See `LICENSE`.

This software is for research and education and is not financial advice.
