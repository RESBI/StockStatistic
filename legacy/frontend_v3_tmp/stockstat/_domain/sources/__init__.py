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

    def probe_range(self, symbol: str, timeframe: str = "1d") -> tuple[str | None, str | None]:
        if hasattr(self._adapter, "probe_range"):
            return self._adapter.probe_range(symbol, timeframe)
        return None, None


class _LazySourcePlugin:
    """Lazy data source plugin that creates the adapter on first use.

    Used when the backend package is not installed — the actual adapter
    (ccxt/yfinance) is instantiated only when fetch_ohlcv() is first
    called, so missing optional deps (ccxt, requests) don't cause
    import errors at registration time.
    """
    category = "sources"

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.version = "1.0"
        self.description = description
        self._adapter: Any = None
        self._initialized = False

    def _ensure_adapter(self) -> Any:
        if not self._initialized:
            self._adapter = _create_local_adapter(self.name)
            self._initialized = True
        return self._adapter

    def initialize(self, context: Any) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        adapter = self._ensure_adapter()
        if adapter is None:
            return False
        try:
            return adapter.health_check()
        except Exception:
            return False

    @property
    def adapter(self) -> Any:
        return self._ensure_adapter()

    def fetch_ohlcv(self, symbol: str, start: Optional[str] = None,
                    end: Optional[str] = None, timeframe: str = "1d") -> pd.DataFrame:
        adapter = self._ensure_adapter()
        if adapter is None:
            raise RuntimeError(
                f"Data source '{self.name}' is not available. "
                f"Install the required package (ccxt for crypto, requests for yfinance) "
                f"or install stockstat-backend."
            )
        return adapter.fetch_ohlcv(symbol, start=start, end=end, timeframe=timeframe)

    def fetch_symbols(self) -> list[dict]:
        adapter = self._ensure_adapter()
        if adapter is None:
            return []
        if hasattr(adapter, "fetch_symbols"):
            return adapter.fetch_symbols()
        return []

    def supports(self, symbol: str) -> bool:
        adapter = self._ensure_adapter()
        if adapter is None:
            return False
        return adapter.supports(symbol)

    def probe_range(self, symbol: str, timeframe: str = "1d") -> tuple[str | None, str | None]:
        adapter = self._ensure_adapter()
        if adapter is None:
            return None, None
        if hasattr(adapter, "probe_range"):
            return adapter.probe_range(symbol, timeframe)
        return None, None


def _create_adapters(proxies: dict | None = None) -> list[tuple[str, Any, str]]:
    """Create adapter instances, trying backend package first then frontend-local.

    Returns list of (name, adapter_instance, description) tuples.
    """
    adapters: list[tuple[str, Any, str]] = []

    # Path 1: backend package installed (full adapters with fetch_symbols/probe_range)
    try:
        from stockstat_backend.adapters.yahoo_direct import YahooDirectAdapter
        from stockstat_backend.adapters.ccxt_adapter import CcxtAdapter
        from stockstat_backend.adapters.synthetic import SyntheticAdapter

        adapters.append(("yfinance", YahooDirectAdapter(proxy=proxies), "Yahoo Finance direct API"))
        adapters.append(("binance", CcxtAdapter("binance", proxies=proxies), "Binance via ccxt"))
        adapters.append(("coinbase", CcxtAdapter("coinbase", proxies=proxies), "Coinbase via ccxt"))
        adapters.append(("synthetic", SyntheticAdapter(), "Synthetic data for offline testing"))
        return adapters
    except ImportError:
        pass

    # Path 2: frontend-local adapters (lightweight, fetch_ohlcv only)
    # These are created on-demand by _create_local_adapter() to avoid
    # importing ccxt/yfinance at module level when not needed.
    return []


