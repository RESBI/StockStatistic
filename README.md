# StockStat — Programmable Financial Instrument Statistical Computing Platform

A user-programmable stock / cryptocurrency statistical computing platform with **compute-storage separation** architecture, supporting local / remote / offline deployment modes, reserved for future distributed compute.

- **Unified data access**: yfinance direct (85 curated symbols + manual input for any ticker) / ccxt (Binance 4,498, Coinbase 1,183 pairs) / synthetic data
- **Programmable computation**: Python library + SQL-like DSL (v2.0 auto-reflects 23 indicators from `PluginRegistry`)
- **Backtest subsystem**: multi-instrument / multi-timeframe / pluggable execution model / 9 visualization charts / intrabar matching
- **Compute-storage separation**: Storage backend independently deployed; frontend library connects via HTTP or local Storage; **offline mode can directly download data from sources or read existing SQLite files**
- **Zero hard dependency**: Core depends only on pandas / numpy / scipy; matplotlib / lark / PyWavelets / rich are optional extras
- **Visual management**: Web SPA (lazy-loading K-line chart + download modal + source range probing) + TUI terminal interface

## Quick Start

### Local Development (SQLite, no Docker)

```bash
# 1. Install backend
cd backend && pip install -e .

# 2. (Optional) Enable proxy
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889

# 3. Start API service (default sqlite:///stockstat.db, data persists; includes Admin Plugin)
stockstat serve --host 0.0.0.0 --port 8000

# 4. Install frontend library (another terminal)
cd frontend && pip install -e .

# 5. (Optional) Install extras
pip install -e "frontend/[matplotlib]"          # Visualization
pip install -e "frontend/[dsl]"                 # DSL parser (lark)
pip install -e "frontend/[signal_processing]"   # Wavelets (PyWavelets)
pip install -e "frontend/[backtest_full]"       # Full backtest suite
pip install rich                                # TUI colored tables
```

After startup, visit `http://localhost:8000/admin/` in a browser to use the web admin interface.

### Compute-Storage Separation

Backend deployed independently; frontend accesses via HTTP:

```python
from stockstat import StockStatClient
client = StockStatClient(host="192.168.1.100", port=8000)

client.ingest("BTC/USDT", source="binance", start="2024-01-01")
data = client.ohlcv("BTC/USDT")
symbols = client.symbols()
```

Also accessible via CLI / TUI / browser against the same backend.

### Offline Mode (no backend needed)

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage, SQLStorage

# Option 1: Download to memory
client = V2Client(mode="offline", storage=MemoryStorage())
client.ingest("BTC/USDT", source="binance", start="2024-01-01")  # Direct Binance download
df = client.ohlcv("BTC/USDT")

# Option 2: Read existing SQLite database file
client = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///stockstat.db"))
df = client.ohlcv("BTC/USDT")

# Option 3: Download + persist to SQLite
client = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///my_data.db"))
client.ingest("AAPL", source="yfinance", start="2024-01-01")
```

### Docker Production

```bash
docker compose up -d
# API available at http://localhost:8000
```

## Usage

StockStat provides three usage entry points (sharing the same backend service and data):

- **Python library**: `StockStatClient` — full-featured programmatic API (indicators, backtest, DSL, visualization)
- **CLI**: `stockstat` — ingest, query, and manage plugins without writing Python
- **DSL**: SQL-like declarative query language — one-liner for data query + indicator computation

### Ingest data

Supports multiple data sources (yfinance / Binance / Coinbase / synthetic), auto-detects source type (`/` in symbol → crypto, else → stock). Each source supports multiple timeframes (Binance 16: 1s ~ 1M; yfinance 12: 1m ~ 3mo). `probe_range()` can probe the actual available time range before ingestion.

```python
from stockstat import StockStatClient
client = StockStatClient(host="localhost", port=8000)

# Stocks (Yahoo Finance direct, supports any ticker: AAPL / ^GSPC / 600519.SS / GC=F / JPY=X)
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")

# Crypto (Binance, supports 16 timeframes: 1s/1m/3m/5m/15m/30m/1h/2h/4h/6h/8h/12h/1d/3d/1w/1M)
client.ingest("BTC/USDT", source="binance", start="2024-01-01", timeframe="1h")

# Auto-detect source (stocks → yfinance, crypto → binance)
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")
```

```bash
# CLI equivalent
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

### Query data

Supports time range filtering, timeframe selection, row limit, and `order=asc/desc` bidirectional pagination (for K-line chart lazy loading). Results are pandas DataFrames with ascending time index. JSON / CSV output formats supported.

```python
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")
# Bidirectional pagination (lazy-loading scenarios)
recent = client.ohlcv("BTC/USDT", limit=500, order="desc")  # most recent 500 bars
earlier = client.ohlcv("BTC/USDT", end="2024-01-01", limit=1000, order="desc")  # 1000 earlier bars

# Batch query multiple symbols
batch = client.ohlcv_batch(["BTC/USDT", "ETH/USDT"], start="2024-01-01")
```

