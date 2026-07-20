"""Indicator plugins — v2.0 plugin protocol for indicators.

Defines the :class:`IndicatorPlugin` protocol and a helper to register
all v1.7 built-in indicators to the v2.0 PluginRegistry. The actual
computation code remains in ``stockstat.indicators`` (trend, oscillator,
volatility, statistics, nonlinear).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class IndicatorSignature:
    """Metadata describing an indicator's callable signature."""
    params: list[tuple[str, str]] = field(default_factory=list)  # (name, type_hint)
    returns: str = "series"  # "series" | "float" | "dict" | "tuple"


class IndicatorPlugin:
    """Plugin wrapper for an indicator function.

    Wraps a callable (the v1.7 module-level indicator function) and
    exposes it as a v2.0 plugin with metadata.
    """
    category = "indicators"

    def __init__(self, name: str, func: Callable, category: str = "custom",
                 signature: Optional[IndicatorSignature] = None,
                 description: str = "") -> None:
        self.name = name
        self.version = "1.0"
        self.category = category
        self.description = description or func.__doc__ or ""
        self._func = func
        self._signature = signature or IndicatorSignature()

    def initialize(self, context: Any) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        return True

    @property
    def func(self) -> Callable:
        return self._func

    @property
    def signature(self) -> IndicatorSignature:
        return self._signature

    def compute(self, **kwargs) -> Any:
        return self._func(**kwargs)


def register_default_indicators(registry: Any) -> int:
    """Register all v1.7 built-in indicators to the registry.

    Returns the number of indicators registered.
    """
    from ...indicators import trend, oscillator, volatility, statistics, nonlinear

    count = 0

    # Trend
    registry.register("indicators", "ma",
        IndicatorPlugin("ma", trend.ma, "trend", description="Simple moving average"))
    count += 1
    registry.register("indicators", "ema",
        IndicatorPlugin("ema", trend.ema, "trend", description="Exponential moving average"))
    count += 1
    registry.register("indicators", "macd",
        IndicatorPlugin("macd", trend.macd, "trend", description="MACD (returns 3 series)"))
    count += 1

    # Oscillator
    registry.register("indicators", "rsi",
        IndicatorPlugin("rsi", oscillator.rsi, "oscillator", description="Relative Strength Index"))
    count += 1
    registry.register("indicators", "kdj",
        IndicatorPlugin("kdj", oscillator.kdj, "oscillator", description="KDJ (returns 3 series)"))
    count += 1

    # Volatility
    registry.register("indicators", "std",
        IndicatorPlugin("std", volatility.std, "volatility", description="Rolling standard deviation"))
    count += 1
    registry.register("indicators", "atr",
        IndicatorPlugin("atr", volatility.atr, "volatility", description="Average True Range"))
    count += 1
    registry.register("indicators", "bollinger",
        IndicatorPlugin("bollinger", volatility.bollinger, "volatility",
                        description="Bollinger Bands (returns 3 series)"))
    count += 1

    # Statistics
    registry.register("indicators", "corr",
        IndicatorPlugin("corr", statistics.corr, "statistics", description="Pearson correlation"))
    count += 1
    registry.register("indicators", "beta",
        IndicatorPlugin("beta", statistics.beta, "statistics", description="Rolling Beta"))
    count += 1
    registry.register("indicators", "sharpe",
        IndicatorPlugin("sharpe", statistics.sharpe, "statistics", description="Sharpe ratio"))
    count += 1
    registry.register("indicators", "max_drawdown",
        IndicatorPlugin("max_drawdown", statistics.max_drawdown, "statistics",
                        description="Maximum drawdown"))
    count += 1
    registry.register("indicators", "var",
        IndicatorPlugin("var", statistics.var_historical, "statistics",
                        description="Historical VaR"))
    count += 1
    registry.register("indicators", "returns",
        IndicatorPlugin("returns", statistics.returns, "transform",
                        description="Percentage returns"))
    count += 1
    registry.register("indicators", "log_returns",
        IndicatorPlugin("log_returns", statistics.log_returns, "transform",
                        description="Log returns"))
    count += 1

    # Nonlinear
    for name, func in [
        ("wavelet_decompose", nonlinear.wavelet_decompose),
        ("spectral_entropy", nonlinear.spectral_entropy),
        ("grey_relation", nonlinear.grey_relation),
        ("gm11_predict", nonlinear.gm11_predict),
        ("transfer_entropy", nonlinear.transfer_entropy),
        ("hurst_dfa", nonlinear.hurst_dfa),
        ("sample_entropy", nonlinear.sample_entropy),
        ("permutation_entropy", nonlinear.permutation_entropy),
    ]:
        registry.register("indicators", name,
            IndicatorPlugin(name, func, "nonlinear"))
        count += 1

    return count


def get_indicator(registry: Any, name: str) -> Optional[IndicatorPlugin]:
    """Look up an indicator plugin by name."""
    return registry.get("indicators", name)


def list_indicators(registry: Any, category: Optional[str] = None) -> list[dict]:
    """List registered indicators, optionally filtered by category."""
    result = []
    for item in registry.list("indicators"):
        plugin = item["plugin"]
        if category is None or plugin.category == category:
            result.append({
                "name": plugin.name,
                "category": plugin.category,
                "description": plugin.description,
            })
    return result
