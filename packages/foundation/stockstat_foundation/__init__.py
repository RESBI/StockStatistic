"""stockstat-foundation — V3.1 基础层（协议/传输/契约/错误/配置）。

Foundation 是 Layer 0，零业务依赖，承载：
- 跨进程通信所需的 Envelope/TaskSpec
- 编码层（JSON/Arrow/Cloudpickle/Msgpack/...）
- 传输层抽象与实现（InProcess/HTTP/SHM/Redis/TCP）
- 各业务模块的 Protocol 契约
- 错误体系（AppError + 12 异常类）
- 配置体系（Config + 环境变量）
- 插件注册表（PluginRegistry）
"""
from __future__ import annotations

__version__ = "3.1.0"

from .errors import (
    AppError, TaskError, TaskNotReadyError, TaskCancelledError,
    TaskTimeoutError, TaskNotFoundError, ProtocolMismatchError,
    TransportError, DispatcherUnavailableError, WorkerCapabilityError,
    StorageError, ComputeError, ConfigError,
)
from .contracts import (
    ComputeBackend, TaskRef, TaskInfo, TaskState, TaskPriority,
    Transport, StorageBackend, Cache, Codec, Plugin, Renderer,
    Event, EventSubscriber,
)
from .protocol import (
    Envelope, Headers,
    TaskSpec, DataSpec, ComputeSpec, DispatchSpec,
    RetryPolicy,
    TYPE_TO_PATH, ALL_TYPES, CONTROL_TYPES, DISPATCH_TYPES,
    DATA_TYPES, DISCOVERY_TYPES,
    is_control, is_dispatch, is_data,
    TASK_SUBMIT, TASK_ACK, TASK_STATUS, TASK_RESULT, TASK_CANCEL,
    DISPATCH_ASSIGN, DISPATCH_COMPLETE, DISPATCH_REGISTER,
    DISPATCH_HEARTBEAT,
)
from .codec import (
    JsonCodec, ArrowCodec, ParquetCodec, CsvCodec,
    CloudpickleCodec, MsgpackCodec, RawCodec,
    get_codec, get_codec_for_content_type,
)
from .codec.cloudpickle_codec import cloudpickle_dumps, cloudpickle_loads
from .transport import (
    InProcessTransport, make_pair,
    HttpTransport, SharedMemoryTransport, RedisTransport, TcpTransport,
    build_transport,
)
from .config import Config
from .logging import get_logger, set_trace_id, get_trace_id
from .plugin import PluginRegistry
from .utils import (
    estimate_data_size, choose_data_dispatch, resolve_data_dispatch,
    Timeout, now_iso,
)

__all__ = [
    "__version__",
    # errors
    "AppError", "TaskError", "TaskNotReadyError", "TaskCancelledError",
    "TaskTimeoutError", "TaskNotFoundError", "ProtocolMismatchError",
    "TransportError", "DispatcherUnavailableError", "WorkerCapabilityError",
    "StorageError", "ComputeError", "ConfigError",
    # contracts
    "ComputeBackend", "TaskRef", "TaskInfo", "TaskState", "TaskPriority",
    "Transport", "StorageBackend", "Cache", "Codec", "Plugin", "Renderer",
    "Event", "EventSubscriber",
    # protocol
    "Envelope", "Headers",
    "TaskSpec", "DataSpec", "ComputeSpec", "DispatchSpec",
    "RetryPolicy",
    "TYPE_TO_PATH", "ALL_TYPES", "CONTROL_TYPES", "DISPATCH_TYPES",
    "DATA_TYPES", "DISCOVERY_TYPES",
    "is_control", "is_dispatch", "is_data",
    "TASK_SUBMIT", "TASK_ACK", "TASK_STATUS", "TASK_RESULT", "TASK_CANCEL",
    "DISPATCH_ASSIGN", "DISPATCH_COMPLETE", "DISPATCH_REGISTER",
    "DISPATCH_HEARTBEAT",
    # codec
    "JsonCodec", "ArrowCodec", "ParquetCodec", "CsvCodec",
    "CloudpickleCodec", "MsgpackCodec", "RawCodec",
    "get_codec", "get_codec_for_content_type",
    "cloudpickle_dumps", "cloudpickle_loads",
    # transport
    "InProcessTransport", "make_pair",
    "HttpTransport", "SharedMemoryTransport", "RedisTransport", "TcpTransport",
    "build_transport",
    # config
    "Config",
    # logging
    "get_logger", "set_trace_id", "get_trace_id",
    # plugin
    "PluginRegistry",
    # utils
    "estimate_data_size", "choose_data_dispatch", "resolve_data_dispatch",
    "Timeout", "now_iso",
]
