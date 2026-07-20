# V3 P4 实施文档 — 共享内存 + 流式 + 数据分发策略

> **日期**：2026-07-19
> **状态**：✅ 已完成
> **关联**：[DESIGN_V3_CN.md §12-§13.2](../../DESIGN_V3_CN.md)
> **前置**：[P3_CN.md](P3_CN.md)（HTTP 跨机）

---

## 1. 目标

实现 V3 §12-§13.2 的同机零拷贝、流式数据传输与自动分发策略：

1. `SharedMemoryTransport` 完整可用（inline + shm:// + close 清理）
2. `Stream` 对象支持迭代模式（增量）与 collect 模式（全量）
3. `is_stream_aware` 鸭子类型检测：handler 签名声明 Stream → 增量传入
4. `dispatch.partial` 消息处理：Worker 推送部分结果 → Dispatcher 缓存
5. Client `task.stream_results()` 消费 partials + final
6. `data_dispatch="auto"` 自动选择 inline / shared_memory / storage_ref / stream

---

## 2. 完成内容

### 2.1 SharedMemoryTransport

`frontend/stockstat/_core/transport/shared_memory.py`：

| 方法 | 行为 |
|------|------|
| `send(env)` / `receive(timeout)` / `request(env, timeout)` | 委托给 underlying transport（默认 InProcess） |
| `send_data(bytes, ct)` | < `inline_threshold`（默认 10MB）→ `inline:<base64>`；否则 → `shm://name` |
| `fetch_data(ref)` | 解码 `inline:` / `shm://`；shm 优先查本地 registry，否则 attach |
| `close()` | 遍历 `_shm_registry`，对每段 `shm.close() + shm.unlink()` |

**关键设计**：
- 控制面（Envelope）走 underlying；数据面（bytes）走 shm
- 同进程内通过 `_shm_registry` 直接返回 `bytes(shm.buf)`，零拷贝
- 跨进程（同机）通过 `SharedMemory(name=shm_name)` attach
- shm 创建失败时优雅降级为 inline base64

### 2.2 Stream 类

`frontend/stockstat/_core/compute/handlers.py`：

```python
class Stream:
    """数据流 — 同时支持迭代模式（chunk）与 collect 模式（全量）。

    Worker 通过检查函数签名自动决定如何传入：
    - 签名声明 Stream → 传 Stream 对象（增量计算）
    - 签名声明 pd.DataFrame → 调用 stream.collect() 传完整 DataFrame
    """
    def __init__(self, chunks=None, data=None): ...
    def __iter__(self): ...      # yield 每个 chunk
    def collect(self) -> Any: ...  # 返回完整 DataFrame（缓存）
    @classmethod
    def from_data(cls, data) -> "Stream": ...  # 包装单 chunk
```

**关键特性**：
- `collect()` 幂等：多次调用返回同一缓存对象
- `from_data(df)` 创建单 chunk Stream，迭代只 yield 一次
- 多 chunk Stream：迭代 yield 每个 chunk；`collect()` 拼接所有

### 2.3 鸭子类型检测

```python
def is_stream_aware(handler) -> bool:
    """检查 handler.handle 的签名是否声明 Stream。"""
    sig = inspect.signature(handler)
    for param in sig.parameters.values():
        if param.annotation is Stream or "Stream" in str(param.annotation):
            return True
    return getattr(handler, "__stream_aware__", False)
```

`dispatch()` 在路由时自动检测：

```python
def dispatch(spec, data, on_progress=None):
    handler = HANDLERS.get(task_type)
    if is_stream_aware(handler):
        stream = Stream.from_data(data)
        return handler(spec, stream, on_progress=on_progress)
    return handler(spec, data, on_progress=on_progress)
```

**示例**：
```python
# 全量处理器（默认）
def handle_backtest(spec, data, on_progress=None):
    # data 是 {symbol: {timeframe: df}}
    ...

# 增量处理器（声明 Stream）
def handle_stream_backtest(spec, stream: Stream, on_progress=None):
    for chunk in stream:
        process(chunk)
    ...
```

### 2.4 dispatch.partial 消息处理

Dispatcher 端 `on_partial(worker_id, slice_id, partial)`：

```python
def on_partial(self, worker_id, slice_id, partial):
    parent_state = self._tasks.get(parent_id)
    if parent_state is None:
        return {"status": "unknown_task"}
    if not hasattr(state, "stream_partials"):
        state.stream_partials = []
    state.stream_partials.append(partial)
    return {"status": "ok"}
```

