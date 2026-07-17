# StockStat Usage Guide

> All examples in this document were tested locally with real market data (Yahoo Finance + Binance, via proxy). Expected results are from an actual test run on 2026-07-18.

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Data Ingestion](#2-data-ingestion)
3. [Querying OHLCV Data](#3-querying-ohlcv-data)
4. [Trend Indicators (MA / EMA / MACD)](#4-trend-indicators)
5. [Oscillators (RSI / KDJ)](#5-oscillators)
6. [Volatility Indicators (Bollinger / ATR / STD)](#6-volatility-indicators)
7. [Statistical Indicators (Beta / Sharpe / Drawdown / Correlation)](#7-statistical-indicators)
8. [DSL Queries](#8-dsl-queries)
9. [Custom Indicators](#9-custom-indicators)
10. [Matplotlib Visualization](#10-matplotlib-visualization)
11. [PAXG Weekend Correlation Analysis](#11-paxg-weekend-correlation-analysis)
12. [Result Export](#12-result-export)
13. [Backtesting](#13-backtesting)
14. [Advanced Backtest Features](#14-advanced-backtest-features)
15. [Backtest Visualization](#15-backtest-visualization)
16. [Signal Processing & Nonlinear Dynamics](#16-signal-processing--nonlinear-dynamics)
17. [v2.0 CLI](#17-v20-cli)
18. [v2.0 Offline Mode](#18-v20-offline-mode)
19. [v2.0 Plugin System](#19-v20-plugin-system)

---

## 1. Environment Setup

### Installation

```bash
# Backend
cd backend && pip install -e .

# Frontend core library
cd frontend && pip install -e .

# Optional extras
pip install -e "frontend/[matplotlib]"          # Visualization
pip install -e "frontend/[dsl]"                 # DSL parser (lark)
pip install -e "frontend/[signal_processing]"   # Wavelets (PyWavelets)
pip install -e "frontend/[backtest_full]"       # Full backtest suite (matplotlib + optuna)
```

### Enable a proxy (to access real data)

```bash
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889
```

### Start the backend

```bash
# Option 1: uvicorn direct
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000

# Option 2: v2.0 CLI (equivalent)
stockstat serve --host 0.0.0.0 --port 8000
```

### Frontend connection

```python
from stockstat import StockStatClient

# Style 1: direct configuration (most common)
client = StockStatClient(host="localhost", port=8000)

# Style 2: environment variables
client = StockStatClient.from_env()

# Style 3: dict configuration
client = StockStatClient.from_dict({"host": "localhost", "port": 8000})

# Style 4: connect to a remote storage server
client = StockStatClient(host="192.168.1.100", port=8000)
```

---

## 2. Data Ingestion

### Example 2.1: Ingest stock data

```python
result = client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
print(result)
```

**Expected result**:
```python
{'symbol': 'AAPL', 'source': 'yfinance', 'ingested': 251}
```

### Example 2.2: Ingest crypto data

```python
result = client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
print(result)
```

**Expected result**:
```python
{'symbol': 'BTC/USDT', 'source': 'binance', 'ingested': 366}
```

### Example 2.3: Auto-detect the data source

```python
# Stock symbols (no "/") → yfinance; crypto symbols (with "/") → binance
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")
client.ingest("ETH/USDT", start="2024-01-01", end="2024-12-31")
```

### Example 2.4: Ingest via CLI (v2.0 new)

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --end 2024-12-31
```

### Example 2.5: Batch-ingest symbols for analysis

```python
symbols = [
    ("AAPL", "yfinance", "2023-01-01", "2024-12-31"),
    ("^GSPC", "yfinance", "2023-01-01", "2024-12-31"),
    ("BTC/USDT", "binance", "2024-01-01", "2024-12-31"),
    ("ETH/USDT", "binance", "2024-01-01", "2024-12-31"),
    ("PAXG/USDT", "binance", "2022-01-01", "2024-12-31"),
]
for sym, source, start, end in symbols:
    client.ingest(sym, source=source, start=start, end=end)
```

---

## 3. Querying OHLCV Data

### Example 3.1: Query as a DataFrame

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

### Example 3.2: Batch query

```python
batch = client.ohlcv_batch(["BTC/USDT", "ETH/USDT"], start="2024-01-01")
btc = batch["BTC/USDT"]
eth = batch["ETH/USDT"]
```

### Example 3.3: List registered symbols

```python
symbols = client.symbols()
for s in symbols:
    print(f"{s['unified_symbol']:15s} {s['asset_type']:8s} {s['sources']}")
```

### Example 3.4: Query via CLI (v2.0 new)

```bash
stockstat query BTC/USDT --limit 5
stockstat query AAPL --start 2024-01-01 --format csv
```

---

## 4. Trend Indicators

### Example 4.1: Simple Moving Average (MA)

```python
ma20 = client.compute.ma(data.close, window=20)
print(f"MA(20) latest: {ma20.iloc[-1]:.2f}")
```

### Example 4.2: Exponential Moving Average (EMA)

```python
ema12 = client.compute.ema(data.close, window=12)
```

### Example 4.3: Golden / death cross

```python
ma_short = data.close.rolling(5).mean()
ma_long = data.close.rolling(20).mean()

golden_cross = (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
death_cross = (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))

print(f"Golden crosses: {golden_cross.sum()}")
print(f"Death crosses: {death_cross.sum()}")
```

### Example 4.4: MACD

```python
btc = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
macd_line, signal_line, hist = client.compute.macd(btc.close)
print(f"MACD line: {macd_line.iloc[-1]:.2f}")
print(f"Signal line: {signal_line.iloc[-1]:.2f}")
print(f"Histogram: {hist.iloc[-1]:.2f}")
```

---

## 5. Oscillators

### Example 5.1: RSI

```python
rsi = client.compute.rsi(btc.close, window=14)
print(f"RSI last 5 days:\n{rsi.tail(5).round(2)}")
print(f"Overbought days (>70): {(rsi > 70).sum()}")
print(f"Oversold days (<30): {(rsi < 30).sum()}")
```

### Example 5.2: KDJ

```python
k, d, j = client.compute.kdj(btc.high, btc.low, btc.close, window=9)
print(f"K: {k.iloc[-1]:.2f}, D: {d.iloc[-1]:.2f}, J: {j.iloc[-1]:.2f}")
```

---

## 6. Volatility Indicators

### Example 6.1: Bollinger Bands

```python
upper, mid, lower = client.compute.bollinger(btc.close, window=20, k=2.0)
print(f"Upper: {upper.iloc[-1]:.2f}")
print(f"Middle: {mid.iloc[-1]:.2f}")
print(f"Lower: {lower.iloc[-1]:.2f}")
```

### Example 6.2: ATR

```python
atr = client.compute.atr(btc.high, btc.low, btc.close, window=14)
print(f"ATR(14): {atr.iloc[-1]:.2f}")
```

### Example 6.3: Rolling standard deviation

```python
std = client.compute.std(btc.close, window=20)
print(f"20-day volatility: {std.iloc[-1]:.2f}")
```

---

## 7. Statistical Indicators

### Example 7.1: Beta

```python
stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")
beta = client.compute.beta(stock.close.pct_change(), market.close.pct_change(), window=60)
print(f"Beta (60-day) mean: {beta.dropna().mean():.4f}")
```

### Example 7.2: Sharpe ratio

```python
rets = client.compute.returns(btc.close).dropna()
sharpe = client.compute.sharpe(rets, risk_free=0.02, annualize=True)
print(f"BTC Sharpe ratio (annualized): {sharpe:.4f}")
```

### Example 7.3: Maximum drawdown

```python
dd = client.compute.max_drawdown(btc.close)
print(f"BTC max drawdown: {dd:.4f} ({dd*100:.2f}%)")
```

### Example 7.4: Cross-asset correlation

```python
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
corr = btc.close.pct_change().corr(eth.close.pct_change())
print(f"BTC/ETH daily-return correlation: {corr:.4f}")
```

### Example 7.5: Value at Risk (VaR)

```python
var_95 = client.compute.var(rets, confidence=0.95)
print(f"95% VaR (daily): {var_95:.4f} ({var_95*100:.2f}%)")
```

---

## 8. DSL Queries

> The DSL is based on lark and requires `pip install stockstat[dsl]`. v2.0's `DslEngine` auto-reflects all registered indicators from the PluginRegistry.

### Example 8.1: Basic DSL query

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20
    FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
print(result)
```

### Example 8.2: DSL query for RSI

```python
result = client.run_dsl('''
    SELECT rsi(close, 14) AS rsi_val
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 10
''')
```

### Example 8.3: DSL with a WHERE filter

```python
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

### Example 8.4: DSL with keyword arguments

```python
result = client.run_dsl('''
    SELECT close, ma(close, window=20) AS ma20
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
```

---

## 9. Custom Indicators

### Example 9.1: Register a custom indicator

```python
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, high_threshold=0.04):
    ret = data.close.pct_change()
    vol = ret.rolling(window).std()
    regime = vol.apply(lambda v: "high" if v > high_threshold else "low")
    return {"regime": regime, "volatility": vol}

result = client.compute.call("volatility_regime", data=btc)
```

### Example 9.2: Register via v2.0 IndicatorPlugin (auto DSL-available)

```python
from stockstat._domain.indicators import IndicatorPlugin
from stockstat._core.plugin import get_registry

reg = get_registry()

def my_indicator(x, window=10):
    """Custom rolling maximum."""
    return x.rolling(window).max()

reg.register("indicators", "rolling_max",
    IndicatorPlugin("rolling_max", my_indicator, "custom",
                    description="Rolling maximum"))
# After registration, DSL auto-available (call DslEngine.refresh())
```

---

## 10. Matplotlib Visualization

### Example 10.1: Protocol-based plotting

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
renderer = client.plot.get_renderer("matplotlib")
fig = renderer.render(spec)
renderer.savefig("btc.png")
```

### Example 10.2: Use matplotlib directly

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(btc.index, btc.close, label="Close", color="black")
upper, mid, lower = client.compute.bollinger(btc.close, 20, 2.0)
ax.fill_between(btc.index, lower, upper, alpha=0.15, color="blue", label="Bollinger")
ax.set_title("BTC/USDT Bollinger Bands")
ax.legend()
plt.savefig("btc_bollinger.png", dpi=150)
```

![BTC Bollinger](images/btc_bollinger.png)

### Example 10.3: RSI chart

![BTC RSI](images/btc_rsi.png)

### Example 10.4: MACD chart

![ETH MACD](images/eth_macd.png)

### Example 10.5: Drawdown chart

![BTC Drawdown](images/btc_drawdown.png)

### Example 10.6: Beta scatter

![AAPL Beta](images/aapl_beta_scatter.png)

### Example 10.7: Price comparison

![Price Comparison](images/price_comparison.png)

### Example 10.8: NullRenderer (without matplotlib)

```python
renderer = client.plot.get_renderer("null")
spec = client.plot.spec(title="Test", series=[{"name": "x", "data": btc.close}])
renderer.render(spec)  # UserWarning: No plotting backend available
```

---

## 11. PAXG Weekend Correlation Analysis

### Analysis goal

Test the independent correlation between PAXG (gold-pegged token) weekend return (Friday close → Sunday close) and Monday's **max gain** and **max loss**:

- `max_gain = (high - open) / open` — intraday max upside (always positive)
- `max_loss = (low - open) / open` — intraday max downside (always negative)

### Example 11.1: Full analysis

```python
from scipy import stats
import pandas as pd

paxg = client.ohlcv("PAXG/USDT", start="2022-01-01", timeframe="1d")
df = paxg.copy()
df["weekday"] = df.index.weekday

fridays = df[df.weekday == 4][["close"]]
sundays = df[df.weekday == 6][["close"]]
mondays = df[df.weekday == 0][["open", "high", "low", "close"]]

pairs = []
for mon_date, mon_row in mondays.iterrows():
    prev_fri = fridays.loc[:mon_date].tail(1)
    prev_sun = sundays.loc[:mon_date].tail(1)
    if len(prev_fri) > 0 and len(prev_sun) > 0:
        fri_c = prev_fri["close"].iloc[0]
        sun_c = prev_sun["close"].iloc[0]
        weekend_ret = (sun_c - fri_c) / fri_c
        mon_open = mon_row["open"]
        max_gain = (mon_row["high"] - mon_open) / mon_open
        max_loss = (mon_row["low"] - mon_open) / mon_open
        pairs.append({"weekend_return": weekend_ret, "max_gain": max_gain, "max_loss": max_loss})

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

### Example 11.2: Scatter plot

![PAXG Weekend Scatter](images/paxg_weekend_scatter.png)

### Example 11.3: Directional distribution

![PAXG Directional](images/paxg_directional.png)

---

## 12. Result Export

```python
from stockstat.export.serializers import to_json, to_csv, to_dict

json_str = to_json(data)       # DataFrame → JSON string
csv_str = to_csv(data)         # DataFrame → CSV string
records = to_dict(data)        # DataFrame → list of dicts

# PlotSpec → dict (for web frontends)
spec = client.plot.spec(title="My chart", series=[...])
payload = spec.to_dict()
```

---

## 13. Backtesting

### Example 13.1: Minimal backtest (function-style strategy)

```python
from stockstat import StockStatClient
from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost

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
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1, tag="entry"))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty, tag="exit"))

eng = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, cost_model=ZeroCost(),
                     benchmark="BTC/USDT")
res = eng.run()
print(res.summary())
```

### Example 13.2: Via client convenience entry

```python
res = client.backtest(data, ma_cross, initial_cash=10000, benchmark="BTC/USDT")
# Auto-injects ComputeEngine; ctx.compute has all indicators inside the strategy
```

### Example 13.3: Class-style strategy + hooks

```python
from stockstat.backtest import Strategy, Order

class RSIStrategy(Strategy):
    def on_start(self, ctx):
        ctx.history["trade_count"] = 0

    def on_bar(self, ctx):
        d = ctx.get("BTC/USDT", "1d", lookback=30)
        if len(d) < 15:
            return
        r = ctx.compute.rsi(d.close, window=14).iloc[-1]
        pos = ctx.portfolio.get_position("BTC/USDT")
        if r < 30 and pos.qty == 0:
            ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
            ctx.history["trade_count"] += 1
        elif r > 70 and pos.qty > 0:
            ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

    def on_fill(self, fill, ctx):
        print(f"Fill {fill.side.value} {fill.qty} @ {fill.price:.2f}")
```

### Example 13.4: Multi-asset pair trading + short selling

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
    if len(btc) < 40:
        return
    spread = np.log(btc.close) - np.log(eth.close)
    z = (spread - spread.rolling(20).mean()) / spread.rolling(20).std()
    last = z.iloc[-1]
    if np.isnan(last):
        return
    pb = ctx.portfolio.get_position("BTC/USDT")
    if last > 1.5 and pb.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", 0.1))
        ctx.broker.submit(Order("ETH/USDT", "buy", 0.1))
    elif last < -1.5 and pb.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
        ctx.broker.submit(Order("ETH/USDT", "sell", 0.1))

res = BacktestEngine(data=data, strategy=pair,
                     initial_cash=10000, allow_short=True).run()
```

### Example 13.5: Multi-timeframe resonance

```python
hourly = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1h")
daily  = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
data = {"BTC/USDT": {"1h": hourly, "1d": daily}}

@strategy
def multi_tf(ctx):
    h = ctx.get("BTC/USDT", "1h", lookback=50)
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21 or len(h) < 2:
        return
    trend_up = d.close.iloc[-1] > d.close.rolling(20).mean().iloc[-1]
    breakout = h.close.iloc[-1] > h.close.iloc[-2]
    pos = ctx.portfolio.get_position("BTC/USDT")
    if trend_up and breakout and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif not trend_up and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

res = BacktestEngine(data=data, strategy=multi_tf).run()
```

### Example 13.6: Parameter grid search

```python
from stockstat.backtest.optimizer import grid_search

def make_engine(params):
    @strategy
    def s(ctx):
        d = ctx.get("BTC/USDT", "1d", lookback=params["long"]+5)
        if len(d) < params["long"]+1:
            return
        ma_s = d.close.rolling(params["short"]).mean().iloc[-1]
        ma_l = d.close.rolling(params["long"]).mean().iloc[-1]
        pos = ctx.portfolio.get_position("BTC/USDT")
        if ma_s > ma_l and pos.qty == 0:
            ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
        elif ma_s < ma_l and pos.qty > 0:
            ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))
    return BacktestEngine(data=data, strategy=s, initial_cash=10000)

results = grid_search(make_engine,
                      {"short": [3, 5, 8], "long": [10, 20, 30]},
                      metric="sharpe")
best_params, best_val, best_res = results[0]
print(f"Best params: {best_params}, Sharpe: {best_val:.3f}")
```

---

## 14. Advanced Backtest Features

### Example 14.1: Binance fee models (4 presets)

```python
from stockstat.backtest import BinanceCost, BINANCE_SPOT, BINANCE_SPOT_BNB, \
    BINANCE_FUTURES, BINANCE_FUTURES_BNB, MakerTakerCost

# F1 Spot no BNB:  maker 0.100% / taker 0.100%
# F2 Spot + BNB:   maker 0.075% / taker 0.075%  (−25%)
# F3 Futures no BNB: maker 0.020% / taker 0.050%
# F4 Futures + BNB:  maker 0.018% / taker 0.045%  (−10%)

eng = BacktestEngine(data=data, strategy=s,
                     cost_model=BINANCE_FUTURES_BNB, initial_cash=10000)
```

### Example 14.2: Intrabar execution (same-bar entry + exit)

```python
from stockstat.backtest import (
    BacktestEngine, Strategy, IntrabarMixin, Order,
    IntrabarExecution, BinanceCost,
)

class SimpleTP(Strategy, IntrabarMixin):
    """Market entry → intrabar scan TP limit → close fallback."""
    def on_bar(self, ctx):
        o = ctx.current_price("BTC/USDT", "open")
        if o is None:
            return
        ctx.intrabar_submit(Order("BTC/USDT", "buy", 0.1, tag="entry"))
        ctx.history["tp_price"] = o * 1.01  # 1% take-profit

    def define_exits(self, entry_fill, ctx):
        tp = ctx.history.get("tp_price")
        if tp is None:
            return []
        return [
            Order("BTC/USDT", "sell", entry_fill.qty,
                  order_type="limit", limit_price=tp,
                  tag="tp", exit_reason="tp", priority=1),
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
```

### Example 14.3: Batch backtest (multi-strategy × multi-fee)

```python
from stockstat.backtest import StrategyBatchRunner

runner = StrategyBatchRunner(data=data, initial_cash=10000,
                             cost_model=BINANCE_SPOT, allow_short=True)
results = runner.run_all({"ma_cross": s1, "rsi": s2})
df = results.to_dataframe()
ranked = results.rank("sharpe")
```

### Example 14.4: Subperiod & regime analysis

```python
from stockstat.backtest import BacktestAnalyzer
import pandas as pd

res = BacktestEngine(data=data, strategy=s, initial_cash=10000).run()

# Subperiod analysis
sub = BacktestAnalyzer.subperiod_metrics(
    res, split_dates=[pd.Timestamp("2024-01-01")]
)

# Regime-conditional analysis
reg = BacktestAnalyzer.regime_conditional_metrics(res, regime_series)

# Analysis by exit reason
exit_stats = res.exit_reason_stats()
```

### Example 14.5: DCA benchmark & fee sweep

```python
from stockstat.backtest import dca_equity, fee_sweep, maker_taker_sweep

dca_eq = dca_equity(10000, prices, schedule="weekly")
sweep = fee_sweep(data=data, strategy=s, commissions=[0.0001, 0.0003, 0.0005])
mt = maker_taker_sweep(data=data, strategy=s,
                       maker_rates=[0.0002, 0.0005], taker_rates=[0.0005, 0.001])
```

---

## 15. Backtest Visualization

```python
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

# One-liner render
res.render("equity_curve", path="equity.png")
res.render("drawdown", path="drawdown.png")

# Combined dashboard (2×2)
res.render("dashboard", path="dashboard.png")

# Batch save
res.render_all("./charts")

# Advanced charts
res.render("returns_distribution", path="dist.png")
res.render("monthly_heatmap", path="monthly.png")
res.render("yearly_returns", path="yearly.png")

# Parameter grid heatmap
from stockstat.backtest.optimizer import grid_search
results = grid_search(make_engine, {"short": [3,5,8], "long": [10,20,30]}, metric="sharpe")
res.render("parameter_heatmap", grid_results=results, path="param.png")
```

![BTC Backtest Dashboard](../docs/images/backtest_btc_dashboard.png)

---

## 16. Signal Processing & Nonlinear Dynamics

> Requires `pip install stockstat[signal_processing]`. When PyWavelets is not installed, CWT gracefully degrades to an FFT-based Morlet.

### Example 16.1: Wavelet multiscale decomposition

```python
import numpy as np

signal = data.close.values[-48:]
scales = np.arange(1, 25)
coef, scales = client.compute.wavelet_decompose(signal, scales=scales, wavelet="morl")
print(f"CWT coefficient shape: {coef.shape}")  # (24, 48)
```

### Example 16.2: Spectral entropy

```python
h_spec = client.compute.spectral_entropy(np.diff(np.log(data.close.values[-100:])))
print(f"Spectral entropy: {h_spec:.4f}")
```

### Example 16.3: Grey relational degree

```python
path_a = data.close.values[-48:]
path_b = data.close.values[-96:-48]
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)
print(f"Grey relational degree: {gr:.4f}")  # [0, 1]; 1 = identical shape
```

### Example 16.4: Hurst exponent

```python
hurst = client.compute.hurst_dfa(np.diff(np.log(data.close.values[-500:])))
print(f"Hurst exponent: {hurst:.4f}")
# ≈ 0.5: random walk | > 0.5: persistent | < 0.5: anti-persistent
```

### Example 16.5: Transfer entropy

```python
btc = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")

btc_rets = np.diff(np.log(btc.close.values))[:200]
eth_rets = np.diff(np.log(eth.close.values))[:200]

te = client.compute.transfer_entropy(btc_rets, eth_rets, k=1)
print(f"TE(BTC→ETH): {te:.4f} bits")
```

### Example 16.6: Visualization — CWT scalogram

```python
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
renderer = client.plot.get_renderer()
renderer.render(spec)
renderer.savefig("cwt_scalogram.png")
```

### Example 16.7: Visualization — DFA fit plot

```python
spec = client.compute.dfa_fit(np.diff(np.log(signal)))
renderer = client.plot.get_renderer()
renderer.render(spec)
renderer.savefig("dfa_fit.png")
```

---

## 17. v2.0 CLI

v2.0 adds the `stockstat` CLI tool, enabling common operations without writing Python scripts.

### Example 17.1: Start the API server

```bash
stockstat serve --host 0.0.0.0 --port 8000
```

### Example 17.2: Ingest data from CLI

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --end 2024-12-31
```

Output:
```json
{"symbol": "AAPL", "source": "yfinance", "ingested": 251}
```

### Example 17.3: Query data

```bash
# Table format (default)
stockstat query BTC/USDT --limit 5

# JSON format
stockstat query BTC/USDT --format json

# CSV format
stockstat query AAPL --start 2024-01-01 --format csv
```

### Example 17.4: List registered plugins

```bash
# List all plugins
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
indicators           ma                        trend
indicators           rsi                       oscillator
indicators           hurst_dfa                 nonlinear
cost_models          binance                   cost
renderers            matplotlib                renderers

Total: 45 plugin(s)
```

### Example 17.5: List registered indicators

```bash
# All indicators
stockstat indicators

# Filter by category
stockstat indicators --category trend
stockstat indicators --category nonlinear
```

---

## 18. v2.0 Offline Mode

v2.0's `V2Client` supports offline mode, using local Storage directly without starting a backend HTTP service. Useful for:
- Analyzing pre-loaded data in Jupyter
- Running backtests without network access
- Unit testing

### Example 18.1: Basic offline usage

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage
from stockstat._core.contracts import DataSchema, FieldDef
import pandas as pd

# Create local storage and write data
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

# Offline client
client = V2Client(mode="offline", storage=storage)

# Query data (from local Storage, no HTTP)
df = client.ohlcv("BTC")
print(df)
```

### Example 18.2: Offline computation and backtesting

```python
# Compute indicators (local ComputeEngine)
ma = client.compute.ma(df.close, window=2)

# Run backtest (local BacktestEngine)
from stockstat.backtest import strategy, Order
@strategy
def s(ctx):
    d = ctx.get("BTC", "1d", lookback=3)
    if len(d) < 2: return
    pos = ctx.portfolio.get_position("BTC")
    if pos.qty == 0:
        ctx.broker.submit(Order("BTC", "buy", 1))
    elif pos.qty > 0:
        ctx.broker.submit(Order("BTC", "sell", pos.qty))

data = {"BTC": {"1d": df}}
res = client.backtest(data, s, initial_cash=10000)
print(res.summary())
```

### Example 18.3: Offline mode limitations

```python
# Offline mode cannot ingest data (requires online mode)
try:
    client.ingest("BTC/USDT")
except RuntimeError as e:
    print(e)  # "Ingest requires online mode"
```

---

## 19. v2.0 Plugin System

All extension points in v2.0 are registered to a unified `PluginRegistry`.

### Example 19.1: Register a custom indicator plugin

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

### Example 19.2: DSL auto-reflection of new indicators

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

### Example 19.3: Register a custom backtest component

```python
from stockstat._domain.backtest import BacktestComponentPlugin

# Suppose we have a custom cost model
class MyCostModel:
    def __init__(self, rate=0.001):
        self.rate = rate
    def compute(self, qty, price, side):
        return abs(qty * price * self.rate)

reg.register("cost_models", "my_cost",
    BacktestComponentPlugin("my_cost", MyCostModel, "cost",
                            description="Custom cost model"))
```

### Example 19.4: List all plugins

```python
for item in reg.list():
    plugin = item["plugin"]
    print(f"{item['namespace']:<20} {item['name']:<25} {getattr(plugin, 'category', '')}")
```

### Example 19.5: Theme system

```python
from stockstat._viz.themes import get_theme, register_theme, Theme, list_themes

# Built-in themes
print(list_themes())  # ['default', 'dark', 'publication']

dark = get_theme("dark")
print(dark.background)  # '#1e1e1e'

# Register a custom theme
custom = Theme("ocean", background="#0a1929", primary="#64ffda",
               secondary="#ff6b6b", grid="#1c3a5e")
register_theme(custom)
print(get_theme("ocean").primary)  # '#64ffda'
```

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

### Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCKSTAT_HOST` | `localhost` | Frontend host |
| `STOCKSTAT_PORT` | `8000` | Frontend port |
| `STOCKSTAT_API_KEY` | (empty) | Optional API key |
| `STOCKSTAT_TIMEOUT` | `30` | HTTP timeout in seconds |
| `STOCKSTAT_USE_HTTPS` | `false` | Whether to use HTTPS |
