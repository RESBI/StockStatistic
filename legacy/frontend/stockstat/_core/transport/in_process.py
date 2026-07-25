"""In-process transport — single-process message passing for tests.

V3 Phase 1 transport. Implements the :class:`Transport` protocol using
in-process queues, so Client / Dispatcher / Worker can all live in the
same Python process without any network or serialization overhead.

Use cases:
- Unit / integration tests (no need to spin up a Dispatcher process)
- Single-machine full-stack deployment (Scenario A in DESIGN_V3_CN §18)
- Phase 1 validation of the protocol layer before P2 introduces real
  cross-process transport

The transport supports both fire-and-forget (``send``) and
request-response (``request``) patterns. Replies are matched by the
``reply_to`` field (set to the original envelope's ``id``).

Although this transport doesn't actually need serialization (everything
is in-process), we still go through Envelope.encode/decode so that the
upper layers can switch to HttpTransport / TcpTransport unchanged.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Optional


class InProcessTransport:
    """In-process transport — V3 Phase 1.

    Messages flow through ``queue.Queue`` objects. Multiple
    InProcessTransport instances can be wired together by sharing
    queues: the Client's transport puts into the Dispatcher's receive
    queue, and the Dispatcher's transport puts into the Client's
    receive queue.

    For tests, you can create a single transport and use it for both
    sides (loopback), or create a pair and wire them together via
    :meth:`wire_to`.
    """

    name = "in_process"

    def __init__(self, *, encode_envelopes: bool = False):
        self._inbox: "queue.Queue" = queue.Queue()
        self._replies: dict[str, "queue.Queue"] = {}
        self._peer: Optional["InProcessTransport"] = None
        self._closed = False
        self._encode = encode_envelopes  # if True, round-trip through bytes

    def wire_to(self, peer: "InProcessTransport") -> None:
        """Wire this transport's send output to peer's inbox.

        Both directions must be wired for bidirectional communication:
        ``a.wire_to(b); b.wire_to(a)``.
        """
        self._peer = peer

    def send(self, envelope) -> None:
        """Fire-and-forget send to the wired peer."""
        if self._closed:
            raise RuntimeError("Transport is closed")
        target = self._peer or self  # loopback if not wired
        target._inbox.put(self._maybe_encode(envelope))

    def receive(self, timeout: Optional[float] = None):
        """Block waiting for an incoming Envelope. Returns None on timeout."""
        if self._closed:
            return None
        try:
            raw = self._inbox.get(timeout=timeout)
            return self._maybe_decode(raw)
        except queue.Empty:
            return None

    def request(self, envelope, timeout: Optional[float] = None):
        """Request-response pattern.

        Sends the envelope, then waits for a reply whose ``reply_to``
        matches the original envelope's ``id``. Raises TimeoutError if
        no reply within ``timeout`` seconds.
        """
        if self._closed:
            raise RuntimeError("Transport is closed")

        reply_q: "queue.Queue" = queue.Queue(maxsize=1)
        self._replies[envelope.id] = reply_q

        try:
            self.send(envelope)
            try:
                raw_reply = reply_q.get(timeout=timeout)
            except queue.Empty:
                raise TimeoutError(
                    f"No reply for envelope {envelope.id} within {timeout}s"
                )
            return self._maybe_decode(raw_reply)
        finally:
            self._replies.pop(envelope.id, None)

    def reply(self, original_envelope, reply_envelope) -> None:
        """Deliver a reply envelope to the original sender.

        Called by the receiver (Dispatcher / Worker) when it has
        processed a request and wants to send back a reply. The reply
        is routed to the original sender's reply queue.
        """
        reply_envelope.reply_to = original_envelope.id
        # Find the sender's reply queue
        # In the loopback case, the sender is the same transport
        target = self._peer or self
        reply_q = target._replies.get(original_envelope.id)
        if reply_q is not None:
            reply_q.put(self._maybe_encode(reply_envelope), timeout=1.0)
        else:
            # No registered request — deliver as a regular message
            target._inbox.put(self._maybe_encode(reply_envelope))

    def send_data(self, data: bytes, content_type: str) -> str:
        """Inline data as base64 — no shared memory in Phase 1."""
        import base64
        return f"inline:{base64.b64encode(data).decode('ascii')}"

    def fetch_data(self, data_ref: str) -> bytes:
        """Decode an inline data reference back to bytes."""
        if not data_ref.startswith("inline:"):
            raise ValueError(f"Unsupported data_ref: {data_ref}")
        import base64
        return base64.b64decode(data_ref[len("inline:"):])

    def close(self) -> None:
        self._closed = True
        # Drain queues
        while not self._inbox.empty():
            try:
                self._inbox.get_nowait()
            except queue.Empty:
                break

    def _maybe_encode(self, envelope):
        """Optionally serialize through bytes to validate the codec path."""
        if not self._encode:
            return envelope
        return envelope.encode()

    def _maybe_decode(self, raw):
        if not self._encode:
            return raw
        from ..protocol.envelope import Envelope
        if isinstance(raw, bytes):
            return Envelope.decode(raw)
        return raw


def make_pair(*, encode_envelopes: bool = False):
    """Create a wired pair of InProcessTransport for bidirectional use.

    Returns ``(client_transport, server_transport)``. Messages sent on
    the client transport are received on the server transport, and
    vice versa.

    Useful for tests that need both sides:
    ```
    client_t, server_t = make_pair()
    dispatcher = Dispatcher(transport=server_t)
    backend = RemoteComputeBackend(transport=client_t)
    ```
    """
    a = InProcessTransport(encode_envelopes=encode_envelopes)
    b = InProcessTransport(encode_envelopes=encode_envelopes)
    a.wire_to(b)
    b.wire_to(a)
    return a, b
