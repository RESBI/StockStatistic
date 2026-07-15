from __future__ import annotations

from typing import Optional

import pandas as pd

from ..indicators import trend, oscillator, volatility, statistics
from .registry import register, call_indicator, list_indicators


class ComputeEngine:
    def __init__(self, client):
        self._client = client

    def ma(self, data: pd.Series, window: int = 20) -> pd.Series:
        return trend.ma(data, window)

    def ema(self, data: pd.Series, window: int = 12) -> pd.Series:
        return trend.ema(data, window)

    def macd(self, data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        return trend.macd(data, fast, slow, signal)

    def rsi(self, data: pd.Series, window: int = 14) -> pd.Series:
        return oscillator.rsi(data, window)

    def kdj(self, high: pd.Series, low: pd.Series, close: pd.Series, window: int = 9):
        return oscillator.kdj(high, low, close, window)

    def std(self, data: pd.Series, window: int = 20) -> pd.Series:
        return volatility.std(data, window)

    def atr(self, high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        return volatility.atr(high, low, close, window)

    def bollinger(self, data: pd.Series, window: int = 20, k: float = 2.0):
        return volatility.bollinger(data, window, k)

    def corr(self, x: pd.Series, y: pd.Series) -> float:
        return statistics.corr(x, y)

    def beta(self, asset: pd.Series, benchmark: pd.Series, window: int = 60) -> pd.Series:
        return statistics.beta(asset, benchmark, window)

    def sharpe(self, returns: pd.Series, risk_free: float = 0.02, annualize: bool = True) -> float:
        return statistics.sharpe(returns, risk_free, annualize)

    def max_drawdown(self, close: pd.Series) -> float:
        return statistics.max_drawdown(close)

    def var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        return statistics.var_historical(returns, confidence)

    def returns(self, data: pd.Series) -> pd.Series:
        return statistics.returns(data)

    def log_returns(self, data: pd.Series) -> pd.Series:
        return statistics.log_returns(data)

    def register(self, name: str, func=None, category: str = "custom"):
        if func is not None:
            register(name, func, category)
            return func
        def decorator(f):
            register(name, f, category)
            return f
        return decorator

    def call(self, name: str, **kwargs):
        return call_indicator(name, **kwargs)

    def list_indicators(self) -> list[dict]:
        return list_indicators()
