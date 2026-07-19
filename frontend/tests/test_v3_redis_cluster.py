"""V3 P5 Redis + MessagePack tests.

Covers DESIGN_V3_CN §13.5 (MessagePack) + P5 (Redis cluster):
- MsgpackCodec encode/decode roundtrip
- Envelope with encoding="msgpack" smaller than JSON
- Envelope msgpack <-> JSON interop (decode auto-detects)
- RedisTransport (skipped if redis not installed)
- RedisTaskQueue (skipped if redis not installed)
- Headers protocol negotiation (accepted_codecs / accepted_encodings)
- Heartbeat message size comparison: JSON vs Msgpack

These tests gracefully skip when optional dependencies (redis, msgpack)
are not installed.
"""
from __future__ import annotations

import json
import pytest


# ═══════════════════════════════════════════════════════════════
# P5.1: MsgpackCodec
# ═══════════════════════════════════════════════════════════════


def _has_msgpack():
    try:
        import msgpack  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark_msgpack = pytest.mark.skipif(
    not _has_msgpack(), reason="msgpack not installed"
)


@pytestmark_msgpack
class TestMsgpackCodec:
    def test_name_and_media_type(self):
        from stockstat._core.codec import MsgpackCodec
        c = MsgpackCodec()
        assert c.name == "msgpack"
        assert c.media_type == "application/msgpack"

    def test_encode_decode_dict(self):
        from stockstat._core.codec import MsgpackCodec
        c = MsgpackCodec()
        data = {"a": 1, "b": [1, 2, 3], "c": "hello"}
        raw = c.encode(data)
        assert isinstance(raw, bytes)
        restored = c.decode(raw)
        assert restored == data

    def test_encode_decode_nested(self):
        from stockstat._core.codec import MsgpackCodec
        c = MsgpackCodec()
        data = {
            "worker_id": "w1",
            "hardware": {"cpu": {"cores_logical": 8, "freq_mhz": 3200}},
            "labels": {"rack": "A-12"},
        }
        raw = c.encode(data)
        restored = c.decode(raw)
        assert restored == data

    def test_msgpack_smaller_than_json_for_heartbeats(self):
        """Heartbeat payloads are smaller with msgpack."""
        from stockstat._core.codec import MsgpackCodec, JsonCodec
        heartbeat = {
            "worker_id": "550e8400-e29b-41d4-a716-446655440000",
            "alias": "gpu-box-alpha",
            "timestamp": "2026-07-19T10:30:00Z",
            "load": {
                "cpu_percent": 37.5,
                "memory_used_gb": 15.2,
                "memory_available_gb": 48.8,
                "gpu_percent": [85.0],
                "gpu_memory_used_gb": [18.5],
            },
            "active_tasks": 3,
            "completed_tasks": 156,
            "failed_tasks": 2,
            "avg_task_duration_s": 12.3,
            "status": "online",
        }
        json_size = len(JsonCodec().encode(heartbeat))
        msgpack_size = len(MsgpackCodec().encode(heartbeat))
        # msgpack should be smaller (typically 10-30% for dict-heavy payloads)
        assert msgpack_size < json_size

    def test_get_codec_for_content_type(self):
        from stockstat._core.codec import get_codec_for_content_type, MsgpackCodec
        c = get_codec_for_content_type("application/msgpack")
        assert isinstance(c, MsgpackCodec)


# ═══════════════════════════════════════════════════════════════
# P5.2: Envelope with msgpack encoding
# ═══════════════════════════════════════════════════════════════


