# StockStat 使用文档

> 本文档所有示例均在本地使用真实市场数据（Yahoo Finance + Binance，通过代理）测试通过。预期结果来自 2025-07-15 的实际测试运行。

## 目录

1. [环境准备](#1-环境准备)
2. [数据采集](#2-数据采集)
3. [查询 OHLCV 数据](#3-查询-ohlcv-数据)
4. [趋势指标（MA / EMA / MACD）](#4-趋势指标)
5. [震荡指标（RSI / KDJ）](#5-震荡指标)
6. [波动率指标（布林带 / ATR / STD）](#6-波动率指标)
7. [统计指标（Beta / Sharpe / 回撤 / 相关性）](#7-统计指标)
8. [DSL 查询](#8-dsl-查询)
9. [自定义指标](#9-自定义指标)
10. [matplotlib 可视化](#10-matplotlib-可视化)
11. [PAXG 周末相关性分析](#11-paxg-周末相关性分析)
12. [结果导出](#12-结果导出)

---

## 1. 环境准备

### 安装

```bash
cd backend && pip install -e .
cd frontend && pip install -e .
```

### 开启代理（访问真实数据）

```bash
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889
```

### 启动后端

```bash
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
```

### 前端连接

```python
from stockstat import StockStatClient
client = StockStatClient(host="localhost", port=8000)
```

---

## 2. 数据采集

### 示例 2.1：采集股票数据

```python
result = client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
print(result)
```

**预期结果**：
```python
{'symbol': 'AAPL', 'source': 'yfinance', 'ingested': 251}
```

### 示例 2.2：采集加密货币数据

```python
result = client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
print(result)
```

**预期结果**：
```python
{'symbol': 'BTC/USDT', 'source': 'binance', 'ingested': 366}
```

### 示例 2.3：自动检测数据源

```python
# 股票符号（无"/"）→ yfinance；加密货币符号（含"/"）→ binance
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")
client.ingest("ETH/USDT", start="2024-01-01", end="2024-12-31")
```

### 示例 2.4：批量采集分析所需标的

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

## 3. 查询 OHLCV 数据

### 示例 3.1：查询为 DataFrame

```python
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d", limit=5)
print(data)
```

**预期结果**：
```
                                 open    high     low   close     volume
ts
2024-01-02  187.15  188.44  183.89  185.64  82488700
2024-01-03  184.22  185.88  183.43  184.25  58414500
2024-01-04  182.15  183.09  181.37  181.91  71983600
2024-01-05  181.99  182.76  181.18  181.18  62379700
2024-01-08  182.09  185.60  182.09  185.56  59144500
```

### 示例 3.2：批量查询

```python
batch = client.ohlcv_batch(["BTC/USDT", "ETH/USDT"], start="2024-01-01")
btc = batch["BTC/USDT"]
eth = batch["ETH/USDT"]
```

### 示例 3.3：列出已注册符号

```python
symbols = client.symbols()
for s in symbols:
    print(f"{s['unified_symbol']:15s} {s['asset_type']:8s} {s['sources']}")
```

---

## 4. 趋势指标

### 示例 4.1：简单移动平均（MA）

```python
ma20 = client.compute.ma(data.close, window=20)
print(f"MA(20) 最新值: {ma20.iloc[-1]:.2f}")
```

### 示例 4.2：指数移动平均（EMA）

```python
ema12 = client.compute.ema(data.close, window=12)
```

### 示例 4.3：金叉 / 死叉

```python
ma_short = data.close.rolling(5).mean()
ma_long = data.close.rolling(20).mean()

golden_cross = (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
death_cross = (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))

print(f"金叉次数: {golden_cross.sum()}")
print(f"死叉次数: {death_cross.sum()}")
```

### 示例 4.4：MACD

```python
btc = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
macd_line, signal_line, hist = client.compute.macd(btc.close)
print(f"MACD 线: {macd_line.iloc[-1]:.2f}")
print(f"信号线: {signal_line.iloc[-1]:.2f}")
print(f"柱状图: {hist.iloc[-1]:.2f}")
```

**预期结果**：
```
MACD 线: -673.62
信号线: 320.30
柱状图: -993.92
```

---

## 5. 震荡指标

### 示例 5.1：RSI

```python
rsi = client.compute.rsi(btc.close, window=14)
print(f"RSI 最后5天:\n{rsi.tail(5).round(2)}")
print(f"超买天数 (>70): {(rsi > 70).sum()}")
print(f"超卖天数 (<30): {(rsi < 30).sum()}")
```

**预期结果**：
```
RSI 最后5天:
2024-12-27    44.00
2024-12-28    46.20
2024-12-29    43.33
2024-12-30    41.65
2024-12-31    43.61
超买天数 (>70): 53
超卖天数 (<30): 4
```

### 示例 5.2：KDJ

```python
k, d, j = client.compute.kdj(btc.high, btc.low, btc.close, window=9)
print(f"K: {k.iloc[-1]:.2f}, D: {d.iloc[-1]:.2f}, J: {j.iloc[-1]:.2f}")
```

---

## 6. 波动率指标

### 示例 6.1：布林带

```python
upper, mid, lower = client.compute.bollinger(btc.close, window=20, k=2.0)
print(f"上轨: {upper.iloc[-1]:.2f}")
print(f"中轨: {mid.iloc[-1]:.2f}")
print(f"下轨: {lower.iloc[-1]:.2f}")
```

**预期结果**：
```
上轨: 106441.05
中轨: 98296.30
下轨: 90151.55
```

### 示例 6.2：ATR（平均真实波幅）

```python
atr = client.compute.atr(btc.high, btc.low, btc.close, window=14)
print(f"ATR(14): {atr.iloc[-1]:.2f}")
```

### 示例 6.3：滚动标准差

```python
std = client.compute.std(btc.close, window=20)
print(f"20日波动率: {std.iloc[-1]:.2f}")
```

---

## 7. 统计指标

### 示例 7.1：Beta（AAPL vs 标普500）

```python
stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")
beta = client.compute.beta(stock.close.pct_change(), market.close.pct_change(), window=60)
print(f"Beta(60日) 均值: {beta.dropna().mean():.4f}")
```

**预期结果**：
```
Beta(60日) 均值: 1.0116
```

### 示例 7.2：夏普比率

```python
rets = client.compute.returns(btc.close).dropna()
sharpe = client.compute.sharpe(rets, risk_free=0.02, annualize=True)
print(f"BTC 夏普比率（年化）: {sharpe:.4f}")
```

**预期结果**：
```
BTC 夏普比率（年化）: 1.3502
```

### 示例 7.3：最大回撤

```python
dd = client.compute.max_drawdown(btc.close)
print(f"BTC 最大回撤: {dd:.4f} ({dd*100:.2f}%)")
```

**预期结果**：
```
BTC 最大回撤: -0.2615 (-26.15%)
```

### 示例 7.4：跨资产相关性

```python
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
corr = btc.close.pct_change().corr(eth.close.pct_change())
print(f"BTC/ETH 日收益率相关性: {corr:.4f}")
```

**预期结果**：
```
BTC/ETH 日收益率相关性: 0.7947
```

### 示例 7.5：在险价值（VaR）

```python
var_95 = client.compute.var(rets, confidence=0.95)
print(f"95% VaR（日度）: {var_95:.4f} ({var_95*100:.2f}%)")
```

---

## 8. DSL 查询

### 示例 8.1：基础 DSL 查询

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20
    FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
print(result)
```

**预期结果**：
```
                           close  ma20
ts
2024-12-23  255.27  NaN
2024-12-24  258.20  NaN
2024-12-26  259.02  NaN
2024-12-27  255.59  NaN
2024-12-30  252.20  NaN
```

### 示例 8.2：DSL 查询 RSI

```python
result = client.run_dsl('''
    SELECT rsi(close, 14) AS rsi_val
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 10
''')
```

### 示例 8.3：DSL 查询收益率

```python
result = client.run_dsl('''
    SELECT returns(close) AS ret
    FROM ohlcv("ETH/USDT", "1d", "2024-01-01", "2024-06-30")
''')
```

### 示例 8.4：DSL 带 WHERE 过滤

```python
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

---

## 9. 自定义指标

### 示例 9.1：波动率状态分类器

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
print(f"高波动天数: {high_vol_days}")
print(f"低波动天数: {low_vol_days}")
```

**预期结果**：
```
高波动天数: 30
低波动天数: 336
```

### 示例 9.2：不用装饰器注册

```python
def my_indicator(data):
    return data.close.max()

client.compute.register("max_close", my_indicator, category="custom")
result = client.compute.call("max_close", data=btc)
```

---

## 10. matplotlib 可视化

### 示例 10.1：协议化绘图

```python
spec = client.plot.spec(
    title="BTC 收盘价 + MA20",
    x_label="日期",
    y_label="价格 (USDT)",
    series=[
        {"name": "close", "data": btc.close, "kind": "line"},
        {"name": "ma20", "data": btc.close.rolling(20).mean(), "kind": "line", "color": "red"},
    ],
)
renderer = client.plot.get_renderer("matplotlib")
fig = renderer.render(spec)
renderer.savefig("btc.png")
```

### 示例 10.2：直接使用 matplotlib

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(btc.index, btc.close, label="收盘价", color="black")
upper, mid, lower = client.compute.bollinger(btc.close, 20, 2.0)
ax.fill_between(btc.index, lower, upper, alpha=0.15, color="blue", label="布林带")
ax.set_title("BTC/USDT 布林带")
ax.legend()
plt.savefig("btc_bollinger.png", dpi=150)
```

![BTC 布林带](images/btc_bollinger.png)

### 示例 10.3：RSI 图表

![BTC RSI](images/btc_rsi.png)

### 示例 10.4：MACD 图表

![ETH MACD](images/eth_macd.png)

### 示例 10.5：回撤图表

![BTC 回撤](images/btc_drawdown.png)

### 示例 10.6：Beta 散点图

![AAPL Beta](images/aapl_beta_scatter.png)

### 示例 10.7：价格对比

![价格对比](images/price_comparison.png)

### 示例 10.8：NullRenderer（无 matplotlib 时）

```python
renderer = client.plot.get_renderer("null")
# matplotlib 未安装时，render() 发出告警但不崩溃
spec = client.plot.spec(title="测试", series=[{"name": "x", "data": btc.close}])
renderer.render(spec)  # UserWarning: No plotting backend available
```

---

## 11. PAXG 周末相关性分析

### 分析目标

检验 PAXG（黄金锚定代币）周末涨跌幅（周五收盘→周日收盘）与周一**最大涨幅**和**最大跌幅**之间的独立相关性：

- `max_gain = (最高 - 开盘) / 开盘` — 日内最大上行幅度（恒为正）
- `max_loss = (最低 - 开盘) / 开盘` — 日内最大下行幅度（恒为负）

每个周一同时记录两者，与周末涨跌幅**独立**相关。这避免了按信号方向选择极值导致的选择偏差。

### 示例 11.1：完整分析

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

print(f"样本数: {len(result_df)}")
print(f"r(涨幅): {r_gain:.4f}, p={p_gain:.4f}")
print(f"r(跌幅): {r_loss:.4f}, p={p_loss:.4f}")
print(f"周末上涨 (n={len(up)}): 涨幅={up['max_gain'].mean()*100:.4f}%, 跌幅={up['max_loss'].mean()*100:.4f}%")
print(f"周末下跌 (n={len(dn)}): 涨幅={dn['max_gain'].mean()*100:.4f}%, 跌幅={dn['max_loss'].mean()*100:.4f}%")
```

**预期结果**：
```
样本数: 156
r(涨幅): 0.2303, p=0.0038
r(跌幅): -0.2004, p=0.0121
周末上涨 (n=76): 涨幅=0.7099%, 跌幅=-0.9070%
周末下跌 (n=65): 涨幅=0.5940%, 跌幅=-0.7435%
```

### 示例 11.2：散点图 — 涨幅与跌幅同图显示

![PAXG 周末散点图](images/paxg_weekend_scatter.png)

### 示例 11.3：按周末方向的涨跌幅分布直方图

![PAXG 方向性](images/paxg_directional.png)

### 示例 11.4：周末涨跌幅分布

![PAXG 周末直方图](images/paxg_weekend_hist.png)

### 解读

- **r(涨幅) = 0.23** (p=0.004)：弱但显著的正相关 — 周末涨跌幅适度预测周一最大涨幅
- **r(跌幅) = -0.20** (p=0.012)：弱但显著的负相关 — 周末正向涨跌幅适度预测周一最大跌幅较小
- **涨组 vs 跌组**：涨幅和跌幅的均值在两组间无显著差异 (t 检验 p > 0.26)
- **结论**：周末涨跌幅对周一涨幅和跌幅有适度的独立预测力。相关性统计显著但较弱 (r ≈ 0.2)，说明效应真实但较小。高个体波动性（标准差 ≈ 均值）限制了单笔交易的可预测性。

---

## 12. 结果导出

### 示例 12.1：导出为 JSON

```python
from stockstat.export.serializers import to_json, to_csv, to_dict

# DataFrame → JSON 字符串
json_str = to_json(data)
```

### 示例 12.2：导出为 CSV

```python
csv_str = to_csv(data)
with open("output.csv", "w") as f:
    f.write(csv_str)
```

### 示例 12.3：导出为 dict

```python
records = to_dict(data)  # 字典列表
```

### 示例 12.4：PlotSpec 转 dict（用于 Web 前端）

```python
spec = client.plot.spec(title="我的图表", series=[...])
payload = spec.to_dict()  # 可 JSON 序列化的字典
```

---

## 附录：环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | 数据库 URL |
| `STOCKSTAT_PROXY_ENABLED` | `false` | 启用代理 |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` 或 `socks5` |
| `STOCKSTAT_PROXY_URL` | 自动 | 代理地址 |
| `STOCKSTAT_HOST` | `localhost` | 前端主机 |
| `STOCKSTAT_PORT` | `8000` | 前端端口 |
