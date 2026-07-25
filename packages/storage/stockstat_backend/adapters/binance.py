"""BinanceAdapter — Binance 行情数据。"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import register_adapter


@register_adapter("binance")
class BinanceAdapter:
    """Binance 行情数据适配器。"""
    name = "binance"

    def __init__(self, *, api_key: str = "", api_secret: str = "",
                 testnet: bool = False, base_url: Optional[str] = None):
        self._base_url = base_url or (
            "https://testnet.binance.vision" if testnet else "https://api.binance.com"
        )
        self._api_key = api_key
        self._api_secret = api_secret

    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> pd.DataFrame:
        """从 Binance 拉取 K 线数据。"""
        import httpx
        params = {"symbol": symbol, "interval": timeframe, "limit": 1000}
        if start:
            params["startTime"] = int(pd.Timestamp(start).timestamp() * 1000)
        if end:
            params["endTime"] = int(pd.Timestamp(end).timestamp() * 1000)
        resp = httpx.get(f"{self._base_url}/api/v3/klines", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df[["timestamp", "open", "high", "low", "close", "volume"]]


__all__ = ["BinanceAdapter"]
