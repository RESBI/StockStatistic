"""ComputeEngine — 指标计算引擎主体。"""
from __future__ import annotations

from typing import Any

from .registry import IndicatorRegistry


class ComputeEngine:
    """指标计算引擎 — 提供 40+ 技术指标便捷方法。

    用法：
        engine = ComputeEngine()
        sma = engine.ma(data.close, window=20)
        rsi = engine.rsi(data.close, window=14)
    """

    def __init__(self):
        pass

    @property
    def registry(self) -> IndicatorRegistry:
        return IndicatorRegistry

    def list_indicators(self) -> list:
        return IndicatorRegistry.list()

    def compute(self, name: str, *args, **params):
        """通用指标调用入口（支持多位置参数，如 atr(high, low, close, window=14)）。"""
        func = IndicatorRegistry.get(name)
        return func(*args, **params)

    # ── 趋势指标便捷方法 ──
    def ma(self, data, window: int = 20):
        return self.compute("ma", data, window=window)

    def sma(self, data, window: int = 20):
        return self.compute("sma", data, window=window)

    def ema(self, data, window: int = 12):
        return self.compute("ema", data, window=window)

    def wma(self, data, window: int = 20):
        return self.compute("wma", data, window=window)

    def dema(self, data, window: int = 20):
        return self.compute("dema", data, window=window)

    def tema(self, data, window: int = 20):
        return self.compute("tema", data, window=window)

    def hma(self, data, window: int = 20):
        return self.compute("hma", data, window=window)

    def macd(self, data, fast: int = 12, slow: int = 26, signal: int = 9):
        return self.compute("macd", data, fast=fast, slow=slow, signal=signal)

    def adx(self, high, low, close, window: int = 14):
        return self.compute("adx", high, low, close, window=window)

    def dpo(self, data, window: int = 20):
        return self.compute("dpo", data, window=window)

    def trix(self, data, window: int = 12):
        return self.compute("trix", data, window=window)

    # ── 振荡指标 ──
    def rsi(self, data, window: int = 14):
        return self.compute("rsi", data, window=window)

    def kd(self, high, low, close, k_window: int = 9, d_window: int = 3):
        return self.compute("kd", high, low, close, k_window=k_window, d_window=d_window)

    def williams_r(self, high, low, close, window: int = 14):
        return self.compute("williams_r", high, low, close, window=window)

    def cci(self, high, low, close, window: int = 20):
        return self.compute("cci", high, low, close, window=window)

    def stoch(self, high, low, close, k_window: int = 14, d_window: int = 3):
        return self.compute("stoch", high, low, close, k_window=k_window, d_window=d_window)

    # ── 波动率指标 ──
    def bollinger(self, data, window: int = 20, std: float = 2.0):
        return self.compute("bollinger", data, window=window, std=std)

    def atr(self, high, low, close, window: int = 14):
        return self.compute("atr", high, low, close, window=window)

    def keltner(self, high, low, close, window: int = 20, mult: float = 1.5):
        return self.compute("keltner", high, low, close, window=window, mult=mult)

    def donchian(self, high, low, window: int = 20):
        return self.compute("donchian", high, low, window=window)

    def stddev(self, data, window: int = 20):
        return self.compute("stddev", data, window=window)

    # ── 统计指标 ──
    def rolling_corr(self, x, y, window: int = 20):
        return self.compute("rolling_corr", x, y, window=window)

    def rolling_beta(self, asset, market, window: int = 20):
        return self.compute("rolling_beta", asset, market, window=window)

    def zscore(self, data, window: int = 20):
        return self.compute("zscore", data, window=window)

    def percentile(self, data, window: int = 20):
        return self.compute("percentile", data, window=window)

    def rolling_std(self, data, window: int = 20):
        return self.compute("rolling_std", data, window=window)

    def rolling_mean(self, data, window: int = 20):
        return self.compute("rolling_mean", data, window=window)

    # ── 非线性指标 ──
    def hurst_rs(self, data):
        return self.compute("hurst_rs", data)

    def sample_entropy(self, data, m: int = 2, r: float = None):
        return self.compute("sample_entropy", data, m=m, r=r)

    def permutation_entropy(self, data, m: int = 4, tau: int = 1):
        return self.compute("permutation_entropy", data, m=m, tau=tau)

    def __getattr__(self, name: str):
        """动态分派到注册表。"""
        if name.startswith("_"):
            raise AttributeError(name)
        if IndicatorRegistry.has(name):
            def wrapper(*args, **kwargs):
                return self.compute(name, *args, **kwargs)
            return wrapper
        raise AttributeError(f"Unknown indicator: {name}")


__all__ = ["ComputeEngine"]
