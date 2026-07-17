# StockStat — Programmable Financial Instrument Statistical Computing Platform

A user-programmable stock/cryptocurrency statistical computing platform with separated storage backend and computation frontend. v2.0 adopts a five-layer architecture (Universal Core / Financial Domain / Visualization / Interface / Application) with plugin-based extensibility, CLI, and offline mode.

## Quick Start

### Option A: Local development (SQLite, no Docker)

```bash
# 1. Install the backend
cd backend && pip install -e .

# 2. (Optional) Enable a proxy to access real data sources
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889

# 3. Start the API service (default sqlite:///stockstat.db, data persists to file)
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
# Or using v2.0 CLI:
stockstat serve --host 0.0.0.0 --port 8000

# 4. Install the frontend library (another terminal)
cd frontend && pip install -e .

# 5. (Optional) Install extras
pip install -e "frontend/[matplotlib]"          # Visualization
pip install -e "frontend/[dsl]"                 # DSL parser (lark)
pip install -e "frontend/[signal_processing]"   # Wavelets (PyWavelets)
pip install -e "frontend/[backtest_full]"       # Full backtest suite (matplotlib + optuna)
```

### Option B: Network remote deployment (storage service on a separate machine)

The backend can be deployed independently on any networked machine; other machines access via HTTP:

```bash
# === On the storage server (e.g. 192.168.1.100) ===
cd backend && pip install -e .

# Specify database storage location (optional; default is stockstat.db in CWD)
export DATABASE_URL="sqlite:////data/stockstat/stockstat.db"
#   SQLite absolute path: sqlite:/// + /abs/path = 4 slashes
#   PostgreSQL:           postgresql://user:pwd@host:5432/dbname

python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
# Data persists to the specified file; restarts automatically read previous data
```

**`DATABASE_URL` path rules**:

| `DATABASE_URL` value | Actual storage location |
|---|---|
| `sqlite:///stockstat.db` (default) | `stockstat.db` in the current working directory |
| `sqlite:////data/stockstat.db` | `/data/stockstat.db` (absolute path, 4 slashes) |
| `sqlite:///../data/stockstat.db` | `data/` in the parent directory (relative path) |
| `postgresql://user:pwd@host:5432/db` | Remote PostgreSQL database |

```python
# === On user machines ===
from stockstat import StockStatClient
client = StockStatClient(host="192.168.1.100", port=8000)

client.ingest("BTC/USDT", source="binance", start="2024-01-01")  # Download via API
data = client.ohlcv("BTC/USDT")                                   # Query via API
symbols = client.symbols()                                        # List downloaded symbols
```

### Option C: Offline mode (no backend needed)

v2.0's `V2Client` supports pure offline mode, using local Storage directly:

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage

client = V2Client(mode="offline", storage=MemoryStorage())
# ohlcv / compute / run_dsl / backtest / plot all run locally, no HTTP needed
```

### Option D: Docker (production)

```bash
docker compose up -d
# API available at http://localhost:8000
```

## Optional Extras

| Extra | Install command | Purpose |
|-------|-----------------|---------|
| `matplotlib` | `pip install stockstat[matplotlib]` | Protocol-based visualization (lazy import, zero core dependency) |
| `dsl` | `pip install stockstat[dsl]` | DSL parser (lark) |
| `signal_processing` | `pip install stockstat[signal_processing]` | PyWavelets (full CWT) |
| `backtest_full` | `pip install stockstat[backtest_full]` | Full backtest suite (matplotlib + optuna) |

## Proxy Configuration

The backend supports HTTP/SOCKS5 proxies for accessing real data sources. **Disabled by default**.

| Env var | Default | Description |
|---------|---------|-------------|
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable the proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | Proxy type: `http` or `socks5` |
| `STOCKSTAT_PROXY_URL` | auto by type | HTTP: `http://127.0.0.1:8889`, SOCKS5: `socks5://127.0.0.1:1089` |

## Usage

StockStat provides three usage entry points:

