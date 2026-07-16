from __future__ import annotations

import warnings
from typing import Any

from .chart_spec import BacktestChartSpec


class NullBacktestChartRenderer:
    """Zero-dependency fallback renderer.

    Emits a UserWarning on render/savefig and returns None, so the backtest
    core never hard-requires matplotlib.
    """

    def render(self, spec: BacktestChartSpec) -> Any:
        warnings.warn(
            "No backtest chart backend available. Install matplotlib via "
            "`pip install stockstat[backtest_viz]` to enable backtest charts.",
            UserWarning,
            stacklevel=2,
        )
        return None

    def show(self) -> None:
        pass

    def savefig(self, path: str) -> None:
        warnings.warn(
            "No backtest chart backend available for savefig. "
            "Install matplotlib via `pip install stockstat[backtest_viz]`.",
            UserWarning,
            stacklevel=2,
        )

    def available(self) -> bool:
        return False
