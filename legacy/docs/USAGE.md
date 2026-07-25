# StockStat V3 Usage Guide

> **Version**: v3.0 (P0-P7 all complete)
> **Test baseline**: 922 tests passing + 6 Redis skipped; PAXG 132 backtests byte-level identical
> **Related**: [README.md](../README.md) | [DESIGN_V3_CN.md](../DESIGN_V3_CN.md) | [DESIGN_ARCHITECTURE.md](../DESIGN_ARCHITECTURE.md)

---

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Data Ingestion](#2-data-ingestion)
3. [Querying OHLCV Data](#3-querying-ohlcv-data)
4. [Computing Indicators](#4-computing-indicators)
5. [DSL Queries](#5-dsl-queries)
6. [Custom Indicators](#6-custom-indicators)
7. [Visualization](#7-visualization)
8. [Backtest](#8-backtest)
9. [Advanced Backtest Features](#9-advanced-backtest-features)
10. [Signal Processing and Nonlinear Dynamics](#10-signal-processing-and-nonlinear-dynamics)
11. [Result Export](#11-result-export)
12. [CLI Commands](#12-cli-commands)
13. [Offline Mode](#13-offline-mode)
14. [Plugin System](#14-plugin-system)
15. [Management Interface](#15-management-interface)
16. [V3 Distributed Compute](#16-v3-distributed-compute)
17. [V3 ComputeBackend Compatibility Layer](#17-v3-computebackend-compatibility-layer)
18. [V3 Dispatcher Deployment](#18-v3-dispatcher-deployment)
19. [V3 Worker Deployment](#19-v3-worker-deployment)
20. [V3 Cluster Management](#20-v3-cluster-management)
21. [V3 Task Lifecycle](#21-v3-task-lifecycle)
22. [V3 Deployment Scenarios](#22-v3-deployment-scenarios)
23. [PAXG Weekend Correlation Analysis](#23-paxg-weekend-correlation-analysis)
24. [Connection and Performance Tests](#24-connection-and-performance-tests)
25. [Startup Scripts](#25-startup-scripts)
26. [Environment Variables Reference](#26-environment-variables-reference)

---

## 1. Environment Setup

### 1.1 Installation

The project contains three independent pip packages:

```bash
# Backend (FastAPI + SQLAlchemy + Dispatcher)
cd backend && pip install -e .

# Frontend core library (ComputeEngine + backtest + DSL + V3 protocol layer)
cd frontend && pip install -e .

# V3 Worker standalone package (distributed compute)
cd worker && pip install -e .
```

### 1.2 Optional Extras

```bash
pip install -e "frontend/[matplotlib]"          # visualization
pip install -e "frontend/[dsl]"                 # DSL parser (lark)
pip install -e "frontend/[signal_processing]"   # wavelet transform (PyWavelets)
pip install -e "frontend/[backtest_full]"       # full backtest suite
pip install -e "frontend/[compute]"             # V3 local backend (cloudpickle + psutil)
pip install -e "frontend/[distributed]"         # V3 distributed (+ redis + msgpack)
pip install rich                                # TUI colored tables
```

> Frontend core dependencies are only pandas / numpy / scipy / httpx / pyarrow. When optional extras are not installed, related features gracefully degrade (CWT falls back to FFT self-implementation, visualization to NullRenderer with warning).

### 1.3 Enable Proxy (for Real Data Sources)

```bash
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http                    # or socks5
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889    # your proxy address
```

### 1.4 Start Backend

```bash
# Basic startup (Storage only)
stockstat serve --host 0.0.0.0 --port 8000

# V3 enable Dispatcher
STOCKSTAT_DISPATCHER_ENABLED=true stockstat serve --host 0.0.0.0 --port 8000

# V3 enable Dispatcher + Redis queue
STOCKSTAT_DISPATCHER_ENABLED=true \
STOCKSTAT_DISPATCHER_QUEUE=redis \
REDIS_URL=redis://redis:6379/0 \
stockstat serve --host 0.0.0.0 --port 8000
```

After startup:
- REST API at `http://localhost:8000/api/v1/*`
- Admin UI at `http://localhost:8000/admin/`
- Dispatcher routes at `http://localhost:8000/dispatch/*`

### 1.5 Specify Database

```bash
# SQLite default
export DATABASE_URL="sqlite:///stockstat.db"

# SQLite absolute path (note 4 slashes)
export DATABASE_URL="sqlite:////data/stockstat/stockstat.db"

# PostgreSQL
export DATABASE_URL="postgresql://user:pwd@host:5432/stockstat"
```

---

## 2. Data Ingestion

Supports multiple data sources (yfinance / Binance / Coinbase / synthetic), auto-detects source type (`/` in symbol → crypto, else → stock).

```python
from stockstat import StockStatClient
client = StockStatClient(host="localhost", port=8000)

# Stocks (Yahoo Finance)
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")

# Crypto (Binance, 16 time granularities)
client.ingest("BTC/USDT", source="binance", start="2024-01-01", timeframe="1h")

# Auto-detect
client.ingest("MSFT", start="2024-01-01")
```

CLI equivalent:

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

### 2.1 Batch Ingestion

```python
client.ingest_batch(["BTC/USDT", "ETH/USDT", "AAPL"],
                     source="binance", start="2024-01-01")
```

---

## 3. Querying OHLCV Data

```python
# Basic query
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")

# Bidirectional pagination (lazy-load)
recent = client.ohlcv("BTC/USDT", limit=500, order="desc")
earlier = client.ohlcv("BTC/USDT", end="2024-01-01", limit=1000, order="desc")

# Batch query
batch = client.ohlcv_batch(["BTC/USDT", "ETH/USDT"], start="2024-01-01")
```

CLI:

```bash
stockstat query BTC/USDT --limit 5
stockstat query AAPL --start 2024-01-01 --format csv
```

---

## 4. Computing Indicators

23 technical indicators + 8 nonlinear dynamics functions.

### 4.1 Trend Indicators

```python
sma = client.compute.ma(data.close, window=20)
ema = client.compute.ema(data.close, window=12)
macd_line, signal_line, hist = client.compute.macd(data.close)
```

### 4.2 Oscillator Indicators

```python
rsi = client.compute.rsi(data.close, window=14)
k, d, j = client.compute.kdj(data.high, data.low, data.close, window=9)
```

### 4.3 Volatility Indicators

```python
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
atr = client.compute.atr(data.high, data.low, data.close, window=14)
std = client.compute.std(data.close, window=20)
```

### 4.4 Statistical Indicators

```python
beta = client.compute.beta(stock_returns, market_returns, window=60)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
dd = client.compute.max_drawdown(data.close)
var_95 = client.compute.var(returns, confidence=0.95)
corr = client.compute.corr(x, y)
```

### 4.5 Signal Processing and Nonlinear Dynamics

```python
import numpy as np
path = data.close.values[-48:]

# Signal processing
coef, scales = client.compute.wavelet_decompose(path, scales=np.arange(1, 25))
h_spec = client.compute.spectral_entropy(np.diff(np.log(path)))
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)
forecast = client.compute.gm11_predict(sequence)

# Nonlinear dynamics
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))
te = client.compute.transfer_entropy(btc_rets, eth_rets)
sampen = client.compute.sample_entropy(signal, m=2)
permen = client.compute.permutation_entropy(signal, m=3)

# Visualization
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
client.plot.get_renderer().render(spec)
```

---

## 5. DSL Queries

SQL-like declarative query language, one-line data query + indicator computation.

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')

# WHERE filter
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

---

## 6. Custom Indicators

```python
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, threshold=0.04):
    vol = data.close.pct_change().rolling(window).std()
    return vol.apply(lambda v: "high" if v > threshold else "low")

# Immediately available in DSL
result = client.run_dsl('''
    SELECT close, volatility_regime(close, 20) AS regime
    FROM ohlcv("BTC/USDT", "1d")
''')
```

---

## 7. Visualization

### 7.1 Protocol-Based Plotting

```python
from stockstat.plot import PlotSpec

spec = PlotSpec(title="BTC Price", x_label="Date", y_label="Price")
spec.add_series(name="close", data=data.close, kind="line")
spec.add_series(name="ma20", data=data.close.rolling(20).mean(), kind="line")

renderer = client.plot.get_renderer()
renderer.render(spec, path="btc.png")
```

### 7.2 Backtest Visualization

```python
res.render("equity", path="equity.png")           # equity curve
res.render("drawdown", path="drawdown.png")       # drawdown
res.render("trades", path="trades.png")           # trade markers
res.render("dashboard", path="dashboard.png")     # full dashboard
```

Supports 9 chart types: equity curve, drawdown, trade markers, returns distribution, monthly heatmap, annual returns, parameter grid heatmap, underwater curve, comprehensive dashboard.

---

## 8. Backtest

### 8.1 Basic Backtest

```python
from stockstat.backtest import BacktestEngine, strategy, Order

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21: return
    ma5 = d.close.rolling(5).mean().iloc[-1]
    ma20 = d.close.rolling(20).mean().iloc[-1]
    pos = ctx.portfolio.get_position("BTC/USDT")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

data = client.ohlcv("BTC/USDT", start="2024-01-01")
res = client.backtest({"BTC/USDT": {"1d": data}}, ma_cross, initial_cash=10000)
print(res.summary())
```

### 8.2 Multi-Instrument / Multi-Timeframe

```python
data = {
    "BTC/USDT": {"1d": btc_1d, "1h": btc_1h},
    "ETH/USDT": {"1d": eth_1d, "1h": eth_1h},
}
res = client.backtest(data, strategy, initial_cash=10000)
```

### 8.3 Cost / Fill / Execution Models

```python
from stockstat.backtest import (
    BacktestEngine, IntrabarExecution,
    BINANCE_SPOT_BNB, BINANCE_FUTURES_BNB,
)

engine = BacktestEngine(
    data=data,
    strategy=strategy,
    initial_cash=10000,
    cost_model=BINANCE_SPOT_BNB,           # Binance spot + BNB discount
    execution_model=IntrabarExecution(     # same-bar entry+exit
        intrabar_tf="1h", parent_tf="1d",
    ),
    allow_short=True,
    periods_per_year=52,
)
res = engine.run()
```

**8 cost models**: PercentCost / FixedCost / TieredCost / MinCost / StampDutyCost / ZeroCost / MakerTakerCost / BinanceCost (incl. 4 BINANCE_* presets)

**7 fill models**: NextOpenFill / NextCloseFill / ThisCloseFill / VWAPFill / WorstPriceFill / IntrabarLimitFill / IntrabarFillModel

**2 execution models**: NextBarExecution (default) / IntrabarExecution (same-bar entry+exit)

---

## 9. Advanced Backtest Features

### 9.1 Parameter Grid Search

```python
from stockstat.backtest.optimizer import grid_search

results = grid_search(
    make_engine,
    param_grid={"short": [3, 5, 8, 10], "long": [20, 30, 40]},
    metric="sharpe",
    maximize=True,
)
print(results[0])  # best parameter combination
```

### 9.2 Batch Backtest

```python
from stockstat.backtest.batch_runner import StrategyBatchRunner

runner = StrategyBatchRunner(data=data, initial_cash=10000)
results = runner.run_all_fees(
    strategies={"ma_cross": ma_cross_strategy, "rsi_reversal": rsi_strategy},
    fee_models={"spot": BINANCE_SPOT, "futures": BINANCE_FUTURES},
)
df = results.to_dataframe()
```

### 9.3 Monte Carlo Simulation

```python
from stockstat.backtest.montecarlo import monte_carlo_equity

curves = monte_carlo_equity(
    returns, initial=10000, n_samples=1000, seed=42,
)
# 1000 simulated equity curves
```

---

## 10. Signal Processing and Nonlinear Dynamics

8 advanced analysis functions:

| Function | Use case |
|----------|----------|
| `wavelet_decompose(signal, scales, wavelet)` | Continuous Wavelet Transform (CWT) |
| `spectral_entropy(signal, fs)` | Spectral entropy (frequency-domain complexity) |
| `grey_relation(x0, xi, rho)` | Grey relational degree |
| `gm11_predict(sequence)` | GM(1,1) grey prediction |
| `transfer_entropy(x, y, k, n_bins)` | Transfer entropy (directed information flow) |
| `hurst_dfa(signal)` | Hurst exponent (DFA) |
| `sample_entropy(signal, m, r)` | Sample entropy |
| `permutation_entropy(signal, m, tau)` | Permutation entropy |

3 PlotSpec factories: `wavelet_scalogram` / `dfa_fit` / `psd_plot`

---

## 11. Result Export

```python
# DataFrame export
df = data.reset_index()
df.to_csv("btc.csv", index=False)
df.to_parquet("btc.parquet")

# Backtest result export
res.equity.to_csv("equity.csv")
res.fills_df.to_csv("fills.csv")
res.metrics()  # dict

# Via Codec
from stockstat._core.codec import ArrowCodec, ParquetCodec
arrow_bytes = ArrowCodec().encode(data)
parquet_bytes = ParquetCodec().encode(data)
```

---

## 12. CLI Commands

```bash
# Data ingestion
stockstat ingest AAPL --source yfinance --start 2024-01-01
stockstat ingest BTC/USDT --source binance --tf 1h

# Data query
stockstat query BTC/USDT --limit 5
stockstat query AAPL --start 2024-01-01 --format csv

# Symbol management
stockstat symbols
stockstat sources

# TUI interface
stockstat tui
stockstat tui --host 192.168.1.100

# Service startup
stockstat serve --host 0.0.0.0 --port 8000

# V3 cluster management (P7+)
stockstat cluster info
stockstat cluster workers
stockstat cluster stats

# V3 Worker startup (standalone package)
stockstat-compute worker --dispatcher-url http://localhost:8000
```

---

## 13. Offline Mode

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage, SQLStorage

# In-memory offline
client = V2Client(mode="offline", storage=MemoryStorage())
client.ingest("BTC/USDT", source="binance", start="2024-01-01")
df = client.ohlcv("BTC/USDT")

# Read existing SQLite
client = V2Client(mode="offline",
                  storage=SQLStorage(database_url="sqlite:///stockstat.db"))

# Persist to new SQLite
client = V2Client(mode="offline",
                  storage=SQLStorage(database_url="sqlite:///my_data.db"))
client.ingest("AAPL", source="yfinance", start="2024-01-01")
```

---

## 14. Plugin System

```python
from stockstat._core.plugin import PluginRegistry
from stockstat._domain.indicators import register_default_indicators
from stockstat._domain.sources import register_default_sources

reg = PluginRegistry()
register_default_indicators(reg)
register_default_sources(reg)

# List registered plugins
print(reg.list("indicators"))
print(reg.list("sources"))

# Call
plugin = reg.get("sources", "binance")
df = plugin.fetch_ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
```

---

## 15. Management Interface

### 15.1 TUI Terminal

```bash
stockstat tui                    # connect to local server
stockstat tui --host 192.168.1.100
```

6 interactive menus: browse symbols / query OHLCV / ingest data / data stats / list sources / view proxy config.

### 15.2 Web Admin

Browse to `http://storage-server:8000/admin/`:

| Page | Features |
|------|----------|
| Overview dashboard | Symbol count, row count, disk, data coverage Gantt |
| Source browser | Pagination + search + batch download + manual input |
| Local symbols | K-line chart (lazy-load on zoom) + CSV export |
| Config | Database / proxy / cache / disk |
| Logs | Ingest history (paginated + filtered) |

### 15.3 V3 Dispatcher Monitoring

When `STOCKSTAT_DISPATCHER_ENABLED=true` + `STOCKSTAT_ADMIN_ENABLED=true`:

```bash
# Cluster topology
curl http://localhost:8000/admin/api/dispatcher/cluster

# Task history
curl http://localhost:8000/admin/api/dispatcher/tasks?limit=10

# Task stats
curl http://localhost:8000/admin/api/dispatcher/stats

# Autoscaler metrics
curl http://localhost:8000/admin/api/dispatcher/autoscaler
```

---

## 16. V3 Distributed Compute

### 16.1 Design Philosophy

V3 adds a **distributed compute layer** on top of v2.1, decoupling "where to compute" from "what to compute" via the `ComputeBackend` Protocol:

```
Client → ComputeBackend Protocol → LocalComputeBackend (default)
                                 → RemoteComputeBackend (HTTP → Dispatcher → Worker)
                                 → AutoComputeBackend (auto-route by size)
```

**Core constraint**: v1.7 / v2 public APIs unchanged; when `compute_backend=None` (default), behavior is identical to v2.1.

### 16.2 Three ComputeBackends

| Implementation | Scenario | Behavior |
|----------------|----------|----------|
| `LocalComputeBackend` | Default / single-machine | Background thread, returns TaskRef; identical to v2.1 |
| `RemoteComputeBackend` | Distributed | Build TaskSpec → Transport submit to Dispatcher → poll results |
| `AutoComputeBackend` | Hybrid | Heavy tasks (grid_search/monte_carlo) → remote; light → local |

### 16.3 V3 Explicit Async

```python
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)

# Explicit async submit
task = client.compute.remote(
    "backtest",
    symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01",
    strategy_ref=strategy_ref,
    initial_cash=10000,
)
print(task.id, task.status)  # UUID + "pending" / "running" / "completed"

# Wait for result
result = task.wait(timeout=3600)

# Non-blocking query
info = client.compute_backend.get(task.id)
print(info.state, info.progress)

# Cancel
task.cancel()

# Stream results
for partial in task.stream_results():
    print(f"Progress: {partial.get('progress', 0):.0%}")
```

### 16.4 Transparent Sync Mode

```python
# Inject RemoteComputeBackend, backtest() auto submit + wait
from stockstat._core.compute import RemoteComputeBackend
client = StockStatClient(
    host="localhost", port=8000,
    compute_backend=RemoteComputeBackend("http://localhost:8000"),
)
result = client.backtest(data, strategy, initial_cash=10000)
# Internal: build TaskSpec → submit → wait → return BacktestResult

# async_submit=True returns TaskRef
task = client.backtest(data, strategy, async_submit=True)
# ... do other things ...
result = task.wait(timeout=3600)
```

---

## 17. V3 ComputeBackend Compatibility Layer

### 17.1 StockStatClient Integration

```python
from stockstat import StockStatClient
from stockstat._core.compute import (
    LocalComputeBackend, RemoteComputeBackend, AutoComputeBackend,
)

# Default (no compute_backend) → LocalComputeBackend lazily created
client = StockStatClient(host="localhost", port=8000)

# Explicit LocalComputeBackend
client = StockStatClient(compute_backend=LocalComputeBackend())

# Remote
client = StockStatClient(
    compute_backend=RemoteComputeBackend("http://dispatch:9000"),
)

# Auto routing
client = StockStatClient(compute_backend=AutoComputeBackend(
    local=LocalComputeBackend(),
    remote=RemoteComputeBackend("http://dispatch:9000"),
))
```

### 17.2 V2Client Integration

```python
from stockstat._api.client import V2Client
from stockstat._core.compute import RemoteComputeBackend

client = V2Client(mode="offline",
                  compute_backend=RemoteComputeBackend("http://dispatch:9000"))
```

### 17.3 Compatibility Matrix

| Client | ComputeBackend | Behavior |
|--------|---------------|----------|
| `StockStatClient` | `LocalComputeBackend` (default) | Identical to v2.1 |
| `StockStatClient` | `RemoteComputeBackend` | Transparent sync + explicit async |
| `V2Client(mode="online")` | `LocalComputeBackend` (default) | Identical to v2.1 |
| `V2Client(mode="online")` | `RemoteComputeBackend` | Transparent sync + explicit async |
| `V2Client(mode="offline")` | `LocalComputeBackend` (default) | Identical to v2.1 |
| `V2Client(mode="offline")` | `RemoteComputeBackend` | Offline data + remote compute |

---

## 18. V3 Dispatcher Deployment

### 18.1 As Storage Plugin (Scenario D)

```bash
# 1. Start Storage + Dispatcher (same process)
STOCKSTAT_DISPATCHER_ENABLED=true \
STOCKSTAT_ADMIN_ENABLED=true \
stockstat serve --host 0.0.0.0 --port 8000

# 2. Start Worker (another machine)
stockstat-compute worker --dispatcher-url http://storage:8000 --concurrency 8

# 3. Client
client = StockStatClient(
    host="storage", port=8000,
    compute_backend=RemoteComputeBackend("http://storage:8000"),
)
```

### 18.2 Independent Dispatcher (Scenario E)

```bash
# 1. Start Storage
stockstat serve --host 0.0.0.0 --port 8000

# 2. Start Dispatcher (independent process, Redis queue)
STOCKSTAT_DISPATCHER_ENABLED=true \
STOCKSTAT_DISPATCHER_QUEUE=redis \
REDIS_URL=redis://redis:6379/0 \
stockstat serve --host 0.0.0.0 --port 9000

# 3. Start multiple Workers
stockstat-compute worker --dispatcher-url http://dispatcher:9000 --concurrency 8

# 4. Client
client = StockStatClient(
    compute_backend=RemoteComputeBackend("http://dispatcher:9000"),
)
```

### 18.3 Docker Compose

```bash
docker compose up -d
# Starts db + redis + api + dispatcher + 4 workers
```

### 18.4 Dispatcher REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dispatch/submit` | POST | Submit TaskSpec |
| `/dispatch/status/{id}` | GET | Query status |
| `/dispatch/result/{id}` | GET | Get result |
| `/dispatch/cancel/{id}` | POST | Cancel task |
| `/dispatch/cluster` | GET | Cluster topology |
| `/dispatch/register` | POST | Worker register |
| `/dispatch/heartbeat` | POST | Worker heartbeat |
| `/dispatch/assign` | POST | Worker pull task |
| `/dispatch/complete` | POST | Return result |
| `/dispatch/fail` | POST | Report failure |
| `/dispatch/partial` | POST | Stream partial result |
| `/dispatch/preempt/{id}` | POST | Preempt task |
| `/dispatch/resume/{id}` | POST | Resume task |
| `/dispatch/drain/{id}` | POST | Worker drain |
| `/dispatch/discover` | GET | Service discovery |
| `/dispatch/autoscaler` | GET | Autoscaler metrics |
| `/dispatch/sub/register` | POST | Sub-dispatcher register |
| `/dispatch/tasks/history` | GET | Task history |
| `/dispatch/tasks/stats` | GET | Task stats |
| `/api/v1/tasks` | POST/GET | V2 §10.2 compat |

---

## 19. V3 Worker Deployment

### 19.1 Start Worker

```bash
# Basic startup
stockstat-compute worker \
    --dispatcher-url http://localhost:8000 \
    --concurrency 8 \
    --alias "gpu-box-alpha" \
    --label rack=A-12 \
    --label zone=datacenter-east

# Support preemption
stockstat-compute worker \
    --dispatcher-url http://dispatch:9000 \
    --preemptable
```

### 19.2 Worker CLI Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--dispatcher-url` | required | Dispatcher URL |
| `--concurrency` | CPU count | Max concurrent tasks |
| `--alias` | hostname-pid | Worker alias |
| `--label key=value` | — | Labels (repeatable) |
| `--capability` | all | Task type capability (repeatable) |
| `--preemptable` | false | Allow preemption |
| `--poll-interval` | 1.0s | Task poll interval |
| `--heartbeat-interval` | 10.0s | Heartbeat interval |

### 19.3 Worker Lifecycle

```
start → detect_hardware() → POST /dispatch/register
                          ↓
            heartbeat thread (10s) → POST /dispatch/heartbeat
                          ↓
            main loop → POST /dispatch/assign → execute → POST /dispatch/complete
                          ↓
            SIGTERM → stop() → wait active tasks → POST /dispatch/unregister → exit
```

### 19.4 Worker State Machine

| status | Meaning | Dispatcher behavior |
|--------|---------|---------------------|
| `online` | Normal, accepting tasks | Normal dispatch |
| `busy` | Active tasks = concurrency | No new task dispatch |
| `draining` | Graceful drain in progress | Wait for active tasks |
| `offline` | Heartbeat timeout (30s) | Remove + reassign tasks |

---

## 20. V3 Cluster Management

### 20.1 Query Cluster Topology

```python
info = client.compute.cluster_info()

print(f"Dispatcher: {info['dispatcher']['alias']} @ {info['dispatcher']['address']}")
print(f"  status: {info['dispatcher']['status']}")
print(f"  uptime: {info['dispatcher']['uptime_s']}s")
print(f"  queue_depth: {info['dispatcher']['queue_depth']}")
print(f"  cache: {info['dispatcher']['cache_size_mb']}MB ({info['dispatcher']['cache_hit_rate']:.1%} hit)")

print(f"\nWorkers ({info['stats']['online_workers']}/{info['stats']['total_workers']} online):")
for w in info["workers"]:
    print(f"  {w['alias']:20s}  {w['status']:8s}  "
          f"CPU {w['hardware']['cpu']['cores_logical']} cores  "
          f"mem {w['hardware']['memory']['total_gb']}GB  "
          f"load {w['load'].get('cpu_percent', 0):.1f}%  "
          f"active {w['active_tasks']}/{w['concurrency']}")

print(f"\nSub-dispatchers: {len(info.get('sub_dispatchers', []))}")
for sub in info.get("sub_dispatchers", []):
    print(f"  {sub['alias']:20s}  {sub['address']}  {sub['status']}")
```

### 20.2 Filter by Labels

```python
info = client.compute.cluster_info(filter_labels={"zone": "datacenter-east"})
for w in info["workers"]:
    print(w["alias"])
```

### 20.3 Autoscaler Metrics

```python
import httpx
metrics = httpx.get("http://dispatch:8000/dispatch/autoscaler").json()
print(f"Queue depth: {metrics['queue_depth']}")
print(f"Active tasks: {metrics['active_tasks']}")
print(f"Available concurrency: {metrics['available_concurrency']}")
print(f"Scale up recommended: {metrics['scale_up_recommended']}")
print(f"Scale down recommended: {metrics['scale_down_recommended']}")
```

### 20.4 Task History

```python
import httpx
resp = httpx.get("http://dispatch:8000/dispatch/tasks/history?limit=10")
for h in resp.json()["history"]:
    print(f"  {h['task_id'][:8]}...  {h['task_type']:15s}  {h['state']:10s}  "
          f"worker={h.get('worker_id', '-')[:8]}")

# Filter by state
resp = httpx.get("http://dispatch:8000/dispatch/tasks/history?state=failed")
fails = resp.json()["history"]
print(f"\nFailed tasks: {len(fails)}")
for f in fails:
    print(f"  {f['task_id'][:8]}...  error: {f.get('error', '')[:80]}")
```

### 20.5 Task Stats

```python
import httpx
stats = httpx.get("http://dispatch:8000/dispatch/tasks/stats").json()
print(f"Total tasks: {stats['total_tasks']}")
print(f"By state: {stats['by_state']}")
print(f"By type: {stats['by_type']}")
print(f"Avg duration: {stats['avg_duration_s']}s")
```

---

## 21. V3 Task Lifecycle

### 21.1 Complete Flow

```python
# 1. Client builds TaskSpec
from stockstat._core.contracts.task import (
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
)

spec = TaskSpec(
    task_id=new_task_id(),
    data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d",
                       start="2024-01-01", end="2024-12-31"),
    compute_spec=ComputeSpec(
        task_type="grid_search",
        strategy_ref=strategy_ref,
        param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
        metric="sharpe",
        maximize=True,
        initial_cash=10000,
    ),
    dispatch_spec=DispatchSpec(
        split_strategy="param_wise",
        max_workers=4,
        timeout=3600,
        retry_count=2,
        preemptable=True,
    ),
    trace_id="my-trace-001",
)

# 2. Submit
task = client.compute_backend.submit(spec)
print(f"Submitted: {task.id}, status={task.status}")

# 3. Poll status
import time
while not task.ready():
    info = client.compute_backend.get(task.id)
    print(f"  state={info.state.value}, progress={info.progress:.0%}")
    time.sleep(1)

# 4. Get result
result = task.result()  # or task.wait(timeout=3600)
print(f"Best params: {result[0]['params']}, sharpe: {result[0]['sharpe']}")
```

### 21.2 Task States

```
pending → running → completed
   |         |
   |         |--> failed
   |         |
   |         +--> cancelled
   |
   +--> cancelled
```

### 21.3 Streaming Results

```python
# grid_search progress push
for partial in task.stream_results():
    if "progress" in partial:
        print(f"  Progress: {partial['progress']:.0%} "
              f"({partial.get('completed', 0)}/{partial.get('total', 0)})")
    else:
        # Final result
        print(f"  Final result: {len(partial)} combinations")
```

### 21.4 Task Cancellation

```python
task.cancel()
# or
client.compute_backend.cancel(task.id)
```

### 21.5 Preemption and Resume

```python
import httpx
# Preempt
httpx.post(f"http://dispatch:8000/dispatch/preempt/{task.id}?worker_id=w1")
# Resume
httpx.post(f"http://dispatch:8000/dispatch/resume/{task.id}?worker_id=w1")
```

### 21.6 Error Handling

```python
from stockstat._core.errors import (
    TaskError, TaskNotReadyError, TaskCancelledError,
    TaskTimeoutError, TaskNotFoundError,
)

try:
    result = task.wait(timeout=60)
except TaskError as e:
    print(f"Task failed: {e.message}")
    print(f"Error code: {e.code}")
    print(f"Context: {e.context}")
except TaskCancelledError:
    print("Task was cancelled")
except TaskTimeoutError:
    print("Task timed out")
```

---

## 22. V3 Deployment Scenarios

### 22.1 Scenario A: Single-Machine Full-Stack (Default)

```python
client = StockStatClient()  # default LocalComputeBackend
result = client.backtest(data, strategy)
```

### 22.2 Scenario B: Storage-Compute Separation

```python
client = StockStatClient(host="storage", port=8000)
# Data via HTTP, compute locally
data = client.ohlcv("BTC/USDT")
result = client.backtest(data, strategy)
```

### 22.3 Scenario C: Offline Mode

```python
client = V2Client(mode="offline", storage=MemoryStorage())
client.ingest("BTC/USDT", source="binance", start="2024-01-01")
result = client.backtest(client.ohlcv("BTC/USDT"), strategy)
```

### 22.4 Scenario D: Dispatcher + Worker

```bash
# Terminal 1: Storage + Dispatcher
STOCKSTAT_DISPATCHER_ENABLED=true stockstat serve --port 8000

# Terminal 2: Worker
stockstat-compute worker --dispatcher-url http://localhost:8000
```

```python
client = StockStatClient(
    compute_backend=RemoteComputeBackend("http://localhost:8000"),
)
result = client.backtest(data, strategy)
```

### 22.5 Scenario E: Independent Dispatcher + Worker Cluster

```bash
# 3 processes
stockstat serve --port 8000                    # Storage
STOCKSTAT_DISPATCHER_QUEUE=redis \
REDIS_URL=redis://redis:6379/0 \
stockstat serve --port 9000                    # Dispatcher
stockstat-compute worker --dispatcher-url http://localhost:9000 --concurrency 8
```

### 22.6 Scenario F: Multi-Level Dispatcher

```python
# Main Dispatcher
POST /dispatch/sub/register
{
    "sub_id": "sub-east-1",
    "alias": "dispatch-east",
    "address": "http://east:9000",
    "parent_url": "http://parent:8000"
}

# Query global topology
info = client.compute.cluster_info()
# info["sub_dispatchers"] contains all sub-dispatchers
```

### 22.7 Deployment Tests

```bash
cd tests/deployments

# Single-machine
python test_case_a_single_machine.py

# Storage-compute separation
python test_case_b_storage_separated.py --host 192.168.1.100

# Offline
python test_case_c_offline.py

# Explicit LocalComputeBackend
python test_case_d_local_compute_backend.py

# V3 distributed
python test_case_e_dispatcher_worker.py

# V3 multi-level
python test_case_f_multilevel.py
```

---

## 23. PAXG Weekend Correlation Analysis

V3 validation: 132 backtests byte-level identical to baseline.

```bash
cd working/PAXG-Weekend-Monday-Law-v5-redo/phase2_backtest

# Run 132 backtests
python run_redo.py

# V3 vs direct path comparison
python compare_v3.py
# Expected: All V3 LocalComputeBackend results identical to direct path

# View results
cat results/all_metrics_redo.csv | head
```

---

## 24. Connection and Performance Tests

```bash
# Connection smoke test
python tests/test_connection.py --host localhost --port 8000

# Communication performance test
python tests/test_perf.py --host localhost --port 8000 --rounds 10
```

---

## 25. Startup Scripts

```bash
# Minimal startup
backend/start.bat            # Windows
backend/start.sh             # Linux/macOS

# Full config (CLI args + interactive config)
backend/serve.bat --config   # Windows
backend/serve.sh --config    # Linux/macOS

# V3 Worker
stockstat-compute worker --dispatcher-url http://localhost:8000
```

---

## 26. Environment Variables Reference

### 26.1 Backend

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database connection string |
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | Proxy type (http/socks5) |
| `STOCKSTAT_PROXY_URL` | — | Proxy URL |
| `STOCKSTAT_ADMIN_ENABLED` | `true` | Enable web admin |
| `STOCKSTAT_DEFAULT_SOURCE` | `yfinance` | Default data source |
| `STOCKSTAT_DISPATCHER_ENABLED` | `false` | **V3** enable Dispatcher |
| `STOCKSTAT_DISPATCHER_QUEUE` | `memory` | **V3** queue backend (memory/redis) |
| `STOCKSTAT_DISPATCHER_CACHE_MB` | `512` | **V3** DataCache max size |
| `REDIS_URL` | — | **V3** Redis connection |

### 26.2 Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCKSTAT_HOST` | `localhost` | Default host |
| `STOCKSTAT_PORT` | `8000` | Default port |
| `STOCKSTAT_USE_HTTPS` | — | Enable HTTPS |
| `STOCKSTAT_DISPATCHER_URL` | — | **V3** Dispatcher URL |
| `STOCKSTAT_TRANSPORT` | `in_process` | **V3** transport type |
| `STOCKSTAT_SKIP_NETWORK` | `false` | Skip network steps in tests |
| `STOCKSTAT_TEST_SYMBOL` | `BTC/USDT` | Test symbol |
| `STOCKSTAT_TEST_START` | `2024-01-01` | Test start date |
| `STOCKSTAT_TEST_END` | `2024-12-31` | Test end date |

---

## Appendix: Test Execution

```bash
# Backend tests
cd backend && python -m pytest tests/ -v          # 15 tests

# Frontend tests (incl V3)
cd frontend && python -m pytest tests/ -v          # 814 tests + 6 skipped

# Deployment scenario tests
cd tests/deployments
python test_case_a_single_machine.py              # Single-machine
python test_case_e_dispatcher_worker.py           # V3 distributed
python test_case_f_multilevel.py                  # V3 multi-level

# PAXG research validation
cd working/PAXG-Weekend-Monday-Law-v5-redo/phase2_backtest
python run_redo.py                                 # 132 backtests
python compare_v3.py                               # V3 vs direct comparison
```

**Total**: 922 tests passing + 6 Redis skipped + 132 PAXG backtests byte-level identical.

---

*V3 usage guide follows the code implementation.*