- **Python library**: `StockStatClient` — full-featured programmatic API (§1–§5 below)
- **CLI**: `stockstat` command — ingest, query, and manage plugins without writing Python
- **DSL**: SQL-like declarative query language — one-liner for common statistics

> All three share the same backend service and data. Each section below shows both Python and CLI usage side by side.

### 1. Ingest data

**Python:**

```python
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)

# Stock data (Yahoo Finance direct)
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
client.ingest("^GSPC", source="yfinance", start="2023-01-01", end="2024-12-31")

# Crypto data (Binance)
client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
client.ingest("ETH/USDT", source="binance", start="2024-01-01", end="2024-12-31")
client.ingest("PAXG/USDT", source="binance", start="2022-01-01", end="2024-12-31")

# Auto-detect source (stocks → yfinance, crypto → binance)
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")
```

**CLI:**

```bash
# Ingest stock data
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31

# Ingest crypto (source auto-detected)
stockstat ingest BTC/USDT --start 2024-01-01 --end 2024-12-31

# Specify timeframe
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

### 2. Query OHLCV data

**Python:**

```python
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")
#                    open    high     low   close     volume
# ts
# 2024-01-02  187.15  188.44  183.89  184.25  82488700
# 2024-01-03  184.22  185.88  183.43  184.40  58414500
```

**CLI:**

```bash
# Table format (default)
stockstat query BTC/USDT --limit 5

# Specify time range and format
stockstat query AAPL --start 2024-01-01 --end 2024-06-30 --format csv
stockstat query BTC/USDT --tf 1h --format json
```

### 3. Compute indicators

**Python:**

```python
sma = client.compute.ma(data.close, window=20)
rsi = client.compute.rsi(data.close, window=14)
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
beta = client.compute.beta(asset_returns, benchmark_returns, window=60)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
dd = client.compute.max_drawdown(data.close)
```

> Indicator computation is currently available via the Python library only. The `stockstat indicators` CLI command lists all registered indicators and their categories for quick reference:

```bash
# List all indicators
stockstat indicators

# Filter by category
stockstat indicators --category trend
stockstat indicators --category nonlinear
```

### 4. DSL queries

> The DSL is based on lark and requires `pip install stockstat[dsl]`. v2.0 auto-reflects all registered indicators from the PluginRegistry.

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')
```

### 5. Signal Processing & Nonlinear Dynamics

```python
import numpy as np

# Weekend 48h close-price path
path = data.close.values[-48:]

# Wavelet multiscale decomposition
coef, scales = client.compute.wavelet_decompose(path, scales=np.arange(1, 25))

# Spectral entropy (frequency-domain complexity)
h_spec = client.compute.spectral_entropy(np.diff(np.log(path)))

# Grey relational degree (path shape similarity)
gr = client.compute.grey_relation(path, reference_path)

# Hurst exponent (path persistence)
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))

# Transfer entropy (weekend → Monday information flow)
te = client.compute.transfer_entropy(weekend_returns, monday_returns)
```

## Available Indicators

### Built-in Technical Indicators (Python library + DSL)

| Category | Function | Description | DSL |
|----------|----------|-------------|-----|
| Trend | `ma(x, window)` | Simple moving average | ✅ |
| | `ema(x, window)` | Exponential moving average | ✅ |
| | `macd(x, fast, slow, signal)` | MACD (returns 3 series) | ✅ |
| Oscillator | `rsi(x, window)` | Relative Strength Index | ✅ |
| | `kdj(high, low, close, window)` | KDJ (returns 3 series) | ❌ Python only |
| Volatility | `std(x, window)` | Rolling standard deviation | ✅ |
| | `atr(high, low, close, window)` | Average True Range | ✅ |
| | `bollinger(x, window, k)` | Bollinger Bands (returns 3 series) | ✅ |
| Statistics | `corr(x, y)` | Pearson correlation | ✅ |
| | `beta(asset, benchmark, window)` | Rolling Beta | ❌ Python only |
| | `sharpe(returns, risk_free, annualize)` | Sharpe ratio | ❌ Python only |
| | `max_drawdown(close)` | Maximum drawdown | ❌ Python only |
| | `var(returns, confidence)` | Historical VaR | ❌ Python only |
| Transform | `returns(x)` | Percentage returns | ✅ |
| | `log_returns(x)` | Log returns | ✅ |

