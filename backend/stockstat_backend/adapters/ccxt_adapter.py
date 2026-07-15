from __future__ import annotations

from typing import Optional

import ccxt
import pandas as pd

from .base import DataSourceAdapter


class CcxtAdapter(DataSourceAdapter):
    name = "ccxt"
    source_type = "crypto"

    _TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
        "1w": "1w",
    }

    def __init__(self, exchange_id: str = "binance", proxies: dict | None = None):
        self.exchange_id = exchange_id
        exchange_class = getattr(ccxt, exchange_id)
        config = {"enableRateLimit": True}
        if proxies:
            config["proxies"] = proxies
        self.exchange = exchange_class(config)

    def fetch_ohlcv(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        tf = self._TIMEFRAME_MAP.get(timeframe, "1d")

        since = None
        if start:
            since = self.exchange.parse8601(f"{start}T00:00:00Z")

        all_ohlcv = []
        limit = 1000

        while True:
            data = self.exchange.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=limit)
            if not data:
                break
            all_ohlcv.extend(data)
            last_ts = data[-1][0]
            if end:
                end_ms = self.exchange.parse8601(f"{end}T23:59:59Z")
                if last_ts >= end_ms:
                    all_ohlcv = [d for d in all_ohlcv if d[0] <= end_ms]
                    break
            since = last_ts + 1
            if len(data) < limit:
                break

        if not all_ohlcv:
            return pd.DataFrame()

        df = pd.DataFrame(all_ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts")
        return df

    def supports(self, symbol: str) -> bool:
        return "/" in symbol

    def health_check(self) -> bool:
        try:
            self.exchange.load_markets()
            return True
        except Exception:
            return False
