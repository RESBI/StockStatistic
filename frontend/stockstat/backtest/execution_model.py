"""Execution models: pluggable order matching strategies.

BT-11: ExecutionModel ABC + NextBarExecution (default, existing behavior).
BT-12: IntrabarExecution (intrabar sub-bar matching).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd

from .orders import Order, Fill, OrderType, OrderSide
from .fill_model import IntrabarFillModel, IntrabarFillResult


class ExecutionModel(ABC):
    """Abstract base for order execution models.

    An ExecutionModel decides how/when pending orders fill within a bar.
    It is injected into BacktestEngine via the ``execution_model`` parameter.

    - NextBarExecution (default): orders fill at the next bar's open (existing behavior)
    - IntrabarExecution: orders fill within the current bar's sub-bar sequence
    """

    @abstractmethod
    def execute(self, engine, ctx, t: pd.Timestamp,
                pending_orders: list[Order]) -> list[Fill]:
        """Execute pending orders for bar ``t``."""
        ...

    @property
    @abstractmethod
    def is_intrabar(self) -> bool:
        """Whether this model uses intrabar (sub-bar) execution."""
        ...


class NextBarExecution(ExecutionModel):
    """Default execution model: orders fill at the next bar.

    When execution_model=None (default), BacktestEngine uses this model
    internally via its existing broker.process_bar() code path.
    """

    @property
    def is_intrabar(self) -> bool:
        return False

    def execute(self, engine, ctx, t, pending_orders):
        """This method is not called in default mode — BacktestEngine.run()
        uses its inline broker.process_bar() loop for NextBarExecution.
        """
        return []


class IntrabarExecution(ExecutionModel):
    """Intrabar execution model: fill orders within sub-bar sequences.

    Supports:
    - Gap-1: Fill timing tracking (sub_bar_ts, sub_bar_index)
    - Gap-2: Same-bar entry + exit
    - Gap-3: Post-entry exit scanning (define_exits)
    - Gap-4: Mutual OCO (both fill → both cancel)
    - Gap-5: Order priority within same sub-bar
    """

    def __init__(self,
                 intrabar_tf: str,
                 parent_tf: Optional[str] = None,
                 fill_model: Optional[IntrabarFillModel] = None):
        self.intrabar_tf = intrabar_tf
        self.parent_tf = parent_tf
        self._filler = fill_model or IntrabarFillModel()
        self._oco_mutual_pairs: dict[str, str] = {}

    @property
    def is_intrabar(self) -> bool:
        return True

    def register_oco_mutual(self, order_a: Order, order_b: Order):
        """Register a mutual-OCO pair."""
        self._oco_mutual_pairs[order_a.order_id] = order_b.order_id
        self._oco_mutual_pairs[order_b.order_id] = order_a.order_id

    def execute(self, engine, ctx, t, pending_orders):
        """Execute intrabar orders on sub-bar sequences."""
        if not pending_orders:
            return []

        fills = []
        symbols = engine.universe.symbols
        parent_tf = self.parent_tf or engine.data_feed.primary_tf

        for sym in symbols:
            sub_bars = engine.data_feed.intrabar_slice(
                sym, parent_tf, self.intrabar_tf, t
            )
            if sub_bars is None or len(sub_bars) == 0:
                continue

            sym_orders = [o for o in pending_orders if o.symbol == sym]
            if not sym_orders:
                continue

            sym_fills = self._scan_sub_bars(
                engine, ctx, sym_orders, sub_bars, sym, t
            )
            fills.extend(sym_fills)

        return fills

    def _scan_sub_bars(self, engine, ctx, orders, sub_bars, sym, t):
        """Scan sub-bars: first find all fills, then apply (supports mutual OCO cancel)."""
        all_fills = []
        entry_orders = sorted(orders, key=lambda o: getattr(o, 'priority', 99))

        # Phase 1: Pre-scan each order to find fill time (no apply yet)
        fill_results: dict[str, tuple[Order, IntrabarFillResult]] = {}
        for order in entry_orders:
            result = self._filler.fill_with_timing(order, sub_bars)
            if result is not None:
                fill_results[order.order_id] = (order, result)

        # Phase 2: Check mutual OCO cancellations
        to_cancel: set[str] = set()
        for oid, (order, result) in list(fill_results.items()):
            if oid in to_cancel:
                continue
            paired_id = self._oco_mutual_pairs.get(oid)
            if paired_id and paired_id in fill_results:
                # Both filled → cancel both
                to_cancel.add(oid)
                to_cancel.add(paired_id)

        # Remove cancelled
        for oid in to_cancel:
            fill_results.pop(oid, None)

        if not fill_results:
            return all_fills

        # Phase 3: Apply fills in chronological order, scan exits after each
        sorted_fills = sorted(fill_results.values(), key=lambda x: x[1].sub_bar_index)

        for order, result in sorted_fills:
            fill = self._make_fill(engine, order, result, t)
            engine.portfolio.apply_fill(fill)
            all_fills.append(fill)

            # Get exit orders from strategy
            exit_orders = self._get_exits(engine.strategy, fill, ctx)
            if exit_orders:
                # Exit scan starts from the entry fill's sub-bar (inclusive),
                # matching v5 behavior where exits can trigger on the same bar.
                remaining = sub_bars.iloc[result.sub_bar_index:]
                exit_fills = self._scan_exits(
                    engine, ctx, exit_orders, remaining, sym, t
                )
                all_fills.extend(exit_fills)

        return all_fills

    def _scan_exits(self, engine, ctx, exit_orders, remaining_bars, sym, t):
        """Scan exit orders on remaining sub-bars after entry.

        Market orders with tag='close' fill at the LAST sub-bar's close
        (session close), matching v5 behavior. Other market orders fill
        at the first sub-bar's open. Limit/stop orders scan normally.
        """
        all_fills = []
        exit_orders = sorted(exit_orders, key=lambda o: getattr(o, 'priority', 99))

        # Separate session-close market orders from active exit orders
        close_orders = [o for o in exit_orders
                        if o.order_type == OrderType.MARKET and o.tag == "close"]
        active_orders = [o for o in exit_orders
                         if not (o.order_type == OrderType.MARKET and o.tag == "close")]

        # Phase 1: Scan active orders (limit/stop/market non-close) on each sub-bar
        for i in range(len(remaining_bars)):
            current_sub = remaining_bars.iloc[[i]]

            for order in active_orders:
                result = self._filler.fill_with_timing(order, current_sub)
                if result is not None:
                    fill = self._make_fill(engine, order, result, t)
                    engine.portfolio.apply_fill(fill)
                    all_fills.append(fill)
                    return all_fills  # First exit fill ends the trade

        # Phase 2: If no active exit filled, fill close orders at session close
        if not all_fills and close_orders and len(remaining_bars) > 0:
            last_bar = remaining_bars.iloc[-1]
            last_ts = remaining_bars.index[-1]
            last_idx = len(remaining_bars) - 1
            for order in close_orders:
                result = IntrabarFillResult(
                    float(last_bar["close"]), last_ts, last_idx
                )
                fill = self._make_fill(engine, order, result, t)
                engine.portfolio.apply_fill(fill)
                all_fills.append(fill)
            return all_fills

        # Phase 3: If still no fill, force close at last bar
        if not all_fills and close_orders and len(remaining_bars) > 0:
            pass  # Already handled in Phase 2

        return all_fills

    def _get_exits(self, strategy, entry_fill, ctx):
        """Get exit orders from strategy via duck typing."""
        define_exits = getattr(strategy, 'define_exits', None)
        if define_exits is None:
            return []
        try:
            return define_exits(entry_fill, ctx) or []
        except Exception:
            return []

    def _find_order(self, orders, order_id):
        for o in orders:
            if o.order_id == order_id:
                return o
        return None

    def _make_fill(self, engine, order, result, t):
        """Construct a Fill object with intrabar timing."""
        commission, slippage = engine.cost_model.compute(
            order, result.fill_price, order.qty
        )
        return Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=result.fill_price,
            commission=commission,
            slippage_cost=slippage,
            ts=t,
            tag=order.tag,
            exit_reason=order.exit_reason,
            sub_bar_ts=result.sub_bar_ts,
            sub_bar_index=result.sub_bar_index,
        )
