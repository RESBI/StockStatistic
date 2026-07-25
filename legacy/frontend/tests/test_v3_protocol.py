"""V3 P0 protocol skeleton tests — Envelope / TaskSpec / Headers / Codec.

Covers DESIGN_V3_CN §5 (protocol design) and §3 (contracts):
- Envelope encode/decode roundtrip (JSON + Msgpack)
- Headers field roundtrip
- TaskSpec three-section structure (data_spec / compute_spec / dispatch_spec)
- DataSpec / ComputeSpec / DispatchSpec serialization
- TaskInfo / TaskState transitions
- CloudpickleCodec / MsgpackCodec / RawCodec
- Message type table completeness
- Error class hierarchy
"""
from __future__ import annotations

import json
import pytest


# ═══════════════════════════════════════════════════════════════
# P0.1: Envelope encode/decode
# ═══════════════════════════════════════════════════════════════


class TestEnvelope:
    def test_envelope_default_fields(self):
        from stockstat._core.protocol import Envelope, PROTOCOL_NAME, PROTOCOL_VERSION
        env = Envelope(type="task.submit")
        assert env.protocol == PROTOCOL_NAME == "stockstat-rpc"
        assert env.version == PROTOCOL_VERSION == "1.0"
        assert env.type == "task.submit"
        assert isinstance(env.id, str) and len(env.id) > 0
        assert env.reply_to is None
        assert env.headers is not None

    def test_envelope_unique_ids(self):
        from stockstat._core.protocol import Envelope
        ids = {Envelope().id for _ in range(100)}
        assert len(ids) == 100  # all unique UUIDs

    def test_envelope_to_dict_roundtrip(self):
        from stockstat._core.protocol import Envelope, Headers
        env = Envelope(
            type="task.submit",
            reply_to="msg-123",
            headers=Headers(
                content_type="application/vnd.stockstat.task+json",
                trace_id="trace-abc",
                priority=-1,
                timeout=120,
            ),
            payload={"task_id": "t1", "data": [1, 2, 3]},
        )
        d = env.to_dict()
        assert d["type"] == "task.submit"
        assert d["reply_to"] == "msg-123"
        assert d["headers"]["trace_id"] == "trace-abc"
        assert d["headers"]["priority"] == -1
        assert d["payload"]["task_id"] == "t1"

        restored = Envelope.from_dict(d)
        assert restored.type == env.type
        assert restored.id == env.id
        assert restored.headers.trace_id == "trace-abc"
        assert restored.headers.priority == -1
        assert restored.payload == env.payload

    def test_envelope_json_encode_decode_roundtrip(self):
        from stockstat._core.protocol import Envelope, Headers
        env = Envelope(
            type="task.submit",
            headers=Headers(content_type="application/json", trace_id="t1"),
            payload={"task_id": "abc", "n": 42, "list": [1, 2, 3]},
        )
        raw = env.encode()
        assert isinstance(raw, bytes)

        restored = Envelope.decode(raw)
        assert restored.type == "task.submit"
        assert restored.headers.trace_id == "t1"
        assert restored.payload["task_id"] == "abc"
        assert restored.payload["n"] == 42

    def test_envelope_bytes_payload_base64_encoded(self):
        """Bytes payloads must be base64-encoded so envelope stays JSON-safe."""
        import base64
        from stockstat._core.protocol import Envelope, Headers
        binary = b"\x00\x01\x02\xff\xfe"
        env = Envelope(
            type="dispatch.complete",
            headers=Headers(content_type="application/octet-stream"),
            payload=binary,
        )
        raw = env.encode()
        # Should be valid JSON
        d = json.loads(raw.decode("utf-8"))
        assert d.get("_payload_b64") is True
        assert base64.b64decode(d["payload"]) == binary

        restored = Envelope.decode(raw)
        assert restored.payload == binary

    def test_envelope_reply_construction(self):
        from stockstat._core.protocol import Envelope, Headers
        original = Envelope(
            type="task.submit",
            headers=Headers(trace_id="trace-xyz"),
            payload={"task_id": "t1"},
        )
        reply = original.reply("task.ack", payload={"task_id": "t1", "status": "pending"})
        assert reply.type == "task.ack"
        assert reply.reply_to == original.id
        assert reply.headers.trace_id == "trace-xyz"
        assert reply.payload["status"] == "pending"

    def test_envelope_msgpack_encode_smaller_than_json(self):
        """V2 §13.5: msgpack should be smaller than json for typical payloads."""
        from stockstat._core.protocol import Envelope, Headers
        env = Envelope(
            type="dispatch.heartbeat",
            headers=Headers(encoding="json"),
            payload={
                "worker_id": "worker-01",
                "alias": "gpu-box-alpha",
                "load": {"cpu_percent": 37.5, "memory_used_gb": 15.2},
                "active_tasks": 3,
                "completed_tasks": 156,
                "status": "online",
            },
        )
        json_size = len(env.encode())

        env_msgpack = Envelope(
            type="dispatch.heartbeat",
            headers=Headers(encoding="msgpack"),
            payload=env.payload,
        )
        try:
            msgpack_size = len(env_msgpack.encode())
            # msgpack should be smaller (or at worst equal)
            assert msgpack_size < json_size, (
                f"msgpack ({msgpack_size}B) should be < json ({json_size}B)"
            )
        except ImportError:
            pytest.skip("msgpack not installed")

    def test_envelope_decode_invalid_bytes_raises(self):
        from stockstat._core.protocol import Envelope
        with pytest.raises((ValueError, json.JSONDecodeError, UnicodeDecodeError)):
            Envelope.decode(b"not a valid envelope \x00\xff")


