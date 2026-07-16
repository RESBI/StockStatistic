from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from .data_feed import DataFeed
from .fill_model import LookaheadError


class ContextHistory:
    """Per-strategy scratchpad for persisting state across bars."""

    def __init__(self):
        self._store: dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        return self._store[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._store[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value


class BacktestContext:
    """The strategy's view of the world at bar `t`.

    Enforces lookahead protection: only data `<= t` is accessible.
    """

    def __init__(self, data_feed: DataFeed, portfolio, broker,
                 compute_engine, now: pd.Timestamp,
                 current_bar: dict[str, pd.Series],
                 lookahead_audit: bool = False):
        self._feed = data_feed
        self._portfolio = portfolio
        self._broker = broker
        self._compute = compute_engine
        self.now = now
        self.current_bar = current_bar
        self._lookahead_audit = lookahead_audit
        self._history = ContextHistory()

    @property
    def compute(self):
        return self._compute

    @property
    def broker(self):
        return self._broker

    @property
    def portfolio(self):
        return self._portfolio

    @property
    def history(self) -> ContextHistory:
        return self._history

    def get(self, symbol: str, timeframe: str = "1d",
            lookback: Optional[int] = None) -> pd.DataFrame:
        df = self._feed.get_slice(symbol, timeframe, self.now, lookback)
        if self._lookahead_audit and not df.empty:
            if df.index.max() > self.now:
                raise LookaheadError(
                    f"Access to future data at {df.index.max()} > {self.now}"
                )
        return df

    def current_price(self, symbol: str, field: str = "close") -> Optional[float]:
        bar = self.current_bar.get(symbol)
        if bar is None:
            return None
        return float(bar[field])
