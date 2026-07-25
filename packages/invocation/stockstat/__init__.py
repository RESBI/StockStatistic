"""stockstat — StockStat V3.1 用户入口。"""
from __future__ import annotations

__version__ = "3.1.0"

from .client import StockStatClient
from .compute_api import ComputeAPI
from .data_access import DataClient
from .dsl import DslEngine, DslParser
from .export import ResultSerializer
from ._viz import ChartSpec, MatplotlibRenderer, NullRenderer
from ._compat import grid_search, batch_backtest, BacktestEngine, ComputeEngine

__all__ = [
    "__version__",
    "StockStatClient",
    "ComputeAPI",
    "DataClient",
    "DslEngine", "DslParser",
    "ResultSerializer",
    "ChartSpec", "MatplotlibRenderer", "NullRenderer",
    # V2 兼容
    "grid_search", "batch_backtest", "BacktestEngine", "ComputeEngine",
]