# ═══════════════════════════════════════════════════════════════
# P0.2: Headers
# ═══════════════════════════════════════════════════════════════


class TestHeaders:
    def test_headers_defaults(self):
        from stockstat._core.protocol import Headers
        h = Headers()
        assert h.content_type == "application/json"
        assert h.data_codec == "arrow"
        assert h.strategy_codec == "cloudpickle"
        assert h.encoding == "json"
        assert h.priority == 0
        assert h.timeout == 3600
        assert h.protocol_version == "1.0"

    def test_headers_roundtrip(self):
        from stockstat._core.protocol import Headers
        h = Headers(
            content_type="application/vnd.apache.arrow.file",
            data_codec="parquet",
            strategy_codec="json",
            encoding="msgpack",
            priority=-1,
            timeout=60,
            trace_id="trace-1",
            data_ref="shm://abc",
            retry_count=2,
            accepted_codecs=["arrow", "json"],
            accepted_encodings=["json", "msgpack"],
        )
        d = h.to_dict()
        restored = Headers.from_dict(d)
        assert restored.content_type == "application/vnd.apache.arrow.file"
        assert restored.data_codec == "parquet"
        assert restored.encoding == "msgpack"
        assert restored.priority == -1
        assert restored.trace_id == "trace-1"
        assert restored.data_ref == "shm://abc"
        assert restored.retry_count == 2
        assert restored.accepted_codecs == ["arrow", "json"]

    def test_headers_from_dict_handles_none(self):
        from stockstat._core.protocol import Headers
        h = Headers.from_dict(None)
        assert h.content_type == "application/json"  # defaults

    def test_headers_from_dict_partial(self):
        from stockstat._core.protocol import Headers
        h = Headers.from_dict({"trace_id": "t1", "priority": 5})
        assert h.trace_id == "t1"
        assert h.priority == 5
        # Unspecified fields use defaults
        assert h.content_type == "application/json"


# ═══════════════════════════════════════════════════════════════
# P0.3: TaskSpec three-section structure
# ═══════════════════════════════════════════════════════════════


