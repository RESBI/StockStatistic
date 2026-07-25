"""backtest handler。"""
from __future__ import annotations

import base64
from typing import Any, Optional, Callable

from stockstat_foundation import TaskSpec, CloudpickleCodec

from .._base import register  # type: ignore


@register("backtest")
def handle_backtest(spec: TaskSpec, data: Any, *,
                    on_progress: Optional[Callable] = None) -> Any:
    """单次策略回测。"""
    cs = spec.compute_spec
    from ...backtest import BacktestEngine

    # 解码策略
    strategy = _decode_strategy(cs.strategy_ref, cs.strategy_codec)

    engine = BacktestEngine(
        data=data,
        strategy=strategy,
        initial_cash=cs.initial_cash,
        cost_model=cs.cost_model,
        fill_model=cs.fill_model,
        execution_model=cs.execution_model,
        benchmark=cs.benchmark,
        trade_on=cs.trade_on,
        allow_short=cs.allow_short,
        periods_per_year=cs.periods_per_year,
        symbol=spec.data_spec.symbols[0] if spec.data_spec.symbols else "",
        timeframe=spec.data_spec.timeframe,
        strategy_name=cs.params.get("strategy_name", "backtest"),
    )
    return engine.run()


def _decode_strategy(strategy_ref, strategy_codec: str = "cloudpickle"):
    if strategy_ref is None:
        raise ValueError("strategy_ref required for backtest")
    if isinstance(strategy_ref, str) and strategy_ref.startswith("cloudpickle:"):
        ref = strategy_ref[len("cloudpickle:"):]
        return CloudpickleCodec().decode(base64.b64decode(ref))
    if isinstance(strategy_ref, str) and strategy_ref.startswith("registry:"):
        from ...backtest import StrategyRegistry  # type: ignore
        # StrategyRegistry 是可选的，这里用 fallback
        raise NotImplementedError("StrategyRegistry not implemented; use cloudpickle strategy_ref")
    # 直接是可调用对象
    if callable(strategy_ref):
        return strategy_ref
    raise ValueError(f"Invalid strategy_ref: {type(strategy_ref).__name__}")


__all__ = ["handle_backtest"]
