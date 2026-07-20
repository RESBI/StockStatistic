# StockStat V3.1 Invocation 架构设计

> 大模块：Invocation（Python SDK、CLI、DSL 与管理入口）
> 版本：V3.1 设计稿
> 关联：[DESIGN_ARCH_V31.md](DESIGN_ARCH_V31.md)、[DESIGN_PROT_V31.md](DESIGN_PROT_V31.md)

## 1. 模块定位

Invocation 向金融研究用户提供统一调用入口，把用户意图编译为类型化 JobSpec，并通过 Local 或 Remote Session 执行。它包含 Python SDK、CLI、可选 DSL 编译器和 Admin 查询入口，但不包含金融算法实现和服务端状态。

V3.1 不保留 `StockStatClient` 与 `V2Client` 两套客户端，也不要求用户注入 `ComputeBackend`。统一入口为 `StockStat`/`Session`。

## 2. 设计目标

- 同一用户代码可选择本地组合部署或远程服务。
- 同步便捷调用和异步 JobHandle 共用同一提交路径。
- 数据表、快照、策略包和结果有明确类型。
- 当前所有旧客户代码都有明确迁移写法。
- SDK 不暴露 Dispatcher/Transport 实现细节。
- SDK 不通过 `isinstance(LocalBackend)` 分叉业务行为。

## 3. 包结构

建议包名继续使用 `stockstat`，但内容完全重构：

```text
packages/sdk/
└── stockstat/
    ├── __init__.py
    ├── facade.py
    ├── session.py
    ├── jobs.py
    ├── results.py
    ├── tables.py
    ├── strategy.py
    ├── api/
    │   ├── market.py
    │   ├── features.py
    │   ├── statistics.py
    │   ├── backtests.py
    │   ├── experiments.py
    │   ├── simulations.py
    │   ├── validation.py
    │   ├── render.py
    │   └── cluster.py
    ├── transports/
    │   ├── http.py
    │   └── inprocess.py
    ├── dsl/
    │   ├── parser.py
    │   └── compiler.py
    ├── migrate/
    │   ├── scanner.py
    │   └── report.py
    └── cli.py
```

## 4. 统一 Session

### 4.1 创建方式

```python
from stockstat import StockStat

# 本地一体化：本地 Storage + Dispatcher + Worker
session = StockStat.local("./runtime")

# 远程：Dispatcher 和 Storage 可分别部署
session = StockStat.connect(
    dispatcher_url="https://dispatch.example.com",
    storage_url="https://storage.example.com",
    token="...",
)
```

本地与远程 Session 都实现相同内部接口：

```python
class SessionProtocol(Protocol):
    jobs: JobService
    storage: StorageService
```

### 4.2 资源 API

```python
session.market
session.features
session.statistics
session.backtests
session.experiments
session.simulations
session.validation
session.render
session.cluster
```

这些是金融领域 API，不是服务端对象的直接代理。

## 5. 数据使用

### 5.1 采集与查询

```python
session.market.ingest(
    "crypto:binance:PAXG/USDT",
    timeframe="1h",
    start="2020-08-28",
    end="2026-07-16",
).wait()

snapshot = session.market.snapshot(
    instruments=["crypto:binance:PAXG/USDT"],
    timeframes=["1d", "1h"],
    start="2020-08-28",
    end="2026-07-16",
)
```

### 5.2 小数据本地读取

```python
table = snapshot.read(
    instrument="crypto:binance:PAXG/USDT",
    timeframe="1d",
)
```

`table` 是 `MarketTable` 包装，可通过 `.to_pandas()` 显式转换。避免所有 API 默认返回 pandas，从而保留 Arrow/schema 边界。

### 5.3 临时内联数据

用户已有 DataFrame 时：

```python
market = session.market.from_pandas(
    df,
    instrument="crypto:binance:PAXG/USDT",
    timeframe="1d",
)
```

SDK 在本地或远程 Storage 中提交为临时 Artifact/Snapshot，再构造 Job。大 DataFrame 不直接塞进 Job JSON。

## 6. 指标与统计 API

### 6.1 本地即时与 Job 统一

```python
job = session.features.indicators(
    snapshot,
    specs=[
        {"id": "trend.ma", "input": "close", "params": {"window": 20}, "output": "ma20"},
        {"id": "oscillator.rsi", "input": "close", "params": {"window": 14}, "output": "rsi14"},
    ],
)

features = job.wait().as_table()
```

