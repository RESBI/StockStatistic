"""Renderer Protocol — Viz 渲染器协议。"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Renderer(Protocol):
    name: str

    def render(self, spec: Any) -> bytes: ...


__all__ = ["Renderer"]
