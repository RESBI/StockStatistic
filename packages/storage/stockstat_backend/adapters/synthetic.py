"""SyntheticAdapter — 合成数据（测试/开发用）。"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base import register_adapter


@register_adapter("synthetic")
class SyntheticAdapter:
    """合成数据适配器 — 生成 GBM 模拟 K 线。"""
    name = "synthetic"

    def __init__(self, seed: int = 0, volatility: float = 0.02,
                 drift: float = 0.0005):
        self._seed = seed
        self._vol = volatility
        self._drift = drift

    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> pd.DataFrame:
        n = 100
        if start and end:
            ts = pd.date_range(start=start, end=end, freq="D")
            n = len(ts)
        else:
            ts = pd.date_range("2024-01-01", periods=n, freq="D")
        rng = np.random.default_rng(self._seed)
        returns = rng.normal(self._drift, self._vol, n)
        prices = 100 * np.exp(np.cumsum(returns))
        df = pd.DataFrame({
            "timestamp": ts,
            "open": prices * (1 + rng.normal(0, 0.001, n)),
            "high": prices * (1 + np.abs(rng.normal(0, 0.005, n))),
            "low": prices * (1 - np.abs(rng.normal(0, 0.005, n))),
            "close": prices,
            "volume": rng.integers(1000, 100000, n).astype(float),
        })
        return df


__all__ = ["SyntheticAdapter"]
