"""Data source adapter plugins.

Registers the v1.7 adapters (YahooDirectAdapter, CcxtAdapter,
SyntheticAdapter) to the v2.0 PluginRegistry under the ``sources``
namespace. The adapter implementations themselves remain in
``stockstat_backend.adapters`` — this module provides the plugin
registration bridge.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


class DataSourcePlugin:
    """Plugin wrapper for a data source adapter.

    Wraps any object with ``fetch_ohlcv(symbol, start, end, timeframe)``
    and ``supports(symbol)`` methods (the v1.7 DataSourceAdapter
    interface) and exposes it as a v2.0 plugin.
    """
    category = "sources"

    def __init__(self, name: str, adapter: Any, description: str = "") -> None:
        self.name = name
        self.version = "1.0"
        self.description = description
        self._adapter = adapter

    def initialize(self, context: Any) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        try:
            return self._adapter.health_check()
        except Exception:
            return False

    @property
    def adapter(self) -> Any:
        return self._adapter

    def fetch_ohlcv(self, symbol: str, start: Optional[str] = None,
                    end: Optional[str] = None, timeframe: str = "1d") -> pd.DataFrame:
        return self._adapter.fetch_ohlcv(symbol, start=start, end=end, timeframe=timeframe)

    def fetch_symbols(self) -> list[dict]:
        return self._adapter.fetch_symbols()

    def supports(self, symbol: str) -> bool:
        return self._adapter.supports(symbol)


def register_default_sources(registry: Any) -> None:
    """Register all built-in data source adapters to the registry.

    This function attempts to import the v1.7 backend adapters. If the
    backend is not installed (frontend-only environment), it skips
    silently.
    """
    try:
        from stockstat_backend.adapters.yahoo_direct import YahooDirectAdapter
        from stockstat_backend.adapters.ccxt_adapter import CcxtAdapter
        from stockstat_backend.adapters.synthetic import SyntheticAdapter
        from stockstat_backend.config import settings

        proxies = settings.proxy.proxies

        registry.register("sources", "yfinance",
                          DataSourcePlugin("yfinance", YahooDirectAdapter(proxy=proxies),
                                           "Yahoo Finance direct API"))
        registry.register("sources", "binance",
                          DataSourcePlugin("binance", CcxtAdapter("binance", proxies=proxies),
                                           "Binance via ccxt"))
        registry.register("sources", "coinbase",
                          DataSourcePlugin("coinbase", CcxtAdapter("coinbase", proxies=proxies),
                                           "Coinbase via ccxt"))
        registry.register("sources", "synthetic",
                          DataSourcePlugin("synthetic", SyntheticAdapter(),
                                           "Synthetic data for offline testing"))
    except ImportError:
        pass  # Backend not available


def get_source(registry: Any, name: str) -> Optional[DataSourcePlugin]:
    """Look up a data source plugin by name."""
    return registry.get("sources", name)


def list_sources(registry: Any) -> list[dict]:
    """List all registered data sources."""
    return [{"name": p.name, "description": p.description}
            for p in [item["plugin"] for item in registry.list("sources")]]
