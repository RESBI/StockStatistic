"""ComputeBackend 实现 — Local / Remote / Auto。"""
from __future__ import annotations

from .local import LocalComputeBackend
from .remote import RemoteComputeBackend
from .auto import AutoComputeBackend

__all__ = ["LocalComputeBackend", "RemoteComputeBackend", "AutoComputeBackend"]
