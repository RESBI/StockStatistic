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


def dca_equity(initial_cash: float, prices: pd.Series,
               schedule: str = "auto") -> pd.Series:
    """Dollar-cost average equity curve.

    Splits initial_cash evenly across investment points and invests at each.

    Args:
        initial_cash: Total cash to invest over the period.
        prices: Price series (e.g., daily close).
        schedule: "auto" (invest at every bar), "weekly", "monthly".

    Returns:
        Equity curve (cash + position value) aligned to prices index.
    """
    if prices.empty:
        return pd.Series(dtype=float)

    if schedule == "weekly":
        invest_mask = pd.Series(False, index=prices.index)
        seen_weeks = set()
        for ts in prices.index:
            week = ts.strftime("%Y-W%W")
            if week not in seen_weeks:
                seen_weeks.add(week)
                invest_mask.loc[ts] = True
    elif schedule == "monthly":
        invest_mask = pd.Series(False, index=prices.index)
        seen_months = set()
        for ts in prices.index:
            month = ts.strftime("%Y-%m")
            if month not in seen_months:
                seen_months.add(month)
                invest_mask.loc[ts] = True
    else:
        invest_mask = pd.Series(True, index=prices.index)

    n_invests = invest_mask.sum()
    invest_per_period = initial_cash / n_invests if n_invests > 0 else 0

    qty = 0.0
    cash = initial_cash
    equity_values = []

    for i, (ts, price) in enumerate(prices.items()):
        if invest_mask.iloc[i]:
            buy_qty = invest_per_period / price
            qty += buy_qty
            cash -= invest_per_period
        equity_values.append(cash + qty * price)

    return pd.Series(equity_values, index=prices.index, name="DCA")
