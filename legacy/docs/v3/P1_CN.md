# V3 阶段文档 P1 — 本地计算后端 + 单进程传输

> **阶段**：P1（LocalComputeBackend + InProcessTransport）
> **日期**：2026-07-19
> **状态**：✅ 已完成
> **关联**：[DESIGN_V3_CN.md §4 v1.7 与 v2 接口统一接入](../../DESIGN_V3_CN.md#4-v17-与-v2-接口的统一接入)、[§8.1 LocalComputeBackend](../../DESIGN_V3_CN.md#81-localcomputebackend默认零行为变更)

---

## 1. 目标

实现 V3 兼容层核心：`LocalComputeBackend` + `InProcessTransport`，让 v1.7 `StockStatClient` 与 v2 `V2Client` 可透明使用 `compute_backend` 参数。

**核心验收**：
- 默认 `compute_backend=None` → `LocalComputeBackend` → 行为完全等同 v2.1
- `client.compute.remote("backtest", ...)` 返回 `TaskRef`，`task.wait()` 返回 `BacktestResult`
- 远程（InProcess）模式与直接调用 `BacktestEngine` 结果数值一致

---

## 2. 新增模块

### 2.1 `frontend/stockstat/_core/transport/in_process.py`

`InProcessTransport` 实现 `Transport` Protocol：

- 基于 `queue.Queue` 的进程内消息传递，零序列化开销
- `send()` / `receive()`：fire-and-forget 模式
- `request()` / `reply()`：请求-响应模式，按 `reply_to` 匹配
- `send_data()` / `fetch_data()`：内联 base64 数据引用
- `make_pair()`：创建双向通信的传输对（用于测试）
- `encode_envelopes=True` 选项：强制走 Envelope.encode/decode 往返，验证编解码路径

### 2.2 `frontend/stockstat/_core/compute/local.py`

`LocalComputeBackend` 实现 `ComputeBackend` Protocol：

- **`submit(spec)`**：在后台 daemon 线程执行，立即返回 `TaskRef`
- **`get(task_id)`**：返回 `TaskInfo` 状态快照
- **`result(task_id)`**：非阻塞；未完成抛 `TaskNotReadyError`
- **`wait(task_id, timeout)`**：阻塞等待；失败抛 `TaskError`
- **`cancel(task_id)`**：标记 CANCELLED；后台线程检测 `cancel_requested` 后中止
- **`cluster_info()`**：返回单 worker in-process 拓扑
- **`stream_results(task_id)`**：yield partials + final
- **`publish_partial(task_id, partial)`**：handler 用此发布中间结果

核心调度入口 `_dispatch_to_handler(spec, ...)`：按 `task_type` 路由到对应处理器：

| task_type | 处理函数 | 复用的 stockstat 核心 |
|-----------|---------|---------------------|
| `indicator` | `_handle_indicator` | `ComputeEngine.<method>()` |
| `backtest` | `_handle_backtest` | `BacktestEngine(...).run()` |
| `grid_search` | `_handle_grid_search` | `BacktestEngine` + 串行循环 + `publish_partial` 进度 |
| `batch_backtest` | `_handle_batch_backtest` | `StrategyBatchRunner.run_all_fees()` |
| `monte_carlo` | `_handle_monte_carlo` | `BacktestEngine` + `monte_carlo_equity()` |
| `custom` | `_handle_custom` | 返回 params 确认（支持 `_sleep_seconds` 测试） |

辅助函数：
- `_resolve_data(spec, client/data_client/storage)` — 从 spec.data_spec 拉 OHLCV
- `_deserialize_strategy(strategy_ref, codec)` — 解码 cloudpickle/json 策略
- `_resolve_cost_model(name)` / `_resolve_fill_model(name)` / `_resolve_execution_model(name)` — 按注册名解析组件

### 2.3 `StockStatClient` / `V2Client` 改造

**`StockStatClient.__init__`** 新增可选参数：

```python
def __init__(self, ..., compute_backend: Optional[Any] = None):
    self._compute_backend = compute_backend  # None → lazily LocalComputeBackend
```

**`StockStatClient.backtest(data, strategy, **kwargs)`**：

```python
async_submit = kwargs.pop("async_submit", False)
if self._compute_backend is not None and not _is_local_backend(self._compute_backend):
    # 远程路径：构建 TaskSpec 提交
    spec = _build_backtest_task_spec(data, strategy, kwargs)
    task_ref = self._compute_backend.submit(spec)
    if async_submit:
        return task_ref
    return task_ref.wait(timeout=kwargs.get("timeout", 3600))
# 默认路径：完全保留 v2.1 行为（直接 BacktestEngine）
from .backtest import BacktestEngine
kwargs.setdefault("compute_engine", self._compute)
return BacktestEngine(data=data, strategy=strategy, **kwargs).run()
```

**关键不变量**：
- `compute_backend=None`（默认）→ 走 v2.1 原路径，已有 277 项回测测试零修改通过
- `compute_backend=LocalComputeBackend()`（显式本地）→ 也走原路径（_is_local_backend 判定）
- `compute_backend=RemoteComputeBackend(...)` → 走 TaskSpec 提交路径

**`V2Client.__init__`** 同样新增 `compute_backend` 参数；`V2Client.backtest()` 同样优先走原路径。

### 2.4 `ComputeEngine.remote()` / `cluster_info()`

在 `compute/engine.py` 的 `ComputeEngine` 类上直接新增 V3 入口方法（不破坏现有 40+ 指标方法）：

- **`remote(task_type, *, data_spec=None, compute_spec=None, dispatch_spec=None, **kwargs)`** — 构建 `TaskSpec` 提交到 `client.compute_backend`，返回 `TaskRef`
- **`cluster_info(**kwargs)`** — 查询集群拓扑
- **`_get_compute_backend()`** — 从绑定的 client 解析 ComputeBackend

`remote()` 智能识别已知 ComputeSpec 字段（`strategy_ref` / `initial_cash` / `param_grid` 等），从 kwargs 中提取并填入 `ComputeSpec`；未知字段进入 `params`。

### 2.5 `_build_backtest_task_spec()` 辅助函数

`client.py` 新增辅助函数，将 `(data, strategy, kwargs)` 三元组转换为 `TaskSpec`：

- 用 `CloudpickleCodec` 编码 strategy → `strategy_ref="cloudpickle:base64..."`
- 从 data dict 提取 symbols + timeframe 填入 `DataSpec`
- 映射 `initial_cash` / `cost_model` / `fill_model` / `benchmark` 等 kwargs 到 `ComputeSpec`

---

## 3. 兼容性保证

### 3.1 三种调用方式行为一致

| 调用方式 | 路径 | 行为 |
|---------|------|------|
| `client.backtest(data, strategy)` | 默认（LocalComputeBackend 隐式） | 完全等同 v2.1：直接 BacktestEngine |
| `client.backtest(data, strategy, compute_backend=LocalComputeBackend())` | 显式本地 | 同上（_is_local_backend 短路） |
| `client.backtest(data, strategy, async_submit=True)` | 本地异步 | submit + wait；返回 BacktestResult |
| `client.compute.remote("backtest", ...)` | 显式异步 | 返回 TaskRef；wait() 返回 BacktestResult |

### 3.2 V2Client 离线模式

- `V2Client(mode="offline")` 默认 `LocalComputeBackend(client=self, storage=storage)`
- `V2Client(mode="offline").backtest()` 走原路径（直接 BacktestEngine）
- `V2Client(mode="offline").compute_backend.cluster_info()` 返回单 worker 拓扑

### 3.3 数值一致性测试

`test_backtest_local_equals_direct` 验证：

```python
# 直接调用 BacktestEngine
direct = BacktestEngine(data, strategy, initial_cash=10000).run()

# 通过 LocalComputeBackend
backend = LocalComputeBackend()
spec = TaskSpec(..., compute_spec=ComputeSpec(task_type="backtest", ...))
via_backend = backend.submit(spec).wait()

# 数值完全一致
np.testing.assert_array_almost_equal(
    via_backend.equity.values, direct.equity.values, decimal=6,
)
```

---

## 4. 测试覆盖

测试文件：`frontend/tests/test_v3_compute_backend.py`（35 项）

| 测试类 | 测试数 | 覆盖范围 |
|--------|--------|---------|
| `TestLocalComputeBackend` | 10 | backend name / cluster_info / submit 返回 TaskRef / custom task 完成 / 未知 task_type 失败 / 状态转换 / result() 未就绪抛错 / cancel pending / stream_results / 未知 task_id |
| `TestInProcessTransport` | 8 | transport name / send-receive loopback / make_pair 双向 / request-reply / request 超时 / send_data inline / encode_envelopes 模式 / close |
| `TestStockStatClientComputeBackend` | 6 | 默认 backend is Local / compute.remote 存在 / cluster_info / backtest 默认路径不变 / 显式 local backend / compute.remote('backtest') / compute.remote('indicator') |
| `TestV2ClientComputeBackend` | 3 | offline 默认 Local / offline backtest / offline cluster_info |
| `TestResultConsistency` | 2 | backtest 本地与直调一致 / grid_search 排序结果 |
| `TestStreamResults` | 1 | grid_search 发布进度 partials |
| `TestErrorHandling` | 2 | 失败任务错误消息传播 / TaskInfo 记录错误 |
| `TestProtocolConformance` | 2 | LocalComputeBackend satisfies ComputeBackend / InProcessTransport satisfies Transport |

### 4.1 测试结果

```
============================= 35 passed in 2.43s ==============================
```

---

## 5. 回归验证

### 5.1 前端全量测试

```
576 passed, 12 warnings in 83.24s
```

- 原有 491 项：**全部通过**（零回归）
- P0 协议骨架 50 项：**全部通过**
- P1 计算后端 35 项：**全部通过**
- 合计 576 项

### 5.2 关键回归点

| 测试集 | 数量 | 状态 |
|--------|------|------|
| `test_backtest_*.py`（17 个文件） | 277 | ✅ 全部通过——回测引擎零修改 |
| `test_v2_*.py`（4 个文件） | 116 | ✅ 全部通过——v2 五层架构无影响 |
| `test_frontend.py` | 31 | ✅ 全部通过——v1.7 公共 API 不变 |
| `test_nonlinear.py` | 38 | ✅ 全部通过——指标计算无影响 |
| `test_integration.py` | 19 | ✅ 全部通过——PAXG 集成无影响 |
| `test_matplotlib_charts.py` | 10 | ✅ 全部通过——可视化无影响 |

**结论**：P1 完全零回归。v1.7 / v2 客户端的默认行为与 v2.1 完全一致；新增的 `compute_backend` 参数全部可选。

---

## 6. 包配置更新

### 6.1 `frontend/pyproject.toml`

新增两个 V3 optional extras：

```toml
[project.optional-dependencies]
# ... 已有 ...
# V3 distributed compute offload
compute = ["cloudpickle>=3.0", "psutil>=5.9"]
distributed = ["stockstat[compute]", "redis>=5.0", "msgpack>=1.0"]
```

### 6.2 版本号

`stockstat/__init__.py` 版本：`0.1.0` → `3.0.0`（反映 V3 设计落地）

---

## 7. 关键设计决策

### 7.1 为什么 `compute_backend` 默认是 `None` 而非 `LocalComputeBackend()`？

为了让默认路径**完全跳过** V3 代码——`backtest()` 直接调用 `BacktestEngine`，连 `LocalComputeBackend` 的后台线程都不创建。这保证了：

1. 已有 277 项回测测试零修改通过（无任何 V3 代码介入）
2. 性能完全等同 v2.1（无线程创建开销）
3. `compute_backend` 属性在首次访问时才惰性创建 `LocalComputeBackend`

### 7.2 为什么 `_is_local_backend()` 检查？

显式传入 `LocalComputeBackend` 时，`backtest()` 仍走 v2.1 原路径，避免：
- 不必要的 `TaskSpec` 构建与 cloudpickle 序列化
- 后台线程切换开销
- 策略对象跨线程访问的潜在问题

只有显式传入**非本地** backend（如 `RemoteComputeBackend`）时，才走 TaskSpec 提交路径。

### 7.3 为什么 `remote()` 直接在 `ComputeEngine` 上实现？

- `client.compute` 已经返回 `ComputeEngine`，向后兼容
- 不引入新的 `ComputeAPI` 包装层，减少代码量
- `remote()` / `cluster_info()` 通过 `_get_compute_backend()` 解析 client 的 backend
- 已有 40+ 指标方法零修改

### 7.4 为什么 `LocalComputeBackend` 用后台线程而非进程？

- Phase 1 目标是**协议层验证**，不是并行加速
- 线程间共享内存，`BacktestResult` 等对象可直接传递，无需序列化
- Phase 2+ 的 `RemoteComputeBackend` + Worker 进程才真正实现并行
- daemon 线程在主进程退出时自动结束，无残留进程

### 7.5 为什么 `custom` task 支持 `_sleep_seconds`？

为了测试 `cancel()` 与 `stream_results()`：
- `cancel()` 需要任务还在运行才能取消
- `stream_results()` 需要任务有 partials 才能验证流式
- `_sleep_seconds` 让 custom task 可控地"慢下来"，便于测试时序

生产环境的 `grid_search` / `monte_carlo` 天然耗时长，不需要此参数。

---

## 8. 用法示例

### 8.1 v1.7 行为完全不变

```python
from stockstat import StockStatClient
client = StockStatClient(host="localhost", port=8000)
sma = client.compute.ma(data.close, window=20)
res = client.backtest(data, strategy, initial_cash=10000)
```

### 8.2 V3 显式异步提交

```python
import base64
from stockstat._core.codec import CloudpickleCodec

strategy_ref = "cloudpickle:" + base64.b64encode(
    CloudpickleCodec().encode(my_strategy)
).decode("ascii")

task = client.compute.remote(
    "backtest",
    symbols=["BTC/USDT"], timeframe="1d",
    strategy_ref=strategy_ref,
    initial_cash=10000,
)
print(task.id, task.status)  # UUID, "pending" -> "running" -> "completed"
result = task.wait(timeout=60)
```

### 8.3 V3 集群查询

```python
info = client.compute.cluster_info()
print(info["stats"]["total_workers"])  # 1 (本地)
print(info["workers"][0]["capabilities"])
# ['indicator', 'backtest', 'grid_search', 'batch_backtest', 'monte_carlo', 'custom']
```

### 8.4 V3 流式结果

```python
task = client.compute.remote("grid_search", ...)
for partial in task.stream_results():
    print(f"Progress: {partial.get('progress', 0):.0%}")
# Progress: 33%
# Progress: 67%
# Progress: 100%
# [final result]
```

### 8.5 V2Client 离线模式

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage

client = V2Client(mode="offline", storage=MemoryStorage())
# 默认 LocalComputeBackend
res = client.backtest(data, strategy)  # v2.1 行为
info = client.compute_backend.cluster_info()  # V3 新能力
```

---

## 9. 文件清单

```
frontend/stockstat/
├── _core/
│   ├── compute/                  [新增目录]
│   │   ├── __init__.py           [新增, 导出 LocalComputeBackend]
│   │   └── local.py              [新增, ~470 行]
│   └── transport/                [新增目录]
│       ├── __init__.py           [新增, 导出 InProcessTransport, make_pair]
│       └── in_process.py         [新增, ~155 行]
├── compute/
│   └── engine.py                 [修改, +remote() / cluster_info() / _get_compute_backend()]
├── client.py                     [修改, +compute_backend 参数 / +_build_backtest_task_spec()]
├── _api/
│   └── client/__init__.py        [修改, +compute_backend 参数 / +compute_backend 属性]
└── __init__.py                   [修改, 版本 0.1.0 -> 3.0.0]

frontend/pyproject.toml            [修改, +compute / distributed extras]
frontend/tests/
├── test_v3_protocol.py           [新增, 50 项]
├── test_v3_compute_backend.py    [新增, 35 项]
└── test_v3_compat.py             [新增, 23 项]

tests/                             [P1+ 部署场景测试]
├── deployments/                   [新增目录]
│   ├── README.md                  [部署测试指南]
│   ├── _common.py                 [共享辅助模块]
│   ├── test_case_a_single_machine.py + .bat + .sh   [Case A: 单机全栈]
│   ├── test_case_b_storage_separated.py + .bat + .sh [Case B: 存储-计算分离]
│   ├── test_case_c_offline.py + .bat + .sh           [Case C: 离线模式]
│   └── test_case_d_local_compute_backend.py + .bat + .sh [Case D: V3 API 全覆盖]
├── test_connection.py             [重写, V3 适配 + 步骤 8/9/10]
└── test_perf.py                   [重写, V3 适配 + 步骤 9-12]
```

---

## 10. 下阶段（P2）准备

P1 完成的 `LocalComputeBackend` + `InProcessTransport` 为 P2 铺平道路：

- P2 将实现 `DispatcherPlugin`（作为 Storage 插件）+ 独立 `Worker` 进程
- `Dispatcher` 复用 P0 的 Envelope / TaskSpec / 消息类型
- `Worker` 复用 P1 的 `_dispatch_to_handler` 调度逻辑
- `RemoteComputeBackend`（P3）将通过 `HttpTransport` 提交到 Dispatcher
- P2 验收：启动 `stockstat serve --enable-dispatcher` + `stockstat-compute worker`，跨进程任务可执行

---

*P1 完成。下一步进入 P2：实现 Dispatcher + Worker 跨进程任务执行。*
