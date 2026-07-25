from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .orders import OrderSide


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0

    @property
    def is_long(self) -> bool:
        return self.qty > 0

    @property
    def is_short(self) -> bool:
        return self.qty < 0

    @property
    def is_flat(self) -> bool:
        return self.qty == 0

    @property
    def direction(self) -> int:
        return (self.qty > 0) - (self.qty < 0)

    def market_value(self, price: float) -> float:
        return self.qty * price

    def unrealized_pnl(self, price: float) -> float:
        return self.qty * (price - self.avg_cost)

    def apply_fill(self, fill_qty: float, fill_price: float) -> float:
        """Apply a signed fill quantity. Returns realized pnl from closing trades."""
        signed = fill_qty
        old_qty = self.qty
        new_qty = old_qty + signed
        realized = 0.0
        if old_qty != 0 and ((old_qty > 0) != (signed > 0)):
            closing = min(abs(signed), abs(old_qty))
            realized = closing * (fill_price - self.avg_cost) * (1 if old_qty > 0 else -1)
            self.realized_pnl += realized
        if new_qty == 0:
            self.qty = 0.0
            self.avg_cost = 0.0
        elif (old_qty >= 0) == (new_qty >= 0) and old_qty != 0:
            self.avg_cost = (old_qty * self.avg_cost + signed * fill_price) / new_qty
        else:
            self.avg_cost = fill_price
        self.qty = new_qty
        return realized


class Portfolio:
    """Account: cash + positions, marked-to-market each bar."""

    def __init__(self, initial_cash: float = 1_000_000.0, allow_short: bool = False):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.allow_short = allow_short
        self.positions: dict[str, Position] = {}
        self.fills: list = []
        self.realized_history: list[tuple[object, str, float]] = []
        self._equity_curve: list[tuple[pd.Timestamp, float]] = []

    def get_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def apply_fill(self, fill) -> None:
        pos = self.get_position(fill.symbol)
        signed_qty = fill.signed_qty
        if not self.allow_short and (pos.qty + signed_qty) < -1e-9:
            raise RuntimeError(
                f"Short selling disabled: would make {fill.symbol} position negative"
            )
        realized = pos.apply_fill(signed_qty, fill.price)
        if abs(realized) > 1e-12:
            self.realized_history.append((fill.ts, fill.symbol, realized))
        self.cash += fill.net_value
        self.fills.append(fill)

    def mark_to_market(self, prices: dict[str, float], ts: object = None) -> float:
        equity = self.cash
        for sym, pos in self.positions.items():
            price = prices.get(sym)
            if price is not None:
                equity += pos.market_value(price)
        if ts is not None:
            self._equity_curve.append((ts, equity))
        return equity

    def positions_value(self, prices: dict[str, float]) -> float:
        return sum(pos.market_value(prices.get(sym, 0.0)) for sym, pos in self.positions.items())

    @property
    def equity_curve(self) -> pd.Series:
        if not self._equity_curve:
            return pd.Series(dtype=float)
        idx = pd.DatetimeIndex([t for t, _ in self._equity_curve])
        return pd.Series([v for _, v in self._equity_curve], index=idx)

    def net_exposure(self, prices: dict[str, float]) -> float:
        long_v = sum(pos.market_value(prices.get(s, 0.0)) for s, pos in self.positions.items() if pos.qty > 0)
        short_v = sum(-pos.market_value(prices.get(s, 0.0)) for s, pos in self.positions.items() if pos.qty < 0)
        return long_v - short_v

    def gross_exposure(self, prices: dict[str, float]) -> float:
        return sum(abs(pos.market_value(prices.get(s, 0.0))) for s, pos in self.positions.items())
