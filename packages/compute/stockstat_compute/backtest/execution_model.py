"""ExecutionModel — 执行模型（决定订单何时触发）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionModel:
    """执行模型。"""
    name: str = "next_bar"
    allow_partial_fill: bool = True
    max_slippage_bps: float = 0.0


EXECUTION_MODELS = {
    "next_bar": ExecutionModel(name="next_bar"),
    "intrabar": ExecutionModel(name="intrabar"),
    "market": ExecutionModel(name="next_bar"),
    "limit": ExecutionModel(name="intrabar"),
}


def get_execution_model(name: str = "next_bar") -> ExecutionModel:
    if name is None or name == "":
        return EXECUTION_MODELS["next_bar"]
    return EXECUTION_MODELS.get(name, EXECUTION_MODELS["next_bar"])


__all__ = ["ExecutionModel", "EXECUTION_MODELS", "get_execution_model"]