class TestTaskSpec:
    def test_data_spec_defaults(self):
        from stockstat._core.contracts.task import DataSpec
        ds = DataSpec(symbols=["BTC/USDT"])
        assert ds.symbols == ["BTC/USDT"]
        assert ds.timeframe == "1d"
        assert ds.start is None
        assert ds.source is None

    def test_data_spec_roundtrip(self):
        from stockstat._core.contracts.task import DataSpec
        ds = DataSpec(
            symbols=["BTC/USDT", "ETH/USDT"],
            timeframe="1h",
            start="2024-01-01",
            end="2024-12-31",
            source="binance",
        )
        d = ds.to_dict()
        assert d["symbols"] == ["BTC/USDT", "ETH/USDT"]
        assert d["timeframe"] == "1h"

        restored = DataSpec.from_dict(d)
        assert restored.symbols == ds.symbols
        assert restored.timeframe == "1h"
        assert restored.start == "2024-01-01"
        assert restored.source == "binance"

    def test_data_spec_cache_key_stable(self):
        """Same DataSpec must produce same cache key (for Dispatcher data cache)."""
        from stockstat._core.contracts.task import DataSpec
        ds1 = DataSpec(symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01")
        ds2 = DataSpec(symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01")
        ds3 = DataSpec(symbols=["BTC/USDT"], timeframe="1d", start="2024-02-01")
        assert ds1.cache_key() == ds2.cache_key()
        assert ds1.cache_key() != ds3.cache_key()

    def test_dispatch_spec_defaults(self):
        from stockstat._core.contracts.task import DispatchSpec
        ds = DispatchSpec()
        assert ds.split_strategy == "auto"
        assert ds.data_dispatch == "auto"
        assert ds.priority == 0
        assert ds.timeout == 3600
        assert ds.preemptable is False
        assert ds.retry_count == 0

    def test_dispatch_spec_roundtrip(self):
        from stockstat._core.contracts.task import DispatchSpec
        ds = DispatchSpec(
            split_strategy="param_wise",
            max_workers=8,
            data_dispatch="shared_memory",
            priority=-1,
            timeout=60,
            preemptable=True,
        )
        restored = DispatchSpec.from_dict(ds.to_dict())
        assert restored.split_strategy == "param_wise"
        assert restored.max_workers == 8
        assert restored.data_dispatch == "shared_memory"
        assert restored.priority == -1
        assert restored.preemptable is True

    def test_compute_spec_defaults(self):
        from stockstat._core.contracts.task import ComputeSpec
        cs = ComputeSpec(task_type="backtest")
        assert cs.task_type == "backtest"
        assert cs.initial_cash == 1_000_000.0
        assert cs.metric == "sharpe"
        assert cs.maximize is True
        assert cs.trade_on == "open"
        assert cs.allow_short is False
        assert cs.n_simulations == 1000

    def test_compute_spec_roundtrip(self):
        from stockstat._core.contracts.task import ComputeSpec
        cs = ComputeSpec(
            task_type="grid_search",
            strategy_ref="cloudpickle:abc123",
            param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
            metric="sharpe",
            initial_cash=10000,
            cost_model="binance_spot",
            allow_short=True,
        )
        restored = ComputeSpec.from_dict(cs.to_dict())
        assert restored.task_type == "grid_search"
        assert restored.strategy_ref == "cloudpickle:abc123"
        assert restored.param_grid["short"] == [3, 5, 8]
        assert restored.initial_cash == 10000
        assert restored.cost_model == "binance_spot"
        assert restored.allow_short is True

    def test_task_spec_three_sections(self):
        """V2 §12.5: TaskSpec must have data_spec, compute_spec, dispatch_spec."""
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(task_type="backtest", initial_cash=10000),
            dispatch_spec=DispatchSpec(timeout=60),
        )
        d = spec.to_dict()
        assert "data_spec" in d
        assert "compute_spec" in d
        assert "dispatch_spec" in d
        assert d["data_spec"]["symbols"] == ["BTC/USDT"]
        assert d["compute_spec"]["task_type"] == "backtest"
        assert d["dispatch_spec"]["timeout"] == 60

    def test_task_spec_roundtrip(self):
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec,
        )
        spec = TaskSpec(
            task_id="t-001",
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1h",
                               start="2024-01-01", end="2024-06-30"),
            compute_spec=ComputeSpec(
                task_type="grid_search",
                strategy_ref="cloudpickle:xyz",
                param_grid={"short": [3, 5], "long": [10, 20]},
                metric="sharpe",
                initial_cash=5000,
            ),
            dispatch_spec=DispatchSpec(
                split_strategy="param_wise",
                max_workers=4,
                priority=-1,
            ),
            trace_id="trace-001",
            created_by="client-A",
        )
        d = spec.to_dict()
        restored = TaskSpec.from_dict(d)

        assert restored.task_id == "t-001"
        assert restored.data_spec.symbols == ["BTC/USDT"]
        assert restored.data_spec.timeframe == "1h"
        assert restored.compute_spec.task_type == "grid_search"
        assert restored.compute_spec.param_grid["short"] == [3, 5]
        assert restored.compute_spec.initial_cash == 5000
        assert restored.dispatch_spec.split_strategy == "param_wise"
        assert restored.dispatch_spec.max_workers == 4
        assert restored.dispatch_spec.priority == -1
        assert restored.trace_id == "trace-001"
        assert restored.created_by == "client-A"

    def test_new_task_id_generates_uuid(self):
        from stockstat._core.contracts.task import new_task_id
        tid = new_task_id()
        # UUID v4 format: 8-4-4-4-12 hex chars
        assert len(tid) == 36
        parts = tid.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8


