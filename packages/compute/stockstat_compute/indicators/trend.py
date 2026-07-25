"""趋势指标。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _to_series(data) -> pd.Series:
    if isinstance(data, pd.Series):
        return data
    if isinstance(data, pd.DataFrame):
        return data.iloc[:, 0]
    return pd.Series(np.asarray(data, dtype=float))


def ma(data, window: int = 20) -> pd.Series:
    """简单移动平均。"""
    s = _to_series(data)
    return s.rolling(window=window, min_periods=window).mean()


def ema(data, window: int = 12) -> pd.Series:
    """指数移动平均。"""
    s = _to_series(data)
    return s.ewm(span=window, adjust=False).mean()


def wma(data, window: int = 20) -> pd.Series:
    """加权移动平均。"""
    s = _to_series(data)
    weights = np.arange(1, window + 1, dtype=float)
    weights = weights / weights.sum()
    return s.rolling(window=window).apply(lambda x: (x * weights).sum(), raw=True)


def dema(data, window: int = 20) -> pd.Series:
    """双指数移动平均。"""
    s = _to_series(data)
    e1 = s.ewm(span=window, adjust=False).mean()
    e2 = e1.ewm(span=window, adjust=False).mean()
    return 2 * e1 - e2


def tema(data, window: int = 20) -> pd.Series:
    """三指数移动平均。"""
    s = _to_series(data)
    e1 = s.ewm(span=window, adjust=False).mean()
    e2 = e1.ewm(span=window, adjust=False).mean()
    e3 = e2.ewm(span=window, adjust=False).mean()
    return 3 * e1 - 3 * e2 + e3


def hma(data, window: int = 20) -> pd.Series:
    """Hull 移动平均。"""
    s = _to_series(data)
    half = max(1, window // 2)
    sqrt_n = max(1, int(np.sqrt(window)))
    wma1 = s.rolling(window=half).apply(
        lambda x: (x * np.arange(1, len(x) + 1)).sum() / np.arange(1, len(x) + 1).sum(),
        raw=True
    )
    wma2 = s.rolling(window=window).apply(
        lambda x: (x * np.arange(1, len(x) + 1)).sum() / np.arange(1, len(x) + 1).sum(),
        raw=True
    )
    diff = 2 * wma1 - wma2
    return diff.rolling(window=sqrt_n).mean()


def moving_average(data, window: int = 20, method: str = "sma") -> pd.Series:
    """通用移动平均入口。"""
    method = method.lower()
    if method in ("sma", "ma"):
        return ma(data, window)
    if method == "ema":
        return ema(data, window)
    if method == "wma":
        return wma(data, window)
    if method == "dema":
        return dema(data, window)
    if method == "tema":
        return tema(data, window)
    if method == "hma":
        return hma(data, window)
    raise ValueError(f"Unknown MA method: {method}")


def macd(data, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD 指标。返回 DataFrame: macd / signal / histogram。"""
    s = _to_series(data)
    ema_fast = s.ewm(span=fast, adjust=False).mean()
    ema_slow = s.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({
        "macd": macd_line, "signal": signal_line, "histogram": hist,
    })


def adx(high, low, close, window: int = 14) -> pd.Series:
    """ADX 趋势强度指标。"""
    high = _to_series(high)
    low = _to_series(low)
    close = _to_series(close)
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[(plus_dm < minus_dm)] = 0
    minus_dm[(minus_dm < plus_dm)] = 0
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / window, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / window, adjust=False).mean() / atr_)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / window, adjust=False).mean() / atr_)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / window, adjust=False).mean()


def dpo(data, window: int = 20) -> pd.Series:
    """Detrended Price Oscillator。"""
    s = _to_series(data)
    shift = (window // 2) + 1
    return s - s.shift(shift).rolling(window=window).mean()


def trix(data, window: int = 12) -> pd.Series:
    """TRIX 指标。"""
    s = _to_series(data)
    e1 = s.ewm(span=window, adjust=False).mean()
    e2 = e1.ewm(span=window, adjust=False).mean()
    e3 = e2.ewm(span=window, adjust=False).mean()
    return e3.pct_change() * 100


__all__ = ["ma", "ema", "wma", "dema", "tema", "hma", "moving_average",
           "macd", "adx", "dpo", "trix"]
