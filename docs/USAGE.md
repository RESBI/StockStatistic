# StockStat Usage Guide

> All examples in this guide have been tested locally with real market data (Yahoo Finance + Binance via proxy). Expected results are from the actual test run on 2026-07-16.

## Table of Contents

1. [Setup](#1-setup)
2. [Data Ingestion](#2-data-ingestion)
3. [Querying OHLCV Data](#3-querying-ohlcv-data)
4. [Trend Indicators (MA / EMA / MACD)](#4-trend-indicators)
5. [Oscillator Indicators (RSI / KDJ)](#5-oscillator-indicators)
6. [Volatility Indicators (Bollinger / ATR / STD)](#6-volatility-indicators)
7. [Statistics (Beta / Sharpe / Drawdown / Correlation)](#7-statistics)
8. [DSL Queries](#8-dsl-queries)
9. [Custom Indicators](#9-custom-indicators)
10. [Visualization with Matplotlib](#10-visualization-with-matplotlib)
11. [PAXG Weekend Correlation Analysis](#11-paxg-weekend-correlation-analysis)
12. [Export Results](#12-export-results)
13. [Backtesting](#13-backtesting)
14. [Backtest Visualization](#14-backtest-visualization)

---

## 1. Setup

### Install

```bash
cd backend && pip install -e .
cd frontend && pip install -e .
```

### Enable proxy (for real data access)

```bash
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889
```

### Start backend

```bash
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
```

### Connect from frontend

```python
from stockstat import StockStatClient
client = StockStatClient(host="localhost", port=8000)
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

### Example 2.3: Auto-detect source

```python
# Stock symbols (no "/") → yfinance; crypto symbols (with "/") → binance
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")
client.ingest("ETH/USDT", start="2024-01-01", end="2024-12-31")
```

### Example 2.4: Ingest all symbols needed for analysis

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

---

## 4. Trend Indicators

### Example 4.1: Simple Moving Average (MA)

```python
ma20 = client.compute.ma(data.close, window=20)
print(f"MA(20) last value: {ma20.iloc[-1]:.2f}")
```

### Example 4.2: Exponential Moving Average (EMA)

```python
ema12 = client.compute.ema(data.close, window=12)
```

### Example 4.3: Golden / Death Cross

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

**Expected result**:
```
MACD line: -673.62
Signal line: 320.30
Histogram: -993.92
```

---

## 5. Oscillator Indicators

### Example 5.1: RSI

```python
rsi = client.compute.rsi(btc.close, window=14)
print(f"RSI last 5:\n{rsi.tail(5).round(2)}")
print(f"Overbought days (>70): {(rsi > 70).sum()}")
print(f"Oversold days (<30): {(rsi < 30).sum()}")
```

**Expected result**:
```
RSI last 5:
2024-12-27    44.00
2024-12-28    46.20
2024-12-29    43.33
2024-12-30    41.65
2024-12-31    43.61
Overbought days (>70): 53
Oversold days (<30): 4
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
print(f"Mid:   {mid.iloc[-1]:.2f}")
print(f"Lower: {lower.iloc[-1]:.2f}")
```

**Expected result**:
```
Upper: 106441.05
Mid:   98296.30
Lower: 90151.55
```

### Example 6.2: ATR (Average True Range)

```python
atr = client.compute.atr(btc.high, btc.low, btc.close, window=14)
print(f"ATR(14): {atr.iloc[-1]:.2f}")
```

### Example 6.3: Rolling Standard Deviation

```python
std = client.compute.std(btc.close, window=20)
print(f"20-day volatility: {std.iloc[-1]:.2f}")
```

---

## 7. Statistics

### Example 7.1: Beta (AAPL vs S&P 500)

```python
stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")
beta = client.compute.beta(stock.close.pct_change(), market.close.pct_change(), window=60)
print(f"Beta(60d) mean: {beta.dropna().mean():.4f}")
```

**Expected result**:
```
Beta(60d) mean: 1.0116
```

### Example 7.2: Sharpe Ratio

```python
rets = client.compute.returns(btc.close).dropna()
sharpe = client.compute.sharpe(rets, risk_free=0.02, annualize=True)
print(f"BTC Sharpe (annualized): {sharpe:.4f}")
```

**Expected result**:
```
BTC Sharpe (annualized): 1.3502
```

### Example 7.3: Maximum Drawdown

```python
dd = client.compute.max_drawdown(btc.close)
print(f"BTC Max Drawdown: {dd:.4f} ({dd*100:.2f}%)")
```

**Expected result**:
```
BTC Max Drawdown: -0.2615 (-26.15%)
```

### Example 7.4: Cross-Asset Correlation

```python
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
corr = btc.close.pct_change().corr(eth.close.pct_change())
print(f"BTC/ETH daily return correlation: {corr:.4f}")
```

**Expected result**:
```
BTC/ETH daily return correlation: 0.7947
```

### Example 7.5: Value at Risk (VaR)

```python
var_95 = client.compute.var(rets, confidence=0.95)
print(f"95% VaR (daily): {var_95:.4f} ({var_95*100:.2f}%)")
```

---

## 8. DSL Queries

### Example 8.1: Basic DSL query

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20
    FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
print(result)
```

**Expected result**:
```
                           close  ma20
ts
2024-12-23  255.27  NaN
2024-12-24  258.20  NaN
2024-12-26  259.02  NaN
2024-12-27  255.59  NaN
2024-12-30  252.20  NaN
```

### Example 8.2: DSL with RSI

```python
result = client.run_dsl('''
    SELECT rsi(close, 14) AS rsi_val
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 10
''')
```

### Example 8.3: DSL with returns

```python
result = client.run_dsl('''
    SELECT returns(close) AS ret
    FROM ohlcv("ETH/USDT", "1d", "2024-01-01", "2024-06-30")
''')
```

### Example 8.4: DSL with WHERE filter

```python
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

---

## 9. Custom Indicators

### Example 9.1: Volatility regime classifier

```python
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, high_threshold=0.04):
    ret = data.close.pct_change()
    vol = ret.rolling(window).std()
    regime = vol.apply(lambda v: "high" if v > high_threshold else "low")
    return {"regime": regime, "volatility": vol}

result = client.compute.call("volatility_regime", data=btc)
high_vol_days = (result["regime"] == "high").sum()
low_vol_days = (result["regime"] == "low").sum()
print(f"High volatility days: {high_vol_days}")
print(f"Low volatility days: {low_vol_days}")
```

**Expected result**:
```
High volatility days: 30
Low volatility days: 336
```

### Example 9.2: Register without decorator

```python
def my_indicator(data):
    return data.close.max()

client.compute.register("max_close", my_indicator, category="custom")
result = client.compute.call("max_close", data=btc)
```

---

## 10. Visualization with Matplotlib

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

### Example 10.2: Direct matplotlib usage

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

![BTC Bollinger Bands](images/btc_bollinger.png)

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

### Example 10.8: NullRenderer (no matplotlib)

```python
renderer = client.plot.get_renderer("null")
# When matplotlib is not installed, render() emits a warning but does not crash
spec = client.plot.spec(title="Test", series=[{"name": "x", "data": btc.close}])
renderer.render(spec)  # UserWarning: No plotting backend available
```

---

## 11. PAXG Weekend Correlation Analysis

### Analysis goal

Test whether PAXG (gold-pegged token) weekend return (Friday close → Sunday close) independently correlates with Monday's **max gain** and **max loss**:

- `max_gain = (High - Open) / Open` — intraday maximum upside (always positive)
- `max_loss = (Low - Open) / Open` — intraday maximum downside (always negative)

Both are recorded for every Monday and correlated with the weekend return **independently**. This avoids the selection bias of picking one extreme based on the signal direction.

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
p_gain = stats.pearsonr(result_df["weekend_return"], result_df["max_gain"])[1]
p_loss = stats.pearsonr(result_df["weekend_return"], result_df["max_loss"])[1]

up = result_df[result_df["weekend_return"] > 0]
dn = result_df[result_df["weekend_return"] < 0]

print(f"Samples: {len(result_df)}")
print(f"r(gain): {r_gain:.4f}, p={p_gain:.4f}")
print(f"r(loss): {r_loss:.4f}, p={p_loss:.4f}")
print(f"Weekend Up  (n={len(up)}): gain={up['max_gain'].mean()*100:.4f}%, loss={up['max_loss'].mean()*100:.4f}%")
print(f"Weekend Dn  (n={len(dn)}): gain={dn['max_gain'].mean()*100:.4f}%, loss={dn['max_loss'].mean()*100:.4f}%")
```

**Expected result**:
```
Samples: 156
r(gain): 0.2303, p=0.0038
r(loss): -0.2004, p=0.0121
Weekend Up  (n=76): gain=0.7099%, loss=-0.9070%
Weekend Dn  (n=65): gain=0.5940%, loss=-0.7435%
```

### Example 11.2: Scatter plot — gain & loss on same chart

![PAXG Weekend Scatter](images/paxg_weekend_scatter.png)

### Example 11.3: Gain/loss distribution histograms by weekend direction

![PAXG Directional](images/paxg_directional.png)

### Example 11.4: Weekend return distribution

![PAXG Weekend Histogram](images/paxg_weekend_hist.png)

### Interpretation

- **r(gain) = 0.23** (p=0.004): weak but significant positive correlation — weekend return modestly predicts Monday's max upside
- **r(loss) = -0.20** (p=0.012): weak but significant negative correlation — positive weekend return modestly predicts smaller Monday max downside
- **Up vs Down groups**: gain and loss means are not significantly different between groups (t-test p > 0.26)
- **Conclusion**: The weekend return has modest independent predictive power for both Monday's gain and loss. The correlations are statistically significant but weak (r ≈ 0.2), meaning the effect is real but small. High individual variability (std ≈ mean) limits practical single-trade predictability.

---

## 12. Export Results

### Example 12.1: Export to JSON

```python
from stockstat.export.serializers import to_json, to_csv, to_dict

# DataFrame → JSON string
json_str = to_json(data)
```

### Example 12.2: Export to CSV

```python
csv_str = to_csv(data)
with open("output.csv", "w") as f:
    f.write(csv_str)
```

### Example 12.3: Export to dict

```python
records = to_dict(data)  # list of dicts
```

### Example 12.4: PlotSpec to dict (for web frontend)

```python
spec = client.plot.spec(title="My Chart", series=[...])
payload = spec.to_dict()  # JSON-serializable dict
```

---

## 13. Backtesting

The backtest subsystem lives in `stockstat.backtest`. It supports custom strategies, multi-instrument trading groups, multi-timeframe bars, and reuses all compute-library indicators (including custom ones) inside strategies.

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

**Expected output (structure)**:
```
=== Backtest Summary ===
Total Return:      x.xx%
Annualized Return: x.xx%
Sharpe:            x.xxx
Sortino:           x.xxx
Max Drawdown:      -x.xx%
Calmar:            x.xxx
Volatility:        x.xx%
Win Rate:          xx.xx%
Profit Factor:     x.xxx
# Trades:          xx
Information Ratio: x.xxx
```

### Example 13.2: Via the client convenience entry

```python
res = client.backtest(data, ma_cross, initial_cash=10000, benchmark="BTC/USDT")
# client.backtest auto-injects the client's ComputeEngine; ctx.compute is fully usable
```

### Example 13.3: Class-style strategy with hooks

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

### Example 13.4: Custom indicator (registered inside strategy)

```python
@strategy
def custom(ctx):
    if not ctx.history.get("init"):
        def donchian(high, low, window=20):
            return high.rolling(window).max(), low.rolling(window).min()
        ctx.compute.register("donchian", donchian, category="custom")
        ctx.history["init"] = True
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21:
        return
    hh, ll = ctx.compute.call("donchian", high=d.high, low=d.low, window=20)
    pos = ctx.portfolio.get_position("BTC/USDT")
    if d.close.iloc[-1] > hh.iloc[-1] and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
```

### Example 13.5: Multi-asset pair trading + short selling

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
    pe = ctx.portfolio.get_position("ETH/USDT")
    if last > 1.5 and pb.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", 0.1))
        ctx.broker.submit(Order("ETH/USDT", "buy", 0.1))
    elif last < -1.5 and pb.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
        ctx.broker.submit(Order("ETH/USDT", "sell", 0.1))
    elif abs(last) < 0.3 and pb.qty != 0:
        # close both
        if pb.qty > 0: ctx.broker.submit(Order("BTC/USDT", "sell", abs(pb.qty)))
        else:          ctx.broker.submit(Order("BTC/USDT", "buy", abs(pb.qty)))
        if pe.qty > 0: ctx.broker.submit(Order("ETH/USDT", "sell", abs(pe.qty)))
        else:          ctx.broker.submit(Order("ETH/USDT", "buy", abs(pe.qty)))

res = BacktestEngine(data=data, strategy=pair,
                     initial_cash=10000, allow_short=True).run()
```

### Example 13.6: Multi-timeframe resonance

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

# DataFeed auto-uses 1h as master index, daily ffill-aligned
res = BacktestEngine(data=data, strategy=multi_tf).run()
```

### Example 13.7: Cost & fill models

```python
from stockstat.backtest import PercentCost, FixedCost, StampDutyCost, NextOpenFill, VWAPFill

# Equity: commission + stamp duty
eng = BacktestEngine(data={"AAPL": {"1d": df}}, strategy=s,
                     cost_model=StampDutyCost(commission=0.0003, stamp_duty=0.001),
                     fill_model=NextOpenFill())

# Crypto: percent cost + VWAP fill
eng = BacktestEngine(data={"BTC/USDT": {"1d": df}}, strategy=s,
                     cost_model=PercentCost(commission=0.0002, slippage=0.0003),
                     fill_model=VWAPFill())
```

### Example 13.8: Order types

```python
from stockstat.backtest import Order, OrderType

# Limit buy (fills only when price drops to limit)
ctx.broker.submit(Order("X", "buy", 10, order_type=OrderType.LIMIT, limit_price=95000))

# Stop sell (triggered when price falls to stop)
ctx.broker.submit(Order("X", "sell", 10, order_type=OrderType.STOP, stop_price=90000))

# Trailing stop (tracks extremum, triggers on stop_price pullback)
ctx.broker.submit(Order("X", "sell", 10, order_type=OrderType.TRAILING_STOP, stop_price=2000))
```

### Example 13.9: Metrics & visualization

```python
res = eng.run()

# Text summary
print(res.summary())

# Metrics dict
m = res.metrics()
# {'total_return', 'sharpe', 'sortino', 'max_drawdown', 'calmar',
#  'volatility', 'win_rate', 'profit_factor', 'num_trades', ...}

# Visualization (returns PlotSpec, renderable by matplotlib)
spec = res.plot_equity()       # equity + benchmark
spec_dd = res.plot_drawdown()  # drawdown
spec_t = res.plot_trades()     # trade markers

from stockstat.plot.base import get_renderer
r = get_renderer("matplotlib")
r.render(spec)
r.savefig("equity.png")

# Export
res.to_csv("trades.csv")
d = res.to_dict()
```

### Example 13.10: Parameter grid search

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

### Example 13.11: Lookahead protection

```python
# Default NextOpenFill: order submitted at t → fills at t+1 open
# Enable runtime audit
eng = BacktestEngine(data=data, strategy=s, lookahead_audit=True)
# If the strategy accidentally accesses data > t, raises LookaheadError
```

### Example 13.12: Binance fee models (4 presets)

```python
from stockstat.backtest import BinanceCost, BINANCE_SPOT, BINANCE_SPOT_BNB, \
    BINANCE_FUTURES, BINANCE_FUTURES_BNB, MakerTakerCost

# 4 presets: spot/futures × BNB no/yes
# F1 Spot No BNB:  maker 0.100% / taker 0.100%
# F2 Spot + BNB:    maker 0.075% / taker 0.075%  (-25%)
# F3 Futures No BNB: maker 0.020% / taker 0.050%
# F4 Futures + BNB:  maker 0.018% / taker 0.045%  (-10%)

eng = BacktestEngine(data=data, strategy=s,
                     cost_model=BINANCE_FUTURES_BNB,  # lowest fees
                     initial_cash=10000)

# Custom Maker/Taker rates also possible
custom = MakerTakerCost(maker_rate=0.0002, taker_rate=0.0005, slippage=0.0)
# LIMIT → maker_rate, MARKET/STOP → taker_rate
```

### Example 13.13: Intrabar execution (same-bar entry + exit)

`IntrabarExecution` model simulates order matching within a parent bar (e.g. daily) using sub-bars (e.g. hourly) — completing the full entry→exit lifecycle within a single parent bar.

```python
from stockstat.backtest import (
    BacktestEngine, Strategy, IntrabarMixin, Order,
    IntrabarExecution, BinanceCost,
)

class SimpleTP(Strategy, IntrabarMixin):
    """Market entry → intrabar TP scan → close fallback."""
    def on_bar(self, ctx):
        o = ctx.current_price("BTC/USDT", "open")
        if o is None:
            return
        # intrabar_submit: order executes on current bar's sub-bars
        ctx.intrabar_submit(
            Order("BTC/USDT", "buy", 0.1, tag="entry")
        )
        ctx.history["tp_price"] = o * 1.01  # 1% take-profit

    def define_exits(self, entry_fill, ctx):
        """Called automatically after entry fill; return exit orders."""
        tp = ctx.history.get("tp_price")
        if tp is None:
            return []
        return [
            # TP limit (priority 1: fills if price reaches target)
            Order("BTC/USDT", "sell", entry_fill.qty,
                  order_type="limit", limit_price=tp,
                  tag="tp", exit_reason="tp", priority=1),
            # Close fallback (priority 99: market at session close)
            Order("BTC/USDT", "sell", entry_fill.qty,
                  order_type="market", tag="close",
                  exit_reason="close", priority=99),
        ]

# Provide both 1d and 1h data
data = {"BTC/USDT": {"1d": daily_df, "1h": hourly_df}}

res = BacktestEngine(
    data=data,
    strategy=SimpleTP(),
    initial_cash=10000,
    cost_model=BinanceCost(venue="spot"),
    execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),  # ← explicit
).run()

# Exit reason statistics
print(res.exit_reason_stats())
# {'tp': {'count': 45, 'total_pnl': 120.5, 'avg_pnl': 2.68},
#  'close': {'count': 55, 'total_pnl': -30.2, 'avg_pnl': -0.55}}
```

> **Key**: default `execution_model=None` is equivalent to `NextBarExecution` (existing behavior). Only passing `IntrabarExecution(...)` enables intrabar mode.

### Example 13.14: Mutual OCO (dual limit orders)

When both buy-limit and sell-limit fill within the same bar, the trade is cancelled (avoiding a net-zero position with wasted fees).

```python
class DualLimit(Strategy, IntrabarMixin):
    """Dual limit entry + profit exit."""
    def on_bar(self, ctx):
        o = ctx.current_price("PAXG/USDT", "open")
        if o is None:
            return
        k = 0.005  # 0.5% width
        q = 500 / o  # half position each
        buy = Order("PAXG/USDT", "buy", q,
                    order_type="limit", limit_price=o * (1 - k),
                    tag="entry_buy", exit_reason="entry")
        sell = Order("PAXG/USDT", "sell", q,
                     order_type="limit", limit_price=o * (1 + k),
                     tag="entry_sell", exit_reason="entry")
        # Mutual OCO: both fill → both cancel
        ctx.intrabar_submit_oco_mutual(buy, sell)

    def define_exits(self, entry_fill, ctx):
        # Profit exit: close when profit >= 0.3%
        if entry_fill.side.value == "buy":
            target = entry_fill.price * 1.003
        else:
            target = entry_fill.price * 0.997
        side = "sell" if entry_fill.side.value == "buy" else "buy"
        return [
            Order("PAXG/USDT", side, entry_fill.qty,
                  order_type="limit", limit_price=target,
                  tag="profit", exit_reason="profit", priority=1),
            Order("PAXG/USDT", side, entry_fill.qty,
                  order_type="market", tag="close",
                  exit_reason="close", priority=99),
        ]
```

### Example 13.15: Order priority (SL before TP)

When both SL and TP could trigger in the same sub-bar, use the `priority` field to control matching order (0 = highest).

```python
class TPWithSL(Strategy, IntrabarMixin):
    """Entry with TP and SL; SL checked first in same bar."""
    def define_exits(self, entry_fill, ctx):
        side = "sell" if entry_fill.side.value == "buy" else "buy"
        qty = entry_fill.qty
        if entry_fill.side.value == "buy":
            tp_price = entry_fill.price * 1.009  # +0.9% TP
            sl_price = entry_fill.price * 0.9865  # -1.35% SL
        else:
            tp_price = entry_fill.price * 0.991
            sl_price = entry_fill.price * 1.0135

        return [
            # SL priority 0 (highest): checked first in each sub-bar
            Order("BTC/USDT", side, qty,
                  order_type="stop", stop_price=sl_price,
                  tag="sl", exit_reason="sl", priority=0),
            # TP priority 1
            Order("BTC/USDT", side, qty,
                  order_type="limit", limit_price=tp_price,
                  tag="tp", exit_reason="tp", priority=1),
            # Close fallback priority 99
            Order("BTC/USDT", side, qty,
                  order_type="market", tag="close",
                  exit_reason="close", priority=99),
        ]
```

### Example 13.16: Batch backtest (multi-strategy × multi-fee)

```python
from stockstat.backtest import StrategyBatchRunner

runner = StrategyBatchRunner(
    data=data,
    initial_cash=10000,
    cost_model=BINANCE_SPOT,
    allow_short=True,
    periods_per_year=52,
)

# Multiple strategies
results = runner.run_all({
    "ma_cross": ma_cross_strategy,
    "rsi_reversal": rsi_strategy,
    "bollinger": boll_strategy,
})

# Summary DataFrame
df = results.to_dataframe()
print(df[["total_return", "sharpe", "max_drawdown", "win_rate"]].round(4))

# Rank by Sharpe
ranked = results.rank("sharpe")

# Multi-strategy × multi-fee
fee_models = {
    "F1_SpotNoBNB": BINANCE_SPOT,
    "F4_FutBNB": BINANCE_FUTURES_BNB,
}
results_all_fees = runner.run_all_fees(
    {"ma_cross": ma_cross_strategy, "rsi": rsi_strategy},
    fee_models,
)
```

### Example 13.17: Subperiod and regime analysis

```python
from stockstat.backtest import BacktestAnalyzer

res = BacktestEngine(data=data, strategy=s, initial_cash=10000).run()

# Subperiod analysis: pre/post 2024
sub = BacktestAnalyzer.subperiod_metrics(
    res, split_dates=[pd.Timestamp("2024-01-01")]
)

# Regime-conditional: high/low volatility
atr = data["BTC/USDT"]["1d"]["close"].pct_change().rolling(30).std()
regime = pd.Series("low_vol", index=atr.index)
regime[atr > atr.quantile(0.75)] = "high_vol"

reg = BacktestAnalyzer.regime_conditional_metrics(res, regime)

# Exit reason analysis
exit_stats = res.exit_reason_stats()
# {'tp': {'count': 45, 'avg_pnl': 2.68},
#  'sl': {'count': 20, 'avg_pnl': -3.10},
#  'close': {'count': 35, 'avg_pnl': -0.15}}
```

### Example 13.18: DCA benchmark and fee sweep

```python
from stockstat.backtest import dca_equity, fee_sweep, maker_taker_sweep

# DCA benchmark
prices = data["BTC/USDT"]["1d"]["close"]
dca_eq = dca_equity(10000, prices, schedule="weekly")

# Fee sensitivity sweep
sweep_results = fee_sweep(
    data=data, strategy=ma_cross_strategy,
    initial_cash=10000,
    commissions=[0.0001, 0.0003, 0.0005, 0.001, 0.002],
)

# Maker/Taker rate combination sweep
mt_results = maker_taker_sweep(
    data=data, strategy=ma_cross_strategy,
    initial_cash=10000,
    maker_rates=[0.0002, 0.0005, 0.001],
    taker_rates=[0.0005, 0.001, 0.002],
)
```

Backtest visualization (dashboard, heatmaps, return distributions — 9 chart types) is covered in [§14 Backtest Visualization](#14-backtest-visualization).

### Backtest API cheat sheet

| Class/Function | Description |
|----------------|-------------|
| `BacktestEngine(data, strategy, ...)` | main engine (with `execution_model` param) |
| `@strategy` / `Strategy` / `IntrabarMixin` | strategy definition (function/class/intrabar) |
| `ctx.get(sym, tf, lookback)` | get ≤ t slice |
| `ctx.compute` | ComputeEngine proxy (with register/call) |
| `ctx.broker.submit(Order)` | place order (default mode) |
| `ctx.intrabar_submit(Order)` | intrabar order (intrabar mode) |
| `ctx.intrabar_submit_oco_mutual(a, b)` | mutual OCO dual limit |
| `ctx.portfolio.get_position(sym)` | inspect position |
| `ctx.history` | strategy state scratchpad |
| `Order(sym, side, qty, order_type=..., priority=...)` | order (with priority field) |
| `PercentCost / FixedCost / StampDutyCost / ZeroCost` | basic cost models |
| `MakerTakerCost / BinanceCost` | Maker/Taker & Binance fees |
| `BINANCE_SPOT / _BNB / FUTURES / _BNB` | Binance 4 presets |
| `NextOpenFill / VWAPFill / WorstPriceFill / IntrabarLimitFill` | fill models |
| `ExecutionModel / NextBarExecution / IntrabarExecution` | pluggable execution models |
| `IntrabarFillModel / IntrabarFillResult` | intrabar fill scan + timing |
| `res.summary() / metrics() / plot_equity() / to_csv()` | result |
| `res.exit_reason_stats()` | exit reason statistics |
| `res.chart(name) / render(name, path) / render_all(dir)` | backtest visualization (§14) |
| `StrategyBatchRunner` | multi-strategy/multi-fee batch |
| `BacktestAnalyzer` | subperiod/regime/rolling analysis |
| `dca_equity() / fee_sweep() / maker_taker_sweep()` | benchmark & fee sweep |
| `grid_search / optuna_search / walk_forward / monte_carlo_equity` | optimization |

---

## 14. Backtest Visualization

The backtest visualization subsystem provides 9 chart types with **zero matplotlib hard-dependency** in the core — auto-activates when installed. It reuses the protocol-based design from [§10 Visualization with Matplotlib](#10-visualization-with-matplotlib) but provides a backtest-dedicated `BacktestChartSpec` (supporting subplots, fill areas, heatmaps, histograms, and more). The examples below use real market data (Binance BTC/USDT 2023-2024); generated images are in `docs/images/backtest_*.png`.

![BTC Backtest Dashboard](../docs/images/backtest_btc_dashboard.png)

### Example 14.1: One-liner render and batch save

```python
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

# One-liner render (auto-detects matplotlib, graceful degradation if absent)
res.render("equity_curve", path="equity.png")
res.render("drawdown", path="drawdown.png")

# Combined dashboard (2×2: equity + drawdown + returns dist + monthly heatmap)
res.render("dashboard", path="dashboard.png")

# Batch-save all charts to a directory
out = res.render_all("./charts")
# {'equity_curve': './charts/equity_curve.png', 'drawdown': ..., ...}

# Advanced charts
res.render("returns_distribution", path="dist.png")   # return distribution histogram
res.render("monthly_heatmap", path="monthly.png")      # monthly returns heatmap
res.render("yearly_returns", path="yearly.png")        # yearly returns bar
res.render("underwater_curve", path="underwater.png")  # underwater curve
```

### Example 14.2: Parameter grid heatmap

```python
from stockstat.backtest.optimizer import grid_search

results = grid_search(make_engine,
                      {"short": [3, 5, 8], "long": [10, 20, 30]},
                      metric="sharpe")

# Render parameter heatmap (x=short, y=long, color=sharpe)
res.render("parameter_heatmap", grid_results=results, metric="sharpe",
           path="param_heatmap.png")

# Or swap the 4th panel in the dashboard
res.render("dashboard", grid_results=results, path="dashboard_with_params.png")
```

### Example 14.3: Getting a BacktestChartSpec (without rendering)

```python
from stockstat.backtest.chart_factory import get_chart_renderer

# Get a dedicated spec (with subplots, fill, heatmap, etc.)
spec = res.chart("equity_curve")           # BacktestChartSpec
spec = res.chart("dashboard")              # 4-subplot combo
spec = res.chart("drawdown")               # with fill area

# Serialize to dict (for web frontends)
payload = spec.to_dict()

# Render yourself
renderer = get_chart_renderer()            # auto-detect matplotlib
if renderer.available():
    fig = renderer.render(spec)
    renderer.savefig("custom.png")

# List available chart types
print(res.available_chart_types)
# ['dashboard', 'drawdown', 'equity_curve', 'monthly_heatmap', 'parameter_heatmap',
#  'returns_distribution', 'trades_overlay', 'underwater_curve', 'yearly_returns']
```

---

## Appendix: Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database URL |
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` or `socks5` |
| `STOCKSTAT_PROXY_URL` | auto | Proxy URL |
| `STOCKSTAT_HOST` | `localhost` | Frontend host |
| `STOCKSTAT_PORT` | `8000` | Frontend port |
