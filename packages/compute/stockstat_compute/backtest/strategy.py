"""Strategy — 策略基类与信号。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


@dataclass
class Signal:
    """交易信号。"""
    timestamp: Any
    symbol: str
    side: str  # buy / sell / hold
    quantity: Optional[float] = None  # None=按目标持仓比例 / 数值=具体数量
    strength: float = 1.0
    notes: str = ""

    def __post_init__(self):
        if self.side not in ("buy", "sell", "hold"):
            raise ValueError(f"Invalid side: {self.side}; must be buy/sell/hold")


class StrategyBase:
    """策略基类 — 子类实现 on_bar / on_tick。"""

    name: str = "base"

    def on_bar(self, i: int, bar: pd.Series, data: pd.DataFrame,
               context: dict) -> Optional[Signal]:
        """每根 K 线调用 — 返回 Signal 或 None。"""
        raise NotImplementedError

    def on_init(self, data: pd.DataFrame, context: dict) -> None:
        """初始化（可选）。"""
        pass

    def on_finish(self, data: pd.DataFrame, context: dict) -> None:
        """结束（可选）。"""
        pass


class Strategy(StrategyBase):
    """函数式策略包装 — 接受一个 on_bar 函数。"""

    def __init__(self, on_bar_func, name: str = "func_strategy"):
        self._on_bar_func = on_bar_func
        self.name = name

    def on_bar(self, i: int, bar: pd.Series, data: pd.DataFrame,
               context: dict) -> Optional[Signal]:
        return self._on_bar_func(i, bar, data, context)


def run_strategy_func(strategy_func, data: pd.DataFrame, context: dict) -> list:
    """运行函数式策略（每个 bar 调用一次），返回 Signal 列表。"""
    signals = []
    for i in range(len(data)):
        bar = data.iloc[i]
        sig = strategy_func(i, bar, data, context)
        if sig is not None:
            signals.append(sig)
    return signals


__all__ = ["Signal", "StrategyBase", "Strategy", "run_strategy_func"]
