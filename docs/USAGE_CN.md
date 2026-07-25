# StockStat V3.1 使用文档

> **版本**：v3.1
> **测试基线**：882 项测试通过 + 1 跳过
> **关联**：[README_CN.md](../README_CN.md) | [DESIGN_CN.md](../DESIGN_CN.md)

---

## 目录

1. [环境准备](#1-环境准备)
2. [数据采集与存储](#2-数据采集与存储)
3. [计算指标](#3-计算指标)
4. [回测](#4-回测)
5. [批量回测与网格搜索](#5-批量回测与网格搜索)
6. [统计分析](#6-统计分析)
7. [信号处理](#7-信号处理)
8. [非线性动力学](#8-非线性动力学)
9. [灰色系统](#9-灰色系统)
10. [机器学习](#10-机器学习)
11. [组合风险管理](#11-组合风险管理)
12. [DSL 策略表达式](#12-dsl-策略表达式)
13. [可视化](#13-可视化)
14. [结果导出](#14-结果导出)
15. [CLI 命令行](#15-cli-命令行)
16. [分布式计算](#16-分布式计算)
17. [部署场景](#17-部署场景)
18. [PostgreSQL 配置](#18-postgresql-配置)
19. [REST API 参考](#19-rest-api-参考)
20. [环境变量参考](#20-环境变量参考)

---

## 1. 环境准备

### 1.1 安装

V3.1 采用多包发布。五个模块包可以独立安装，也可以一次性全部安装。最常见的方式是开发安装（`-e` 可编辑模式），便于贡献者修改代码后立即生效：

```bash
# 方式一：五大模块独立安装（推荐贡献者使用）
pip install -e packages/foundation
pip install -e packages/storage
pip install -e packages/compute
pip install -e packages/invocation
pip install -e packages/dispatcher

# 方式二：用户安装（仅用户入口，自动拉取必要依赖）
pip install -e packages/invocation
```

安装顺序不影响最终结果——pip 会自动解析依赖。但建议先装 Foundation，因为它被其他四个包依赖。

### 1.2 可选依赖

V3.1 把重型依赖设为可选，核心功能在最小依赖下即可运行。按需启用对应的 extras：

```bash
pip install -e packages/storage[postgres]     # PostgreSQL 驱动（psycopg2）
pip install -e packages/compute[ml]           # scikit-learn + xgboost（机器学习）
pip install -e packages/compute[signal]       # PyWavelets（小波变换）
pip install -e packages/compute[nonlinear]    # nolds（非线性分析增强）
pip install -e packages/foundation[redis]     # Redis 传输（跨进程持久化队列）
pip install -e packages/foundation[msgpack]   # Msgpack 编码（紧凑二进制）
pip install matplotlib                         # 可视化（ChartSpec 渲染）
```

> **优雅降级**：未安装可选依赖时，相关功能不会让程序崩溃，而是自动 fallback 到替代实现或抛出清晰的 `ImportError` 并提示安装命令。例如：
> - PyWavelets 未装时，`wavelet` handler fallback 为自实现的 Morlet CWT。
> - redis 未装时，`RedisTransport` / `RedisTaskQueue` 抛出 `ImportError` 并提示 `pip install stockstat-dispatcher[redis]`。
> - yfinance 未装时，对应测试跳过（1 skipped）。

### 1.3 验证安装

安装完成后，运行以下代码确认所有包正确加载，且 38 个 handler 全部注册：

```python
import stockstat_foundation, stockstat_compute, stockstat_backend
import stockstat_dispatcher, stockstat
print("All V3.1 packages OK")
print("Foundation:", stockstat_foundation.__version__)
print("Handlers:", len(stockstat_compute.ALL_TASK_TYPES))  # 38
```

如果输出 `Handlers: 38`，说明 Compute 模块的所有 handler 子包已被正确导入并注册。

---

## 2. 数据采集与存储

数据是量化研究的起点。V3.1 的 Storage 模块提供 OHLCV 数据的持久化、查询和采集能力，支持 SQLite（开发）和 PostgreSQL（生产）两种数据库。

### 2.1 启动 Storage 服务

Storage 是一个 FastAPI 服务，通过 CLI 启动。默认使用 SQLite（WAL 模式），无需额外配置：

```bash
# SQLite（默认，零配置）
stockstat-backend serve --host 0.0.0.0 --port 8000

# PostgreSQL（生产环境）
STOCKSTAT_DATABASE_URL=postgresql://user:pwd@host:5432/stockstat \
stockstat-backend serve --host 0.0.0.0 --port 8000
```

启动后可访问 `http://localhost:8000/docs` 查看 Swagger 文档，或 `http://localhost:8000/health` 检查健康状态。

### 2.2 采集数据

V3.1 提供 3 个数据源适配器。最便捷的方式是通过 Client 的 `ingest` 方法写入：

```python
from stockstat import StockStatClient

client = StockStatClient(storage_url="http://localhost:8000")

# 方式一：从 Binance 采集
from stockstat_backend import BinanceAdapter
adapter = BinanceAdapter()
df = adapter.fetch_ohlcv("BTCUSDT", "1d")
rows = client.ingest("BTC/USDT", "1d", df)
print(f"写入 {rows} 条")

# 方式二：从合成数据源采集（开发/测试，无需网络）
from stockstat_backend import SyntheticAdapter
adapter = SyntheticAdapter(seed=42)
df = adapter.fetch_ohlcv("TEST/USDT", "1d")
client.ingest("TEST/USDT", "1d", df)

# 方式三：直接写入 DataFrame
import pandas as pd
df = pd.DataFrame({
    "timestamp": pd.date_range("2024-01-01", periods=100, freq="D"),
    "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...,
})
client.ingest("CUSTOM", "1d", df)
```

`ingest(symbol, timeframe, data)` 返回写入行数。数据会自动去重（复合主键 `(symbol, timeframe, timestamp)`）。

### 2.3 查询数据

```python
# 查询单个标的的 OHLCV
df = client.ohlcv("BTC/USDT", timeframe="1d", start="2024-01-01")
print(df.head())
#                           open     high     low    close    volume
# timestamp
# 2024-01-01  42000.0  42500.0  41800.0  42300.0  1500.0
# ...

# 列出所有已入库的标的
symbols = client.list_symbols()
print(symbols)  # ["BTC/USDT", "TEST/USDT", ...]
```

`ohlcv()` 返回 pandas DataFrame，列名为 `timestamp` / `open` / `high` / `low` / `close` / `volume`。DataClient 内置进程内缓存，重复查询同一参数不会重复请求 Storage。

### 2.4 CLI 数据命令

```bash
# 从数据源采集并入库
stockstat data ingest --symbol BTC/USDT --source binance

# 查询数据（默认显示前 20 行）
stockstat data fetch BTC/USDT --timeframe 1d

# 列出所有标的
stockstat data list
```

`stockstat-backend` 也提供独立的数据 CLI：

```bash
stockstat-backend ingest --symbol BTC/USDT --source binance
stockstat-backend list-symbols
stockstat-backend init-db          # 初始化数据库表
```

---

## 3. 计算指标

V3.1 内置 40+ 技术指标，通过 `client.compute.*` 调用。本地后端下即时返回，远程后端下自动构建 `indicator` TaskSpec 提交。所有指标接收 pandas Series 或 DataFrame，返回 Series 或 DataFrame。

### 3.1 趋势指标

趋势指标衡量价格的方向性。下例展示常用的移动平均线家族和 MACD：

```python
# 简单移动平均（SMA）
sma = client.compute.ma(data.close, window=20)

# 指数移动平均（EMA，权重衰减更快，对近期价格更敏感）
ema = client.compute.ema(data.close, window=12)

# 加权移动平均（WMA，线性权重）
wma = client.compute.wma(data.close, window=20)

# 双指数移动平均（DEMA，减少滞后）
dema = client.compute.dema(data.close, window=20)

# 三指数移动平均（TEMA，进一步减少滞后）
tema = client.compute.tema(data.close, window=20)

# Hull 移动平均（HMA，平滑且低滞后）
hma = client.compute.hma(data.close, window=20)

# MACD — 返回 DataFrame，包含 macd / signal / histogram 三列
macd_df = client.compute.macd(data.close, fast=12, slow=26, signal=9)
print(macd_df.tail())
#                    macd    signal  histogram
# 2024-04-26  120.5  80.3      40.2
```

此外还有 `adx`（平均趋向指数，衡量趋势强度）、`dpo`（去趋势价格震荡）、`trix`（三重平滑均线）。

![收盘价 + MA + 布林带](../docs/images/indicators_bollinger.png)

### 3.2 振荡指标

振荡指标衡量价格的超买超卖状态，通常在固定区间内波动：

```python
# RSI（相对强弱指数，0~100，>70 超买，<30 超卖）
rsi = client.compute.rsi(data.close, window=14)

# KD 随机指标 — 返回 DataFrame，包含 k / d 两列
kd_df = client.compute.kd(data.high, data.low, data.close, k_window=9, d_window=3)

# Williams %R（-100~0，接近 0 为超买）
wr = client.compute.williams_r(data.high, data.low, data.close, window=14)

# CCI（商品通道指数，>100 超买，<-100 超卖）
cci = client.compute.cci(data.high, data.low, data.close, window=20)
```

![RSI 超买超卖](../docs/images/indicators_rsi.png)

### 3.3 波动率指标

波动率指标衡量价格的离散程度：

```python
# 布林带 — 返回 DataFrame，包含 upper / middle / lower / bandwidth
bb = client.compute.bollinger(data.close, window=20, std=2.0)

# ATR（平均真实波幅，衡量波动幅度）
atr = client.compute.atr(data.high, data.low, data.close, window=14)

# Keltner 通道（基于 ATR 的通道）
keltner = client.compute.keltner(data.high, data.low, data.close, window=20, mult=1.5)

# Donchian 通道（最高/最低价通道）
donchian = client.compute.donchian(data.high, data.low, window=20)

# 滚动标准差
stddev = client.compute.stddev(data.close, window=20)
```

### 3.4 统计指标

统计指标基于滚动窗口的统计量：

```python
# 滚动相关系数
corr = client.compute.rolling_corr(x, y, window=20)

# 滚动 Beta（资产相对市场的敏感度）
beta = client.compute.rolling_beta(asset, market, window=20)

# 滚动 Z-Score（标准化）
zsc = client.compute.zscore(data.close, window=20)

# 滚动百分位
pct = client.compute.percentile(data.close, window=20)
```

### 3.5 非线性指标

非线性指标衡量时间序列的复杂度和确定性：

```python
# Hurst 指数（R/S 法）— H≈0.5 随机游走，H>0.5 持久性，H<0.5 反持久性
hurst = client.compute.hurst_rs(data.close)

# 样本熵 — 越高越复杂
sampen = client.compute.sample_entropy(data.close[:100], m=2)

# 排列熵 — 衡量序列的规则性
permen = client.compute.permutation_entropy(data.close[:100], m=4, tau=1)
```

![MACD 柱状图](../docs/images/indicators_macd.png)

---

## 4. 回测

回测是量化研究的核心环节。V3.1 的 BacktestEngine 是事件驱动、按 bar 推进的引擎，支持自定义策略、多种费率模型、成交模型和执行模型。

### 4.1 基础回测

最简单的回测——买入持有策略。策略是一个接收 `(i, bar, data, ctx)` 的函数，返回 `Signal` 或 `None`：

```python
from stockstat import StockStatClient
from stockstat_compute import Signal

client = StockStatClient()

def buy_and_hold(i, bar, data, ctx):
    """第一根 K 线买入，之后持有不动。"""
    if i == 0:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
    return None

result = client.backtest(data, buy_and_hold, initial_cash=10000)
print(result.summary())
# BacktestResult: total_return=105.79%, sharpe=0.627, max_drawdown=-27.84%
```

`result` 是 `BacktestResult` 对象，包含：
- `metrics`：`BacktestMetrics`（18 项指标）
- `equity_curve`：权益曲线 DataFrame
- `trades`：交易列表
- `summary()`：人类可读的摘要文本

### 4.2 MA 交叉策略

经典的均线交叉策略——短期均线上穿长期均线买入，下穿卖出：

```python
def ma_cross(i, bar, data, ctx):
    if i < 20:
        return None
    ma5 = data["close"].iloc[i-5:i+1].mean()
    ma20 = data["close"].iloc[i-20:i+1].mean()
    prev_ma5 = data["close"].iloc[i-6:i].mean()
    prev_ma20 = data["close"].iloc[i-21:i].mean()
    if prev_ma5 <= prev_ma20 and ma5 > ma20:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
    if prev_ma5 >= prev_ma20 and ma5 < ma20:
        return Signal(timestamp=bar["timestamp"], symbol="TEST", side="sell")
    return None

result = client.backtest(data, ma_cross, initial_cash=10000,
                         cost_model="F1_SpotNoBNB")
```

也可以用 `StrategyBase` 类定义有状态的策略：

```python
from stockstat_compute import StrategyBase

class MaCross(StrategyBase):
    name = "ma_cross"
    def __init__(self, short=5, long=20):
        self.short = short
        self.long = long
    def on_bar(self, i, bar, data, ctx):
        if i < self.long:
            return None
        s = data["close"].iloc[i-self.short:i+1].mean()
        l = data["close"].iloc[i-self.long:i+1].mean()
        ps = data["close"].iloc[i-self.short-1:i].mean()
        pl = data["close"].iloc[i-self.long-1:i].mean()
        if ps <= pl and s > l:
            return Signal(timestamp=bar["timestamp"], symbol="TEST", side="buy")
        if ps >= pl and s < l:
            return Signal(timestamp=bar["timestamp"], symbol="TEST", side="sell")
        return None

result = client.backtest(data, MaCross(short=5, long=20), initial_cash=10000)
```

![回测资金曲线 + 回撤](../docs/images/backtest_equity_drawdown.png)

### 4.3 费率模型

V3.1 内置 10 个预定义费率模型，覆盖主流交易场景：

| 名称 | 费率 | 说明 |
|------|------|------|
| `default` | 0.1% | 默认费率 |
| `zero` | 0% | 无手续费（基准对比） |
| `F1_SpotNoBNB` | 0.1% | Binance 现货不用 BNB 抵扣 |
| `F2_SpotBNB` | 0.075% | Binance 现货用 BNB 抵扣 |
| `F3_FutNoBNB` | 0.04% | Binance 合约不用 BNB |
| `F4_FutBNB` | 0.018% | Binance 合约用 BNB |
| `binance_spot` | 0.1% | Binance 现货（同 F1） |
| `binance_futures_bnb` | 0.018% | Binance 合约 BNB（同 F4） |
| `binance_futures` | 0.04% | Binance 合约（同 F3） |
| `stock` | 0.05% | 美股（最低 $5） |

```python
# 使用预定义费率
result = client.backtest(data, strategy, cost_model="F4_FutBNB")

# 使用自定义费率（传入数字字符串）
result = client.backtest(data, strategy, cost_model="0.0008")  # 0.08%
```

### 4.4 成交模型

成交模型决定订单以何价成交。V3.1 提供 5 种模型，均支持 `slippage_bps`（滑点，单位为基点）：

| 名称 | 成交价 | 适用 |
|------|--------|------|
| `next_open` | 下一根 K 线 open | 默认，最贴近实盘 |
| `this_close` | 当前 K 线 close | 信号即成交 |
| `next_close` | 下一根 K 线 close | 延迟成交 |
| `intrabar_fill` | 下一根 (H+L+C)/3 | 近似 VWAP |
| `signal_price` | 信号价 | 限价单 |

```python
result = client.backtest(data, strategy,
                         fill_model="next_open",
                         cost_model="F1_SpotNoBNB")
```

### 4.5 执行模型

执行模型决定订单何时触发：

| 名称 | 行为 |
|------|------|
| `next_bar` | 下一根 K 线触发（默认） |
| `intrabar` | bar 内触发 |

```python
result = client.backtest(data, strategy, execution_model="intrabar")
```

### 4.6 异步回测

对于耗时较长的回测，可以使用异步模式——提交后立即返回 `TaskRef`，在需要结果时再 `wait()`：

```python
# 异步提交
task = client.backtest(data, strategy, async_submit=True)
print(task.id, task.status)  # UUID + "pending"

# ... 做其他事情 ...

# 阻塞等待结果（最多等 3600 秒）
result = task.wait(timeout=3600)
```

`TaskRef` 还支持 `result()`（非阻塞获取）、`ready()`（检查是否完成）、`cancel()`（取消任务）、`stream_results()`（流式获取部分结果）。

---

## 5. 批量回测与网格搜索

### 5.1 批量回测（策略 × 费率）

批量回测同时运行多个策略和多种费率，返回汇总 DataFrame。适合横向对比不同策略在不同费率下的表现：

```python
strategies = {
    "buy_hold": buy_and_hold,
    "ma_cross_5_20": lambda i, b, d, c: ma_cross(i, b, d, c, 5, 20),
    "ma_cross_3_10": lambda i, b, d, c: ma_cross(i, b, d, c, 3, 10),
}
df = client.batch_backtest(
    data, strategies,
    fee_models=["F1_SpotNoBNB", "F2_SpotBNB", "F3_FutNoBNB", "F4_FutBNB"],
    initial_cash=10000,
)
print(df[["strategy", "fee_model", "sharpe", "max_drawdown"]])
#        strategy        fee_model   sharpe  max_drawdown
# 0    buy_hold      F1_SpotNoBNB    0.627        -0.278
# 1    buy_hold      F2_SpotBNB      0.631        -0.276
# ...
```

在分布式场景下，`batch_backtest` 会被 `shard_task` 按 `param_wise` 策略分片——每个 Worker 执行一部分策略×费率组合，最后 `merge_results` 拼接为完整 DataFrame。

![批量回测 Sharpe 对比](../docs/images/backtest_batch_sharpe.png)

### 5.2 网格搜索

网格搜索在参数空间上穷举所有组合，找出最优参数。`grid_search` 接收 `StrategyBase` 子类和参数网格，返回按指标排序的 DataFrame：

```python
df = client.grid_search(
    data, MaCross,
    param_grid={"short": [3, 5, 8, 10], "long": [20, 30, 40, 50]},
    metric="sharpe",    # 排序指标
    maximize=True,      # 降序排列（找最大 Sharpe）
    initial_cash=10000,
)
print(df.head())
#    short  long    sharpe  total_return  max_drawdown
# 0      5    20     0.812        0.452        -0.184
# 1      3    20     0.768        0.398        -0.201
# ...
```

参数网格的笛卡尔积为 4×4=16 种组合。分布式下按 `param_wise` 分片，每个 Worker 跑一部分组合。

### 5.3 蒙特卡洛模拟

蒙特卡洛通过随机重采样收益序列，评估策略的统计稳健性：

```python
from stockstat_compute import MonteCarloEngine

engine = MonteCarloEngine(data, buy_and_hold, initial_cash=10000,
                          n_simulations=1000, seed=42)
summary = engine.summary()
print(f"Mean return: {summary['mean_return']:.2%}")
print(f"5th percentile: {summary['p5_return']:.2%}")
print(f"Prob(loss): {summary['prob_loss']:.1%}")
```

分布式下 `monte_carlo` 按 `param_wise` 分片——1000 次模拟均分到 N 个 Worker，每个 Worker 独立运行一部分并使用不同 seed，最后合并统计量。

### 5.4 前向验证

前向验证（Walk-Forward）模拟"训练-测试"滚动窗口，评估策略的样本外稳定性：

```python
from stockstat_compute import WalkForward

wf = WalkForward(data, buy_and_hold,
                 train_window=252,   # 训练窗口（约 1 年日线）
                 test_window=63,     # 测试窗口（约 3 个月日线）
                 step=63,            # 滚动步长
                 initial_cash=10000)
df = wf.run()
print(df[["window", "total_return", "sharpe"]])
#    window  total_return  sharpe
# 0       1        0.052    0.42
# 1       2       -0.018   -0.15
# ...
```

---

## 6. 统计分析

8 个统计检验 handler（Tier 2），覆盖经典统计推断的常见场景。通过 `client.compute.*` 便捷方法或 `client.compute._submit_sync(task_type, **params)` 调用。

### 6.1 相关分析

计算两个序列的相关系数及置信区间。支持 Pearson（线性）、Spearman（秩）、Kendall（秩）三种方法：

```python
result = client.compute.correlation(x, y, method="pearson")
# {"method": "pearson", "r": 0.612, "p_value": 0.0001,
#  "n": 100, "ci_lower": 0.52, "ci_upper": 0.69}
```

置信区间基于 Fisher z 变换计算。`r` 接近 1 表示强正相关，接近 -1 表示强负相关，`p_value < 0.05` 表示统计显著。

![相关性散点图](../docs/images/stats_correlation.png)

### 6.2 假设检验

统一的假设检验接口，通过 `test` 参数选择检验类型：

```python
# 卡方独立性检验（2×2 列联表）
result = client.compute.hypothesis_test(
    data={"table": [[10, 20], [30, 40]]},
    test="chi2_independence",
)
# {"statistic": 1.33, "p_value": 0.248, "cramers_v": 0.058}

# 单样本 t 检验（检验均值是否等于 popmean）
result = client.compute.hypothesis_test(data=x, test="t_test", popmean=0)
```

### 6.3 Bootstrap 置信区间

通过重采样估计统计量的置信区间，不假设分布形式：

```python
result = client.compute._submit_sync("bootstrap", n_resamples=1000)
# {"estimate": 0.002, "ci_lower": -0.001, "ci_upper": 0.005, "se": 0.0015}
```

### 6.4 排列检验

非参数检验，通过随机打乱标签构建零分布：

```python
result = client.compute._submit_sync("permutation_test",
                                      x=group_a, y=group_b, n_permutations=1000)
# {"observed_stat": 0.5, "p_value": 0.032, "null_distribution": [...]}
```

### 6.5 Chow 检验

检验两个时间段是否存在结构断点：

```python
result = client.compute._submit_sync("chow_test",
    data={"x": x_series, "y": y_series, "split_point": 50})
# {"statistic": 4.21, "p_value": 0.007, "has_breakpoint": True}
```

### 6.6 生存分析

分析"时间到事件"数据，估计生存函数：

```python
result = client.compute._submit_sync("survival_analysis",
    data={"duration": durations, "event": events})
# {"survival_curve": {...}, "median_survival": 12.5}
```

### 6.7 经验累积分布函数（ECDF）

```python
result = client.compute._submit_sync("ecdf", data=sample)
# {"x": [...], "y": [...], "n": 100}
```

### 6.8 多重检验校正

对多个 p 值进行校正，控制族错误率或发现率：

```python
result = client.compute._submit_sync("multiple_testing",
    p_values=[0.001, 0.01, 0.04, 0.5],
    method="bh_fdr")  # Benjamini-Hochberg FDR
# DataFrame: index / p_value / adjusted_p / reject
```

支持 `bonferroni`（族错误率）和 `bh_fdr`（发现率）两种方法。

---

## 7. 信号处理

5 个信号处理 handler（Tier 3），覆盖频域和时频域分析。

### 7.1 频谱分析

估计信号的功率谱密度（PSD）。支持 Welch 法（分段平均）和周期图法：

```python
result = client.compute.spectral_analysis(signal, method="welch", nperseg=256)
# {"frequencies": [...], "psd": [...], "peak_freq": 10.0}
```

`peak_freq` 是 PSD 最大的频率分量，反映信号的主导周期。

![Welch 频谱](../docs/images/signal_spectral.png)

### 7.2 小波变换

连续小波变换（CWT），生成时频热力图。PyWavelets 未安装时自动 fallback 为自实现的 Morlet CWT：

```python
result = client.compute._submit_sync("wavelet",
    signal=signal, method="cwt",
    scales=list(range(1, 25)))
# {"coefficients": [...], "power": [...], "scales": [...]}
```

![小波时频热力图](../docs/images/signal_wavelet.png)

### 7.3 谱熵

衡量信号在频域的复杂度。值域 0~1，越高越复杂（接近白噪声），越低越规则（单一频率）：

```python
result = client.compute._submit_sync("spectral_entropy", signal=signal)
# {"spectral_entropy": 0.72}
```

### 7.4 交叉谱

分析两个信号的频域关系，包括相干性（coherence）和相位差（phase）：

```python
result = client.compute._submit_sync("cross_spectrum",
    data={"x": signal_a, "y": signal_b})
# {"coherence": [...], "phase": [...]}
```

### 7.5 滤波器设计

```python
result = client.compute._submit_sync("filter_design",
    data=signal, filter_type="lowpass", cutoff=0.1)
# {"filtered": [...], "coefficients": {...}}
```

---

## 8. 非线性动力学

7 个非线性 handler（Tier 4），用于分析时间序列的非线性特征。

### 8.1 传递熵

衡量两个时间序列之间的有向信息流。`te_forward`（X→Y）和 `te_backward`（Y→X）的差值 `net_te` 表示净信息传递方向：

```python
result = client.compute.transfer_entropy(x=btc_returns, y=eth_returns, k=1, l=1)
# {"te_forward": 0.045, "te_backward": 0.012, "net_te": 0.033,
#  "p_value": 0.03, "significant": True}
```

`significant=True` 表示传递熵在统计上显著（基于置换检验）。

### 8.2 Hurst 指数

衡量时间序列的长期记忆性。支持 DFA（去趋势波动分析）和 R/S 法：

```python
result = client.compute.hurst_exponent(data, method="dfa")
# {"hurst": 0.52, "fit_r2": 0.98}
```

解读：H ≈ 0.5 随机游走，H > 0.5 持久性（趋势延续），H < 0.5 反持久性（均值回复）。`fit_r2` 是双对数拟合的 R²。

![Hurst DFA 拟合](../docs/images/nonlinear_hurst.png)

### 8.3 互信息

衡量两个变量共享的信息量（非线性版本的相关性）：

```python
result = client.compute.mutual_information(x, y, estimator="binning")
# {"mutual_information": 0.35}
```

支持 `binning`（分箱）和 `knn`（k 近邻）两种估计器。

### 8.4 样本熵 / 排列熵

衡量序列的复杂度和规则性：

```python
# 样本熵 — 越高越复杂
sampen = client.compute.sample_entropy(signal, m=2)

# 排列熵 — 基于排列模式，越高越随机
permen = client.compute.permutation_entropy(signal, m=4, tau=1)
```

### 8.5 递归定量分析

递归图（Recurrence Plot）及其定量分析。递归图可视化相空间中轨迹的回归模式：

```python
# 递归图
result = client.compute._submit_sync("recurrence_plot", data=signal, m=3, tau=1)
# {"matrix": [[0,1,0,...], [1,0,1,...], ...]}

# 递归定量分析
result = client.compute._submit_sync("rqa", data=signal, m=3, tau=1)
# {"RR": 0.12, "DET": 0.85, "LAM": 0.78, "ENTR": 2.3}
```

- `RR`（递归率）：递归点占比。
- `DET`（确定性）：构成对角线的递归点占比，越高越确定性。
- `LAM`（层状度）：构成垂直线的递归点占比，反映状态停留。
- `ENTR`（熵）：对角线长度的 Shannon 熵。

![递归图](../docs/images/nonlinear_recurrence.png)

---

## 9. 灰色系统

3 个灰色系统 handler（Tier 5），适用于小样本、贫信息的预测与决策。

### 9.1 灰色关联分析

衡量参考序列与多个比较序列的关联程度，用于因素影响分析：

```python
result = client.compute._submit_sync("grey_relation",
    data={"reference": ref_series, "sequences": [seq1, seq2, seq3]},
    rho=0.5)  # 分辨系数，通常取 0.5
# {"relation_degrees": [0.85, 0.62, 0.43], "rank": [0, 1, 2]}
```

`rank` 按关联度降序排列，`relation_degrees[0]` 对应关联度最高的序列。

### 9.2 GM(1,1) 灰色预测

一阶单变量灰色模型，适用于短期、少数据预测：

```python
result = client.compute._submit_sync("gm11_predict", data=sequence, n_ahead=3)
# {"predicted": [10.2, 10.8, 11.5], "mape": 2.1}
```

`mape` 是平均绝对百分比误差，衡量拟合精度。

### 9.3 灰色聚类

```python
result = client.compute._submit_sync("grey_cluster",
    data={"samples": samples, "indicators": indicators},
    n_clusters=3)
# {"labels": [...], "whitening_weights": [...]}
```

---

## 10. 机器学习

7 个 ML handler（Tier 6），封装 scikit-learn 风格的训练与预测流程。需要安装 `pip install -e packages/compute[ml]`。

### 10.1 训练 + 预测

训练返回 `model_ref`（cloudpickle 编码的模型引用），预测时传入 `model_ref`：

```python
# 训练
result = client.compute._submit_sync("ml_train",
    data={"X": X_train, "y": y_train},
    model_type="random_forest")
model_ref = result["model_ref"]  # "cloudpickle:base64..."

# 预测
predictions = client.compute._submit_sync("ml_predict",
    data=X_test, model_ref=model_ref)
```

支持的 `model_type`：`random_forest` / `gradient_boosting` / `logistic` / `svm` / `xgboost`（需安装 xgboost）。

### 10.2 特征重要性

```python
result = client.compute._submit_sync("feature_importance",
    data={"X": X, "y": y}, model_ref=model_ref)
# {"importances": [0.3, 0.1, 0.25, ...], "feature_names": [...]}
```

### 10.3 聚类

无监督聚类，返回标签、质心和轮廓系数：

```python
result = client.compute._submit_sync("clustering",
    data=X, method="kmeans", n_clusters=3)
# {"labels": [...], "centroids": [...], "silhouette": 0.65}
```

支持 `kmeans` / `dbscan` / `hierarchical` 三种方法。`silhouette` 是轮廓系数（-1~1，越高越好）。

![K-Means 聚类](../docs/images/ml_clustering.png)

### 10.4 降维

```python
result = client.compute._submit_sync("dimension_reduction",
    data=X, method="pca", n_components=2)
# {"transformed": [...], "explained_variance": [0.7, 0.15]}
```

支持 `pca`（主成分分析）和 `tsne`（t-SNE 非线性降维）。`explained_variance` 是各主成分的方差解释比例。

![PCA 降维](../docs/images/ml_pca.png)

### 10.5 前向验证交叉验证

时序交叉验证，避免未来信息泄漏：

```python
result = client.compute._submit_sync("walkforward_cv",
    data={"X": X, "y": y}, n_folds=5)
# {"fold_scores": [0.72, 0.68, 0.75, 0.70, 0.73], "mean": 0.716, "std": 0.024}
```

### 10.6 分类评估指标

```python
result = client.compute._submit_sync("classification_metrics",
    data={"y_true": y_true, "y_pred": y_pred})
# {"accuracy": 0.85, "precision": 0.82, "recall": 0.78, "f1": 0.80,
#  "confusion_matrix": [[40, 5], [10, 45]]}
```

---

## 11. 组合风险管理

2 个组合风险 handler（Tier 7）。

### 11.1 风险度量

计算收益率序列的风险指标：

```python
result = client.compute._submit_sync("risk_metrics",
    data=returns, confidence=0.95)
# {"var": -0.03, "cvar": -0.045, "max_drawdown": -0.28,
#  "sharpe": 1.2, "sortino": 1.5, "calmar": 0.8}
```

- `VaR`（在险价值）：95% 置信下的最大日损。
- `CVaR`（条件在险价值）：超过 VaR 的平均损失。
- `max_drawdown`：最大回撤。
- `sharpe` / `sortino` / `calmar`：风险调整收益指标。

### 11.2 市场状态识别

识别价格序列中的不同市场状态（如牛市/熊市/震荡）：

```python
result = client.compute._submit_sync("regime_detection",
    data=prices, method="change_point", n_regimes=2)
# {"labels": [...], "regime_stats": {0: {"mean": 0.002, "vol": 0.01},
#                                    1: {"mean": -0.001, "vol": 0.02}}}
```

支持 `change_point`（变点检测）和 `hmm`（隐马尔可夫模型）两种方法。

---

## 12. DSL 策略表达式

DSL 引擎允许用简洁的表达式字符串调用常用策略，免去编写完整策略函数的样板代码：

```python
# 买入持有
result = client.run_dsl("buy_and_hold()", data=data)

# MA 交叉（指定参数）
result = client.run_dsl("ma_cross(short=5, long=20)", data=data)
```

DSL 解析器支持 `func_name(arg1, arg2, key=value)` 形式，参数支持数字、字符串、标识符和嵌套调用。`buy_and_hold` 和 `ma_cross` 是内置策略，未知函数名会尝试作为 indicator 调用：

```python
# 计算 RSI 指标
rsi = client.run_dsl("rsi(window=14)", data=data)
```

---

## 13. 可视化

V3.1 提供声明式图表和便捷绘图函数两种可视化方式。

### 13.1 声明式图表（ChartSpec + MatplotlibRenderer）

```python
from stockstat import ChartSpec, MatplotlibRenderer

# 构建图表规格
spec = ChartSpec(
    title="BTC Price",
    chart_type="line",
    data=data[["close"]],
)

# 渲染为 PNG bytes
png_bytes = MatplotlibRenderer().render(spec)

# 保存到文件
with open("chart.png", "wb") as f:
    f.write(png_bytes)
```

未安装 matplotlib 时，`NullRenderer` 提供空实现，不报错但不生成图像。

### 13.2 回测图表

```python
from stockstat.plot import plot_equity_curve, plot_drawdown

# 资金曲线
equity_png = plot_equity_curve(result.equity_curve)

# 回撤图
drawdown_png = plot_drawdown(result.equity_curve)
```

---

## 14. 结果导出

`ResultSerializer` 支持多种格式导出，适合把结果写入文件或与其他系统集成：

```python
from stockstat import ResultSerializer

# JSON（适合 Web 交互）
json_str = ResultSerializer.to_json(result.metrics.to_dict())

# CSV（适合表格分析）
csv_str = ResultSerializer.to_csv(df)

# Arrow（列式二进制，适合大数据）
arrow_bytes = ResultSerializer.to_arrow(df)

# Parquet（文件级列式存储）
parquet_bytes = ResultSerializer.to_parquet(df)

# 保存到文件（自动按扩展名推断格式）
ResultSerializer.save(df, "output.csv", format="csv")
ResultSerializer.save(df, "output.arrow", format="arrow")
ResultSerializer.save(df, "output.parquet", format="parquet")
```

---

## 15. CLI 命令行

V3.1 提供三组 CLI，分别对应用户入口、存储端和计算端。

### 15.1 stockstat（用户入口）

```bash
# 数据管理
stockstat data fetch BTC/USDT --timeframe 1d [--start 2024-01-01] [--limit 20]
stockstat data list
stockstat data ingest --symbol BTC/USDT --source binance

# 计算指标
stockstat compute indicator ma --symbol BTC/USDT --window 20
stockstat compute list-handlers    # 列出 38 个 task_type

# 任务管理
stockstat task status <task_id>

# 集群
stockstat cluster info

# 配置
stockstat config       # 显示当前配置
stockstat version      # 显示版本

# 服务（便捷入口，等价 stockstat-backend serve）
stockstat serve --host 0.0.0.0 --port 8000
```

### 15.2 stockstat-backend（存储端）

```bash
stockstat-backend serve --host 0.0.0.0 --port 8000 [--database-url ...] [--admin]
stockstat-backend init-db [--database-url ...]
stockstat-backend ingest --symbol BTC/USDT --source binance [--timeframe 1d]
stockstat-backend list-symbols [--database-url ...]
```

### 15.3 stockstat-dispatcher（分发端）

```bash
stockstat-dispatcher serve \
    --storage-url http://localhost:8000 \
    --listen 0.0.0.0:9000 \
    [--queue-backend memory|redis] \
    [--redis-url redis://localhost:6379] \
    [--alias dispatch-primary]

stockstat-dispatcher cluster --dispatcher-url http://localhost:9000
```

### 15.4 stockstat-compute（计算端）

```bash
# 启动 Worker
stockstat-compute worker \
    --dispatcher-url http://localhost:9000 \
    --concurrency 8 \
    --alias compute-node-1 \
    --label gpu=true \
    --capabilities backtest,grid_search \
    --preemptable

# 列出所有 handler
stockstat-compute list-handlers

# 显示硬件信息
stockstat-compute hardware
```

`--label key=value` 可多次指定，用于 Worker 标签过滤。`--capabilities` 逗号分隔，限定 Worker 支持的 task_type（不指定则支持全部 38 种）。

---

## 16. 分布式计算

### 16.1 三种 ComputeBackend

| 后端 | 类名 | 场景 | 行为 |
|------|------|------|------|
| 本地 | `LocalComputeBackend` | 单机（场景 A/B/C） | 后台线程执行，`wait()` 阻塞等待 |
| 远程 | `RemoteComputeBackend` | 分布式（场景 D/E/F） | HTTP 提交到 Dispatcher，`TaskRef.wait()` 轮询 |
| 自动 | `AutoComputeBackend` | 混合 | 重型任务→远程，轻型→本地，远程不可达降级本地 |

切换后端只需修改 Client 构造参数，调用代码完全一致。

### 16.2 显式异步提交

```python
from stockstat_foundation import ComputeSpec, DataSpec, DispatchSpec

task = client.compute.remote("grid_search", data=data,
    compute_spec=ComputeSpec(
        task_type="grid_search",
        param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
        metric="sharpe",
    ))
print(task.id, task.status)  # UUID + "pending"

# 轮询状态
info = task.info
print(info.progress)  # 0.0 ~ 1.0

# 阻塞等待结果
result = task.wait(timeout=3600)
```

`remote()` 返回 `TaskRef`，提供 `id` / `status` / `info` / `ready()` / `wait()` / `result()` / `cancel()` / `stream_results()` 方法。

### 16.3 本地/远程透明切换

同一套 API，单机与分布式行为一致：

```python
# 本地
client_local = StockStatClient()
result_local = client_local.backtest(data, strategy)

# 远程（同一 API，只改构造参数）
from stockstat_compute.backend.remote import RemoteComputeBackend
client_remote = StockStatClient(
    compute_backend=RemoteComputeBackend("http://dispatcher:9000"),
)
result_remote = client_remote.backtest(data, strategy)

# 结果一致（精度 1e-10）
```

### 16.4 AutoComputeBackend 路由规则

```python
from stockstat_compute.backend.auto import AutoComputeBackend
from stockstat_compute import LocalComputeBackend
from stockstat_compute.backend.remote import RemoteComputeBackend

auto = AutoComputeBackend(
    local=LocalComputeBackend(client=client, data_client=data_client),
    remote=RemoteComputeBackend(dispatcher_url="http://dispatcher:9000"),
)

client = StockStatClient(compute_backend=auto)
# grid_search → 远程（HEAVY_TYPES）
# indicator(ma) → 本地（轻型）
```

`HEAVY_TYPES` = `{grid_search, batch_backtest, monte_carlo, bootstrap, permutation_test, walkforward, walkforward_cv, ml_train, deep_learning}`。此外，内联数据超过 `local_threshold_mb`（默认 1MB）也走远程。

---

## 17. 部署场景

### 场景 A：单机全栈

最简单的部署——所有计算在进程内完成，无需启动任何服务：

```python
client = StockStatClient()  # 默认 LocalComputeBackend
result = client.backtest(data, strategy)
```

### 场景 B：存储分离

Storage 独立部署，Client 本地计算。适合团队共享数据：

```bash
# Storage 服务
stockstat-backend serve --host 0.0.0.0 --port 8000
```

```python
client = StockStatClient(storage_url="http://storage-host:8000")
data = client.ohlcv("BTC/USDT", "1d")
result = client.backtest(data, strategy)  # 本地计算
```

### 场景 C：离线

无网络环境，数据本地入库，本地计算：

```bash
stockstat-backend ingest --symbol BTC/USDT --source synthetic
```

```python
client = StockStatClient(storage_url="http://localhost:8000")
```

### 场景 D：Dispatcher + Worker

Storage 与 Dispatcher 同机，Worker 远程。适合小型集群：

```bash
# Terminal 1: Storage + Dispatcher
stockstat-backend serve --port 8000
stockstat-dispatcher serve --storage-url http://localhost:8000 --listen 0.0.0.0:9000

# Terminal 2: Worker
stockstat-compute worker --dispatcher-url http://localhost:9000 --concurrency 8
```

### 场景 E：独立 Dispatcher 集群

Storage、Dispatcher、Worker 各自独立部署。适合生产集群：

```bash
# Storage
stockstat-backend serve --port 8000

# Dispatcher（独立）
stockstat-dispatcher serve --listen 0.0.0.0:9000

# Worker ×N（可部署到多台机器）
stockstat-compute worker --dispatcher-url http://dispatcher:9000 --concurrency 8
```

### 场景 F：多级 Dispatcher

主 Dispatcher + 子 Dispatcher，形成树状调度。适合大规模集群：

```bash
# 主 Dispatcher
stockstat-dispatcher serve --listen 0.0.0.0:9000 --alias dispatch-primary

# 子 Dispatcher（向父注册）
stockstat-dispatcher serve --listen 0.0.0.0:9001 \
    --alias dispatch-child-1 --parent-url http://primary:9000

# Worker（连接子 Dispatcher）
stockstat-compute worker --dispatcher-url http://child-1:9001
```

---

## 18. PostgreSQL 配置

生产环境推荐使用 PostgreSQL。V3.1 通过 SQLAlchemy ORM 抽象数据库，切换只需修改连接 URL：

```bash
# 环境变量
export STOCKSTAT_DATABASE_URL=postgresql://stockstat:stockstat123@192.168.0.114:5432/stockstat

# 启动
stockstat-backend serve --host 0.0.0.0 --port 8000
```

验证连接：

```python
from stockstat_backend import OrmSession, StorageBackendImpl, create_engine_from_url

engine = create_engine_from_url("postgresql://stockstat:stockstat123@192.168.0.114:5432/stockstat")
orm = OrmSession(engine)
orm.create_all()  # 创建表（首次）
backend = StorageBackendImpl(orm)

# 写入
backend.ingest_ohlcv("BTC/USDT", "1d", df)

# 查询
result = backend.fetch_ohlcv(["BTC/USDT"], "1d")
```

需要安装 PostgreSQL 驱动：`pip install -e packages/storage[postgres]`。

---

## 19. REST API 参考

### 19.1 Storage REST API

| 端点 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/api/v1/ohlcv` | GET | `symbol`（逗号分隔多标的）/ `timeframe` / `start` / `end` / `source` / `format`（arrow/json） | 查询 OHLCV，默认返回 Arrow IPC 二进制 |
| `/api/v1/ohlcv` | POST | Header: `X-Symbol` / `X-Timeframe`；Body: Arrow IPC 或 JSON | 写入 OHLCV |
| `/api/v1/ohlcv/stats` | GET | — | OHLCV 数据统计 |
| `/api/v1/symbols` | GET | — | 标的列表 |
| `/api/v1/ingest` | POST | `symbol` / `timeframe` / `source` | 从数据源采集 |
| `/health` | GET | — | 健康检查 |

示例（curl）：

```bash
# 查询 OHLCV（Arrow 格式）
curl "http://localhost:8000/api/v1/ohlcv?symbol=BTC/USDT&timeframe=1d&format=json"

# 写入 OHLCV（JSON）
curl -X POST http://localhost:8000/api/v1/ohlcv \
    -H "Content-Type: application/json" \
    -H "X-Symbol: BTC/USDT" \
    -H "X-Timeframe: 1d" \
    -d '[{"timestamp":"2024-01-01","open":42000,"high":42500,"low":41800,"close":42300,"volume":1500}]'
```

### 19.2 Dispatcher REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/dispatch/submit` | POST | 提交任务（Body: TaskSpec JSON） |
| `/dispatch/status/{task_id}` | GET | 查询任务状态 |
| `/dispatch/result/{task_id}` | GET | 获取结果（base64 cloudpickle） |
| `/dispatch/cancel/{task_id}` | POST | 取消任务 |
| `/dispatch/cluster` | GET | 集群拓扑（`?include_offline=true&include_hardware=true`） |
| `/dispatch/autoscaler` | GET | Autoscaler 指标 |
| `/dispatch/tasks/history` | GET | 任务历史（`?limit=100&state=completed`） |
| `/dispatch/register` | POST | Worker 注册 |
| `/dispatch/heartbeat` | POST | Worker 心跳 |
| `/dispatch/unregister/{worker_id}` | POST | Worker 注销 |
| `/dispatch/assign` | POST | Worker 拉取任务 |
| `/dispatch/complete` | POST | Worker 回传结果 |
| `/dispatch/fail` | POST | Worker 回传失败 |
| `/dispatch/partial` | POST | Worker 流式部分结果 |

示例（Python httpx）：

```python
import httpx, json
from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec, DispatchSpec

# 提交任务
spec = TaskSpec(
    task_id="task-001",
    data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
    compute_spec=ComputeSpec(task_type="backtest", initial_cash=10000),
    dispatch_spec=DispatchSpec(timeout=3600),
)
resp = httpx.post("http://localhost:9000/dispatch/submit",
                   json=spec.to_dict())
print(resp.json())  # {"task_id": "task-001", "status": "pending", "n_slices": 1}

# 查询状态
resp = httpx.get("http://localhost:9000/dispatch/status/task-001")
print(resp.json())  # {"state": "completed", "progress": 1.0, ...}

# 获取结果
import base64
from stockstat_foundation import CloudpickleCodec
resp = httpx.get("http://localhost:9000/dispatch/result/task-001")
result_bytes = base64.b64decode(resp.json()["result"])
result = CloudpickleCodec().decode(result_bytes)
```

---

## 20. 环境变量参考

V3.1 通过 `Config` 类统一管理配置，共 18 个环境变量。所有变量以 `STOCKSTAT_` 前缀开头，可通过 `stockstat config` 命令查看当前生效值：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKSTAT_CLIENT_MODE` | `online` | 客户端模式 |
| `STOCKSTAT_DEFAULT_BACKEND` | `local` | 默认计算后端（local/remote/auto） |
| `STOCKSTAT_STORAGE_URL` | — | Storage 服务地址 |
| `STOCKSTAT_DATABASE_URL` | `sqlite:///stockstat.db` | 数据库连接 URL |
| `STOCKSTAT_DISPATCHER_URL` | — | Dispatcher 服务地址 |
| `STOCKSTAT_DISPATCHER_ENABLED` | `false` | 是否启用 Dispatcher |
| `STOCKSTAT_DISPATCHER_QUEUE` | `memory` | 队列后端（memory/redis） |
| `STOCKSTAT_DISPATCHER_CACHE_DIR` | — | Dispatcher 数据缓存目录 |
| `STOCKSTAT_DISPATCHER_CACHE_SIZE_MB` | `512` | Dispatcher 数据缓存上限（MB） |
| `STOCKSTAT_REDIS_URL` | — | Redis 连接 URL |
| `STOCKSTAT_ADMIN_ENABLED` | `false` | 是否启用 Admin 面板 |
| `STOCKSTAT_SCHEDULER_ENABLED` | `false` | 是否启用定时采集 |
| `STOCKSTAT_WORKER_CONCURRENCY` | CPU 核数 | Worker 并发数 |
| `STOCKSTAT_WORKER_ALIAS` | hostname-pid | Worker 别名 |
| `STOCKSTAT_WORKER_PREEMPTABLE` | `false` | Worker 是否支持抢占 |
| `STOCKSTAT_TRANSPORT_TIMEOUT` | `30` | 传输超时（秒） |
| `STOCKSTAT_PROTOCOL_VERSION` | `1.0` | 协议版本 |
| `STOCKSTAT_DEFAULT_ENCODING` | `json` | 默认编码（json/msgpack） |

也可通过 JSON / TOML 配置文件加载：`Config.from_file("config.json")`。

---

*V3.1 使用文档以代码实现为准。如有不一致，请以源码为准。*
