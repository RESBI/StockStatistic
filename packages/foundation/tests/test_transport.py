"""test_transport.py — InProcess / HTTP / SHM / Redis / build_transport (35 项)。"""
from __future__ import annotations

import threading
import time

import pytest

from stockstat_foundation.transport import (
    InProcessTransport, make_pair,
    HttpTransport, SharedMemoryTransport, RedisTransport, TcpTransport,
    build_transport,
)
from stockstat_foundation.protocol.envelope import Envelope, Headers


class TestInProcessTransport:
    def test_make_pair_wired(self):
        a, b = make_pair()
        assert a._peer is b
        assert b._peer is a

    def test_send_receive(self):
        a, b = make_pair()
        env = Envelope(type="task.submit", payload={"x": 1})
        a.send(env)
        received = b.receive(timeout=1.0)
        assert received is not None
        assert received.type == "task.submit"
        assert received.payload == {"x": 1}

    def test_send_no_reply_to_goes_to_inbox(self):
        a, b = make_pair()
        a.send(Envelope(type="task.submit"))
        assert b.receive(timeout=0.5) is not None

    def test_request_response(self):
        a, b = make_pair()

        def responder():
            env = b.receive(timeout=2.0)
            assert env is not None
            b.reply(env, Envelope(type="task.ack", payload={"task_id": "t1"}))

        t = threading.Thread(target=responder, daemon=True)
        t.start()
        reply = a.request(Envelope(type="task.submit", payload={}), timeout=2.0)
        assert reply.type == "task.ack"
        assert reply.payload["task_id"] == "t1"
        t.join(timeout=2.0)

    def test_request_timeout(self):
        a, b = make_pair()
        with pytest.raises(TimeoutError):
            a.request(Envelope(type="task.submit"), timeout=0.1)

    def test_send_data_inline(self):
        a, _ = make_pair()
        ref = a.send_data(b"hello", "application/octet-stream")
        assert ref.startswith("inline:")
        assert a.fetch_data(ref) == b"hello"

    def test_send_large_data_inline(self):
        a, _ = make_pair()
        big = b"x" * (5 * 1024 * 1024)  # 5MB
        ref = a.send_data(big, "application/octet-stream")
        assert a.fetch_data(ref) == big

    def test_close(self):
        a, b = make_pair()
        a.close()
        b.close()

    def test_unwired_send_raises(self):
        t = InProcessTransport()
        with pytest.raises(RuntimeError):
            t.send(Envelope(type="x"))

    def test_receive_empty_returns_none(self):
        a, _ = make_pair()
        assert a.receive(timeout=0.05) is None

    def test_encode_envelopes_mode(self):
        a, b = make_pair(encode_envelopes=True)
        env = Envelope(type="task.submit", payload={"x": 1})
        a.send(env)
        received = b.receive(timeout=1.0)
        assert received.payload == {"x": 1}
        # 编码后 id 应保持
        assert received.id == env.id


class TestSharedMemoryTransport:
    def test_small_data_uses_inline(self):
        t = SharedMemoryTransport()
        ref = t.send_data(b"small", "application/octet-stream")
        assert ref.startswith("inline:")
        assert t.fetch_data(ref) == b"small"

    def test_large_data_uses_shm(self):
        t = SharedMemoryTransport(inline_threshold=1024)
        big = b"x" * (100 * 1024)  # 100KB > 1KB threshold
        ref = t.send_data(big, "application/octet-stream")
        assert ref.startswith("shm://")
        assert t.fetch_data(ref) == big

    def test_shm_20mb(self):
        t = SharedMemoryTransport(inline_threshold=1024)
        big = b"y" * (20 * 1024 * 1024)  # 20MB
        ref = t.send_data(big, "application/octet-stream")
        assert ref.startswith("shm://")
        data = t.fetch_data(ref)
        assert len(data) == 20 * 1024 * 1024
        assert data == big

    def test_shm_multiple_segments(self):
        t = SharedMemoryTransport(inline_threshold=10)
        refs = []
        for i in range(5):
            refs.append(t.send_data(bytes([i]) * 1024, "application/octet-stream"))
        for i, ref in enumerate(refs):
            data = t.fetch_data(ref)
            assert data[0] == i
            assert len(data) == 1024

    def test_shm_unlink_on_close(self):
        t = SharedMemoryTransport(inline_threshold=10)
        ref = t.send_data(b"x" * 1024, "application/octet-stream")
        t.close()
        # 关闭后 fetch_data 跨进程 attach 也不应再找到
        with pytest.raises(ValueError):
            t.fetch_data(ref)

    def test_inline_threshold_boundary(self):
        t = SharedMemoryTransport(inline_threshold=100)
        ref = t.send_data(b"a" * 50, "application/octet-stream")
        assert ref.startswith("inline:")
        ref2 = t.send_data(b"b" * 200, "application/octet-stream")
        assert ref2.startswith("shm://")

    def test_send_envelope_via_underlying(self):
        from stockstat_foundation.transport.in_process import InProcessTransport
        a_under = InProcessTransport()
        b_under = InProcessTransport()
        a_under.wire_to(b_under)
        b_under.wire_to(a_under)
        a = SharedMemoryTransport(underlying=a_under)
        b = SharedMemoryTransport(underlying=b_under)
        a.send(Envelope(type="task.submit", payload={"x": 1}))
        env = b.receive(timeout=1.0)
        assert env.payload == {"x": 1}


