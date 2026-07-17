"""Backtest component plugins.

Registers the v1.7 backtest components (CostModel, FillModel,
ExecutionModel subclasses) to the v2.0 PluginRegistry under their
respective namespaces. The actual implementations remain in
``stockstat.backtest``.
"""
from __future__ import annotations

from typing import Any, Optional


class BacktestComponentPlugin:
    """Generic plugin wrapper for backtest components."""
    category = "backtest"

    def __init__(self, name: str, cls: type, component_type: str,
                 description: str = "") -> None:
        self.name = name
        self.version = "1.0"
        self.component_type = component_type  # "cost" | "fill" | "execution" | "sizing"
        self.description = description
        self._cls = cls

    def initialize(self, context: Any) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        return True

    @property
    def cls(self) -> type:
        return self._cls

    def create(self, **kwargs) -> Any:
        return self._cls(**kwargs)


def register_default_backtest_components(registry: Any) -> int:
    """Register all v1.7 backtest components to the registry.

    Returns the number of components registered.
    """
    from ...backtest import (
        PercentCost, FixedCost, TieredCost, MinCost, StampDutyCost, ZeroCost,
        MakerTakerCost, BinanceCost,
        NextOpenFill, NextCloseFill, ThisCloseFill, VWAPFill, WorstPriceFill,
        IntrabarLimitFill, IntrabarFillModel,
        NextBarExecution, IntrabarExecution,
    )

    count = 0

    # Cost models
    for name, cls, desc in [
        ("percent", PercentCost, "Percentage commission + slippage"),
        ("fixed", FixedCost, "Fixed per-trade fee"),
        ("tiered", TieredCost, "Tiered fee by notional"),
        ("min", MinCost, "Minimum commission floor"),
        ("stamp_duty", StampDutyCost, "Stamp duty (stock seller)"),
        ("zero", ZeroCost, "Zero cost (testing)"),
        ("maker_taker", MakerTakerCost, "Maker/Taker distinction"),
        ("binance", BinanceCost, "Binance spot/futures + BNB"),
    ]:
        registry.register("cost_models", name,
            BacktestComponentPlugin(name, cls, "cost", desc))
        count += 1

    # Fill models
    for name, cls, desc in [
        ("next_open", NextOpenFill, "Fill at next bar open (default)"),
        ("next_close", NextCloseFill, "Fill at next bar close"),
        ("this_close", ThisCloseFill, "Fill at current bar close (warns)"),
        ("vwap", VWAPFill, "VWAP fill"),
        ("worst_price", WorstPriceFill, "Worst price fill (impact)"),
        ("intrabar_limit", IntrabarLimitFill, "Intrabar limit fill"),
        ("intrabar", IntrabarFillModel, "Intrabar sub-bar scan fill"),
    ]:
        registry.register("fill_models", name,
            BacktestComponentPlugin(name, cls, "fill", desc))
        count += 1

    # Execution models
    for name, cls, desc in [
        ("next_bar", NextBarExecution, "Default: t -> t+1 fill"),
        ("intrabar", IntrabarExecution, "Intrabar sub-bar matching"),
    ]:
        registry.register("execution_models", name,
            BacktestComponentPlugin(name, cls, "execution", desc))
        count += 1

    return count


def get_cost_model(registry: Any, name: str) -> Optional[BacktestComponentPlugin]:
    return registry.get("cost_models", name)


def get_fill_model(registry: Any, name: str) -> Optional[BacktestComponentPlugin]:
    return registry.get("fill_models", name)


def get_execution_model(registry: Any, name: str) -> Optional[BacktestComponentPlugin]:
    return registry.get("execution_models", name)
