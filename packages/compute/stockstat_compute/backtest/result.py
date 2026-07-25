"""BacktestResult — 回测结果数据类。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class Trade:
    """单笔交易记录。"""
    timestamp: datetime
    symbol: str
    side: str  # buy / sell
    quantity: float
    price: float
    cost: float = 0.0
    fill_model: str = "next_open"
    notes: str = ""

    @property
    def value(self) -> float:
        return self.quantity * self.price

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "symbol": self.symbol, "side": self.side,
            "quantity": self.quantity, "price": self.price,
            "cost": self.cost, "fill_model": self.fill_model,
            "notes": self.notes,
        }


@dataclass
class EquityPoint:
    """权益曲线点。"""
    timestamp: datetime
    equity: float
    cash: float = 0.0
    position_value: float = 0.0
    drawdown: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "equity": self.equity, "cash": self.cash,
            "position_value": self.position_value, "drawdown": self.drawdown,
        }


@dataclass
class BacktestMetrics:
    """回测指标。"""
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0
    calmar: float = 0.0
    volatility: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    n_trades: int = 0
    n_winning: int = 0
    n_losing: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_trade: float = 0.0
    initial_cash: float = 0.0
    final_equity: float = 0.0
    periods_per_year: int = 252

    def to_dict(self) -> dict:
        return {
            "total_return": self.total_return,
            "annual_return": self.annual_return,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown": self.max_drawdown,
            "calmar": self.calmar,
            "volatility": self.volatility,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "n_trades": self.n_trades,
            "n_winning": self.n_winning,
            "n_losing": self.n_losing,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "avg_trade": self.avg_trade,
            "initial_cash": self.initial_cash,
            "final_equity": self.final_equity,
            "periods_per_year": self.periods_per_year,
        }


@dataclass
class BacktestResult:
    """完整回测结果。"""
    metrics: BacktestMetrics
    trades: list = field(default_factory=list)
    equity_curve: pd.DataFrame = None
    positions: pd.DataFrame = None
    strategy_name: str = ""
    symbol: str = ""
    timeframe: str = ""
    initial_cash: float = 0.0
    final_equity: float = 0.0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def summary(self) -> str:
        """人类可读的简报。"""
        m = self.metrics
        return (
            f"BacktestResult(strategy={self.strategy_name!r}, symbol={self.symbol!r})\n"
            f"  total_return: {m.total_return * 100:.2f}%\n"
            f"  annual_return: {m.annual_return * 100:.2f}%\n"
            f"  sharpe: {m.sharpe:.3f}\n"
            f"  max_drawdown: {m.max_drawdown * 100:.2f}%\n"
            f"  n_trades: {m.n_trades}\n"
            f"  win_rate: {m.win_rate * 100:.1f}%\n"
            f"  final_equity: {self.final_equity:.2f}"
        )

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics.to_dict(),
            "trades": [t.to_dict() if isinstance(t, Trade) else t for t in self.trades],
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "initial_cash": self.initial_cash,
            "final_equity": self.final_equity,
            "error": self.error,
            "metadata": self.metadata,
        }


__all__ = ["Trade", "EquityPoint", "BacktestMetrics", "BacktestResult"]
