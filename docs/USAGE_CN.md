# StockStat 使用文档

> 本文档所有示例均在本地使用真实市场数据（Yahoo Finance + Binance，通过代理）测试通过。预期结果来自 2026-07-18 的实际测试运行。

## 目录

1. [环境准备](#1-环境准备)
2. [数据采集](#2-数据采集)
3. [查询 OHLCV 数据](#3-查询-ohlcv-数据)
4. [计算指标](#4-计算指标)
5. [DSL 查询](#5-dsl-查询)
6. [自定义指标](#6-自定义指标)
7. [可视化](#7-可视化)
8. [回测](#8-回测)
9. [回测高级功能](#9-回测高级功能)
10. [信号处理与非线性动力学](#10-信号处理与非线性动力学)
11. [结果导出](#11-结果导出)
12. [v2.0 CLI 命令行](#12-v20-cli-命令行)
13. [离线模式](#13-离线模式)
14. [插件系统](#14-插件系统)
15. [管理界面](#15-管理界面)
16. [PAXG 周末相关性分析](#16-paxg-周末相关性分析)
17. [连接与性能测试](#17-连接与性能测试)
18. [启动脚本](#18-启动脚本)

---

## 1. 环境准备

### 安装

项目包含两个独立 pip 包：`stockstat-backend`（存储后端服务）和 `stockstat`（计算前端库）。两者均可通过 `pip install -e .` 以开发模式安装。

```bash
# 后端（FastAPI + SQLAlchemy + 数据源适配器）
cd backend && pip install -e .

# 前端核心库（ComputeEngine + 回测 + DSL + 可视化 + CLI/TUI）
cd frontend && pip install -e .

# 可选 extras（按需安装）
pip install -e "frontend/[matplotlib]"          # 可视化（matplotlib 延迟导入，核心零依赖）
pip install -e "frontend/[dsl]"                 # DSL 解析器（lark，EBNF 语法）
pip install -e "frontend/[signal_processing]"   # 小波变换（PyWavelets，CWT 完整实现）
pip install -e "frontend/[backtest_full]"       # 回测全套（matplotlib + optuna 参数优化）
pip install rich                                # TUI 彩色表格（未安装时降级纯文本）
```

> 前端库的核心依赖仅有 pandas / numpy / scipy / httpx / pyarrow，不强制依赖 matplotlib / lark / PyWavelets。未安装可选 extras 时，相关功能会优雅降级（如 CWT 降级为 FFT 自实现 Morlet，可视化降级为 NullRenderer 发告警不崩溃）。

### 开启代理（访问真实数据源）

后端默认直连 Yahoo Finance / Binance API。如果在中国大陆等地区需要代理：

```bash
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http                    # 或 socks5
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889    # 你的代理地址
```

代理配置对后端的所有数据源适配器（yfinance / ccxt）生效。修改后需重启后端服务。

### 启动后端

```bash
# 方式1：uvicorn 直接启动（最透明）
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000

# 方式2：v2.0 CLI（等价，更简洁，自动加载 Admin Plugin）
stockstat serve --host 0.0.0.0 --port 8000
```

后端启动后：
- REST API 在 `http://localhost:8000/api/v1/*` 可用
- 网页管理界面在 `http://localhost:8000/admin/` 可用（由 `STOCKSTAT_ADMIN_ENABLED` 控制，默认开启）
- 默认使用 SQLite（`stockstat.db`），数据持久化到文件，关闭后重启自动读取

### 指定数据库存储位置

默认数据存储在后端工作目录下的 `stockstat.db` 文件中。可通过 `DATABASE_URL` 环境变量指定自定义位置：

```bash
# SQLite — 指定绝对路径（注意：sqlite:/// + /abs/path = 4 个斜杠）
export DATABASE_URL="sqlite:////data/stockstat/stockstat.db"

# SQLite — 相对路径（上级目录的 data/ 下）
export DATABASE_URL="sqlite:///../data/stockstat.db"

# PostgreSQL / TimescaleDB（Docker 生产环境）
export DATABASE_URL="postgresql://stockstat:password@db-host:5432/stockstat"
```

| `DATABASE_URL` 值 | 实际存储位置 |
|---|---|
| `sqlite:///stockstat.db`（默认） | 当前工作目录下的 `stockstat.db` |
| `sqlite:////data/stockstat.db` | `/data/stockstat.db`（绝对路径，4 个斜杠） |
| `sqlite:///../data/stockstat.db` | 上级目录的 `data/` 下（相对路径） |
| `postgresql://user:pwd@host:5432/db` | 远程 PostgreSQL 数据库 |

> SQLite 的 URL 格式为 `sqlite:///` + 路径。绝对路径以 `/` 开头，因此拼接后为 4 个斜杠 `sqlite:////abs/path`。数据写入指定文件后，服务关闭重启时自动读取先前数据。

### 前端连接

```python
from stockstat import StockStatClient

# 方式1：直接配置（最常用）
client = StockStatClient(host="localhost", port=8000)

# 方式2：从环境变量读取（STOCKSTAT_HOST / STOCKSTAT_PORT / STOCKSTAT_API_KEY 等）
client = StockStatClient.from_env()

# 方式3：字典配置
client = StockStatClient.from_dict({"host": "localhost", "port": 8000})

# 方式4：连接远程 storage 服务器（存储-计算分离部署）
client = StockStatClient(host="192.168.1.100", port=8000)

# 方式5：使用 API Key 认证（如果后端配置了 Bearer auth）
client = StockStatClient(host="192.168.1.100", port=8000, api_key="my-secret-key")
```

前端通过 `httpx` 库发送 HTTP 请求到后端 REST API。连接超时默认 30 秒，可通过 `timeout` 参数调整。

---

## 2. 数据采集

数据采集是后端的能力：前端调用 `client.ingest()` → HTTP POST → 后端适配器从数据源拉取 → 标准化 → 存入数据库。支持 4 种数据源，自动检测数据源类型（含 `/` → 加密货币 binance，否则 → 股票 yfinance）。

### 示例 2.1：采集股票数据

```python
result = client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
print(result)
```

**预期结果**：
```python
{'symbol': 'AAPL', 'source': 'yfinance', 'ingested': 251}
```

返回值 `ingested` 是实际写入数据库的行数。如果同一标的同一时间段已采集过，会执行 upsert（按 `(symbol, ts, timeframe, source)` 联合唯一约束去重更新），不会产生重复数据。

### 示例 2.2：采集加密货币数据

```python
result = client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
print(result)
```

**预期结果**：
```python
{'symbol': 'BTC/USDT', 'source': 'binance', 'ingested': 366}
```

加密货币 7×24 小时交易，2024 年有 366 天（闰年），因此日线数据有 366 行。Binance 通过 ccxt 库接入，支持分页拉取（每页 1000 根，自动翻页直到拉完指定范围）。

### 示例 2.3：自动检测数据源

不指定 `source` 参数时，系统按标的符号格式自动检测：

```python
# 股票符号（无"/"）→ yfinance
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")

# 加密货币符号（含"/"）→ binance
client.ingest("ETH/USDT", start="2024-01-01", end="2024-12-31")
```

### 示例 2.4：更细时间粒度

Binance 支持 16 种时间粒度（从 1 秒到 1 月），yfinance 支持 12 种（从 1 分钟到 3 个月）。通过 `timeframe` 参数指定：

```python
# Binance: 1s / 1m / 3m / 5m / 15m / 30m / 1h / 2h / 4h / 6h / 8h / 12h / 1d / 3d / 1w / 1M
client.ingest("BTC/USDT", source="binance", start="2024-06-01", end="2024-06-02", timeframe="1m")
# 1 分钟数据，2 天约 2880 行

# yfinance: 1m / 2m / 5m / 15m / 30m / 60m / 90m / 1d / 5d / 1wk / 1mo / 3mo
client.ingest("AAPL", source="yfinance", start="2024-06-01", end="2024-06-07", timeframe="5m")
# 5 分钟数据，美股交易时段约 390 行/天 × 5 天
```

> **存储估算**：1 分钟粒度 1 年约 15 MB，1 秒粒度 1 年约 900 MB。Binance 全部 1,479 个 USDT 交易对 1 分钟数据 1 年约 22 GB。SQLite 适合单机小规模；GB 级建议切换 TimescaleDB + Hypertable 压缩。

### 示例 2.5：下载任意 yfinance 标的

Yahoo Finance 没有公开的"列出所有标的"API，但支持任意有效 ticker。除网页管理界面提供 85 个精选标的外，用户可直接下载任意标的：

```python
# 中国 A 股（上海证券交易所）
client.ingest("600519.SS", source="yfinance", start="2020-01-01", end="2024-12-31")  # 贵州茅台

# 汇率
client.ingest("USDCNY=X", source="yfinance", start="2022-01-01", end="2024-12-31")  # 美元/人民币

# 商品期货
client.ingest("GC=F", source="yfinance", start="2020-01-01", end="2024-12-31")      # 黄金期货
client.ingest("CL=F", source="yfinance", start="2020-01-01", end="2024-12-31")      # 原油期货

# 港股
client.ingest("0700.HK", source="yfinance", start="2020-01-01", end="2024-12-31")   # 腾讯控股
```

### 示例 2.6：通过 CLI 采集

无需写 Python 脚本，直接命令行采集：

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

输出：
```json
{"symbol": "AAPL", "source": "yfinance", "ingested": 251}
```

### 示例 2.7：批量采集分析所需标的

一次采集多个标的，为后续分析做准备：

```python
symbols = [
    ("AAPL", "yfinance", "2023-01-01", "2024-12-31"),
    ("^GSPC", "yfinance", "2023-01-01", "2024-12-31"),    # S&P 500 指数（作为市场基准）
    ("BTC/USDT", "binance", "2024-01-01", "2024-12-31"),
    ("ETH/USDT", "binance", "2024-01-01", "2024-12-31"),
    ("PAXG/USDT", "binance", "2022-01-01", "2024-12-31"),  # PAXG 周末效应研究需要更长历史
]
for sym, source, start, end in symbols:
    result = client.ingest(sym, source=source, start=start, end=end)
    print(f"{sym}: {result['ingested']} rows")
```

---

## 3. 查询 OHLCV 数据

查询是前端通过 HTTP GET 从后端拉取已存储的数据。返回 pandas DataFrame，时间索引按升序排列（UTC 时区）。

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

DataFrame 的索引是 `ts`（UTC 时间戳），列包含 `open / high / low / close / volume`。`limit=5` 表示只返回最近 5 条（按时间升序排列）。

### 示例 3.2：双向分页查询（懒加载场景）

`order` 参数支持双向分页，用于 K 线图懒加载场景：

```python
# 最近 500 根（K 线图初始加载）
recent = client.ohlcv("BTC/USDT", limit=500, order="desc")

# 更早的 1000 根（用户向左滚动时加载）
earlier = client.ohlcv("BTC/USDT", end="2024-01-01", limit=1000, order="desc")

# 更晚的 1000 根（用户向右滚动时加载）
later = client.ohlcv("BTC/USDT", start="2024-06-01", limit=1000, order="asc")
```

> 无论 `order=asc` 还是 `desc`，返回的 DataFrame 内部都按时间升序排列，方便下游消费。`order=desc` 时 `limit=N` 返回的是**最近 N 根**（从最新往回数），而非最旧 N 根。网页管理界面的 K 线图懒加载正是基于此参数实现。

### 示例 3.3：批量查询

一次查询多个标的，返回字典：

```python
batch = client.ohlcv_batch(["BTC/USDT", "ETH/USDT"], start="2024-01-01")
btc = batch["BTC/USDT"]
eth = batch["ETH/USDT"]
print(f"BTC: {len(btc)} rows, ETH: {len(eth)} rows")
```

### 示例 3.4：列出已注册符号

查看数据库中已有哪些标的：

```python
for s in client.symbols():
    print(f"{s['unified_symbol']:15s} {s['asset_type']:8s} {s['sources']}")
```

输出示例：
```
BTC/USDT       crypto   ['binance']
ETH/USDT       crypto   ['binance']
AAPL           stock    ['yfinance']
```

### 示例 3.5：通过 CLI 查询

```bash
# 表格格式（默认，适合终端查看）
stockstat query BTC/USDT --limit 5

# JSON 格式（适合管道处理）
stockstat query BTC/USDT --format json

# CSV 格式（适合导出到文件）
stockstat query AAPL --start 2024-01-01 --format csv > aapl.csv
```

---

## 4. 计算指标

`client.compute` 是 `ComputeEngine` 实例，提供 23 个内置指标。所有指标接受 pandas Series 输入，返回 Series 或标量。指标计算完全在前端进程内完成，不需要 HTTP 请求。

### 趋势指标

```python
# 简单移动平均（Simple Moving Average）
ma20 = client.compute.ma(data.close, window=20)
print(f"MA(20) 最新值: {ma20.iloc[-1]:.2f}")

# 指数移动平均（Exponential Moving Average）— 近期数据权重更高
ema12 = client.compute.ema(data.close, window=12)

# MACD（Moving Average Convergence Divergence）— 返回 3 条线
macd_line, signal_line, hist = client.compute.macd(data.close)
# macd_line: MACD 线（快慢均线差）
# signal_line: 信号线（MACD 线的 9 日 EMA）
# hist: 柱状图（MACD 线 - 信号线）
print(f"MACD: {macd_line.iloc[-1]:.2f}, Signal: {signal_line.iloc[-1]:.2f}, Hist: {hist.iloc[-1]:.2f}")
```

### 震荡指标

```python
# RSI（Relative Strength Index）— 0~100，>70 超买，<30 超卖
rsi = client.compute.rsi(data.close, window=14)
print(f"RSI 最后5天:\n{rsi.tail(5).round(2)}")
print(f"超买天数 (>70): {(rsi > 70).sum()}")
print(f"超卖天数 (<30): {(rsi < 30).sum()}")

# KDJ — 返回 K、D、J 三条线
k, d, j = client.compute.kdj(data.high, data.low, data.close, window=9)
print(f"K: {k.iloc[-1]:.2f}, D: {d.iloc[-1]:.2f}, J: {j.iloc[-1]:.2f}")
```

### 波动率指标

```python
# 布林带（Bollinger Bands）— 返回上轨、中轨、下轨三条线
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
print(f"上轨: {upper.iloc[-1]:.2f}")
print(f"中轨: {mid.iloc[-1]:.2f}")   # 中轨 = MA(20)
print(f"下轨: {lower.iloc[-1]:.2f}")  # 下轨 = 中轨 - 2×Std(20)

# ATR（Average True Range）— 衡量波动幅度
atr = client.compute.atr(data.high, data.low, data.close, window=14)
print(f"ATR(14): {atr.iloc[-1]:.2f}")

# 滚动标准差 — 波动率的直接度量
std = client.compute.std(data.close, window=20)
print(f"20日波动率: {std.iloc[-1]:.2f}")
```

### 统计指标

```python
# Beta — 标的相对于市场基准的系统性风险
stock = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
market = client.ohlcv("^GSPC", start="2023-01-01", timeframe="1d")  # S&P 500
beta = client.compute.beta(stock.close.pct_change(), market.close.pct_change(), window=60)
print(f"Beta(60日) 均值: {beta.dropna().mean():.4f}")
# Beta > 1: 比市场波动更大；Beta < 1: 比市场波动更小

# Sharpe 比率 — 风险调整后收益
rets = client.compute.returns(data.close).dropna()
sharpe = client.compute.sharpe(rets, risk_free=0.02, annualize=True)
print(f"BTC 夏普比率（年化）: {sharpe:.4f}")
# Sharpe > 1: 良好；> 2: 优秀

# 最大回撤 — 从历史最高点到最低点的最大跌幅
dd = client.compute.max_drawdown(data.close)
print(f"BTC 最大回撤: {dd:.4f} ({dd*100:.2f}%)")

# 在险价值（VaR）— 给定置信水平下的最大潜在损失
var_95 = client.compute.var(rets, confidence=0.95)
print(f"95% VaR（日度）: {var_95:.4f} ({var_95*100:.2f}%)")
# 含义：有 95% 的把握，单日损失不超过此值

# Pearson 相关系数
eth = client.ohlcv("ETH/USDT", start="2024-01-01", timeframe="1d")
corr = client.compute.corr(btc.close.pct_change().dropna(), eth.close.pct_change().dropna())
print(f"BTC/ETH 日收益率相关性: {corr:.4f}")
```

### 金叉 / 死叉

利用移动平均线的交叉判断趋势变化：

```python
ma_short = data.close.rolling(5).mean()   # 短期均线
ma_long = data.close.rolling(20).mean()   # 长期均线

# 金叉：短期均线从下方穿越长期均线（看涨信号）
golden_cross = (ma_short > ma_long) & (ma_short.shift(1) <= ma_long.shift(1))
# 死叉：短期均线从上方穿越长期均线（看跌信号）
death_cross = (ma_short < ma_long) & (ma_short.shift(1) >= ma_long.shift(1))

print(f"金叉次数: {golden_cross.sum()}")
print(f"死叉次数: {death_cross.sum()}")
```

---

## 5. DSL 查询

> DSL 基于 lark 库解析，需 `pip install stockstat[dsl]`。v2.0 的 `DslEngine` 从 `PluginRegistry` 自动反射全部 23 个已注册指标作为 DSL 函数，取代 v1.7 手动维护的 `_BUILTIN_FUNCS` 字典（15 个函数）。当 v2.0 层不可用时，自动 fallback 到 v1.7 `Evaluator`。

DSL 是一种 SQL-like 声明式查询语言，语法为 `SELECT ... FROM ohlcv(...) WHERE ... LIMIT ...`。它将数据查询和指标计算合为一步，适合快速探索性分析。

### 示例 5.1：基础 DSL 查询

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20
    FROM ohlcv("AAPL", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
print(result)
```

`ohlcv()` 函数的参数依次为：标的符号、时间粒度、开始日期、结束日期。`AS` 关键字为计算列指定别名。

### 示例 5.2：DSL 查询 RSI

```python
result = client.run_dsl('''
    SELECT rsi(close, 14) AS rsi_val
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 10
''')
```

### 示例 5.3：DSL 带 WHERE 过滤

```python
# 只看收盘价大于 100000 的交易日
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

### 示例 5.4：DSL 关键字参数

DSL 支持关键字参数语法：

```python
result = client.run_dsl('''
    SELECT close, ma(close, window=20) AS ma20
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
```

> v2.0 `DslEngine` 比 v1.7 多支持 8 个非线性指标（`wavelet_decompose`、`spectral_entropy`、`grey_relation`、`gm11_predict`、`transfer_entropy`、`hurst_dfa`、`sample_entropy`、`permutation_entropy`）。注册新指标到 `PluginRegistry` 后，调用 `engine.refresh()` 即可 DSL 自动可用。

---

## 6. 自定义指标

### 通过 ComputeEngine 注册（Python 库内使用）

用 `@client.compute.register` 装饰器注册自定义指标，之后可通过 `client.compute.call()` 调用：

```python
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, high_threshold=0.04):
    """识别高/低波动率状态。

    当 20 日滚动标准差 > 4% 时标记为 "high"，否则为 "low"。
    返回 dict 包含 regime 标签和波动率序列。
    """
    ret = data.close.pct_change()
    vol = ret.rolling(window).std()
    regime = vol.apply(lambda v: "high" if v > high_threshold else "low")
    return {"regime": regime, "volatility": vol}

# 调用自定义指标
result = client.compute.call("volatility_regime", data=btc)
print(result["regime"].value_counts())  # 统计高/低波动率天数
```

### 通过 v2.0 IndicatorPlugin 注册（DSL 自动可用）

通过 `IndicatorPlugin` 注册到 `PluginRegistry` 后，DSL 引擎可自动反射：

```python
from stockstat._domain.indicators import IndicatorPlugin
from stockstat._core.plugin import get_registry

reg = get_registry()

def rolling_max(x, window=10):
    """滚动最大值。"""
    return x.rolling(window).max()

reg.register("indicators", "rolling_max",
    IndicatorPlugin("rolling_max", rolling_max, "custom",
                    description="Rolling maximum"))

# 注册后刷新 DSL 引擎即可使用
from stockstat._api.dsl import DslEngine
engine = DslEngine(reg, client=client._data_client)
engine.refresh()

# rolling_max 现在 DSL 可用
result = engine.eval('''
    SELECT close, rolling_max(close, 5) AS rmax
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 5
''')
```

> v1.7 新增指标需改 3 处（写函数 → ComputeEngine 加方法 → DSL `_BUILTIN_FUNCS` 加映射）；v2.0 只需写一个 `IndicatorPlugin` 并注册，DSL 自动可用。

---

## 7. 可视化

可视化层基于协议化设计：`PlotSpec` 是后端无关的绘图规格，`Renderer` 负责实际渲染。核心库零硬依赖 matplotlib，未安装时降级为 `NullRenderer`（发 UserWarning，不崩溃）。

### 协议化绘图

通过 `client.plot.spec()` 构建 `PlotSpec`，再用 `client.plot.get_renderer()` 获取渲染器渲染：

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
renderer = client.plot.get_renderer("matplotlib")  # 指定 matplotlib；不传则自动检测
fig = renderer.render(spec)
renderer.savefig("btc.png")
```

`series` 中每条系列支持 `kind: line / bar / scatter / fill / histogram / heatmap`，可设置 `color`、`alpha`、`secondary_y` 等属性。

### 直接使用 matplotlib

也可以绕过协议层，直接用 matplotlib 绘图，配合 `client.compute` 计算指标：

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(btc.index, btc.close, label="收盘价", color="black")

# 用 ComputeEngine 计算布林带
upper, mid, lower = client.compute.bollinger(btc.close, 20, 2.0)
ax.fill_between(btc.index, lower, upper, alpha=0.15, color="blue", label="布林带")
ax.plot(btc.index, mid, color="blue", linestyle="--", label="MA20")

ax.set_title("BTC/USDT 布林带")
ax.set_xlabel("日期")
ax.set_ylabel("价格 (USDT)")
ax.legend()
ax.grid(True, alpha=0.3)
plt.savefig("btc_bollinger.png", dpi=150)
```

![BTC 布林带](images/btc_bollinger.png)

### 其他经典图表

以下是使用真实市场数据生成的经典统计图表：

![BTC RSI](images/btc_rsi.png)

![ETH MACD](images/eth_macd.png)

![BTC 回撤](images/btc_drawdown.png)

![AAPL Beta 散点图](images/aapl_beta_scatter.png)

![BTC ETH 相关性](images/btc_eth_corr.png)

![价格对比](images/price_comparison.png)

### NullRenderer（无 matplotlib 时）

未安装 matplotlib 时，`get_renderer()` 返回 `NullRenderer`，调用 `render()` 会发出 UserWarning 但不会崩溃：

```python
renderer = client.plot.get_renderer("null")
spec = client.plot.spec(title="测试", series=[{"name": "x", "data": btc.close}])
renderer.render(spec)  # UserWarning: No plotting backend available
```

这使得在无图形环境（如服务器）中运行回测代码不会报错。

---

## 8. 回测

回测子系统位于 `stockstat.backtest`（28 个文件），是功能完整的量化回测引擎。支持：多标的交易组、多时间尺度 K 线、6 种订单类型（市价/限价/止损/移动止损/OCO/互斥 OCO）、8 种成本模型、7 种成交模型、可插拔执行模型（`NextBarExecution`/`IntrabarExecution`）、做空、未来函数防护、参数网格搜索、批量回测。

### 最简回测（函数式策略）

用 `@strategy` 装饰器将普通函数变为策略，函数接收 `ctx`（回测上下文）：

```python
from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost

client = StockStatClient(host="localhost", port=8000)
data = {"BTC/USDT": {"1d": client.ohlcv("BTC/USDT", start="2024-01-01")}}

@strategy
def ma_cross(ctx):
    """双均线交叉策略：MA5 上穿 MA20 买入，下穿卖出。"""
    d = ctx.get("BTC/USDT", "1d", lookback=30)  # 获取最近 30 根 K 线
    if len(d) < 21: return                        # 数据不足时跳过

    ma5 = d.close.rolling(5).mean().iloc[-1]     # 短期均线
    ma20 = d.close.rolling(20).mean().iloc[-1]   # 长期均线
    pos = ctx.portfolio.get_position("BTC/USDT")  # 当前持仓

    if ma5 > ma20 and pos.qty == 0:               # 金叉 + 空仓 → 买入
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1, tag="entry"))
    elif ma5 < ma20 and pos.qty > 0:              # 死叉 + 持仓 → 卖出
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty, tag="exit"))

eng = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, cost_model=ZeroCost(),
                     benchmark="BTC/USDT")
res = eng.run()
print(res.summary())
# 输出包含：总收益、年化收益、Sharpe、Sortino、Calmar、最大回撤、胜率、盈亏比等
```

### 通过 client 便捷入口

`client.backtest()` 是便捷方法，自动注入 `ComputeEngine`，策略内可通过 `ctx.compute` 使用全部 23 个指标：

```python
res = client.backtest(data, ma_cross, initial_cash=10000, benchmark="BTC/USDT")
# 策略内可用：ctx.compute.rsi(d.close, window=14)
```

### 类式策略 + 生命周期钩子

继承 `Strategy` 基类，可实现 `on_start` / `on_bar` / `on_fill` 等钩子：

```python
from stockstat.backtest import Strategy, Order

class RSIStrategy(Strategy):
    """RSI 超买超卖策略：<30 买入，>70 卖出。"""

    def on_start(self, ctx):
        """回测开始前调用，可初始化状态。"""
        ctx.history["trade_count"] = 0

    def on_bar(self, ctx):
        """每根 K 线调用一次。"""
        d = ctx.get("BTC/USDT", "1d", lookback=30)
        if len(d) < 15: return

        # 通过 ctx.compute 调用指标（自动注入的 ComputeEngine）
        r = ctx.compute.rsi(d.close, window=14).iloc[-1]
        pos = ctx.portfolio.get_position("BTC/USDT")

        if r < 30 and pos.qty == 0:        # RSI < 30：超卖，买入
            ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
            ctx.history["trade_count"] += 1
        elif r > 70 and pos.qty > 0:       # RSI > 70：超买，卖出
            ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

    def on_fill(self, fill, ctx):
        """每次成交后调用。"""
        print(f"成交 {fill.side.value} {fill.qty} @ {fill.price:.2f}")
```

### 多标的配对交易 + 做空

配对交易策略：当 BTC/ETH 价差偏离均值超过 1.5 个标准差时，做空强势、做多弱势：

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

    # 计算对数价差及其 Z-score
    spread = np.log(btc.close) - np.log(eth.close)
    z = (spread - spread.rolling(20).mean()) / spread.rolling(20).std()
    last = z.iloc[-1]
    if np.isnan(last): return

    pb = ctx.portfolio.get_position("BTC/USDT")
    # Z > 1.5: BTC 相对 ETH 偏贵 → 做空 BTC、做多 ETH
    if last > 1.5 and pb.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", 0.1))   # 做空
        ctx.broker.submit(Order("ETH/USDT", "buy", 0.1))    # 做多
    # Z < -1.5: BTC 相对 ETH 偏便宜 → 做多 BTC、做空 ETH
    elif last < -1.5 and pb.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
        ctx.broker.submit(Order("ETH/USDT", "sell", 0.1))

res = BacktestEngine(data=data, strategy=pair,
                     initial_cash=10000, allow_short=True).run()
# allow_short=True 开启做空支持
```

### 多时间尺度共振

同时使用日线和小时线，日线判断趋势方向，小时线判断突破时机：

```python
hourly = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1h")
daily  = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
data = {"BTC/USDT": {"1h": hourly, "1d": daily}}

@strategy
def multi_tf(ctx):
    h = ctx.get("BTC/USDT", "1h", lookback=50)  # 小时线
    d = ctx.get("BTC/USDT", "1d", lookback=30)  # 日线
    if len(d) < 21 or len(h) < 2: return

    # 日线趋势：收盘价在 MA20 之上
    trend_up = d.close.iloc[-1] > d.close.rolling(20).mean().iloc[-1]
    # 小时线突破：最新收盘价突破上一根
    breakout = h.close.iloc[-1] > h.close.iloc[-2]

    pos = ctx.portfolio.get_position("BTC/USDT")
    if trend_up and breakout and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif not trend_up and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

res = BacktestEngine(data=data, strategy=multi_tf).run()
# 引擎自动以最细时间粒度（1h）为主索引，日线数据 ffill 对齐
```

### 参数网格搜索

`grid_search` 自动遍历参数组合，返回按指标排序的结果列表：

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

# 遍历 3×3=9 种参数组合，按 Sharpe 排序
results = grid_search(make_engine,
                      {"short": [3, 5, 8], "long": [10, 20, 30]},
                      metric="sharpe")
best_params, best_val, best_res = results[0]
print(f"最佳参数: {best_params}, Sharpe: {best_val:.3f}")
```

### 回测可视化

`BacktestResult` 提供 9 种图表类型，安装 matplotlib 后自动激活：

```python
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

# 一行渲染单个图表
res.render("equity_curve", path="equity.png")         # 资金曲线 + 基准
res.render("drawdown", path="drawdown.png")            # 回撤填充图
res.render("dashboard", path="dashboard.png")          # 2×2 综合仪表盘

# 批量保存全部图表到目录
res.render_all("./charts")

# 其他图表类型
res.render("returns_distribution", path="dist.png")    # 收益分布直方图
res.render("monthly_heatmap", path="monthly.png")      # 月度收益热力图
res.render("yearly_returns", path="yearly.png")        # 年度收益柱状图
res.render("trades_overlay", path="trades.png")        # 交易点标注（B/S 箭头）
res.render("parameter_heatmap", grid_results=results, path="param.png")  # 参数网格热力图
res.render("underwater_curve", path="underwater.png")  # 水下曲线
```

![BTC 回测仪表盘](../docs/images/backtest_btc_dashboard.png)

---

## 9. 回测高级功能

### Binance 费率模型（4 种预设）

`BinanceCost` 支持 Binance 现货和合约的 4 种费率预设，精确模拟 BNB 折扣：

```python
from stockstat.backtest import BinanceCost, BINANCE_SPOT, BINANCE_SPOT_BNB, \
    BINANCE_FUTURES, BINANCE_FUTURES_BNB

# F1 现货无 BNB：  maker 0.100% / taker 0.100%
# F2 现货+BNB：    maker 0.075% / taker 0.075%  (BNB 抵扣省 25%)
# F3 合约无 BNB：  maker 0.020% / taker 0.050%
# F4 合约+BNB：    maker 0.018% / taker 0.045%  (BNB 抵扣省 10%)

eng = BacktestEngine(data=data, strategy=s,
                     cost_model=BINANCE_FUTURES_BNB,  # 使用 F4 预设
                     initial_cash=10000)
```

也可以自定义费率参数：
```python
custom_cost = BinanceCost(venue="spot", bnb_discount=True, slippage=0.001)
# slippage: 额外滑点成本（0.1%）
```

### Intrabar 执行（同 bar 入场+出场）

`IntrabarExecution` 允许在同一根 K 线内完成入场和出场（例如日线入场 → 小时线止盈）。需要提供两个时间粒度的数据：

```python
from stockstat.backtest import Strategy, IntrabarMixin, IntrabarExecution, BinanceCost

class SimpleTP(Strategy, IntrabarMixin):
    """市价入场 → intrabar 扫描 TP 限价 → 收盘兜底。

    策略逻辑：
    1. 日线开盘时市价买入
    2. 设置 1% 止盈限价单
    3. 在日内（1h K 线）扫描是否触及止盈价
    4. 如果日内未止盈，收盘市价平仓
    """
    def on_bar(self, ctx):
        o = ctx.current_price("BTC/USDT", "open")
        if o is None: return
        ctx.intrabar_submit(Order("BTC/USDT", "buy", 0.1, tag="entry"))
        ctx.history["tp_price"] = o * 1.01  # 1% 止盈

    def define_exits(self, entry_fill, ctx):
        """定义入场后的退出订单。"""
        tp = ctx.history.get("tp_price")
        if tp is None: return []
        return [
            # 止盈限价单（priority=1，优先于止损）
            Order("BTC/USDT", "sell", entry_fill.qty,
                  order_type="limit", limit_price=tp,
                  tag="tp", exit_reason="tp", priority=1),
            # 收盘兜底市价单（priority=99，最低优先级）
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
# 输出各退出原因的统计：tp / close 的次数和收益
```

### 批量回测（多策略 × 多费率）

`StrategyBatchRunner` 并行运行多策略 × 多费率组合：

```python
from stockstat.backtest import StrategyBatchRunner

runner = StrategyBatchRunner(data=data, initial_cash=10000,
                             cost_model=BINANCE_SPOT, allow_short=True)
results = runner.run_all({"ma_cross": s1, "rsi": s2})
df = results.to_dataframe()       # 转为 DataFrame 便于比较
ranked = results.rank("sharpe")   # 按 Sharpe 排序
print(ranked[["strategy", "sharpe", "max_drawdown", "win_rate"]])
```

### 子期间与状态分析

`BacktestAnalyzer` 提供分时段和分状态的条件分析：

```python
from stockstat.backtest import BacktestAnalyzer
import pandas as pd

res = BacktestEngine(data=data, strategy=s, initial_cash=10000).run()

# 子期间分析：将回测按日期切分，比较各段表现
sub = BacktestAnalyzer.subperiod_metrics(
    res, split_dates=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-06-01")]
)
# 输出：2024H1 / 2024H2 各自的 Sharpe / 回撤 / 收益率

# 状态条件分析：按市场状态（如高/低波动率）分组统计
reg = BacktestAnalyzer.regime_conditional_metrics(res, regime_series)
# regime_series 是一个标记市场状态的 Series（如 "bull"/"bear"/"sideways"）

# 按退出原因分析
exit_stats = res.exit_reason_stats()
# 输出：tp / close / stop_loss 各自的次数、平均收益、胜率
```

### DCA 基准与费率扫描

```python
from stockstat.backtest import dca_equity, fee_sweep, maker_taker_sweep

# DCA（定投）基准：每周定投 10000/N 元
dca_eq = dca_equity(10000, prices, schedule="weekly")

# 费率扫描：测试不同佣金率对策略表现的影响
sweep = fee_sweep(data=data, strategy=s, commissions=[0.0001, 0.0003, 0.0005])
# 输出：每个佣金率下的 Sharpe / 收益 / 回撤

# Maker/Taker 扫描：测试不同 Maker/Taker 组合
mt = maker_taker_sweep(data=data, strategy=s,
                       maker_rates=[0.0002, 0.0005], taker_rates=[0.0005, 0.001])
```

---

## 10. 信号处理与非线性动力学

> 需要 `pip install stockstat[signal_processing]`（安装 PyWavelets）。未安装时 CWT 自动降级为基于 FFT 的自实现 Morlet 小波（功能可用但精度略低）。

本模块提供 8 个高级分析函数，涵盖信号处理和非线性动力学，适合研究价格序列的复杂行为特征。

```python
import numpy as np

signal = data.close.values[-48:]  # 取最近 48 个数据点

# ── 信号处理 ──

# 连续小波变换（CWT）：将信号分解为不同尺度的时频表示
coef, scales = client.compute.wavelet_decompose(signal, scales=np.arange(1, 25))
# coef 形状: (24, 48)，24 个尺度 × 48 个时间点
print(f"CWT 系数形状: {coef.shape}")

# 谱熵：衡量信号在频域的复杂度（0=单一频率，高值=复杂多频）
h_spec = client.compute.spectral_entropy(np.diff(np.log(signal)))
print(f"谱熵: {h_spec:.4f}")

# 灰色关联度：衡量两条路径的形态相似度（0~1，1=完全相似）
path_a = data.close.values[-48:]
path_b = data.close.values[-96:-48]
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)
print(f"灰色关联度: {gr:.4f}")

# GM(1,1) 灰色预测：基于少数据的短期预测
forecast = client.compute.gm11_predict(signal)
print(f"GM(1,1) 下一步预测: {forecast:.2f}")

# ── 非线性动力学 ──

# Hurst 指数（DFA 法）：判断序列的持久性
hurst = client.compute.hurst_dfa(np.diff(np.log(signal)))
print(f"Hurst 指数: {hurst:.4f}")
# ≈ 0.5: 随机游走（不可预测）
# > 0.5: 持久性（趋势会延续）
# < 0.5: 反持久性（趋势会反转）

# 传递熵：衡量 X → Y 的有向信息流（单位：bits）
btc_rets = np.diff(np.log(btc.close.values))[:200]
eth_rets = np.diff(np.log(eth.close.values))[:200]
te = client.compute.transfer_entropy(btc_rets, eth_rets, k=1)
print(f"TE(BTC→ETH): {te:.4f} bits")
# 值越大表示 BTC 对 ETH 的信息引导越强

# 样本熵：衡量序列的可预测性（低值=更可预测）
sampen = client.compute.sample_entropy(signal, m=2)
print(f"样本熵: {sampen:.4f}")

# 排列熵：基于排列模式的复杂度度量（单位：bits）
permen = client.compute.permutation_entropy(signal, m=3, tau=1)
print(f"排列熵: {permen:.4f}")
```

### 可视化

提供 3 个 PlotSpec 工厂函数，返回可被渲染器渲染的 PlotSpec：

```python
# CWT 时频热力图
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
renderer = client.plot.get_renderer()
renderer.render(spec)
renderer.savefig("cwt_scalogram.png")

# DFA 双对数拟合图（Hurst 指数）
spec = client.compute.dfa_fit(np.diff(np.log(signal)))
renderer.render(spec)
renderer.savefig("dfa_fit.png")
```

---

## 11. 结果导出

```python
from stockstat.export.serializers import to_json, to_csv, to_dict

# DataFrame → JSON 字符串（时间戳转为 ISO 格式）
json_str = to_json(data)

# DataFrame → CSV 字符串
csv_str = to_csv(data)

# DataFrame → 字典列表（每行一个 dict）
records = to_dict(data)

# PlotSpec → dict（用于 Web 前端渲染或序列化传输）
spec = client.plot.spec(title="我的图表", series=[...])
payload = spec.to_dict()
```

---

## 12. v2.0 CLI 命令行

v2.0 新增 `stockstat` CLI 命令行工具，无需写 Python 脚本即可完成常用操作。

### 启动 API 服务器

```bash
stockstat serve --host 0.0.0.0 --port 8000
```

### 命令行采集数据

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

输出：
```json
{"symbol": "AAPL", "source": "yfinance", "ingested": 251}
```

### 查询数据

```bash
# 表格格式（默认，适合终端查看）
stockstat query BTC/USDT --limit 5

# JSON 格式（适合管道处理或脚本消费）
stockstat query BTC/USDT --format json

# CSV 格式（适合导出到文件）
stockstat query AAPL --start 2024-01-01 --format csv > aapl.csv
```

### 列出已注册插件

```bash
# 列出全部插件（46 个）
stockstat plugins

# 按命名空间过滤
stockstat plugins --namespace indicators    # 23 个指标
stockstat plugins --namespace sources       # 4 个数据源
stockstat plugins --namespace cost_models   # 8 个成本模型
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

Total: 46 plugin(s)
```

### 列出已注册指标

```bash
# 全部指标
stockstat indicators

# 按类别过滤
stockstat indicators --category trend        # ma / ema / macd
stockstat indicators --category nonlinear    # wavelet_decompose / hurst_dfa / ...
```

---

## 13. 离线模式

离线模式无需启动后端服务，全部计算在本地完成。v2.1 支持四种数据获取方式：

### 方式1：离线从数据源下载（v2.1 新增）

无需启动后端，前端直接通过 `PluginRegistry` 适配器从数据源下载数据：

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage

client = V2Client(mode="offline", storage=MemoryStorage())

# 直接从 Binance 下载，存入内存
result = client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
print(result)  # {'symbol': 'BTC/USDT', 'source': 'binance', 'ingested': 366}

# 查询、计算、回测全部本地运行
df = client.ohlcv("BTC/USDT")
ma = client.compute.ma(df.close, window=20)
```

> 离线 `ingest()` 的数据流：`registry.get("sources", "binance")` → `adapter.fetch_ohlcv()` → 标准化 → `storage.upsert()`。需要安装 `ccxt`（加密货币）或 `requests`（yfinance），或安装 `stockstat-backend` 包。后端未安装时自动使用前端本地适配器（`_LazySourcePlugin` 延迟实例化）。

### 方式2：读取现有 SQLite 数据库文件

直接读取后端创建的数据库文件，无需启动后端服务：

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import SQLStorage

# 直接读取后端创建的数据库文件
client = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///stockstat.db"))
df = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
print(df[["close"]].head())

# 也可以用绝对路径
client = V2Client(mode="offline",
                  storage=SQLStorage(database_url="sqlite:////data/stockstat/stockstat.db"))
```

> `SQLStorage` 通过 `_compat.py` 委托到 `ohlcv_repo.query()`。当后端包未安装时，`_compat.py` 自动用独立 SQLAlchemy 建表和查询。

### 方式3：手动写入数据

适用于测试或从其他数据源导入的数据：

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

### 方式4：离线下载 + 持久化到 SQLite

下载的数据持久化到 SQLite 文件，下次启动时数据仍在：

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import SQLStorage

# 下载并写入 SQLite 文件（持久化）
client = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///my_data.db"))
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")

# 下次启动时数据仍在（无需重新下载）
client2 = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///my_data.db"))
df = client2.ohlcv("AAPL")
print(f"AAPL: {len(df)} rows")
```

### 离线模式功能对照

| 功能 | 在线模式 | 离线模式 |
|------|---------|---------|
| `ohlcv()` | HTTP → 后端 REST API | `storage.query()` 本地查询 |
| `ingest()` | HTTP → 后端采集 | 适配器 → `fetch_ohlcv()` → `storage.upsert()` |
| `compute` | 后端无关 | 本地 `ComputeEngine` |
| `run_dsl()` | `DslEngine`（HTTP 取数据） | `DslEngine`（本地 Storage 取数据） |
| `backtest()` | 后端无关 | 本地 `BacktestEngine` |
| `plot` | 后端无关 | 本地 `PlotAPI` |

---

## 14. 插件系统

v2.0 的所有可扩展点统一注册到 `PluginRegistry`（46 个内置插件，分布在 6 个命名空间）。

### 注册自定义指标

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

### DSL 自动反射新指标

注册新指标后，刷新 DSL 引擎即可自动可用：

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

### 注册自定义回测组件

```python
from stockstat._domain.backtest import BacktestComponentPlugin

# 自定义成本模型
class MyCostModel:
    def __init__(self, rate=0.001):
        self.rate = rate
    def compute(self, qty, price, side):
        return abs(qty * price * self.rate)

reg.register("cost_models", "my_cost",
    BacktestComponentPlugin("my_cost", MyCostModel, "cost",
                            description="Custom cost model"))
```

### 列出所有插件

```python
for item in reg.list():
    plugin = item["plugin"]
    print(f"{item['namespace']:<20} {item['name']:<25} {getattr(plugin, 'category', '')}")
```

### 主题系统

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

## 15. 管理界面

### TUI 终端管理界面

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
  1. Browse symbols      — 列出所有已注册标的
  2. Query OHLCV data    — 查询最近 N 行数据
  3. Ingest new data     — 交互式采集
  4. Data statistics     — 数据统计概览
  5. List data sources   — 列出可用数据源
  6. View proxy config   — 查看代理配置
  q. Quit
```

> 推荐安装 `pip install rich` 以获得彩色表格体验。未安装时自动降级为纯文本菜单。

### 网页管理界面

```bash
# 启动后端后，浏览器访问：
# http://localhost:8000/admin/        (本地)
# http://192.168.1.100:8000/admin/    (远程)
```

| 页面 | 功能 |
|------|------|
| **概览** | 标的数、行数、磁盘、数据覆盖甘特图、最近采集 |
| **数据源浏览** | 分页 + 搜索 + 批量下载 + **手动输入任意标的** |
| **本地标的** | K 线图（**缩放时懒加载**）+ 截选范围补全 + 导出 CSV |
| **配置** | 数据库 / 代理（在线修改）/ 缓存 / 磁盘 |
| **日志** | 采集历史（分页 + 过滤） |

### K 线图懒加载

选择标的后：
1. **初始加载**：自动拉取最近 500 根（`order=desc&limit=500`）
2. **向左滚动**：当可视范围超出已加载区域时，自动拉取更早的 1000 根（300ms 防抖）
3. **向右滚动**：自动拉取更晚的 1000 根
4. **去重合并**：按时间戳去重，通过 `series.update()` 合并，不重复加载
5. **进度显示**：底部显示"已加载: 2024-01-01 ~ 2024-06-30 (500 bars) | 全部: 2017-08-17 ~ 2024-07-18 (35%)"

### 下载模态框

点击"下载"按钮后：
1. 调用 `probe_range` 实测数据源中该标的的实际可用时间范围（拉首末 K 线）
2. 显示"实测 / 估算"标签
3. 日期默认填入最大范围（`min`/`max` 限制为范围）
4. 时间粒度根据数据源动态生成（Binance 16 种、yfinance 12 种等）
5. 显示本地已有数据范围 + 存储估算提示（"1分钟粒度1年约15MB"）

### 通过 Admin API 操作

```bash
# 采集
curl -X POST "http://localhost:8000/admin/api/ingest?symbol=BTC/USDT&source=binance&start=2024-01-01"

# 探测数据源范围（实测）
curl "http://localhost:8000/admin/api/sources/binance/info?symbol=BTC/USDT&probe=true"
# 返回：earliest_available / latest_available / timeframes / local_earliest / local_latest

# 查看统计
curl http://localhost:8000/admin/api/stats
# {"total_symbols":5,"total_rows":1234,"symbols_by_source":{"binance":3,"yfinance":2}}

# 删除标的
curl -X DELETE http://localhost:8000/admin/api/symbols/BTC/USDT
# {"deleted":true,"symbol":"BTC/USDT","rows_removed":366}
```

---

## 16. PAXG 周末相关性分析

### 分析目标

检验 PAXG（黄金锚定代币）周末涨跌幅（周五收盘→周日收盘）与周一**最大涨幅**和**最大跌幅**之间的独立相关性：

- `max_gain = (最高 - 开盘) / 开盘` — 日内最大上行幅度（恒为正）
- `max_loss = (最低 - 开盘) / 开盘` — 日内最大下行幅度（恒为负）

"独立记录"意味着将涨幅和跌幅作为两个独立变量分别与周末涨跌幅做相关分析，而非合并为净涨跌。

### 完整分析

```python
from scipy import stats
import pandas as pd

# 获取 PAXG 日线数据（需要 2022 年起，覆盖多轮牛熊周期）
paxg = client.ohlcv("PAXG/USDT", start="2022-01-01", timeframe="1d")
df = paxg.copy()
df["weekday"] = df.index.weekday  # 0=Monday, 4=Friday, 6=Sunday

# 分离周五、周日、周一的数据
fridays = df[df.weekday == 4][["close"]]
sundays = df[df.weekday == 6][["close"]]
mondays = df[df.weekday == 0][["open", "high", "low", "close"]]

# 配对：每个周一找到其前一个周五和周日
pairs = []
for mon_date, mon_row in mondays.iterrows():
    prev_fri = fridays.loc[:mon_date].tail(1)  # 最近一个周五
    prev_sun = sundays.loc[:mon_date].tail(1)  # 最近一个周日
    if len(prev_fri) > 0 and len(prev_sun) > 0:
        fri_c = prev_fri["close"].iloc[0]
        sun_c = prev_sun["close"].iloc[0]
        weekend_ret = (sun_c - fri_c) / fri_c           # 周末涨跌幅
        mon_open = mon_row["open"]
        max_gain = (mon_row["high"] - mon_open) / mon_open  # 周一最大涨幅
        max_loss = (mon_row["low"] - mon_open) / mon_open    # 周一最大跌幅
        pairs.append({"weekend_return": weekend_ret,
                       "max_gain": max_gain, "max_loss": max_loss})

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

**解读**：周末涨跌幅与周一最大涨幅正相关（r=0.23, p<0.01），与周一最大跌幅负相关（r=-0.20, p<0.05）。两者均统计显著但相关性较弱，说明周末涨跌幅对周一的涨跌方向有适度的独立预测力——周末涨则周一更可能涨（涨幅更大），周末跌则周一更可能跌（跌幅更大）。

### 散点图

![PAXG 周末散点图](images/paxg_weekend_scatter.png)

### 方向性分布

![PAXG 方向性](images/paxg_directional.png)

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
| `STOCKSTAT_ADMIN_ENABLED` | `true` | 启用网页管理界面 |

### 前端

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKSTAT_HOST` | `localhost` | 前端主机 |
| `STOCKSTAT_PORT` | `8000` | 前端端口 |
| `STOCKSTAT_API_KEY` | （空） | 可选 API key |
| `STOCKSTAT_TIMEOUT` | `30` | HTTP 超时秒数 |
| `STOCKSTAT_USE_HTTPS` | `false` | 是否使用 HTTPS |

---

## 17. 连接与性能测试

项目附带两个测试脚本，用于验证前后端通讯通路完整性和测量通讯性能。位于 `tests/` 目录。

### 17.1 连接通路测试（`tests/test_connection.py`）

对远程后端执行完整的端到端测试：健康检查 → 下载标的数据 → 查询 → 计算指标 → DSL 查询 → 回测 → 可视化。每个步骤输出 ✓/✗ 结果和耗时。

```bash
# 默认连接 localhost:8000
python tests/test_connection.py

# 指定远程后端
python tests/test_connection.py --host 192.168.1.100 --port 8000

# 使用 HTTPS
python tests/test_connection.py --host example.com --port 443 --https
```

测试流程（7 步）：

| 步骤 | 测试内容 | 验证点 |
|------|---------|--------|
| 1. 健康检查 | `GET /api/v1/health` | 后端在线、代理状态、延迟 |
| 2. 下载标的 | `ingest AAPL + BTC/USDT + ETH/USDT` | 数据源可达、采集行数 |
| 3. 查询数据 | `ohlcv()` + `order=desc` + `symbols()` | DataFrame 返回、双向分页 |
| 4. 计算指标 | MA / RSI / 布林带 / Sharpe / 最大回撤 | 指标计算正确 |
| 5. DSL 查询 | `run_dsl()` 多列+指标 | DSL 引擎工作 |
| 6. 回测 | 双均线策略 + `client.backtest()` | 回测完成、指标输出 |
| 7. 可视化 | `res.render()` 生成 PNG | matplotlib 渲染（可选） |

输出示例：
```
ℹ 1. 连接后端 + 健康检查
  ✓ 后端在线 (健康检查延迟: 2.1 ms)
  ✓ 可用数据源: ['yfinance', 'binance', 'coinbase', 'synthetic']

ℹ 2. 下载标的数据 (ingest)
  ✓ AAPL 日线: 251 行 (耗时 3112 ms)
  ✓ BTC/USDT 日线: 366 行 (耗时 5615 ms)

ℹ 6. 回测 (双均线策略)
  ✓ 回测完成 (耗时 303 ms)
       总收益:     21.78%
       Sharpe:     0.2838
       最大回撤:   -22.64%
```

### 17.2 通讯性能测试（`tests/test_perf.py`）

测量前后端之间的通讯延迟、传输速度和抖动。适合评估远程部署的网络质量。

```bash
# 默认 localhost:8000，20 轮
python tests/test_perf.py

# 指定远程后端，5 轮（减少测试时间）
python tests/test_perf.py --host 192.168.1.100 --port 8000 --rounds 5

# 指定测试标的和时间粒度（需预先下载好数据）
python tests/test_perf.py --symbol BTC/USDT --timeframe 1h --rounds 10
```

测试项目（8 项）：

| 测试 | 说明 |
|------|------|
| 1. 健康检查 RTT | `GET /api/v1/health` 的往返延迟，多次测量取 min/mean/median/p95/max |
| 2. 空查询延迟 | 查询不存在的标的（404 响应），测量后端空请求处理速度 |
| 3. 查询延迟 vs 数据量 | 1 / 10 / 100 / 500 / 1000 / 5000 / 10000 行的查询延迟 + 传输大小 + 传输速度 |
| 4. order 参数对比 | `order=asc` vs `order=desc`（相同行数），验证双向分页性能差异 |
| 5. 符号列表查询 | `GET /api/v1/symbols` 延迟 |
| 6. 采集延迟 | `POST /api/v1/ingest`（含网络下载+存储，非纯通讯延迟） |
| 7. 连续抖动 | 50 次快速查询的延迟分布（直方图 + jitter 标准差） |
| 8. 原始 HTTP 延迟 | `httpx.get` 直连（绕过前端库），测量纯 TCP+HTTP 开销 |

输出示例：
```
3. 数据查询延迟 vs 数据量 (BTC/USDT 1h)

  查询                            min       mean     median      p95       max       大小      速度
  limit=1                     2.0 ms     2.1 ms     2.0 ms     2.3 ms    2.3 ms     129 B     63 KB/s
  limit=100                   2.5 ms     2.7 ms     2.6 ms     3.0 ms    3.0 ms    12.7 KB   4.8 MB/s
  limit=1000                  5.1 ms     5.5 ms     5.4 ms     6.2 ms    6.2 ms   127.5 KB  23.5 MB/s
  limit=10000                28.3 ms    29.5 ms    29.0 ms    32.1 ms   32.1 ms    1.24 MB  42.3 MB/s

7. 连续请求抖动 (50 次快速查询, limit=10)
  延迟分布:
        <5ms:  48 ( 96.0%) ████████████████████████████████████████████████
      5-10ms:   2 (  4.0%) █

  评估: 🟢 延迟极低，适合本地开发
```

### 17.3 性能优化提示

**连接池复用**：默认 `StockStatClient` 每次请求新建 TCP 连接。对于高频查询场景（如 K 线图懒加载、批量回测），传入 `httpx.Client()` 启用连接池可大幅降低延迟：

```python
import httpx
from stockstat import StockStatClient

# 默认：每次请求新建 TCP 连接（适合低频使用）
client = StockStatClient(host="192.168.1.100", port=8000)

# 优化：传入 httpx.Client 启用连接池（适合高频查询）
with httpx.Client() as pool:
    client = StockStatClient(host="192.168.1.100", port=8000, http_client=pool)
    # 后续所有 client.ohlcv() / client.ingest() 复用同一 TCP 连接
    for _ in range(100):
        client.ohlcv("BTC/USDT", limit=100)  # 首次后每次仅 ~1ms
```

| 模式 | 首次请求 | 后续请求 | 适用场景 |
|------|---------|---------|---------|
| 默认（无连接池） | ~2000ms（含 TCP 建立） | ~2000ms（每次新建） | 低频脚本、一次性查询 |
| 连接池（`http_client`） | ~2000ms（含 TCP 建立） | **~1ms**（复用连接） | K 线图懒加载、批量回测、高频查询 |

> **Windows `localhost` 注意**：Windows 上 `localhost` 可能先尝试 IPv6（`::1`）再回退 IPv4，导致 TCP 连接建立延迟 ~2 秒。使用 `127.0.0.1` 或连接池可避免此问题。

---

## 18. 启动脚本

后端提供两类启动脚本，位于 `backend/` 目录。

### 18.1 极简启动脚本（`start.bat` / `start.sh`）

直接设置环境变量并启动，适合快速启动或部署时修改参数后使用。每个环境变量占一行，行尾有注释说明：

```bash
# Windows
backend\start.bat

# Linux/macOS
backend/start.sh
```

脚本内容（以 `start.sh` 为例）：
```bash
export HOST="0.0.0.0"                              # Listen address
export PORT="8000"                                 # Listen port
export DATABASE_URL="sqlite:///stockstat.db"       # SQLite file
export STOCKSTAT_PROXY_ENABLED="false"             # Enable proxy
export STOCKSTAT_ADMIN_ENABLED="true"              # Web admin UI
python3 -m uvicorn stockstat_backend.app:app --host "$HOST" --port "$PORT"
```

修改对应行的值即可自定义配置。

### 18.2 完整配置脚本（`serve.bat` / `serve.sh`）

支持命令行参数和交互式配置，适合首次部署或需要灵活配置的场景：

```bash
# 交互式配置（引导式设置数据库/代理/Admin/热重载）
backend/serve.bat --config       # Windows
backend/serve.sh --config        # Linux/macOS

# 命令行指定参数
backend/serve.bat --host 0.0.0.0 --port 9000
backend/serve.sh --db-url "sqlite:////data/stockstat.db"
backend/serve.bat --proxy http http://127.0.0.1:8889
backend/serve.sh --no-admin --reload
```

支持的参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 监听地址 | `0.0.0.0` |
| `--port` | 监听端口 | `8000` |
| `--db-url` | 数据库连接字符串 | `sqlite:///stockstat.db` |
| `--redis-url` | Redis 连接（可选） | （空） |
| `--proxy <type> <url>` | 启用代理 | 禁用 |
| `--no-admin` | 关闭网页管理界面 | 开启 |
| `--reload` | 热重载（开发模式） | 关闭 |
| `--config` | 交互式配置 | 跳过 |
