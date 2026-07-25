"""波动率指标。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _to_series(data) -> pd.Series:
    if isinstance(data, pd.Series):
        return data
    if isinstance(data, pd.DataFrame):
        return data.iloc[:, 0]
    return pd.Series(np.asarray(data, dtype=float))


def bollinger(data, window: int = 20, std: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands。返回 upper/middle/lower。"""
    s = _to_series(data)
    middle = s.rolling(window=window).mean()
    sd = s.rolling(window=window).std()
    return pd.DataFrame({
        "upper": middle + std * sd,
        "middle": middle,
        "lower": middle - std * sd,
        "bandwidth": 4 * sd / middle.replace(0, np.nan),
    })


def atr(high, low, close, window: int = 14) -> pd.Series:
    """ATR 平均真实波幅。"""
    high = _to_series(high)
    low = _to_series(low)
    close = _to_series(close)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False).mean()


def keltner(high, low, close, window: int = 20, mult: float = 1.5) -> pd.DataFrame:
    """Keltner Channel。"""
    high = _to_series(high)
    low = _to_series(low)
    close = _to_series(close)
    middle = close.ewm(span=window, adjust=False).mean()
    atr_ = atr(high, low, close, window)
    return pd.DataFrame({
        "upper": middle + mult * atr_,
        "middle": middle,
        "lower": middle - mult * atr_,
    })


def donchian(high, low, window: int = 20) -> pd.DataFrame:
    """Donchian Channel。"""
    high = _to_series(high)
    low = _to_series(low)
    return pd.DataFrame({
        "upper": high.rolling(window=window).max(),
        "middle": (high.rolling(window=window).max() + low.rolling(window=window).min()) / 2,
        "lower": low.rolling(window=window).min(),
    })


def stddev(data, window: int = 20) -> pd.Series:
    """滚动标准差。"""
    return _to_series(data).rolling(window=window).std()


__all__ = ["bollinger", "atr", "keltner", "donchian", "stddev"]
