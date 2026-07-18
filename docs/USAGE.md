# StockStat Usage Guide

> All examples in this document were tested locally with real market data (Yahoo Finance + Binance, via proxy). Expected results are from an actual test run on 2026-07-18.

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Data Ingestion](#2-data-ingestion)
3. [Querying OHLCV Data](#3-querying-ohlcv-data)
4. [Computing Indicators](#4-computing-indicators)
5. [DSL Queries](#5-dsl-queries)
6. [Custom Indicators](#6-custom-indicators)
7. [Visualization](#7-visualization)
8. [Backtesting](#8-backtesting)
9. [Advanced Backtest Features](#9-advanced-backtest-features)
10. [Signal Processing & Nonlinear Dynamics](#10-signal-processing--nonlinear-dynamics)
11. [Result Export](#11-result-export)
12. [v2.0 CLI](#12-v20-cli)
13. [Offline Mode](#13-offline-mode)
14. [Plugin System](#14-plugin-system)
15. [Management Interfaces](#15-management-interfaces)
16. [PAXG Weekend Correlation Analysis](#16-paxg-weekend-correlation-analysis)
17. [Connection & Performance Tests](#17-connection--performance-tests)
18. [Startup Scripts](#18-startup-scripts)

---

## 1. Environment Setup

### Installation

The project contains two independent pip packages: `stockstat-backend` (storage backend service) and `stockstat` (computation frontend library). Both can be installed in development mode via `pip install -e .`.

```bash
# Backend (FastAPI + SQLAlchemy + data source adapters)
cd backend && pip install -e .

# Frontend core library (ComputeEngine + backtest + DSL + visualization + CLI/TUI)
cd frontend && pip install -e .

# Optional extras (install as needed)
pip install -e "frontend/[matplotlib]"          # Visualization (lazy import, zero core dependency)
pip install -e "frontend/[dsl]"                 # DSL parser (lark, EBNF grammar)
pip install -e "frontend/[signal_processing]"   # Wavelets (PyWavelets, full CWT)
pip install -e "frontend/[backtest_full]"       # Full backtest suite (matplotlib + optuna)
pip install rich                                # TUI colored tables (falls back to plain text)
```

> The frontend library's core dependencies are only pandas / numpy / scipy / httpx / pyarrow. It does not force dependency on matplotlib / lark / PyWavelets. When optional extras are not installed, relevant features gracefully degrade (e.g., CWT degrades to FFT-based Morlet, visualization degrades to NullRenderer which warns but never crashes).

### Enable Proxy (to access real data sources)

The backend directly connects to Yahoo Finance / Binance API by default. If you need a proxy (e.g., in mainland China):

```bash
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http                    # or socks5
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889    # your proxy address
```

Proxy configuration applies to all data source adapters (yfinance / ccxt) in the backend. Requires backend restart after change.

### Start the Backend

```bash
# Option 1: uvicorn direct (most transparent)
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000

# Option 2: v2.0 CLI (equivalent, more concise, auto-loads Admin Plugin)
stockstat serve --host 0.0.0.0 --port 8000
```

After backend startup:
- REST API available at `http://localhost:8000/api/v1/*`
- Web admin interface at `http://localhost:8000/admin/` (controlled by `STOCKSTAT_ADMIN_ENABLED`, default on)
- Default SQLite (`stockstat.db`), data persists to file, auto-reads on restart

### Specifying the Database Storage Location

By default, data is stored in `stockstat.db` in the backend's working directory. Custom location via `DATABASE_URL`:

```bash
# SQLite — absolute path (note: sqlite:/// + /abs/path = 4 slashes)
export DATABASE_URL="sqlite:////data/stockstat/stockstat.db"

# SQLite — relative path (data/ in parent directory)
export DATABASE_URL="sqlite:///../data/stockstat.db"

# PostgreSQL / TimescaleDB (Docker production)
export DATABASE_URL="postgresql://stockstat:password@db-host:5432/stockstat"
```

| `DATABASE_URL` value | Actual storage location |
|---|---|
| `sqlite:///stockstat.db` (default) | `stockstat.db` in current working directory |
| `sqlite:////data/stockstat.db` | `/data/stockstat.db` (absolute path, 4 slashes) |
| `sqlite:///../data/stockstat.db` | `data/` in parent directory (relative path) |
| `postgresql://user:pwd@host:5432/db` | Remote PostgreSQL database |

> The SQLite URL format is `sqlite:///` + path. Absolute paths start with `/`, so the concatenation yields 4 slashes: `sqlite:////abs/path`. Once data is written to the specified file, the service automatically reads previous data on restart.

### Frontend Connection

```python
from stockstat import StockStatClient

# Style 1: direct configuration (most common)
client = StockStatClient(host="localhost", port=8000)

# Style 2: from environment variables (STOCKSTAT_HOST / STOCKSTAT_PORT / STOCKSTAT_API_KEY etc.)
client = StockStatClient.from_env()

# Style 3: dict configuration
client = StockStatClient.from_dict({"host": "localhost", "port": 8000})

# Style 4: connect to remote storage server (compute-storage separation)
client = StockStatClient(host="192.168.1.100", port=8000)

# Style 5: with API Key authentication (if backend configured with Bearer auth)
client = StockStatClient(host="192.168.1.100", port=8000, api_key="my-secret-key")
```

The frontend sends HTTP requests to the backend REST API via `httpx`. Default connection timeout is 30 seconds, adjustable via `timeout` parameter.

---

## 2. Data Ingestion

Data ingestion is a backend capability: frontend calls `client.ingest()` → HTTP POST → backend adapter fetches from data source → normalizes → stores in database. Supports 4 data sources with auto-detection (symbol containing `/` → crypto binance, else → stock yfinance).

### Example 2.1: Ingest stock data

```python
result = client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
print(result)
```

**Expected result**:
```python
{'symbol': 'AAPL', 'source': 'yfinance', 'ingested': 251}
```

The return value `ingested` is the actual number of rows written to the database. If the same symbol and time range has been ingested before, it performs an upsert (deduplicated by `(symbol, ts, timeframe, source)` composite unique constraint), so no duplicate data is produced.

### Example 2.2: Ingest crypto data

```python
result = client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
print(result)
```

**Expected result**:
```python
{'symbol': 'BTC/USDT', 'source': 'binance', 'ingested': 366}
```

Crypto trades 24/7, so 2024 (leap year) has 366 daily bars. Binance is accessed via ccxt library with automatic pagination (1000 bars per page, auto-fetching until the full range is retrieved).

### Example 2.3: Auto-detect data source

When `source` parameter is omitted, the system auto-detects based on symbol format:

```python
# Stock symbols (no "/") → yfinance
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")

# Crypto symbols (with "/") → binance
client.ingest("ETH/USDT", start="2024-01-01", end="2024-12-31")
```

### Example 2.4: Finer timeframes

Binance supports 16 timeframes (1 second to 1 month), yfinance supports 12 (1 minute to 3 months). Specify via `timeframe` parameter:

```python
# Binance: 1s / 1m / 3m / 5m / 15m / 30m / 1h / 2h / 4h / 6h / 8h / 12h / 1d / 3d / 1w / 1M
client.ingest("BTC/USDT", source="binance", start="2024-06-01", end="2024-06-02", timeframe="1m")
# 1-minute data, ~2880 rows for 2 days

# yfinance: 1m / 2m / 5m / 15m / 30m / 60m / 90m / 1d / 5d / 1wk / 1mo / 3mo
client.ingest("AAPL", source="yfinance", start="2024-06-01", end="2024-06-07", timeframe="5m")
# 5-minute data, ~390 rows/day × 5 trading days
```

> **Storage estimate**: 1-minute granularity 1 year ≈ 15 MB; 1-second granularity 1 year ≈ 900 MB. All 1,479 Binance USDT pairs at 1-minute for 1 year ≈ 22 GB. SQLite is suitable for small single-machine workloads; for GB-scale, switch to TimescaleDB + Hypertable compression.

### Example 2.5: Download any yfinance symbol

Yahoo Finance has no public "list all symbols" API but supports any valid ticker. Beyond the 85 curated symbols in the web admin UI, users can download any symbol directly:

```python
# China A-shares (Shanghai Stock Exchange)
client.ingest("600519.SS", source="yfinance", start="2020-01-01", end="2024-12-31")  # Kweichow Moutai

# FX rates
client.ingest("USDCNY=X", source="yfinance", start="2022-01-01", end="2024-12-31")  # USD/CNY

# Commodity futures
client.ingest("GC=F", source="yfinance", start="2020-01-01", end="2024-12-31")      # Gold futures
client.ingest("CL=F", source="yfinance", start="2020-01-01", end="2024-12-31")      # Crude oil futures

# Hong Kong stocks
client.ingest("0700.HK", source="yfinance", start="2020-01-01", end="2024-12-31")   # Tencent
```

### Example 2.6: Ingest via CLI

No Python script needed — ingest directly from command line:

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

Output:
```json
{"symbol": "AAPL", "source": "yfinance", "ingested": 251}
```

### Example 2.7: Batch ingest symbols for analysis

Ingest multiple symbols at once to prepare for analysis:

```python
symbols = [
    ("AAPL", "yfinance", "2023-01-01", "2024-12-31"),
    ("^GSPC", "yfinance", "2023-01-01", "2024-12-31"),    # S&P 500 index (market benchmark)
    ("BTC/USDT", "binance", "2024-01-01", "2024-12-31"),
    ("ETH/USDT", "binance", "2024-01-01", "2024-12-31"),
    ("PAXG/USDT", "binance", "2022-01-01", "2024-12-31"),  # PAXG weekend effect needs longer history
]
for sym, source, start, end in symbols:
    result = client.ingest(sym, source=source, start=start, end=end)
    print(f"{sym}: {result['ingested']} rows")
```

---

## 3. Querying OHLCV Data

Querying is the frontend fetching stored data from the backend via HTTP GET. Returns a pandas DataFrame with ascending time index (UTC timezone).

### Example 3.1: Query as DataFrame

```python
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d", limit=5)
print(data)
```

**Expected result**:
```
                                   open    high     low   close     volume
ts
2024-01-02  187.15  188.44  183.89  185.64  82488700
2024-01-03  184.22  185.88  183.43  184.25  58414500
2024-01-04  182.15  183.09  181.37  181.91  71983600
2024-01-05  181.99  182.76  181.18  181.18  62379700
2024-01-08  182.09  185.60  182.09  185.56  59144500
```

The DataFrame index is `ts` (UTC timestamp), columns include `open / high / low / close / volume`. `limit=5` returns only the 5 most recent bars (in ascending order).

### Example 3.2: Bidirectional pagination (lazy-loading scenarios)

The `order` parameter supports bidirectional pagination for K-line chart lazy loading:

```python
# Most recent 500 bars (K-line chart initial load)
recent = client.ohlcv("BTC/USDT", limit=500, order="desc")

# 1000 earlier bars (load when user scrolls left)
earlier = client.ohlcv("BTC/USDT", end="2024-01-01", limit=1000, order="desc")

# 1000 later bars (load when user scrolls right)
later = client.ohlcv("BTC/USDT", start="2024-06-01", limit=1000, order="asc")
```

> Whether `order=asc` or `desc`, the returned DataFrame is internally ascending by time for downstream convenience. With `order=desc`, `limit=N` returns the **most recent N bars** (counting backward from latest), not the oldest N. The web admin's K-line chart lazy loading is based on this parameter.

### Example 3.3: Batch query

Query multiple symbols at once, returns a dict:

```python
batch = client.ohlcv_batch(["BTC/USDT", "ETH/USDT"], start="2024-01-01")
btc = batch["BTC/USDT"]
eth = batch["ETH/USDT"]
print(f"BTC: {len(btc)} rows, ETH: {len(eth)} rows")
```

### Example 3.4: List registered symbols

See what symbols are in the database:

```python
for s in client.symbols():
    print(f"{s['unified_symbol']:15s} {s['asset_type']:8s} {s['sources']}")
```

Output example:
```
BTC/USDT       crypto   ['binance']
ETH/USDT       crypto   ['binance']
AAPL           stock    ['yfinance']
```

### Example 3.5: Query via CLI

```bash
# Table format (default, for terminal viewing)
stockstat query BTC/USDT --limit 5

# JSON format (for piping)
stockstat query BTC/USDT --format json

# CSV format (for file export)
stockstat query AAPL --start 2024-01-01 --format csv > aapl.csv
```

---

## 4. Computing Indicators

`client.compute` is a `ComputeEngine` instance providing 23 built-in indicators. All accept pandas Series input, return Series or scalar. Indicator computation runs entirely in the frontend process — no HTTP requests needed.

### Trend Indicators

```python
# Simple Moving Average
ma20 = client.compute.ma(data.close, window=20)
print(f"MA(20) latest: {ma20.iloc[-1]:.2f}")

# Exponential Moving Average — more weight on recent data
ema12 = client.compute.ema(data.close, window=12)

# MACD — returns 3 series
macd_line, signal_line, hist = client.compute.macd(data.close)
# macd_line: MACD line (fast-slow EMA difference)
# signal_line: Signal line (9-day EMA of MACD line)
# hist: Histogram (MACD line - Signal line)
print(f"MACD: {macd_line.iloc[-1]:.2f}, Signal: {signal_line.iloc[-1]:.2f}, Hist: {hist.iloc[-1]:.2f}")
```

### Oscillators

```python
# RSI (Relative Strength Index) — 0~100, >70 overbought, <30 oversold
rsi = client.compute.rsi(data.close, window=14)
print(f"RSI last 5 days:\n{rsi.tail(5).round(2)}")
print(f"Overbought days (>70): {(rsi > 70).sum()}")
print(f"Oversold days (<30): {(rsi < 30).sum()}")

# KDJ — returns K, D, J three lines
k, d, j = client.compute.kdj(data.high, data.low, data.close, window=9)
print(f"K: {k.iloc[-1]:.2f}, D: {d.iloc[-1]:.2f}, J: {j.iloc[-1]:.2f}")
```

### Volatility Indicators

```python
# Bollinger Bands — returns upper, middle, lower three lines
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
print(f"Upper: {upper.iloc[-1]:.2f}")
print(f"Middle: {mid.iloc[-1]:.2f}")   # Middle = MA(20)
print(f"Lower: {lower.iloc[-1]:.2f}")  # Lower = Middle - 2×Std(20)

# ATR (Average True Range) — measures volatility magnitude
atr = client.compute.atr(data.high, data.low, data.close, window=14)
print(f"ATR(14): {atr.iloc[-1]:.2f}")

# Rolling standard deviation — direct volatility measure
std = client.compute.std(data.close, window=20)
print(f"20-day volatility: {std.iloc[-1]:.2f}")
```

### Statistical Indicators

```python
# Beta — systematic risk relative to market benchmark
stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")  # S&P 500
beta = client.compute.beta(stock.close.pct_change(), market.close.pct_change(), window=60)
print(f"Beta (60-day) mean: {beta.dropna().mean():.4f}")
# Beta > 1: more volatile than market; Beta < 1: less volatile

# Sharpe ratio — risk-adjusted return
rets = client.compute.returns(data.close).dropna()
sharpe = client.compute.sharpe(rets, risk_free=0.02, annualize=True)
print(f"BTC Sharpe ratio (annualized): {sharpe:.4f}")
# Sharpe > 1: good; > 2: excellent

# Maximum drawdown — largest peak-to-trough decline
dd = client.compute.max_drawdown(data.close)
print(f"BTC max drawdown: {dd:.4f} ({dd*100:.2f}%)")

# Value at Risk (VaR) — max potential loss at given confidence level
var_95 = client.compute.var(rets, confidence=0.95)
print(f"95% VaR (daily): {var_95:.4f} ({var_95*100:.2f}%)")
# Meaning: 95% confident that daily loss won't exceed this value

# Pearson correlation
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
corr = client.compute.corr(btc.close.pct_change().dropna(), eth.close.pct_change().dropna())
print(f"BTC/ETH daily-return correlation: {corr:.4f}")
```

### Golden / Death Cross

Using moving average crossovers to identify trend changes:

```python
ma_short = data.close.rolling(5).mean()   # Short-term MA
ma_long = data.close.rolling(20).mean()   # Long-term MA

# Golden cross: short MA crosses above long MA (bullish signal)
golden_cross = (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
# Death cross: short MA crosses below long MA (bearish signal)
death_cross = (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))

print(f"Golden crosses: {golden_cross.sum()}")
print(f"Death crosses: {death_cross.sum()}")
```

---

## 5. DSL Queries

> The DSL is based on lark and requires `pip install stockstat[dsl]`. v2.0's `DslEngine` auto-reflects all 23 registered indicators from `PluginRegistry` as DSL functions, replacing v1.7's manually-maintained `_BUILTIN_FUNCS` dict (15 functions). Falls back to v1.7 `Evaluator` when v2.0 layer unavailable.

DSL is a SQL-like declarative query language with syntax `SELECT ... FROM ohlcv(...) WHERE ... LIMIT ...`. It combines data query and indicator computation in one step, suitable for quick exploratory analysis.

### Example 5.1: Basic DSL query

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20
    FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
print(result)
```

The `ohlcv()` function parameters are: symbol, timeframe, start date, end date. The `AS` keyword assigns an alias to the computed column.

### Example 5.2: DSL query for RSI

```python
result = client.run_dsl('''
    SELECT rsi(close, 14) AS rsi_val
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 10
''')
```

### Example 5.3: DSL with WHERE filter

```python
# Only days where close > 100000
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

### Example 5.4: DSL with keyword arguments

DSL supports keyword argument syntax:

```python
result = client.run_dsl('''
    SELECT close, ma(close, window=20) AS ma20
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
```

> v2.0 `DslEngine` supports 8 more nonlinear indicators than v1.7 (`wavelet_decompose`, `spectral_entropy`, `grey_relation`, `gm11_predict`, `transfer_entropy`, `hurst_dfa`, `sample_entropy`, `permutation_entropy`). After registering a new indicator to `PluginRegistry`, call `engine.refresh()` to make it DSL-available.

---

## 6. Custom Indicators

### Register via ComputeEngine (for Python library use)

Use `@client.compute.register` decorator to register custom indicators, then call via `client.compute.call()`:

```python
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, high_threshold=0.04):
    """Identify high/low volatility regimes.

    When 20-day rolling std > 4%, label as "high", otherwise "low".
    Returns dict with regime labels and volatility series.
    """
    ret = data.close.pct_change()
    vol = ret.rolling(window).std()
    regime = vol.apply(lambda v: "high" if v > high_threshold else "low")
    return {"regime": regime, "volatility": vol}

# Call custom indicator
result = client.compute.call("volatility_regime", data=btc)
print(result["regime"].value_counts())  # Count high/low volatility days
```

### Register via v2.0 IndicatorPlugin (auto DSL-available)

Register to `PluginRegistry` via `IndicatorPlugin`, then DSL engine auto-reflects:

```python
from stockstat._domain.indicators import IndicatorPlugin
from stockstat._core.plugin import get_registry

reg = get_registry()

def rolling_max(x, window=10):
    """Rolling maximum."""
    return x.rolling(window).max()

reg.register("indicators", "rolling_max",
    IndicatorPlugin("rolling_max", rolling_max, "custom",
                    description="Rolling maximum"))

# Refresh DSL engine to make it available
from stockstat._api.dsl import DslEngine
engine = DslEngine(reg, client=client._data_client)
engine.refresh()

# rolling_max is now DSL-available
result = engine.eval('''
    SELECT close, rolling_max(close, 5) AS rmax
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
```

> v1.7 required 3 changes per new indicator (write function → add ComputeEngine method → add DSL `_BUILTIN_FUNCS` mapping); v2.0 requires only writing one `IndicatorPlugin` and registering — DSL auto-available.

---

## 7. Visualization

The visualization layer uses protocol-based design: `PlotSpec` is a backend-agnostic plot specification, `Renderer` handles actual rendering. The core library has zero hard dependency on matplotlib — when not installed, degrades to `NullRenderer` (issues UserWarning, never crashes).

### Protocol-based plotting

Build a `PlotSpec` via `client.plot.spec()`, then get a renderer via `client.plot.get_renderer()`:

```python
spec = client.plot.spec(
    title="BTC Close + MA20",
    x_label="Date",
    y_label="Price (USDT)",
    series=[
        {"name": "close", "data": btc.close, "kind": "line"},
        {"name": "ma20", "data": btc.close.rolling(20).mean(), "kind": "line", "color": "red"},
    ],
)
renderer = client.plot.get_renderer("matplotlib")  # specify matplotlib; auto-detect if omitted
fig = renderer.render(spec)
renderer.savefig("btc.png")
```

Each series in `series` supports `kind: line / bar / scatter / fill / histogram / heatmap`, with `color`, `alpha`, `secondary_y` and other properties.

### Use matplotlib directly

You can also bypass the protocol layer and use matplotlib directly with `client.compute` for indicators:

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(btc.index, btc.close, label="Close", color="black")

# Compute Bollinger Bands via ComputeEngine
upper, mid, lower = client.compute.bollinger(btc.close, 20, 2.0)
ax.fill_between(btc.index, lower, upper, alpha=0.15, color="blue", label="Bollinger")
ax.plot(btc.index, mid, color="blue", linestyle="--", label="MA20")

ax.set_title("BTC/USDT Bollinger Bands")
ax.set_xlabel("Date")
ax.set_ylabel("Price (USDT)")
ax.legend()
ax.grid(True, alpha=0.3)
plt.savefig("btc_bollinger.png", dpi=150)
```

![BTC Bollinger](images/btc_bollinger.png)

### Other classic charts

The following charts are generated from real market data:

![BTC RSI](images/btc_rsi.png)

![ETH MACD](images/eth_macd.png)

![BTC Drawdown](images/btc_drawdown.png)

![AAPL Beta Scatter](images/aapl_beta_scatter.png)

![BTC ETH Correlation](images/btc_eth_corr.png)

![Price Comparison](images/price_comparison.png)

### NullRenderer (without matplotlib)

When matplotlib is not installed, `get_renderer()` returns `NullRenderer`. Calling `render()` issues a UserWarning but does not crash:

```python
renderer = client.plot.get_renderer("null")
spec = client.plot.spec(title="Test", series=[{"name": "x", "data": btc.close}])
renderer.render(spec)  # UserWarning: No plotting backend available
```

This allows backtest code to run without errors in headless environments (e.g., servers).

---

## 8. Backtesting

The backtest subsystem lives in `stockstat.backtest` (28 files) and is a full-featured quantitative backtest engine. Supports: multi-instrument groups, multi-timeframe bars, 6 order types (market/limit/stop/trailing stop/OCO/mutual OCO), 8 cost models, 7 fill models, pluggable execution (`NextBarExecution`/`IntrabarExecution`), short selling, lookahead protection, parameter grid search, batch backtesting.

### Minimal backtest (function-style strategy)

Use `@strategy` decorator to turn a plain function into a strategy. The function receives `ctx` (backtest context):

```python
from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost

client = StockStatClient(host="localhost", port=8000)
data = {"BTC/USDT": {"1d": client.ohlcv("BTC/USDT", start="2024-01-01")}}

@strategy
def ma_cross(ctx):
    """Dual MA crossover strategy: buy when MA5 crosses above MA20, sell when below."""
    d = ctx.get("BTC/USDT", "1d", lookback=30)  # Get last 30 bars
    if len(d) < 21: return                        # Skip if insufficient data

    ma5 = d.close.rolling(5).mean().iloc[-1]     # Short-term MA
    ma20 = d.close.rolling(20).mean().iloc[-1]   # Long-term MA
    pos = ctx.portfolio.get_position("BTC/USDT")  # Current position

    if ma5 > ma20 and pos.qty == 0:               # Golden cross + no position → buy
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1, tag="entry"))
    elif ma5 < ma20 and pos.qty > 0:              # Death cross + has position → sell
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty, tag="exit"))

eng = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, cost_model=ZeroCost(),
                     benchmark="BTC/USDT")
res = eng.run()
print(res.summary())
# Output includes: total return, annualized return, Sharpe, Sortino, Calmar,
#                  max drawdown, win rate, profit factor, etc.
```

### Via client convenience entry

`client.backtest()` is a convenience method that auto-injects `ComputeEngine`. Strategies can use all 23 indicators via `ctx.compute`:

```python
res = client.backtest(data, ma_cross, initial_cash=10000, benchmark="BTC/USDT")
# Inside strategy: ctx.compute.rsi(d.close, window=14) is available
```

### Class-style strategy + lifecycle hooks

Inherit from `Strategy` base class to implement `on_start` / `on_bar` / `on_fill` hooks:

```python
from stockstat.backtest import Strategy, Order

class RSIStrategy(Strategy):
    """RSI overbought/oversold strategy: buy <30, sell >70."""

    def on_start(self, ctx):
        """Called before backtest starts. Initialize state here."""
        ctx.history["trade_count"] = 0

    def on_bar(self, ctx):
        """Called on each bar."""
        d = ctx.get("BTC/USDT", "1d", lookback=30)
        if len(d) < 15: return

        # Use ctx.compute for indicators (auto-injected ComputeEngine)
        r = ctx.compute.rsi(d.close, window=14).iloc[-1]
        pos = ctx.portfolio.get_position("BTC/USDT")

        if r < 30 and pos.qty == 0:        # RSI < 30: oversold, buy
            ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
            ctx.history["trade_count"] += 1
        elif r > 70 and pos.qty > 0:       # RSI > 70: overbought, sell
            ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

    def on_fill(self, fill, ctx):
        """Called after each fill."""
        print(f"Fill {fill.side.value} {fill.qty} @ {fill.price:.2f}")
```

### Multi-asset pair trading + short selling

Pair trading: when BTC/ETH spread deviates >1.5 std from mean, short the strong, long the weak:

```python
import numpy as np
from stockstat.backtest import BacktestEngine, strategy, Order

data = {
    "BTC/USDT": {"1d": client.ohlcv("BTC/USDT", start="2024-01-01")},
    "ETH/USDT": {"1d": client.ohlcv("ETH/USDT", start="2024-01-01")},
}

@strategy
def pair(ctx):
    btc = ctx.get("BTC/USDT", "1d", lookback=60)
    eth = ctx.get("ETH/USDT", "1d", lookback=60)
    if len(btc) < 40: return

    # Compute log spread and its Z-score
    spread = np.log(btc.close) - np.log(eth.close)
    z = (spread - spread.rolling(20).mean()) / spread.rolling(20).std()
    last = z.iloc[-1]
    if np.isnan(last): return

    pb = ctx.portfolio.get_position("BTC/USDT")
    # Z > 1.5: BTC relatively expensive vs ETH → short BTC, long ETH
    if last > 1.5 and pb.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", 0.1))   # Short
        ctx.broker.submit(Order("ETH/USDT", "buy", 0.1))    # Long
    # Z < -1.5: BTC relatively cheap vs ETH → long BTC, short ETH
    elif last < -1.5 and pb.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
        ctx.broker.submit(Order("ETH/USDT", "sell", 0.1))

res = BacktestEngine(data=data, strategy=pair,
                     initial_cash=10000, allow_short=True).run()
# allow_short=True enables short selling
```

### Multi-timeframe resonance

Use daily and hourly bars simultaneously: daily for trend direction, hourly for breakout timing:

```python
hourly = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1h")
daily  = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
data = {"BTC/USDT": {"1h": hourly, "1d": daily}}

@strategy
def multi_tf(ctx):
    h = ctx.get("BTC/USDT", "1h", lookback=50)  # Hourly bars
    d = ctx.get("BTC/USDT", "1d", lookback=30)  # Daily bars
    if len(d) < 21 or len(h) < 2: return

    # Daily trend: close above MA20
    trend_up = d.close.iloc[-1] > d.close.rolling(20).mean().iloc[-1]
    # Hourly breakout: latest close breaks previous
    breakout = h.close.iloc[-1] > h.close.iloc[-2]

    pos = ctx.portfolio.get_position("BTC/USDT")
    if trend_up and breakout and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif not trend_up and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

res = BacktestEngine(data=data, strategy=multi_tf).run()
# Engine auto-uses finest timeframe (1h) as master index, daily data ffill-aligned
```

### Parameter grid search

`grid_search` automatically traverses parameter combinations, returns results sorted by metric:

```python
from stockstat.backtest.optimizer import grid_search

def make_engine(params):
    @strategy
    def s(ctx):
        d = ctx.get("BTC/USDT", "1d", lookback=params["long"]+5)
        if len(d) < params["long"]+1: return
        ma_s = d.close.rolling(params["short"]).mean().iloc[-1]
        ma_l = d.close.rolling(params["long"]).mean().iloc[-1]
        pos = ctx.portfolio.get_position("BTC/USDT")
        if ma_s > ma_l and pos.qty == 0:
            ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
        elif ma_s < ma_l and pos.qty > 0:
            ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))
    return BacktestEngine(data=data, strategy=s, initial_cash=10000)

# Traverse 3×3=9 parameter combinations, sorted by Sharpe
results = grid_search(make_engine,
                      {"short": [3, 5, 8], "long": [10, 20, 30]},
                      metric="sharpe")
best_params, best_val, best_res = results[0]
print(f"Best params: {best_params}, Sharpe: {best_val:.3f}")
```

### Backtest visualization

`BacktestResult` provides 9 chart types, auto-activated when matplotlib is installed:

```python
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

# One-liner render
res.render("equity_curve", path="equity.png")         # Equity curve + benchmark
res.render("drawdown", path="drawdown.png")            # Drawdown fill
res.render("dashboard", path="dashboard.png")          # 2×2 dashboard

# Batch save all charts to directory
res.render_all("./charts")

# Other chart types
res.render("returns_distribution", path="dist.png")    # Returns histogram
res.render("monthly_heatmap", path="monthly.png")      # Monthly returns heatmap
res.render("yearly_returns", path="yearly.png")        # Yearly returns bar
res.render("trades_overlay", path="trades.png")        # Trade annotations (B/S arrows)
res.render("parameter_heatmap", grid_results=results, path="param.png")  # Parameter grid heatmap
res.render("underwater_curve", path="underwater.png")  # Underwater curve
```

![BTC Backtest Dashboard](../docs/images/backtest_btc_dashboard.png)

---

## 9. Advanced Backtest Features

### Binance fee models (4 presets)

`BinanceCost` supports 4 fee presets for Binance spot and futures, accurately simulating BNB discount:

```python
from stockstat.backtest import BinanceCost, BINANCE_SPOT, BINANCE_SPOT_BNB, \
    BINANCE_FUTURES, BINANCE_FUTURES_BNB

# F1 Spot no BNB:  maker 0.100% / taker 0.100%
# F2 Spot + BNB:   maker 0.075% / taker 0.075%  (BNB discount saves 25%)
# F3 Futures no BNB: maker 0.020% / taker 0.050%
# F4 Futures + BNB:  maker 0.018% / taker 0.045%  (BNB discount saves 10%)

eng = BacktestEngine(data=data, strategy=s,
                     cost_model=BINANCE_FUTURES_BNB,  # Use F4 preset
                     initial_cash=10000)
```

Custom fee parameters:
```python
custom_cost = BinanceCost(venue="spot", bnb_discount=True, slippage=0.001)
# slippage: additional slippage cost (0.1%)
```

### Intrabar execution (same-bar entry + exit)

`IntrabarExecution` allows entry and exit within the same bar (e.g., daily entry → hourly take-profit). Requires two timeframe data:

```python
from stockstat.backtest import Strategy, IntrabarMixin, IntrabarExecution, BinanceCost

class SimpleTP(Strategy, IntrabarMixin):
    """Market entry → intrabar scan TP limit → close fallback.

    Strategy logic:
    1. Market buy at daily open
    2. Set 1% take-profit limit order
    3. Scan hourly bars within the day for TP hit
    4. If not hit intrabar, close at market on bar close
    """
    def on_bar(self, ctx):
        o = ctx.current_price("BTC/USDT", "open")
        if o is None: return
        ctx.intrabar_submit(Order("BTC/USDT", "buy", 0.1, tag="entry"))
        ctx.history["tp_price"] = o * 1.01  # 1% take-profit

    def define_exits(self, entry_fill, ctx):
        """Define exit orders after entry."""
        tp = ctx.history.get("tp_price")
        if tp is None: return []
        return [
            # Take-profit limit order (priority=1, before stop-loss)
            Order("BTC/USDT", "sell", entry_fill.qty,
                  order_type="limit", limit_price=tp,
                  tag="tp", exit_reason="tp", priority=1),
            # Close fallback market order (priority=99, lowest)
            Order("BTC/USDT", "sell", entry_fill.qty,
                  order_type="market", tag="close",
                  exit_reason="close", priority=99),
        ]

data = {"BTC/USDT": {"1d": daily_df, "1h": hourly_df}}
res = BacktestEngine(
    data=data, strategy=SimpleTP(), initial_cash=10000,
    cost_model=BinanceCost(venue="spot"),
    execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),
).run()

print(res.exit_reason_stats())
# Output: statistics for each exit reason: tp / close counts and returns
```

### Batch backtest (multi-strategy × multi-fee)

`StrategyBatchRunner` runs multiple strategies × multiple fee models in parallel:

```python
from stockstat.backtest import StrategyBatchRunner

runner = StrategyBatchRunner(data=data, initial_cash=10000,
                             cost_model=BINANCE_SPOT, allow_short=True)
results = runner.run_all({"ma_cross": s1, "rsi": s2})
df = results.to_dataframe()       # Convert to DataFrame for comparison
ranked = results.rank("sharpe")   # Rank by Sharpe
print(ranked[["strategy", "sharpe", "max_drawdown", "win_rate"]])
```

### Subperiod & regime analysis

`BacktestAnalyzer` provides time-segmented and state-conditional analysis:

```python
from stockstat.backtest import BacktestAnalyzer
import pandas as pd

res = BacktestEngine(data=data, strategy=s, initial_cash=10000).run()

# Subperiod analysis: split backtest by dates, compare each segment
sub = BacktestAnalyzer.subperiod_metrics(
    res, split_dates=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-06-01")]
)
# Output: 2024H1 / 2024H2 each with Sharpe / drawdown / return

# Regime-conditional analysis: group by market state
reg = BacktestAnalyzer.regime_conditional_metrics(res, regime_series)
# regime_series: a Series labeling market state (e.g., "bull"/"bear"/"sideways")

# Exit reason analysis
exit_stats = res.exit_reason_stats()
# Output: tp / close / stop_loss each with count, avg return, win rate
```

### DCA benchmark & fee sweep

```python
from stockstat.backtest import dca_equity, fee_sweep, maker_taker_sweep

# DCA (Dollar Cost Averaging) benchmark: invest 10000/N per week
dca_eq = dca_equity(10000, prices, schedule="weekly")

# Fee sweep: test impact of different commission rates
sweep = fee_sweep(data=data, strategy=s, commissions=[0.0001, 0.0003, 0.0005])
# Output: Sharpe / return / drawdown for each commission rate

# Maker/Taker sweep: test different Maker/Taker combinations
mt = maker_taker_sweep(data=data, strategy=s,
                       maker_rates=[0.0002, 0.0005], taker_rates=[0.0005, 0.001])
```

---

## 10. Signal Processing & Nonlinear Dynamics

> Requires `pip install stockstat[signal_processing]` (installs PyWavelets). When not installed, CWT gracefully degrades to FFT-based Morlet (functional but slightly lower precision).

This module provides 8 advanced analysis functions covering signal processing and nonlinear dynamics, suitable for studying complex behavior of price series.

```python
import numpy as np

signal = data.close.values[-48:]  # Last 48 data points

# ── Signal Processing ──

# Continuous Wavelet Transform (CWT): decompose signal into time-frequency representation
coef, scales = client.compute.wavelet_decompose(signal, scales=np.arange(1, 25))
# coef shape: (24, 48), 24 scales × 48 time points
print(f"CWT coefficient shape: {coef.shape}")

# Spectral entropy: measures signal complexity in frequency domain (0=single freq, high=complex)
h_spec = client.compute.spectral_entropy(np.diff(np.log(signal)))
print(f"Spectral entropy: {h_spec:.4f}")

# Grey relational degree: measures shape similarity between two paths (0~1, 1=identical)
path_a = data.close.values[-48:]
path_b = data.close.values[-96:-48]
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)
print(f"Grey relational degree: {gr:.4f}")

# GM(1,1) grey prediction: short-term forecast with limited data
forecast = client.compute.gm11_predict(signal)
print(f"GM(1,1) next-step forecast: {forecast:.2f}")

# ── Nonlinear Dynamics ──

# Hurst exponent (DFA method): determines persistence of series
hurst = client.compute.hurst_dfa(np.diff(np.log(signal)))
print(f"Hurst exponent: {hurst:.4f}")
# ≈ 0.5: random walk (unpredictable)
# > 0.5: persistent (trends tend to continue)
# < 0.5: anti-persistent (trends tend to reverse)

# Transfer entropy: measures directed information flow X → Y (unit: bits)
btc_rets = np.diff(np.log(btc.close.values))[:200]
eth_rets = np.diff(np.log(eth.close.values))[:200]
te = client.compute.transfer_entropy(btc_rets, eth_rets, k=1)
print(f"TE(BTC→ETH): {te:.4f} bits")
# Higher value = stronger information flow from BTC to ETH

# Sample entropy: measures predictability of series (low = more predictable)
sampen = client.compute.sample_entropy(signal, m=2)
print(f"Sample entropy: {sampen:.4f}")

# Permutation entropy: complexity based on permutation patterns (unit: bits)
permen = client.compute.permutation_entropy(signal, m=3, tau=1)
print(f"Permutation entropy: {permen:.4f}")
```

### Visualization

3 PlotSpec factory functions return renderable PlotSpec:

```python
# CWT scalogram (time-frequency heatmap)
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
renderer = client.plot.get_renderer()
renderer.render(spec)
renderer.savefig("cwt_scalogram.png")

# DFA log-log fit plot (Hurst exponent)
spec = client.compute.dfa_fit(np.diff(np.log(signal)))
renderer.render(spec)
renderer.savefig("dfa_fit.png")
```

---

## 11. Result Export

```python
from stockstat.export.serializers import to_json, to_csv, to_dict

# DataFrame → JSON string (timestamps as ISO format)
json_str = to_json(data)

# DataFrame → CSV string
csv_str = to_csv(data)

# DataFrame → list of dicts (one dict per row)
records = to_dict(data)

# PlotSpec → dict (for web frontend rendering or serialization)
spec = client.plot.spec(title="My chart", series=[...])
payload = spec.to_dict()
```

---

## 12. v2.0 CLI

v2.0 adds the `stockstat` CLI tool for common operations without writing Python.

### Start API server

```bash
stockstat serve --host 0.0.0.0 --port 8000
```

### Ingest data from CLI

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

Output:
```json
{"symbol": "AAPL", "source": "yfinance", "ingested": 251}
```

### Query data

```bash
# Table format (default, for terminal)
stockstat query BTC/USDT --limit 5

# JSON format (for piping)
stockstat query BTC/USDT --format json

# CSV format (for file export)
stockstat query AAPL --start 2024-01-01 --format csv > aapl.csv
```

### List registered plugins

```bash
# All plugins (46 total)
stockstat plugins

# Filter by namespace
stockstat plugins --namespace indicators    # 23 indicators
stockstat plugins --namespace sources       # 4 data sources
stockstat plugins --namespace cost_models   # 8 cost models
```

Output example:
```
Namespace            Name                      Category
--------------------------------------------------------------------
sources              yfinance                  sources
sources              binance                   sources
indicators           ma                        trend
indicators           rsi                       oscillator
indicators           hurst_dfa                 nonlinear
cost_models          binance                   cost
renderers            matplotlib                renderers

Total: 46 plugin(s)
```

### List registered indicators

```bash
# All indicators
stockstat indicators

# Filter by category
stockstat indicators --category trend        # ma / ema / macd
stockstat indicators --category nonlinear    # wavelet_decompose / hurst_dfa / ...
```

---

## 13. Offline Mode

Offline mode requires no backend service — all computation runs locally. v2.1 supports four data acquisition methods:

### Option 1: Download from data sources (v2.1 new)

Download data directly via `PluginRegistry` adapters without starting the backend:

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage

client = V2Client(mode="offline", storage=MemoryStorage())

# Download directly from Binance, store in memory
result = client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
print(result)  # {'symbol': 'BTC/USDT', 'source': 'binance', 'ingested': 366}

# Query, compute, backtest all run locally
df = client.ohlcv("BTC/USDT")
ma = client.compute.ma(df.close, window=20)
```

> Offline `ingest()` data flow: `registry.get("sources", "binance")` → `adapter.fetch_ohlcv()` → normalize → `storage.upsert()`. Requires `ccxt` (crypto) or `requests` (yfinance) installed, or the `stockstat-backend` package. When backend not installed, auto-uses frontend-local adapters (`_LazySourcePlugin` lazy instantiation).

### Option 2: Read existing SQLite database file

Read database files created by the backend directly, without starting the backend service:

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import SQLStorage

# Read a database file created by the backend
client = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///stockstat.db"))
df = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
print(df[["close"]].head())

# Also works with absolute path
client = V2Client(mode="offline",
                  storage=SQLStorage(database_url="sqlite:////data/stockstat/stockstat.db"))
```

> `SQLStorage` delegates to `ohlcv_repo.query()` via `_compat.py`. When backend package is not installed, `_compat.py` auto-creates tables and queries with standalone SQLAlchemy.

### Option 3: Manually write data

For testing or importing data from other sources:

```python
import pandas as pd
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage
from stockstat._core.contracts import DataSchema, FieldDef

storage = MemoryStorage()
storage.register_schema("ohlcv", DataSchema(
    name="ohlcv",
    fields=[
        FieldDef("symbol", "str", nullable=False),
        FieldDef("ts", "datetime", nullable=False),
        FieldDef("open", "float"), FieldDef("high", "float"),
        FieldDef("low", "float"), FieldDef("close", "float"),
        FieldDef("volume", "float"),
    ],
    unique_constraints=[("symbol", "ts")],
))

storage.write("ohlcv", [
    {"symbol": "BTC", "ts": pd.Timestamp("2024-01-01", tz="UTC"),
     "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000},
    {"symbol": "BTC", "ts": pd.Timestamp("2024-01-02", tz="UTC"),
     "open": 102, "high": 106, "low": 101, "close": 104, "volume": 1200},
])

client = V2Client(mode="offline", storage=storage)
df = client.ohlcv("BTC")
print(df)
```

### Option 4: Download + persist to SQLite

Downloaded data persists to SQLite file, available on next startup:

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import SQLStorage

# Download and write to SQLite file (persisted)
client = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///my_data.db"))
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")

# Data persists across restarts (no re-download needed)
client2 = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///my_data.db"))
df = client2.ohlcv("AAPL")
print(f"AAPL: {len(df)} rows")
```

### Offline Mode Feature Comparison

| Feature | Online mode | Offline mode |
|---------|-------------|--------------|
| `ohlcv()` | HTTP → backend REST API | `storage.query()` local |
| `ingest()` | HTTP → backend ingestion | adapter → `fetch_ohlcv()` → `storage.upsert()` |
| `compute` | Backend-agnostic | Local `ComputeEngine` |
| `run_dsl()` | `DslEngine` (HTTP data fetch) | `DslEngine` (local Storage data fetch) |
| `backtest()` | Backend-agnostic | Local `BacktestEngine` |
| `plot` | Backend-agnostic | Local `PlotAPI` |

---

## 14. Plugin System

All extension points in v2.0 are registered to a unified `PluginRegistry` (46 built-in plugins across 6 namespaces).

### Register custom indicator

```python
from stockstat._domain.indicators import IndicatorPlugin
from stockstat._core.plugin import get_registry

reg = get_registry()

def rolling_max(x, window=10):
    """Rolling maximum."""
    return x.rolling(window).max()

plugin = IndicatorPlugin(
    name="rolling_max",
    func=rolling_max,
    category="custom",
    description="Rolling maximum",
)
reg.register("indicators", "rolling_max", plugin)

# Query
print(reg.get("indicators", "rolling_max"))
```

### DSL auto-reflection of new indicators

After registering, refresh DSL engine to make it available:

```python
from stockstat._api.dsl import DslEngine

engine = DslEngine(reg, client=mock_client)
engine.refresh()  # Reload function table from registry

# rolling_max is now DSL-available
result = engine.eval('''
    SELECT close, rolling_max(close, 5) AS rmax
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
```

### Register custom backtest component

```python
from stockstat._domain.backtest import BacktestComponentPlugin

# Custom cost model
class MyCostModel:
    def __init__(self, rate=0.001):
        self.rate = rate
    def compute(self, qty, price, side):
        return abs(qty * price * self.rate)

reg.register("cost_models", "my_cost",
    BacktestComponentPlugin("my_cost", MyCostModel, "cost",
                            description="Custom cost model"))
```

### List all plugins

```python
for item in reg.list():
    plugin = item["plugin"]
    print(f"{item['namespace']:<20} {item['name']:<25} {getattr(plugin, 'category', '')}")
```

### Theme system

```python
from stockstat._viz.themes import get_theme, register_theme, Theme, list_themes

# Built-in themes
print(list_themes())  # ['default', 'dark', 'publication']

dark = get_theme("dark")
print(dark.background)  # '#1e1e1e'

# Register custom theme
custom = Theme("ocean", background="#0a1929", primary="#64ffda",
               secondary="#ff6b6b", grid="#1c3a5e")
register_theme(custom)
print(get_theme("ocean").primary)  # '#64ffda'
```

---

## 15. Management Interfaces

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

```bash
# After starting backend, visit in browser:
# http://localhost:8000/admin/        (local)
# http://192.168.1.100:8000/admin/    (remote)
```

| Page | Function |
|------|----------|
| **Overview** | Symbol count, rows, disk, data coverage Gantt chart, recent ingests |
| **Source Browser** | Pagination + search + batch download + **manual symbol input** |
| **Local Symbols** | K-line chart (**lazy loading on zoom**) + range ingest + CSV export |
| **Config** | Database / proxy (live update) / cache / disk |
| **Logs** | Ingest history (paginated + filtered) |

### K-line chart lazy loading

After selecting a symbol:
1. **Initial load**: Auto-fetches 500 most recent bars (`order=desc&limit=500`)
2. **Scroll left**: When visible range exceeds loaded area, auto-fetches 1000 earlier bars (300ms debounce)
3. **Scroll right**: Auto-fetches 1000 later bars
4. **Deduplication**: Merges via `series.update()` by timestamp, no duplicate loads
5. **Progress display**: Bottom shows "Loaded: 2024-01-01 ~ 2024-06-30 (500 bars) | All: 2017-08-17 ~ 2024-07-18 (35%)"

### Download modal

Clicking "Download":
1. Calls `probe_range` to probe actual available time range (fetches first/last bars)
2. Shows "Probed / Estimated" badge
3. Pre-fills dates with max range (with `min`/`max` limits)
4. Timeframe dropdown dynamically generated based on source (Binance 16, yfinance 12, etc.)
5. Shows local existing data range + storage estimate hint ("1-minute granularity 1 year ≈ 15MB")

### Via Admin API

```bash
# Ingest
curl -X POST "http://localhost:8000/admin/api/ingest?symbol=BTC/USDT&source=binance&start=2024-01-01"

# Probe source range (measured)
curl "http://localhost:8000/admin/api/sources/binance/info?symbol=BTC/USDT&probe=true"
# Returns: earliest_available / latest_available / timeframes / local_earliest / local_latest

# View stats
curl http://localhost:8000/admin/api/stats
# {"total_symbols":5,"total_rows":1234,"symbols_by_source":{"binance":3,"yfinance":2}}

# Delete symbol
curl -X DELETE http://localhost:8000/admin/api/symbols/BTC/USDT
# {"deleted":true,"symbol":"BTC/USDT","rows_removed":366}
```

---

## 16. PAXG Weekend Correlation Analysis

### Analysis goal

Test the independent correlation between PAXG (gold-pegged token) weekend return (Friday close → Sunday close) and Monday's **max gain** and **max loss**:

- `max_gain = (high - open) / open` — intraday max upside (always positive)
- `max_loss = (low - open) / open` — intraday max downside (always negative)

"Independent" means analyzing gain and loss as two separate variables against weekend return, rather than combining into net change.

### Full analysis

```python
from scipy import stats
import pandas as pd

# Get PAXG daily data (needs 2022+ to cover multiple bull/bear cycles)
paxg = client.ohlcv("PAXG/USDT", start="2022-01-01", timeframe="1d")
df = paxg.copy()
df["weekday"] = df.index.weekday  # 0=Monday, 4=Friday, 6=Sunday

# Separate Friday, Sunday, Monday data
fridays = df[df.weekday == 4][["close"]]
sundays = df[df.weekday == 6][["close"]]
mondays = df[df.weekday == 0][["open", "high", "low", "close"]]

# Pair: for each Monday, find the preceding Friday and Sunday
pairs = []
for mon_date, mon_row in mondays.iterrows():
    prev_fri = fridays.loc[:mon_date].tail(1)  # Most recent Friday
    prev_sun = sundays.loc[:mon_date].tail(1)  # Most recent Sunday
    if len(prev_fri) > 0 and len(prev_sun) > 0:
        fri_c = prev_fri["close"].iloc[0]
        sun_c = prev_sun["close"].iloc[0]
        weekend_ret = (sun_c - fri_c) / fri_c           # Weekend return
        mon_open = mon_row["open"]
        max_gain = (mon_row["high"] - mon_open) / mon_open  # Monday max gain
        max_loss = (mon_row["low"] - mon_open) / mon_open    # Monday max loss
        pairs.append({"weekend_return": weekend_ret,
                       "max_gain": max_gain, "max_loss": max_loss})

result_df = pd.DataFrame(pairs)
r_gain = result_df["weekend_return"].corr(result_df["max_gain"])
r_loss = result_df["weekend_return"].corr(result_df["max_loss"])

print(f"Samples: {len(result_df)}")
print(f"r(gain): {r_gain:.4f}")
print(f"r(loss): {r_loss:.4f}")
```

**Expected result**:
```
Samples: 156
r(gain): 0.2303, p=0.0038
r(loss): -0.2004, p=0.0121
```

**Interpretation**: Weekend return is positively correlated with Monday max gain (r=0.23, p<0.01) and negatively correlated with Monday max loss (r=-0.20, p<0.05). Both are statistically significant but weak, indicating that weekend return has modest independent predictive power for Monday's direction — positive weekend → Monday more likely to rise (larger gain), negative weekend → Monday more likely to fall (larger loss).

### Scatter plot

![PAXG Weekend Scatter](images/paxg_weekend_scatter.png)

### Directional distribution

![PAXG Directional](images/paxg_directional.png)

---

## Appendix: Environment Variables

### Backend

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database URL |
| `REDIS_URL` | (empty) | Redis connection (optional) |
| `HOST` | `0.0.0.0` | Backend listen address |
| `PORT` | `8000` | Backend listen port |
| `STOCKSTAT_DEFAULT_SOURCE` | `yfinance` | Default data source |
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` or `socks5` |
| `STOCKSTAT_PROXY_URL` | auto | Proxy URL |
| `STOCKSTAT_ADMIN_ENABLED` | `true` | Enable web admin interface |

### Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCKSTAT_HOST` | `localhost` | Frontend host |
| `STOCKSTAT_PORT` | `8000` | Frontend port |
| `STOCKSTAT_API_KEY` | (empty) | Optional API key |
| `STOCKSTAT_TIMEOUT` | `30` | HTTP timeout in seconds |
| `STOCKSTAT_USE_HTTPS` | `false` | Whether to use HTTPS |

---

## 17. Connection & Performance Tests

Two test scripts are included for verifying frontend-backend communication and measuring performance. Located in `tests/`.

### 17.1 Connection Test (`tests/test_connection.py`)

End-to-end test against a remote backend: health check -> ingest data -> query -> compute indicators -> DSL query -> backtest -> visualization. Each step outputs ✓/✗ result and timing.

```bash
# Default: localhost:8000
python tests/test_connection.py

# Specify remote backend
python tests/test_connection.py --host 192.168.1.100 --port 8000

# Use HTTPS
python tests/test_connection.py --host example.com --port 443 --https
```

Test flow (7 steps):

| Step | Test | Verification |
|------|------|-------------|
| 1. Health check | `GET /api/v1/health` | Backend online, proxy status, latency |
| 2. Ingest data | `ingest AAPL + BTC/USDT + ETH/USDT` | Data source reachable, row counts |
| 3. Query data | `ohlcv()` + `order=desc` + `symbols()` | DataFrame returned, bidirectional pagination |
| 4. Compute indicators | MA / RSI / Bollinger / Sharpe / Max Drawdown | Indicator computation correct |
| 5. DSL query | `run_dsl()` multi-column + indicators | DSL engine working |
| 6. Backtest | Dual MA strategy + `client.backtest()` | Backtest complete, metrics output |
| 7. Visualization | `res.render()` generates PNG | matplotlib rendering (optional) |

Output example:
```
ℹ 1. Connect + Health Check
  ✓ Backend online (health check latency: 2.1 ms)
  ✓ Available sources: ['yfinance', 'binance', 'coinbase', 'synthetic']

ℹ 2. Ingest data
  ✓ AAPL daily: 251 rows (took 3112 ms)
  ✓ BTC/USDT daily: 366 rows (took 5615 ms)

ℹ 6. Backtest (Dual MA strategy)
  ✓ Backtest complete (took 303 ms)
       Total return:  21.78%
       Sharpe:        0.2838
       Max drawdown:  -22.64%
```

### 17.2 Performance Test (`tests/test_perf.py`)

Measures communication latency, transfer speed, and jitter between frontend and backend. Suitable for evaluating network quality of remote deployments.

```bash
# Default: localhost:8000, 20 rounds
python tests/test_perf.py

# Specify remote backend, 5 rounds (reduce test time)
python tests/test_perf.py --host 192.168.1.100 --port 8000 --rounds 5

# Specify test symbol and timeframe (data must be pre-ingested)
python tests/test_perf.py --symbol BTC/USDT --timeframe 1h --rounds 10
```

Test items (8 items):

| Test | Description |
|------|-------------|
| 1. Health check RTT | Round-trip latency of `GET /api/v1/health`, multiple measurements with min/mean/median/p95/max |
| 2. Empty query latency | Query non-existent symbol (404 response), measures backend empty request handling |
| 3. Query latency vs data size | 1 / 10 / 100 / 500 / 1000 / 5000 / 10000 rows query latency + transfer size + transfer speed |
| 4. order param comparison | `order=asc` vs `order=desc` (same row count), verifies bidirectional pagination performance |
| 5. Symbol list query | `GET /api/v1/symbols` latency |
| 6. Ingest latency | `POST /api/v1/ingest` (includes network download + storage, not pure communication) |
| 7. Continuous jitter | 50 rapid queries latency distribution (histogram + jitter stdev) |
| 8. Raw HTTP latency | `httpx.get` direct (bypasses frontend library), measures pure TCP+HTTP overhead |

Output example:
```
3. Query latency vs data size (BTC/USDT 1h)

  Query                          min       mean     median      p95       max       Size      Speed
  limit=1                     2.0 ms     2.1 ms     2.0 ms     2.3 ms    2.3 ms     129 B     63 KB/s
  limit=100                   2.5 ms     2.7 ms     2.6 ms     3.0 ms    3.0 ms    12.7 KB   4.8 MB/s
  limit=1000                  5.1 ms     5.5 ms     5.4 ms     6.2 ms    6.2 ms   127.5 KB  23.5 MB/s
  limit=10000                28.3 ms    29.5 ms    29.0 ms    32.1 ms   32.1 ms    1.24 MB  42.3 MB/s

7. Continuous jitter (50 rapid queries, limit=10)
  Latency distribution:
        <5ms:  48 ( 96.0%) ████████████████████████████████████████████████
      5-10ms:   2 (  4.0%) █

  Assessment: 🟢 Extremely low latency, suitable for local development
```

### 17.3 Performance Tips

**Connection pooling**: By default, `StockStatClient` creates a new TCP connection per request. For high-frequency query scenarios (e.g., K-line chart lazy loading, batch backtesting), pass `httpx.Client()` to enable connection pooling and drastically reduce latency:

```python
import httpx
from stockstat import StockStatClient

# Default: new TCP connection per request (suitable for low-frequency use)
client = StockStatClient(host="192.168.1.100", port=8000)

# Optimized: pass httpx.Client for connection pooling (suitable for high-frequency queries)
with httpx.Client() as pool:
    client = StockStatClient(host="192.168.1.100", port=8000, http_client=pool)
    # All subsequent client.ohlcv() / client.ingest() reuse the same TCP connection
    for _ in range(100):
        client.ohlcv("BTC/USDT", limit=100)  # ~1ms per request after first
```

| Mode | First request | Subsequent | Use case |
|------|--------------|-----------|----------|
| Default (no pool) | ~2000ms (includes TCP setup) | ~2000ms (new each time) | Low-frequency scripts, one-off queries |
| Connection pool (`http_client`) | ~2000ms (includes TCP setup) | **~1ms** (reused) | K-line lazy loading, batch backtesting, high-frequency |

> **Windows `localhost` note**: On Windows, `localhost` may try IPv6 (`::1`) first then fall back to IPv4, causing ~2s TCP connection delay. Use `127.0.0.1` or connection pooling to avoid this.

---

## 18. Startup Scripts

The backend provides two types of startup scripts, located in `backend/`.

### 18.1 Minimal Startup Scripts (`start.bat` / `start.sh`)

Directly sets environment variables and starts the server. Each env var occupies one line with an inline comment. Suitable for quick startup or deployment after editing parameters:

```bash
# Windows
backend\start.bat

# Linux/macOS
backend/start.sh
```

Script content (using `start.sh` as example):
```bash
export HOST="0.0.0.0"                              # Listen address
export PORT="8000"                                 # Listen port
export DATABASE_URL="sqlite:///stockstat.db"       # SQLite file
export STOCKSTAT_PROXY_ENABLED="false"             # Enable proxy
export STOCKSTAT_ADMIN_ENABLED="true"              # Web admin UI
python3 -m uvicorn stockstat_backend.app:app --host "$HOST" --port "$PORT"
```

Edit the corresponding line values to customize configuration.

### 18.2 Full Configuration Scripts (`serve.bat` / `serve.sh`)

Supports CLI arguments and interactive configuration. Suitable for first-time deployment or when flexible configuration is needed:

```bash
# Interactive configuration (guided setup for database/proxy/admin/reload)
backend/serve.bat --config       # Windows
backend/serve.sh --config        # Linux/macOS

# Specify parameters via CLI
backend/serve.bat --host 0.0.0.0 --port 9000
backend/serve.sh --db-url "sqlite:////data/stockstat.db"
backend/serve.bat --proxy http http://127.0.0.1:8889
backend/serve.sh --no-admin --reload
```

Supported parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--host` | Listen address | `0.0.0.0` |
| `--port` | Listen port | `8000` |
| `--db-url` | Database connection string | `sqlite:///stockstat.db` |
| `--redis-url` | Redis connection (optional) | (empty) |
| `--proxy <type> <url>` | Enable proxy | disabled |
| `--no-admin` | Disable web admin UI | enabled |
| `--reload` | Hot reload (dev mode) | disabled |
| `--config` | Interactive configuration | skipped |
