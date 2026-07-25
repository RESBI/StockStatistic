# V3 P3 实施文档 — HTTP 跨机部署 + AutoComputeBackend

> **日期**：2026-07-19
> **状态**：✅ 已完成
> **关联**：[DESIGN_V3_CN.md §7-§8](../../DESIGN_V3_CN.md)
> **前置**：[P2_CN.md](P2_CN.md)（Dispatcher + Worker）

---

## 1. 目标

实现 V3 §7-§8 的 HTTP 跨机部署与自动路由：

1. `HttpTransport` 完整实现（send / request / send_data / close）
2. `RemoteComputeBackend` 基于 `HttpTransport` 真实可用
3. `AutoComputeBackend` 按任务规模/类型路由（light → local, heavy → remote）
4. Envelope 在 HTTP 上的传输（JSON + base64 bytes payload）
5. 跨机部署场景（Case E：Client → Dispatcher → Worker via HTTP）

---

## 2. 完成内容

### 2.1 HttpTransport 增强

`frontend/stockstat/_core/transport/http.py`：

| 方法 | 行为 |
|------|------|
| `send(env)` | 火忘模式，POST 到 `TYPE_TO_PATH[type]` |
| `request(env, timeout)` | 请求-响应模式，自动解析 Envelope 或包装 JSON 响应 |
| `send_data(bytes, ct)` | 返回 `inline:<base64>` 引用（P3 默认；P4 支持 `shm://`） |
| `post_json(path, json)` | 直连 REST，绕过 Envelope（Worker / Client 内部用） |
| `get_json(path, params)` | 直连 REST GET |
| `close()` | 关闭内部 `httpx.Client` |

**关键改进**（P3 修复）：`request()` 现在能正确区分两种响应：

```python
# 1. 真正的 Envelope 响应（带 protocol=stockstat-rpc）
return Envelope.decode(resp.content)

# 2. 普通 JSON 响应（Dispatcher 直接返回的 dict）
return Envelope(type=f"{env.type}.reply", reply_to=env.id, payload=d)
```

通过检查 `d.get("protocol") == "stockstat-rpc"` 区分，避免把 Dispatcher 的
`{"task_id": "...", "status": "pending"}` 当成 Envelope 解析导致 `payload=None`。

### 2.2 RemoteComputeBackend

`frontend/stockstat/_core/compute/remote.py` 完整实现 `ComputeBackend` 协议：

| 方法 | 实现 |
|------|------|
| `submit(spec)` | `post_json("/dispatch/submit", spec.to_dict())` → `TaskRef` |
| `get(task_id)` | `get_json("/dispatch/status/{id}")` → `TaskInfo` |
| `result(task_id)` | 检查 state → `get_json("/dispatch/result/{id}")` → base64 解码 cloudpickle |
| `wait(task_id, timeout)` | 轮询 `get()` 直到完成/失败/超时 |
| `cancel(task_id)` | `post_json("/dispatch/cancel/{id}", {})` |
| `cluster_info(**kw)` | `get_json("/dispatch/cluster", params=kw)` |
| `stream_results(task_id)` | 轮询 `get()` 直到完成，yield 最终结果 |

**关键路径**：所有调用都通过 `transport.post_json` / `transport.get_json`，
未使用 Envelope 包装（保持 REST 简单性）。Envelope 主要用于未来 TcpTransport
等需要消息路由的场景。

### 2.3 AutoComputeBackend

`frontend/stockstat/_core/compute/auto.py` 按规则路由：

```python
HEAVY_TYPES = {"grid_search", "batch_backtest", "monte_carlo"}

def _choose(self, spec):
    if spec.compute_spec.task_type in HEAVY_TYPES and self._remote:
        return self._remote  # 重型 → 远程
    return self._local       # 轻型 → 本地
```

**特性**：
- 路由记录在 `self._routing[task_id] = "local"|"remote"`，后续 `get/wait/result` 自动反查
- 远程不可达时 `cluster_info()` 降级到 local
- 默认 `local=None` 时自动创建 `LocalComputeBackend`
- 用户可通过 `force="local"|"remote"` 显式覆盖（P6 扩展）

