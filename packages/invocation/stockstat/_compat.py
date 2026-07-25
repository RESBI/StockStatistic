"""_compat — V2 旧 API 迁移辅助。"""
from __future__ import annotations

from typing import Any, Optional

from stockstat_foundation import cloudpickle_dumps

from .client import StockStatClient


def grid_search(data, strategy, param_grid: dict, metric: str = "sharpe",
                maximize: bool = True, **kwargs) -> Any:
    """V2 兼容包装 — 内部提交 grid_search task。"""
    client = StockStatClient()
    return client.grid_search(data, strategy, param_grid,
                               metric=metric, maximize=maximize, **kwargs)


def batch_backtest(data, strategies: dict, fee_models: list = None, **kwargs) -> Any:
    """V2 兼容包装 — 内部提交 batch_backtest task。"""
    client = StockStatClient()
    return client.batch_backtest(data, strategies, fee_models, **kwargs)


def BacktestEngine(data, strategy, **kwargs):
    """V2 兼容 — 直接用 Compute 模块的 BacktestEngine。"""
    from stockstat_compute import BacktestEngine as _BE
    return _BE(data, strategy, **kwargs)


def ComputeEngine():
    """V2 兼容 — 直接用 Compute 模块的 ComputeEngine。"""
    from stockstat_compute import ComputeEngine as _CE
    return _CE()


__all__ = ["grid_search", "batch_backtest", "BacktestEngine", "ComputeEngine"]
