from __future__ import annotations

from typing import Optional

import ccxt
import pandas as pd

from .base import DataSourceAdapter


class CcxtAdapter(DataSourceAdapter):
    name = "ccxt"
    source_type = "crypto"

    # All timeframes supported by Binance (and most ccxt exchanges)
    _TIMEFRAME_MAP = {
        "1s": "1s",
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1d",
        "3d": "3d",
        "1w": "1w",
        "1M": "1M",
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

    def fetch_symbols(self) -> list[dict]:
        try:
            self.exchange.load_markets()
        except Exception:
            return []
        result = []
        for sym, market in self.exchange.markets.items():
            result.append({
                "unified_symbol": sym,
                "base_asset": market.get("base"),
                "quote_asset": market.get("quote"),
                "asset_type": "crypto",
                "description": market.get("id", sym),
            })
        return result

    def health_check(self) -> bool:
        try:
            self.exchange.load_markets()
            return True
        except Exception:
            return False

    def probe_range(self, symbol: str, timeframe: str = "1d") -> tuple[str | None, str | None]:
        """Probe the source for the actual earliest and latest available bar timestamps.

        Returns (earliest_iso, latest_iso); either may be None on failure.
        """
        tf = self._TIMEFRAME_MAP.get(timeframe, "1d")
        earliest = None
        latest = None
        try:
            # Earliest: fetch the first bar since epoch
            data = self.exchange.fetch_ohlcv(symbol, timeframe=tf, since=0, limit=1)
            if data:
                earliest = pd.Timestamp(data[0][0], unit="ms", tz="UTC").isoformat()
        except Exception:
            pass
        try:
            # Latest: fetch the most recent bar
            now_ms = self.exchange.milliseconds()
            data = self.exchange.fetch_ohlcv(symbol, timeframe=tf, since=now_ms - 86400000, limit=1)
            if data:
                latest = pd.Timestamp(data[-1][0], unit="ms", tz="UTC").isoformat()
        except Exception:
            pass
        return earliest, latest
