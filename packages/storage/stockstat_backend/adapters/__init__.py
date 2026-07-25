"""Adapters — 数据源适配器（Binance / YFinance）。"""
from __future__ import annotations

from .base import DataSource, get_adapter, list_adapters, ADAPTERS
from .binance import BinanceAdapter
from .yfinance import YFinanceAdapter
from .synthetic import SyntheticAdapter

__all__ = [
    "DataSource", "get_adapter", "list_adapters", "ADAPTERS",
    "BinanceAdapter", "YFinanceAdapter", "SyntheticAdapter",
]
