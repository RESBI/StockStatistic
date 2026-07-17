"""Domain models — financial data entities.

These are pure-Python dataclasses (not ORM-bound). The v1.7 SQLAlchemy
ORM classes remain in ``stockstat_backend.models.ohlcv``; these domain
models provide a storage-agnostic abstraction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class OHLCV:
    """A single OHLCV bar."""
    symbol: str
    ts: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: str = ""
    timeframe: str = "1d"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "ts": self.ts,
            "open": self.open, "high": self.high,
            "low": self.low, "close": self.close,
            "volume": self.volume, "source": self.source,
            "timeframe": self.timeframe,
        }


@dataclass
class Symbol:
    """A registered trading symbol."""
    unified_symbol: str
    asset_type: str  # "crypto" | "stock"
    base_asset: str = ""
    quote_asset: Optional[str] = None
    description: Optional[str] = None
    sources: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "unified_symbol": self.unified_symbol,
            "asset_type": self.asset_type,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "description": self.description,
            "sources": self.sources,
        }


@dataclass
class Quote:
    """A real-time quote (bid/ask)."""
    symbol: str
    ts: pd.Timestamp
    bid: float
    ask: float
    mid: Optional[float] = None

    def __post_init__(self):
        if self.mid is None:
            self.mid = (self.bid + self.ask) / 2


@dataclass
class Trade:
    """A single executed trade."""
    symbol: str
    ts: pd.Timestamp
    price: float
    qty: float
    side: str  # "buy" | "sell"


def df_to_ohlcv_list(df: pd.DataFrame, symbol: str, source: str = "",
                     timeframe: str = "1d") -> list[OHLCV]:
    """Convert a DataFrame (DatetimeIndex + OHLCV columns) to a list of OHLCV."""
    result = []
    for ts, row in df.iterrows():
        result.append(OHLCV(
            symbol=symbol, ts=ts,
            open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]), close=float(row["close"]),
            volume=float(row.get("volume", 0)),
            source=source, timeframe=timeframe,
        ))
    return result


def ohlcv_list_to_df(records: list[OHLCV]) -> pd.DataFrame:
    """Convert a list of OHLCV back to a DataFrame."""
    if not records:
        return pd.DataFrame()
    data = [r.to_dict() for r in records]
    df = pd.DataFrame(data)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts")
    return df[["open", "high", "low", "close", "volume"]]
