"""CheckpointStore — Checkpoint 存储（抢占恢复）。"""
from __future__ import annotations

import threading
from typing import Optional


class CheckpointStore:
    """Checkpoint 存储 — 进程内 dict（V3.1 可扩展为 Redis）。"""

    def __init__(self):
        self._store: dict = {}
        self._lock = threading.Lock()

    def save(self, slice_id: str, state: bytes) -> None:
        with self._lock:
            self._store[slice_id] = state

    def load(self, slice_id: str) -> Optional[bytes]:
        with self._lock:
            return self._store.get(slice_id)

    def delete(self, slice_id: str) -> None:
        with self._lock:
            self._store.pop(slice_id, None)

    def list(self) -> list:
        with self._lock:
            return list(self._store.keys())

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


__all__ = ["CheckpointStore"]
