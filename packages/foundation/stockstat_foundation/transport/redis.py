"""RedisTransport — Redis 列表 + pub/sub 传输。"""
from __future__ import annotations

import base64
import threading
import time
import uuid
from typing import Optional

from ..protocol.envelope import Envelope


class RedisTransport:
    """Redis 列表 + pub/sub 传输。"""
    name = "redis"

    def __init__(self, redis_url: str, *, node_id: Optional[str] = None,
                 queue_prefix: str = "stockstat:node"):
        try:
            import redis
        except ImportError as e:
            raise ImportError(
                "RedisTransport requires 'redis'. "
                "Install with: pip install stockstat-foundation[redis]"
            ) from e
        self._r = redis.from_url(redis_url)
        self._node_id = node_id or f"node-{uuid.uuid4().hex[:8]}"
        self._my_queue = f"{queue_prefix}:{self._node_id}"
        self._queue_prefix = queue_prefix
        self._replies: dict = {}
        self._reply_events: dict = {}
        self._reply_lock = threading.Lock()
        self._closed = False
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()

    def _dispatch_loop(self):
        while not self._closed:
            try:
                result = self._r.brpop(self._my_queue, timeout=1)
                if result is None:
                    continue
                _, raw = result
                env = Envelope.decode(raw)
                if env.reply_to and env.reply_to in self._reply_events:
                    with self._reply_lock:
                        self._replies[env.reply_to] = env
                        self._reply_events[env.reply_to].set()
                else:
                    self._inbox_put(env)
            except Exception:
                time.sleep(0.1)

    def _inbox_put(self, env):
        if not hasattr(self, "_inbox"):
            import queue as q
            self._inbox = q.Queue()
        self._inbox.put(env)

    def receive(self, timeout: Optional[float] = None):
        if not hasattr(self, "_inbox"):
            import queue as q
            self._inbox = q.Queue()
        try:
            return self._inbox.get(timeout=timeout)
        except Exception:
            return None

    def send(self, envelope: Envelope) -> None:
        peer_id = envelope.reply_to or "dispatcher"
        target = f"{self._queue_prefix}:{peer_id}"
        self._r.lpush(target, envelope.encode())

    def request(self, envelope: Envelope, timeout: Optional[float] = None) -> Envelope:
        reply_id = envelope.id
        event = threading.Event()
        with self._reply_lock:
            self._reply_events[reply_id] = event
        try:
            self.send(envelope)
            if not event.wait(timeout=timeout):
                raise TimeoutError(f"Request {envelope.type} timed out")
            return self._replies.pop(reply_id)
        finally:
            with self._reply_lock:
                self._reply_events.pop(reply_id, None)
                self._replies.pop(reply_id, None)

    def reply(self, original: Envelope, reply: Envelope) -> None:
        reply.reply_to = original.id
        self.send(reply)

    def send_data(self, data: bytes, content_type: str) -> str:
        ref_id = uuid.uuid4().hex
        self._r.set(f"stockstat:data:{ref_id}", data, ex=3600)
        return f"redis://{ref_id}"

    def fetch_data(self, data_ref: str) -> bytes:
        if data_ref.startswith("inline:"):
            return base64.b64decode(data_ref[len("inline:"):])
        if data_ref.startswith("redis://"):
            ref_id = data_ref[len("redis://"):]
            data = self._r.get(f"stockstat:data:{ref_id}")
            if data is None:
                raise ValueError(f"Redis data expired or not found: {ref_id}")
            return data
        raise ValueError(f"Unknown data_ref: {data_ref}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._reply_lock:
            for ev in self._reply_events.values():
                ev.set()
            self._reply_events.clear()
            self._replies.clear()
        try:
            self._r.close()
        except Exception:
            pass


__all__ = ["RedisTransport"]
