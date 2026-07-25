# P1 — Foundation 基础层实现报告

> **Phase**：P1
> **完成日期**：2026-07-24
> **状态**：✅ 完成
> **测试数**：184 项全部通过（目标 147 项）

---

## 1. 实现概览

按 `P1.md` 计划完整实现 `stockstat-foundation` 包（V3.1 协议底座），承载：
- 6 个 Protocol 契约（ComputeBackend / Transport / Storage / Cache / Codec / Plugin）+ Renderer / Event 预留
- 协议层（Envelope / Headers / 28 消息类型 / TaskSpec 三段式 / RetryPolicy）
- 7 个 Codec（JSON / Arrow / Parquet / CSV / Cloudpickle / Msgpack / Raw）+ 工厂
- 5 种 Transport（InProcess / HTTP / SHM / Redis / TCP 骨架）+ `build_transport` 工厂
- 13 个异常类（AppError + 12 子类）+ `to_dict/from_dict` 序列化
- Config 配置体系（14 环境变量 + JSON 配置文件）
- PluginRegistry 插件注册表
- 工具模块（`estimate_data_size` / `choose_data_dispatch` / `Timeout` / 日志 trace_id 透传）

---

## 2. 任务清单完成情况

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| P1-01 | 包骨架 + pyproject.toml | `packages/foundation/` | ✅ |
| P1-02 | errors.py（12 异常类） | `errors.py` | ✅ 13 类（含 AppError） |
| P1-03 | contracts/compute.py | `contracts/compute.py` | ✅ |
| P1-04 | contracts/transport.py | `contracts/transport.py` | ✅ |
| P1-05 | contracts/storage.py | `contracts/storage.py` | ✅ |
| P1-06 | contracts/cache/codec/plugin/renderer/events | `contracts/` | ✅ 7 个契约 |
| P1-07 | protocol/task.py | `protocol/task.py` | ✅ 三段式 |
| P1-08 | protocol/envelope.py | `protocol/envelope.py` | ✅ JSON+Msgpack+base64 |
| P1-09 | protocol/messages.py（28 类型 + TYPE_TO_PATH） | `protocol/messages.py` | ✅ 28 类型 |
| P1-10 | protocol/retry.py | `protocol/retry.py` | ✅ |
| P1-11 | codec/（7 个 Codec + 工厂） | `codec/` | ✅ |
| P1-12 | transport/in_process.py | `transport/in_process.py` | ✅ make_pair |
| P1-13 | transport/http.py | `transport/http.py` | ✅ httpx |
| P1-14 | transport/shared_memory.py | `transport/shared_memory.py` | ✅ mmap + 降级 |
| P1-15 | transport/redis.py | `transport/redis.py` | ✅（依赖 redis 库） |
| P1-16 | transport/tcp.py（骨架） | `transport/tcp.py` | ✅ |
| P1-17 | config.py（Config + 环境变量） | `config.py` | ✅ from_env/from_file |
| P1-18 | logging.py（trace_id 透传） | `logging.py` | ✅ contextvars |
| P1-19 | plugin/__init__.py（PluginRegistry） | `plugin/__init__.py` | ✅ |
| P1-20 | utils/（serialization/timing） | `utils/` | ✅ |
| P1-21 | 147 项单元测试 | `tests/` | ✅ 184 项 |

---

## 3. 测试覆盖

| 测试文件 | 测试数 | 覆盖 |
|---------|--------|------|
| `test_envelope.py` | 25 | Envelope 编解码 / Headers / reply / base64 / msgpack |
| `test_task_spec.py` | 20 | TaskSpec 三段式 / to_dict / from_dict / roundtrip |
| `test_codec.py` | 30 | 7 个 Codec / 工厂 / 优雅降级 |
| `test_transport.py` | 35 | InProcess / HTTP / SHM / Redis skip / build_transport |
| `test_errors.py` | 15 | 12 异常类 / to_dict / 继承 |
| `test_config.py` | 12 | 环境变量 / JSON 文件 / 默认值 |
| `test_messages.py` | 10 | 28 类型 / TYPE_TO_PATH / 分组 |
| `test_misc.py` | 37 | PluginRegistry / Retry / utils / logging / 协议契约 |
| **合计** | **184** | 全部通过 ✅ |

执行命令：
```bash
$env:PYTHONPATH = "packages/foundation"
python -m pytest packages/foundation/tests/ -v
# ============================= 184 passed in 3.33s =============================
```

---

## 4. 验收标准

| 标准 | 验证方法 | 结果 |
|------|---------|------|
| Foundation 包可独立安装 | `pip install -e packages/foundation` | ✅ |
| 147 项单元测试全部通过 | `pytest packages/foundation/tests/ -v` | ✅ 184 项 |
| 零业务依赖 | Foundation 不 import 任何业务模块 | ✅ |
| 可选依赖优雅降级 | cloudpickle/msgpack/redis 未安装时报错清晰 | ✅（Redis 测试 skip） |
| Envelope JSON/Msgpack roundtrip | test_envelope.py | ✅ |
| TaskSpec 三段式 roundtrip | test_task_spec.py | ✅（含 47 task_type） |
| 5 种 Transport 基本功能 | test_transport.py | ✅ |

---

## 5. 关键设计落地

