# V3 阶段文档 P0 — 协议骨架

> **阶段**：P0（Protocol Skeleton）
> **日期**：2026-07-19
> **状态**：✅ 已完成
> **关联**：[DESIGN_V3_CN.md §5 协议设计](../../DESIGN_V3_CN.md#5-协议设计envelope-与-taskspec)、[§3 兼容层核心](../../DESIGN_V3_CN.md#3-兼容层核心computebackend-协议)

---

## 1. 目标

定义 V3 全部 Protocol 与数据结构，为后续阶段（P1 LocalComputeBackend、P2 Dispatcher/Worker）打基础。

**核心约束**：
- 零行为变更——已有 491 项前端测试 + 15 项后端测试全部通过
- 所有新模块可独立 import，不引入强依赖
- 新增功能全部可选（cloudpickle / msgpack 走 optional extras）

---

## 2. 新增模块

### 2.1 Layer 0 契约（`frontend/stockstat/_core/contracts/`）

| 文件 | 内容 | 说明 |
|------|------|------|
| `compute.py` | `ComputeBackend` Protocol、`TaskRef`、`TaskInfo`、`TaskState` | V3 兼容层核心——抽象"在哪算"（本地 / 远程） |
| `task.py` | `TaskSpec`、`DataSpec`、`ComputeSpec`、`DispatchSpec`、`new_task_id()` | V2 §12.5 三段式任务规范 |
| `transport.py` | `Transport` Protocol | V2 §12.7 传输层抽象 |

`contracts/__init__.py` 同步导出全部新协议：

```python
from .compute import ComputeBackend, TaskRef, TaskInfo, TaskState
from .task import TaskSpec, DataSpec, ComputeSpec, DispatchSpec
from .transport import Transport
```

### 2.2 协议层（`frontend/stockstat/_core/protocol/`）

| 文件 | 内容 | 说明 |
|------|------|------|
| `envelope.py` | `Envelope`、`Headers`、`PROTOCOL_NAME`、`PROTOCOL_VERSION` | V2 §12.3 统一消息信封，支持 JSON / Msgpack 双编码 |
| `messages.py` | 全部消息类型常量（task.\* / dispatch.\* / data.\* / cluster.\*）、`TYPE_TO_PATH` 映射、谓词函数 | V2 §12.4 消息类型表 |

`protocol/__init__.py` 导出：`Envelope`、`Headers`、`messages`。

### 2.3 编码层扩展（`frontend/stockstat/_core/codec/`）

在已有 `JsonCodec` / `CsvCodec` / `ArrowCodec` / `ParquetCodec` 基础上新增：

| Codec | media_type | 用途 |
|-------|-----------|------|
| `CloudpickleCodec` | `application/vnd.python.cloudpickle` | 策略函数闭包、用户对象 |
| `MsgpackCodec` | `application/msgpack` | 高效控制面（V2 §13.5） |
| `RawCodec` | `application/octet-stream` | 二进制透传 |

新增辅助函数 `get_codec_for_content_type(ct)`：按 MIME 类型自动选择 codec。

### 2.4 错误类扩展（`frontend/stockstat/_core/errors.py`）

在已有 `AppError` 体系下新增 9 个 V3 异常：

| 异常 | code | recoverable | 说明 |
|------|------|------------|------|
| `TaskError` | `TASK_FAILED` | False | 任务执行失败 |
| `TaskNotReadyError` | `TASK_NOT_READY` | True | 任务未完成 |
| `TaskCancelledError` | `TASK_CANCELLED` | False | 任务被取消 |
| `TaskTimeoutError` | `TASK_TIMEOUT` | True | 任务超时 |
| `TaskNotFoundError` | `TASK_NOT_FOUND` | False | 未知 task_id |
| `ProtocolMismatchError` | `PROTOCOL_MISMATCH` | False | 协议版本不兼容 |
| `TransportError` | `TRANSPORT_ERROR` | True | 传输层故障 |
| `DispatcherUnavailableError` | `DISPATCHER_UNAVAILABLE` | True | Dispatcher 不可达 |
| `WorkerCapabilityError` | `WORKER_CAPABILITY_INSUFFICIENT` | True | 无可用 Worker |

---

## 3. 关键设计决策

### 3.1 `TaskState` 用 `str, Enum` 双继承

```python
class TaskState(str, Enum):
    PENDING = "pending"
    ...
```

这样 `TaskState.PENDING == "pending"` 为真，便于 JSON 序列化和协议传输；同时保留 `enum.Enum` 的类型安全和迭代能力。

### 3.2 `Envelope.encode()` 自动处理 bytes payload

Envelope 的 payload 可能是 dict（控制面）或 bytes（数据面）。为保持整个信封可 JSON 序列化，bytes payload 会被 base64 编码并标记 `_payload_b64: True`；`decode()` 时自动还原。大数据应走 `headers.data_ref` 引用，而非内联 bytes。

### 3.3 `Envelope.encode()` 支持双编码

- `headers.encoding == "json"`（默认）：人可读，跨语言
- `headers.encoding == "msgpack"`：紧凑二进制（V2 §13.5），约 60% 体积

`decode()` 会先尝试 JSON 解析，失败再 fallback 到 Msgpack——传输方不需要显式声明编码方式。

### 3.4 `DataSpec.cache_key()`

为 Dispatcher 的 `DataCache` 提供稳定哈希键。相同 `data_spec` 的后续任务命中缓存，零拉取。

### 3.5 所有 dataclass 都提供 `to_dict()` / `from_dict()`

数据结构可 JSON 序列化，便于跨进程传输；不依赖 `dataclasses.asdict()`（避免 Timestamp / datetime 等不可序列化字段）。

---

## 4. 测试覆盖

测试文件：`frontend/tests/test_v3_protocol.py`（50 项）

| 测试类 | 测试数 | 覆盖范围 |
|--------|--------|---------|
| `TestEnvelope` | 8 | 默认字段 / UUID 唯一性 / dict 往返 / JSON 编解码 / bytes payload base64 / reply 构造 / msgpack 比 json 小 / 非法字节报错 |
| `TestHeaders` | 4 | 默认值 / 字段往返 / None 容错 / 部分字段 |
| `TestTaskSpec` | 10 | DataSpec 默认/往返/cache_key 稳定 / DispatchSpec 默认/往返 / ComputeSpec 默认/往返 / TaskSpec 三段式 / 完整往返 / new_task_id UUID 格式 |
| `TestTaskInfo` | 5 | TaskState 字符串值 / str 比较 / 默认值 / dict 往返 / 非法 state fallback |
| `TestComputeBackendProtocol` | 2 | Protocol 检测 / TaskRef API（id/state/status/ready/wait/result/cancel/stream_results） |
| `TestCodecExtensions` | 7 | codec 列表 / cloudpickle 闭包 / cloudpickle 对象 / msgpack 往返 / raw bytes / raw 拒绝复杂类型 / content_type 映射 |
| `TestMessageTypes` | 6 | 控制面类型 / 调度面类型 / 数据面类型 / 类型不相交 / HTTP 路径映射 / 谓词函数 |
| `TestErrorHierarchy` | 4 | 继承 AppError / code 唯一 / to_dict / recoverable 标志 |
| `TestTransportProtocol` | 2 | Protocol 检测 / 方法签名 |
| `TestEnvelopeTaskSpecIntegration` | 2 | task.submit 携带 TaskSpec / dispatch.complete 携带 bytes |

### 4.1 测试结果

```
============================= 50 passed in 1.98s ==============================
```

安装 `cloudpickle` 后从 48 passed + 2 skipped 变为 50 passed。

---

## 5. 回归验证

### 5.1 前端全量测试

```
======================= 541 passed, 12 warnings in 94.60s =======================
```

- 原有 491 项测试：**全部通过**
- 新增 50 项 V3 测试：**全部通过**
- 合计 541 项

### 5.2 关键回归点

| 测试集 | 数量 | 状态 |
|--------|------|------|
| `test_v2_core.py` | 49 | ✅ 全部通过 |
| `test_v2_domain.py` | 27 | ✅ 全部通过 |
| `test_v2_api.py` | 17 | ✅ 全部通过 |
| `test_backtest_*.py` | 277 | ✅ 全部通过 |
| `test_frontend.py` | 31 | ✅ 全部通过 |
| 其他 | 90 | ✅ 全部通过 |

**结论**：P0 完全零回归，v2.1 全部能力不受影响。

---

## 6. 依赖更新

P0 引入 3 个可选依赖（已在环境中安装）：

| 包 | 用途 | 必需性 |
|----|------|--------|
| `cloudpickle` | `CloudpickleCodec` —— 策略函数序列化 | V3 计算必需（P1+ 强依赖） |
| `msgpack` | `MsgpackCodec` —— 控制面高效编码 | 可选（生产部署用，调试用 JSON） |
| `psutil` | Worker 硬件检测（P2+ 使用） | P2+ 必需 |

`pyproject.toml` 待 P1 完成后统一更新 optional extras。

---

## 7. 下阶段（P1）准备

P0 完成的 Protocol 与数据结构为 P1 铺平道路：

- `LocalComputeBackend` 实现 `ComputeBackend` Protocol
- `InProcessTransport` 实现 `Transport` Protocol
- `StockStatClient` / `V2Client` 接入可选 `compute_backend` 参数
- `ComputeAPI` 提供 `remote()` / `cluster_info()` 入口
- `build_backtest_task_spec()` 等辅助函数将业务对象转换为 `TaskSpec`

P1 验收目标：
- `StockStatClient()` 默认 `LocalComputeBackend`，277 项回测测试零修改通过
- `V2Client(mode="offline")` 默认 `LocalComputeBackend`，离线测试通过
- `client.compute.remote("backtest", ...)` 返回 `TaskRef`，`task.wait()` 返回 `BacktestResult`
- `client.backtest(data, strategy)` 本地与远程（InProcess）模式结果一致

---

## 8. 文件清单

```
frontend/stockstat/_core/
├── contracts/
│   ├── compute.py          [新增, 165 行]
│   ├── task.py             [新增, 244 行]
│   ├── transport.py        [新增, 65 行]
│   └── __init__.py         [修改, 导出 V3 协议]
├── protocol/               [新增目录]
│   ├── __init__.py         [新增]
│   ├── envelope.py         [新增, 200 行]
│   └── messages.py         [新增, 145 行]
├── codec/
│   └── __init__.py         [修改, +3 个 Codec + get_codec_for_content_type]
└── errors.py               [修改, +9 个 V3 异常类]

frontend/tests/
└── test_v3_protocol.py     [新增, 50 项测试]
```

---

*P0 完成。下一步进入 P1：实现 LocalComputeBackend + InProcessTransport，让 v1.7 / v2 客户端可透明使用 compute_backend。*
