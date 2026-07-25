from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from .engine import BacktestEngine
from .result import BacktestResult


def walk_forward(make_engine: Callable[[pd.Timestamp, pd.Timestamp], BacktestEngine],
                 index: pd.DatetimeIndex,
                 train_size: int,
                 test_size: int,
                 step: Optional[int] = None) -> list[tuple[pd.Timestamp, pd.Timestamp, BacktestResult]]:
    """Rolling walk-forward analysis.

    `make_engine(start, end)` builds an engine restricted to [start, end].
    Returns list of (test_start, test_end, result).
    """
    step = step or test_size
    results = []
    n = len(index)
    start_i = 0
    while start_i + train_size + test_size <= n:
        train_end = index[start_i + train_size - 1]
        test_start = index[start_i + train_size]
        test_end = index[min(start_i + train_size + test_size - 1, n - 1)]
        engine = make_engine(test_start, test_end)
        res = engine.run()
        results.append((test_start, test_end, res))
        start_i += step
    return results
