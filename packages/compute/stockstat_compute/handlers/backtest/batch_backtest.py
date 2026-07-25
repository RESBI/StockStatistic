"""batch_backtest handler — 策略 × 费率。"""
from __future__ import annotations

import base64
from typing import Any, Optional, Callable

from stockstat_foundation import TaskSpec, CloudpickleCodec

from .._base import register  # type: ignore


@register("batch_backtest")
def handle_batch_backtest(spec: TaskSpec, data: Any, *,
                          on_progress: Optional[Callable] = None) -> Any:
    """批量策略回测。"""
    cs = spec.compute_spec
    if not cs.strategies:
        raise ValueError("compute_spec.strategies required for batch_backtest")

    # 解码所有策略
    strategies = {}
    for name, ref in cs.strategies.items():
        strategies[name] = _decode_strategy(ref)

    fee_models = cs.fee_models or ["default"]

    from ...backtest import batch_backtest as _batch
    return _batch(
        data=data,
        strategies=strategies,
        fee_models=fee_models,
        initial_cash=cs.initial_cash,
        fill_model=cs.fill_model or "next_open",
        trade_on=cs.trade_on,
        allow_short=cs.allow_short,
        periods_per_year=cs.periods_per_year,
        symbol=spec.data_spec.symbols[0] if spec.data_spec.symbols else "",
        timeframe=spec.data_spec.timeframe,
        on_progress=on_progress,
    )


def _decode_strategy(ref):
    if isinstance(ref, str) and ref.startswith("cloudpickle:"):
        return CloudpickleCodec().decode(base64.b64decode(ref[len("cloudpickle:"):]))
    if callable(ref):
        return ref
    raise ValueError(f"Invalid strategy ref: {type(ref).__name__}")


__all__ = ["handle_batch_backtest"]