### 2.4 Envelope over HTTP

`HttpTransport.request()` 处理三种响应：

| 响应类型 | 检测 | 处理 |
|----------|------|------|
| 真正 Envelope | `d["protocol"] == "stockstat-rpc"` | `Envelope.decode()` |
| 普通 JSON | 任意 dict | 包装为 `Envelope(type=reply, payload=d)` |
| 二进制 | 非 UTF-8 | 包装为 `Envelope(payload=resp.content)` |

Envelope 自身的 `encode()` 处理 bytes payload：

```python
if isinstance(d["payload"], (bytes, bytearray)):
    d["payload"] = base64.b64encode(d["payload"]).decode("ascii")
    d["_payload_b64"] = True
```

`decode()` 自动检测 `_payload_b64` 标志并还原。

### 2.5 部署场景

| 场景 | Client | Dispatcher | Worker | 测试 |
|------|--------|-----------|--------|------|
| A 单机全栈 | 同进程 | — | — | test_case_a |
| B 存储分离 | HTTP→Storage | — | — | test_case_b |
| C 离线 | 本地 | — | — | test_case_c |
| D 显式 LocalBackend | 本地 | — | — | test_case_d |
| **E Dispatcher+Worker** | HTTP→Dispatch | Storage同机 | HTTP | test_v3_e2e + test_v3_http_transport |

Case E 的真实跨机部署需要：
1. 启动 Storage + Dispatcher：`STOCKSTAT_DISPATCHER_ENABLED=true stockstat serve`
2. 启动 Worker：`stockstat-compute worker --dispatcher-url http://storage:8000`
3. Client 用 `RemoteComputeBackend(dispatcher_url="http://storage:8000")`

---

## 3. 测试体系

### 3.1 新增测试

**文件**：`frontend/tests/test_v3_http_transport.py` — **22 项**

| 类 | 测试数 | 覆盖 |
|----|--------|------|
| `TestHttpTransport` | 6 | name / trailing slash / post_json / get_json / send_data / close |
| `TestRemoteComputeBackendHTTP` | 5 | name / constructor / cluster_info / submit+get_status / cancel |
| `TestAutoComputeBackend` | 6 | name / heavy→remote / light→local / no-remote fallback / cluster_info fallback / get routing |
| `TestCrossProcessE2E` | 2 | remote submit+complete / auto routes to remote |
| `TestEnvelopeOverHTTP` | 3 | TYPE_TO_PATH / envelope request via HTTP / bytes payload |

### 3.2 关键测试场景

#### 3.2.1 AutoComputeBackend 路由
```python
def test_routes_heavy_to_remote(self):
    remote = FakeRemote()
    b = AutoComputeBackend(local=LocalComputeBackend(), remote=remote)
    for task_type in ("grid_search", "batch_backtest", "monte_carlo"):
        spec = self._make_spec(task_type)
        b.submit(spec)
        assert remote.last.task_id == spec.task_id  # remote was called

def test_routes_light_to_local(self):
    b = AutoComputeBackend(local=LocalComputeBackend(),
                            remote=FakeRemote())  # remote raises if called
    spec = self._make_spec("custom")
    ref = b.submit(spec)  # goes to local
    ref.wait(timeout=5)
```

#### 3.2.2 Envelope + HTTP 互操作
```python
def test_envelope_request_via_http(self, http_stack):
    env = Envelope(type=DISPATCH_REGISTER, payload={...})
    reply = transport.request(env, timeout=5)
    # Dispatcher returns plain JSON; transport wraps it as Envelope
    assert reply.payload.get("status") == "registered"
```

#### 3.2.3 跨进程 e2e（同进程模拟）
```python
def test_remote_submit_and_complete(self, http_stack, worker_for_http):
    transport = HttpTransport("http://localhost:8000")
    transport._client = _HttpxCompatClient(test_client)  # in-process routing
    backend = RemoteComputeBackend(transport=transport)
    spec = TaskSpec(..., compute_spec=ComputeSpec(task_type="custom", params={"http_e2e": True}))
    result = backend.submit(spec).wait(timeout=10)
    assert result["params"]["http_e2e"] is True
```