```bash
stockstat query BTC/USDT --limit 5
stockstat query AAPL --start 2024-01-01 --format csv
```

### Compute indicators

23 built-in technical indicators across 5 categories: trend (MA / EMA / MACD), oscillator (RSI / KDJ), volatility (Bollinger / ATR / STD), statistics (Beta / Sharpe / Max Drawdown / VaR / Correlation), transform (returns / log returns). All accept pandas Series, return Series or scalar.

```python
# Trend indicators
sma = client.compute.ma(data.close, window=20)
ema = client.compute.ema(data.close, window=12)
macd_line, signal_line, hist = client.compute.macd(data.close)

# Oscillators
rsi = client.compute.rsi(data.close, window=14)
k, d, j = client.compute.kdj(data.high, data.low, data.close, window=9)

# Volatility indicators
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
atr = client.compute.atr(data.high, data.low, data.close, window=14)

# Statistical indicators
beta = client.compute.beta(stock_returns, market_returns, window=60)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
dd = client.compute.max_drawdown(data.close)
var_95 = client.compute.var(returns, confidence=0.95)

# Register custom indicator
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, threshold=0.04):
    vol = data.close.pct_change().rolling(window).std()
    return vol.apply(lambda v: "high" if v > threshold else "low")
```

### DSL queries (v2.0 auto-reflection)

SQL-like declarative query language — one-liner for data query + indicator computation. v2.0 `DslEngine` auto-reflects all 23 registered indicators from `PluginRegistry` (including 8 nonlinear indicators), richer than v1.7's 15 hardcoded functions. Supports `SELECT ... FROM ... WHERE ... LIMIT` syntax with keyword arguments.

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')

# With WHERE filter
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

> After registering a new indicator to `PluginRegistry`, call `engine.refresh()` to make it DSL-available — no manual function mapping needed.

### Backtesting

Full-featured quantitative backtest engine: multi-instrument groups, multi-timeframe bars (finest tf drives master index, higher tfs ffill-aligned), 6 order types (market / limit / stop / trailing stop / OCO / mutual OCO), 8 cost models (including Binance spot/futures + BNB discount 4 presets), 7 fill models, pluggable execution (`NextBarExecution` default / `IntrabarExecution` same-bar entry+exit), short selling, lookahead protection, parameter grid search, batch backtesting, exit reason analysis, subperiod/regime analysis, DCA benchmark, fee sweep. Strategies can use all 23 indicators via `ctx.compute`.

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
print(res.summary())  # Sharpe / Sortino / Calmar / drawdown / win rate / profit factor
res.render("dashboard", path="dashboard.png")  # 9 chart types, auto-activated with matplotlib
```

Backtest visualization provides 9 chart types: equity curve, drawdown, trade annotations, returns distribution, monthly heatmap, yearly returns, parameter grid heatmap, underwater curve, dashboard (2×2). Without matplotlib, gracefully degrades to `NullBacktestChartRenderer` (warns, never crashes).

<details open>
<summary>📊 Classic Statistical Charts (real data)</summary>

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

</details>

<details open>
<summary>📈 Backtest Visualization Charts (real data)</summary>

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

</details>

### Signal Processing & Nonlinear Dynamics

8 advanced analysis functions covering signal processing (CWT / spectral entropy / grey relation / GM(1,1) grey prediction) and nonlinear dynamics (transfer entropy / Hurst exponent DFA / sample entropy / permutation entropy). When PyWavelets is not installed, CWT gracefully degrades to FFT-based Morlet. Also provides 3 PlotSpec factory functions (CWT scalogram / DFA fit plot / PSD plot).

```python
import numpy as np
path = data.close.values[-48:]

# Signal processing
coef, scales = client.compute.wavelet_decompose(path, scales=np.arange(1, 25))  # CWT
h_spec = client.compute.spectral_entropy(np.diff(np.log(path)))                  # Spectral entropy
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)                       # Grey relation
forecast = client.compute.gm11_predict(sequence)                                  # GM(1,1) prediction

# Nonlinear dynamics
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))    # Hurst (≈0.5 random | >0.5 persistent)
te = client.compute.transfer_entropy(btc_rets, eth_rets)   # Transfer entropy (directed info flow)
sampen = client.compute.sample_entropy(signal, m=2)         # Sample entropy
permen = client.compute.permutation_entropy(signal, m=3)    # Permutation entropy

