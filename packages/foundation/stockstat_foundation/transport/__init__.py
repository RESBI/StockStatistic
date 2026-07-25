"""Transport 层 — 5 种 Transport + 工厂函数。"""
from __future__ import annotations

from typing import Optional

from .in_process import InProcessTransport, make_pair
from .http import HttpTransport
from .shared_memory import SharedMemoryTransport
from .redis import RedisTransport
from .tcp import TcpTransport


def build_transport(url: Optional[str] = None, *,
                    transport=None,
                    transport_type: str = "auto"):
    """根据 URL scheme 自动选择 Transport。"""
    if transport is not None:
        return transport
    if url is None or transport_type == "in_process":
        return InProcessTransport()
    if url.startswith("http://") or url.startswith("https://"):
        return HttpTransport(url)
    if url.startswith("shm://"):
        return SharedMemoryTransport()
    if url.startswith("redis://") or url.startswith("rediss://"):
        return RedisTransport(url)
    if url.startswith("tcp://"):
        return TcpTransport(url)
    raise ValueError(f"Unknown transport for URL: {url}")


__all__ = [
    "InProcessTransport", "make_pair",
    "HttpTransport", "SharedMemoryTransport", "RedisTransport", "TcpTransport",
    "build_transport",
]