### Signal Processing & Nonlinear Dynamics (Python library only)

| Category | Function | Description |
|----------|----------|-------------|
| Signal Processing | `wavelet_decompose(signal, scales, wavelet)` | Continuous Wavelet Transform (CWT) |
| | `spectral_entropy(signal, fs, nperseg)` | Spectral entropy (frequency-domain complexity) |
| | `grey_relation(x0, xi, rho)` | Grey relational degree (path shape similarity) |
| | `gm11_predict(sequence)` | GM(1,1) grey prediction |
| Nonlinear Dynamics | `transfer_entropy(x, y, k, n_bins)` | Transfer entropy (directed information flow) |
| | `hurst_dfa(signal)` | Hurst exponent (DFA method) |
| | `sample_entropy(signal, m, r)` | Sample entropy |
| | `permutation_entropy(signal, m, tau)` | Permutation entropy |
| PlotSpec factories | `wavelet_scalogram(coef, scales, title, cmap)` | CWT time-frequency heatmap (returns PlotSpec) |
| | `dfa_fit(signal, title)` | DFA log-log fit plot (returns PlotSpec) |
| | `psd_plot(signal, fs, nperseg, title)` | Power spectral density plot (returns PlotSpec) |

> The **Signal Processing & Nonlinear Dynamics** module requires the optional dependency `pip install stockstat[signal_processing]` (installs PyWavelets). When PyWavelets is not installed, CWT gracefully degrades to a built-in FFT-based Morlet implementation.

## v2.0 Plugin System

All extension points in v2.0 (data sources, indicators, cost models, fill models, execution models, renderers) are registered to a unified `PluginRegistry`, queryable via CLI or code.

**CLI:**

```bash
# List all registered plugins
stockstat plugins

# Filter by namespace
stockstat plugins --namespace indicators
stockstat plugins --namespace sources
stockstat plugins --namespace cost_models
```

Output example:
```
Namespace            Name                      Category
--------------------------------------------------------------------
sources              yfinance                  sources
sources              binance                   sources
sources              coinbase                  sources
sources              synthetic                 sources
indicators           ma                        trend
indicators           rsi                       oscillator
indicators           hurst_dfa                 nonlinear
...
cost_models          percent                   cost
cost_models          binance                   cost
fill_models          next_open                 fill
execution_models     next_bar                  execution
renderers            matplotlib                renderers

Total: 45 plugin(s)
```

**Python:**

```python
from stockstat._core.plugin import PluginRegistry
from stockstat._domain.indicators import register_default_indicators, list_indicators

reg = PluginRegistry()
register_default_indicators(reg)
print(list_indicators(reg, category="nonlinear"))
```

## Management Interfaces

StockStat provides two management interfaces for administering data on the Storage Server without writing Python.

### TUI Terminal Interface

```bash
# Connect to local server
stockstat tui

# Connect to remote server
stockstat tui --host 192.168.1.100 --port 8000
```

Launches an interactive menu:

```
┌─────────────────────────────────────────┐
│     StockStat Storage Manager           │
│  Server: localhost:8000  Status: ONLINE │
└─────────────────────────────────────────┘

Menu:
  1. Browse symbols      — List all registered symbols
  2. Query OHLCV data    — Query last N rows
  3. Ingest new data     — Interactive ingestion
  4. Data statistics     — Data overview
  5. List data sources   — List available sources
  6. View proxy config   — View proxy settings
  q. Quit
```

> Install `pip install rich` for colored tables. Falls back to plain text when not installed.

### Web Admin Interface

The Storage Server has a built-in web admin interface. Access via browser at `http://storage-server:8000/admin/`:

| Function | Description |
|----------|-------------|
| Overview dashboard | Symbol count, row count, per-source distribution, health status |
| Symbol browse | List all symbols + row count + date range + delete |
| Data ingest | Trigger ingestion from the web (symbol/source/date) |
| Config viewer | View DB URL / proxy / cache config (password masked) |
| Health monitor | DB connection / cache status / proxy status |

