# V3 P2 实施文档 — Dispatcher + Worker 跨进程任务执行

> **日期**：2026-07-19
> **状态**：✅ 已完成
> **关联**：[DESIGN_V3_CN.md §9-§10](../../DESIGN_V3_CN.md)
> **前置**：[P0_CN.md](P0_CN.md)（协议骨架）、[P1_CN.md](P1_CN.md)（本地后端）

---

## 1. 目标

实现 V3 §9-§10 的 Dispatcher + Worker 跨进程任务执行：

1. `DispatcherPlugin` 作为 FastAPI 插件挂载到 Storage 后端
2. `Dispatcher` 主体：任务调度 + 状态管理 + 数据预取 + 结果合并
3. `MemoryTaskQueue` / `RedisTaskQueue`：任务队列
4. `WorkerRegistry`：Worker 注册 / 心跳 / 超时检测
5. `DataCache`：Dispatcher 端数据预取 + LRU 缓存
6. `shard_task`：参数/标的/时间分片
7. `Worker` 独立包：注册 / 心跳 / 轮询 / 执行 / 回传
8. `TaskExecutor`：路由到 5 种 task handler
9. `register.py`：硬件检测（CPU/mem/GPU/disk via psutil）
10. `stockstat-compute` CLI

---

## 2. 完成内容

### 2.1 模块清单

| 模块 | 文件 | 说明 |
|------|------|------|
| Plugin | `backend/stockstat_backend/dispatcher/plugin.py` | `DispatcherPlugin.mount(app)` 挂载到 FastAPI |
| Core | `backend/stockstat_backend/dispatcher/core.py` | `Dispatcher` 主体（submit/get/cancel/assign/complete/fail/cluster_info） |
| Queue | `backend/stockstat_backend/dispatcher/queue.py` | `MemoryTaskQueue`（优先级队列）+ `RedisTaskQueue`（ZADD/BRPOP） |
| Workers | `backend/stockstat_backend/dispatcher/workers.py` | `WorkerRegistry`（register/heartbeat/timeout/stats） |
| Prefetch | `backend/stockstat_backend/dispatcher/prefetch.py` | `DataCache`（LRU + 命中率 + `cache://` ref） |
| Dispatch | `backend/stockstat_backend/dispatcher/dispatch.py` | `shard_task`（param_wise / symbol_wise / time_wise） |
| Routes | `backend/stockstat_backend/dispatcher/routes.py` | `/dispatch/*` + `/api/v1/tasks/*` 路由 |
| Worker | `worker/stockstat_compute/worker.py` | `Worker`（register/heartbeat/poll/execute/complete） |
| Executor | `worker/stockstat_compute/executor.py` | `TaskExecutor`（路由到 `stockstat._core.compute.handlers`） |
| Register | `worker/stockstat_compute/register.py` | `detect_hardware()` / `get_current_load()` via psutil |
| CLI | `worker/stockstat_compute/cli.py` | `stockstat-compute worker --dispatcher-url ...` |
| App | `backend/stockstat_backend/app.py` | `STOCKSTAT_DISPATCHER_ENABLED=true` 加载插件 |

### 2.2 REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/dispatch/submit` | POST | Client 提交 TaskSpec |
| `/dispatch/status/{id}` | GET | 查询任务状态 |
| `/dispatch/result/{id}` | GET | 获取任务结果（base64 cloudpickle） |
| `/dispatch/cancel/{id}` | POST | 取消任务 |
| `/dispatch/cluster` | GET | 集群拓扑（workers + stats） |
| `/dispatch/register` | POST | Worker 注册 |
| `/dispatch/heartbeat` | POST | Worker 心跳 |
| `/dispatch/unregister/{id}` | POST | Worker 主动下线 |
| `/dispatch/assign` | POST | Worker 拉取任务（capability 过滤） |
| `/dispatch/complete` | POST | Worker 回传结果 |
| `/dispatch/fail` | POST | Worker 上报失败 |
| `/dispatch/partial` | POST | Worker 流式部分结果（V2 §13.2） |
| `/api/v1/tasks` | POST/GET | V2 §10.2 兼容路由 |
| `/api/v1/tasks/{id}` | GET/DELETE | 状态/取消 |
| `/api/v1/tasks/{id}/result` | GET | 结果 |

### 2.3 任务分片

| 策略 | 适用 | 实现 |
|------|------|------|
| `none` / `auto` | 单次任务 | 不分片，1 个 slice |
| `param_wise` | grid_search | `param_grid` 切分为 N 个 chunk，每个 chunk 是 `params["param_slice"]` |
| `symbol_wise` | 多标的回测 | 每标的一个 slice |
| `time_wise` | 大时间范围 | 时间窗口均分 |