### 3.3 测试基础设施

P3 复用 P2 的 httpx monkey-patch 桥接机制，新增 `_HttpxCompatClient` 包装
`fastapi.testclient.TestClient` 使其看起来像 `httpx.Client`：

```python
class _HttpxCompatClient:
    """Wrap TestClient to look like httpx.Client for HttpTransport."""
    def post(self, url, *, content=None, json=None, headers=None, timeout=None):
        p = urlparse(url)
        if json is not None:
            r = self._tc.post(p.path, json=json, headers=headers)
        elif content is not None:
            r = self._tc.post(p.path, content=content, headers=headers)
        ...
        return _HttpxCompatResponse(r)
```

让 `HttpTransport._client` 用 `TestClient` 而非真实 `httpx.Client`，实现
同进程 HTTP 模拟。

---

## 4. 兼容性

### 4.1 与 P2 兼容

- P2 的 `RemoteComputeBackend(transport=InProcessTransport())` 路径不变
- P3 新增 `RemoteComputeBackend(dispatcher_url="http://...")` 自动构建
  `HttpTransport`
- 两套 API 都可正常工作

### 4.2 与 v2.1 客户端兼容

```python
# v1.7 行为（不变）
client = StockStatClient()  # 默认 LocalComputeBackend
client.backtest(data, strategy)

# V3 远程模式（P3 真正可用）
client = StockStatClient(
    compute_backend=RemoteComputeBackend("http://dispatch:9000"),
)
result = client.backtest(data, strategy)  # 透明同步

# V3 自动路由
client = StockStatClient(
    compute_backend=AutoComputeBackend(
        local=LocalComputeBackend(),
        remote=RemoteComputeBackend("http://dispatch:9000"),
    ),
)
# 重型任务自动走远程，轻型走本地
```

---

## 5. 性能基线

| 场景 | P3 实测 | 备注 |
|------|---------|------|
| HTTP 单次 custom 任务往返 | ~50ms | 同进程模拟 |
| cluster_info 查询 | < 10ms | 同进程 |
| AutoComputeBackend 路由决策 | < 1ms | 纯字典查 |

**P3+ 真实跨机测量**（待 docker compose 集成）：
- 跨机 RTT 延迟（局域网）：~1ms 量级
- 跨机 grid_search 加速比（4 Worker）：目标 >= 3x

---

## 6. 已知限制

1. **未实测真实跨机**：测试用 `TestClient` 模拟 HTTP，不验证真实网络故障
   （连接拒绝 / 超时 / DNS 失败等）。Case E 部署测试在 `tests/deployments/`
   中补充（task #4）。
2. **不包含 TCP/SHM/Redis Transport**：P4/P5 实现。
3. **Worker 拉模式**：每秒一次 `POST /dispatch/assign` 轮询。低延迟场景
   可考虑长轮询或 WebSocket 推送（P7）。

---

## 7. 文件清单

```
frontend/stockstat/_core/
├── transport/
│   └── http.py              [88→113 行]   +JSON/Envelope 响应区分
├── compute/
│   ├── remote.py            [138 行]      已完整
│   └── auto.py              [78 行]       已完整

frontend/tests/
└── test_v3_http_transport.py [~470 行]    NEW — 22 项
```

---

## 8. 下阶段规划

### P4：共享内存 + 流式
- `SharedMemoryTransport` 实测（已存在，需测试）
- `Stream` 鸭子类型检测
- `dispatch.partial` 流式回传
- `data_dispatch="auto"` 自动选择（inline vs shm vs storage_ref）

### P5：Redis 集群
- `RedisTaskQueue` 实测
- `RedisTransport` 实现
- MessagePack envelope 协商

### P6：抢占 / 弹性
- `dispatch.preempt` / `dispatch.resume`
- `dispatch.drain` 优雅下线
- `cluster.discover` Worker 自动发现

### P7：多级 Dispatcher + 监控
- 子 Dispatcher 注册
- Admin Task 监控页面

---

*P3 完成。下一步进入 P4：共享内存 + 流式数据分发。*