# Visualization
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
renderer = client.plot.get_renderer()
renderer.render(spec)
```

<details open>
<summary>🔬 PAXG Weekend Return vs Monday Gain/Loss (real data 2022-2024)</summary>

PAXG (gold-pegged token) weekend return (Friday close → Sunday close) vs Monday's **max gain** and **max loss**, recorded **independently**.

#### Scatter plot — gain & loss on same chart
![PAXG Weekend Scatter](docs/images/paxg_weekend_scatter.png)

**Result**: r(gain)=0.23 (p=0.004), r(loss)=-0.20 (p=0.012). Both significant but weak — the weekend return has modest independent predictive power for both Monday's upside and downside.

#### Gain/loss distribution by weekend direction
![PAXG Directional](docs/images/paxg_directional.png)

#### Weekend return distribution
![PAXG Weekend Histogram](docs/images/paxg_weekend_hist.png)

</details>

## Management Interfaces

### TUI Terminal Interface

```bash
stockstat tui                    # Connect to local server
stockstat tui --host 192.168.1.100
```

Provides 6 interactive menu items: browse symbols / query OHLCV / ingest data / data statistics / list data sources / view proxy config. Based on `rich` (optional), falls back to plain text.

### Web Admin Interface

Visit `http://storage-server:8000/admin/` in a browser:

| Page | Function |
|------|----------|
| Overview | Symbol count, rows, disk, data coverage Gantt chart, recent ingests |
| Source Browser | Pagination + search + batch download + **manual symbol input** |
| Local Symbols | K-line chart (**lazy loading on zoom**) + range ingest + CSV export |
| Config | Database / proxy (live update) / cache / disk |
| Logs | Ingest history (paginated + filtered) |

**K-line chart lazy loading**: Initial load of 500 bars → auto-loads off-screen data on zoom (300ms debounce + timestamp dedup + progress display)

**Download modal**: Auto-probes source range (`probe_range` fetches first/last bars) → pre-fills max date range → dynamic timeframe dropdown → storage estimate hint

## Data Sources

| Source | Type | Symbols | Timeframes | Range probing |
|--------|------|---------|------------|---------------|
| `yfinance` | stock/ETF/index/commodity/FX | 85 curated + manual input | 12 | ✅ Yahoo API probed |
| `binance` | crypto | 4,498 (1,479 USDT pairs) | 16 | ✅ First/last bar probed |
| `coinbase` | crypto | 1,183 (528 USD pairs) | 7 | ✅ First/last bar probed |
| `synthetic` | mixed | 5 examples | 9 | ✅ Fixed range |

## Optional Extras

| Extra | Purpose |
|-------|---------|
| `matplotlib` | Protocol-based visualization (lazy import, zero core dependency) |
| `dsl` | DSL parser (lark) |
| `signal_processing` | PyWavelets (full CWT) |
| `backtest_full` | Full backtest suite (matplotlib + optuna) |
| `rich` | TUI colored tables |

## Running Tests

```bash
cd backend && python -m pytest tests/ -v          # Backend: 15 tests
cd frontend && python -m pytest tests/ -v          # Frontend: 491 tests
```

**506 tests total, all passing.**

### Connection & Performance Tests

Two integration test scripts are included for verifying frontend-backend communication and measuring performance:

```bash
# Connection test: health check -> ingest data -> query -> indicators -> DSL -> backtest -> visualization
python tests/test_connection.py --host localhost --port 8000
python tests/test_connection.py --host 192.168.1.100 --port 8000   # remote backend

# Performance test: RTT latency -> query latency vs data size -> transfer speed -> jitter
python tests/test_perf.py --host localhost --port 8000 --rounds 10
```

See [Usage Guide §17](docs/USAGE.md#17-connection--performance-tests).

## Startup Scripts

The backend provides minimal startup scripts and full configuration scripts:

```bash
# Minimal startup (edit env vars and run)
backend/start.bat            # Windows
backend/start.sh             # Linux/macOS

# Full configuration (CLI args + interactive config)
backend/serve.bat --config   # Windows
backend/serve.sh --config    # Linux/macOS
```

## Documentation

- [Usage Guide](docs/USAGE.md) — detailed examples with expected results
- [Design Report](DESIGN.md) — full architecture design (including distributed compute reservation)
- [Backtest Phase Docs](docs/backtest/) — BT-0 through BT-14 + BT-V0 through V3
- [Compute Offload Plan](reports/COMPUTE_OFFLOAD_PLAN_V2_CN.md) — distributed compute architecture design

## Configuration

### Backend environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database connection string |
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_ADMIN_ENABLED` | `true` | Enable web admin interface |

### Frontend environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCKSTAT_HOST` | `localhost` | Frontend default host |
| `STOCKSTAT_PORT` | `8000` | Frontend default port |

---

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file.

Copyright (C) 2026 RESBI

## Acknowledgements & Disclaimer

This project — including all source code, documentation, tests, and charts — was entirely designed, implemented, and documented by **GLM-5.2**, an AI assistant.

This software is provided for **educational and research purposes only**. It is **not** financial, investment, or trading advice. Users are solely responsible for their own investment decisions and should consult a qualified financial professional before making any investment.
