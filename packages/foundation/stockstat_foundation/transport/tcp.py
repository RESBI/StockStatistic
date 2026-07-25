"""TcpTransport — 高性能 LAN（预留骨架）。"""
from __future__ import annotations

import base64
import socket
import struct
from typing import Optional

from ..protocol.envelope import Envelope


class TcpTransport:
    """TCP length-prefixed binary transport（骨架，未完整实现）。"""
    name = "tcp"

    def __init__(self, url: str = "tcp://localhost:9000", *, timeout: int = 30):
        if url.startswith("tcp://"):
            url = url[len("tcp://"):]
        host, _, port = url.partition(":")
        self._host = host or "localhost"
        self._port = int(port) if port else 9000
        self._timeout = timeout
        self._sock = None
        self._closed = False

    def _ensure_socket(self):
        if self._sock is None:
            self._sock = socket.create_connection(
                (self._host, self._port), timeout=self._timeout
            )
        return self._sock

    def _send_frame(self, data: bytes) -> None:
        sock = self._ensure_socket()
        sock.sendall(struct.pack("!I", len(data)) + data)

    def _recv_frame(self) -> bytes:
        sock = self._ensure_socket()
        header = self._recv_exact(sock, 4)
        (length,) = struct.unpack("!I", header)
        return self._recv_exact(sock, length)

    @staticmethod
    def _recv_exact(sock, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by peer")
            buf.extend(chunk)
        return bytes(buf)

    def send(self, envelope: Envelope) -> None:
        self._send_frame(envelope.encode())

    def receive(self, timeout: Optional[float] = None):
        if timeout is not None:
            self._sock.settimeout(timeout)
        return Envelope.decode(self._recv_frame())

    def request(self, envelope: Envelope, timeout: Optional[float] = None) -> Envelope:
        self.send(envelope)
        return self.receive(timeout=timeout)

    def reply(self, original: Envelope, reply: Envelope) -> None:
        reply.reply_to = original.id
        self.send(reply)

    def send_data(self, data: bytes, content_type: str) -> str:
        return f"inline:{base64.b64encode(data).decode('ascii')}"

    def fetch_data(self, data_ref: str) -> bytes:
        if data_ref.startswith("inline:"):
            return base64.b64decode(data_ref[len("inline:"):])
        raise ValueError(f"Unknown data_ref: {data_ref}")

    def close(self) -> None:
        if not self._closed and self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._closed = True


__all__ = ["TcpTransport"]
