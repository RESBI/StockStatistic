"""batch_runner — 批量策略回测（策略 × 费率）。"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .engine import BacktestEngine
from .result import BacktestResult
from .strategy import StrategyBase, Strategy
from ..indicators.trend import ma


def batch_backtest(
    data: pd.DataFrame,
    strategies: dict,
    fee_models: list = None,
    *,
    initial_cash: float = 1_000_000.0,
    fill_model: str = "next_open",
    trade_on: str = "open",
    allow_short: bool = False,
    periods_per_year: Optional[int] = None,
    symbol: str = "",
    timeframe: str = "1d",
    on_progress=None,
) -> pd.DataFrame:
    """批量策略回测。

    Args:
        data: OHLCV 数据
        strategies: {name: strategy_obj_or_func}
        fee_models: 费率模型列表（如 ["F1_SpotNoBNB", "F4_FutBNB"]）
    Returns:
        DataFrame，每行是一个 strategy × fee_model 的回测摘要
    """
    if fee_models is None:
        fee_models = ["default"]
    if isinstance(fee_models, str):
        fee_models = [fee_models]

    results = []
    total = len(strategies) * len(fee_models)
    idx = 0
    for name, strat in strategies.items():
        for fee in fee_models:
            try:
                engine = BacktestEngine(
                    data=data,
                    strategy=strat,
                    initial_cash=initial_cash,
                    cost_model=fee,
                    fill_model=fill_model,
                    trade_on=trade_on,
                    allow_short=allow_short,
                    periods_per_year=periods_per_year,
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_name=name,
                )
                result = engine.run()
                m = result.metrics
                results.append({
                    "strategy": name,
                    "fee_model": fee,
                    "total_return": m.total_return,
                    "annual_return": m.annual_return,
                    "sharpe": m.sharpe,
                    "sortino": m.sortino,
                    "max_drawdown": m.max_drawdown,
                    "calmar": m.calmar,
                    "volatility": m.volatility,
                    "win_rate": m.win_rate,
                    "profit_factor": m.profit_factor,
                    "n_trades": m.n_trades,
                    "initial_cash": m.initial_cash,
                    "final_equity": m.final_equity,
                    "error": result.error,
                })
            except Exception as e:
                results.append({
                    "strategy": name, "fee_model": fee,
                    "error": str(e),
                    "total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                    "n_trades": 0, "final_equity": initial_cash,
                })
            idx += 1
            if on_progress:
                on_progress(idx, total)
    return pd.DataFrame(results)


__all__ = ["batch_backtest"]