每个 slice 的 `task_id` 形如 `{parent_id}-s{index}`，Dispatcher 通过前缀反查父任务状态。

### 2.4 数据预取

```python
def _prefetch_data(self, spec, parent_state) -> str:
    cache_key = DataCache.make_key(spec.data_spec)
    if cached := self._cache.get_ref(cache_key):
        return cached                    # 命中
    data = self._fetch_from_storage(spec.data_spec)  # 1 次 Storage 拉取
    return self._cache.put(cache_key, cloudpickle_bytes)  # 返回 cache://key
```

- 缓存键 = `sha256(symbols + timeframe + start + end + source)` 前 32 字节
- LRU 淘汰，默认 512MB
- 命中率统计：`cache_hit_rate = hits / (hits + misses)`
- Worker 收到 `data_ref` + 内联 base64 数据（`data_dispatch="inline"`）

### 2.5 结果合并

- 单 slice：直接返回该 slice 结果（解码后 cloudpickle 重编码为 base64 上线）
- grid_search：所有 slice 的 list 拼接 + 按 `metric` 排序（`maximize` 控制方向）
- batch_backtest：所有 slice 的 DataFrame 拼接
- 其他：返回第一个 slice 的结果

### 2.6 Worker 生命周期

```
启动 → detect_hardware() → POST /dispatch/register
                          ↓
            心跳线程（10s）→ POST /dispatch/heartbeat
                          ↓
            主循环 → POST /dispatch/assign → 执行 → POST /dispatch/complete
                          ↓
            SIGTERM → stop() → 等待活跃任务 → POST /dispatch/unregister → 退出
```

- `Worker.start()`：阻塞，适用于 CLI
- `Worker.start_background()`：后台线程，适用于测试 / 嵌入
- `Worker.wait_registered(timeout)`：等待注册完成
- `Worker.stop()` + `Worker.join(timeout)`：优雅停止

### 2.7 配置

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `STOCKSTAT_DISPATCHER_ENABLED` | `false` | 启用 Dispatcher 插件 |
| `STOCKSTAT_DISPATCHER_QUEUE` | `memory` | 队列后端（`memory`/`redis`） |
| `STOCKSTAT_DISPATCHER_CACHE_MB` | `512` | DataCache 最大尺寸 |
| `REDIS_URL` | — | Redis 连接 URL（queue=redis 时） |

---

## 3. 测试体系

### 3.1 新增测试文件

| 文件 | 测试数 | 覆盖 |
|------|--------|------|
| `frontend/tests/test_v3_dispatcher.py` | 48 | MemoryTaskQueue / WorkerRegistry / DataCache / shard_task / Dispatcher 主体 / DispatcherPlugin / 结果合并 |
| `frontend/tests/test_v3_worker.py` | 22 | detect_hardware / Worker 构造 / TaskExecutor / Worker E2E / 心跳超时 / 多 Worker / 能力路由 |
| `frontend/tests/test_v3_e2e.py` | 13 | Client → Dispatcher → Worker 完整链路 / 5 种任务类型 / 数值一致性 / async_submit / cluster_info |

**合计**：83 项新增测试，全部通过

### 3.2 关键测试场景

#### 3.2.1 跨进程任务执行
```python
def test_custom_task_e2e(self, dispatcher_app, worker):
    spec = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                    compute_spec=ComputeSpec(task_type="custom", params={"e2e": "yes"}))
    httpx.post("http://localhost:8000/dispatch/submit", json=spec.to_dict())
    # 轮询直到完成
    while not done: ...
    # 取结果（base64 cloudpickle）
    raw = base64.b64decode(resp.json()["result"])
    result = CloudpickleCodec().decode(raw)
    assert result["params"]["e2e"] == "yes"
```

#### 3.2.2 远程回测与直调数值一致
```python
def test_backtest_numerical_match_direct(self, e2e_stack, sample_data, sample_strategy):
    # 通过 RemoteComputeBackend → Dispatcher → Worker
    remote_result = backend.submit(spec).wait(timeout=30)
    # 直调 BacktestEngine
    direct = BacktestEngine(data=sample_data, strategy=..., initial_cash=10000).run()
    np.testing.assert_array_almost_equal(
        remote_result.equity.values, direct.equity.values, decimal=6,
    )
```

