from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


def corr(x: pd.Series, y: pd.Series) -> float:
    aligned = pd.concat([x, y], axis=1, keys=["x", "y"]).dropna()
    if len(aligned) < 3:
        return float("nan")
    return aligned["x"].corr(aligned["y"])


def beta(asset: pd.Series, benchmark: pd.Series, window: int = 60) -> pd.Series:
    aligned = pd.concat([asset, benchmark], axis=1, keys=["asset", "bench"]).dropna()
    cov = aligned["asset"].rolling(window=window).cov(aligned["bench"])
    var = aligned["bench"].rolling(window=window).var()
    return cov / var


def sharpe(returns: pd.Series, risk_free: float = 0.02, annualize: bool = True) -> float:
    periods = 252 if annualize else 1
    excess = returns - risk_free / periods
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(periods))


def max_drawdown(close: pd.Series) -> float:
    cumret = close / close.iloc[0]
    running_max = cumret.cummax()
    drawdown = (cumret - running_max) / running_max
    return float(drawdown.min())


def var_historical(returns: pd.Series, confidence: float = 0.95) -> float:
    return float(np.percentile(returns.dropna(), (1 - confidence) * 100))


def returns(data: pd.Series) -> pd.Series:
    return data.pct_change()


def log_returns(data: pd.Series) -> pd.Series:
    return np.log(data / data.shift(1))