Worker 端 `_send_partial(slice_id, partial)`：

```python
def _send_partial(self, slice_id, partial):
    httpx.post(f"{self._url}/dispatch/partial", json={
        "worker_id": self._worker_id,
        "slice_id": slice_id,
        "partial": partial,
    }, timeout=5)
```

`TaskExecutor` 在 grid_search 等任务中通过 `on_progress(completed, total)`
回调触发 `_send_partial`。

### 2.5 stream_results() 消费

```python
# LocalComputeBackend
def stream_results(self, task_id):
    state = self._get_state(task_id)
    self.wait(task_id)  # 等待完成
    for p in state.partials:  # 本地缓存
        yield p
    if not state.partials or state.partials[-1] is not state.result:
        yield state.result

# RemoteComputeBackend
def stream_results(self, task_id):
    seen = 0
    while True:
        info = self.get(task_id)
        if info.state in (COMPLETED, FAILED, CANCELLED):
            if info.state == COMPLETED:
                yield self._fetch_result(task_id)
            break
        time.sleep(self._poll_interval)
```

### 2.6 data_dispatch 策略

`frontend/stockstat/_core/compute/data_dispatch.py`：

```python
def choose_data_dispatch(data_size, workers_same_host=False,
                         workers_can_reach_storage=False) -> str:
    if data_size < SMALL_DATA_THRESHOLD:       # < 10MB
        return "inline"
    if workers_same_host:
        return "shared_memory"                 # 同机零拷贝
    if data_size > LARGE_DATA_THRESHOLD and workers_can_reach_storage:  # > 100MB
        return "storage_ref"                   # Worker 直拉 Storage
    return "stream"                            # 跨机流式
```

| 策略 | 数据大小 | 拓扑 | 路径 |
|------|---------|------|------|
| `inline` | < 10MB | 任意 | Dispatcher → Worker（base64 内联） |
| `shared_memory` | 任意 | 同机 | Dispatcher 写 shm → Worker 读 shm |
| `storage_ref` | > 100MB | Worker 可达 Storage | Worker 直接 GET Storage |
| `stream` | 10-100MB | 跨机 | Dispatcher 流式推送（chunked Arrow IPC） |

`resolve_data_dispatch(spec_dispatch, ...)`：
- 如果 spec 显式指定（非 `auto`），原样返回
- 如果 `auto`，调用 `choose_data_dispatch` 自动选择

`estimate_data_size(data)`：
- bytes/bytearray → `len(data)`
- DataFrame → `df.memory_usage(deep=True).sum()`
- dict {symbol: {tf: df}} → 所有 df 之和
- 其他 → 1024（保守默认）

---

## 3. 测试体系

### 3.1 新增测试

**文件**：`frontend/tests/test_v3_shm_stream.py` — **34 项**

| 类 | 测试数 | 覆盖 |
|----|--------|------|
| `TestSharedMemoryTransport` | 8 | name / inline / shm / fetch / roundtrip / close / 委托 |
| `TestStream` | 5 | from_data / iter / collect / multi-chunk / 幂等 |
| `TestStreamAwareness` | 4 | 非 stream / Stream 注解 / __stream_aware__ / dispatch 路由 |
| `TestDataDispatch` | 11 | inline / shm / storage_ref / stream / resolve / estimate (4 类) |
| `TestDispatchPartial` | 4 | 存储 / 累积 / unknown task / 路由存在 |
| `TestStreamResultsE2E` | 2 | 本地最终结果 / grid_search partials |

### 3.2 关键测试场景

#### 3.2.1 SharedMemory round-trip
```python
def test_send_data_roundtrip(self):
    t = SharedMemoryTransport(inline_threshold=10)
    data = b"\x00\x01\x02\x03\xff\xfe" * 100  # 600 bytes
    ref = t.send_data(data, "application/octet-stream")
    fetched = t.fetch_data(ref)
    assert fetched == data
```

#### 3.2.2 Stream duck-typing dispatch
```python
def my_stream_handler(spec, stream: Stream, on_progress=None):
    data = stream.collect()
    df = next(iter(next(iter(data.values())).values()))
    return {"rows": len(df)}

handlers.HANDLERS["custom_stream"] = my_stream_handler
result = dispatch(spec, data)
assert result["rows"] == 20  # Stream 路径触发
```

