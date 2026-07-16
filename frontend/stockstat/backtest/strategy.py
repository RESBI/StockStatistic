from __future__ import annotations

from typing import Callable, Optional

from .context import BacktestContext
from .orders import Fill


class Strategy:
    """Base class for strategies. Override hooks as needed."""

    name: str = "base"

    def on_start(self, ctx: BacktestContext) -> None:
        pass

    def on_bar(self, ctx: BacktestContext) -> None:
        pass

    def on_bar_close(self, ctx: BacktestContext) -> None:
        pass

    def on_fill(self, fill: Fill, ctx: BacktestContext) -> None:
        pass

    def on_end(self, ctx: BacktestContext) -> None:
        pass


class FunctionStrategy(Strategy):
    """Wraps a simple `on_bar(ctx)` callable into a Strategy."""

    def __init__(self, fn: Callable[[BacktestContext], None], name: Optional[str] = None,
                 on_start: Optional[Callable] = None, on_end: Optional[Callable] = None):
        self._fn = fn
        self.name = name or getattr(fn, "__name__", "function_strategy")
        self._on_start = on_start
        self._on_end = on_end

    def on_start(self, ctx: BacktestContext) -> None:
        if self._on_start:
            self._on_start(ctx)

    def on_bar(self, ctx: BacktestContext) -> None:
        self._fn(ctx)

    def on_end(self, ctx: BacktestContext) -> None:
        if self._on_end:
            self._on_end(ctx)


def strategy(fn: Optional[Callable[[BacktestContext], None]] = None, *,
             name: Optional[str] = None):
    """Decorator turning `def on_bar(ctx)` into a FunctionStrategy."""

    def _wrap(f: Callable[[BacktestContext], None]) -> FunctionStrategy:
        return FunctionStrategy(f, name=name)

    if fn is None:
        return _wrap
    return _wrap(fn)


class Signal:
    """Helper to build orders from boolean signal series."""

    @staticmethod
    def market_on_signal(symbol: str, signal: bool, qty: float, ctx: BacktestContext,
                         side: str = "buy", tag: str = ""):
        from .orders import Order
        if signal:
            return ctx.broker.submit(Order(symbol=symbol, side=side, qty=qty, tag=tag))
        return None
