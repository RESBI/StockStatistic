"""v2.0 Python client with offline mode support.

Wraps the v1.7 ``StockStatClient`` and adds:
- Offline mode (direct Storage access, no HTTP)
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
    bypassing HTTP entirely. This is useful for:
    - Running backtests on pre-loaded data
    - Jupyter analysis without a backend server
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
            from ..._core.storage import MemoryStorage
            self._storage = kwargs.get("storage", MemoryStorage())
        else:
            raise ValueError(f"Unknown mode: {mode!r}. Use 'online' or 'offline'.")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from ..._core.plugin import get_registry
            self._registry = get_registry()
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
            raise RuntimeError("Ingest requires online mode")

    def symbols(self, asset_type: Optional[str] = None) -> list[dict]:
        if self._mode == "online":
            return self._online_client.symbols(asset_type=asset_type)
        else:
            # Offline: return from local storage
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
