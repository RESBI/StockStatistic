from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .artifacts import ArtifactRef
from .base import ContractModel


class ComponentRef(ContractModel):
    id: str
    version: str = "1"
    params: dict[str, Any] = Field(default_factory=dict)


class StrategyRef(ContractModel):
    kind: Literal["builtin", "python_package", "python_module", "declarative"]
    name: str
    version: str = "1.0.0"
    entrypoint: str | None = None
    artifact: ArtifactRef | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    digest: str | None = None
    signature: str | None = None


class BacktestParameters(ContractModel):
    strategy: StrategyRef
    initial_cash: float = Field(default=1_000_000.0, gt=0)
    benchmark: str | None = None
    trade_on: Literal["open", "close"] = "open"
    allow_short: bool = False
    lookahead_audit: bool = True
    random_seed: int = 0
    periods_per_year: int | None = Field(default=None, gt=0)
    cost_model: ComponentRef = ComponentRef(id="cost.percent")
    fill_model: ComponentRef = ComponentRef(id="fill.next_open")
    execution_model: ComponentRef = ComponentRef(id="execution.next_bar")


class IndicatorParameters(ContractModel):
    indicator: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    columns: tuple[str, ...] = ("close",)
