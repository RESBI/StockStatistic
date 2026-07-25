"""Plugin Protocol — 可挂载到 FastAPI 或独立运行。"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Plugin(Protocol):
    name: str
    version: str

    def mount(self, app: Any, **kwargs) -> None: ...
    def unmount(self, app: Any) -> None: ...


__all__ = ["Plugin"]
