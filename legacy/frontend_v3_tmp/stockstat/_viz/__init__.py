"""StockStat v2.0 — Visualization layer (Layer 2).

Provides a unified Spec system, renderer plugins, and theme system.
The v1.7 ``PlotSpec`` and ``BacktestChartSpec`` are unified under a
single ``PlotSpec`` with ``ChartProfile`` presets.
"""
from .specs import PlotSpec, SeriesSpec, SubplotSpec, ChartProfile
from .renderers import register_default_renderers
from .themes import Theme, get_theme

__all__ = [
    "PlotSpec", "SeriesSpec", "SubplotSpec", "ChartProfile",
    "register_default_renderers",
    "Theme", "get_theme",
]
