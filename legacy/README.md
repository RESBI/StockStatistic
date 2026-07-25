# StockStat — Programmable Financial Instrument Statistical Computing Platform

A user-programmable stock / cryptocurrency statistical computing platform with **compute-storage separation + V3 distributed compute offload** architecture, supporting local / remote / offline / distributed deployment modes.

- **Unified data access**: yfinance direct (85 curated symbols + manual input for any ticker) / ccxt (Binance 4,498, Coinbase 1,183 pairs) / synthetic data
- **Programmable computation**: Python library + SQL-like DSL (v2.0 auto-reflects 23 indicators from `PluginRegistry`)
- **Backtest subsystem**: multi-instrument / multi-timeframe / pluggable execution model / 9 visualization charts / intrabar matching
- **V3 distributed compute**: `ComputeBackend` protocol transparent swap; Dispatcher + Worker cross-process; multi-level Dispatcher topology; preemption / elasticity / Autoscaler
- **Three-layer protocol stack**: Codec (JSON/Arrow/Cloudpickle/Msgpack) + Message (Envelope) + Transport (HTTP/InProcess/SHM/Redis)
- **Zero core modification**: `BacktestEngine` / `ComputeEngine` unchanged; Worker reuses directly; 599 existing tests zero regression
- **Visual management**: Web SPA + TUI terminal interface + V3 Task monitoring API

---

## V3 New Capabilities (P0-P7 All Complete)

| Phase | Content | Tests |
|-------|---------|-------|
| P0 | Protocol skeleton (Envelope / TaskSpec / Codec / Errors) | 50 |
| P1 | LocalComputeBackend + InProcessTransport | 58 |
| P2 | Dispatcher + Worker cross-process (HTTP + memory queue) | 83 |
| P3 | HttpTransport + RemoteComputeBackend + AutoComputeBackend | 22 |
| P4 | SharedMemoryTransport + Stream + dispatch.partial + data_dispatch | 34 |
| P5 | RedisTaskQueue + RedisTransport + MessagePack | 17 |
| P6 | Preemption / Drain / Discover / Autoscaler / RetryPolicy | 36 |
| P7 | Multi-level Dispatcher + Admin monitoring + task history | 23 |

**Total**: 922 tests passing + 6 Redis skipped

See [DESIGN_V3_CN.md](DESIGN_V3_CN.md) (full design), [DESIGN_ARCHITECTURE.md](DESIGN_ARCHITECTURE.md) (architecture), [DESIGN_PROTOCOL.md](DESIGN_PROTOCOL.md) (protocol).

---

## Quick Start

### 1. Installation

```bash
# Backend (Storage + Dispatcher)
cd backend && pip install -e .

# Frontend (compute library + V3 protocol layer)
cd frontend && pip install -e .

# V3 distributed compute (optional)
pip install -e "frontend/[compute]"          # cloudpickle + psutil
pip install -e "frontend/[distributed]"      # + redis + msgpack
pip install -e worker/                       # stockstat-compute Worker package

# Other optional extras
pip install -e "frontend/[matplotlib]"       # visualization
pip install -e "frontend/[dsl]"              # DSL parser (lark)
pip install -e "frontend/[backtest_full]"    # full backtest suite
pip install rich                              # TUI colored tables
```

### 2. Start Backend

```bash
# Basic startup (Storage only)
stockstat serve --host 0.0.0.0 --port 8000

# V3 enable Dispatcher (P2+)
STOCKSTAT_DISPATCHER_ENABLED=true stockstat serve --host 0.0.0.0 --port 8000
```

Browse to `http://localhost:8000/admin/` for the management UI.

### 3. Start Worker (V3 Distributed)

```bash
# On another machine (or another process on same machine)
stockstat-compute worker \
    --dispatcher-url http://storage:8000 \
    --concurrency 8 \
    --alias "gpu-box-alpha" \
    --label rack=A-12
```

