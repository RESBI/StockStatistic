# StockStat V3 使用文档

> **版本**：v3.0（P0-P7 全部完成）
> **测试基线**：922 项测试通过 + 6 项 Redis 跳过；PAXG 132 次回测字节级一致
> **关联**：[README_CN.md](../README_CN.md) | [DESIGN_V3_CN.md](../DESIGN_V3_CN.md) | [DESIGN_ARCHITECTURE_CN.md](../DESIGN_ARCHITECTURE_CN.md)

---

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
12. [CLI 命令行](#12-cli-命令行)
13. [离线模式](#13-离线模式)
14. [插件系统](#14-插件系统)
15. [管理界面](#15-管理界面)
16. [V3 分布式计算](#16-v3-分布式计算)
17. [V3 ComputeBackend 兼容层](#17-v3-computebackend-兼容层)
18. [V3 Dispatcher 部署](#18-v3-dispatcher-部署)
19. [V3 Worker 部署](#19-v3-worker-部署)
20. [V3 集群管理](#20-v3-集群管理)
21. [V3 任务生命周期](#21-v3-任务生命周期)
22. [V3 部署场景](#22-v3-部署场景)
23. [PAXG 周末相关性分析](#23-paxg-周末相关性分析)
24. [连接与性能测试](#24-连接与性能测试)
25. [启动脚本](#25-启动脚本)
26. [环境变量参考](#26-环境变量参考)

---

## 1. 环境准备

### 1.1 安装

项目包含三个独立 pip 包：

```bash
# 后端（FastAPI + SQLAlchemy + Dispatcher）
cd backend && pip install -e .

# 前端核心库（ComputeEngine + 回测 + DSL + V3 协议层）
cd frontend && pip install -e .

# V3 Worker 独立包（分布式计算）
cd worker && pip install -e .
```

### 1.2 可选 extras

```bash
pip install -e "frontend/[matplotlib]"          # 可视化
pip install -e "frontend/[dsl]"                 # DSL 解析（lark）
pip install -e "frontend/[signal_processing]"   # 小波变换（PyWavelets）
pip install -e "frontend/[backtest_full]"       # 回测全套
pip install -e "frontend/[compute]"             # V3 本地后端（cloudpickle + psutil）
pip install -e "frontend/[distributed]"         # V3 分布式（+ redis + msgpack）
pip install rich                                # TUI 彩色表格
```

> 前端核心依赖仅有 pandas / numpy / scipy / httpx / pyarrow。未安装可选 extras 时相关功能优雅降级（CWT 降级为 FFT 自实现，可视化降级为 NullRenderer）。

### 1.3 开启代理（访问真实数据源）

```bash
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http                    # 或 socks5
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889    # 你的代理地址
```

### 1.4 启动后端

```bash
# 基础启动（仅 Storage）
stockstat serve --host 0.0.0.0 --port 8000

# V3 启用 Dispatcher
STOCKSTAT_DISPATCHER_ENABLED=true stockstat serve --host 0.0.0.0 --port 8000

# V3 启用 Dispatcher + Redis 队列
STOCKSTAT_DISPATCHER_ENABLED=true \
STOCKSTAT_DISPATCHER_QUEUE=redis \
REDIS_URL=redis://redis:6379/0 \
stockstat serve --host 0.0.0.0 --port 8000
```

启动后：
- REST API 在 `http://localhost:8000/api/v1/*`
- 管理界面在 `http://localhost:8000/admin/`
- Dispatcher 路由在 `http://localhost:8000/dispatch/*`

### 1.5 指定数据库

```bash
# SQLite 默认
export DATABASE_URL="sqlite:///stockstat.db"

# SQLite 绝对路径（注意 4 个斜杠）
export DATABASE_URL="sqlite:////data/stockstat/stockstat.db"

# PostgreSQL
export DATABASE_URL="postgresql://user:pwd@host:5432/stockstat"
```

---

## 2. 数据采集

支持多数据源（yfinance / Binance / Coinbase / 合成数据），自动检测数据源类型（含 `/` → 加密货币，否则 → 股票）。

```python
from stockstat import StockStatClient
client = StockStatClient(host="localhost", port=8000)

# 股票（Yahoo Finance）
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")

# 加密货币（Binance，16 种时间粒度）
client.ingest("BTC/USDT", source="binance", start="2024-01-01", timeframe="1h")

# 自动检测
client.ingest("MSFT", start="2024-01-01")
```

CLI 等价：

```bash
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

### 2.1 批量采集

```python
client.ingest_batch(["BTC/USDT", "ETH/USDT", "AAPL"],
                     source="binance", start="2024-01-01")
```

### 2.2 数据源范围探测

```python
# 实测数据源中该标的的实际可用时间范围
info = client.sources()
for src in info:
    print(f"{src['name']}: {src['symbols']} symbols")
```

---

## 3. 查询 OHLCV 数据

```python
# 基础查询
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")

# 双向分页（懒加载场景）
recent = client.ohlcv("BTC/USDT", limit=500, order="desc")
earlier = client.ohlcv("BTC/USDT", end="2024-01-01", limit=1000, order="desc")

# 批量查询
batch = client.ohlcv_batch(["BTC/USDT", "ETH/USDT"], start="2024-01-01")
```

CLI：

```bash
stockstat query BTC/USDT --limit 5
stockstat query AAPL --start 2024-01-01 --format csv
```

---

## 4. 计算指标

23 个技术指标 + 8 个非线性动力学函数。

### 4.1 趋势指标

```python
sma = client.compute.ma(data.close, window=20)
ema = client.compute.ema(data.close, window=12)
macd_line, signal_line, hist = client.compute.macd(data.close)
```

### 4.2 震荡指标

```python
rsi = client.compute.rsi(data.close, window=14)
k, d, j = client.compute.kdj(data.high, data.low, data.close, window=9)
```

### 4.3 波动率指标

```python
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
atr = client.compute.atr(data.high, data.low, data.close, window=14)
std = client.compute.std(data.close, window=20)
```

### 4.4 统计指标

```python
beta = client.compute.beta(stock_returns, market_returns, window=60)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
dd = client.compute.max_drawdown(data.close)
var_95 = client.compute.var(returns, confidence=0.95)
corr = client.compute.corr(x, y)
```

### 4.5 信号处理与非线性动力学

```python
import numpy as np
path = data.close.values[-48:]

# 信号处理
coef, scales = client.compute.wavelet_decompose(path, scales=np.arange(1, 25))
h_spec = client.compute.spectral_entropy(np.diff(np.log(path)))
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)
forecast = client.compute.gm11_predict(sequence)

# 非线性动力学
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))
te = client.compute.transfer_entropy(btc_rets, eth_rets)
sampen = client.compute.sample_entropy(signal, m=2)
permen = client.compute.permutation_entropy(signal, m=3)

# 可视化
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
client.plot.get_renderer().render(spec)
```

---

## 5. DSL 查询

SQL-like 声明式查询语言，一行完成数据查询 + 指标计算。

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')

# WHERE 过滤
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

---

## 6. 自定义指标

```python
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, threshold=0.04):
    vol = data.close.pct_change().rolling(window).std()
    return vol.apply(lambda v: "high" if v > threshold else "low")

# 立即可在 DSL 中使用
result = client.run_dsl('''
    SELECT close, volatility_regime(close, 20) AS regime
    FROM ohlcv("BTC/USDT", "1d")
''')
```

---

## 7. 可视化

### 7.1 协议化绘图

```python
from stockstat.plot import PlotSpec

spec = PlotSpec(title="BTC 价格走势", x_label="日期", y_label="价格")
spec.add_series(name="close", data=data.close, kind="line")
spec.add_series(name="ma20", data=data.close.rolling(20).mean(), kind="line")

renderer = client.plot.get_renderer()
renderer.render(spec, path="btc.png")
```

### 7.2 回测可视化

```python
res.render("equity", path="equity.png")           # 资金曲线
res.render("drawdown", path="drawdown.png")       # 回撤
res.render("trades", path="trades.png")           # 交易标注
res.render("dashboard", path="dashboard.png")     # 综合仪表盘
```

支持 9 种图表：资金曲线、回撤、交易标注、收益分布、月度热力图、年度收益、参数网格热力图、水下曲线、综合仪表盘。

---

## 8. 回测

### 8.1 基础回测

```python
from stockstat.backtest import BacktestEngine, strategy, Order

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21: return
    ma5 = d.close.rolling(5).mean().iloc[-1]
    ma20 = d.close.rolling(20).mean().iloc[-1]
    pos = ctx.portfolio.get_position("BTC/USDT")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

data = client.ohlcv("BTC/USDT", start="2024-01-01")
res = client.backtest({"BTC/USDT": {"1d": data}}, ma_cross, initial_cash=10000)
print(res.summary())
```

### 8.2 多标的 / 多时间尺度

```python
data = {
    "BTC/USDT": {"1d": btc_1d, "1h": btc_1h},
    "ETH/USDT": {"1d": eth_1d, "1h": eth_1h},
}
res = client.backtest(data, strategy, initial_cash=10000)
```

### 8.3 成本 / 成交 / 执行模型

```python
from stockstat.backtest import (
    BacktestEngine, IntrabarExecution,
    BINANCE_SPOT_BNB, BINANCE_FUTURES_BNB,
)

engine = BacktestEngine(
    data=data,
    strategy=strategy,
    initial_cash=10000,
    cost_model=BINANCE_SPOT_BNB,           # Binance 现货 + BNB 折扣
    execution_model=IntrabarExecution(     # 同 bar 入场+出场
        intrabar_tf="1h", parent_tf="1d",
    ),
    allow_short=True,
    periods_per_year=52,
)
res = engine.run()
```

**8 种成本模型**：PercentCost / FixedCost / TieredCost / MinCost / StampDutyCost / ZeroCost / MakerTakerCost / BinanceCost（含 4 个 BINANCE_* 预设）

**7 种成交模型**：NextOpenFill / NextCloseFill / ThisCloseFill / VWAPFill / WorstPriceFill / IntrabarLimitFill / IntrabarFillModel

**2 种执行模型**：NextBarExecution（默认）/ IntrabarExecution（同 bar 入场+出场）

---

## 9. 回测高级功能

### 9.1 参数网格搜索

```python
from stockstat.backtest.optimizer import grid_search

results = grid_search(
    make_engine,
    param_grid={"short": [3, 5, 8, 10], "long": [20, 30, 40]},
    metric="sharpe",
    maximize=True,
)
print(results[0])  # 最佳参数组合
```

### 9.2 批量回测

```python
from stockstat.backtest.batch_runner import StrategyBatchRunner

runner = StrategyBatchRunner(data=data, initial_cash=10000)
results = runner.run_all_fees(
    strategies={"ma_cross": ma_cross_strategy, "rsi_reversal": rsi_strategy},
    fee_models={"spot": BINANCE_SPOT, "futures": BINANCE_FUTURES},
)
df = results.to_dataframe()
```

### 9.3 蒙特卡洛模拟

```python
from stockstat.backtest.montecarlo import monte_carlo_equity

curves = monte_carlo_equity(
    returns, initial=10000, n_samples=1000, seed=42,
)
# 1000 条模拟资金曲线
```

### 9.4 退出原因分析

```python
res = engine.run()
print(res.exit_reasons())  # 止损 / 止盈 / 信号反转 / 时间退出
```

---

## 10. 信号处理与非线性动力学

8 个高级分析函数：

| 函数 | 用途 |
|------|------|
| `wavelet_decompose(signal, scales, wavelet)` | 连续小波变换（CWT） |
| `spectral_entropy(signal, fs)` | 谱熵（频域复杂度） |
| `grey_relation(x0, xi, rho)` | 灰色关联度 |
| `gm11_predict(sequence)` | GM(1,1) 灰色预测 |
| `transfer_entropy(x, y, k, n_bins)` | 传递熵（有向信息流） |
| `hurst_dfa(signal)` | Hurst 指数（DFA） |
| `sample_entropy(signal, m, r)` | 样本熵 |
| `permutation_entropy(signal, m, tau)` | 排列熵 |

3 个 PlotSpec 工厂：`wavelet_scalogram` / `dfa_fit` / `psd_plot`

---

## 11. 结果导出

```python
# DataFrame 导出
df = data.reset_index()
df.to_csv("btc.csv", index=False)
df.to_parquet("btc.parquet")

# 回测结果导出
res.equity.to_csv("equity.csv")
res.fills_df.to_csv("fills.csv")
res.metrics()  # dict

# 通过 Codec
from stockstat._core.codec import ArrowCodec, ParquetCodec
arrow_bytes = ArrowCodec().encode(data)
parquet_bytes = ParquetCodec().encode(data)
```

---

## 12. CLI 命令行

```bash
# 数据采集
stockstat ingest AAPL --source yfinance --start 2024-01-01
stockstat ingest BTC/USDT --source binance --tf 1h

# 数据查询
stockstat query BTC/USDT --limit 5
stockstat query AAPL --start 2024-01-01 --format csv

# 标的管理
stockstat symbols
stockstat sources

# TUI 界面
stockstat tui
stockstat tui --host 192.168.1.100

# 服务启动
stockstat serve --host 0.0.0.0 --port 8000

# V3 集群管理（P7+）
stockstat cluster info
stockstat cluster workers
stockstat cluster stats

# V3 Worker 启动（独立包）
stockstat-compute worker --dispatcher-url http://localhost:8000
```

---

## 13. 离线模式

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage, SQLStorage

# 内存离线
client = V2Client(mode="offline", storage=MemoryStorage())
client.ingest("BTC/USDT", source="binance", start="2024-01-01")
df = client.ohlcv("BTC/USDT")

# 读取现有 SQLite
client = V2Client(mode="offline",
                  storage=SQLStorage(database_url="sqlite:///stockstat.db"))

# 持久化到新 SQLite
client = V2Client(mode="offline",
                  storage=SQLStorage(database_url="sqlite:///my_data.db"))
client.ingest("AAPL", source="yfinance", start="2024-01-01")
```

---

## 14. 插件系统

```python
from stockstat._core.plugin import PluginRegistry
from stockstat._domain.indicators import register_default_indicators
from stockstat._domain.sources import register_default_sources

reg = PluginRegistry()
register_default_indicators(reg)
register_default_sources(reg)

# 列出已注册插件
print(reg.list("indicators"))
print(reg.list("sources"))

# 调用
plugin = reg.get("sources", "binance")
df = plugin.fetch_ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
```

---

## 15. 管理界面

### 15.1 TUI 终端界面

```bash
stockstat tui                    # 连接本地服务器
stockstat tui --host 192.168.1.100
```

6 项交互式菜单：浏览标的 / 查询 OHLCV / 采集数据 / 数据统计 / 列出数据源 / 查看代理配置。

### 15.2 网页管理界面

浏览器访问 `http://storage-server:8000/admin/`：

| 页面 | 功能 |
|------|------|
| 概览仪表盘 | 标的数、行数、磁盘、数据覆盖甘特图 |
| 数据源浏览 | 分页 + 搜索 + 批量下载 + 手动输入任意标的 |
| 本地标的 | K 线图（缩放时懒加载）+ 导出 CSV |
| 配置 | 数据库 / 代理 / 缓存 / 磁盘 |
| 日志 | 采集历史（分页 + 过滤） |

### 15.3 V3 Dispatcher 监控

启用 `STOCKSTAT_DISPATCHER_ENABLED=true` + `STOCKSTAT_ADMIN_ENABLED=true` 后：

```bash
# 集群拓扑
curl http://localhost:8000/admin/api/dispatcher/cluster

# 任务历史
curl http://localhost:8000/admin/api/dispatcher/tasks?limit=10

# 任务统计
curl http://localhost:8000/admin/api/dispatcher/stats

# Autoscaler 指标
curl http://localhost:8000/admin/api/dispatcher/autoscaler
```

---

## 16. V3 分布式计算

### 16.1 设计理念

V3 在 v2.1 基础上新增**分布式计算层**，通过 `ComputeBackend` Protocol 将"在哪算"与"算什么"解耦：

```
Client → ComputeBackend Protocol → LocalComputeBackend (默认)
                                 → RemoteComputeBackend (HTTP → Dispatcher → Worker)
                                 → AutoComputeBackend (按规模自动路由)
```

**核心约束**：v1.7 / v2 公共 API 零修改；默认 `compute_backend=None` 时行为与 v2.1 完全一致。

### 16.2 三种 ComputeBackend

| 实现 | 场景 | 行为 |
|------|------|------|
| `LocalComputeBackend` | 默认 / 单机 | 后台线程执行，返回 TaskRef；与 v2.1 行为一致 |
| `RemoteComputeBackend` | 分布式 | 构建 TaskSpec → Transport 提交到 Dispatcher → 轮询结果 |
| `AutoComputeBackend` | 混合 | 重型任务(grid_search/monte_carlo)→远程；轻型→本地 |

### 16.3 V3 显式异步

```python
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)

# 显式异步提交
task = client.compute.remote(
    "backtest",
    symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01",
    strategy_ref=strategy_ref,
    initial_cash=10000,
)
print(task.id, task.status)  # UUID + "pending" / "running" / "completed"

# 等待结果
result = task.wait(timeout=3600)

# 非阻塞查询
info = client.compute_backend.get(task.id)
print(info.state, info.progress)

# 取消
task.cancel()

# 流式结果
for partial in task.stream_results():
    print(f"Progress: {partial.get('progress', 0):.0%}")
```

### 16.4 透明同步模式

```python
# 注入 RemoteComputeBackend，backtest() 自动 submit + wait
from stockstat._core.compute import RemoteComputeBackend
client = StockStatClient(
    host="localhost", port=8000,
    compute_backend=RemoteComputeBackend("http://localhost:8000"),
)
result = client.backtest(data, strategy, initial_cash=10000)
# 内部：build TaskSpec → submit → wait → 返回 BacktestResult

# async_submit=True 返回 TaskRef
task = client.backtest(data, strategy, async_submit=True)
# ... 做其他事 ...
result = task.wait(timeout=3600)
```

---

## 17. V3 ComputeBackend 兼容层

### 17.1 StockStatClient 接入

```python
from stockstat import StockStatClient
from stockstat._core.compute import (
    LocalComputeBackend, RemoteComputeBackend, AutoComputeBackend,
)

# 默认（不传 compute_backend）→ LocalComputeBackend 惰性创建
client = StockStatClient(host="localhost", port=8000)

# 显式 LocalComputeBackend
client = StockStatClient(compute_backend=LocalComputeBackend())

# 远程
client = StockStatClient(
    compute_backend=RemoteComputeBackend("http://dispatch:9000"),
)

# 自动路由
client = StockStatClient(compute_backend=AutoComputeBackend(
    local=LocalComputeBackend(),
    remote=RemoteComputeBackend("http://dispatch:9000"),
))
```

### 17.2 V2Client 接入

```python
from stockstat._api.client import V2Client
from stockstat._core.compute import RemoteComputeBackend

client = V2Client(mode="offline",
                  compute_backend=RemoteComputeBackend("http://dispatch:9000"))
```

### 17.3 兼容性矩阵

| 客户端 | ComputeBackend | 行为 |
|--------|---------------|------|
| `StockStatClient` | `LocalComputeBackend`（默认） | 完全等同 v2.1 |
| `StockStatClient` | `RemoteComputeBackend` | 透明同步 + 显式异步 |
| `V2Client(mode="online")` | `LocalComputeBackend`（默认） | 完全等同 v2.1 |
| `V2Client(mode="online")` | `RemoteComputeBackend` | 透明同步 + 显式异步 |
| `V2Client(mode="offline")` | `LocalComputeBackend`（默认） | 完全等同 v2.1 |
| `V2Client(mode="offline")` | `RemoteComputeBackend` | 离线数据 + 远程计算 |

---

## 18. V3 Dispatcher 部署

### 18.1 作为 Storage 插件（场景 D）

```bash
# 1. 启动 Storage + Dispatcher（同进程）
STOCKSTAT_DISPATCHER_ENABLED=true \
STOCKSTAT_ADMIN_ENABLED=true \
stockstat serve --host 0.0.0.0 --port 8000

# 2. 启动 Worker（另一台机器）
stockstat-compute worker --dispatcher-url http://storage:8000 --concurrency 8

# 3. Client
client = StockStatClient(
    host="storage", port=8000,
    compute_backend=RemoteComputeBackend("http://storage:8000"),
)
```

### 18.2 独立 Dispatcher（场景 E）

```bash
# 1. 启动 Storage
stockstat serve --host 0.0.0.0 --port 8000

# 2. 启动 Dispatcher（独立进程，Redis 队列）
STOCKSTAT_DISPATCHER_ENABLED=true \
STOCKSTAT_DISPATCHER_QUEUE=redis \
REDIS_URL=redis://redis:6379/0 \
stockstat serve --host 0.0.0.0 --port 9000

# 3. 启动多个 Worker
stockstat-compute worker --dispatcher-url http://dispatcher:9000 --concurrency 8

# 4. Client
client = StockStatClient(
    compute_backend=RemoteComputeBackend("http://dispatcher:9000"),
)
```

### 18.3 Docker Compose

```bash
docker compose up -d
# 启动 db + redis + api + dispatcher + 4 个 worker
```

### 18.4 Dispatcher REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/dispatch/submit` | POST | 提交 TaskSpec |
| `/dispatch/status/{id}` | GET | 查询状态 |
| `/dispatch/result/{id}` | GET | 获取结果 |
| `/dispatch/cancel/{id}` | POST | 取消任务 |
| `/dispatch/cluster` | GET | 集群拓扑 |
| `/dispatch/register` | POST | Worker 注册 |
| `/dispatch/heartbeat` | POST | Worker 心跳 |
| `/dispatch/assign` | POST | Worker 拉取任务 |
| `/dispatch/complete` | POST | 回传结果 |
| `/dispatch/fail` | POST | 上报失败 |
| `/dispatch/partial` | POST | 流式部分结果 |
| `/dispatch/preempt/{id}` | POST | 抢占任务 |
| `/dispatch/resume/{id}` | POST | 恢复任务 |
| `/dispatch/drain/{id}` | POST | Worker 下线 |
| `/dispatch/discover` | GET | 服务发现 |
| `/dispatch/autoscaler` | GET | Autoscaler 指标 |
| `/dispatch/sub/register` | POST | 子 Dispatcher 注册 |
| `/dispatch/tasks/history` | GET | 任务历史 |
| `/dispatch/tasks/stats` | GET | 任务统计 |
| `/api/v1/tasks` | POST/GET | V2 §10.2 兼容 |

---

## 19. V3 Worker 部署

### 19.1 启动 Worker

```bash
# 基础启动
stockstat-compute worker \
    --dispatcher-url http://localhost:8000 \
    --concurrency 8 \
    --alias "gpu-box-alpha" \
    --label rack=A-12 \
    --label zone=datacenter-east

# 支持抢占
stockstat-compute worker \
    --dispatcher-url http://dispatch:9000 \
    --preemptable

# 配置文件（TOML）
# stockstat-compute.toml:
# [worker]
# alias = "gpu-box-alpha"
# concurrency = 8
# dispatcher_url = "http://dispatch:9000"
# [worker.labels]
# rack = "A-12"
```

### 19.2 Worker CLI 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--dispatcher-url` | 必填 | Dispatcher URL |
| `--concurrency` | CPU 核数 | 最大并发任务数 |
| `--alias` | hostname-pid | Worker 别名 |
| `--label key=value` | — | 标签（可重复） |
| `--capability` | 全部 | 任务类型能力（可重复） |
| `--preemptable` | false | 允许被抢占 |
| `--poll-interval` | 1.0s | 任务轮询间隔 |
| `--heartbeat-interval` | 10.0s | 心跳间隔 |

### 19.3 Worker 生命周期

```
启动 → detect_hardware() → POST /dispatch/register
                          ↓
            心跳线程（10s）→ POST /dispatch/heartbeat
                          ↓
            主循环 → POST /dispatch/assign → 执行 → POST /dispatch/complete
                          ↓
            SIGTERM → stop() → 等待活跃任务 → POST /dispatch/unregister → 退出
```

### 19.4 Worker 状态机

| status | 含义 | Dispatcher 行为 |
|--------|------|----------------|
| `online` | 正常，接受任务 | 正常分发 |
| `busy` | 活动任务 = concurrency | 不再分发新任务 |
| `draining` | 优雅下线中 | 等待现有任务完成 |
| `offline` | 心跳超时（30s） | 移除 + 任务重新分配 |

---

## 20. V3 集群管理

### 20.1 查询集群拓扑

```python
info = client.compute.cluster_info()

print(f"Dispatcher: {info['dispatcher']['alias']} @ {info['dispatcher']['address']}")
print(f"  status: {info['dispatcher']['status']}")
print(f"  uptime: {info['dispatcher']['uptime_s']}s")
print(f"  queue_depth: {info['dispatcher']['queue_depth']}")
print(f"  cache: {info['dispatcher']['cache_size_mb']}MB ({info['dispatcher']['cache_hit_rate']:.1%} hit)")

print(f"\nWorkers ({info['stats']['online_workers']}/{info['stats']['total_workers']} online):")
for w in info["workers"]:
    print(f"  {w['alias']:20s}  {w['status']:8s}  "
          f"CPU {w['hardware']['cpu']['cores_logical']}核  "
          f"内存 {w['hardware']['memory']['total_gb']}GB  "
          f"负载 {w['load'].get('cpu_percent', 0):.1f}%  "
          f"活动 {w['active_tasks']}/{w['concurrency']}")

print(f"\nSub-dispatchers: {len(info.get('sub_dispatchers', []))}")
for sub in info.get("sub_dispatchers", []):
    print(f"  {sub['alias']:20s}  {sub['address']}  {sub['status']}")

print(f"\nStats:")
for k, v in info["stats"].items():
    print(f"  {k}: {v}")
```

### 20.2 按标签过滤

```python
info = client.compute.cluster_info(filter_labels={"zone": "datacenter-east"})
for w in info["workers"]:
    print(w["alias"])
```

### 20.3 Autoscaler 指标

```python
import httpx
metrics = httpx.get("http://dispatch:8000/dispatch/autoscaler").json()
print(f"Queue depth: {metrics['queue_depth']}")
print(f"Active tasks: {metrics['active_tasks']}")
print(f"Available concurrency: {metrics['available_concurrency']}")
print(f"Scale up recommended: {metrics['scale_up_recommended']}")
print(f"Scale down recommended: {metrics['scale_down_recommended']}")
```

### 20.4 任务历史

```python
import httpx
resp = httpx.get("http://dispatch:8000/dispatch/tasks/history?limit=10")
for h in resp.json()["history"]:
    print(f"  {h['task_id'][:8]}...  {h['task_type']:15s}  {h['state']:10s}  "
          f"worker={h.get('worker_id', '-')[:8]}")

# 按状态过滤
resp = httpx.get("http://dispatch:8000/dispatch/tasks/history?state=failed")
fails = resp.json()["history"]
print(f"\nFailed tasks: {len(fails)}")
for f in fails:
    print(f"  {f['task_id'][:8]}...  error: {f.get('error', '')[:80]}")
```

### 20.5 任务统计

```python
import httpx
stats = httpx.get("http://dispatch:8000/dispatch/tasks/stats").json()
print(f"Total tasks: {stats['total_tasks']}")
print(f"By state: {stats['by_state']}")
print(f"By type: {stats['by_type']}")
print(f"Avg duration: {stats['avg_duration_s']}s")
```

---

## 21. V3 任务生命周期

### 21.1 完整流程

```python
# 1. Client 构建 TaskSpec
from stockstat._core.contracts.task import (
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
)

spec = TaskSpec(
    task_id=new_task_id(),
    data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d",
                       start="2024-01-01", end="2024-12-31"),
    compute_spec=ComputeSpec(
        task_type="grid_search",
        strategy_ref=strategy_ref,
        param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
        metric="sharpe",
        maximize=True,
        initial_cash=10000,
    ),
    dispatch_spec=DispatchSpec(
        split_strategy="param_wise",
        max_workers=4,
        timeout=3600,
        retry_count=2,
        preemptable=True,
    ),
    trace_id="my-trace-001",
)

# 2. 提交
task = client.compute_backend.submit(spec)
print(f"Submitted: {task.id}, status={task.status}")

# 3. 轮询状态
import time
while not task.ready():
    info = client.compute_backend.get(task.id)
    print(f"  state={info.state.value}, progress={info.progress:.0%}")
    time.sleep(1)

# 4. 获取结果
result = task.result()  # 或 task.wait(timeout=3600)
print(f"Best params: {result[0]['params']}, sharpe: {result[0]['sharpe']}")
```

### 21.2 任务状态

```
pending → running → completed
   |         |
   |         |--> failed
   |         |
   |         +--> cancelled
   |
   +--> cancelled
```

### 21.3 流式结果

```python
# grid_search 进度推送
for partial in task.stream_results():
    if "progress" in partial:
        print(f"  Progress: {partial['progress']:.0%} "
              f"({partial.get('completed', 0)}/{partial.get('total', 0)})")
    else:
        # 最终结果
        print(f"  Final result: {len(partial)} combinations")
```

### 21.4 任务取消

```python
task.cancel()
# 或
client.compute_backend.cancel(task.id)
```

### 21.5 抢占与恢复

```python
import httpx
# 抢占
httpx.post(f"http://dispatch:8000/dispatch/preempt/{task.id}?worker_id=w1")
# 恢复
httpx.post(f"http://dispatch:8000/dispatch/resume/{task.id}?worker_id=w1")
```

### 21.6 错误处理

```python
from stockstat._core.errors import (
    TaskError, TaskNotReadyError, TaskCancelledError,
    TaskTimeoutError, TaskNotFoundError,
)

try:
    result = task.wait(timeout=60)
except TaskError as e:
    print(f"Task failed: {e.message}")
    print(f"Error code: {e.code}")
    print(f"Context: {e.context}")
except TaskCancelledError:
    print("Task was cancelled")
except TaskTimeoutError:
    print("Task timed out")
```

---

## 22. V3 部署场景

### 22.1 场景 A：单机全栈（默认）

```python
client = StockStatClient()  # 默认 LocalComputeBackend
result = client.backtest(data, strategy)
```

### 22.2 场景 B：存储-计算分离

```python
client = StockStatClient(host="storage", port=8000)
# 数据通过 HTTP 拉取，计算在本地
data = client.ohlcv("BTC/USDT")
result = client.backtest(data, strategy)
```

### 22.3 场景 C：离线模式

```python
client = V2Client(mode="offline", storage=MemoryStorage())
client.ingest("BTC/USDT", source="binance", start="2024-01-01")
result = client.backtest(client.ohlcv("BTC/USDT"), strategy)
```

### 22.4 场景 D：Dispatcher + Worker

```bash
# Terminal 1: Storage + Dispatcher
STOCKSTAT_DISPATCHER_ENABLED=true stockstat serve --port 8000

# Terminal 2: Worker
stockstat-compute worker --dispatcher-url http://localhost:8000
```

```python
client = StockStatClient(
    compute_backend=RemoteComputeBackend("http://localhost:8000"),
)
result = client.backtest(data, strategy)
```

### 22.5 场景 E：独立 Dispatcher + Worker 集群

```bash
# 3 个进程
stockstat serve --port 8000                    # Storage
STOCKSTAT_DISPATCHER_QUEUE=redis \
REDIS_URL=redis://redis:6379/0 \
stockstat serve --port 9000                    # Dispatcher
stockstat-compute worker --dispatcher-url http://localhost:9000 --concurrency 8
```

### 22.6 场景 F：多级 Dispatcher

```python
# 主 Dispatcher
POST /dispatch/sub/register
{
    "sub_id": "sub-east-1",
    "alias": "dispatch-east",
    "address": "http://east:9000",
    "parent_url": "http://parent:8000"
}

# 查询全局拓扑
info = client.compute.cluster_info()
# info["sub_dispatchers"] 含所有子 Dispatcher
```

### 22.7 部署测试

```bash
cd tests/deployments

# 单机
python test_case_a_single_machine.py

# 存储-计算分离
python test_case_b_storage_separated.py --host 192.168.1.100

# 离线
python test_case_c_offline.py

# 显式 LocalComputeBackend
python test_case_d_local_compute_backend.py

# V3 分布式
python test_case_e_dispatcher_worker.py

# V3 多级
python test_case_f_multilevel.py
```

---

## 23. PAXG 周末相关性分析

V3 验证：132 次回测与基线字节级一致。

```bash
cd working/PAXG-Weekend-Monday-Law-v5-redo/phase2_backtest

# 运行 132 次回测
python run_redo.py

# V3 与直调路径对比
python compare_v3.py
# Expected: All V3 LocalComputeBackend results identical to direct path

# 查看结果
cat results/all_metrics_redo.csv | head
```

---

## 24. 连接与性能测试

```bash
# 连接通路测试
python tests/test_connection.py --host localhost --port 8000

# 通讯性能测试
python tests/test_perf.py --host localhost --port 8000 --rounds 10
```

---

## 25. 启动脚本

```bash
# 极简启动
backend/start.bat            # Windows
backend/start.sh             # Linux/macOS

# 完整配置（命令行参数 + 交互式配置）
backend/serve.bat --config   # Windows
backend/serve.sh --config    # Linux/macOS

# V3 Worker
stockstat-compute worker --dispatcher-url http://localhost:8000
```

---

## 26. 环境变量参考

### 26.1 后端

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | 数据库连接字符串 |
| `STOCKSTAT_PROXY_ENABLED` | `false` | 启用代理 |
| `STOCKSTAT_PROXY_TYPE` | `http` | 代理类型（http/socks5） |
| `STOCKSTAT_PROXY_URL` | — | 代理 URL |
| `STOCKSTAT_ADMIN_ENABLED` | `true` | 启用网页管理界面 |
| `STOCKSTAT_DEFAULT_SOURCE` | `yfinance` | 默认数据源 |
| `STOCKSTAT_DISPATCHER_ENABLED` | `false` | **V3** 启用 Dispatcher |
| `STOCKSTAT_DISPATCHER_QUEUE` | `memory` | **V3** 队列后端（memory/redis） |
| `STOCKSTAT_DISPATCHER_CACHE_MB` | `512` | **V3** DataCache 最大尺寸 |
| `REDIS_URL` | — | **V3** Redis 连接 |

### 26.2 前端

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKSTAT_HOST` | `localhost` | 默认主机 |
| `STOCKSTAT_PORT` | `8000` | 默认端口 |
| `STOCKSTAT_USE_HTTPS` | — | 启用 HTTPS |
| `STOCKSTAT_DISPATCHER_URL` | — | **V3** Dispatcher URL |
| `STOCKSTAT_TRANSPORT` | `in_process` | **V3** 传输类型 |
| `STOCKSTAT_SKIP_NETWORK` | `false` | 测试时跳过网络步骤 |
| `STOCKSTAT_TEST_SYMBOL` | `BTC/USDT` | 测试标的 |
| `STOCKSTAT_TEST_START` | `2024-01-01` | 测试起始日期 |
| `STOCKSTAT_TEST_END` | `2024-12-31` | 测试结束日期 |

---

## 附录：测试运行

```bash
# 后端测试
cd backend && python -m pytest tests/ -v          # 15 项

# 前端测试（含 V3）
cd frontend && python -m pytest tests/ -v          # 814 项 + 6 跳过

# 部署场景测试
cd tests/deployments
python test_case_a_single_machine.py              # 单机
python test_case_e_dispatcher_worker.py           # V3 分布式
python test_case_f_multilevel.py                  # V3 多级

# PAXG 研究验证
cd working/PAXG-Weekend-Monday-Law-v5-redo/phase2_backtest
python run_redo.py                                 # 132 次回测
python compare_v3.py                               # V3 与直调对比
```

**总计**：922 项测试通过 + 6 项 Redis 跳过 + 132 次 PAXG 回测字节级一致。

---

*V3 使用文档以代码实现为准。*
