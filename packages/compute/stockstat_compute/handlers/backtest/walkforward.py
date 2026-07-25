"""walkforward handler。"""
from __future__ import annotations

import base64
from typing import Any, Optional, Callable

from stockstat_foundation import TaskSpec, CloudpickleCodec

from .._base import register  # type: ignore


@register("walkforward")
def handle_walkforward(spec: TaskSpec, data: Any, *,
                       on_progress: Optional[Callable] = None) -> Any:
    """前向验证回测。"""
    cs = spec.compute_spec
    from ...backtest import WalkForward

    strategy = _decode_strategy(cs.strategy_ref)
    engine = WalkForward(
        data=data,
        strategy=strategy,
        train_window=cs.params.get("train_window", 252),
        test_window=cs.params.get("test_window", 63),
        step=cs.params.get("step"),
        initial_cash=cs.initial_cash,
        cost_model=cs.cost_model or "default",
        fill_model=cs.fill_model or "next_open",
        symbol=spec.data_spec.symbols[0] if spec.data_spec.symbols else "",
        timeframe=spec.data_spec.timeframe,
    )
    return engine.run(on_progress=on_progress)


def _decode_strategy(ref):
    if isinstance(ref, str) and ref.startswith("cloudpickle:"):
        return CloudpickleCodec().decode(base64.b64decode(ref[len("cloudpickle:"):]))
    if callable(ref):
        return ref
    raise ValueError(f"Invalid strategy ref: {type(ref).__name__}")


__all__ = ["handle_walkforward"]
