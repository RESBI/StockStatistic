"""Transport layer implementations — V3 §7.

- InProcessTransport (P1): in-process queues, zero serialization
- HttpTransport (P3): REST + JSON, default cross-machine
- SharedMemoryTransport (P4): same-host zero-copy (basic)
"""
from .in_process import InProcessTransport, make_pair
from .http import HttpTransport

# SharedMemoryTransport is optional (P4) — import lazily
try:
    from .shared_memory import SharedMemoryTransport
except ImportError:
    SharedMemoryTransport = None

__all__ = [
    "InProcessTransport", "make_pair",
    "HttpTransport",
    "SharedMemoryTransport",
]
