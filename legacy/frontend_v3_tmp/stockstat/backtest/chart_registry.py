from __future__ import annotations

from typing import Callable, Optional

from .chart_spec import BacktestChartSpec


_CHART_BUILDERS: dict[str, Callable] = {}


def register_chart(name: str):
    """Decorator to register a BacktestChartSpec builder keyed by `name`.

    A builder has signature: fn(result: BacktestResult, **kwargs) -> BacktestChartSpec
    """
    def decorator(fn: Callable) -> Callable:
        _CHART_BUILDERS[name] = fn
        return fn
    return decorator


def get_chart_builder(name: str) -> Optional[Callable]:
    return _CHART_BUILDERS.get(name)


def list_chart_types() -> list[str]:
    return sorted(_CHART_BUILDERS.keys())


def build_chart(name: str, result, **kwargs) -> BacktestChartSpec:
    builder = _CHART_BUILDERS.get(name)
    if builder is None:
        raise KeyError(
            f"Unknown chart type '{name}'. Available: {list_chart_types()}"
        )
    return builder(result, **kwargs)
