from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

from .base import DataSourceAdapter


class YahooDirectAdapter(DataSourceAdapter):
    """Direct Yahoo Finance API adapter (bypasses yfinance cookie/crumb issues)."""

    name = "yfinance"
    source_type = "stock"

    _INTERVAL_MAP = {
        "1d": "1d",
        "1w": "1wk",
        "1mo": "1mo",
        "1h": "60m",
        "5m": "5m",
        "15m": "15m",
    }

    _BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    def __init__(self, proxy: dict | None = None):
        self._proxies = proxy
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)
        if proxy:
            self._session.proxies.update(proxy)

    def fetch_ohlcv(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        interval = self._INTERVAL_MAP.get(timeframe, "1d")

        period1 = 0
        period2 = int(time.time())
        if start:
            period1 = int(pd.Timestamp(start, tz="UTC").timestamp())
        if end:
            period2 = int(pd.Timestamp(end, tz="UTC").timestamp())

        url = f"{self._BASE_URL}/{symbol}"
        params = {
            "period1": period1,
            "period2": period2,
            "interval": interval,
            "events": "div,split",
        }

        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            raise RuntimeError(f"Yahoo API rate limited for {symbol}")
        resp.raise_for_status()

        data = resp.json()
        result = data.get("chart", {}).get("result")
        if not result:
            return pd.DataFrame()

        quote = result[0]
        timestamps = quote.get("timestamp", [])
        indicators = quote.get("indicators", {}).get("quote", [{}])[0]

        df = pd.DataFrame({
            "open": indicators.get("open"),
            "high": indicators.get("high"),
            "low": indicators.get("low"),
            "close": indicators.get("close"),
            "volume": indicators.get("volume"),
        }, index=pd.to_datetime(timestamps, unit="s", utc=True))
        df.index.name = "ts"

        df = df.dropna(subset=["open", "high", "low", "close"])
        return df

    def supports(self, symbol: str) -> bool:
        return "/" not in symbol

    def health_check(self) -> bool:
        try:
            resp = self._session.get(
                f"{self._BASE_URL}/AAPL",
                params={"period1": int(time.time()) - 86400, "period2": int(time.time()), "interval": "1d"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False
