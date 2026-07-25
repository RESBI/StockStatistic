"""Metrics — 回测指标计算。"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .result import BacktestMetrics, Trade


def calculate_metrics(equity_curve: pd.DataFrame,
                      trades: list,
                      initial_cash: float,
                      periods_per_year: int = 252,
                      benchmark: Optional[pd.Series] = None) -> BacktestMetrics:
    """从权益曲线和交易列表计算指标。"""
    if equity_curve is None or len(equity_curve) == 0:
        return BacktestMetrics(initial_cash=initial_cash)

    equity = equity_curve["equity"].astype(float)
    n = len(equity)
    final_equity = float(equity.iloc[-1])
    total_return = (final_equity / initial_cash - 1) if initial_cash > 0 else 0.0

    # 年化收益
    if n > 1 and periods_per_year > 0:
        years = n / periods_per_year
        if years > 0 and final_equity > 0:
            annual_return = (final_equity / initial_cash) ** (1 / years) - 1
        else:
            annual_return = 0.0
    else:
        annual_return = 0.0

    # 日收益率
    returns = equity.pct_change().dropna()
    if len(returns) == 0:
        return BacktestMetrics(
            total_return=total_return, annual_return=annual_return,
            initial_cash=initial_cash, final_equity=final_equity,
            periods_per_year=periods_per_year,
        )

    volatility = float(returns.std() * np.sqrt(periods_per_year))
    sharpe = float(returns.mean() / returns.std() * np.sqrt(periods_per_year)) if returns.std() > 0 else 0.0

    # Sortino
    downside = returns[returns < 0]
    sortino = float(returns.mean() / downside.std() * np.sqrt(periods_per_year)) if len(downside) > 0 and downside.std() > 0 else 0.0

    # 最大回撤
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_dd = float(drawdown.min())

    # Calmar
    calmar = annual_return / abs(max_dd) if max_dd < 0 else 0.0

    # 交易统计
    n_trades = len(trades)
    # 配对计算 P&L（简化：每对 buy/sell 算一次）
    trade_pnls = _compute_trade_pnls(trades)
    n_winning = sum(1 for p in trade_pnls if p > 0)
    n_losing = sum(1 for p in trade_pnls if p < 0)
    win_rate = n_winning / n_trades if n_trades > 0 else 0.0
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    avg_trade = float(np.mean(trade_pnls)) if trade_pnls else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    return BacktestMetrics(
        total_return=total_return,
        annual_return=annual_return,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        calmar=calmar,
        volatility=volatility,
        win_rate=win_rate,
        profit_factor=profit_factor,
        n_trades=n_trades,
        n_winning=n_winning,
        n_losing=n_losing,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_trade=avg_trade,
        initial_cash=initial_cash,
        final_equity=final_equity,
        periods_per_year=periods_per_year,
    )


def _compute_trade_pnls(trades: list) -> list:
    """配对计算每次完整交易的 P&L（简化版）。"""
    pnls = []
    open_buy = None
    for t in trades:
        if isinstance(t, Trade):
            if t.side == "buy":
                if open_buy is None:
                    open_buy = t
                else:
                    # 连续买入，合并
                    pass
            elif t.side == "sell":
                if open_buy is not None:
                    pnl = (t.price - open_buy.price) * t.quantity - t.cost - open_buy.cost
                    pnls.append(pnl)
                    open_buy = None
                else:
                    # 卖空
                    pass
    return pnls


__all__ = ["calculate_metrics"]
