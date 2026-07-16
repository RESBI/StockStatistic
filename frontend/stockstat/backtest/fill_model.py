from __future__ import annotations

from abc import ABC, abstractmethod
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
