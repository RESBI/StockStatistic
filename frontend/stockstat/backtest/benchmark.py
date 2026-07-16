from __future__ import annotations

from typing import Optional

import pandas as pd


def buy_and_hold(initial_cash: float, prices: pd.Series) -> pd.Series:
    """Equity curve of buying and holding with all initial cash at first price."""
    if prices.empty:
        return pd.Series(dtype=float)
    shares = initial_cash / prices.iloc[0]
    return shares * prices


def benchmark_equity(initial_cash: float, prices: pd.Series) -> pd.Series:
    return buy_and_hold(initial_cash, prices)
