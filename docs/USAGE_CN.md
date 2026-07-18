# StockStat 使用文档

> 本文档所有示例均在本地使用真实市场数据（Yahoo Finance + Binance，通过代理）测试通过。预期结果来自 2026-07-18 的实际测试运行。

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
14. [回测高级功能](#14-回测高级功能)
15. [回测可视化](#15-回测可视化)
16. [信号处理与非线性动力学](#16-信号处理与非线性动力学)
17. [v2.0 CLI 命令行](#17-v20-cli-命令行)
18. [v2.0 离线模式](#18-v20-离线模式)
19. [v2.0 插件系统](#19-v20-插件系统)
20. [管理界面](#20-管理界面)

---

## 1. 环境准备

### 安装

```bash
# 后端
cd backend && pip install -e .

# 前端核心库
cd frontend && pip install -e .

# 可选 extras
pip install -e "frontend/[matplotlib]"          # 可视化
pip install -e "frontend/[dsl]"                 # DSL 解析（lark）
pip install -e "frontend/[signal_processing]"   # 小波变换（PyWavelets）
pip install -e "frontend/[backtest_full]"       # 回测全套（matplotlib + optuna）
```

### 开启代理（访问真实数据）

```bash
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889
```

### 启动后端

```bash
# 方式1：uvicorn 直接启动
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000

# 方式2：v2.0 CLI（等价）
stockstat serve --host 0.0.0.0 --port 8000
```

### 指定数据库存储位置（可选）

默认数据存储在后端工作目录下的 `stockstat.db` 文件中。可通过 `DATABASE_URL` 环境变量指定自定义位置：

```bash
# SQLite — 指定绝对路径（注意：sqlite:/// + /abs/path = 4 个斜杠）
export DATABASE_URL="sqlite:////data/stockstat/stockstat.db"

# SQLite — 相对路径（上级目录的 data/ 下）
export DATABASE_URL="sqlite:///../data/stockstat.db"

# PostgreSQL / TimescaleDB
export DATABASE_URL="postgresql://stockstat:password@db-host:5432/stockstat"

# 然后启动
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
```

| `DATABASE_URL` 值 | 实际存储位置 |
|---|---|
| `sqlite:///stockstat.db`（默认） | 当前工作目录下的 `stockstat.db` |
| `sqlite:////data/stockstat.db` | `/data/stockstat.db`（绝对路径） |
| `sqlite:///../data/stockstat.db` | 上级目录的 `data/` 下（相对路径） |
| `postgresql://user:pwd@host:5432/db` | 远程 PostgreSQL 数据库 |

> SQLite 的 URL 格式为 `sqlite:///` + 路径。绝对路径以 `/` 开头，因此拼接后为 4 个斜杠。数据写入指定文件后，服务关闭重启时自动读取先前数据。

### 前端连接

```python
from stockstat import StockStatClient

# 方式1：直接配置（最常用）
client = StockStatClient(host="localhost", port=8000)

# 方式2：环境变量
client = StockStatClient.from_env()

# 方式3：字典配置
client = StockStatClient.from_dict({"host": "localhost", "port": 8000})

# 方式4：连接远程 storage 服务器
client = StockStatClient(host="192.168.1.100", port=8000)
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

### 示例 2.4：通过 CLI 采集（v2.0 新增）

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --end 2024-12-31
```

### 示例 2.5：批量采集分析所需标的

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

### 示例 3.4：通过 CLI 查询（v2.0 新增）

```bash
stockstat query BTC/USDT --limit 5
stockstat query AAPL --start 2024-01-01 --format csv
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

---

## 5. 震荡指标

### 示例 5.1：RSI

```python
rsi = client.compute.rsi(btc.close, window=14)
print(f"RSI 最后5天:\n{rsi.tail(5).round(2)}")
print(f"超买天数 (>70): {(rsi > 70).sum()}")
print(f"超卖天数 (<30): {(rsi < 30).sum()}")
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

### 示例 6.2：ATR

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

### 示例 7.1：Beta

```python
stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")
beta = client.compute.beta(stock.close.pct_change(), market.close.pct_change(), window=60)
print(f"Beta(60日) 均值: {beta.dropna().mean():.4f}")
```

### 示例 7.2：夏普比率

```python
rets = client.compute.returns(btc.close).dropna()
sharpe = client.compute.sharpe(rets, risk_free=0.02, annualize=True)
print(f"BTC 夏普比率（年化）: {sharpe:.4f}")
```

### 示例 7.3：最大回撤

```python
dd = client.compute.max_drawdown(btc.close)
print(f"BTC 最大回撤: {dd:.4f} ({dd*100:.2f}%)")
```

### 示例 7.4：跨资产相关性

```python
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
corr = btc.close.pct_change().corr(eth.close.pct_change())
print(f"BTC/ETH 日收益率相关性: {corr:.4f}")
```

### 示例 7.5：在险价值（VaR）

```python
var_95 = client.compute.var(rets, confidence=0.95)
print(f"95% VaR（日度）: {var_95:.4f} ({var_95*100:.2f}%)")
```

---

## 8. DSL 查询

> DSL 基于 lark，需 `pip install stockstat[dsl]`。v2.0 的 `DslEngine` 从 `PluginRegistry` 自动反射所有已注册指标。

### 示例 8.1：基础 DSL 查询

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20
    FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
print(result)
```

### 示例 8.2：DSL 查询 RSI

```python
result = client.run_dsl('''
    SELECT rsi(close, 14) AS rsi_val
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 10
''')
```

### 示例 8.3：DSL 带 WHERE 过滤

```python
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

### 示例 8.4：DSL 关键字参数

```python
result = client.run_dsl('''
    SELECT close, ma(close, window=20) AS ma20
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
```

---

## 9. 自定义指标

### 示例 9.1：注册自定义指标

```python
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, high_threshold=0.04):
    ret = data.close.pct_change()
    vol = ret.rolling(window).std()
    regime = vol.apply(lambda v: "high" if v > high_threshold else "low")
    return {"regime": regime, "volatility": vol}

result = client.compute.call("volatility_regime", data=btc)
```

### 示例 9.2：通过 v2.0 IndicatorPlugin 注册（自动 DSL 可用）

```python
from stockstat._domain.indicators import IndicatorPlugin
from stockstat._core.plugin import get_registry

reg = get_registry()

def my_indicator(x, window=10):
    """自定义滚动最大值。"""
    return x.rolling(window).max()

reg.register("indicators", "rolling_max",
    IndicatorPlugin("rolling_max", my_indicator, "custom",
                    description="Rolling maximum"))
# 注册后 DSL 自动可用（需 DslEngine.refresh()）
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
spec = client.plot.spec(title="测试", series=[{"name": "x", "data": btc.close}])
renderer.render(spec)  # UserWarning: No plotting backend available
```

---

## 11. PAXG 周末相关性分析

### 分析目标

检验 PAXG（黄金锚定代币）周末涨跌幅（周五收盘→周日收盘）与周一**最大涨幅**和**最大跌幅**之间的独立相关性：

- `max_gain = (最高 - 开盘) / 开盘` — 日内最大上行幅度（恒为正）
- `max_loss = (最低 - 开盘) / 开盘` — 日内最大下行幅度（恒为负）

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

print(f"样本数: {len(result_df)}")
print(f"r(涨幅): {r_gain:.4f}")
print(f"r(跌幅): {r_loss:.4f}")
```

**预期结果**：
```
样本数: 156
r(涨幅): 0.2303, p=0.0038
r(跌幅): -0.2004, p=0.0121
```

### 示例 11.2：散点图

![PAXG 周末散点图](images/paxg_weekend_scatter.png)

### 示例 11.3：方向性分布

![PAXG 方向性](images/paxg_directional.png)

---

## 12. 结果导出

```python
from stockstat.export.serializers import to_json, to_csv, to_dict

json_str = to_json(data)       # DataFrame → JSON 字符串
csv_str = to_csv(data)         # DataFrame → CSV 字符串
records = to_dict(data)        # DataFrame → 字典列表

# PlotSpec → dict（用于 Web 前端）
spec = client.plot.spec(title="我的图表", series=[...])
payload = spec.to_dict()
```

---

## 13. 回测

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

### 示例 13.2：通过 client 便捷入口

```python
res = client.backtest(data, ma_cross, initial_cash=10000, benchmark="BTC/USDT")
# 自动注入 ComputeEngine，策略内 ctx.compute 可用全部指标
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

### 示例 13.4：多标的配对交易 + 做空

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

### 示例 13.5：多时间尺度共振

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

### 示例 13.6：参数网格搜索

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

---

## 14. 回测高级功能

### 示例 14.1：Binance 费率模型（4 种预设）

```python
from stockstat.backtest import BinanceCost, BINANCE_SPOT, BINANCE_SPOT_BNB, \
    BINANCE_FUTURES, BINANCE_FUTURES_BNB, MakerTakerCost

# F1 现货无 BNB:  maker 0.100% / taker 0.100%
# F2 现货+BNB:    maker 0.075% / taker 0.075%  (−25%)
# F3 合约无 BNB:  maker 0.020% / taker 0.050%
# F4 合约+BNB:    maker 0.018% / taker 0.045%  (−10%)

eng = BacktestEngine(data=data, strategy=s,
                     cost_model=BINANCE_FUTURES_BNB, initial_cash=10000)
```

### 示例 14.2：Intrabar 执行（同 bar 入场+出场）

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
        ctx.intrabar_submit(Order("BTC/USDT", "buy", 0.1, tag="entry"))
        ctx.history["tp_price"] = o * 1.01  # 1% 止盈

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

### 示例 14.3：批量回测（多策略 × 多费率）

```python
from stockstat.backtest import StrategyBatchRunner

runner = StrategyBatchRunner(data=data, initial_cash=10000,
                             cost_model=BINANCE_SPOT, allow_short=True)
results = runner.run_all({"ma_cross": s1, "rsi": s2})
df = results.to_dataframe()
ranked = results.rank("sharpe")
```

### 示例 14.4：子期间与状态分析

```python
from stockstat.backtest import BacktestAnalyzer
import pandas as pd

res = BacktestEngine(data=data, strategy=s, initial_cash=10000).run()

# 子期间分析
sub = BacktestAnalyzer.subperiod_metrics(
    res, split_dates=[pd.Timestamp("2024-01-01")]
)

# 状态条件分析
reg = BacktestAnalyzer.regime_conditional_metrics(res, regime_series)

# 按退出原因分析
exit_stats = res.exit_reason_stats()
```

### 示例 14.5：DCA 基准与费率扫描

```python
from stockstat.backtest import dca_equity, fee_sweep, maker_taker_sweep

dca_eq = dca_equity(10000, prices, schedule="weekly")
sweep = fee_sweep(data=data, strategy=s, commissions=[0.0001, 0.0003, 0.0005])
mt = maker_taker_sweep(data=data, strategy=s,
                       maker_rates=[0.0002, 0.0005], taker_rates=[0.0005, 0.001])
```

---

## 15. 回测可视化

```python
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

# 一行渲染
res.render("equity_curve", path="equity.png")
res.render("drawdown", path="drawdown.png")

# 组合仪表盘（2×2）
res.render("dashboard", path="dashboard.png")

# 批量保存
res.render_all("./charts")

# 高级图表
res.render("returns_distribution", path="dist.png")
res.render("monthly_heatmap", path="monthly.png")
res.render("yearly_returns", path="yearly.png")

# 参数网格热力图
from stockstat.backtest.optimizer import grid_search
results = grid_search(make_engine, {"short": [3,5,8], "long": [10,20,30]}, metric="sharpe")
res.render("parameter_heatmap", grid_results=results, path="param.png")
```

![BTC 回测仪表盘](../docs/images/backtest_btc_dashboard.png)

---

## 16. 信号处理与非线性动力学

> 需要 `pip install stockstat[signal_processing]`。未安装 PyWavelets 时 CWT 自动降级为 FFT 自实现 Morlet。

### 示例 16.1：小波多尺度分解

```python
import numpy as np

signal = data.close.values[-48:]
scales = np.arange(1, 25)
coef, scales = client.compute.wavelet_decompose(signal, scales=scales, wavelet="morl")
print(f"CWT 系数形状: {coef.shape}")  # (24, 48)
```

### 示例 16.2：谱熵

```python
h_spec = client.compute.spectral_entropy(np.diff(np.log(data.close.values[-100:])))
print(f"谱熵: {h_spec:.4f}")
```

### 示例 16.3：灰色关联度

```python
path_a = data.close.values[-48:]
path_b = data.close.values[-96:-48]
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)
print(f"灰色关联度: {gr:.4f}")  # [0, 1]，1 = 完全相似
```

### 示例 16.4：Hurst 指数

```python
hurst = client.compute.hurst_dfa(np.diff(np.log(data.close.values[-500:])))
print(f"Hurst 指数: {hurst:.4f}")
# ≈ 0.5: 随机游走 | > 0.5: 持久性 | < 0.5: 反持久性
```

### 示例 16.5：传递熵

```python
btc = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")

btc_rets = np.diff(np.log(btc.close.values))[:200]
eth_rets = np.diff(np.log(eth.close.values))[:200]

te = client.compute.transfer_entropy(btc_rets, eth_rets, k=1)
print(f"TE(BTC→ETH): {te:.4f} bits")
```

### 示例 16.6：可视化——CWT 时频热力图

```python
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
renderer = client.plot.get_renderer()
renderer.render(spec)
renderer.savefig("cwt_scalogram.png")
```

### 示例 16.7：可视化——DFA 拟合图

```python
spec = client.compute.dfa_fit(np.diff(np.log(signal)))
renderer = client.plot.get_renderer()
renderer.render(spec)
renderer.savefig("dfa_fit.png")
```

---

## 17. v2.0 CLI 命令行

v2.0 新增 `stockstat` CLI 命令行工具，无需写 Python 脚本即可完成常用操作。

### 示例 17.1：启动 API 服务器

```bash
stockstat serve --host 0.0.0.0 --port 8000
```

### 示例 17.2：命令行采集数据

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --end 2024-12-31
```

输出：
```json
{"symbol": "AAPL", "source": "yfinance", "ingested": 251}
```

### 示例 17.3：查询数据

```bash
# 表格格式（默认）
stockstat query BTC/USDT --limit 5

# JSON 格式
stockstat query BTC/USDT --format json

# CSV 格式
stockstat query AAPL --start 2024-01-01 --format csv
```

### 示例 17.4：列出已注册插件

```bash
# 列出全部插件
stockstat plugins

# 按命名空间过滤
stockstat plugins --namespace indicators
stockstat plugins --namespace sources
stockstat plugins --namespace cost_models
```

输出示例：
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

### 示例 17.5：列出已注册指标

```bash
# 全部指标
stockstat indicators

# 按类别过滤
stockstat indicators --category trend
stockstat indicators --category nonlinear
```

---

## 18. v2.0 离线模式

v2.0 的 `V2Client` 支持离线模式，直接使用本地 Storage，无需启动后端 HTTP 服务。适用于：
- 在 Jupyter 中分析预加载数据
- 无网络环境下的回测
- 单元测试

### 示例 18.1：离线模式基本用法

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage
from stockstat._core.contracts import DataSchema, FieldDef

# 创建本地存储并写入数据
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

# 离线客户端
client = V2Client(mode="offline", storage=storage)

# 查询数据（从本地 Storage，不经过 HTTP）
df = client.ohlcv("BTC")
print(df)
```

### 示例 18.2：离线模式计算与回测

```python
# 计算指标（本地 ComputeEngine）
ma = client.compute.ma(df.close, window=2)

# 运行回测（本地 BacktestEngine）
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

### 示例 18.3：离线模式限制

```python
# 离线模式不能采集数据（需在线模式）
try:
    client.ingest("BTC/USDT")
except RuntimeError as e:
    print(e)  # "Ingest requires online mode"
```

---

## 19. v2.0 插件系统

v2.0 的所有可扩展点统一注册到 `PluginRegistry`。

### 示例 19.1：注册自定义指标插件

```python
from stockstat._domain.indicators import IndicatorPlugin
from stockstat._core.plugin import get_registry

reg = get_registry()

def rolling_max(x, window=10):
    """滚动最大值。"""
    return x.rolling(window).max()

plugin = IndicatorPlugin(
    name="rolling_max",
    func=rolling_max,
    category="custom",
    description="Rolling maximum",
)
reg.register("indicators", "rolling_max", plugin)

# 查询
print(reg.get("indicators", "rolling_max"))
```

### 示例 19.2：DSL 自动反射新指标

```python
from stockstat._api.dsl import DslEngine

engine = DslEngine(reg, client=mock_client)
engine.refresh()  # 从 registry 重新加载函数表

# rolling_max 现在 DSL 可用
result = engine.eval('''
    SELECT close, rolling_max(close, 5) AS rmax
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
```

### 示例 19.3：注册自定义回测组件

```python
from stockstat._domain.backtest import BacktestComponentPlugin

# 假设有一个自定义成本模型
class MyCostModel:
    def __init__(self, rate=0.001):
        self.rate = rate
    def compute(self, qty, price, side):
        return abs(qty * price * self.rate)

reg.register("cost_models", "my_cost",
    BacktestComponentPlugin("my_cost", MyCostModel, "cost",
                            description="Custom cost model"))
```

### 示例 19.4：列出所有插件

```python
for item in reg.list():
    plugin = item["plugin"]
    print(f"{item['namespace']:<20} {item['name']:<25} {getattr(plugin, 'category', '')}")
```

### 示例 19.5：主题系统

```python
from stockstat._viz.themes import get_theme, register_theme, Theme, list_themes

# 内置主题
print(list_themes())  # ['default', 'dark', 'publication']

dark = get_theme("dark")
print(dark.background)  # '#1e1e1e'

# 注册自定义主题
custom = Theme("ocean", background="#0a1929", primary="#64ffda",
               secondary="#ff6b6b", grid="#1c3a5e")
register_theme(custom)
print(get_theme("ocean").primary)  # '#64ffda'
```

---

## 20. 管理界面

StockStat 提供两种管理界面用于管理 Storage Server 上的数据：TUI 终端界面和网页管理界面。

### 20.1 TUI 终端管理界面

`stockstat tui` 提供交互式终端界面，用于浏览和管理 Storage Server 上的数据。

#### 示例 20.1：启动 TUI

```bash
# 连接本地服务器
stockstat tui

# 连接远程服务器
stockstat tui --host 192.168.1.100 --port 8000
```

启动后显示交互式菜单：

```
┌─────────────────────────────────────────┐
│     StockStat Storage Manager           │
│  Server: localhost:8000  Status: ONLINE │
└─────────────────────────────────────────┘

Menu:
  1. Browse symbols
  2. Query OHLCV data
  3. Ingest new data
  4. Data statistics
  5. List data sources
  6. View proxy config
  q. Quit
```

#### 示例 20.2：浏览标的

选择菜单 `1` 后，显示已注册标的表格：

```
Registered Symbols
├──────────┬────────┬──────┬──────┬──────────┐
│ Symbol   │ Type   │ Base │ Quote│ Sources  │
├──────────┼────────┼──────┼──────┼──────────┤
│ BTC/USDT │ crypto │ BTC  │ USDT │ binance  │
│ ETH/USDT │ crypto │ ETH  │ USDT │ binance  │
│ AAPL     │ stock  │ AAPL │      │ yfinance │
└──────────┴────────┴──────┴──────┴──────────┘
```

#### 示例 20.3：采集数据

选择菜单 `3`，交互式输入参数：

```
Symbol to ingest: PAXG/USDT
Source (blank=auto):
Start date (blank=skip): 2022-01-01
End date (blank=skip): 2024-12-31
Timeframe: 1d

Ingesting PAXG/USDT...
Done! {'symbol': 'PAXG/USDT', 'source': 'binance', 'ingested': 1095}
```

> 推荐安装 `pip install rich` 以获得彩色表格体验。未安装时自动降级为纯文本菜单。

### 20.2 网页管理界面（Admin Plugin）

Storage Server 内置网页管理界面（可插拔 plugin，由 `STOCKSTAT_ADMIN_ENABLED` 控制，默认开启），浏览器访问即可管理。

#### 示例 20.4：访问网页管理界面

```bash
# 启动 Storage Server
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000

# 浏览器访问
# http://localhost:8000/admin/        (本地)
# http://192.168.1.100:8000/admin/    (远程)
```

#### 功能一览

| 页面 | 功能 |
|------|------|
| **Overview** | 概览仪表盘：标的数、行数、按来源分布、健康状态 |
| **Symbols** | 标的列表：行数、时间范围、删除按钮 |
| **Ingest** | 采集数据：输入 symbol/source/date/timeframe |
| **Config** | 配置查看：DB URL（密码脱敏）、代理、缓存 |
| **Sources** | 数据源列表：名称、类型、描述 |

#### 示例 20.5：通过 Admin API 采集数据

```bash
# 通过 curl 采集
curl -X POST "http://localhost:8000/admin/api/ingest?symbol=BTC/USDT&source=binance&start=2024-01-01&timeframe=1d"

# 响应
# {"symbol":"BTC/USDT","source":"binance","ingested":366}
```

#### 示例 20.6：查看数据统计

```bash
curl http://localhost:8000/admin/api/stats
# {"total_symbols":5,"total_rows":1234,"symbols_by_source":{"binance":3,"yfinance":2}}
```

#### 示例 20.7：删除标的数据

```bash
curl -X DELETE http://localhost:8000/admin/api/symbols/BTC/USDT
# {"deleted":true,"symbol":"BTC/USDT","rows_removed":366}
```

---

## 附录：环境变量

### 后端

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | 数据库 URL |
| `REDIS_URL` | （空） | Redis 连接（可选） |
| `HOST` | `0.0.0.0` | 后端监听地址 |
| `PORT` | `8000` | 后端监听端口 |
| `STOCKSTAT_DEFAULT_SOURCE` | `yfinance` | 默认数据源 |
| `STOCKSTAT_PROXY_ENABLED` | `false` | 启用代理 |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` 或 `socks5` |
| `STOCKSTAT_PROXY_URL` | 自动 | 代理地址 |
| `STOCKSTAT_ADMIN_ENABLED` | `true` | 是否启用网页管理界面 |

### 前端

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKSTAT_HOST` | `localhost` | 前端主机 |
| `STOCKSTAT_PORT` | `8000` | 前端端口 |
| `STOCKSTAT_API_KEY` | （空） | 可选 API key |
| `STOCKSTAT_TIMEOUT` | `30` | HTTP 超时秒数 |
| `STOCKSTAT_USE_HTTPS` | `false` | 是否使用 HTTPS |
