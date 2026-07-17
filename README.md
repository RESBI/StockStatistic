# StockStat — Programmable Financial Instrument Statistical Computing Platform

A user-programmable stock/cryptocurrency statistical computing platform with separated storage backend and computation frontend.

## Quick Start

### Option A: Local development (SQLite, no Docker)

```bash
# 1. Install the backend
cd backend
pip install -e .

# 2. (Optional) Enable a proxy to access real data sources
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889

# 3. Start the API service (default sqlite:///stockstat.db)
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000

# 4. Install the frontend library (another terminal)
cd frontend
pip install -e .

# 5. (Optional) Install extras on demand
pip install -e "frontend/[matplotlib]"          # visualization
pip install -e "frontend/[dsl]"                 # DSL parser (lark)
pip install -e "frontend/[signal_processing]"   # wavelets (PyWavelets)
pip install -e "frontend/[backtest_full]"       # full backtest suite (matplotlib + optuna)
```

### Option B: Docker (production)

```bash
docker compose up -d
# API available at http://localhost:8000
```

> **Note**: Docker deployment starts TimescaleDB + Redis containers, but the current `api` service code still uses `InMemoryCache` and does not automatically connect to Redis; the `scheduler` service is a placeholder stub. See [DESIGN.md §9](DESIGN.md#9-deployment).

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

```bash
# HTTP proxy (default address)
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http

# SOCKS5 proxy (default address)
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=socks5

# Custom proxy
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_URL=http://192.168.1.100:8080
```

## Usage

### 1. Ingest data

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

### 2. Query OHLCV data

```python
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")
#                    open    high     low   close     volume
# ts
# 2024-01-02  187.15  188.44  183.89  184.25  82488700
# 2024-01-03  184.22  185.88  183.43  184.40  58414500
```

### 3. Compute indicators

```python
sma = client.compute.ma(data.close, window=20)
rsi = client.compute.rsi(data.close, window=14)
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
beta = client.compute.beta(asset_returns, benchmark_returns, window=60)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
dd = client.compute.max_drawdown(data.close)
```

### 4. DSL queries

> The DSL is based on lark and requires `pip install stockstat[dsl]`. It currently supports only `SELECT ... FROM ... WHERE ... LIMIT`; it does not support `GROUP BY` / `ORDER BY` / `CASE WHEN`.

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

8 analytical functions + 3 PlotSpec factory functions, in `stockstat.indicators.nonlinear`:

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

> The **Signal Processing & Nonlinear Dynamics** module requires the optional dependency `pip install stockstat[signal_processing]` (installs PyWavelets). When PyWavelets is not installed, CWT gracefully degrades to a built-in FFT-based Morlet implementation. PlotSpec factory functions return `PlotSpec` objects renderable via `client.plot.render(spec)` — PlotSpec has been extended to support heatmaps, log scales, and subplots.

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

# Option A: via the client convenience entry (auto-injects ComputeEngine)
res = client.backtest(data, ma_cross, initial_cash=10000)

# Option B: build the engine directly
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000,
                     benchmark="BTC/USDT").run()

print(res.summary())
spec = res.plot_equity()  # returns a PlotSpec renderable by matplotlib
```

### Custom indicator + multi-asset pair trading

```python
from stockstat.backtest import strategy, Order, BacktestEngine
import numpy as np

@strategy
def pair_trade(ctx):
    if not ctx.history.get("init"):
        def donchian(high, low, window=20):
            return high.rolling(window).max(), low.rolling(window).min()
        ctx.compute.register("donchian", donchian)
        ctx.history["init"] = True

    btc = ctx.get("BTC/USDT", "1d", lookback=60)
    eth = ctx.get("ETH/USDT", "1d", lookback=60)
    if len(btc) < 40:
        return
    spread = np.log(btc.close) - np.log(eth.close)
    z = (spread - spread.rolling(20).mean()) / spread.rolling(20).std()
    last = z.iloc[-1]
    if last > 1.5:
        ctx.broker.submit(Order("BTC/USDT", "sell", 0.1))
        ctx.broker.submit(Order("ETH/USDT", "buy", 0.1))
    # ... closing logic

res = BacktestEngine(data=data, strategy=pair_trade,
                     initial_cash=10000, allow_short=True).run()
