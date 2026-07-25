"""振荡指标。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _to_series(data) -> pd.Series:
    if isinstance(data, pd.Series):
        return data
    if isinstance(data, pd.DataFrame):
        return data.iloc[:, 0]
    return pd.Series(np.asarray(data, dtype=float))


def rsi(data, window: int = 14) -> pd.Series:
    """RSI 相对强弱指标。"""
    s = _to_series(data)
    delta = s.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def kd(high, low, close, k_window: int = 9, d_window: int = 3) -> pd.DataFrame:
    """KD 随机指标。"""
    high = _to_series(high)
    low = _to_series(low)
    close = _to_series(close)
    lowest_low = low.rolling(window=k_window).min()
    highest_high = high.rolling(window=k_window).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
    k = rsv.ewm(alpha=1 / d_window, adjust=False).mean()
    d = k.ewm(alpha=1 / d_window, adjust=False).mean()
    j = 3 * k - 2 * d
    return pd.DataFrame({"K": k, "D": d, "J": j})


def williams_r(high, low, close, window: int = 14) -> pd.Series:
    """Williams %R。"""
    high = _to_series(high)
    low = _to_series(low)
    close = _to_series(close)
    hh = high.rolling(window=window).max()
    ll = low.rolling(window=window).min()
    return -100 * (hh - close) / (hh - ll).replace(0, np.nan)


def cci(high, low, close, window: int = 20) -> pd.Series:
    """CCI 商品通道指标。"""
    high = _to_series(high)
    low = _to_series(low)
    close = _to_series(close)
    tp = (high + low + close) / 3
    ma_tp = tp.rolling(window=window).mean()
    md = tp.rolling(window=window).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - ma_tp) / (0.015 * md.replace(0, np.nan))


def stoch(high, low, close, k_window: int = 14, d_window: int = 3) -> pd.DataFrame:
    """Stochastic Oscillator。"""
    return kd(high, low, close, k_window, d_window).rename(columns={"J": "J"})


__all__ = ["rsi", "kd", "williams_r", "cci", "stoch"]
