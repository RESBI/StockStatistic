"""统计指标。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _to_series(data) -> pd.Series:
    if isinstance(data, pd.Series):
        return data
    if isinstance(data, pd.DataFrame):
        return data.iloc[:, 0]
    return pd.Series(np.asarray(data, dtype=float))


def rolling_mean(data, window: int = 20) -> pd.Series:
    return _to_series(data).rolling(window=window).mean()


def rolling_std(data, window: int = 20) -> pd.Series:
    return _to_series(data).rolling(window=window).std()


def rolling_corr(x, y, window: int = 20) -> pd.Series:
    """滚动相关系数。"""
    return _to_series(x).rolling(window=window).corr(_to_series(y))


def rolling_beta(asset, market, window: int = 20) -> pd.Series:
    """滚动 Beta。"""
    a = _to_series(asset)
    m = _to_series(market)
    cov = a.rolling(window=window).cov(m)
    var = m.rolling(window=window).var()
    return cov / var.replace(0, np.nan)


def zscore(data, window: int = 20) -> pd.Series:
    """滚动 Z-Score。"""
    s = _to_series(data)
    return (s - s.rolling(window=window).mean()) / s.rolling(window=window).std().replace(0, np.nan)


def percentile(data, window: int = 20) -> pd.Series:
    """滚动百分位。"""
    s = _to_series(data)
    return s.rolling(window=window).apply(
        lambda x: (x[-1] - x.min()) / (x.max() - x.min()) if (x.max() - x.min()) > 0 else 0.5,
        raw=True
    )


__all__ = ["rolling_mean", "rolling_std", "rolling_corr", "rolling_beta",
           "zscore", "percentile"]
