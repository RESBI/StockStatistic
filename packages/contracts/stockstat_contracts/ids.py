from __future__ import annotations

import secrets
import threading
import time
import uuid

_LOCK = threading.Lock()
_LAST_TIMESTAMP_MS = -1
_LAST_RANDOM = 0


def new_id() -> str:
    """Create a sortable UUIDv7-compatible identifier."""
    global _LAST_RANDOM, _LAST_TIMESTAMP_MS
    with _LOCK:
        timestamp_ms = time.time_ns() // 1_000_000
        if timestamp_ms > _LAST_TIMESTAMP_MS:
            _LAST_TIMESTAMP_MS = timestamp_ms
            _LAST_RANDOM = secrets.randbits(74)
        else:
            timestamp_ms = _LAST_TIMESTAMP_MS
            _LAST_RANDOM = (_LAST_RANDOM + 1) & ((1 << 74) - 1)
        rand_a = _LAST_RANDOM >> 62
        rand_b = _LAST_RANDOM & ((1 << 62) - 1)
    value = (timestamp_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0b10 << 62
    value |= rand_b
    return str(uuid.UUID(int=value))


def parse_id(value: str) -> str:
    parsed = uuid.UUID(value)
    if parsed.version != 7:
        raise ValueError("identifier must be UUIDv7")
    return str(parsed)