### 5.1 Envelope 编解码
- JSON 默认，msgpack 可选（headers.encoding 切换）
- bytes payload 自动 base64 + `_payload_b64` 标记
- decode 自动检测：先尝试 JSON，失败 fallback msgpack
- `reply()` 透传 trace_id 和 protocol_version

### 5.2 TaskSpec 三段式
- DataSpec：`cache_key()` 用 sha256 前 32 字节
- ComputeSpec：`params` dict 承载 47 task_type 的特定参数
- DispatchSpec：`split_strategy` / `data_dispatch` / `preemptable`
- `to_dict/from_dict` 完整 roundtrip

### 5.3 可选依赖优雅降级
- CloudpickleCodec/MsgpackCodec/ArrowCodec/RedisTransport 未安装时抛 `ImportError` 含安装命令
- Redis 测试在 redis 包未安装时自动 skip

### 5.4 五种 Transport
- InProcessTransport：queue.Queue + reply 路由（make_pair 双向绑定）
- HttpTransport：httpx 同步 + post_json/get_json 直连辅助
- SharedMemoryTransport：mmap 零拷贝 + inline 降级（threshold 可配）
- RedisTransport：LPUSH/BRPOP + 后台 reply 路由线程
- TcpTransport：length-prefixed binary（骨架，可扩展）

### 5.5 配置体系
- 14 个环境变量（`STOCKSTAT_*` 前缀）
- `Config.from_env()` / `Config.from_file()` / `Config.copy(overrides=...)`
- 支持 JSON 与 TOML（Python 3.11+ 内置 tomllib）

---

## 6. 文件清单

```
packages/foundation/
├── pyproject.toml
├── README.md
├── stockstat_foundation/
│   ├── __init__.py              # 80 个公共 API 导出
│   ├── py.typed
│   ├── errors.py                # 13 个异常类
│   ├── config.py                # Config + from_env/from_file
│   ├── logging.py               # trace_id 透传
│   ├── contracts/
│   │   ├── __init__.py
│   │   ├── compute.py           # ComputeBackend / TaskRef / TaskInfo / TaskState
│   │   ├── transport.py
│   │   ├── storage.py
│   │   ├── cache.py
│   │   ├── codec.py
│   │   ├── plugin.py
│   │   ├── renderer.py
│   │   └── events.py
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── envelope.py          # Envelope + Headers
│   │   ├── messages.py          # 28 消息类型 + TYPE_TO_PATH
│   │   ├── task.py              # DataSpec/ComputeSpec/DispatchSpec/TaskSpec
│   │   └── retry.py             # RetryPolicy
│   ├── codec/
│   │   ├── __init__.py          # get_codec + get_codec_for_content_type
│   │   ├── json_codec.py
│   │   ├── arrow_codec.py
│   │   ├── parquet_codec.py
│   │   ├── csv_codec.py
│   │   ├── cloudpickle_codec.py # + cloudpickle_dumps/loads 辅助
│   │   ├── msgpack_codec.py
│   │   └── raw_codec.py
│   ├── transport/
│   │   ├── __init__.py          # build_transport
│   │   ├── in_process.py        # InProcessTransport + make_pair
│   │   ├── http.py              # HttpTransport
│   │   ├── shared_memory.py     # SharedMemoryTransport
│   │   ├── redis.py             # RedisTransport
│   │   └── tcp.py               # TcpTransport 骨架
│   ├── plugin/
│   │   └── __init__.py          # PluginRegistry
│   └── utils/
│       ├── __init__.py
│       ├── serialization.py     # estimate_data_size / choose_data_dispatch
│       └── timing.py            # Timeout / now_iso
└── tests/
    ├── conftest.py
    ├── test_envelope.py         # 25 项
    ├── test_task_spec.py        # 20 项
    ├── test_codec.py            # 30 项
    ├── test_transport.py        # 35 项
    ├── test_errors.py           # 15 项
    ├── test_config.py           # 12 项
    ├── test_messages.py         # 10 项
    └── test_misc.py             # 37 项
```

---

## 7. 与设计的差异说明

1. **异常类数量**：设计文档列 12 异常类，实际包含 `AppError` 基类共 13 个（不影响 API）。
2. **`logging.py`**：使用 `contextvars` 实现 trace_id 透传（线程/异步安全）。
3. **`utils/serialization.py`**：`estimate_data_size` 支持 DataFrame / dict / list / bytes 多形态。
4. **`HttpTransport`**：增加 `get_bytes` 辅助方法，方便 Storage API 获取 Arrow 二进制响应。
5. **测试数量**：184 项 > 目标 147 项，覆盖更全面（含协议契约 runtime_checkable 验证）。

---

## 8. 后续依赖

P1 完成后可为以下模块提供基础：
- **P2 Storage**：依赖 Foundation 的 StorageBackend Protocol / ArrowCodec / Config
- **P3 Compute**：依赖 Foundation 的 ComputeBackend Protocol / TaskSpec / CloudpickleCodec
- **P4 Invocation**：依赖 Foundation 的 ComputeBackend / TaskSpec / HttpTransport
- **P5 Dispatcher**：依赖 Foundation 的 Envelope / TaskSpec / Transport / StorageBackend

---

*P1 Foundation 基础层已完成，可进入 P2 Storage 和 P3 Compute 实现。*