@pytestmark_msgpack
class TestEnvelopeMsgpack:
    def test_envelope_msgpack_encode_decode_roundtrip(self):
        from stockstat._core.protocol.envelope import Envelope, Headers
        env = Envelope(
            type="dispatch.heartbeat",
            headers=Headers(encoding="msgpack", trace_id="t-msgpack"),
            payload={
                "worker_id": "w1",
                "load": {"cpu_percent": 42.5},
                "active_tasks": 2,
            },
        )
        raw = env.encode()
        # msgpack bytes are binary (not UTF-8 decodable)
        with pytest.raises(UnicodeDecodeError):
            raw.decode("utf-8")

        restored = Envelope.decode(raw)
        assert restored.type == "dispatch.heartbeat"
        assert restored.headers.trace_id == "t-msgpack"
        assert restored.payload["worker_id"] == "w1"
        assert restored.payload["load"]["cpu_percent"] == 42.5

    def test_envelope_json_to_msgpack_size_comparison(self):
        """Same envelope, msgpack encoding is smaller."""
        from stockstat._core.protocol.envelope import Envelope, Headers
        payload = {
            "worker_id": "w-" + "x" * 30,
            "load": {"cpu": 50.0, "mem": 16.0, "disk": 100.0},
            "tasks": [1, 2, 3, 4, 5],
        }
        env_json = Envelope(
            type="dispatch.heartbeat",
            headers=Headers(encoding="json"),
            payload=payload,
        )
        env_msgpack = Envelope(
            type="dispatch.heartbeat",
            headers=Headers(encoding="msgpack"),
            payload=payload,
        )
        json_size = len(env_json.encode())
        msgpack_size = len(env_msgpack.encode())
        assert msgpack_size < json_size

    def test_envelope_decode_auto_detects_json(self):
        """Envelope.decode tries JSON first, then msgpack."""
        from stockstat._core.protocol.envelope import Envelope, Headers
        env = Envelope(
            type="task.submit",
            headers=Headers(encoding="json"),
            payload={"task_id": "abc"},
        )
        raw = env.encode()
        # Should decode as JSON
        restored = Envelope.decode(raw)
        assert restored.headers.encoding == "json"
        assert restored.payload["task_id"] == "abc"

    def test_envelope_decode_auto_detects_msgpack(self):
        """Envelope.decode falls back to msgpack when JSON fails."""
        from stockstat._core.protocol.envelope import Envelope, Headers
        env = Envelope(
            type="task.submit",
            headers=Headers(encoding="msgpack"),
            payload={"task_id": "xyz"},
        )
        raw = env.encode()
        # Should decode as msgpack (JSON parse will fail)
        restored = Envelope.decode(raw)
        assert restored.payload["task_id"] == "xyz"


# ═══════════════════════════════════════════════════════════════
# P5.3: Protocol negotiation
# ═══════════════════════════════════════════════════════════════


class TestProtocolNegotiation:
    def test_headers_accept_codecs_default_empty(self):
        from stockstat._core.protocol.envelope import Headers
        h = Headers()
        assert h.accepted_codecs == []
        assert h.accepted_encodings == []

    def test_headers_with_accept_codecs(self):
        from stockstat._core.protocol.envelope import Headers
        h = Headers(
            accepted_codecs=["arrow", "parquet", "json"],
            accepted_encodings=["json", "msgpack"],
        )
        d = h.to_dict()
        assert d["accepted_codecs"] == ["arrow", "parquet", "json"]
        assert d["accepted_encodings"] == ["json", "msgpack"]

        # Roundtrip
        from stockstat._core.protocol.envelope import Headers as H2
        restored = H2.from_dict(d)
        assert restored.accepted_codecs == ["arrow", "parquet", "json"]
        assert restored.accepted_encodings == ["json", "msgpack"]

    def test_headers_protocol_version_default(self):
        from stockstat._core.protocol.envelope import Headers, PROTOCOL_VERSION
        h = Headers()
        assert h.protocol_version == PROTOCOL_VERSION == "1.0"

    def test_envelope_carries_negotiation(self):
        """Envelope carries accepted_codecs for negotiation."""
        from stockstat._core.protocol.envelope import Envelope, Headers
        env = Envelope(
            type="task.submit",
            headers=Headers(
                accepted_codecs=["arrow", "cloudpickle"],
                accepted_encodings=["json", "msgpack"],
                protocol_version="1.0",
            ),
            payload={"task_id": "t1"},
        )
        d = env.to_dict()
        assert d["headers"]["accepted_codecs"] == ["arrow", "cloudpickle"]
        assert d["headers"]["protocol_version"] == "1.0"


# ═══════════════════════════════════════════════════════════════
# P5.4: RedisTransport (skipped if redis not installed)
# ═══════════════════════════════════════════════════════════════


def _has_redis():
    try:
        import redis  # noqa: F401
        return True
    except ImportError:
        return False


def _has_redis_running():
    """Check if a Redis server is running on localhost."""
    if not _has_redis():
        return False
    try:
        import redis
        r = redis.from_url("redis://localhost:6379/0", socket_timeout=0.5)
        r.ping()
        return True
    except Exception:
        return False


pytestmark_redis = pytest.mark.skipif(
    not _has_redis_running(),
    reason="redis not installed or not running",
)


@pytestmark_redis
class TestRedisTransport:
    def test_name(self):
        from stockstat._core.transport import RedisTransport
        t = RedisTransport("redis://localhost:6379/0", node_id="test-1")
        try:
            assert t.name == "redis"
        finally:
            t.close()

    def test_send_data_returns_redis_ref(self):
        from stockstat._core.transport import RedisTransport
        t = RedisTransport("redis://localhost:6379/0", node_id="test-2")
        try:
            data = b"hello redis"
            ref = t.send_data(data, "application/octet-stream")
            assert ref.startswith("redis://")
            fetched = t.fetch_data(ref)
            assert fetched == data
        finally:
            t.close()

    def test_fetch_data_invalid_ref_raises(self):
        from stockstat._core.transport import RedisTransport
        t = RedisTransport("redis://localhost:6379/0", node_id="test-3")
        try:
            with pytest.raises(ValueError):
                t.fetch_data("unknown://x")
        finally:
            t.close()


