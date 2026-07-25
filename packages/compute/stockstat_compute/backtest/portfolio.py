"""Portfolio — 持仓与现金管理。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class Position:
    """单个标的持仓。"""
    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def is_flat(self) -> bool:
        return abs(self.quantity) < 1e-10

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.avg_price) * self.quantity

    def update_on_buy(self, quantity: float, price: float, cost: float = 0.0) -> None:
        """买入更新。"""
        if self.quantity + quantity <= 0 and self.quantity > 0:
            # 平多 + 反手
            self.realized_pnl += (price - self.avg_price) * self.quantity - cost
        new_qty = self.quantity + quantity
        if new_qty * self.quantity > 0:
            # 加仓
            total_cost = self.avg_price * self.quantity + price * quantity
            self.avg_price = total_cost / new_qty if new_qty != 0 else price
        elif new_qty == 0 or abs(new_qty) < 1e-10:
            # 平仓
            self.avg_price = 0.0
        else:
            # 反手
            self.avg_price = price
        self.quantity = new_qty

    def update_on_sell(self, quantity: float, price: float, cost: float = 0.0) -> None:
        """卖出更新。"""
        self.update_on_buy(-quantity, price, cost)


class Portfolio:
    """组合管理 — 现金 + 多个 Position。"""

    def __init__(self, initial_cash: float = 1_000_000.0,
                 allow_short: bool = False):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.allow_short = allow_short
        self._positions: dict = {}

    @property
    def positions(self) -> dict:
        return self._positions

    def get_position(self, symbol: str) -> Position:
        if symbol not in self._positions:
            self._positions[symbol] = Position(symbol=symbol)
        return self._positions[symbol]

    def total_value(self, prices: dict) -> float:
        """总权益 = 现金 + 持仓市值。"""
        total = self.cash
        for sym, pos in self._positions.items():
            if sym in prices:
                total += pos.market_value(prices[sym])
        return total

    def execute_buy(self, symbol: str, quantity: float, price: float,
                    cost: float = 0.0) -> None:
        """执行买入。"""
        if quantity <= 0:
            return
        pos = self.get_position(symbol)
        # 如果当前是空头且不允许做空扩仓，限制买入量不超过平仓
        if not self.allow_short and pos.quantity < 0:
            quantity = min(quantity, -pos.quantity)
            if quantity <= 0:
                return
        # 现金检查：只对加仓/新建多头限制（空头平仓会释放现金）
        if pos.quantity >= 0:
            notional = quantity * price
            if notional + cost > self.cash:
                # 现金不足，按可用资金调整
                affordable = max(0, (self.cash - cost) / price) if price > 0 else 0
                if affordable <= 0:
                    return
                quantity = affordable
                notional = quantity * price
            self.cash -= notional + cost
        else:
            # 平空：释放现金
            notional = quantity * price
            self.cash += notional - cost
        pos.update_on_buy(quantity, price, cost)

    def execute_sell(self, symbol: str, quantity: float, price: float,
                     cost: float = 0.0) -> None:
        """执行卖出。"""
        if quantity <= 0:
            return
        pos = self.get_position(symbol)
        # 如果不允许做空，卖出量不超过持仓量
        if not self.allow_short and pos.quantity >= 0:
            quantity = min(quantity, pos.quantity)
            if quantity <= 0:
                return
        # 现金变动
        if pos.quantity > 0:
            # 平多/减多：增加现金
            self.cash += quantity * price - cost
        else:
            # 加空：扣除现金（保证金）
            self.cash -= quantity * price + cost
        pos.update_on_sell(quantity, price, cost)

    def execute_target_pct(self, symbol: str, target_pct: float,
                           price: float, total_equity: float,
                           cost: float = 0.0) -> None:
        """按目标比例调仓。"""
        target_value = target_pct * total_equity
        pos = self.get_position(symbol)
        current_value = pos.market_value(price)
        diff_value = target_value - current_value
        if abs(diff_value) < 1e-6:
            return
        diff_qty = diff_value / price
        if diff_qty > 0:
            self.execute_buy(symbol, diff_qty, price, cost)
        else:
            self.execute_sell(symbol, -diff_qty, price, cost)

    def reset(self) -> None:
        """重置组合。"""
        self.cash = self.initial_cash
        self._positions.clear()


__all__ = ["Position", "Portfolio"]