便捷同步方法只是在内部立即 `wait`：

```python
features = session.features.indicators_sync(snapshot, specs=[...])
```

不会像 V3 一样本地路径直接调用、远程路径构造 TaskSpec，导致两套语义。

### 6.2 统计研究

```python
tests = session.statistics.hypothesis(
    feature_table,
    tests=[
        {"method": "pearson", "x": "x4_range", "y": "monday_range"},
        {"method": "chi_square", "x": "signal_sign", "y": "path_up_first"},
    ],
).wait().as_table()
```

排列、自助、多重校正、survival、回归分别有独立 API，避免一个万能 `statistics.run(method, **kwargs)`。

## 7. 策略 API

### 7.1 本地模块策略

```python
strategy = session.strategies.from_module(
    "strategies:WeekendRangeStrategy",
    source_root="./research",
    config={"k": 0.8},
)
```

SDK 构建 StrategyBundle 并返回 `StrategyRef`。

### 7.2 内置策略/组件

```python
strategy = session.strategies.ref("builtin.ma_cross@1", short=5, long=20)
```

### 7.3 禁止默认闭包序列化

旧 `@strategy` 函数可以通过迁移工具生成模块文件或显式 trusted-local 包装。远程生产模式不默认 cloudpickle 任意闭包。

## 8. 回测 API

```python
from stockstat_contracts import BacktestParameters, ComponentRef

job = session.backtests.run(
    snapshot,
    strategy=strategy,
    parameters=BacktestParameters(
        initial_cash=10_000,
        allow_short=True,
        periods_per_year=52,
        cost_model=ComponentRef(
            id="cost.binance@1",
            params={"venue": "futures", "bnb_discount": True},
        ),
        execution_policy=ComponentRef(
            id="execution.intrabar@1",
            params={"parent_tf": "1d", "intrabar_tf": "1h"},
        ),
    ),
)

result = job.wait(timeout=600).as_backtest()
print(result.metrics)
equity = result.equity.to_pandas()
```

### 8.1 跨 session 和时间退出

V3.1 参数和策略上下文可以直接表达：

- Friday close 入场，Monday open/close 退出。
- 持仓跨 Monday-Wednesday。
- fill 后六小时退出。
- 第一小时结束后再决策。

这消除 PAXG v5-v31 仍有 7 个策略无法原生迁移的问题。

## 9. 实验 API

### 9.1 Batch

```python
runs = [
    {"run_id": "S1:F1", "strategy": s1, "parameters": p1},
    {"run_id": "S1:F2", "strategy": s1, "parameters": p2},
]
job = session.experiments.batch(snapshot, runs=runs, batch_size=16)
table = job.wait().as_table()
```

### 9.2 Grid Search

```python
job = session.experiments.grid_search(
    snapshot,
    base_backtest=base,
    parameter_space={"short": [3, 5, 8], "long": [10, 20, 30]},
    objective={"metric": "sharpe", "direction": "maximize"},
)
```

### 9.3 Monte Carlo 和 Walk-forward

```python
session.simulations.bootstrap(
    snapshot, base_backtest=base, n_samples=10_000, shards=32, random_seed=42
)

session.validation.walk_forward(
    snapshot, base_backtest=base, windows=windows
)
```

PAXG v7 的受控样本外预测验证通过 `session.validation.predictive(...)` 提交，模型只能引用服务端注册的 method ID 和类型化参数，不接受任意 estimator 或 pickle 模型。

## 10. JobHandle

```python
job.id
job.status()
job.wait(timeout=...)
job.cancel()
job.events()
job.partials()
job.result()
```

### 10.1 事件消费

```python
for event in job.events():
    print(event.sequence, event.type, event.progress)
```

远程使用 SSE，本地使用同一 event stream 接口。

### 10.2 结果视图

`JobResult` 按 manifest kind 提供：

- `.as_table()`
- `.as_backtest()`
- `.as_experiment()`
- `.as_simulation()`
- `.artifacts`
- `.lineage()`

未匹配 kind 时拒绝转换，不返回任意 Python 对象。

## 11. DSL 定位

DSL 保留为轻量前端，但不成为内核或协议：

```sql
SELECT close,
       ma(close, 20) AS ma20,
       rsi(close, 14) AS rsi14
FROM market("crypto:binance:BTC/USDT", "1d")
WHERE ts >= "2024-01-01"
```

流程：

```text
DSL text -> AST -> typed query/feature plan -> JobSpec
```

