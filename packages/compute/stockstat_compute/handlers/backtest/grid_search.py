"""grid_search handler。"""
from __future__ import annotations

import base64
from typing import Any, Optional, Callable

from stockstat_foundation import TaskSpec, CloudpickleCodec

from .._base import register  # type: ignore


@register("grid_search")
def handle_grid_search(spec: TaskSpec, data: Any, *,
                       on_progress: Optional[Callable] = None) -> Any:
    """参数网格搜索。"""
    cs = spec.compute_spec
    if not cs.param_grid:
        raise ValueError("compute_spec.param_grid required for grid_search")

    from ...backtest import grid_search as _grid_search

    strategy = _decode_strategy(cs.strategy_ref)
    if not isinstance(strategy, type):
        # 包装为可调用类
        strategy_cls = type(strategy).__class__ if False else _FuncStrategyCls  # type: ignore
        # 简化：如果传入的是函数，包装成接受任意 params 的类
        strategy_cls = _make_strategy_cls(strategy)
    else:
        strategy_cls = strategy

    return _grid_search(
        data=data,
        strategy_cls=strategy_cls,
        param_grid=cs.param_grid,
        metric=cs.metric,
        maximize=cs.maximize,
        initial_cash=cs.initial_cash,
        cost_model=cs.cost_model or "default",
        fill_model=cs.fill_model or "next_open",
        trade_on=cs.trade_on,
        allow_short=cs.allow_short,
        periods_per_year=cs.periods_per_year,
        symbol=spec.data_spec.symbols[0] if spec.data_spec.symbols else "",
        timeframe=spec.data_spec.timeframe,
        on_progress=on_progress,
    )


def _decode_strategy(strategy_ref):
    if isinstance(strategy_ref, str) and strategy_ref.startswith("cloudpickle:"):
        ref = strategy_ref[len("cloudpickle:"):]
        return CloudpickleCodec().decode(base64.b64decode(ref))
    if callable(strategy_ref):
        return strategy_ref
    raise ValueError(f"Invalid strategy_ref: {type(strategy_ref).__name__}")


def _make_strategy_cls(strategy_func):
    """将函数式策略包装为可接受 **params 的类。"""
    from ...backtest import Strategy
    class _Wrapper(Strategy):
        name = "grid_wrapper"
        def __init__(self, **params):
            super().__init__(self._wrap, name=f"grid_{params}")
            self._params = params
        def _wrap(self, i, bar, data, context):
            return strategy_func(i, bar, data, context, **self._params)
    return _Wrapper


__all__ = ["handle_grid_search"]
