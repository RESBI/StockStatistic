"""DataClient — OHLCV 数据访问客户端。"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from stockstat_foundation.codec import ArrowCodec


class DataClient:
    """OHLCV 数据访问客户端 — 通过 HTTP 访问 Storage。"""

    def __init__(self, base_url: str = "", *, http_client=None,
                 timeout: int = 30, cache_enabled: bool = True):
        self._base_url = base_url.rstrip("/") if base_url else ""
        if http_client is not None:
            self._http = http_client
        elif self._base_url:
            import httpx
            self._http = httpx.Client(timeout=timeout)
        else:
            self._http = None
        self._cache_enabled = cache_enabled
        self._cache: dict = {}

    @property
    def base_url(self) -> str:
        return self._base_url

    def ohlcv(self, symbol: str, timeframe: str = "1d",
              start: Optional[str] = None, end: Optional[str] = None,
              source: Optional[str] = None) -> pd.DataFrame:
        """查询 OHLCV 数据。"""
        cache_key = f"{symbol}:{timeframe}:{start}:{end}:{source}"
        if self._cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        if self._http is None:
            raise RuntimeError("DataClient has no base_url; cannot fetch OHLCV")

        params = {"symbol": symbol, "timeframe": timeframe}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if source:
            params["source"] = source

        resp = self._http.get(f"{self._base_url}/api/v1/ohlcv", params=params)
        resp.raise_for_status()
        df = ArrowCodec().decode(resp.content)

        if self._cache_enabled:
            self._cache[cache_key] = df
        return df

    def ingest(self, symbol: str, timeframe: str, data: pd.DataFrame) -> int:
        """写入 OHLCV 数据。"""
        if self._http is None:
            raise RuntimeError("DataClient has no base_url; cannot ingest")
        body = ArrowCodec().encode(data)
        resp = self._http.post(
            f"{self._base_url}/api/v1/ohlcv",
            content=body,
            headers={"Content-Type": "application/vnd.apache.arrow.file",
                     "X-Symbol": symbol, "X-Timeframe": timeframe},
        )
        return resp.json().get("rows_written", 0)

    def list_symbols(self) -> list:
        if self._http is None:
            return []
        try:
            resp = self._http.get(f"{self._base_url}/api/v1/symbols")
            return resp.json().get("symbols", [])
        except Exception:
            return []

    def clear_cache(self) -> None:
        self._cache.clear()


__all__ = ["DataClient"]
