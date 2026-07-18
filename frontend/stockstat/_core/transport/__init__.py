"""Transport layer implementations — V3 §7.

Five implementations planned (DESIGN_V3_CN §7.2):

- InProcessTransport (Phase 1): in-process queues, zero serialization
- HttpTransport (Phase 3): REST + multipart, default cross-machine
- TcpTransport (Phase 4): raw TCP for high-performance LAN
- SharedMemoryTransport (Phase 4): same-host zero-copy
- RedisTransport (Phase 5): queue-decoupled multi-worker

Phase 1 only ships InProcessTransport. Others are added in their
respective phases.
"""
from .in_process import InProcessTransport, make_pair

__all__ = ["InProcessTransport", "make_pair"]