### 4. Use Client

```python
from stockstat import StockStatClient

# v1.7 behavior (default LocalComputeBackend)
client = StockStatClient(host="localhost", port=8000)
client.ingest("BTC/USDT", source="binance", start="2024-01-01")
data = client.ohlcv("BTC/USDT")
result = client.backtest(data, strategy, initial_cash=10000)

# V3 remote compute (transparent sync)
from stockstat._core.compute import RemoteComputeBackend
client = StockStatClient(
    host="localhost", port=8000,
    compute_backend=RemoteComputeBackend("http://localhost:8000"),
)
result = client.backtest(data, strategy)  # internally submit + wait

# V3 explicit async
task = client.compute.remote(
    "grid_search",
    symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01",
    strategy_ref=strategy_ref,
    param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
    metric="sharpe",
)
print(task.id, task.status)
result = task.wait(timeout=3600)

# V3 auto routing
from stockstat._core.compute import AutoComputeBackend, LocalComputeBackend
client = StockStatClient(compute_backend=AutoComputeBackend(
    local=LocalComputeBackend(),
    remote=RemoteComputeBackend("http://dispatch:9000"),
))
# Heavy tasks go remote, light tasks go local
```

### 5. Offline Mode (No Backend Required)

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage, SQLStorage

# In-memory offline
client = V2Client(mode="offline", storage=MemoryStorage())
client.ingest("BTC/USDT", source="binance", start="2024-01-01")

# Read existing SQLite
client = V2Client(mode="offline",
                  storage=SQLStorage(database_url="sqlite:///stockstat.db"))
```

### 6. Docker Deployment

```bash
docker compose up -d
# Starts db + redis + api + dispatcher + 4 workers
```

---

## Deployment Scenarios

| Scenario | Client | Dispatcher | Storage | Worker | Config |
|----------|--------|-----------|---------|--------|--------|
| A Single-machine full-stack | same process | — | — | — | default |
| B Storage-compute separation | remote HTTP | — | independent | Client local | v2.1 |
| C Offline | local | — | local | Client local | v2.1 |
| D Dispatcher+Worker | remote HTTP | same host as Storage | independent | remote | `--enable-dispatcher` |
| E Independent Dispatcher | remote HTTP | independent | independent | multi-node | `stockstat-dispatcher` |
| F Multi-level Dispatcher | remote HTTP | parent + sub | independent | multi-level | P7 |

Each scenario has a deployment test: [tests/deployments/](tests/deployments/)

```bash
# Run deployment tests
tests/deployments/run_case_a_single_machine.bat   # Windows
./tests/deployments/run_case_a_single_machine.sh  # Linux/macOS

# V3 distributed
tests/deployments/run_case_e_dispatcher_worker.bat
tests/deployments/run_case_f_multilevel.bat
```

---

## Usage

StockStat provides four entry points:

- **Python library**: `StockStatClient` / `V2Client` — full programming interface
- **CLI**: `stockstat` — ingest, query, manage plugins
- **DSL queries**: SQL-like declarative query language
- **V3 remote compute**: `client.compute.remote()` async submit + `TaskRef`

### Ingest Data

```python
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
client.ingest("BTC/USDT", source="binance", start="2024-01-01", timeframe="1h")
client.ingest("MSFT", start="2024-01-01")  # auto-detect source
```

### Compute Indicators

23 technical indicators + 8 nonlinear dynamics functions:

```python
sma = client.compute.ma(data.close, window=20)
rsi = client.compute.rsi(data.close, window=14)
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))  # DFA Hurst exponent
```

### Signal Processing and Nonlinear Dynamics

8 advanced analysis functions covering signal processing (Continuous Wavelet Transform CWT / Spectral Entropy / Grey Relational Degree / GM(1,1) Grey Prediction) and nonlinear dynamics (Transfer Entropy / Hurst Exponent DFA / Sample Entropy / Permutation Entropy). When PyWavelets is not installed, CWT gracefully degrades to an FFT-based self-implemented Morlet wavelet. Also provides 3 PlotSpec factory functions (CWT scalogram / DFA fit plot / PSD plot).

```python
import numpy as np
path = data.close.values[-48:]

