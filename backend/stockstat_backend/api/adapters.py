"""Public adapter management API.

Extracted from routes.py to allow plugins (e.g. admin) to access
data source adapters without importing private symbols.

All functions here are public API (no underscore prefix) and are
safe for external use.
"""
from __future__ import annotations

from typing import Optional

from ..config import settings
from ..adapters.yahoo_direct import YahooDirectAdapter
from ..adapters.ccxt_adapter import CcxtAdapter
from ..adapters.synthetic import SyntheticAdapter

# Module-level adapter cache (shared with routes.py)
_adapters: dict = {}


def get_adapter(source: str):
    """Get or create a data source adapter by name.

    Cached per source name. Uses current proxy settings.

    Args:
        source: Data source name (yfinance/binance/coinbase/synthetic).

    Returns:
        A DataSourceAdapter instance.

    Raises:
        ValueError: If source is unknown.
    """
    if source not in _adapters:
        proxies = settings.proxy.proxies
        if source == "yfinance":
            _adapters[source] = YahooDirectAdapter(proxy=proxies)
        elif source == "binance":
            _adapters[source] = CcxtAdapter("binance", proxies=proxies)
        elif source == "coinbase":
            _adapters[source] = CcxtAdapter("coinbase", proxies=proxies)
        elif source == "synthetic":
            _adapters[source] = SyntheticAdapter()
        else:
            raise ValueError(f"Unknown source: {source}")
    return _adapters[source]


def auto_detect_source(symbol: str) -> str:
    """Auto-detect data source from symbol format.

    Symbols containing '/' -> binance (crypto)
    Symbols without '/' -> yfinance (stock)
    """
    if "/" in symbol:
        return "binance"
    return "yfinance"


def clear_adapters():
    """Clear all cached adapters.

    Called after proxy configuration changes to force adapter
    rebuild with new proxy settings on next access.
    """
    _adapters.clear()
