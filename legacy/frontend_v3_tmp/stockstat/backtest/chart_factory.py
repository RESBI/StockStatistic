from __future__ import annotations

from typing import Optional


def detect() -> str:
    """Auto-detect the best available backtest chart backend."""
    try:
        import matplotlib  # noqa: F401
        return "matplotlib"
    except ImportError:
        return "null"


def get_chart_renderer(name: Optional[str] = None):
    """Return a BacktestChartRenderer instance.

    - name=None: auto-detect (matplotlib if installed, else Null)
    - name="matplotlib": force matplotlib (raises ImportError if missing)
    - name="null": force Null
    """
    if name is None:
        name = detect()
    if name == "matplotlib":
        from .matplotlib_charts import MatplotlibBacktestChartRenderer
        return MatplotlibBacktestChartRenderer()
    if name == "null":
        from .null_charts import NullBacktestChartRenderer
        return NullBacktestChartRenderer()
    raise ValueError(f"Unknown backtest chart renderer: {name}")
