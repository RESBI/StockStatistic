"""charts — 回测图表（空实现，避免 matplotlib 硬依赖）。"""
from __future__ import annotations


class NullChart:
    """空图表 — 默认实现。"""
    name = "null"

    def render(self, *args, **kwargs):
        return b""


__all__ = ["NullChart"]
