"""指标注册表。"""
from __future__ import annotations

from typing import Callable

from ..indicators import (
    ma, ema, wma, dema, tema, hma, macd, adx, dpo, trix, moving_average,
    rsi, kd, williams_r, cci, stoch,
    bollinger, atr, keltner, donchian, stddev,
    rolling_corr, rolling_beta, zscore, percentile, rolling_std, rolling_mean,
    hurst_rs, sample_entropy, permutation_entropy,
)


class IndicatorRegistry:
    """指标注册表。"""

    _registry: dict = {}

    @classmethod
    def register(cls, name: str, func: Callable) -> None:
        cls._registry[name] = func

    @classmethod
    def get(cls, name: str) -> Callable:
        if name not in cls._registry:
            raise KeyError(f"Unknown indicator: {name}; available: {sorted(cls._registry.keys())}")
        return cls._registry[name]

    @classmethod
    def list(cls) -> list:
        return sorted(cls._registry.keys())

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._registry


def register_indicator(name: str):
    """指标注册装饰器。"""
    def decorator(func):
        IndicatorRegistry.register(name, func)
        return func
    return decorator


# 注册内置指标
for _name, _func in [
    ("ma", ma), ("sma", ma), ("ema", ema), ("wma", wma),
    ("dema", dema), ("tema", tema), ("hma", hma),
    ("macd", macd), ("adx", adx), ("dpo", dpo), ("trix", trix),
    ("moving_average", moving_average),
    ("rsi", rsi), ("kd", kd), ("williams_r", williams_r),
    ("cci", cci), ("stoch", stoch),
    ("bollinger", bollinger), ("atr", atr), ("keltner", keltner),
    ("donchian", donchian), ("stddev", stddev),
    ("rolling_corr", rolling_corr), ("rolling_beta", rolling_beta),
    ("zscore", zscore), ("percentile", percentile),
    ("rolling_std", rolling_std), ("rolling_mean", rolling_mean),
    ("hurst_rs", hurst_rs), ("sample_entropy", sample_entropy),
    ("permutation_entropy", permutation_entropy),
]:
    IndicatorRegistry.register(_name, _func)


__all__ = ["IndicatorRegistry", "register_indicator"]