def _create_local_adapter(source: str, proxies: dict | None = None) -> Any | None:
    """Create a frontend-local data source adapter (no backend dependency).

    Each adapter is a thin wrapper that directly calls the data source
    API (Yahoo/ccxt), independent of stockstat_backend.
    """
    if source == "synthetic":
        # Synthetic adapter has no external deps, always available
        try:
            from stockstat_backend.adapters.synthetic import SyntheticAdapter
            return SyntheticAdapter()
        except ImportError:
            from ._local_synthetic import LocalSyntheticAdapter
            return LocalSyntheticAdapter()

    if source in ("binance", "coinbase"):
        try:
            import ccxt
            exchange_class = getattr(ccxt, source)
            config: dict = {"enableRateLimit": True}
            if proxies:
                config["proxies"] = proxies
            exchange = exchange_class(config)

            class _LocalCcxtAdapter:
                name = source
                source_type = "crypto"
                _exchange = exchange

                _TIMEFRAME_MAP = {
                    "1s": "1s", "1m": "1m", "3m": "3m", "5m": "5m",
                    "15m": "15m", "30m": "30m", "1h": "1h", "2h": "2h",
                    "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
                    "1d": "1d", "3d": "3d", "1w": "1w", "1M": "1M",
                }

                def fetch_ohlcv(self, symbol, start=None, end=None, timeframe="1d"):
                    import pandas as pd
                    tf = self._TIMEFRAME_MAP.get(timeframe, "1d")
                    since = None
                    if start:
                        since = self._exchange.parse8601(f"{start}T00:00:00Z")
                    all_data = []
                    limit = 1000
                    while True:
                        data = self._exchange.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=limit)
                        if not data:
                            break
                        all_data.extend(data)
                        last_ts = data[-1][0]
                        if end:
                            end_ms = self._exchange.parse8601(f"{end}T23:59:59Z")
                            if last_ts >= end_ms:
                                all_data = [d for d in all_data if d[0] <= end_ms]
                                break
                        since = last_ts + 1
                        if len(data) < limit:
                            break
                    if not all_data:
                        return pd.DataFrame()
                    df = pd.DataFrame(all_data, columns=["ts", "open", "high", "low", "close", "volume"])
                    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
                    return df.set_index("ts")

                def supports(self, symbol):
                    return "/" in symbol

                def probe_range(self, symbol, timeframe="1d"):
                    tf = self._TIMEFRAME_MAP.get(timeframe, "1d")
                    earliest = latest = None
                    import pandas as pd
                    try:
                        data = self._exchange.fetch_ohlcv(symbol, timeframe=tf, since=0, limit=1)
                        if data:
                            earliest = pd.Timestamp(data[0][0], unit="ms", tz="UTC").isoformat()
                    except Exception:
                        pass
                    try:
                        now_ms = self._exchange.milliseconds()
                        data = self._exchange.fetch_ohlcv(symbol, timeframe=tf, since=now_ms - 86400000, limit=1)
                        if data:
                            latest = pd.Timestamp(data[-1][0], unit="ms", tz="UTC").isoformat()
                    except Exception:
                        pass
                    return earliest, latest

            return _LocalCcxtAdapter()
        except ImportError:
            return None

    if source == "yfinance":
        try:
            import requests
            import time as _time

            class _LocalYahooAdapter:
                name = "yfinance"
                source_type = "stock"
                _BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
                _HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

                _INTERVAL_MAP = {
                    "1m": "1m", "2m": "2m", "5m": "5m", "15m": "15m",
                    "30m": "30m", "60m": "60m", "90m": "90m", "1h": "60m",
                    "1d": "1d", "5d": "5d", "1wk": "1wk", "1w": "1wk",
                    "1mo": "1mo", "3mo": "3mo",
                }

                def __init__(self_self_):
                    self_self_._session = requests.Session()
                    self_self_._session.headers.update(self_self_._HEADERS)
                    if proxies:
                        self_self_._session.proxies.update(proxies)

                def fetch_ohlcv(self_self_, symbol, start=None, end=None, timeframe="1d"):
                    import pandas as pd
                    interval = self_self_._INTERVAL_MAP.get(timeframe, "1d")
                    period1 = 0
                    period2 = int(_time.time())
                    if start:
                        period1 = int(pd.Timestamp(start, tz="UTC").timestamp())
                    if end:
                        period2 = int(pd.Timestamp(end, tz="UTC").timestamp())
                    url = f"{self_self_._BASE_URL}/{symbol}"
                    params = {"period1": period1, "period2": period2, "interval": interval, "events": "div,split"}
                    resp = self_self_._session.get(url, params=params, timeout=30)
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
                    return df.dropna(subset=["open", "high", "low", "close"])

                def supports(self_self_, symbol):
                    return "/" not in symbol

                def probe_range(self_self_, symbol, timeframe="1d"):
                    import pandas as pd
                    interval = self_self_._INTERVAL_MAP.get(timeframe, "1d")
                    now = int(_time.time())
                    earliest = latest = None
                    try:
                        url = f"{self_self_._BASE_URL}/{symbol}"
                        params = {"period1": 0, "period2": now, "interval": interval, "events": "div,split"}
                        resp = self_self_._session.get(url, params=params, timeout=20)
                        if resp.status_code == 200:
                            data = resp.json()
                            result = data.get("chart", {}).get("result")
                            if result:
                                timestamps = result[0].get("timestamp", [])
                                if timestamps:
                                    earliest = pd.Timestamp(timestamps[0], unit="s", tz="UTC").isoformat()
                                    latest = pd.Timestamp(timestamps[-1], unit="s", tz="UTC").isoformat()
                    except Exception:
                        pass
                    return earliest, latest

            adapter = _LocalYahooAdapter()
            return adapter
        except ImportError:
            return None

    return None


def register_default_sources(registry: Any) -> None:
    """Register all built-in data source adapters to the registry.

    Tries backend package first; if not installed, registers a lazy
    resolver that creates frontend-local adapters on demand.
    """
    adapters = _create_adapters()

    if adapters:
        # Backend package available — register full adapters
        for name, adapter, desc in adapters:
            registry.register("sources", name,
                              DataSourcePlugin(name, adapter, desc))
    else:
        # Backend not installed — register lazy adapters
        # Synthetic is always available (no external deps)
        from ._local_synthetic import LocalSyntheticAdapter
        registry.register("sources", "synthetic",
                          DataSourcePlugin("synthetic", LocalSyntheticAdapter(),
                                           "Synthetic data for offline testing"))
        # yfinance / binance / coinbase are registered as lazy:
        # the adapter is created on first use via _create_local_adapter()
        for name, desc in [("yfinance", "Yahoo Finance direct API (frontend-local)"),
                           ("binance", "Binance via ccxt (frontend-local)"),
                           ("coinbase", "Coinbase via ccxt (frontend-local)")]:
            registry.register("sources", name,
                              _LazySourcePlugin(name, desc))


def get_source(registry: Any, name: str) -> Optional[DataSourcePlugin]:
    """Look up a data source plugin by name."""
    return registry.get("sources", name)


def list_sources(registry: Any) -> list[dict]:
    """List all registered data sources."""
    return [{"name": p.name, "description": p.description}
            for p in [item["plugin"] for item in registry.list("sources")]]
