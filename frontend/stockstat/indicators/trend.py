from __future__ import annotations

import numpy as np
import pandas as pd


def ma(data: pd.Series, window: int = 20) -> pd.Series:
    return data.rolling(window=window).mean()


def ema(data: pd.Series, window: int = 12) -> pd.Series:
    return data.ewm(span=window, adjust=False).mean()


def macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = data.ewm(span=fast, adjust=False).mean()
    ema_slow = data.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
