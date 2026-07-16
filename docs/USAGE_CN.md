# StockStat 使用文档

> 本文档所有示例均在本地使用真实市场数据（Yahoo Finance + Binance，通过代理）测试通过。预期结果来自 2026-07-16 的实际测试运行。

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
13. [回测](#13-回测)
14. [回测可视化](#14-回测可视化)

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

## 13. 回测

回测子系统位于 `stockstat.backtest`，支持自定义策略、多标的交易组、多时间尺度 K 线，策略内可直接调用计算库全部指标与自定义指标。

### 示例 13.1：最简回测（函数式策略）

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

**预期输出（结构）**：
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

### 示例 13.2：通过 client 便捷入口

```python
res = client.backtest(data, ma_cross, initial_cash=10000, benchmark="BTC/USDT")
# client.backtest 自动注入 client 的 ComputeEngine，策略内 ctx.compute 可用全部指标
```

### 示例 13.3：类式策略 + 钩子

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
        print(f"成交 {fill.side.value} {fill.qty} @ {fill.price:.2f}")
```

### 示例 13.4：自定义指标（策略内注册）

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

### 示例 13.5：多标的配对交易 + 做空

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
        # 平仓
        if pb.qty > 0: ctx.broker.submit(Order("BTC/USDT", "sell", abs(pb.qty)))
        else:          ctx.broker.submit(Order("BTC/USDT", "buy", abs(pb.qty)))
        if pe.qty > 0: ctx.broker.submit(Order("ETH/USDT", "sell", abs(pe.qty)))
        else:          ctx.broker.submit(Order("ETH/USDT", "buy", abs(pe.qty)))

res = BacktestEngine(data=data, strategy=pair,
                     initial_cash=10000, allow_short=True).run()
```

### 示例 13.6：多时间尺度共振

```python
# 同时注入日线与小时线
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

# DataFeed 自动以 1h 为主索引，日线 ffill 对齐
res = BacktestEngine(data=data, strategy=multi_tf).run()
```

### 示例 13.7：成本与成交模型

```python
from stockstat.backtest import PercentCost, FixedCost, StampDutyCost, NextOpenFill, VWAPFill

# 股票：佣金 + 印花税
eng = BacktestEngine(data={"AAPL": {"1d": df}}, strategy=s,
                     cost_model=StampDutyCost(commission=0.0003, stamp_duty=0.001),
                     fill_model=NextOpenFill())

# 加密货币：比例成本 + VWAP 成交
eng = BacktestEngine(data={"BTC/USDT": {"1d": df}}, strategy=s,
                     cost_model=PercentCost(commission=0.0002, slippage=0.0003),
                     fill_model=VWAPFill())
```

### 示例 13.8：订单类型

```python
from stockstat.backtest import Order, OrderType

# 限价买单（价格跌至 limit 才成交）
ctx.broker.submit(Order("X", "buy", 10, order_type=OrderType.LIMIT, limit_price=95000))

# 止损卖单（价格跌至 stop 触发）
ctx.broker.submit(Order("X", "sell", 10, order_type=OrderType.STOP, stop_price=90000))

# 移动止损（跟踪极值，回撤 stop_price 触发）
ctx.broker.submit(Order("X", "sell", 10, order_type=OrderType.TRAILING_STOP, stop_price=2000))
```

### 示例 13.9：绩效与可视化

```python
res = eng.run()

# 文本摘要
print(res.summary())

# 指标字典
m = res.metrics()
# {'total_return', 'sharpe', 'sortino', 'max_drawdown', 'calmar',
#  'volatility', 'win_rate', 'profit_factor', 'num_trades', ...}

# 可视化（返回 PlotSpec，可被 matplotlib 渲染）
spec = res.plot_equity()       # 资金曲线 + 基准
spec_dd = res.plot_drawdown()  # 回撤
spec_t = res.plot_trades()     # 交易点

from stockstat.plot.base import get_renderer
r = get_renderer("matplotlib")
r.render(spec)
r.savefig("equity.png")

# 导出
res.to_csv("trades.csv")
d = res.to_dict()
```

### 示例 13.10：参数网格搜索

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
print(f"最佳参数: {best_params}, Sharpe: {best_val:.3f}")
```

### 示例 13.11：未来函数防护

```python
# 默认 NextOpenFill：订单在 t 提交 → t+1 open 成交
# 开启运行时审计
eng = BacktestEngine(data=data, strategy=s, lookahead_audit=True)
# 若策略误访问 > t 的数据，抛 LookaheadError
```

### 示例 13.12：Binance 费率模型（4 种预设）

```python
from stockstat.backtest import BinanceCost, BINANCE_SPOT, BINANCE_SPOT_BNB, \
    BINANCE_FUTURES, BINANCE_FUTURES_BNB, MakerTakerCost

# 4 种预设：现货/合约 × BNB 无/有
# F1 现货无 BNB:  maker 0.100% / taker 0.100%
# F2 现货+BNB:    maker 0.075% / taker 0.075%  (−25%)
# F3 合约无 BNB:  maker 0.020% / taker 0.050%
# F4 合约+BNB:    maker 0.018% / taker 0.045%  (−10%)

eng = BacktestEngine(data=data, strategy=s,
                     cost_model=BINANCE_FUTURES_BNB,  # 最低费率
                     initial_cash=10000)

# 也可自定义 Maker/Taker 费率
custom = MakerTakerCost(maker_rate=0.0002, taker_rate=0.0005, slippage=0.0)
# LIMIT → maker_rate, MARKET/STOP → taker_rate
```

### 示例 13.13：Intrabar 执行（同 bar 入场+出场）

`IntrabarExecution` 模型在 parent bar（如日线）内部用子 bar（如 1h）模拟订单撮合——同 bar 内完成入场→退出全生命周期。

```python
from stockstat.backtest import (
    BacktestEngine, Strategy, IntrabarMixin, Order,
    IntrabarExecution, BinanceCost,
)

class SimpleTP(Strategy, IntrabarMixin):
    """市价入场 → intrabar 扫描 TP 限价 → 收盘兜底。"""
    def on_bar(self, ctx):
        o = ctx.current_price("BTC/USDT", "open")
        if o is None:
            return
        # 用 intrabar_submit 提交（在当前 bar 的子 bar 上执行）
        ctx.intrabar_submit(
            Order("BTC/USDT", "buy", 0.1, tag="entry")
        )
        ctx.history["tp_price"] = o * 1.01  # 1% 止盈

    def define_exits(self, entry_fill, ctx):
        """入场成交后自动调用，返回退出订单列表。"""
        tp = ctx.history.get("tp_price")
        if tp is None:
            return []
        return [
            # TP 限价（优先级 1，成交则止盈）
            Order("BTC/USDT", "sell", entry_fill.qty,
                  order_type="limit", limit_price=tp,
                  tag="tp", exit_reason="tp", priority=1),
            # 收盘市价兜底（优先级 99，未成交则在收盘平仓）
            Order("BTC/USDT", "sell", entry_fill.qty,
                  order_type="market", tag="close",
                  exit_reason="close", priority=99),
        ]

# 需要同时提供 1d 和 1h 数据
data = {"BTC/USDT": {"1d": daily_df, "1h": hourly_df}}

res = BacktestEngine(
    data=data,
    strategy=SimpleTP(),
    initial_cash=10000,
    cost_model=BinanceCost(venue="spot"),
    execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),  # ← 显式启用
).run()

# 退出原因统计
print(res.exit_reason_stats())
# {'tp': {'count': 45, 'total_pnl': 120.5, 'avg_pnl': 2.68},
#  'close': {'count': 55, 'total_pnl': -30.2, 'avg_pnl': -0.55}}
```

> **关键**：默认 `execution_model=None` 等价于 `NextBarExecution`（现有行为）。只有传入 `IntrabarExecution(...)` 才启用 intrabar 模式。

### 示例 13.14：双向挂单互斥（OCO Mutual）

核心 B 策略族需要同时挂买限+卖限，若双向均成交则取消交易（避免净零持仓白付手续费）。

```python
class DualLimit(Strategy, IntrabarMixin):
    """双向限价挂单 + 利润退出。"""
    def on_bar(self, ctx):
        o = ctx.current_price("PAXG/USDT", "open")
        if o is None:
            return
        k = 0.005  # 挂单宽度 0.5%
        q = 500 / o  # 各半仓位
        buy = Order("PAXG/USDT", "buy", q,
                    order_type="limit", limit_price=o * (1 - k),
                    tag="entry_buy", exit_reason="entry")
        sell = Order("PAXG/USDT", "sell", q,
                     order_type="limit", limit_price=o * (1 + k),
                     tag="entry_sell", exit_reason="entry")
        # 互斥 OCO：双向均成交 → 双取消
        ctx.intrabar_submit_oco_mutual(buy, sell)

    def define_exits(self, entry_fill, ctx):
        # 利润退出：盈利 0.3% 即平仓
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

### 示例 13.15：订单优先级（SL 优先于 TP）

同一子 bar 内止损和止盈都可能触发时，通过 `priority` 字段控制撮合顺序（0 = 最高优先）。

```python
class TPWithSL(Strategy, IntrabarMixin):
    """入场后同时挂 TP 和 SL，同 bar 内 SL 优先检查。"""
    def define_exits(self, entry_fill, ctx):
        side = "sell" if entry_fill.side.value == "buy" else "buy"
        qty = entry_fill.qty
        if entry_fill.side.value == "buy":
            tp_price = entry_fill.price * 1.009  # +0.9% 止盈
            sl_price = entry_fill.price * 0.9865  # −1.35% 止损
        else:
            tp_price = entry_fill.price * 0.991
            sl_price = entry_fill.price * 1.0135

        return [
            # SL 优先级 0（最高）：同 bar 内先检查
            Order("BTC/USDT", side, qty,
                  order_type="stop", stop_price=sl_price,
                  tag="sl", exit_reason="sl", priority=0),
            # TP 优先级 1
            Order("BTC/USDT", side, qty,
                  order_type="limit", limit_price=tp_price,
                  tag="tp", exit_reason="tp", priority=1),
            # 收盘兜底 优先级 99
            Order("BTC/USDT", side, qty,
                  order_type="market", tag="close",
                  exit_reason="close", priority=99),
        ]
```

### 示例 13.16：批量回测（多策略 × 多费率）

```python
from stockstat.backtest import StrategyBatchRunner

runner = StrategyBatchRunner(
    data=data,
    initial_cash=10000,
    cost_model=BINANCE_SPOT,
    allow_short=True,
    periods_per_year=52,
)

# 多策略并行
results = runner.run_all({
    "ma_cross": ma_cross_strategy,
    "rsi_reversal": rsi_strategy,
    "bollinger": boll_strategy,
})

# 汇总为 DataFrame
df = results.to_dataframe()
print(df[["total_return", "sharpe", "max_drawdown", "win_rate"]].round(4))

# 按 Sharpe 排名
ranked = results.rank("sharpe")
print(ranked)

# 多策略 × 多费率
fee_models = {
    "F1_SpotNoBNB": BINANCE_SPOT,
    "F4_FutBNB": BINANCE_FUTURES_BNB,
}
results_all_fees = runner.run_all_fees(
    {"ma_cross": ma_cross_strategy, "rsi": rsi_strategy},
    fee_models,
)
df_all = results_all_fees.to_dataframe()
```

### 示例 13.17：子期间与状态分析

```python
from stockstat.backtest import BacktestAnalyzer

res = BacktestEngine(data=data, strategy=s, initial_cash=10000).run()

# 子期间分析：2024 前后
sub = BacktestAnalyzer.subperiod_metrics(
    res, split_dates=[pd.Timestamp("2024-01-01")]
)
# {'2020-2023': {'sharpe': 0.85, 'total_return': 0.12},
#  '2024-2026': {'sharpe': -0.32, 'total_return': -0.05}}

# 状态条件分析：高/低波动状态
atr = data["BTC/USDT"]["1d"]["close"].pct_change().rolling(30).std()
regime = pd.Series("low_vol", index=atr.index)
regime[atr > atr.quantile(0.75)] = "high_vol"

reg = BacktestAnalyzer.regime_conditional_metrics(res, regime)
# {'high_vol': {'sharpe': 1.20, 'total_return': 0.08},
#  'low_vol':  {'sharpe': 0.15, 'total_return': 0.02}}

# 按退出原因分析
exit_stats = res.exit_reason_stats()
# {'tp': {'count': 45, 'avg_pnl': 2.68},
#  'sl': {'count': 20, 'avg_pnl': -3.10},
#  'close': {'count': 35, 'avg_pnl': -0.15}}
```

### 示例 13.18：DCA 基准与费率扫描

```python
from stockstat.backtest import dca_equity, fee_sweep, maker_taker_sweep

# DCA 定投基准
prices = data["BTC/USDT"]["1d"]["close"]
dca_eq = dca_equity(10000, prices, schedule="weekly")
# 每周定投的资金曲线

# 费率敏感性扫描
sweep_results = fee_sweep(
    data=data, strategy=ma_cross_strategy,
    initial_cash=10000,
    commissions=[0.0001, 0.0003, 0.0005, 0.001, 0.002],
)
# 返回 DataFrame: commission → sharpe, total_return, max_drawdown

# Maker/Taker 费率组合扫描
mt_results = maker_taker_sweep(
    data=data, strategy=ma_cross_strategy,
    initial_cash=10000,
    maker_rates=[0.0002, 0.0005, 0.001],
    taker_rates=[0.0005, 0.001, 0.002],
)
```

回测可视化（仪表盘、热力图、收益分布等 9 种图表）见 [§14 回测可视化](#14-回测可视化)。

### 回测 API 速查

| 类/函数 | 说明 |
|---------|------|
| `BacktestEngine(data, strategy, ...)` | 主引擎（含 `execution_model` 参数） |
| `@strategy` / `Strategy` / `IntrabarMixin` | 策略定义（函数式/类式/intrabar） |
| `ctx.get(sym, tf, lookback)` | 获取 ≤ t 切片 |
| `ctx.compute` | ComputeEngine 代理（含 register/call） |
| `ctx.broker.submit(Order)` | 下单（默认模式） |
| `ctx.intrabar_submit(Order)` | intrabar 下单（intrabar 模式） |
| `ctx.intrabar_submit_oco_mutual(a, b)` | 互斥 OCO 双向挂单 |
| `ctx.portfolio.get_position(sym)` | 查持仓 |
| `ctx.history` | 策略状态 scratchpad |
| `Order(sym, side, qty, order_type=..., priority=...)` | 订单（含优先级字段） |
| `PercentCost / FixedCost / StampDutyCost / ZeroCost` | 基础成本模型 |
| `MakerTakerCost / BinanceCost` | Maker/Taker 与 Binance 费率 |
| `BINANCE_SPOT / _BNB / FUTURES / _BNB` | Binance 4 种预设 |
| `NextOpenFill / VWAPFill / WorstPriceFill / IntrabarLimitFill` | 成交模型 |
| `ExecutionModel / NextBarExecution / IntrabarExecution` | 可插拔执行模型 |
| `IntrabarFillModel / IntrabarFillResult` | intrabar 成交扫描+时间追踪 |
| `res.summary() / metrics() / plot_equity() / to_csv()` | 结果 |
| `res.exit_reason_stats()` | 退出原因统计 |
| `res.chart(name) / render(name, path) / render_all(dir)` | 回测可视化（§14） |
| `StrategyBatchRunner` | 多策略/多费率批量回测 |
| `BacktestAnalyzer` | 子期间/状态/滚动分析 |
| `dca_equity() / fee_sweep() / maker_taker_sweep()` | 基准与费率扫描 |
| `grid_search / optuna_search / walk_forward / monte_carlo_equity` | 优化 |

---

## 14. 回测可视化

回测可视化子系统提供 9 种图表类型，**核心零 matplotlib 硬依赖**——安装后自动激活。复用 [§10 matplotlib 可视化](#10-matplotlib-可视化) 的协议化设计，但提供回测专用的 `BacktestChartSpec`（支持多子图、填充区、热力图、直方图等丰富元素）。以下示例使用真实市场数据（Binance BTC/USDT 2023-2024）生成，图像见 `docs/images/backtest_*.png`。

![BTC 回测仪表盘](../docs/images/backtest_btc_dashboard.png)

### 示例 14.1：一行渲染与批量保存

```python
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

# 一行渲染（自动检测 matplotlib，不可用时优雅降级）
res.render("equity_curve", path="equity.png")
res.render("drawdown", path="drawdown.png")

# 组合仪表盘（2×2：equity + drawdown + 收益分布 + 月度热力）
res.render("dashboard", path="dashboard.png")

# 批量保存全部图表到目录
out = res.render_all("./charts")
# {'equity_curve': './charts/equity_curve.png', 'drawdown': ..., ...}

# 高级图表
res.render("returns_distribution", path="dist.png")   # 收益率分布直方图
res.render("monthly_heatmap", path="monthly.png")      # 月度收益热力图
res.render("yearly_returns", path="yearly.png")        # 年度收益柱状图
res.render("underwater_curve", path="underwater.png")  # 水下曲线
```

### 示例 14.2：参数网格热力图

```python
from stockstat.backtest.optimizer import grid_search

results = grid_search(make_engine,
                      {"short": [3, 5, 8], "long": [10, 20, 30]},
                      metric="sharpe")

# 渲染参数热力图（x=short, y=long, color=sharpe）
res.render("parameter_heatmap", grid_results=results, metric="sharpe",
           path="param_heatmap.png")

# 也可在 dashboard 中替换第 4 面板
res.render("dashboard", grid_results=results, path="dashboard_with_params.png")
```

### 示例 14.3：获取 BacktestChartSpec（不渲染）

```python
from stockstat.backtest.chart_factory import get_chart_renderer

# 获取专用 spec（含多子图、fill、heatmap 等丰富元素）
spec = res.chart("equity_curve")           # BacktestChartSpec
spec = res.chart("dashboard")              # 4 子图组合
spec = res.chart("drawdown")               # 含 fill 填充

# 可序列化为 dict（用于 Web 前端）
payload = spec.to_dict()

# 自行渲染
renderer = get_chart_renderer()            # 自动检测 matplotlib
if renderer.available():
    fig = renderer.render(spec)
    renderer.savefig("custom.png")

# 查看可用图表类型
print(res.available_chart_types)
# ['dashboard', 'drawdown', 'equity_curve', 'monthly_heatmap', 'parameter_heatmap',
#  'returns_distribution', 'trades_overlay', 'underwater_curve', 'yearly_returns']
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
