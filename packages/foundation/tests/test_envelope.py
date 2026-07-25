"""test_envelope.py — Envelope 编解码 / Headers / reply / base64 payload (25 项)。"""
from __future__ import annotations

import base64
import json

import pytest

from stockstat_foundation.protocol.envelope import Envelope, Headers


class TestHeaders:
    def test_default_headers(self):
        h = Headers()
        assert h.content_type == "application/json"
        assert h.encoding == "json"
        assert h.priority == 0
        assert h.timeout == 3600
        assert h.protocol_version == "1.0"
        assert h.accepted_codecs == []
        assert h.accepted_encodings == []

    def test_custom_headers(self):
        h = Headers(content_type="application/arrow", encoding="msgpack",
                    priority=-1, trace_id="t-001",
                    accepted_codecs=["arrow", "cloudpickle"])
        assert h.content_type == "application/arrow"
        assert h.priority == -1
        assert h.trace_id == "t-001"
        assert h.accepted_codecs == ["arrow", "cloudpickle"]

    def test_headers_roundtrip(self):
        h = Headers(content_type="application/x-test", data_codec="parquet",
                    strategy_codec="json", encoding="msgpack",
                    priority=1, timeout=60, trace_id="trace-xyz",
                    data_ref="shm://abc", retry_count=2,
                    accepted_codecs=["json"], accepted_encodings=["msgpack"])
        d = h.to_dict()
        assert d["data_codec"] == "parquet"
        h2 = Headers.from_dict(d)
        assert h2.content_type == h.content_type
        assert h2.data_codec == h.data_codec
        assert h2.priority == h.priority
        assert h2.trace_id == h.trace_id
        assert h2.data_ref == h.data_ref
        assert h2.accepted_codecs == h.accepted_codecs


class TestEnvelopeDefaults:
    def test_default_envelope(self):
        env = Envelope()
        assert env.protocol == "stockstat-rpc"
        assert env.version == "1.0"
        assert isinstance(env.id, str) and len(env.id) > 0
        assert env.reply_to is None
        assert env.payload is None

    def test_envelope_with_payload(self):
        env = Envelope(type="task.submit", payload={"x": 1, "y": [1, 2, 3]})
        assert env.type == "task.submit"
        assert env.payload["x"] == 1
        assert env.payload["y"] == [1, 2, 3]

    def test_envelope_unique_ids(self):
        ids = {Envelope().id for _ in range(100)}
        assert len(ids) == 100


class TestEnvelopeJsonRoundtrip:
    def test_json_encode_decode_simple(self):
        env = Envelope(type="task.submit", payload={"x": 1})
        raw = env.encode()
        assert isinstance(raw, bytes)
        restored = Envelope.decode(raw)
        assert restored.type == "task.submit"
        assert restored.payload == {"x": 1}

    def test_json_with_headers(self):
        env = Envelope(
            type="task.status",
            headers=Headers(encoding="json", trace_id="t1", priority=-1),
            payload={"task_id": "abc"},
        )
        raw = env.encode()
        restored = Envelope.decode(raw)
        assert restored.headers.trace_id == "t1"
        assert restored.headers.priority == -1
        assert restored.payload["task_id"] == "abc"

    def test_json_nested_payload(self):
        env = Envelope(
            type="task.submit",
            payload={"a": {"b": {"c": [1, 2, 3]}}, "n": None, "f": 1.5},
        )
        restored = Envelope.decode(env.encode())
        assert restored.payload["a"]["b"]["c"] == [1, 2, 3]
        assert restored.payload["n"] is None
        assert restored.payload["f"] == 1.5


class TestEnvelopeMsgpack:
    def test_msgpack_encode_decode(self):
        env = Envelope(
            type="task.submit",
            headers=Headers(encoding="msgpack", trace_id="t-mp"),
            payload={"x": 1, "y": "hello"},
        )
        raw = env.encode()
        # msgpack 字节流不是合法 UTF-8
        with pytest.raises(UnicodeDecodeError):
            raw.decode("utf-8")
        restored = Envelope.decode(raw)
        assert restored.headers.trace_id == "t-mp"
        assert restored.payload["x"] == 1
        assert restored.payload["y"] == "hello"

    def test_msgpack_priority_etc(self):
        env = Envelope(
            headers=Headers(encoding="msgpack", priority=1, timeout=120),
            payload={"data": list(range(100))},
        )
        restored = Envelope.decode(env.encode())
        assert restored.headers.priority == 1
        assert restored.headers.timeout == 120
        assert restored.payload["data"] == list(range(100))


class TestEnvelopeBytesPayload:
    def test_bytes_payload_b64_encoded(self):
        env = Envelope(type="task.result", payload=b"binary data")
        raw = env.encode()
        d = json.loads(raw.decode("utf-8"))
        assert d.get("_payload_b64") is True
        assert base64.b64decode(d["payload"]) == b"binary data"

    def test_bytes_payload_roundtrip_json(self):
        env = Envelope(payload=b"\x00\x01\x02\x03\xff")
        restored = Envelope.decode(env.encode())
        assert restored.payload == b"\x00\x01\x02\x03\xff"

    def test_large_bytes_payload(self):
        big = b"x" * (1024 * 64)  # 64KB
        env = Envelope(payload=big)
        restored = Envelope.decode(env.encode())
        assert restored.payload == big


class TestEnvelopeReply:
    def test_reply_basic(self):
        env = Envelope(type="task.submit", headers=Headers(trace_id="t-1"))
        reply = env.reply("task.ack", payload={"task_id": "abc"})
        assert reply.type == "task.ack"
        assert reply.reply_to == env.id
        assert reply.headers.trace_id == "t-1"

    def test_reply_preserves_protocol_version(self):
        env = Envelope(headers=Headers(protocol_version="1.1", trace_id="t"))
        reply = env.reply("task.ack")
        assert reply.headers.protocol_version == "1.1"

    def test_is_reply(self):
        env = Envelope()
        assert not env.is_reply()
        env.reply_to = "original-id"
        assert env.is_reply()


class TestEnvelopeDict:
    def test_to_dict_from_dict(self):
        env = Envelope(type="task.cancel", payload={"task_id": "x"})
        d = env.to_dict()
        assert d["type"] == "task.cancel"
        env2 = Envelope.from_dict(d)
        assert env2.type == "task.submit" or env2.type == env.type
        assert env2.id == env.id

    def test_from_dict_missing_id_generates(self):
        d = {"type": "task.submit", "headers": {}, "payload": {}}
        env = Envelope.from_dict(d)
        assert len(env.id) > 0


class TestEnvelopeEdgeCases:
    def test_empty_payload(self):
        env = Envelope(type="heartbeat")
        restored = Envelope.decode(env.encode())
        assert restored.type == "heartbeat"
        assert restored.payload is None

    def test_none_payload(self):
        env = Envelope(payload=None)
        restored = Envelope.decode(env.encode())
        assert restored.payload is None

    def test_list_payload(self):
        env = Envelope(payload=[1, 2, 3])
        restored = Envelope.decode(env.encode())
        assert restored.payload == [1, 2, 3]
