from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from . import indicators


@dataclass(frozen=True)
class IndicatorDescriptor:
    id: str
    version: str
    category: str
    callable: Callable
    parameters: dict[str, object] = field(default_factory=dict)
    outputs: tuple[str, ...] = ("value",)
    warmup_parameter: str | None = None
    deterministic: bool = True


class IndicatorCatalog:
    def __init__(self):
        self._items: dict[str, IndicatorDescriptor] = {}

    def register(self, descriptor: IndicatorDescriptor) -> None:
        if descriptor.id in self._items:
            raise ValueError(f"duplicate indicator: {descriptor.id}")
        self._items[descriptor.id] = descriptor

    def descriptor(self, indicator_id: str) -> IndicatorDescriptor:
        try:
            return self._items[indicator_id]
        except KeyError as exc:
            raise KeyError(f"unknown indicator: {indicator_id}") from exc

    def compute(self, indicator_id: str, *args, **kwargs):
        return self.descriptor(indicator_id).callable(*args, **kwargs)

    def list(self) -> tuple[IndicatorDescriptor, ...]:
        return tuple(self._items.values())


INDICATORS = IndicatorCatalog()

for item in (
    IndicatorDescriptor(
        "ma", "1.0", "trend", indicators.ma, {"window": 20}, warmup_parameter="window"
    ),
    IndicatorDescriptor("ema", "1.0", "trend", indicators.ema, {"window": 12}),
    IndicatorDescriptor(
        "macd",
        "1.0",
        "trend",
        indicators.macd,
        {"fast": 12, "slow": 26, "signal": 9},
        ("macd", "signal", "histogram"),
    ),
    IndicatorDescriptor(
        "rsi", "1.0", "oscillator", indicators.rsi, {"window": 14}, warmup_parameter="window"
    ),
    IndicatorDescriptor(
        "kdj", "1.0", "oscillator", indicators.kdj, {"window": 9}, ("k", "d", "j"), "window"
    ),
    IndicatorDescriptor(
        "std", "1.0", "volatility", indicators.std, {"window": 20}, warmup_parameter="window"
    ),
    IndicatorDescriptor(
        "atr", "1.0", "volatility", indicators.atr, {"window": 14}, warmup_parameter="window"
    ),
    IndicatorDescriptor(
        "bollinger",
        "1.0",
        "volatility",
        indicators.bollinger,
        {"window": 20, "k": 2.0},
        ("upper", "middle", "lower"),
        "window",
    ),
    IndicatorDescriptor("corr", "1.0", "statistics", indicators.corr),
    IndicatorDescriptor(
        "beta", "1.0", "statistics", indicators.beta, {"window": 60}, warmup_parameter="window"
    ),
    IndicatorDescriptor(
        "sharpe", "1.0", "statistics", indicators.sharpe, {"risk_free": 0.02, "annualize": True}
    ),
    IndicatorDescriptor("max_drawdown", "1.0", "statistics", indicators.max_drawdown),
    IndicatorDescriptor("var", "1.0", "statistics", indicators.var, {"confidence": 0.95}),
    IndicatorDescriptor("returns", "1.0", "statistics", indicators.returns),
    IndicatorDescriptor("log_returns", "1.0", "statistics", indicators.log_returns),
    IndicatorDescriptor(
        "wavelet_decompose",
        "1.0",
        "timeseries",
        indicators.wavelet_decompose,
        outputs=("coefficients", "scales"),
    ),
    IndicatorDescriptor("spectral_entropy", "1.0", "timeseries", indicators.spectral_entropy),
    IndicatorDescriptor("grey_relation", "1.0", "timeseries", indicators.grey_relation),
    IndicatorDescriptor("gm11_predict", "1.0", "timeseries", indicators.gm11_predict),
    IndicatorDescriptor("transfer_entropy", "1.0", "timeseries", indicators.transfer_entropy),
    IndicatorDescriptor("hurst_dfa", "1.0", "timeseries", indicators.hurst_dfa),
    IndicatorDescriptor("sample_entropy", "1.0", "timeseries", indicators.sample_entropy),
    IndicatorDescriptor("permutation_entropy", "1.0", "timeseries", indicators.permutation_entropy),
):
    INDICATORS.register(item)


class ComponentCatalog:
    def __init__(self):
        self._factories: dict[str, Callable[..., object]] = {}

    def register(self, component_id: str, factory: Callable[..., object]) -> None:
        self._factories[component_id] = factory

    def create(self, component_id: str, **parameters):
        try:
            return self._factories[component_id](**parameters)
        except KeyError as exc:
            raise KeyError(f"unknown component: {component_id}") from exc

    def list(self) -> tuple[str, ...]:
        return tuple(self._factories)


COMPONENTS = ComponentCatalog()