DSL 只支持公开金融 operation，不能执行 Python、shell 或任意 SQL。

## 12. CLI

```bash
stockstat market ingest crypto:binance:PAXG/USDT --tf 1h --start 2020-08-28
stockstat market snapshot --instrument crypto:binance:PAXG/USDT --tf 1d --tf 1h
stockstat job submit job.json
stockstat job status <job-id>
stockstat job watch <job-id>
stockstat job cancel <job-id>
stockstat result download <job-id> --member metrics
stockstat cluster workers
stockstat cluster capabilities
stockstat migrate scan ./research
```

CLI 使用 SDK，不单独实现协议。

## 13. Admin 与可视化

### 13.1 Admin API/UI

管理界面读取 Dispatcher 和 Storage 的公开管理资源：

- Job 列表、状态、耗时、失败。
- Worker、capability、slot 和缓存。
- Snapshot、Artifact、存储空间和 lineage。
- 采集覆盖和数据质量。

UI 不直接持有 Dispatcher 内部对象引用。

### 13.2 图表

```python
chart = session.render.chart(
    result,
    profile="backtest.dashboard@1",
    format="png",
).wait()
```

小结果也可以本地 renderer 渲染。ChartSpec 本身是 Artifact，可在 Web/TUI 复用。

## 14. 旧客户代码迁移

### 14.1 迁移原则

- 不保证原 import 路径继续运行。
- 保证每个公共功能有新 API。
- 提供 scanner、映射文档和结果 parity tests。
- 迁移一次后不依赖兼容包。

### 14.2 典型映射

| 旧代码 | V3.1 |
|---|---|
| `StockStatClient(host, port)` | `StockStat.connect(dispatcher_url, storage_url)` |
| `V2Client(mode="offline")` | `StockStat.local(runtime_dir)` |
| `client.ingest(...)` | `session.market.ingest(...).wait()` |
| `client.ohlcv(...)` | `snapshot.read(...).to_pandas()` |
| `client.compute.ma(series, 20)` | 本地 kernel `ma` 或 `session.features.indicators(...)` |
| `client.run_dsl(text)` | `session.query.run(text)` |
| `client.backtest(data, strategy)` | `session.backtests.run(...).wait()` |
| `client.compute.remote(...)` | 所有 API 默认返回 JobHandle |
| `task.wait()` | `job.wait()` |
| `task.stream_results()` | `job.events()` / `job.partials()` |
| `client.compute.cluster_info()` | `session.cluster.info()` |

### 14.3 自动扫描

`stockstat migrate scan` 检测：

- 旧 import。
- `StockStatClient`/`V2Client`。
- `ComputeBackend`。
- `client.compute.remote`。
- cloudpickle strategy_ref。
- `BacktestEngine` 直接构造。
- `StrategyBatchRunner`、`grid_search`、`walk_forward`。

输出 CSV/Markdown 报告和建议，不自动修改复杂策略逻辑。

## 15. 配置

统一 TOML：

```toml
[profile.local]
mode = "local"
runtime_dir = "./.stockstat"

[profile.lab]
mode = "remote"
dispatcher_url = "http://dispatch:9000"
storage_url = "http://storage:8000"
token_env = "STOCKSTAT_TOKEN"
```

运行时通过 `StockStat.from_profile("lab")` 选择。配置不把 transport 类型暴露给金融 API。

## 16. 测试要求

### 16.1 SDK 契约

- local/remote Session 同一 JobSpec golden。
- sync helper 等于 submit + wait。
- DataFrame 临时上传和 Snapshot 引用。
- JobHandle 状态、取消、SSE 恢复。
- 结果 kind 安全转换。

### 16.2 迁移

- README/USAGE 中每个旧功能有新示例。
- 代表性旧脚本手工迁移。
- PAXG v1-v7 原生 V3.1 工作目录不 import 旧包。
- scanner 对旧 API 发现率有 fixture。

### 16.3 CLI/DSL

- CLI 使用 fake Session 的单元测试。
- DSL AST 到 JobSpec golden。
- 禁止任意 SQL/Python 注入。

## 17. 结论

Invocation 通过一个 Session、一组金融领域 API 和统一 JobHandle 消除 V2/V3 的双客户端、双本地/远程路径和任意 TaskSpec 构造。旧客户代码需要迁移，但所有功能都有清晰目标，并能在本地与远程部署之间不改业务代码地切换。