#### 3.2.3 多 Worker 集群拓扑
```python
def test_two_workers_register(self, dispatcher_app):
    w1 = Worker(alias="w1", concurrency=2, ...)
    w2 = Worker(alias="w2", concurrency=3, ...)
    # 两个 Worker 都注册后
    info = httpx.get(".../dispatch/cluster").json()
    assert info["stats"]["total_workers"] == 2
    assert info["stats"]["total_concurrency"] == 5
```

#### 3.2.4 能力路由
```python
def test_capability_routing(self, dispatcher_app):
    w = Worker(alias="limited", capabilities=["custom"], ...)
    # Worker 只能处理 "custom"；"backtest" 任务会被重新入队
    spec = TaskSpec(..., compute_spec=ComputeSpec(task_type="custom", ...))
    httpx.post(".../dispatch/submit", json=spec.to_dict())
    # custom 任务被 worker 拾取并完成
    assert state == "completed"
```

#### 3.2.5 心跳超时下线
```python
def test_worker_marked_offline_after_timeout(self):
    # offline_timeout=1.0s, heartbeat_interval=0.3s
    w = Worker(alias="ephemeral", heartbeat_interval=0.3, ...)
    w.start_background()
    # 验证 online
    assert info["stats"]["online_workers"] == 1
    w.stop()
    time.sleep(2.5)  # 超过 offline_timeout
    # 验证 offline
    assert info["stats"]["online_workers"] == 0
```

### 3.3 测试基础设施

`conftest.py` 自动将 `backend/` 和 `worker/` 加入 `sys.path`，让前端测试可
直接导入 `stockstat_backend` 和 `stockstat_compute`：

```python
# frontend/tests/conftest.py
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_BACKEND = os.path.join(_PROJECT_ROOT, "backend")
_WORKER = os.path.join(_PROJECT_ROOT, "worker")
for path in (_BACKEND, _WORKER):
    if path not in sys.path:
        sys.path.insert(0, path)
```

跨进程 HTTP 测试用 `fastapi.testclient.TestClient` + `httpx` monkey-patch
桥接，零网络开销：

```python
def _bridge_httpx_to_app(app):
    """Patch httpx.post/get to route localhost:8000 calls to TestClient(app)."""
    test_client = TestClient(app)
    orig_post, orig_get = httpx.post, httpx.get
    def patched_post(url, **kw):
        if "localhost:8000" in url:
            p = urlparse(url)
            return _Resp(test_client.post(p.path, **cleaned))
        return orig_post(url, **kw)
    httpx.post = patched_post
    ...
```

---

## 4. 关键设计决策

### 4.1 Worker 通过 HTTP 拉模式（而非推送）

V2 §5 原始设计支持推/拉两种模式。V3 实现选择**纯拉模式**：

- Worker 主动 `POST /dispatch/assign` 拉取任务
- 简化 Dispatcher 实现（无需维护 Worker 长连接）
- Worker 可控并发（线程池大小 = `--concurrency`）
- 心跳单独线程，与任务执行解耦

### 4.2 数据内联 + base64

P2 阶段采用 `data_dispatch="inline"`：Dispatcher 把 cloudpickle 编码的数据
base64 后随 `dispatch.assign` 一起返回。简单可靠，无需共享内存或额外
HTTP 拉取。

P4 阶段引入 `SharedMemoryTransport` 后会切换为 `shm://` 引用。

### 4.3 结果统一为 base64 cloudpickle

无论原结果是 `BacktestResult` / `pd.Series` / `pd.DataFrame` / dict，
Worker 都用 `CloudpickleCodec` 编码为 bytes，再 base64 后通过 JSON 传输。
Dispatcher 端解码后存为 Python 对象，合并完成后再次编码为 base64 上线。
Client 端的 `RemoteComputeBackend._fetch_result` 自动解码为原对象。

### 4.4 Worker.start_background()

为了测试可嵌入，新增 `start_background()` 方法在守护线程中运行注册
+ 心跳 + 轮询循环。`start()` 仍为阻塞入口（CLI 使用）。

### 4.5 单进程模拟跨进程

测试用 `fastapi.testclient.TestClient` + httpx monkey-patch 实现"假跨
进程"：所有 HTTP 调用都路由到同进程的 FastAPI app。这验证了：

- 协议正确性（Envelope / TaskSpec / JSON 传输）
- Dispatcher / Worker 状态机
- 多线程并发安全

但不验证真实网络故障 / 序列化跨版本兼容（P3+ 真实 HTTP 部署覆盖）。

---

## 5. 兼容性

### 5.1 与 P0+P1 兼容

