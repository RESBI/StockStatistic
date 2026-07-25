"""BacktestEngine — 完整回测引擎（V3.1 重新实现）。"""
from __future__ import annotations

from .result import BacktestResult, BacktestMetrics, Trade, EquityPoint
from .strategy import Strategy, StrategyBase, Signal, run_strategy_func
from .cost_model import CostModel, FEE_MODELS, get_cost_model
from .fill_model import FillModel, FILL_MODELS, get_fill_model
from .execution_model import ExecutionModel, EXECUTION_MODELS, get_execution_model
from .broker import Broker
from .portfolio import Portfolio, Position
from .metrics import calculate_metrics
from .engine import BacktestEngine
from .batch_runner import batch_backtest
from .grid_search import grid_search
from .montecarlo import MonteCarloEngine
from .walkforward import WalkForward

__all__ = [
    "BacktestResult", "BacktestMetrics", "Trade", "EquityPoint",
    "Strategy", "StrategyBase", "Signal", "run_strategy_func",
    "CostModel", "FEE_MODELS", "get_cost_model",
    "FillModel", "FILL_MODELS", "get_fill_model",
    "ExecutionModel", "EXECUTION_MODELS", "get_execution_model",
    "Broker", "Portfolio", "Position",
    "calculate_metrics",
    "BacktestEngine",
    "batch_backtest", "grid_search",
    "MonteCarloEngine", "WalkForward",
]
