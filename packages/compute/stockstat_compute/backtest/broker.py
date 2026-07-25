"""Broker — 订单执行代理。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from .cost_model import CostModel, get_cost_model
from .fill_model import FillModel, get_fill_model
from .portfolio import Portfolio
from .result import Trade


class Broker:
    """订单执行代理 — 协调 Portfolio + CostModel + FillModel。"""

    def __init__(self, portfolio: Portfolio,
                 cost_model=None,
                 fill_model=None):
        self._portfolio = portfolio
        self._cost_model = cost_model or get_cost_model("default")
        if isinstance(self._cost_model, str):
            self._cost_model = get_cost_model(self._cost_model)
        self._fill_model = fill_model or get_fill_model("next_open")
        if isinstance(self._fill_model, str):
            self._fill_model = get_fill_model(self._fill_model)
        self._trades: list = []

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    @property
    def trades(self) -> list:
        return self._trades

    def execute_signal(self, signal, i: int, data: pd.DataFrame,
                       current_equity: float) -> Optional[Trade]:
        """执行 Signal。"""
        if signal is None or signal.side == "hold":
            return None

        fill_price = self._fill_model.get_fill_price(i, data, signal.side)
        symbol = signal.symbol
        if signal.quantity is None:
            # 按目标比例 1.0（全仓）
            target_pct = signal.strength
            qty = (current_equity * target_pct) / fill_price
            if signal.side == "sell":
                qty = -qty
        else:
            qty = signal.quantity if signal.side == "buy" else -signal.quantity

        cost = self._cost_model.calculate(abs(qty), fill_price)

        if qty > 0:
            self._portfolio.execute_buy(symbol, abs(qty), fill_price, cost)
        else:
            self._portfolio.execute_sell(symbol, abs(qty), fill_price, cost)

        trade = Trade(
            timestamp=signal.timestamp,
            symbol=symbol,
            side=signal.side,
            quantity=abs(qty),
            price=fill_price,
            cost=cost,
            fill_model=self._fill_model.name,
            notes=signal.notes,
        )
        self._trades.append(trade)
        return trade

    def reset(self) -> None:
        self._trades.clear()
        self._portfolio.reset()


__all__ = ["Broker"]
