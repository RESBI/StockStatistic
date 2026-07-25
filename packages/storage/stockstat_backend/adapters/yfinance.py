"""YFinanceAdapter — 股票/ETF 数据。"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import register_adapter


@register_adapter("yfinance")
class YFinanceAdapter:
    """YFinance 适配器。"""
    name = "yfinance"

    def __init__(self, **kwargs):
        pass

    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as e:
            raise ImportError(
                "YFinanceAdapter requires 'yfinance'. "
                "Install with: pip install stockstat-backend[yfinance]"
            ) from e
        interval = timeframe
        # yfinance 不支持 1d 之外的某些 interval
        if timeframe == "1d":
            interval = "1d"
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval)
        df = df.reset_index()
        df = df.rename(columns={"Date": "timestamp", "Datetime": "timestamp"})
        return df[["timestamp", "Open", "High", "Low", "Close", "Volume"]].rename(
            columns={"Open": "open", "High": "high", "Low": "low",
                     "Close": "close", "Volume": "volume"}
        )


__all__ = ["YFinanceAdapter"]
