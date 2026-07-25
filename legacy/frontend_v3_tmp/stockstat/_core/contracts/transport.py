"""Transport protocol — V2 §12.7 transport layer abstraction.

Decouples "how messages move between nodes" from message format and
encoding. The same Envelope can travel over HTTP, raw TCP, shared
memory, Redis pub/sub, or in-process queues — the upper layers
(ComputeBackend / Dispatcher / Worker) are completely unaware of
which transport is in use.

Five implementations planned (V3 phases):
- InProcessTransport (P1): same-process, zero serialization — for tests
  and single-machine full-stack deployment
- HttpTransport (P3): cross-machine default, REST + multipart
- SharedMemoryTransport (P4): same-host zero-copy for large data
- TcpTransport (P4): high-performance LAN
- RedisTransport (P5): queue-decoupled multi-worker

Each implementation must satisfy this Protocol.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    """Abstract transport — how an Envelope gets from A to B.

    Implementations are responsible for:
    - Serialization (delegated to Envelope.encode/decode + Codec)
    - Connection management (HTTP keep-alive, TCP persistent, etc.)
    - Error handling (retries, timeouts)
    - Large data transfer via ``send_data`` (returns a reference ID)

    Implementations are NOT responsible for:
    - Message semantics (the Envelope's ``type`` field handles that)
    - Payload encoding (the Envelope's ``headers.content_type`` handles that)
    - Routing decisions (the caller decides where to send)
    """

    name: str

    def send(self, envelope) -> None:
        """Fire-and-forget send. Does not wait for a reply."""
        ...

    def receive(self, timeout: Optional[float] = None):
        """Block waiting for an incoming Envelope. Returns None on timeout."""
        ...

    def request(self, envelope, timeout: Optional[float] = None):
        """Request-response pattern: send envelope, wait for reply.

        The reply is matched by ``reply_to`` field (set to original
        envelope's ``id``). Raises TimeoutError if no reply within
        ``timeout`` seconds.
        """
        ...

    def send_data(self, data: bytes, content_type: str) -> str:
        """Send a large binary payload, return a reference ID.

        The reference ID (e.g. ``"shm://abc123"`` or
        ``"inline:<base64>"``) can be embedded in an Envelope's
        ``headers.data_ref`` so the receiver can fetch the data
        out-of-band.

        Small data (< 10MB) may be inlined; large data goes to shared
        memory, disk, or a content-addressed store depending on the
        transport implementation.
        """
        ...

    def close(self) -> None:
        """Release any underlying resources (sockets, shm, etc.)."""
        ...
