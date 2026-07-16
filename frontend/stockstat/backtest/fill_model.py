from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .orders import Order


class LookaheadError(RuntimeError):
    """Raised when a strategy attempts to access data beyond the current bar."""


class FillModel(ABC):
    """Decides fill price and whether an order can fill on a given bar."""

    @abstractmethod
    def fill_price(self, order: Order, bar: pd.Series, next_bar: Optional[pd.Series]) -> Optional[float]:
        """Return fill price if order fills, else None."""
        ...


class NextOpenFill(FillModel):
    """Fill at the open of the next bar. Strongest lookahead protection."""

    def fill_price(self, order: Order, bar: pd.Series, next_bar: Optional[pd.Series]) -> Optional[float]:
        if next_bar is None:
            return None
        return float(next_bar["open"])


class NextCloseFill(FillModel):
    """Fill at the close of the next bar."""

    def fill_price(self, order: Order, bar: pd.Series, next_bar: Optional[pd.Series]) -> Optional[float]:
        if next_bar is None:
            return None
        return float(next_bar["close"])


class ThisCloseFill(FillModel):
    """Fill at the close of the current bar (use with caution: lookahead risk)."""

    def __init__(self, warn: bool = True):
        self._warned = False
        self.warn = warn

    def fill_price(self, order: Order, bar: pd.Series, next_bar: Optional[pd.Series]) -> Optional[float]:
        if self.warn and not self._warned:
            import warnings
            warnings.warn(
                "ThisCloseFill uses the current bar's close; verify no lookahead in signals.",
                UserWarning,
                stacklevel=2,
            )
            self._warned = True
        return float(bar["close"])


class VWAPFill(FillModel):
    """Approximate VWAP using (open+high+low+close)/4 weighted by volume."""

    def fill_price(self, order: Order, bar: pd.Series, next_bar: Optional[pd.Series]) -> Optional[float]:
        if next_bar is None:
            return None
        o, h, l, c, v = (next_bar["open"], next_bar["high"], next_bar["low"],
                         next_bar["close"], next_bar["volume"])
        if v <= 0:
            return float(c)
        return float((o + h + l + c) / 4.0)


class WorstPriceFill(FillModel):
    """Fill buys at high, sells at low of next bar — conservative impact model."""

    def fill_price(self, order: Order, bar: pd.Series, next_bar: Optional[pd.Series]) -> Optional[float]:
        if next_bar is None:
            return None
        from .orders import OrderSide
        if order.side == OrderSide.BUY:
            return float(next_bar["high"])
        return float(next_bar["low"])


class IntrabarLimitFill(FillModel):
    """Fill limit/stop orders using intrabar high/low; market orders at next open.

    LIMIT buy:  fills if next_bar["low"] <= limit_price, at limit_price.
    LIMIT sell: fills if next_bar["high"] >= limit_price, at limit_price.
    STOP buy:   fills if next_bar["high"] >= stop_price, at stop_price.
    STOP sell:  fills if next_bar["low"] <= stop_price, at stop_price.
    MARKET:     fills at next_bar["open"] (same as NextOpenFill).
    """

    def fill_price(self, order: Order, bar: pd.Series,
                   next_bar: Optional[pd.Series]) -> Optional[float]:
        if next_bar is None:
            return None

        from .orders import OrderType, OrderSide

        if order.order_type == OrderType.MARKET:
            return float(next_bar["open"])

        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY:
                if next_bar["low"] <= order.limit_price:
                    return float(order.limit_price)
            else:
                if next_bar["high"] >= order.limit_price:
                    return float(order.limit_price)
            return None

        if order.order_type == OrderType.STOP:
            if order.side == OrderSide.BUY:
                if next_bar["high"] >= order.stop_price:
                    return float(order.stop_price)
            else:
                if next_bar["low"] <= order.stop_price:
                    return float(order.stop_price)
            return None

        if order.order_type == OrderType.STOP_LIMIT:
            if order.side == OrderSide.BUY:
                if next_bar["high"] >= order.stop_price:
                    if next_bar["low"] <= order.limit_price:
                        return float(order.limit_price)
            else:
                if next_bar["low"] <= order.stop_price:
                    if next_bar["high"] >= order.limit_price:
                        return float(order.limit_price)
            return None

        return None


def _check_limit_stop(order: Order, price: float) -> bool:
    """Validate limit/stop conditions against a candidate fill price."""
    from .orders import OrderType, OrderSide
    if order.order_type == OrderType.MARKET:
        return True
    if order.order_type == OrderType.LIMIT:
        if order.side == OrderSide.BUY:
            return price <= order.limit_price
        return price >= order.limit_price
    if order.order_type == OrderType.STOP:
        if order.side == OrderSide.BUY:
            return price >= order.stop_price
        return price <= order.stop_price
    if order.order_type == OrderType.STOP_LIMIT:
        if order.side == OrderSide.BUY:
            return price >= order.stop_price and price <= order.limit_price
        return price <= order.stop_price and price >= order.limit_price
    return True


# ── Intrabar fill support (BT-11) ──────────────────────────────

@dataclass
class IntrabarFillResult:
    """Result of an intrabar fill: price + sub-bar timing."""

    fill_price: float
    sub_bar_ts: object
    sub_bar_index: int


class IntrabarFillModel(IntrabarLimitFill):
    """Scan a sequence of sub-bars for limit/stop fills, returning timing.

    Inherits from IntrabarLimitFill (reuses single-bar logic) and adds
    ``fill_with_timing`` which returns an IntrabarFillResult.

    Does NOT modify the FillModel ABC — existing subclasses are unaffected.
    """

    def fill_with_timing(self, order: Order,
                         sub_bars: pd.DataFrame) -> Optional[IntrabarFillResult]:
        """Scan sub-bar sequence for the first fill, returning price + timing.

        Logic mirrors IntrabarLimitFill.fill_price but:
        - Input is a DataFrame of sub-bars (not a single next_bar)
        - Returns IntrabarFillResult (with timestamp + index)
        """
        if sub_bars is None or len(sub_bars) == 0:
            return None

        from .orders import OrderType, OrderSide

        for i in range(len(sub_bars)):
            ts = sub_bars.index[i]
            bar = sub_bars.iloc[i]

            if order.order_type == OrderType.MARKET:
                if i == 0:
                    return IntrabarFillResult(float(bar["open"]), ts, i)
                continue

            if order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY:
                    if bar["low"] <= order.limit_price:
                        return IntrabarFillResult(
                            float(order.limit_price), ts, i
                        )
                else:
                    if bar["high"] >= order.limit_price:
                        return IntrabarFillResult(
                            float(order.limit_price), ts, i
                        )
                continue

            if order.order_type == OrderType.STOP:
                if order.side == OrderSide.BUY:
                    if bar["high"] >= order.stop_price:
                        return IntrabarFillResult(
                            float(order.stop_price), ts, i
                        )
                else:
                    if bar["low"] <= order.stop_price:
                        return IntrabarFillResult(
                            float(order.stop_price), ts, i
                        )
                continue

            if order.order_type == OrderType.STOP_LIMIT:
                price = super().fill_price(order, sub_bars.iloc[0], bar)
                if price is not None:
                    return IntrabarFillResult(float(price), ts, i)
                continue

        return None
