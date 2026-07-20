from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .result import BacktestResult


def bootstrap_returns(returns: pd.Series, n_samples: int = 1000,
                      seed: int = 0) -> list[pd.Series]:
    """Resample returns with replacement to generate alternative equity paths."""
    rng = np.random.RandomState(seed)
    n = len(returns)
    samples = []
    for _ in range(n_samples):
        idx = rng.randint(0, n, size=n)
        samples.append(returns.iloc[idx].reset_index(drop=True))
    return samples


def shuffle_orders(fills: list, seed: int = 0) -> list:
    """Return a copy of fills with timestamps reshuffled (order-shuffle MC)."""
    rng = np.random.RandomState(seed)
    if not fills:
        return []
    ts_list = [f.ts for f in fills]
    perm = rng.permutation(len(ts_list))
    out = []
    for f, new_ts in zip(fills, [ts_list[p] for p in perm]):
        out.append(type(f)(
            order_id=f.order_id, symbol=f.symbol, side=f.side, qty=f.qty,
            price=f.price, commission=f.commission, slippage_cost=f.slippage_cost,
            ts=new_ts, tag=f.tag,
        ))
    return out


def monte_carlo_equity(returns: pd.Series, initial: float,
                       n_samples: int = 1000, seed: int = 0) -> pd.DataFrame:
    """Build a DataFrame of `n_samples` bootstrapped equity curves."""
    samples = bootstrap_returns(returns, n_samples=n_samples, seed=seed)
    curves = {}
    for i, r in enumerate(samples):
        curves[f"sample_{i}"] = initial * (1 + r).cumprod()
    return pd.DataFrame(curves)
