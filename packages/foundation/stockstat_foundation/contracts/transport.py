"""Transport Protocol — 传输层抽象。"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocol.envelope import Envelope


@runtime_checkable
class Transport(Protocol):
    """传输层抽象 — 消息如何从 A 到 B。"""
    name: str

    def send(self, envelope: "Envelope") -> None: ...
    def receive(self, timeout: Optional[float] = None) -> "Envelope": ...
    def request(self, envelope: "Envelope", timeout: Optional[float] = None) -> "Envelope": ...
    def reply(self, original: "Envelope", reply: "Envelope") -> None: ...
    def send_data(self, data: bytes, content_type: str) -> str: ...
    def fetch_data(self, data_ref: str) -> bytes: ...
    def close(self) -> None: ...


__all__ = ["Transport"]