# Signal processing
coef, scales = client.compute.wavelet_decompose(path, scales=np.arange(1, 25))  # CWT
h_spec = client.compute.spectral_entropy(np.diff(np.log(path)))                  # Spectral entropy
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)                       # Grey relational degree
forecast = client.compute.gm11_predict(sequence)                                  # GM(1,1) grey prediction

# Nonlinear dynamics
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))    # Hurst exponent (≈0.5 random | >0.5 persistent | <0.5 anti-persistent)
te = client.compute.transfer_entropy(btc_rets, eth_rets)   # Transfer entropy (directed info flow)
sampen = client.compute.sample_entropy(signal, m=2)         # Sample entropy
permen = client.compute.permutation_entropy(signal, m=3)    # Permutation entropy

# Visualization
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
renderer = client.plot.get_renderer()
renderer.render(spec)
```

<details open>
<summary>🔬 PAXG Weekend Returns vs Monday Returns (Real Data 2022-2024)</summary>

PAXG (gold-pegged token) weekend returns (Friday close → Sunday close) vs Monday's **max gain** and **max loss**, **recorded independently**.

#### Scatter Plot — Gains and Losses on Same Chart
![PAXG Weekend Scatter](docs/images/paxg_weekend_scatter.png)

**Result**: r(gain)=0.23 (p=0.004), r(loss)=-0.20 (p=0.012). Both significant but weak — weekend returns have moderate independent predictive power for Monday gains and losses.

#### Distribution by Weekend Direction
![PAXG Directional](docs/images/paxg_directional.png)

#### Weekend Returns Distribution
![PAXG Weekend Histogram](docs/images/paxg_weekend_hist.png)

</details>

### DSL Queries

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')
```

### Backtest

```python
from stockstat.backtest import BacktestEngine, strategy, Order

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21: return
    ma5, ma20 = d.close.rolling(5).mean().iloc[-1], d.close.rolling(20).mean().iloc[-1]
    pos = ctx.portfolio.get_position("BTC/USDT")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

res = client.backtest({"BTC/USDT": {"1d": data}}, ma_cross, initial_cash=10000)
print(res.summary())
res.render("dashboard", path="dashboard.png")
```

