"""InProcessTransport — 单进程传输（queue.Queue）。"""
from __future__ import annotations

import base64
import queue
import threading
from typing import Optional

from ..protocol.envelope import Envelope


class InProcessTransport:
    """单进程传输 — queue.Queue + reply 路由。"""
    name = "in_process"

    def __init__(self, *, encode_envelopes: bool = False):
        self._inbox: "queue.Queue[Envelope]" = queue.Queue()
        self._replies: dict = {}
        self._reply_events: dict = {}
        self._peer: Optional["InProcessTransport"] = None
        self._encode_envelopes = encode_envelopes
        self._closed = False

    def wire_to(self, peer: "InProcessTransport") -> None:
        self._peer = peer

    def send(self, envelope: Envelope) -> None:
        if self._peer is None:
            raise RuntimeError("InProcessTransport not wired to a peer")
        env = envelope
        if self._encode_envelopes:
            env = Envelope.decode(envelope.encode())
        if envelope.reply_to and envelope.reply_to in self._peer._reply_events:
            self._peer._replies[envelope.reply_to] = env
            self._peer._reply_events[envelope.reply_to].set()
        else:
            self._peer._inbox.put(env)

    def receive(self, timeout: Optional[float] = None) -> Optional[Envelope]:
        try:
            return self._inbox.get(timeout=timeout)
        except queue.Empty:
            return None

    def request(self, envelope: Envelope, timeout: Optional[float] = None) -> Envelope:
        reply_id = envelope.id
        event = threading.Event()
        self._reply_events[reply_id] = event
        try:
            self.send(envelope)
            if not event.wait(timeout=timeout):
                raise TimeoutError(f"Request {envelope.type} timed out after {timeout}s")
            return self._replies.pop(reply_id)
        finally:
            self._reply_events.pop(reply_id, None)
            self._replies.pop(reply_id, None)

    def reply(self, original: Envelope, reply_env: Envelope) -> None:
        reply_env.reply_to = original.id
        if self._peer is None:
            raise RuntimeError("InProcessTransport not wired to a peer")
        if original.id in self._peer._reply_events:
            self._peer._replies[original.id] = reply_env
            self._peer._reply_events[original.id].set()
        else:
            self._peer._inbox.put(reply_env)

    def send_data(self, data: bytes, content_type: str) -> str:
        return f"inline:{base64.b64encode(data).decode('ascii')}"

    def fetch_data(self, data_ref: str) -> bytes:
        if data_ref.startswith("inline:"):
            return base64.b64decode(data_ref[len("inline:"):])
        raise ValueError(f"Unknown data_ref for InProcessTransport: {data_ref}")

    def close(self) -> None:
        self._closed = True
        for ev in self._reply_events.values():
            ev.set()
        self._reply_events.clear()
        self._replies.clear()


def make_pair(*, encode_envelopes: bool = False):
    """创建双向绑定的传输对。"""
    a = InProcessTransport(encode_envelopes=encode_envelopes)
    b = InProcessTransport(encode_envelopes=encode_envelopes)
    a.wire_to(b)
    b.wire_to(a)
    return a, b


__all__ = ["InProcessTransport", "make_pair"]