# ═══════════════════════════════════════════════════════════════
# P0.4: TaskInfo / TaskState
# ═══════════════════════════════════════════════════════════════


class TestTaskInfo:
    def test_task_state_string_enum(self):
        """TaskState values must be stable strings for protocol serialization."""
        from stockstat._core.contracts.compute import TaskState
        assert TaskState.PENDING.value == "pending"
        assert TaskState.RUNNING.value == "running"
        assert TaskState.COMPLETED.value == "completed"
        assert TaskState.FAILED.value == "failed"
        assert TaskState.CANCELLED.value == "cancelled"

    def test_task_state_str_comparison(self):
        from stockstat._core.contracts.compute import TaskState
        assert TaskState.PENDING == "pending"
        assert TaskState.RUNNING == "running"

    def test_task_info_defaults(self):
        from stockstat._core.contracts.compute import TaskInfo, TaskState
        info = TaskInfo(task_id="t1")
        assert info.task_id == "t1"
        assert info.state == TaskState.PENDING
        assert info.progress == 0.0
        assert info.error is None
        assert info.retry_count == 0

    def test_task_info_to_dict_roundtrip(self):
        from datetime import datetime
        from stockstat._core.contracts.compute import TaskInfo, TaskState
        info = TaskInfo(
            task_id="t-1",
            state=TaskState.RUNNING,
            progress=0.5,
            started_at=datetime(2026, 7, 19, 10, 30, 0),
            worker_id="worker-01",
            slice_id="slice-3",
            retry_count=1,
        )
        d = info.to_dict()
        assert d["task_id"] == "t-1"
        assert d["state"] == "running"
        assert d["progress"] == 0.5
        assert d["worker_id"] == "worker-01"
        assert d["slice_id"] == "slice-3"

        restored = TaskInfo.from_dict(d)
        assert restored.task_id == "t-1"
        assert restored.state == TaskState.RUNNING
        assert restored.progress == 0.5
        assert restored.worker_id == "worker-01"

    def test_task_info_from_dict_invalid_state_falls_back(self):
        from stockstat._core.contracts.compute import TaskInfo, TaskState
        info = TaskInfo.from_dict({
            "task_id": "t-1",
            "state": "unknown_state",
        })
        assert info.state == TaskState.PENDING  # safe fallback


# ═══════════════════════════════════════════════════════════════
# P0.5: ComputeBackend / TaskRef protocol
# ═══════════════════════════════════════════════════════════════


class TestComputeBackendProtocol:
    def test_compute_backend_is_protocol(self):
        from stockstat._core.contracts.compute import ComputeBackend
        # runtime_checkable Protocol — any object with the right methods satisfies it
        assert hasattr(ComputeBackend, "_is_protocol")

    def test_task_ref_basic_api(self):
        """TaskRef must expose id/state/status/ready/wait/result/cancel/stream_results."""
        from stockstat._core.contracts.compute import TaskRef
        # TaskRef needs a backend; we use a minimal stub
        class StubBackend:
            name = "stub"
            def get(self, tid):
                from stockstat._core.contracts.compute import TaskInfo, TaskState
                return TaskInfo(task_id=tid, state=TaskState.COMPLETED)
            def wait(self, tid, timeout=None):
                return {"result": "ok"}
            def result(self, tid):
                return {"result": "ok"}
            def cancel(self, tid):
                return True
            def stream_results(self, tid):
                yield {"partial": True}
                yield {"final": True}

        ref = TaskRef(task_id="t1", backend=StubBackend())
        assert ref.id == "t1"
        assert ref.status == "completed"
        assert ref.state.value == "completed"
        assert ref.ready() is True
        assert ref.wait() == {"result": "ok"}
        assert ref.result() == {"result": "ok"}
        assert ref.cancel() is True

        parts = list(ref.stream_results())
        assert len(parts) == 2
        assert parts[0] == {"partial": True}
        assert parts[1] == {"final": True}