```
# After starting the Storage Server, visit in browser:
http://192.168.1.100:8000/admin/
```

## Backtesting

The backtest subsystem (`stockstat.backtest`) supports custom strategies, multi-instrument trading groups, multi-timeframe bars, and reuses all compute-library indicators inside strategies.

### Quick example: MA crossover

```python
from stockstat import StockStatClient
from stockstat.backtest import BacktestEngine, strategy, Order

client = StockStatClient(host="localhost", port=8000)
data = {"BTC/USDT": {"1d": client.ohlcv("BTC/USDT", start="2024-01-01")}}

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21:
        return
    ma5  = d.close.rolling(5).mean().iloc[-1]
    ma20 = d.close.rolling(20).mean().iloc[-1]
    pos  = ctx.portfolio.get_position("BTC/USDT")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

# Option A: via client convenience entry (auto-injects ComputeEngine)
res = client.backtest(data, ma_cross, initial_cash=10000)

# Option B: build the engine directly
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

print(res.summary())
spec = res.plot_equity()  # returns a PlotSpec renderable by matplotlib
```

### Backtest capabilities

| Capability | Description |
|------------|-------------|
| Custom strategy | `Strategy` base class / `@strategy` function decorator / `IntrabarMixin` |
| Multi-instrument group | `{symbol: {tf: df}}` Universe |
| Multi-timeframe | finest tf drives master index; higher tfs ffill-aligned |
| Order types | market / limit / stop / trailing stop / OCO / mutual OCO |
| Cost models | percent / fixed / tiered / stamp duty / zero / Maker/Taker / Binance spot+futures+BNB |
| Short selling | `allow_short=True` |
| Performance | Sharpe / Sortino / Calmar / drawdown / win rate / profit factor |
| Visualization | 9 chart types + dashboard; zero matplotlib hard-dependency |
| Optimization | grid search / optuna (extras) / walk-forward / Monte Carlo |
| Lookahead protection | default NextOpenFill + lookahead_audit |
| Pluggable execution | `NextBarExecution` (default) / `IntrabarExecution` (intrabar sub-bar matching) |
| Same-bar entry+exit | `IntrabarExecution`: full lifecycle within parent bar |
| Order priority | `Order(priority=...)`: SL before TP |
| Batch backtest | `StrategyBatchRunner`: multi-strategy/multi-fee parallel |
| Exit reason tags | `Order(exit_reason=...)` + `result.exit_reason_stats()` |
| DCA benchmark | `dca_equity()` |
| Subperiod/regime analysis | `BacktestAnalyzer.subperiod_metrics()` / `regime_conditional_metrics()` |
| Fee sweep | `fee_sweep()` / `maker_taker_sweep()` |

