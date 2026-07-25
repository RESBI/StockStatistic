"""grid_search — 参数网格搜索。"""
from __future__ import annotations

import itertools
from typing import Optional

import pandas as pd

from .engine import BacktestEngine
from .result import BacktestResult


def grid_search(
    data: pd.DataFrame,
    strategy_cls,
    param_grid: dict,
    *,
    metric: str = "sharpe",
    maximize: bool = True,
    initial_cash: float = 1_000_000.0,
    cost_model: str = "default",
    fill_model: str = "next_open",
    trade_on: str = "open",
    allow_short: bool = False,
    periods_per_year: Optional[int] = None,
    symbol: str = "",
    timeframe: str = "1d",
    on_progress=None,
) -> pd.DataFrame:
    """参数网格搜索。

    Args:
        data: OHLCV 数据
        strategy_cls: Strategy 子类（接受 **params 构造）
        param_grid: {param_name: [value1, value2, ...]}
        metric: 排序指标
        maximize: True=最大化 / False=最小化
    Returns:
        DataFrame，每行一组参数 + 指标值，按 metric 排序
    """
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combos = list(itertools.product(*values))

    results = []
    total = len(combos)
    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        try:
            strategy = strategy_cls(**params)
            engine = BacktestEngine(
                data=data, strategy=strategy,
                initial_cash=initial_cash,
                cost_model=cost_model,
                fill_model=fill_model,
                trade_on=trade_on,
                allow_short=allow_short,
                periods_per_year=periods_per_year,
                symbol=symbol, timeframe=timeframe,
                strategy_name=strategy.name if hasattr(strategy, "name") else "grid",
            )
            result = engine.run()
            m = result.metrics
            row = {**params}
            row.update({
                "total_return": m.total_return,
                "sharpe": m.sharpe,
                "sortino": m.sortino,
                "max_drawdown": m.max_drawdown,
                "calmar": m.calmar,
                "volatility": m.volatility,
                "n_trades": m.n_trades,
                "final_equity": m.final_equity,
                "error": result.error,
            })
            results.append(row)
        except Exception as e:
            row = {**params, "error": str(e), "sharpe": 0.0,
                   "total_return": 0.0, "max_drawdown": 0.0, "n_trades": 0}
            results.append(row)
        if on_progress:
            on_progress(i + 1, total)

    df = pd.DataFrame(results)
    if len(df) > 0 and metric in df.columns:
        df = df.sort_values(metric, ascending=not maximize).reset_index(drop=True)
    return df


__all__ = ["grid_search"]