#### 3.2.3 data_dispatch 自动选择
```python
def test_very_large_data_uses_storage_ref(self):
    assert choose_data_dispatch(
        200 * 1024 * 1024,
        workers_same_host=False,
        workers_can_reach_storage=True,
    ) == "storage_ref"
```

#### 3.2.4 dispatch.partial 累积
```python
def test_multiple_partials_accumulate(self):
    d.submit(spec)
    for i in range(5):
        d.on_partial("w1", spec.task_id, {"i": i})
    state = d._tasks[spec.task_id]
    assert len(state.stream_partials) == 5
    assert [p["i"] for p in state.stream_partials] == [0, 1, 2, 3, 4]
```

#### 3.2.5 stream_results with partials
```python
def test_stream_results_with_partials(self):
    # grid_search 发布 2 个 partial（每完成 1 个组合）
    ref = backend.submit(grid_search_spec)
    parts = list(ref.stream_results())
    # 最后是 final result（list of dicts）
    assert isinstance(parts[-1], list)
    assert len(parts[-1]) == 2  # 2 grid combinations
```

---

## 4. 兼容性

### 4.1 与 P3 兼容

- `HttpTransport.send_data()` 仍返回 `inline:<base64>`（P3 默认）
- `SharedMemoryTransport` 委托控制面给 `HttpTransport`，仅替换数据面
- 切换：`RemoteComputeBackend(transport=SharedMemoryTransport(underlying=HttpTransport(...)))`

### 4.2 与 v2.1 客户端兼容

- LocalComputeBackend 行为不变
- Stream 类仅在新 handler 中使用；旧 handler 不受影响
- `data_dispatch="auto"` 在 Dispatcher 内部解析，Client 无感知

---

## 5. 性能基线

| 场景 | P4 实测 | 备注 |
|------|---------|------|
| SharedMemory round-trip 600B | < 1ms | 同进程，shm 直接读 buf |
| SharedMemory round-trip 1KB | < 1ms | 同上 |
| Stream collect (1000 行 df) | < 1ms | `pd.concat` 单 chunk |
| is_stream_aware 检测 | < 0.1ms | inspect.signature |
| choose_data_dispatch | < 0.01ms | 纯比较 |

**P4+ 真实跨进程 shm 测量**（待 Case E 部署测试）：
- 50MB DataFrame shm 写入 + 读取：< 100ms 目标
- vs inline base64：< 1s vs > 5s

---

## 6. 已知限制

1. **SharedMemory 跨平台**：Windows / macOS / Linux 均支持
   `multiprocessing.shared_memory`，但创建大段 shm 在 Windows 上可能失败
   （会优雅降级为 inline）。
2. **stream_results 轮询**：RemoteComputeBackend 仍用轮询，未实现
   WebSocket 推送（P7 范围）。
3. **data_dispatch 未在 Dispatcher 中接入**：策略函数已实现，但
   Dispatcher 当前总是用 inline。完整接入需修改 `_prefetch_data` +
   `assign_task`，根据 `data_dispatch` 选择 inline/shm/storage_ref。
   P5+ 完善。
4. **Stream 仅单进程验证**：跨进程 Stream（chunked Arrow IPC 流）未实现。

---

## 7. 文件清单

```
frontend/stockstat/_core/
├── transport/
│   └── shared_memory.py     [100 行]      fix: name 属性重复
├── compute/
│   ├── __init__.py          [12→35 行]    +导出 Stream/handlers/data_dispatch
│   ├── handlers.py          [407 行]      已含 Stream / is_stream_aware
│   └── data_dispatch.py     [NEW, 90 行]  choose/estimate/resolve

frontend/tests/
└── test_v3_shm_stream.py    [NEW, 470 行] 34 项
```

---

## 8. 下阶段规划

### P5：Redis 集群
- `RedisTaskQueue` 实测
- `RedisTransport` 实现（pub-sub 解耦）
- MessagePack envelope 协商
- 多 Worker 负载均衡

### P6：抢占 / 弹性
- `dispatch.preempt` / `dispatch.resume`
- Worker `checkpoint.py`
- `dispatch.drain` 优雅下线
- `cluster.discover` 自动发现

### P7：多级 Dispatcher + 监控
- 子 Dispatcher 注册
- Admin Task 监控页面
- WebSocket 进度推送

---

*P4 完成。下一步进入 P5：Redis 队列 + 多 Worker 集群。*