# ═══════════════════════════════════════════════════════════════
# P0.6: Codec extensions (Cloudpickle / Msgpack / Raw)
# ═══════════════════════════════════════════════════════════════


class TestCodecExtensions:
    def test_available_codecs_includes_v3(self):
        from stockstat._core.codec import available_codecs
        names = available_codecs()
        assert "cloudpickle" in names
        assert "msgpack" in names
        assert "raw" in names
        # v2 codecs still present
        assert "json" in names
        assert "arrow" in names
        assert "parquet" in names
        assert "csv" in names

    def test_cloudpickle_codec_roundtrip(self):
        """CloudpickleCodec must serialize closures (the whole point)."""
        from stockstat._core.codec import CloudpickleCodec
        try:
            import cloudpickle  # noqa: F401
        except ImportError:
            pytest.skip("cloudpickle not installed")

        codec = CloudpickleCodec()
        # A closure capturing local state — JSON cannot represent this
        def make_adder(n):
            def add(x):
                return x + n
            return add

        fn = make_adder(42)
        raw = codec.encode(fn)
        assert isinstance(raw, bytes)

        restored = codec.decode(raw)
        assert restored(8) == 50  # 42 + 8

    def test_cloudpickle_codec_strategy_object(self):
        """CloudpickleCodec must serialize user strategy objects."""
        from stockstat._core.codec import CloudpickleCodec
        try:
            import cloudpickle  # noqa: F401
        except ImportError:
            pytest.skip("cloudpickle not installed")

        codec = CloudpickleCodec()

        class MyStrategy:
            def __init__(self, window):
                self.window = window
            def decide(self, x):
                return x > self.window

        s = MyStrategy(20)
        raw = codec.encode(s)
        restored = codec.decode(raw)
        assert restored.window == 20
        assert restored.decide(25) is True
        assert restored.decide(15) is False

    def test_msgpack_codec_roundtrip(self):
        from stockstat._core.codec import MsgpackCodec
        try:
            import msgpack  # noqa: F401
        except ImportError:
            pytest.skip("msgpack not installed")

        codec = MsgpackCodec()
        data = {"task_id": "t1", "progress": 0.5, "active": 3, "items": [1, 2, 3]}
        raw = codec.encode(data)
        assert isinstance(raw, bytes)

        restored = codec.decode(raw)
        assert restored["task_id"] == "t1"
        assert restored["progress"] == 0.5
        assert restored["items"] == [1, 2, 3]

    def test_raw_codec_bytes_passthrough(self):
        from stockstat._core.codec import RawCodec
        codec = RawCodec()
        assert codec.encode(b"hello") == b"hello"
        assert codec.decode(b"hello") == b"hello"

    def test_raw_codec_rejects_complex_types(self):
        from stockstat._core.codec import RawCodec
        codec = RawCodec()
        with pytest.raises(TypeError):
            codec.encode({"a": 1})

    def test_get_codec_for_content_type(self):
        from stockstat._core.codec import (
            get_codec_for_content_type,
            JsonCodec, ArrowCodec, ParquetCodec,
            CloudpickleCodec, MsgpackCodec, RawCodec,
        )
        assert isinstance(get_codec_for_content_type("application/json"), JsonCodec)
        assert isinstance(
            get_codec_for_content_type("application/vnd.apache.arrow.file"),
            ArrowCodec,
        )
        assert isinstance(
            get_codec_for_content_type("application/vnd.apache.parquet"),
            ParquetCodec,
        )
        assert isinstance(
            get_codec_for_content_type("application/vnd.python.cloudpickle"),
            CloudpickleCodec,
        )
        assert isinstance(
            get_codec_for_content_type("application/msgpack"),
            MsgpackCodec,
        )
        assert isinstance(
            get_codec_for_content_type("application/octet-stream"),
            RawCodec,
        )
        # Result content types
        assert isinstance(
            get_codec_for_content_type("application/vnd.stockstat.result+arrow"),
            ArrowCodec,
        )
        assert isinstance(
            get_codec_for_content_type("application/vnd.stockstat.result+cloudpickle"),
            CloudpickleCodec,
        )


# ═══════════════════════════════════════════════════════════════
# P0.7: Message type table completeness
# ═══════════════════════════════════════════════════════════════


