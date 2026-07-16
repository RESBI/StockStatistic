from __future__ import annotations

from typing import Optional

import pandas as pd

from .fill_model import FillModel, _check_limit_stop, LookaheadError
from .orders import Order, Fill, OrderStatus, OrderType


class SimulatedBroker:
    """Order routing + simulated matching against upcoming bars."""

    def __init__(self, portfolio, cost_model, fill_model: FillModel, allow_short: bool = False):
        self.portfolio = portfolio
        self.cost_model = cost_model
        self.fill_model = fill_model
        self.allow_short = allow_short
        self._pending: dict[str, Order] = {}
        self._trailing_states: dict[str, float] = {}

    def submit(self, order: Order) -> str:
        self._pending[order.order_id] = order
        if order.order_type == OrderType.TRAILING_STOP:
            self._trailing_states[order.order_id] = 0.0
        return order.order_id

    def cancel(self, order_id: str) -> bool:
        return self._pending.pop(order_id, None) is not None

    def get_position(self, symbol: str):
        return self.portfolio.get_position(symbol)

    def process_bar(self, symbol: str, bar: pd.Series,
                    next_bar: Optional[pd.Series], ts: object) -> list[Fill]:
        """Match pending orders for `symbol` against bar/next_bar."""
        fills: list[Fill] = []
        to_remove = []
        for oid, order in list(self._pending.items()):
            if order.symbol != symbol:
                continue

            fill_price = self._resolve_fill_price(order, bar, next_bar, oid)
            if fill_price is None:
                if order.time_in_force.value == "day":
                    to_remove.append(oid)
                continue
            if not _check_limit_stop(order, fill_price):
                if order.time_in_force.value == "day":
                    to_remove.append(oid)
                continue

            fill = self._make_fill(order, fill_price, ts)
            try:
                self.portfolio.apply_fill(fill)
            except RuntimeError:
                to_remove.append(oid)
                continue
            fills.append(fill)
            to_remove.append(oid)

        for oid in to_remove:
            self._pending.pop(oid, None)
            self._trailing_states.pop(oid, None)
        return fills

    def _resolve_fill_price(self, order: Order, bar: pd.Series,
                            next_bar: Optional[pd.Series], oid: str) -> Optional[float]:
        if order.order_type == OrderType.TRAILING_STOP:
            return self._resolve_trailing(order, next_bar, oid)
        return self.fill_model.fill_price(order, bar, next_bar)

    def _resolve_trailing(self, order: Order, next_bar: Optional[pd.Series], oid: str) -> Optional[float]:
        from .orders import OrderSide
        if next_bar is None:
            return None
        high = float(next_bar["high"])
        low = float(next_bar["low"])
        trail = order.stop_price or 0.0
        if order.side == OrderSide.BUY:
            best = self._trailing_states.get(oid, low)
            best = min(best, low)
            self._trailing_states[oid] = best
            trigger = best + trail
            if high >= trigger:
                return trigger
            return None
        else:
            best = self._trailing_states.get(oid, high)
            best = max(best, high)
            self._trailing_states[oid] = best
            trigger = best - trail
            if low <= trigger:
                return trigger
            return None

    def _make_fill(self, order: Order, fill_price: float, ts: object) -> Fill:
        commission, slippage_cost = self.cost_model.compute(order, fill_price, order.qty)
        return Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=fill_price,
            commission=commission,
            slippage_cost=slippage_cost,
            ts=ts,
            tag=order.tag,
        )

    @property
    def pending_orders(self) -> list[Order]:
        return list(self._pending.values())