# ═══════════════════════════════════════════════════════════════
# P5.5: RedisTaskQueue (skipped if redis not installed)
# ═══════════════════════════════════════════════════════════════


@pytestmark_redis
class TestRedisTaskQueue:
    def test_enqueue_dequeue(self):
        from stockstat_backend.dispatcher.queue import RedisTaskQueue
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, new_task_id,
        )
        # Use a unique queue name to avoid collisions
        import uuid
        qname = f"test:tasks:{uuid.uuid4().hex[:8]}"
        q = RedisTaskQueue("redis://localhost:6379/0", queue_name=qname)
        try:
            spec = TaskSpec(
                task_id=new_task_id(),
                data_spec=DataSpec(symbols=[]),
                compute_spec=ComputeSpec(task_type="custom"),
            )
            q.enqueue(spec)
            assert q.size() == 1
            out = q.dequeue(block=False)
            assert out is not None
            assert out.task_id == spec.task_id
            assert q.size() == 0
        finally:
            q.clear()

    def test_priority_ordering(self):
        """Higher-priority tasks dequeue first."""
        from stockstat_backend.dispatcher.queue import RedisTaskQueue
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec, new_task_id,
        )
        import uuid
        qname = f"test:tasks:{uuid.uuid4().hex[:8]}"
        q = RedisTaskQueue("redis://localhost:6379/0", queue_name=qname)
        try:
            low = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                           compute_spec=ComputeSpec(task_type="custom"),
                           dispatch_spec=DispatchSpec(priority=1))
            high = TaskSpec(task_id=new_task_id(), data_spec=DataSpec(symbols=[]),
                            compute_spec=ComputeSpec(task_type="custom"),
                            dispatch_spec=DispatchSpec(priority=-1))
            q.enqueue(low)
            q.enqueue(high)
            # high should dequeue first
            first = q.dequeue(block=False)
            assert first.task_id == high.task_id
            second = q.dequeue(block=False)
            assert second.task_id == low.task_id
        finally:
            q.clear()

    def test_dequeue_empty_returns_none(self):
        from stockstat_backend.dispatcher.queue import RedisTaskQueue
        import uuid
        qname = f"test:tasks:{uuid.uuid4().hex[:8]}"
        q = RedisTaskQueue("redis://localhost:6379/0", queue_name=qname)
        try:
            assert q.dequeue(block=False) is None
        finally:
            q.clear()


# ═══════════════════════════════════════════════════════════════
# P5.6: build_queue factory
# ═══════════════════════════════════════════════════════════════


class TestBuildQueue:
    def test_memory_backend(self):
        from stockstat_backend.dispatcher.queue import build_queue, MemoryTaskQueue
        q = build_queue("memory")
        assert isinstance(q, MemoryTaskQueue)

    def test_redis_backend_without_url_raises(self):
        from stockstat_backend.dispatcher.queue import build_queue
        with pytest.raises(ValueError, match="redis_url"):
            build_queue("redis", redis_url=None)

    def test_unknown_backend_raises(self):
        from stockstat_backend.dispatcher.queue import build_queue
        with pytest.raises(ValueError, match="Unknown"):
            build_queue("kafka")


# ═══════════════════════════════════════════════════════════════
# P5.7: Heartbeat message size comparison (informational)
# ═══════════════════════════════════════════════════════════════


@pytestmark_msgpack
class TestHeartbeatSize:
    def test_heartbeat_msgpack_smaller_than_json(self):
        """DESIGN_V3 target: msgpack heartbeat smaller than JSON.

        For dict-heavy control-plane messages, msgpack is typically
        15-30% smaller (not the 60% claimed in early V2 estimates).
        The reduction comes mainly from:
        - No quote characters around strings
        - No whitespace/colons/commas
        - Compact binary encoding of numbers
        """
        from stockstat._core.protocol.envelope import Envelope, Headers
        heartbeat = {
            "worker_id": "550e8400-e29b-41d4-a716-446655440000",
            "alias": "gpu-box-alpha",
            "load": {
                "cpu_percent": 37.5,
                "memory_used_gb": 15.2,
                "memory_available_gb": 48.8,
            },
            "active_tasks": 3,
            "completed_tasks": 156,
            "failed_tasks": 2,
            "avg_task_duration_s": 12.3,
            "status": "online",
        }
        env_json = Envelope(
            type="dispatch.heartbeat",
            headers=Headers(encoding="json"),
            payload=heartbeat,
        )
        env_msgpack = Envelope(
            type="dispatch.heartbeat",
            headers=Headers(encoding="msgpack"),
            payload=heartbeat,
        )
        json_size = len(env_json.encode())
        msgpack_size = len(env_msgpack.encode())
        # Target: msgpack reduces size (any amount is acceptable)
        assert msgpack_size < json_size
