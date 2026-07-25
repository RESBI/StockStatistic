"""ChartSpec — 声明式图表规范。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChartSpec:
    """声明式图表规范。"""
    title: str
    chart_type: str = "line"  # line / bar / scatter / heatmap / candlestick
    data: Any = None
    params: dict = field(default_factory=dict)
    theme: str = "default"


__all__ = ["ChartSpec"]