See [DESIGN.md §11](DESIGN.md#11-backtest-subsystem-design) for the backtest design and [docs/backtest/](docs/backtest/) for phase-by-phase docs.

## Visualization with Matplotlib

The core library has **zero hard-dependency** on matplotlib. Install it optionally:

```bash
pip install stockstat[matplotlib]
```

### Protocol-based plotting

```python
spec = client.plot.spec(
    title="BTC Close + MA20",
    x_label="Date", y_label="Price",
    series=[
        {"name": "close", "data": data.close, "kind": "line"},
        {"name": "ma20", "data": data.close.rolling(20).mean(), "kind": "line", "color": "red"},
    ],
)
renderer = client.plot.get_renderer()  # auto-detect matplotlib
renderer.render(spec)
renderer.savefig("btc.png")
```

### Classic statistical charts (generated from real data)

#### Close + MA + Bollinger Bands
![BTC Bollinger Bands](docs/images/btc_bollinger.png)

#### RSI with overbought/oversold zones
![BTC RSI](docs/images/btc_rsi.png)

#### MACD histogram + signal line
![ETH MACD](docs/images/eth_macd.png)

#### Drawdown chart
![BTC Drawdown](docs/images/btc_drawdown.png)

#### Beta scatter (AAPL vs S&P 500)
![AAPL Beta](docs/images/aapl_beta_scatter.png)

#### BTC vs ETH rolling correlation
![BTC ETH Correlation](docs/images/btc_eth_corr.png)

#### Normalized price comparison
![Price Comparison](docs/images/price_comparison.png)

### PAXG weekend return vs Monday gain/loss (independent)

PAXG (gold-pegged token) weekend return (Friday close → Sunday close) vs Monday's **max gain** `(High-Open)/Open` and **max loss** `(Low-Open)/Open`, recorded **independently**. Real data 2022-2024.

#### Scatter plot — gain & loss on same chart
![PAXG Weekend Scatter](docs/images/paxg_weekend_scatter.png)

**Result**: r(gain)=0.23 (p=0.004), r(loss)=-0.20 (p=0.012). Both significant but weak — the weekend return has modest independent predictive power for both Monday's upside and downside.

#### Gain/loss distribution by weekend direction
![PAXG Directional](docs/images/paxg_directional.png)

#### Weekend return distribution
![PAXG Weekend Histogram](docs/images/paxg_weekend_hist.png)

### Backtest visualization

9 chart types, auto-activated when matplotlib is installed. Charts below generated with real market data (Binance BTC/USDT 2023-2024).

#### Dashboard (2×2: equity + drawdown + returns distribution + monthly heatmap)
![BTC Backtest Dashboard](docs/images/backtest_btc_dashboard.png)

#### Equity curve + benchmark
![BTC Equity](docs/images/backtest_btc_equity.png)

#### Drawdown (filled area)
![BTC Drawdown](docs/images/backtest_btc_drawdown.png)

#### Trade annotations (B/S arrows)
![BTC Trades](docs/images/backtest_btc_trades.png)

#### Monthly returns heatmap
![BTC Monthly Heatmap](docs/images/backtest_btc_monthly_heatmap.png)

#### Parameter grid heatmap (AAPL MA short × long → Sharpe)
![Parameter Heatmap](docs/images/backtest_param_heatmap.png)

#### Pair trading dashboard (BTC/ETH)
![Pair Trading Dashboard](docs/images/backtest_pair_dashboard.png)

```python
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

# One-liner render (auto-detects matplotlib)
res.render("equity_curve", path="equity.png")
res.render("dashboard", path="dashboard.png")

# Batch-save all charts
res.render_all("./charts")

# Parameter grid heatmap
from stockstat.backtest.optimizer import grid_search
results = grid_search(make_engine, {"short": [3,5,8], "long": [10,20,30]}, metric="sharpe")
res.render("parameter_heatmap", grid_results=results, path="param.png")
```

Without matplotlib, it gracefully degrades to `NullBacktestChartRenderer` (warns, never crashes).

## Data Sources

| Source | Type | Network | Total Symbols | Description |
|--------|------|---------|---------------|-------------|
| `yfinance` | stock | Yes | On-demand | Yahoo Finance direct API |
| `binance` | crypto | Yes | 4,498 (1,479 USDT pairs) | Binance via ccxt |
| `coinbase` | crypto | Yes | 1,183 (528 USD pairs) | Coinbase via ccxt |
| `synthetic` | mixed | No | — | Synthetic data (fixed seed) for offline testing |

### Data Size Estimates

| Scope | Timeframe | Rows (1 year) | Storage |
|-------|-----------|---------------|---------|
| 1 symbol | daily | ~250 | ~2 KB |
| 1 symbol | 1-minute | ~525,000 | ~15 MB |
| Binance USDT pairs (1,479) | daily | ~370,000 | ~3 MB |
| Binance USDT pairs (1,479) | 1-minute | ~776M | ~22 GB |

> SQLite is suitable for small single-machine workloads; for GB-scale, switch to TimescaleDB + Hypertable compression.

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check (includes proxy status) |
| `/api/v1/proxy` | GET | Get proxy configuration |
| `/api/v1/sources` | GET | List data sources (includes proxy status) |
| `/api/v1/ingest` | POST | Ingest data for a symbol |
| `/api/v1/ohlcv` | GET | Query OHLCV data (json/csv) |
| `/api/v1/symbols` | GET | List registered symbols |
| `/api/v1/symbols/{symbol}` | GET | Symbol detail |

## Running Tests

```bash
# Backend tests
cd backend && python -m pytest tests/test_backend.py -v

# v2.0 core + domain + viz + API tests
cd frontend && python -m pytest tests/test_v2_core.py tests/test_v2_domain.py tests/test_v2_viz.py tests/test_v2_api.py -v

# v1.7 frontend unit tests (indicators, DSL, visualization)
cd frontend && python -m pytest tests/test_frontend.py tests/test_nonlinear.py -v

# Full backtest suite
cd frontend && python -m pytest tests/test_backtest_iface.py tests/test_backtest_mvp.py \
    tests/test_backtest_portfolio.py tests/test_backtest_multitf.py \
    tests/test_backtest_cost.py tests/test_backtest_metrics.py \
    tests/test_backtest_optimize.py tests/test_backtest_strategies.py \
    tests/test_backtest_viz_iface.py tests/test_backtest_viz_mpl.py \
    tests/test_backtest_viz_advanced.py tests/test_backtest_viz_dashboard.py \
    tests/test_backtest_viz_online.py \
    tests/test_backtest_p0.py tests/test_backtest_p1.py tests/test_backtest_p2.py \
    tests/test_backtest_intrabar.py -v

# Integration tests (real data: classic stats + PAXG weekend correlation)
cd frontend && python -m pytest tests/test_integration.py -v -s

# Matplotlib chart tests
cd frontend && python -m pytest tests/test_matplotlib_charts.py -v
```

**489 tests total, all passing.**

## Documentation

- [Usage Guide](docs/USAGE.md) — detailed examples with expected results
- [Design Report](DESIGN.md) — full v2.0 five-layer architecture design
- [Backtest Phase Docs](docs/backtest/) — BT-0 through BT-14 + BT-V0 through V3 + online validation report
- [Reports](reports/) — v2.0 phase implementation reports + PAXG compatibility report

## Configuration

### Backend environment variables

| Env var | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database connection string (switchable to `postgresql://...`) |
| `REDIS_URL` | (empty) | Redis connection (optional) |
| `HOST` | `0.0.0.0` | Backend listen address |
| `PORT` | `8000` | Backend listen port |
| `STOCKSTAT_DEFAULT_SOURCE` | `yfinance` | Default data source |
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` or `socks5` |
| `STOCKSTAT_PROXY_URL` | auto | Proxy URL |

### Frontend environment variables

| Env var | Default | Description |
|---------|---------|-------------|
| `STOCKSTAT_HOST` | `localhost` | Frontend default host |
| `STOCKSTAT_PORT` | `8000` | Frontend default port |
| `STOCKSTAT_API_KEY` | (empty) | Optional API key (Bearer auth) |
| `STOCKSTAT_TIMEOUT` | `30` | HTTP timeout in seconds |
| `STOCKSTAT_USE_HTTPS` | `false` | Whether to use HTTPS |

---

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file for details.

Copyright (C) 2026 RESBI

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

---

## Acknowledgements & Disclaimer

This project — including all source code, documentation, tests, and charts — was entirely designed, implemented, and documented by **GLM-5.2**, an AI assistant. All code was generated through iterative conversation with the user, verified by automated test suites, and validated against real market data (Yahoo Finance + Binance).

This software is provided for **educational and research purposes only**. It is **not** financial, investment, or trading advice.

- The authors and contributors of this project are **not** financial advisors and do not accept any liability for financial losses or damages arising from the use of this software.
- All statistical analyses, indicators, and correlations (including the PAXG weekend effect) are based on historical data and do **not** guarantee future results.
- Users are solely responsible for their own investment decisions and should consult a qualified financial professional before making any investment.
- The software may contain bugs or inaccuracies. Use at your own risk.
- Market data is obtained from third-party sources (Yahoo Finance, Binance) and their accuracy or availability is not guaranteed.

**THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.**
