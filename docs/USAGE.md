# StockStat Usage Guide

> All examples in this guide have been tested locally with real market data (Yahoo Finance + Binance via proxy). Expected results are from the actual test run on 2025-07-15.

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

## Appendix: Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | Database URL |
| `STOCKSTAT_PROXY_ENABLED` | `false` | Enable proxy |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` or `socks5` |
| `STOCKSTAT_PROXY_URL` | auto | Proxy URL |
| `STOCKSTAT_HOST` | `localhost` | Frontend host |
| `STOCKSTAT_PORT` | `8000` | Frontend port |
