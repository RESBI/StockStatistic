"""_viz — 可视化层（ChartSpec + Renderer）。"""
from __future__ import annotations

from .specs import ChartSpec
from .renderers import MatplotlibRenderer, NullRenderer

__all__ = ["ChartSpec", "MatplotlibRenderer", "NullRenderer"]