```

### Intrabar execution: same-bar entry + TP/SL exit

The `IntrabarExecution` model simulates the full order-matching lifecycle inside a parent bar (e.g. daily) using sub-bars (e.g. 1h) — same-bar entry + exit scan + OCO mutual exclusion + order priority.

```python
from stockstat.backtest import (
    BacktestEngine, Strategy, IntrabarMixin, Order,
    IntrabarExecution, BinanceCost,
)

class TPStrategy(Strategy, IntrabarMixin):
    """Market entry → intrabar scan TP limit → close fallback."""
    def on_bar(self, ctx):
        o = ctx.current_price("PAXG/USDT", "open")
        if o is None: return
        ctx.intrabar_submit(Order("PAXG/USDT", "buy", 10.0, tag="entry"))
        ctx.history["tp"] = o * 1.01  # 1% take-profit

    def define_exits(self, entry_fill, ctx):
        tp = ctx.history.get("tp")
        return [
            Order("PAXG/USDT", "sell", entry_fill.qty,
                  order_type="limit", limit_price=tp,
                  tag="tp", exit_reason="tp", priority=1),
            Order("PAXG/USDT", "sell", entry_fill.qty,
                  order_type="market", tag="close",
                  exit_reason="close", priority=99),
        ]

res = BacktestEngine(
    data={"PAXG/USDT": {"1d": paxg_1d, "1h": paxg_1h}},
    strategy=TPStrategy(),
    initial_cash=10000,
    cost_model=BinanceCost(venue="spot"),
    execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),  # ← explicitly enabled
).run()
```

> The default `execution_model=None` is equivalent to `NextBarExecution` (existing behavior, fully backward compatible).

### Backtest capabilities

| Capability | Description |
|------------|-------------|
| Custom strategy | `Strategy` base class / `@strategy` function decorator / **`IntrabarMixin`** |
| Multi-instrument group | `{symbol: {tf: df}}` Universe |
| Multi-timeframe | finest tf drives the master index; higher tfs ffill-aligned |
| Compute-library indicators | `ctx.compute` proxies `ComputeEngine`, includes `register()` |
| Order types | market / limit / stop / trailing stop / **OCO pair** / **mutual OCO** |
| Cost models | percent / fixed / tiered / stamp duty / zero / **Maker/Taker** / **Binance spot+futures+BNB** |
| Short selling | `allow_short=True` |
| Performance | Sharpe / Sortino / Calmar / drawdown / win rate / profit factor |
| Visualization | `plot_equity/plot_drawdown/plot_trades` return PlotSpec |
| **Advanced viz** | `result.chart(name)` returns BacktestChartSpec; dashboard/heatmap/histogram; zero matplotlib hard-dependency |
| Optimization | grid search / optuna (extras) / walk-forward / Monte Carlo |
| Lookahead protection | default NextOpenFill + lookahead_audit |
| **Intrabar limit fill** | `IntrabarLimitFill`: fills when intrabar price crosses limit |
| **Intrabar simulator** | `IntrabarSimulator`: simulate limit fills with finer bars |
| **Pluggable execution** | `ExecutionModel`: `NextBarExecution` (default) / `IntrabarExecution` (sub-bar matching) |
| **Same-bar entry+exit** | `IntrabarExecution`: full lifecycle within a parent bar |
| **Post-entry exit scan** | `IntrabarMixin.define_exits()`: TP/SL/conditional exit after entry fill |
| **Order priority** | `Order(priority=...)`: SL before TP within the same sub-bar |
| **Batch backtest** | `StrategyBatchRunner`: multi-strategy/multi-fee parallel runs |
| **Exit reason tags** | `Order(exit_reason=...)` + `result.exit_reason_stats()` |
| **DCA benchmark** | `dca_equity()` |
| **Subperiod analysis** | `BacktestAnalyzer.subperiod_metrics()` |
| **Regime analysis** | `BacktestAnalyzer.regime_conditional_metrics()` |
| **Fee sweep** | `fee_sweep()` / `maker_taker_sweep()` |

See [DESIGN.md §12](DESIGN.md#12-backtest-subsystem-design) for the backtest design and [docs/backtest/](docs/backtest/) for phase-by-phase docs. Backtest visualization examples are in the [Visualization with Matplotlib](#visualization-with-matplotlib) section below.

## Visualization with Matplotlib

The core library has **zero hard-dependency** on matplotlib. Install it optionally:

```bash
pip install stockstat[matplotlib]          # user install
# or dev install
pip install -e "frontend/[matplotlib]"
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