- `LocalComputeBackend` 行为不变：默认 `compute_backend=None` 仍走 v2.1
  直接路径
- `RemoteComputeBackend` 在 P2 真正可用（之前只支持 InProcessTransport）
- 599 项原有测试零回归

### 5.2 与 v1.7 / v2 客户端兼容

- `StockStatClient(compute_backend=RemoteComputeBackend(...))` 透明同步
- `client.backtest(data, strategy)` 远程模式：内部 submit + wait
- `client.backtest(..., async_submit=True)` 返回 TaskRef
- `client.compute.remote(...)` 显式异步
- `client.compute.cluster_info()` 返回真实集群拓扑

### 5.3 与 v2.1 部署兼容

- `stockstat serve` 行为不变
- `--enable-dispatcher` / `STOCKSTAT_DISPATCHER_ENABLED=true` 启用插件
- 不启用时零开销（不挂载路由、不创建 Dispatcher 实例）

---

## 6. 性能基线

| 场景 | P2 实测 | 备注 |
|------|---------|------|
| Custom 任务往返延迟 | ~50ms | 含 HTTP 序列化 + cloudpickle 解码 |
| Backtest 50 bar 远程 vs 直调 | < 200ms | Worker 线程池串行执行 |
| grid_search 4 组 2 分片 | < 1s | 单 Worker 串行处理 2 个 slice |
| 心跳间隔 | 0.5s（测试）/ 10s（默认） | 可配置 |
| 心跳超时检测周期 | 10s（Dispatcher 后台线程） | `check_timeouts()` |

P3+ 将补充：
- 真实 HTTP 跨机延迟
- 多 Worker 并行加速比
- 大数据（50MB+）分发性能

---

## 7. 已知限制

1. **Redis 队列未实测**：`RedisTaskQueue` 实现完整，但 CI 环境无 Redis。
   P5 阶段补全。
2. **数据预取依赖 Storage 同进程**：`_fetch_from_storage` 优先用
   `storage_app` 同进程访问；若 Storage 在另一台机器，走 HTTP fallback。
3. **任务失败不自动重试**：`on_fail` 当前直接标记父任务 FAILED。重试
   逻辑在 P6 实现（`RetryPolicy`）。
4. **取消只标记状态**：Worker 已开始执行的任务无法强制中断，只能等
   其自然完成或失败。P6 抢占支持后可改进。
5. **没有 Worker 间负载均衡**：当前是"先到先得"——空闲 Worker 拉到
   任务即处理。P5 引入 Redis 队列后自动负载均衡。

---

## 8. 文件清单

```
backend/stockstat_backend/dispatcher/
├── __init__.py             [17 行]
├── plugin.py               [66 行]
├── core.py                 [378→410 行]  +base64 编解码 +结果合并
├── queue.py                [145 行]      -broken import 修复
├── workers.py              [181 行]
├── prefetch.py             [127 行]
├── dispatch.py             [106 行]
└── routes.py               [153 行]

worker/stockstat_compute/
├── __init__.py             [17 行]
├── worker.py               [235→283 行]  +start_background/join/wait_registered
├── executor.py             [70 行]
├── register.py             [95 行]
└── cli.py                  [102 行]

frontend/tests/
├── conftest.py             [15 行]       NEW — sys.path 引导
├── test_v3_dispatcher.py   [615 行]      NEW — 48 项
├── test_v3_worker.py       [615 行]      NEW — 22 项
└── test_v3_e2e.py          [580 行]      NEW — 13 项
```

---

## 9. 下阶段规划

### P3：HTTP 跨机部署
- 真实 HTTP 跨机测试（docker compose）
- `AutoComputeBackend` 路由测试
- 跨机 grid_search 加速比测量

### P4：共享内存 + 流式
- `SharedMemoryTransport` 实测
- `Stream` 鸭子类型检测
- `dispatch.partial` 流式回传
- `data_dispatch="auto"` 自动选择

### P5：Redis 集群
- `RedisTaskQueue` 实测
- `RedisTransport` 实现
- MessagePack 协商
- 多 Worker 负载均衡

### P6：抢占 / 弹性
- `dispatch.preempt` / `dispatch.resume`
- Worker `checkpoint.py`
- `dispatch.drain` 优雅下线
- `cluster.discover` 自动发现
- `RetryPolicy` 任务重试

### P7：多级 Dispatcher + 监控
- 子 Dispatcher 注册
- Admin Task 监控页面
- WebSocket 进度推送

---

*P2 完成。下一步进入 P3：HTTP 跨机部署与 AutoComputeBackend。*
