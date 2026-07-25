"""Timing utils — 计时 / 超时辅助。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional


class Timeout:
    """超时辅助 — 检查 deadline。"""

    def __init__(self, timeout: Optional[float] = None):
        self._deadline = None if timeout is None else time.time() + timeout

    @property
    def deadline(self) -> Optional[float]:
        return self._deadline

    def expired(self) -> bool:
        if self._deadline is None:
            return False
        return time.time() >= self._deadline

    def remaining(self) -> Optional[float]:
        if self._deadline is None:
            return None
        return max(0.0, self._deadline - time.time())

    def sleep(self, seconds: float) -> None:
        rem = self.remaining()
        if rem is None:
            time.sleep(seconds)
        else:
            time.sleep(min(seconds, rem))

    def __repr__(self) -> str:
        return f"Timeout(remaining={self.remaining()})"


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def elapsed_since(start: datetime) -> float:
    return (datetime.utcnow() - start).total_seconds()


__all__ = ["Timeout", "now_iso", "elapsed_since"]
