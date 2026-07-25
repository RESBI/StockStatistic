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
        self._oco_pairs: dict[str, str] = {}
        self._oco_reverse: dict[str, str] = {}

    def submit(self, order: Order) -> str:
        self._pending[order.order_id] = order
        if order.order_type == OrderType.TRAILING_STOP:
            self._trailing_states[order.order_id] = 0.0
        return order.order_id

    def submit_oco(self, order_a: Order, order_b: Order) -> tuple[str, str]:
        """Submit a One-Cancels-Other pair. When either fills, the other is cancelled."""
        self.submit(order_a)
        self.submit(order_b)
        self._oco_pairs[order_a.order_id] = order_b.order_id
        self._oco_reverse[order_b.order_id] = order_a.order_id
        return order_a.order_id, order_b.order_id

    def submit_oco_mutual(self, order_a: Order, order_b: Order) -> tuple[str, str]:
        """Submit a mutual-OCO pair: if BOTH fill, both are cancelled.

        Unlike submit_oco (one fills → cancel other), this requires
        scanning all sub-bars first. The mutual relationship is managed
        by IntrabarExecution via register_oco_mutual().

        For non-intrabar usage, this behaves like submit_oco.
        """
        self.submit(order_a)
        self.submit(order_b)
        self._oco_pairs[order_a.order_id] = order_b.order_id
        self._oco_reverse[order_b.order_id] = order_a.order_id
        return order_a.order_id, order_b.order_id

    def cancel(self, order_id: str) -> bool:
        """Cancel an order. If part of an OCO pair, cancel the other too."""
        paired = self._oco_pairs.get(order_id) or self._oco_reverse.get(order_id)
        if paired:
            self._pending.pop(paired, None)
            self._trailing_states.pop(paired, None)
            self._oco_pairs.pop(paired, None)
            self._oco_reverse.pop(paired, None)
        self._oco_pairs.pop(order_id, None)
        self._oco_reverse.pop(order_id, None)
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

            paired = self._oco_pairs.get(oid) or self._oco_reverse.get(oid)
            if paired and paired not in to_remove:
                to_remove.append(paired)

        for oid in to_remove:
            self._pending.pop(oid, None)
            self._trailing_states.pop(oid, None)
            self._oco_pairs.pop(oid, None)
            self._oco_reverse.pop(oid, None)
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
            exit_reason=order.exit_reason,
        )

    @property
    def pending_orders(self) -> list[Order]:
        return list(self._pending.values())
