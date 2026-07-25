from __future__ import annotations

from typing import Optional

import pandas as pd


def fixed_size(qty: float) -> float:
    return qty


def fixed_amount(amount: float, price: float) -> float:
    if price <= 0:
        return 0.0
    return amount / price


def percent_equity(percent: float, equity: float, price: float) -> float:
    if price <= 0:
        return 0.0
    return (equity * percent) / price


def kelly_fraction(win_rate: float, win_loss_ratio: float, fraction: float = 1.0) -> float:
    """Kelly criterion fraction of equity. `fraction` for half/three-quarter Kelly."""
    k = win_rate - (1 - win_rate) / win_loss_ratio if win_loss_ratio > 0 else 0.0
    return max(0.0, k * fraction)


def atr_risk_budget(equity: float, risk_pct: float, atr: float, price: float,
                    multiplier: float = 1.0) -> float:
    """Position size so that a stop at `multiplier * ATR` risks `risk_pct` of equity."""
    if atr <= 0 or price <= 0:
        return 0.0
    risk_amount = equity * risk_pct
    stop_distance = multiplier * atr
    return risk_amount / stop_distance
