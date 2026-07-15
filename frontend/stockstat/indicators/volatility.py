from __future__ import annotations

import numpy as np
import pandas as pd


def std(data: pd.Series, window: int = 20) -> pd.Series:
    return data.rolling(window=window).std()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=window).mean()


def bollinger(data: pd.Series, window: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = data.rolling(window=window).mean()
    sigma = data.rolling(window=window).std()
    upper = mid + k * sigma
    lower = mid - k * sigma
    return upper, mid, lower
