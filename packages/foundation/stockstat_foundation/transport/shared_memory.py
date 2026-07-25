"""SharedMemoryTransport — 同机零拷贝（mmap）。"""
from __future__ import annotations

import base64
import os
import threading
import uuid
from typing import Optional

from ..protocol.envelope import Envelope


SMALL_DATA_THRESHOLD = 10 * 1024 * 1024  # 10 MB


class SharedMemoryTransport:
    """同机零拷贝 — 控制面走 underlying，数据面走 mmap。"""
    name = "shared_memory"

    def __init__(self, underlying=None, *, inline_threshold: int = SMALL_DATA_THRESHOLD):
        if underlying is not None:
            self._underlying = underlying
        else:
            from .in_process import InProcessTransport
            self._underlying = InProcessTransport()
        self._inline_threshold = inline_threshold
        self._shm_registry: dict = {}
        self._closed = False

    def send(self, envelope: Envelope) -> None:
        self._underlying.send(envelope)

    def receive(self, timeout: Optional[float] = None) -> Optional[Envelope]:
        return self._underlying.receive(timeout=timeout)

    def request(self, envelope: Envelope, timeout: Optional[float] = None) -> Envelope:
        return self._underlying.request(envelope, timeout=timeout)

    def reply(self, original: Envelope, reply: Envelope) -> None:
        self._underlying.reply(original, reply)

    def send_data(self, data: bytes, content_type: str) -> str:
        if len(data) < self._inline_threshold:
            return f"inline:{base64.b64encode(data).decode('ascii')}"
        try:
            from multiprocessing import shared_memory
            shm_name = f"ss_{uuid.uuid4().hex[:16]}"
            try:
                shm = shared_memory.SharedMemory(
                    name=shm_name, create=True, size=len(data)
                )
            except FileExistsError:
                shm_name = f"ss_{uuid.uuid4().hex[:16]}"
                shm = shared_memory.SharedMemory(
                    name=shm_name, create=True, size=len(data)
                )
            shm.buf[:len(data)] = data
            self._shm_registry[shm_name] = (shm, len(data))
            return f"shm://{shm_name}:{len(data)}"
        except Exception:
            return f"inline:{base64.b64encode(data).decode('ascii')}"

    def fetch_data(self, data_ref: str) -> bytes:
        if data_ref.startswith("inline:"):
            return base64.b64decode(data_ref[len("inline:"):])
        if data_ref.startswith("shm://"):
            rest = data_ref[len("shm://"):]
            if ":" in rest:
                shm_name, size_str = rest.rsplit(":", 1)
                size = int(size_str)
            else:
                shm_name = rest
                size = None
            if shm_name in self._shm_registry:
                shm, sz = self._shm_registry[shm_name]
                size = size or sz
                return bytes(shm.buf[:size])
            try:
                from multiprocessing import shared_memory
                shm = shared_memory.SharedMemory(name=shm_name)
                if size is None:
                    data = bytes(shm.buf)
                else:
                    data = bytes(shm.buf[:size])
                shm.close()
                return data
            except FileNotFoundError:
                raise ValueError(f"SharedMemory segment not found: {shm_name}")
        raise ValueError(f"Unknown data_ref: {data_ref}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for shm_name, (shm, _) in self._shm_registry.items():
            try:
                shm.close()
                shm.unlink()
            except Exception:
                pass
        self._shm_registry.clear()
        if hasattr(self._underlying, "close"):
            self._underlying.close()


__all__ = ["SharedMemoryTransport", "SMALL_DATA_THRESHOLD"]