Backtest visualization provides 9 chart types: equity curve, drawdown, trade markers, returns distribution, monthly heatmap, annual returns, parameter grid heatmap, underwater curve, comprehensive dashboard (2×2). When matplotlib is not installed, it gracefully degrades to `NullBacktestChartRenderer` (warns but doesn't crash).

<details open>
<summary>📊 Classic Statistical Charts (Real Data)</summary>

#### Close Price + MA + Bollinger Bands
![BTC Bollinger](docs/images/btc_bollinger.png)

#### RSI Overbought/Oversold Zones
![BTC RSI](docs/images/btc_rsi.png)

#### MACD Histogram + Signal Line
![ETH MACD](docs/images/eth_macd.png)

#### Drawdown
![BTC Drawdown](docs/images/btc_drawdown.png)

#### Beta Scatter (AAPL vs S&P 500)
![AAPL Beta](docs/images/aapl_beta_scatter.png)

#### BTC vs ETH Rolling Correlation
![BTC ETH Correlation](docs/images/btc_eth_corr.png)

#### Normalized Price Comparison
![Price Comparison](docs/images/price_comparison.png)

</details>

<details open>
<summary>📈 Backtest Visualization Charts (Real Data)</summary>

#### Comprehensive Dashboard (2×2: equity + drawdown + returns dist + monthly heatmap)
![BTC Backtest Dashboard](docs/images/backtest_btc_dashboard.png)

#### Equity Curve + Benchmark
![BTC Equity](docs/images/backtest_btc_equity.png)

#### Drawdown (filled area)
![BTC Drawdown](docs/images/backtest_btc_drawdown.png)

#### Trade Markers (B/S arrows)
![BTC Trades](docs/images/backtest_btc_trades.png)

#### Monthly Returns Heatmap
![BTC Monthly Heatmap](docs/images/backtest_btc_monthly_heatmap.png)

#### Parameter Grid Heatmap (AAPL MA short × long → Sharpe)
![Param Heatmap](docs/images/backtest_param_heatmap.png)

#### Pair Trading Dashboard (BTC/ETH)
![Pair Trading Dashboard](docs/images/backtest_pair_dashboard.png)

</details>

### V3 Distributed Compute

```python
# Explicit async submit
task = client.compute.remote(
    "grid_search",
    symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01",
    strategy_ref=strategy_ref,
    param_grid={"short": list(range(2, 22)), "long": list(range(20, 70))},
    metric="sharpe",
    dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=4),
)
print(task.id, task.status)  # UUID + "pending" / "running" / "completed"

# Poll / wait
result = task.wait(timeout=3600)
print(f"Best params: {result[0]['params']}, sharpe: {result[0]['sharpe']}")

# Stream results (grid_search progress)
for partial in task.stream_results():
    print(f"Progress: {partial.get('progress', 0):.0%}")

# Cluster topology
info = client.compute.cluster_info()
for w in info["workers"]:
    print(f"  {w['alias']:20s}  {w['status']:8s}  "
          f"CPU {w['hardware']['cpu']['cores_logical']} cores  "
          f"load {w['load'].get('cpu_percent', 0):.1f}%")
```

### V3 Cluster Management

```bash
# View cluster
stockstat cluster info
stockstat cluster workers
stockstat cluster stats

# Autoscaler metrics
curl http://dispatch:8000/dispatch/autoscaler
# {"queue_depth": 15, "scale_up_recommended": true, ...}

# Task history
curl http://dispatch:8000/dispatch/tasks/history?limit=10
curl http://dispatch:8000/dispatch/tasks/stats
```

---

## Management Interface

### TUI Terminal

```bash
stockstat tui                    # connect to local server
stockstat tui --host 192.168.1.100
```

### Web Admin

Browse to `http://storage-server:8000/admin/`:

| Page | Features |
|------|----------|
| Overview dashboard | Symbol count, row count, disk, data coverage Gantt, recent ingest |
| Source browser | Pagination + search + batch download + manual input for any symbol |
| Local symbols | K-line chart (lazy-load on zoom) + range completion + CSV export |
| Config | Database / proxy / cache / disk |
| Logs | Ingest history (paginated + filtered) |

### V3 Dispatcher Monitoring (P7)

When `STOCKSTAT_DISPATCHER_ENABLED=true` + `STOCKSTAT_ADMIN_ENABLED=true`:

| Endpoint | Description |
|----------|-------------|
| `GET /admin/api/dispatcher/cluster` | Full cluster topology (incl. sub_dispatchers) |
| `GET /admin/api/dispatcher/tasks` | Task history |
| `GET /admin/api/dispatcher/stats` | Task stats (by_state / by_type / avg_duration) |
| `GET /admin/api/dispatcher/autoscaler` | Autoscaler metrics + scale up/down recommendations |

---

## Data Sources

| Source | Type | Symbol count | Time granularities | Range probing |
|--------|------|--------------|---------------------|---------------|
| `yfinance` | Stock/ETF/Index/Commodity/FX | 85 curated + manual | 12 | ✅ Yahoo API probe |
| `binance` | Crypto | 4,498 (1,479 USDT pairs) | 16 | ✅ First/last K-line probe |
| `coinbase` | Crypto | 1,183 (528 USD pairs) | 7 | ✅ First/last K-line probe |
| `synthetic` | Mixed | 5 examples | 9 | ✅ Fixed range |

---

## Optional Extras

| Extras | Use case |
|--------|----------|
| `matplotlib` | Protocol-based visualization (lazy import, core zero-dep) |
| `dsl` | DSL parser (lark) |
| `signal_processing` | PyWavelets (full CWT implementation) |
| `backtest_full` | Full backtest suite (matplotlib + optuna) |
| `rich` | TUI colored tables |
| `compute` | V3 local backend (cloudpickle + psutil) |
| `distributed` | V3 distributed (compute + redis + msgpack) |

---

## Run Tests

```bash
# Backend tests
cd backend && python -m pytest tests/ -v          # 15 tests

# Frontend tests (incl V3)
cd frontend && python -m pytest tests/ -v          # 814 tests + 6 skipped

# Deployment scenario tests (6 Cases)
cd tests/deployments
python test_case_a_single_machine.py              # Single-machine
python test_case_e_dispatcher_worker.py           # V3 distributed
python test_case_f_multilevel.py                  # V3 multi-level

# PAXG research validation
cd working/PAXG-Weekend-Monday-Law-v5-redo/phase2_backtest
python run_redo.py                                 # 132 backtests
python compare_v3.py                               # V3 vs direct comparison
```

**Total 922 tests passing + 6 Redis skipped + 132 PAXG backtests byte-level identical.**

### Connection and Performance Tests

```bash
# Connection smoke test
python tests/test_connection.py --host localhost --port 8000

# Communication performance test
python tests/test_perf.py --host localhost --port 8000 --rounds 10
```

---

## Documentation

- [Usage docs](docs/USAGE.md) — detailed examples and expected results
- [V3 design report](DESIGN_V3_CN.md) — complete design (3057 lines)
- [V3 architecture design](DESIGN_ARCHITECTURE.md) — four-role + three-package + five-layer + ComputeBackend
- [V3 protocol design](DESIGN_PROTOCOL.md) — Envelope + TaskSpec + Codec + Transport
- [V3 phase docs](docs/v3/) — P0-P7 implementation details
- [V3 complete summary](docs/v3/SUMMARY_FULL_CN.md) — P0-P7 full summary
- [v2.1 design report](DESIGN_CN.md) — original architecture (preserved)
- [Backtest phase docs](docs/backtest/) — BT-0 ~ BT-14 + BT-V0 ~ V3
- [Deployment tests](tests/deployments/README.md) — Case A-F deployment scenario tests

---

## Configuration

### Backend Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database connection string |
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_ADMIN_ENABLED` | `true` | Enable web admin |
| `STOCKSTAT_DISPATCHER_ENABLED` | `false` | **V3** enable Dispatcher plugin |
| `STOCKSTAT_DISPATCHER_QUEUE` | `memory` | **V3** queue backend (memory/redis) |
| `STOCKSTAT_DISPATCHER_CACHE_MB` | `512` | **V3** DataCache max size |
| `REDIS_URL` | — | **V3** Redis connection (when queue=redis) |

### Frontend Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCKSTAT_HOST` | `localhost` | Default host |
| `STOCKSTAT_PORT` | `8000` | Default port |
| `STOCKSTAT_DISPATCHER_URL` | — | **V3** Dispatcher URL for Worker/Client |
| `STOCKSTAT_TRANSPORT` | `in_process` | **V3** transport type (in_process/http) |

---

## Startup Scripts

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

## License

This project is licensed under **GNU General Public License v3.0** — see [LICENSE](LICENSE).

Copyright (C) 2026 RESBI

## Disclaimer

This project — including all source code, documentation, test cases, and charts — was entirely designed, implemented, and written by **GLM-5.2** (AI assistant).

This software is for **learning and research purposes only** and does **not constitute** any financial, investment, or trading advice. Users are fully responsible for their own investment decisions and should consult a qualified financial professional before making any investment.
