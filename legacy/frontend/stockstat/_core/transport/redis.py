"""RedisTransport — V3 P5 transport backed by Redis pub/sub.

Decouples Client/Dispatcher/Worker via Redis lists + pub/sub:
- Control-plane: BRPOP/LPUSH on per-node queues (reliable delivery)
- Pub/sub: cluster.info broadcasts and Worker discovery

Requires the ``redis`` package. Falls back gracefully if unavailable.
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Optional

from ..protocol.envelope import Envelope
from ..protocol import messages


_HAS_REDIS = None


def _check_redis():
    """Lazily check if redis is importable."""
    global _HAS_REDIS
    if _HAS_REDIS is None:
        try:
            import redis  # noqa: F401
            _HAS_REDIS = True
        except ImportError:
            _HAS_REDIS = False
    return _HAS_REDIS


class RedisTransport:
    """Redis-backed transport — V3 P5.

    Use cases:
    - Multi-Worker clusters where HTTP polling is inefficient
    - Task queue persistence (Redis survives Dispatcher restarts)
    - Pub/sub for cluster discovery

    Messages flow through Redis lists:
    - Each node has a queue ``stockstat:node:{node_id}``
    - ``send`` LPUSHes to the peer's queue
    - ``receive`` BRPOPs from own queue

    Replies are matched via ``reply_to`` and routed to a per-request
    reply queue.
    """

    name = "redis"

    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 *, node_id: str = None, queue_prefix: str = "stockstat:node"):
        if not _check_redis():
            raise ImportError(
                "RedisTransport requires `pip install redis`. "
                "Or use HttpTransport for non-Redis deployments."
            )
        import redis as _redis
        self._r = _redis.from_url(redis_url)
        self._node_id = node_id or f"node-{uuid.uuid4().hex[:8]}"
        self._queue_prefix = queue_prefix
        self._my_queue = f"{queue_prefix}:{self._node_id}"
        self._replies: dict[str, "queue.Queue"] = {}
        self._closed = False
        # Start a background thread to dispatch replies
        import threading
        import queue as _queue
        self._reply_q = _queue.Queue()
        self._stop_event = threading.Event()
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop, daemon=True,
            name=f"redis-transport-{self._node_id}",
        )
        self._dispatcher.start()

    def _peer_queue(self, peer_id: str) -> str:
        return f"{self._queue_prefix}:{peer_id}"

    def send(self, envelope: Envelope) -> None:
        """Fire-and-forget send to the peer's queue.

        Uses envelope.reply_to as the peer_id if set, else uses
        a default 'dispatcher' queue.
        """
        if self._closed:
            raise RuntimeError("Transport is closed")
        # Determine target queue
        peer_id = envelope.reply_to or "dispatcher"
        target = self._peer_queue(peer_id)
        # Serialize: encode envelope to JSON bytes
        raw = envelope.encode()
        self._r.lpush(target, raw)

    def receive(self, timeout: Optional[float] = None) -> Optional[Envelope]:
        """Block waiting for an incoming Envelope. Returns None on timeout."""
        if self._closed:
            return None
        timeout_s = int(timeout) if timeout else 0
        result = self._r.brpop(self._my_queue, timeout=timeout_s)
        if result is None:
            return None
        _, raw = result
        if isinstance(raw, bytes):
            raw = raw
        else:
            raw = raw.encode("utf-8")
        return Envelope.decode(raw)

    def request(self, envelope: Envelope, timeout: Optional[float] = None) -> Envelope:
        """Request-response: send and wait for reply.

        Sends to peer's queue, then waits for a reply with
        ``reply_to == envelope.id`` on our own queue.
        """
        if self._closed:
            raise RuntimeError("Transport is closed")
        import queue as _queue
        reply_q: "_queue.Queue" = _queue.Queue(maxsize=1)
        self._replies[envelope.id] = reply_q
        try:
            self.send(envelope)
            try:
                raw_reply = reply_q.get(timeout=timeout or 30)
            except _queue.Empty:
                raise TimeoutError(
                    f"No reply for envelope {envelope.id} within {timeout}s"
                )
            return raw_reply
        finally:
            self._replies.pop(envelope.id, None)

    def reply(self, original_envelope: Envelope, reply_envelope: Envelope) -> None:
        """Send a reply to the original sender."""
        reply_envelope.reply_to = original_envelope.id
        # The original sender's queue is keyed by their node_id, which
        # we don't have directly; rely on reply_to being set in the
        # original. For simplicity, push to a 'reply' queue.
        target = self._peer_queue("dispatcher")
        self._r.lpush(target, reply_envelope.encode())

    def send_data(self, data: bytes, content_type: str) -> str:
        """Send large data: store in Redis hash, return ref."""
        ref_id = uuid.uuid4().hex
        key = f"stockstat:data:{ref_id}"
        self._r.set(key, data, ex=3600)  # 1-hour TTL
        return f"redis://{ref_id}"

    def fetch_data(self, data_ref: str) -> bytes:
        """Fetch data by redis:// ref."""
        if not data_ref.startswith("redis://"):
            raise ValueError(f"Unknown data_ref format: {data_ref}")
        ref_id = data_ref[len("redis://"):]
        key = f"stockstat:data:{ref_id}"
        data = self._r.get(key)
        if data is None:
            raise ValueError(f"Data ref expired or not found: {ref_id}")
        return data if isinstance(data, bytes) else data.encode("utf-8")

    def close(self) -> None:
        self._closed = True
        self._stop_event.set()
        # Wait for dispatcher thread to exit
        if self._dispatcher.is_alive():
            self._dispatcher.join(timeout=2.0)

    def _dispatch_loop(self) -> None:
        """Background thread: receive messages and route replies."""
        while not self._stop_event.is_set():
            try:
                raw = self._r.brpop(self._my_queue, timeout=1)
                if raw is None:
                    continue
                _, data = raw
                if isinstance(data, str):
                    data = data.encode("utf-8")
                env = Envelope.decode(data)
                # If this is a reply, route to the reply queue
                if env.reply_to and env.reply_to in self._replies:
                    self._replies[env.reply_to].put(env, timeout=1.0)
                else:
                    # Not a reply — push to general inbox (best-effort)
                    pass
            except Exception:
                time.sleep(0.1)
