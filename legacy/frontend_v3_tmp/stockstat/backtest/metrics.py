from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import statistics as stats


def _periods_per_year(index: pd.Index) -> int:
    if len(index) < 2:
        return 252
    delta = (index[-1] - index[0]).total_seconds() / len(index)
    seconds_per_year = 365.25 * 24 * 3600
    ppy = seconds_per_year / delta
    for guess in (252, 365, 52, 12, 365.25 * 24, 365.25 * 24 * 4, 365.25 * 24 * 60):
        if abs(ppy - guess) < 0.5 or ppy > guess * 0.8 and ppy < guess * 1.2:
            return guess
    return int(round(ppy))


def total_return(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def annualized_return(equity: pd.Series, periods_per_year: int = 252) -> float:
    if len(equity) < 2:
        return 0.0
    n = len(equity) - 1
    ann = (equity.iloc[-1] / equity.iloc[0]) ** (periods_per_year / n) - 1.0
    return float(ann)


def sharpe_ratio(equity: pd.Series, risk_free: float = 0.02,
                 periods_per_year: int = 252) -> float:
    if len(equity) < 2:
        return 0.0
    rets = equity.pct_change().dropna()
    return stats.sharpe(rets, risk_free=risk_free, annualize=True)


def sortino_ratio(equity: pd.Series, risk_free: float = 0.02,
                  periods_per_year: int = 252) -> float:
    if len(equity) < 2:
        return 0.0
    rets = equity.pct_change().dropna()
    excess = rets - risk_free / periods_per_year
    downside = excess[excess < 0]
    if downside.std() == 0:
        return 0.0
    return float(excess.mean() / downside.std() * np.sqrt(periods_per_year))


def max_drawdown(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    return stats.max_drawdown(equity)


def drawdown_series(equity: pd.Series) -> pd.Series:
    running = equity.cummax()
    return (equity - running) / running


def calmar_ratio(equity: pd.Series, periods_per_year: int = 252) -> float:
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return 0.0
    return annualized_return(equity, periods_per_year) / mdd


def omega_ratio(returns: pd.Series, threshold: float = 0.0) -> float:
    gains = returns[returns > threshold]
    losses = returns[returns < threshold]
    if losses.empty or losses.sum() == 0:
        return float("inf") if not gains.empty else 0.0
    return float(gains.sum() / abs(losses.sum()))


def information_ratio(returns: pd.Series, benchmark_returns: pd.Series,
                      periods_per_year: int = 252) -> float:
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 2:
        return 0.0
    active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    if active.std() == 0:
        return 0.0
    return float(active.mean() / active.std() * np.sqrt(periods_per_year))


def trade_stats(realized_history: list = None, fills: list = None) -> dict:
    """Aggregate trade-level statistics from realized PnL history.

    `realized_history`: list of (ts, symbol, pnl) tuples from Portfolio.
    """
    if realized_history is None:
        realized_history = []
    pnls = [p for _, _, p in realized_history]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = sum(abs(p) for p in losses)
    # streaks
    streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    for p in pnls:
        if p > 0:
            streak = streak + 1 if streak >= 0 else 1
            max_win_streak = max(max_win_streak, streak)
        elif p < 0:
            streak = streak - 1 if streak <= 0 else -1
            max_loss_streak = max(max_loss_streak, abs(streak))
    total = len(pnls)
    return {
        "num_trades": total,
        "num_fills": len(fills) if fills is not None else 0,
        "win_rate": len(wins) / total if total else 0.0,
        "avg_pnl": float(np.mean(pnls)) if pnls else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "expectancy": float(np.mean(pnls)) if pnls else 0.0,
    }


def compute_all_metrics(equity: pd.Series, fills: list = None,
                        realized_history: list = None,
                        benchmark: pd.Series = None,
                        risk_free: float = 0.02,
                        periods_per_year: int = 252) -> dict:
    m = {
        "total_return": total_return(equity),
        "annualized_return": annualized_return(equity, periods_per_year),
        "sharpe": sharpe_ratio(equity, risk_free, periods_per_year),
        "sortino": sortino_ratio(equity, risk_free, periods_per_year),
        "max_drawdown": max_drawdown(equity),
        "calmar": calmar_ratio(equity, periods_per_year),
        "volatility": float(equity.pct_change().dropna().std() * np.sqrt(periods_per_year)),
    }
    if realized_history is not None or fills is not None:
        m.update(trade_stats(realized_history=realized_history, fills=fills))
    if benchmark is not None and len(benchmark) >= 2:
        rets = equity.pct_change().dropna()
        bench_rets = benchmark.pct_change().dropna()
        m["information_ratio"] = information_ratio(rets, bench_rets, periods_per_year)
    return m
