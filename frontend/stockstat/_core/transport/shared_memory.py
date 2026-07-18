"""SharedMemoryTransport — same-host zero-copy data transfer (V3 P4).

Uses multiprocessing.SharedMemory for large data payloads when
Dispatcher and Worker run on the same machine. Falls back to inline
base64 for small data or when SharedMemory is unavailable.
"""
from __future__ import annotations

import base64
import uuid
from typing import Optional

from ..protocol.envelope import Envelope


class SharedMemoryTransport:
    """Shared memory transport — V3 P4.

    For control-plane messages, delegates to an underlying transport
    (usually HttpTransport). For data-plane, uses SharedMemory to
    avoid serialization/copy overhead on the same host.
    """

    name = "shared_memory"

    def __init__(self, underlying=None, *, inline_threshold: int = 10 * 1024 * 1024):
        """Args:
            underlying: base transport for control plane (default: InProcess)
            inline_threshold: data < this size goes inline (bytes)
        """
        if underlying is not None:
            self._underlying = underlying
        else:
            from .in_process import InProcessTransport
            self._underlying = InProcessTransport()
        self._inline_threshold = inline_threshold
        self._shm_registry: dict[str, object] = {}

    @property
    def name(self):
        return "shared_memory"

    def send(self, envelope: Envelope) -> None:
        self._underlying.send(envelope)

    def receive(self, timeout: Optional[float] = None) -> Optional[Envelope]:
        return self._underlying.receive(timeout=timeout)

    def request(self, envelope: Envelope, timeout: Optional[float] = None) -> Envelope:
        return self._underlying.request(envelope, timeout=timeout)

    def send_data(self, data: bytes, content_type: str) -> str:
        """Send data via shared memory if large, inline if small."""
        if len(data) < self._inline_threshold:
            return f"inline:{base64.b64encode(data).decode('ascii')}"
        # Use SharedMemory for large data
        try:
            from multiprocessing import shared_memory
            shm = shared_memory.SharedMemory(
                name=f"ss_{uuid.uuid4().hex[:16]}",
                create=True, size=len(data),
            )
            shm.buf[:len(data)] = data
            self._shm_registry[shm.name] = shm
            return f"shm://{shm.name}"
        except Exception:
            # Fallback to inline
            return f"inline:{base64.b64encode(data).decode('ascii')}"

    def fetch_data(self, data_ref: str) -> bytes:
        """Fetch data by reference."""
        if data_ref.startswith("inline:"):
            return base64.b64decode(data_ref[len("inline:"):])
        if data_ref.startswith("shm://"):
            shm_name = data_ref[len("shm://"):]
            # Check local registry first (same process)
            if shm_name in self._shm_registry:
                shm = self._shm_registry[shm_name]
                return bytes(shm.buf)
            # Try to attach (same host, different process)
            try:
                from multiprocessing import shared_memory
                shm = shared_memory.SharedMemory(name=shm_name)
                data = bytes(shm.buf)
                shm.close()
                return data
            except Exception:
                raise ValueError(f"Cannot access shared memory: {shm_name}")
        raise ValueError(f"Unknown data_ref format: {data_ref}")

    def close(self) -> None:
        # Clean up shared memory segments
        for name, shm in self._shm_registry.items():
            try:
                shm.close()
                shm.unlink()
            except Exception:
                pass
        self._shm_registry.clear()
        self._underlying.close()
