# StockStat — Programmable Financial Instrument Statistical Computing Platform

A user-programmable stock/cryptocurrency statistical computing platform with separated storage backend and computation frontend.

## Quick Start

### Option A: Local development (SQLite, no Docker)

```bash
# 1. Install backend
cd backend
pip install -e .

# 2. (Optional) Enable proxy for real data sources
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889

# 3. Start the API server
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000

# 4. Install frontend library (in another terminal)
cd frontend
pip install -e .
```

### Option B: Docker (production)

```bash
docker compose up -d
# API available at http://localhost:8000
```

## Proxy Configuration

The backend supports HTTP/SOCKS5 proxies for accessing real data sources. **Disabled by default**.

| Env Var | Default | Description |
|---------|---------|-------------|
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
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

# Stock data via Yahoo Finance
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
client.ingest("^GSPC", source="yfinance", start="2023-01-01", end="2024-12-31")

# Crypto data via Binance
client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
client.ingest("ETH/USDT", source="binance", start="2024-01-01", end="2024-12-31")
client.ingest("PAXG/USDT", source="binance", start="2022-01-01", end="2024-12-31")

# Auto-detect source (yfinance for stocks, binance for crypto)
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

### 4. DSL mode

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')
```

## Visualization with Matplotlib

The core library has **zero hard-dependency** on matplotlib. Install it optionally:

```bash
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

## Data Sources

| Source | Type | Network | Total Symbols | Description |
|--------|------|---------|---------------|-------------|
| `yfinance` | stock | Yes | On-demand | Yahoo Finance direct API; user provides any ticker (AAPL, MSFT, ^GSPC, ...) |
| `binance` | crypto | Yes | 4,498 (1,479 USDT pairs) | Binance via ccxt |
| `coinbase` | crypto | Yes | 1,183 (528 USD pairs) | Coinbase via ccxt |
| `synthetic` | mixed | No | — | Synthetic data for offline testing |

### Data Size Estimates

| Scope | Timeframe | Rows (1 year) | Storage |
|-------|-----------|---------------|---------|
| 1 symbol | daily | ~250 | ~2 KB |
| 1 symbol | 1-minute | ~525,000 | ~15 MB |
| Binance USDT pairs (1,479) | daily | ~370,000 | ~3 MB |
| Binance USDT pairs (1,479) | 1-minute | ~776M | ~22 GB |
| Coinbase USD pairs (528) | daily | ~132,000 | ~1 MB |
| Coinbase USD pairs (528) | 1-minute | ~277M | ~8 GB |

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check (includes proxy status) |
| `/api/v1/proxy` | GET | Get proxy configuration |
| `/api/v1/sources` | GET | List data sources |
| `/api/v1/ingest` | POST | Ingest data for a symbol |
| `/api/v1/ohlcv` | GET | Query OHLCV data (json/csv) |
| `/api/v1/symbols` | GET | List registered symbols |

## Running Tests

```bash
# Backend tests (real data via proxy)
cd backend && python -m pytest tests/test_backend.py -v

# Frontend unit tests (indicators, DSL, visualization)
cd frontend && python -m pytest tests/test_frontend.py -v

# Integration tests (real data: classic stats + PAXG weekend correlation)
cd frontend && python -m pytest tests/test_integration.py -v -s

# Matplotlib chart tests (generates images to docs/images/)
cd frontend && python -m pytest tests/test_matplotlib_charts.py -v
```

## Available Indicators

| Category | Function | Description |
|----------|----------|-------------|
| Trend | `ma(x, window)` | Simple moving average |
| | `ema(x, window)` | Exponential moving average |
| | `macd(x, fast, slow, signal)` | MACD (returns 3 series) |
| Oscillator | `rsi(x, window)` | Relative Strength Index |
| | `kdj(high, low, close, window)` | KDJ indicator (returns 3 series) |
| Volatility | `std(x, window)` | Rolling standard deviation |
| | `atr(high, low, close, window)` | Average True Range |
| | `bollinger(x, window, k)` | Bollinger Bands (returns 3 series) |
| Statistics | `corr(x, y)` | Pearson correlation |
| | `beta(asset, benchmark, window)` | Rolling Beta |
| | `sharpe(returns, risk_free, annualize)` | Sharpe ratio |
| | `max_drawdown(close)` | Maximum drawdown |
| | `var(returns, confidence)` | Historical VaR |
| Transform | `returns(x)` | Percentage returns |
| | `log_returns(x)` | Log returns |

## Documentation

- [Usage Guide](docs/USAGE.md) — detailed examples with expected results
- [Design Report](docs/DESIGN.md) — full architecture design
- [Test Report](reports/TEST_REPORT.md) — test results

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database connection string |
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` or `socks5` |
| `STOCKSTAT_PROXY_URL` | auto | Proxy URL |
| `STOCKSTAT_HOST` | `localhost` | Frontend default host |
| `STOCKSTAT_PORT` | `8000` | Frontend default port |

---

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file for details.

Copyright (C) 2026 RESBI

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

---

## Acknowledgements

This project — including all source code, documentation, tests, and charts — was entirely designed, implemented, and documented by **GLM-5.2**, an AI assistant.

All code was generated through iterative conversation with the user, verified by automated test suites, and validated against real market data (Yahoo Finance + Binance).

---

## Disclaimer

This software is provided for **educational and research purposes only**. It is **not** financial, investment, or trading advice.

- The authors and contributors of this project are **not** financial advisors and do not accept any liability for financial losses or damages arising from the use of this software.
- All statistical analyses, indicators, and correlations (including the PAXG weekend effect) are based on historical data and do **not** guarantee future results.
- Users are solely responsible for their own investment decisions and should consult a qualified financial professional before making any investment.
- The software may contain bugs or inaccuracies. Use at your own risk.
- Market data is obtained from third-party sources (Yahoo Finance, Binance) and their accuracy or availability is not guaranteed.

**THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.**