class TestMessageTypes:
    def test_control_plane_types_present(self):
        from stockstat._core.protocol import messages as m
        assert m.TASK_SUBMIT == "task.submit"
        assert m.TASK_ACK == "task.ack"
        assert m.TASK_STATUS == "task.status"
        assert m.TASK_RESULT == "task.result"
        assert m.TASK_CANCEL == "task.cancel"
        assert m.TASK_PROGRESS == "task.progress"
        assert m.TASK_ERROR == "task.error"
        assert m.CLUSTER_INFO == "cluster.info"
        assert m.CLUSTER_INFO_REPLY == "cluster.info.reply"

    def test_dispatch_plane_types_present(self):
        from stockstat._core.protocol import messages as m
        assert m.DISPATCH_ASSIGN == "dispatch.assign"
        assert m.DISPATCH_COMPLETE == "dispatch.complete"
        assert m.DISPATCH_PARTIAL == "dispatch.partial"
        assert m.DISPATCH_FAIL == "dispatch.fail"
        assert m.DISPATCH_HEARTBEAT == "dispatch.heartbeat"
        assert m.DISPATCH_REGISTER == "dispatch.register"
        assert m.DISPATCH_UNREGISTER == "dispatch.unregister"
        assert m.DISPATCH_DRAIN == "dispatch.drain"
        assert m.DISPATCH_PREEMPT == "dispatch.preempt"
        assert m.DISPATCH_RESUME == "dispatch.resume"

    def test_data_plane_types_present(self):
        from stockstat._core.protocol import messages as m
        assert m.DATA_FETCH == "data.fetch"
        assert m.DATA_STREAM == "data.stream"
        assert m.DATA_REF == "data.ref"

    def test_all_types_disjoint(self):
        from stockstat._core.protocol import messages as m
        # No type should appear in multiple categories
        control = m.CONTROL_TYPES
        dispatch = m.DISPATCH_TYPES
        data = m.DATA_TYPES
        discovery = m.DISCOVERY_TYPES
        assert control & dispatch == set()
        assert control & data == set()
        assert dispatch & data == set()
        assert (control | dispatch | data | discovery) == m.ALL_TYPES

    def test_type_to_path_mapping(self):
        from stockstat._core.protocol import messages as m
        # Critical types must have HTTP path mappings for HttpTransport
        assert m.TYPE_TO_PATH[m.TASK_SUBMIT] == "/dispatch/submit"
        assert m.TYPE_TO_PATH[m.TASK_STATUS] == "/dispatch/status"
        assert m.TYPE_TO_PATH[m.TASK_RESULT] == "/dispatch/result"
        assert m.TYPE_TO_PATH[m.DISPATCH_REGISTER] == "/dispatch/register"
        assert m.TYPE_TO_PATH[m.DISPATCH_HEARTBEAT] == "/dispatch/heartbeat"

    def test_type_predicates(self):
        from stockstat._core.protocol import messages as m
        assert m.is_control(m.TASK_SUBMIT)
        assert not m.is_control(m.DISPATCH_ASSIGN)
        assert m.is_dispatch(m.DISPATCH_HEARTBEAT)
        assert m.is_data(m.DATA_STREAM)


# ═══════════════════════════════════════════════════════════════
# P0.8: Error class hierarchy
# ═══════════════════════════════════════════════════════════════


