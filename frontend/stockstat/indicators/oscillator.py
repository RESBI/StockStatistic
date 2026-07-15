from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(data: pd.Series, window: int = 14) -> pd.Series:
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi_val = 100.0 - (100.0 / (1.0 + rs))
    return rsi_val


def kdj(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    lowest_low = low.rolling(window=window).min()
    highest_high = high.rolling(window=window).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100.0
    k = rsv.ewm(alpha=1.0 / 3, adjust=False).mean()
    d = k.ewm(alpha=1.0 / 3, adjust=False).mean()
    j = 3.0 * k - 2.0 * d
    return k, d, j
