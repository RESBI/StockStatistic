from __future__ import annotations

from typing import Optional

import httpx
import pandas as pd


class DataClient:
    def __init__(self, config, http_client=None):
        self._config = config
        self._base_url = config.base_url
        self._headers = {}
        if config.api_key:
            self._headers["Authorization"] = f"Bearer {config.api_key}"
        self._client = http_client

    def _get(self, path: str, params: dict = None) -> dict:
        if self._client is not None:
            resp = self._client.get(path, params=params)
        else:
            resp = httpx.get(
                f"{self._base_url}{path}",
                params=params,
                headers=self._headers,
                timeout=self._config.timeout,
            )
        if resp.status_code == 404:
            raise KeyError(resp.json().get("detail", "Not found"))
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, params: dict = None) -> dict:
        if self._client is not None:
            resp = self._client.post(path, params=params)
        else:
            resp = httpx.post(
                f"{self._base_url}{path}",
                params=params,
                headers=self._headers,
                timeout=self._config.timeout,
            )
        resp.raise_for_status()
        return resp.json()

    def ohlcv(
        self,
        symbol: str,
        source: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        params = {"symbol": symbol, "timeframe": timeframe}
        if source:
            params["source"] = source
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if limit:
            params["limit"] = limit

        result = self._get("/api/v1/ohlcv", params)
        df = pd.DataFrame(result["data"])
        if df.empty:
            return pd.DataFrame()
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df.set_index("ts")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df

    def ohlcv_batch(
        self,
        symbols: list[str],
        source: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        result = {}
        for sym in symbols:
            result[sym] = self.ohlcv(sym, source=source, start=start, end=end, timeframe=timeframe)
        return result

    def ingest(
        self,
        symbol: str,
        source: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        timeframe: str = "1d",
    ) -> dict:
        params = {"symbol": symbol, "timeframe": timeframe}
        if source:
            params["source"] = source
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self._post("/api/v1/ingest", params)

    def symbols(self, asset_type: Optional[str] = None) -> list[dict]:
        params = {}
        if asset_type:
            params["asset_type"] = asset_type
        return self._get("/api/v1/symbols", params)["symbols"]

    def sources(self) -> list[dict]:
        return self._get("/api/v1/sources")["sources"]

    def health(self) -> bool:
        try:
            self._get("/api/v1/health")
            return True
        except Exception:
            return False