class TestErrorHierarchy:
    def test_all_v3_errors_inherit_app_error(self):
        from stockstat._core.errors import (
            AppError, TaskError, TaskNotReadyError, TaskCancelledError,
            TaskTimeoutError, TaskNotFoundError,
            ProtocolMismatchError, TransportError,
            DispatcherUnavailableError, WorkerCapabilityError,
        )
        for cls in [TaskError, TaskNotReadyError, TaskCancelledError,
                    TaskTimeoutError, TaskNotFoundError,
                    ProtocolMismatchError, TransportError,
                    DispatcherUnavailableError, WorkerCapabilityError]:
            assert issubclass(cls, AppError)

    def test_error_codes_distinct(self):
        from stockstat._core.errors import (
            TaskError, TaskNotReadyError, TaskCancelledError,
            TaskTimeoutError, TaskNotFoundError,
            ProtocolMismatchError, TransportError,
            DispatcherUnavailableError, WorkerCapabilityError,
        )
        codes = [
            TaskError.code, TaskNotReadyError.code, TaskCancelledError.code,
            TaskTimeoutError.code, TaskNotFoundError.code,
            ProtocolMismatchError.code, TransportError.code,
            DispatcherUnavailableError.code, WorkerCapabilityError.code,
        ]
        assert len(set(codes)) == len(codes), f"Duplicate codes: {codes}"

    def test_error_to_dict(self):
        from stockstat._core.errors import TaskError
        err = TaskError("compute failed", context={"task_id": "t1", "worker_id": "w1"})
        d = err.to_dict()
        assert d["code"] == "TASK_FAILED"
        assert d["message"] == "compute failed"
        assert d["context"]["task_id"] == "t1"

    def test_recoverable_flags(self):
        from stockstat._core.errors import (
            TaskError, TaskNotReadyError, TaskCancelledError,
            TaskTimeoutError, TransportError,
        )
        # TaskNotReadyError, TaskTimeoutError, TransportError should be recoverable
        assert TaskNotReadyError.recoverable is True
        assert TaskTimeoutError.recoverable is True
        assert TransportError.recoverable is True
        # TaskError, TaskCancelledError are typically not recoverable
        assert TaskError.recoverable is False
        assert TaskCancelledError.recoverable is False


# ═══════════════════════════════════════════════════════════════
# P0.9: Transport protocol
# ═══════════════════════════════════════════════════════════════


class TestTransportProtocol:
    def test_transport_is_protocol(self):
        from stockstat._core.contracts.transport import Transport
        assert hasattr(Transport, "_is_protocol")

    def test_transport_protocol_methods(self):
        """Transport must declare send/receive/request/send_data/close."""
        from stockstat._core.contracts.transport import Transport
        # Protocol members (methods) — checking via __protocol_attrs__
        # A simpler check: a stub class satisfies it
        class Stub:
            name = "stub"
            def send(self, env): pass
            def receive(self, timeout=None): pass
            def request(self, env, timeout=None): pass
            def send_data(self, data, ct): return "inline:abc"
            def close(self): pass

        assert isinstance(Stub(), Transport)


# ═══════════════════════════════════════════════════════════════
# P0.10: Cross-module integration — Envelope wrapping TaskSpec
# ═══════════════════════════════════════════════════════════════


class TestEnvelopeTaskSpecIntegration:
    def test_task_submit_envelope_carries_taskspec(self):
        """A task.submit Envelope's payload should be a TaskSpec dict."""
        from stockstat._core.protocol import Envelope, Headers, messages
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        from stockstat._core.protocol.messages import CT_TASK_JSON

        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(task_type="backtest", initial_cash=10000),
            dispatch_spec=DispatchSpec(timeout=60),
            trace_id="trace-001",
        )
        env = Envelope(
            type=messages.TASK_SUBMIT,
            headers=Headers(
                content_type=CT_TASK_JSON,
                trace_id=spec.trace_id,
                timeout=60,
            ),
            payload=spec.to_dict(),
        )
        raw = env.encode()
        restored_env = Envelope.decode(raw)
        assert restored_env.type == "task.submit"
        assert restored_env.headers.trace_id == "trace-001"

        restored_spec = TaskSpec.from_dict(restored_env.payload)
        assert restored_spec.task_id == spec.task_id
        assert restored_spec.data_spec.symbols == ["BTC/USDT"]
        assert restored_spec.compute_spec.task_type == "backtest"
        assert restored_spec.compute_spec.initial_cash == 10000
        assert restored_spec.dispatch_spec.timeout == 60

    def test_dispatch_complete_envelope_with_bytes_payload(self):
        """A dispatch.complete Envelope can carry Arrow bytes as payload."""
        from stockstat._core.protocol import Envelope, Headers, messages
        from stockstat._core.protocol.messages import CT_ARROW

        # Simulate Arrow-encoded result bytes
        result_bytes = b"ARROW\x00\x01\x02\x03\xff"
        env = Envelope(
            type=messages.DISPATCH_COMPLETE,
            headers=Headers(content_type=CT_ARROW, trace_id="trace-002"),
            payload=result_bytes,
        )
        raw = env.encode()
        restored = Envelope.decode(raw)
        assert restored.type == "dispatch.complete"
        assert restored.headers.content_type == CT_ARROW
        assert restored.payload == result_bytes