The signature analysis: PAXG (gold-pegged token) weekend return (x-axis: Friday close → Sunday close) vs Monday's **max gain** `(High-Open)/Open` and **max loss** `(Low-Open)/Open`, recorded **independently** (no selection by signal direction). Real data 2022-2024.

#### Scatter plot — gain & loss on same chart
![PAXG Weekend Scatter](docs/images/paxg_weekend_scatter.png)

**Result**: r(gain)=0.23 (p=0.004), r(loss)=-0.20 (p=0.012). Both significant but weak — the weekend return has modest independent predictive power for both Monday's upside and downside. Up vs Down group means are not significantly different (t-test p>0.26).

#### Gain/loss distribution by weekend direction
![PAXG Directional](docs/images/paxg_directional.png)

#### Weekend return distribution
![PAXG Weekend Histogram](docs/images/paxg_weekend_hist.png)

### Backtest visualization

The backtest visualization subsystem provides 9 chart types with **zero matplotlib hard-dependency** in the core — it auto-activates when matplotlib is installed. The charts below were generated with real market data (Binance BTC/USDT 2023-2024).

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
res.render("drawdown", path="drawdown.png")

# Combined dashboard (2×2 four panels)
res.render("dashboard", path="dashboard.png")

# Batch-save all charts
res.render_all("./charts")

# Advanced charts
res.render("returns_distribution", path="dist.png")   # return distribution histogram
res.render("monthly_heatmap", path="monthly.png")      # monthly returns heatmap
res.render("yearly_returns", path="yearly.png")        # yearly returns bar

# Parameter grid heatmap (with grid_search)
from stockstat.backtest.optimizer import grid_search
results = grid_search(make_engine, {"short": [3,5,8], "long": [10,20,30]}, metric="sharpe")
res.chart("parameter_heatmap", grid_results=results)  # returns BacktestChartSpec
res.render("parameter_heatmap", grid_results=results, path="param.png")
```

Without matplotlib, it gracefully degrades to `NullBacktestChartRenderer` (warns, never crashes).

## Data Sources

| Source | Type | Network | Total Symbols | Description |
|--------|------|---------|---------------|-------------|
| `yfinance` | stock | Yes | On-demand | Yahoo Finance direct API; user provides any ticker (AAPL, MSFT, ^GSPC, ...) |
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
| Coinbase USD pairs (528) | daily | ~132,000 | ~1 MB |
| Coinbase USD pairs (528) | 1-minute | ~277M | ~8 GB |

> SQLite is suitable for small single-machine workloads (tens of thousands to millions of rows). When 1-minute full-market data reaches the GB scale, switch to TimescaleDB (Docker deployment) and enable Hypertable compression.

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
# Backend tests (real data via proxy)
cd backend && python -m pytest tests/test_backend.py -v

# Frontend unit tests (indicators, DSL, visualization)
cd frontend && python -m pytest tests/test_frontend.py -v

# Signal processing & nonlinear dynamics tests
cd frontend && python -m pytest tests/test_nonlinear.py -v

# Backtest tests (interface, MVP, portfolio, multi-tf, cost, metrics, optimizer, 12 strategies, visualization, online real-data, engine enhancement)
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

# Matplotlib chart tests (generates images to docs/images/)
cd frontend && python -m pytest tests/test_matplotlib_charts.py -v
```

## Documentation

- [Usage Guide](docs/USAGE.md) — detailed examples with expected results
- [Design Report](DESIGN.md) — full architecture design (incl. [§12 Backtest Subsystem](DESIGN.md#12-backtest-subsystem-design) · [§12.12 Pluggable Execution Model](DESIGN.md#1212-pluggable-execution-model) · [§12.13 Backtest Visualization](DESIGN.md#1213-backtest-visualization) · [§4.6 Signal Processing & Nonlinear Dynamics](DESIGN.md#46-signal-processing--nonlinear-dynamics-module))
- [Backtest Phase Docs](docs/backtest/) — BT-0 through BT-14 + BT-V0 through V3 + online validation report
- [Test Report](reports/TEST_REPORT.md) — test results
- PAXG Weekend-Monday research (`working/` directory, not version-controlled) — v1~v5 complete study + engine improvement reports; stage report extracted to [docs/backtest/BT11_BT14_CN.md](docs/backtest/BT11_BT14_CN.md)

## Configuration

### Backend environment variables

| Env var | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database connection string (switchable to `postgresql://...`) |
| `REDIS_URL` | (empty) | Redis connection (optional; not auto-wired by current code) |
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
