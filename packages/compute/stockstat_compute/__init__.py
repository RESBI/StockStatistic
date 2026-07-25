"""stockstat-compute — StockStat V3.1 计算端。"""
from __future__ import annotations

__version__ = "3.1.0"

from .backtest import (
    BacktestEngine, BacktestResult, BacktestMetrics, Trade,
    Strategy, StrategyBase, Signal,
    CostModel, FEE_MODELS, get_cost_model,
    FillModel, FILL_MODELS, get_fill_model,
    ExecutionModel, EXECUTION_MODELS, get_execution_model,
    Broker, Portfolio, Position,
    calculate_metrics,
    batch_backtest, grid_search,
    MonteCarloEngine, WalkForward,
)
from .compute_engine import ComputeEngine, IndicatorRegistry, register_indicator
from .indicators import (
    ma, ema, wma, dema, tema, hma, macd, adx, dpo, trix, moving_average,
    rsi, kd, williams_r, cci, stoch,
    bollinger, atr, keltner, donchian, stddev,
    rolling_corr, rolling_beta, zscore, percentile, rolling_std, rolling_mean,
    hurst_rs, sample_entropy, permutation_entropy,
)
from .handlers import (
    HANDLERS, register, dispatch, list_task_types, ALL_TASK_TYPES,
    Stream, is_stream_aware,
)
from .backend import LocalComputeBackend
from .backend.local import LocalComputeBackend as LocalBackend
from .executor import TaskExecutor
from .register import detect_hardware, get_current_load
from .checkpoint import CheckpointStore
from .worker import Worker

__all__ = [
    "__version__",
    # backtest
    "BacktestEngine", "BacktestResult", "BacktestMetrics", "Trade",
    "Strategy", "StrategyBase", "Signal",
    "CostModel", "FEE_MODELS", "get_cost_model",
    "FillModel", "FILL_MODELS", "get_fill_model",
    "ExecutionModel", "EXECUTION_MODELS", "get_execution_model",
    "Broker", "Portfolio", "Position",
    "calculate_metrics",
    "batch_backtest", "grid_search",
    "MonteCarloEngine", "WalkForward",
    # compute engine
    "ComputeEngine", "IndicatorRegistry", "register_indicator",
    # indicators
    "ma", "ema", "wma", "dema", "tema", "hma", "macd", "adx", "dpo", "trix", "moving_average",
    "rsi", "kd", "williams_r", "cci", "stoch",
    "bollinger", "atr", "keltner", "donchian", "stddev",
    "rolling_corr", "rolling_beta", "zscore", "percentile", "rolling_std", "rolling_mean",
    "hurst_rs", "sample_entropy", "permutation_entropy",
    # handlers
    "HANDLERS", "register", "dispatch", "list_task_types", "ALL_TASK_TYPES",
    "Stream", "is_stream_aware",
    # backend
    "LocalComputeBackend", "LocalBackend",
    "TaskExecutor",
    "detect_hardware", "get_current_load",
    "CheckpointStore",
    "Worker",
]
