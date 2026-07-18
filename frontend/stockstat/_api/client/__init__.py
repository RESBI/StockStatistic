"""v2.0 Python client with offline mode support.

Wraps the v1.7 ``StockStatClient`` and adds:
- Offline mode (direct Storage access, no HTTP)
- Direct data source download in offline mode (via PluginRegistry adapters)
- Plugin registry integration
- Codec negotiation
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


class V2Client:
    """v2.0 client with plugin registry and offline mode.

    In **online mode** (default), delegates to the v1.7
    ``StockStatClient`` for HTTP communication with the backend.

    In **offline mode**, uses a local ``StorageBackend`` directly,
    bypassing HTTP entirely. Data can be:
    - Pre-loaded via ``storage.write()``
    - Downloaded from data sources via ``ingest()`` (uses adapters
      from the PluginRegistry — requires ccxt/requests installed)
    - Read from an existing SQLite database via ``SQLStorage``

    This is useful for:
    - Running backtests on pre-loaded data
    - Jupyter analysis without a backend server
    - Downloading data directly in Python without starting a server
    - Testing without network access
    """

    def __init__(self, mode: str = "online", **kwargs: Any) -> None:
        self._mode = mode
        self._online_client: Optional[Any] = None
        self._storage: Optional[Any] = None
        self._registry: Optional[Any] = None

        if mode == "online":
            from ...client import StockStatClient
            self._online_client = StockStatClient(**kwargs)
        elif mode == "offline":
            storage = kwargs.get("storage")
            if storage is None:
                from ..._core.storage import MemoryStorage
                storage = MemoryStorage()
            self._storage = storage
        else:
            raise ValueError(f"Unknown mode: {mode!r}. Use 'online' or 'offline'.")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from ..._core.plugin import PluginRegistry
            from ..._domain.indicators import register_default_indicators
            from ..._domain.sources import register_default_sources

            reg = PluginRegistry()
            register_default_sources(reg)
            register_default_indicators(reg)
            self._registry = reg
        return self._registry

    # ── Data access (works in both modes) ────────────────────

    def ohlcv(self, symbol: str, source: Optional[str] = None,
               start: Optional[str] = None, end: Optional[str] = None,
               timeframe: str = "1d", limit: Optional[int] = None) -> pd.DataFrame:
        if self._mode == "online":
            return self._online_client.ohlcv(
                symbol=symbol, source=source, start=start, end=end,
                timeframe=timeframe, limit=limit,
            )
        else:
            # Offline: query local storage
            filters = {"symbol": symbol}
            if source:
                filters["source"] = source
            filters["timeframe"] = timeframe
            return self._storage.query(
                "ohlcv", filters=filters, start=start, end=end, limit=limit,
            )

    def ingest(self, symbol: str, source: Optional[str] = None,
               start: Optional[str] = None, end: Optional[str] = None,
               timeframe: str = "1d") -> dict:
        if self._mode == "online":
            return self._online_client.ingest(
                symbol=symbol, source=source, start=start, end=end,
                timeframe=timeframe,
            )
        else:
            # Offline: fetch directly from data source adapter
            return self._ingest_offline(symbol, source, start, end, timeframe)

    def _ingest_offline(self, symbol: str, source: Optional[str] = None,
                        start: Optional[str] = None, end: Optional[str] = None,
                        timeframe: str = "1d") -> dict:
        """Download data from a data source and store it locally.

        Uses the PluginRegistry's ``sources`` namespace to find an
        adapter, fetches OHLCV data, normalizes it, and writes to the
        local Storage. No HTTP backend required.
        """
        # Auto-detect source if not specified
        if source is None:
            source = "binance" if "/" in symbol else "yfinance"

        # Get adapter from registry
        plugin = self.registry.get("sources", source)
        if plugin is None:
            raise ValueError(
                f"Data source '{source}' is not registered. "
                f"Available: {[item['name'] for item in self.registry.list('sources')]}"
            )

        # Fetch raw data
        df = plugin.fetch_ohlcv(symbol, start=start, end=end, timeframe=timeframe)
        if df.empty:
            return {"symbol": symbol, "source": source, "ingested": 0}

        # Normalize: ensure UTC timezone, required columns
        df = df.copy()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing required OHLCV columns: {missing}")
        df = df[list(required)].dropna(subset=["open", "high", "low", "close"])

        # Convert to records for storage
        records = []
        for ts, row in df.iterrows():
            records.append({
                "symbol": symbol,
                "ts": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
                "source": source,
                "timeframe": timeframe,
            })

        count = self._storage.upsert("ohlcv", records)
        return {"symbol": symbol, "source": source, "ingested": count}

    def symbols(self, asset_type: Optional[str] = None) -> list[dict]:
        if self._mode == "online":
            return self._online_client.symbols(asset_type=asset_type)
        else:
            # Offline: return empty (no symbol registry in local storage)
            return []

    # ── Compute (works in both modes) ────────────────────────

    @property
    def compute(self) -> Any:
        if self._mode == "online":
            return self._online_client.compute
        else:
            from ...compute.engine import ComputeEngine
            return ComputeEngine(client=None)

    # ── DSL ──────────────────────────────────────────────────

    def run_dsl(self, dsl_string: str) -> pd.DataFrame:
        if self._mode == "online":
            return self._online_client.run_dsl(dsl_string)
        else:
            from ..dsl import DslEngine
            engine = DslEngine(self.registry, client=self)
            return engine.eval(dsl_string)

    # ── Backtest ─────────────────────────────────────────────

    def backtest(self, data: Any, strategy: Any, **kwargs: Any) -> Any:
        from ...backtest import BacktestEngine
        if self._mode == "online":
            return self._online_client.backtest(data, strategy, **kwargs)
        else:
            kwargs.setdefault("compute_engine", self.compute)
            return BacktestEngine(data=data, strategy=strategy, **kwargs).run()

    # ── Plot ─────────────────────────────────────────────────

    @property
    def plot(self) -> Any:
        if self._mode == "online":
            return self._online_client.plot
        else:
            from ...client import PlotAPI
            return PlotAPI()
