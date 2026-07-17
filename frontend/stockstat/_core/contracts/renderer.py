"""Renderer protocol — abstract plotting backend."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Renderer(Protocol):
    """Abstract chart renderer.

    Implementations: NullRenderer, MatplotlibRenderer, PlotlyRenderer.
    """
    name: str

    def render(self, spec: Any) -> Any: ...
    def show(self) -> None: ...
    def savefig(self, path: str) -> None: ...
    def available(self) -> bool: ...