class TestHttpTransport:
    def test_construction(self):
        t = HttpTransport("http://localhost:8000/")
        assert t._base_url == "http://localhost:8000"
        t.close()

    def test_send_data_inline(self):
        t = HttpTransport("http://localhost:8000")
        ref = t.send_data(b"hello", "application/octet-stream")
        assert ref.startswith("inline:")
        assert t.fetch_data(ref) == b"hello"
        t.close()

    def test_post_json_get_json_methods_exist(self):
        t = HttpTransport("http://localhost:8000")
        assert callable(t.post_json)
        assert callable(t.get_json)
        assert callable(t.get_bytes)
        t.close()

    def test_with_real_server(self):
        """与真实 FastAPI 服务器的集成测试。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.post("/dispatch/submit")
        def submit(req: dict):
            return {"protocol": "stockstat-rpc", "type": "task.ack",
                    "id": "reply-id", "reply_to": None,
                    "headers": {}, "payload": {"task_id": "abc", "status": "pending"}}

        client = TestClient(app)
        t = HttpTransport("http://testserver", http_client=client)
        env = Envelope(type="task.submit", payload={"task_id": "abc"})
        reply = t.request(env, timeout=2.0)
        # FastAPI 返回 dict，被包装为 Envelope
        assert reply.payload["task_id"] == "abc"
        t.close()


class TestRedisTransportSkipped:
    """Redis 未安装时跳过。"""

    def test_redis_import_error_message(self):
        try:
            import redis  # noqa: F401
            pytest.skip("redis installed; skipping import error test")
        except ImportError:
            with pytest.raises(ImportError, match="redis"):
                RedisTransport("redis://localhost:6379/0")


class TestBuildTransport:
    def test_none_returns_in_process(self):
        t = build_transport()
        assert isinstance(t, InProcessTransport)

    def test_http_url(self):
        t = build_transport("http://localhost:8000")
        assert isinstance(t, HttpTransport)
        t.close()

    def test_https_url(self):
        t = build_transport("https://example.com")
        assert isinstance(t, HttpTransport)
        t.close()

    def test_shm_url(self):
        t = build_transport("shm://local")
        assert isinstance(t, SharedMemoryTransport)
        t.close()

    def test_redis_url(self):
        try:
            import redis  # noqa: F401
            t = build_transport("redis://localhost:6379/0")
            assert isinstance(t, RedisTransport)
            t.close()
        except ImportError:
            with pytest.raises(ImportError):
                build_transport("redis://localhost:6379/0")

    def test_tcp_url(self):
        t = build_transport("tcp://localhost:9000")
        assert isinstance(t, TcpTransport)
        t.close()

    def test_explicit_transport_passthrough(self):
        custom = InProcessTransport()
        t = build_transport(transport=custom)
        assert t is custom

    def test_in_process_explicit_type(self):
        t = build_transport(transport_type="in_process")
        assert isinstance(t, InProcessTransport)

    def test_unknown_scheme_raises(self):
        with pytest.raises(ValueError):
            build_transport("ftp://example.com")


class TestTcpTransportSkeleton:
    def test_construction(self):
        t = TcpTransport("tcp://localhost:9000")
        assert t._host == "localhost"
        assert t._port == 9000
        t.close()

    def test_send_data_inline(self):
        t = TcpTransport("tcp://localhost:9000")
        ref = t.send_data(b"hello", "application/octet-stream")
        assert ref.startswith("inline:")
        assert t.fetch_data(ref) == b"hello"
        t.close()


class TestTransportProtocol:
    def test_runtime_checkable(self):
        from stockstat_foundation import Transport
        a, b = make_pair()
        assert isinstance(a, Transport)
        assert isinstance(b, Transport)
