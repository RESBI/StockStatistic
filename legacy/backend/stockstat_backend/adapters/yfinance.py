from __future__ import annotations

from typing import Optional

import pandas as pd
import yfinance as yf

from .base import DataSourceAdapter


class YFinanceAdapter(DataSourceAdapter):
    name = "yfinance"
    source_type = "stock"

    _INTERVAL_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "60m",
        "1d": "1d",
        "1w": "1wk",
        "1mo": "1mo",
    }

    def __init__(self, proxy: dict | None = None):
        self._proxies = proxy

    def _make_session(self):
        if not self._proxies:
            return None
        import requests
        session = requests.Session()
        session.proxies.update(self._proxies)
        return session

    def fetch_ohlcv(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        interval = self._INTERVAL_MAP.get(timeframe, "1d")

        session = self._make_session()
        ticker_kwargs = {}
        if session is not None:
            ticker_kwargs["session"] = session

        ticker = yf.Ticker(symbol, **ticker_kwargs)

        kwargs = {"interval": interval}
        if start and end:
            kwargs["start"] = start
            kwargs["end"] = end
        elif start:
            kwargs["start"] = start
            kwargs["period"] = "max"
        else:
            kwargs["period"] = "max"

        df = ticker.history(**kwargs)

        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })

        df = df[["open", "high", "low", "close", "volume"]].copy()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df.index.name = "ts"
        return df

    def supports(self, symbol: str) -> bool:
        return "/" not in symbol

    def health_check(self) -> bool:
        try:
            session = self._make_session()
            kwargs = {}
            if session is not None:
                kwargs["session"] = session
            yf.Ticker("AAPL", **kwargs).history(period="1d")
            return True
        except Exception:
            return False
