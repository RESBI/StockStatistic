"""Shared task handlers — used by both LocalComputeBackend and Worker.

Extracted from _core/compute/local.py so that the Worker package
can import them without depending on LocalComputeBackend internals.

Each handler takes a TaskSpec + data dict and returns a result.
Handlers are stateless (no backend reference needed); the caller
is responsible for data resolution and progress reporting.
"""
from __future__ import annotations

from typing import Any, Optional, Callable
import base64
import inspect


def deserialize_strategy(strategy_ref: Optional[str], codec: str = "cloudpickle"):
    """Decode a strategy_ref into a Strategy instance.

    ``strategy_ref`` formats:
    - ``"cloudpickle:base64..."`` — cloudpickle-encoded bytes
    - ``"json:{...}"`` — JSON dict
    - ``None`` — return None
    """
    if strategy_ref is None:
        return None
    if strategy_ref.startswith("cloudpickle:"):
        raw = base64.b64decode(strategy_ref[len("cloudpickle:"):])
        from ..codec import CloudpickleCodec
        return CloudpickleCodec().decode(raw)
    if strategy_ref.startswith("json:"):
        import json
        return json.loads(strategy_ref[len("json:"):])
    raise ValueError(
        f"Cannot deserialize strategy_ref (unknown prefix). "
        f"Expected 'cloudpickle:' or 'json:'."
    )


def encode_strategy(strategy) -> str:
    """Encode a strategy object to a strategy_ref string."""
    raw = _get_cloudpickle().dumps(strategy)
    return "cloudpickle:" + base64.b64encode(raw).decode("ascii")


def _get_cloudpickle():
    import cloudpickle
    return cloudpickle


# ── Component resolution (registered names → instances) ───────


def resolve_cost_model(name: Optional[str]):
    """Resolve a registered cost model name to an instance."""
    if name is None:
        return None
    from ...backtest.cost_model import (
        PercentCost, FixedCost, TieredCost, MinCost, StampDutyCost,
        ZeroCost, MakerTakerCost, BinanceCost,
        BINANCE_SPOT, BINANCE_SPOT_BNB, BINANCE_FUTURES, BINANCE_FUTURES_BNB,
    )
    registry = {
        "percent": PercentCost, "fixed": FixedCost, "tiered": TieredCost,
        "min": MinCost, "stamp_duty": StampDutyCost, "zero": ZeroCost,
        "maker_taker": MakerTakerCost, "binance_spot": BINANCE_SPOT,
        "binance_spot_bnb": BINANCE_SPOT_BNB, "binance_futures": BINANCE_FUTURES,
        "binance_futures_bnb": BINANCE_FUTURES_BNB, "binance": BinanceCost,
    }
    if name in registry:
        cls_or_inst = registry[name]
        return cls_or_inst() if isinstance(cls_or_inst, type) else cls_or_inst
    raise ValueError(f"Unknown cost_model: {name!r}")


def resolve_fill_model(name: Optional[str]):
    if name is None:
        return None
    from ...backtest.fill_model import (
        NextOpenFill, NextCloseFill, ThisCloseFill, VWAPFill,
        WorstPriceFill, IntrabarLimitFill, IntrabarFillModel,
    )
    registry = {
        "next_open": NextOpenFill, "next_close": NextCloseFill,
        "this_close": ThisCloseFill, "vwap": VWAPFill,
        "worst_price": WorstPriceFill, "intrabar_limit": IntrabarLimitFill,
        "intrabar_fill": IntrabarFillModel,
    }
    if name in registry:
        return registry[name]()
    raise ValueError(f"Unknown fill_model: {name!r}")


def resolve_execution_model(name: Optional[str]):
    if name is None:
        return None
    from ...backtest.execution_model import NextBarExecution, IntrabarExecution
    registry = {"next_bar": NextBarExecution, "intrabar": IntrabarExecution}
    if name in registry:
        return registry[name]()
    raise ValueError(f"Unknown execution_model: {name!r}")


def default_cost_model():
    from ...backtest.cost_model import PercentCost
    return PercentCost()


# ── Result serialization helpers ──────────────────────────────


def serialize_result(result: Any, codec: str = "cloudpickle") -> bytes:
    """Serialize a task result to bytes.

    Uses cloudpickle by default (handles BacktestResult with DataFrames).
    Arrow is an alternative for pure-DataFrame results.
    """
    if codec == "arrow":
        from ..codec import ArrowCodec
        return ArrowCodec().encode(result)
    if codec == "json":
        from ..codec import JsonCodec
        return JsonCodec().encode(result)
    # default: cloudpickle
    from ..codec import CloudpickleCodec
    return CloudpickleCodec().encode(result)


def deserialize_result(raw: bytes, codec: str = "cloudpickle") -> Any:
    """Deserialize task result bytes back to Python object."""
    if codec == "arrow":
        from ..codec import ArrowCodec
        return ArrowCodec().decode(raw)
    if codec == "json":
        from ..codec import JsonCodec
        return JsonCodec().decode(raw)
    from ..codec import CloudpickleCodec
    return CloudpickleCodec().decode(raw)


# ── Stream awareness (V2 §13.1 duck-typing) ───────────────────


def is_stream_aware(handler: Callable) -> bool:
    """Check if a handler's signature declares a Stream parameter."""
    try:
        sig = inspect.signature(handler)
        for param in sig.parameters.values():
            if param.annotation is Stream or "Stream" in str(param.annotation):
                return True
    except (ValueError, TypeError):
        pass
    return getattr(handler, "__stream_aware__", False)


class Stream:
    """Data stream — supports both iterative (chunk) and collect (full) modes.

    V2 §13.1: Worker detects via duck-typing whether the handler
    accepts a Stream (incremental) or a DataFrame (full).
    """

    def __init__(self, chunks=None, data=None):
        self._chunks = chunks
        self._collected = data

    def __iter__(self):
        if self._chunks:
            for chunk in self._chunks:
                yield chunk
                if self._collected is not None:
                    import pandas as pd
                    self._collected = pd.concat([self._collected, chunk])
        elif self._collected is not None:
            yield self._collected

    def collect(self) -> Any:
        """Return the full DataFrame (collects all chunks if needed)."""
        if self._collected is None and self._chunks:
            import pandas as pd
            self._collected = pd.concat(list(self._chunks))
        return self._collected

    @classmethod
    def from_data(cls, data: Any) -> "Stream":
        """Wrap a complete DataFrame as a single-chunk Stream."""
        return cls(data=data)


# ── Task handlers ─────────────────────────────────────────────
# Each handler takes (spec, data) and returns a result.
# `data` is {symbol: {timeframe: DataFrame}}.
# `on_progress` is an optional callback(completed, total) for partial reporting.


def handle_indicator(spec, data, on_progress=None):
    """Indicator task — call ComputeEngine.<method>()."""
    from ...compute.engine import ComputeEngine
    engine = ComputeEngine(client=None)
    cs = spec.compute_spec
    method_name = cs.params.get("method")
    if not method_name:
        raise ValueError("compute_spec.params.method is required for indicator tasks")
    method = getattr(engine, method_name, None)
    if method is None or not callable(method):
        raise ValueError(f"Unknown indicator method: {method_name!r}")
    sym = spec.data_spec.symbols[0]
    tf = spec.data_spec.timeframe
    df = data.get(sym, {}).get(tf)
    if df is None or df.empty:
        raise ValueError(f"No data for {sym} {tf}")
    column = cs.params.get("column", "close")
    series = df[column] if column in df.columns else df["close"]
    kwargs = cs.params.get("kwargs", {})
    return method(series, **kwargs)


def handle_backtest(spec, data, on_progress=None):
    """Backtest task — call BacktestEngine(...).run()."""
    from ...backtest import BacktestEngine
    from ...compute.engine import ComputeEngine
    cs = spec.compute_spec
    strategy = deserialize_strategy(cs.strategy_ref, cs.strategy_codec)
    if strategy is None:
        raise ValueError("compute_spec.strategy_ref is required for backtest tasks")
    cost_model = resolve_cost_model(cs.cost_model) or default_cost_model()
    fill_model = resolve_fill_model(cs.fill_model)
    execution_model = resolve_execution_model(cs.execution_model)
    kwargs = dict(
        data=data, strategy=strategy,
        initial_cash=cs.initial_cash,
        cost_model=cost_model,
        benchmark=cs.benchmark,
        trade_on=cs.trade_on,
        allow_short=cs.allow_short,
        periods_per_year=cs.periods_per_year,
        compute_engine=ComputeEngine(client=None),
    )
    if fill_model is not None:
        kwargs["fill_model"] = fill_model
    if execution_model is not None:
        kwargs["execution_model"] = execution_model
    engine = BacktestEngine(**kwargs)
    return engine.run()


def handle_grid_search(spec, data, on_progress=None):
    """Grid search task — sharded execution.

    If spec.compute_spec.params contains 'param_slice', only that
    subset is evaluated (Worker-side sharding). Otherwise, the full
    param_grid is searched serially.
    """
    from itertools import product
    from ...backtest import BacktestEngine
    from ...compute.engine import ComputeEngine
    cs = spec.compute_spec
    if not cs.param_grid:
        raise ValueError("compute_spec.param_grid is required for grid_search tasks")
    # Check for sharded execution
    param_slice = cs.params.get("param_slice")
    if param_slice is not None:
        grids = param_slice
    else:
        keys = list(cs.param_grid.keys())
        grids = [dict(zip(keys, vals)) for vals in product(*[cs.param_grid[k] for k in keys])]
    results = []
    total = len(grids)
    for i, params in enumerate(grids):
        strategy = deserialize_strategy(cs.strategy_ref, cs.strategy_codec)
        cost_model = resolve_cost_model(cs.cost_model) or default_cost_model()
        fill_model = resolve_fill_model(cs.fill_model)
        execution_model = resolve_execution_model(cs.execution_model)
        kwargs = dict(
            data=data, strategy=strategy,
            initial_cash=cs.initial_cash,
            cost_model=cost_model,
            benchmark=cs.benchmark,
            trade_on=cs.trade_on,
            allow_short=cs.allow_short,
            periods_per_year=cs.periods_per_year,
            compute_engine=ComputeEngine(client=None),
        )
        if fill_model is not None:
            kwargs["fill_model"] = fill_model
        if execution_model is not None:
            kwargs["execution_model"] = execution_model
        if hasattr(strategy, "update_params"):
            strategy.update_params(params)
        engine = BacktestEngine(**kwargs)
        res = engine.run()
        m = res.metrics()
        val = m.get(cs.metric, float("-inf"))
        results.append({"params": params, cs.metric: val, "result": res})
        if on_progress:
            on_progress(i + 1, total)
    results.sort(key=lambda x: x[cs.metric], reverse=cs.maximize)
    return results


def handle_batch_backtest(spec, data, on_progress=None):
    """Batch backtest — strategies x fee_models."""
    from ...backtest.batch_runner import StrategyBatchRunner
    cs = spec.compute_spec
    if not cs.strategies:
        raise ValueError("compute_spec.strategies is required for batch_backtest tasks")
    strategies = {
        name: deserialize_strategy(ref, cs.strategy_codec)
        for name, ref in cs.strategies.items()
    }
    fee_models = {}
    if cs.fee_models:
        if all(isinstance(f, str) for f in cs.fee_models):
            fee_models = {f: resolve_cost_model(f) for f in cs.fee_models}
        else:
            fee_models = {f"model_{i}": resolve_cost_model(None) or default_cost_model()
                          for i, _ in enumerate(cs.fee_models)}
    else:
        fee_models = {"default": default_cost_model()}
    runner = StrategyBatchRunner(
        data=data, initial_cash=cs.initial_cash,
        benchmark=cs.benchmark, trade_on=cs.trade_on,
        allow_short=cs.allow_short, periods_per_year=cs.periods_per_year,
    )
    results = runner.run_all_fees(strategies, fee_models)
    return results.to_dataframe()


def handle_monte_carlo(spec, data, on_progress=None):
    """Monte Carlo simulation."""
    from ...backtest import BacktestEngine
    from ...backtest.montecarlo import monte_carlo_equity
    from ...compute.engine import ComputeEngine
    cs = spec.compute_spec
    strategy = deserialize_strategy(cs.strategy_ref, cs.strategy_codec)
    if strategy is None:
        raise ValueError("compute_spec.strategy_ref is required for monte_carlo tasks")
    cost_model = resolve_cost_model(cs.cost_model) or default_cost_model()
    fill_model = resolve_fill_model(cs.fill_model)
    kwargs = dict(
        data=data, strategy=strategy,
        initial_cash=cs.initial_cash,
        cost_model=cost_model,
        benchmark=cs.benchmark, trade_on=cs.trade_on,
        allow_short=cs.allow_short,
        periods_per_year=cs.periods_per_year,
        compute_engine=ComputeEngine(client=None),
    )
    if fill_model is not None:
        kwargs["fill_model"] = fill_model
    engine = BacktestEngine(**kwargs)
    baseline = engine.run()
    returns = baseline.returns
    curves = monte_carlo_equity(
        returns, initial=cs.initial_cash,
        n_samples=cs.n_simulations, seed=cs.seed,
    )
    return {"baseline": baseline, "equity_curves": curves, "n_simulations": cs.n_simulations}


def handle_custom(spec, data, on_progress=None):
    """Custom task — returns params as acknowledgement.

    Supports optional _sleep_seconds for testing timing/cancellation.
    """
    import time
    cs = spec.compute_spec
    sleep_s = cs.params.get("_sleep_seconds", 0)
    if sleep_s:
        deadline = time.time() + sleep_s
        while time.time() < deadline:
            time.sleep(0.05)
    return {
        "task_type": "custom",
        "params": {k: v for k, v in cs.params.items() if k != "_sleep_seconds"},
        "data_keys": list(data.keys()),
    }


# ── Master dispatch function ──────────────────────────────────


HANDLERS = {
    "indicator": handle_indicator,
    "backtest": handle_backtest,
    "grid_search": handle_grid_search,
    "batch_backtest": handle_batch_backtest,
    "monte_carlo": handle_monte_carlo,
    "custom": handle_custom,
}


def dispatch(spec, data, on_progress=None):
    """Route a TaskSpec to the appropriate handler.

    This is the shared entry point used by both LocalComputeBackend
    and Worker. Adding a new task type means adding it to HANDLERS.
    """
    task_type = spec.compute_spec.task_type
    handler = HANDLERS.get(task_type)
    if handler is None:
        raise ValueError(f"Unknown task_type: {task_type!r}")
    # Check stream awareness (V2 §13.1)
    if is_stream_aware(handler):
        stream = Stream.from_data(data)
        return handler(spec, stream, on_progress=on_progress)
    return handler(spec, data, on_progress=on_progress)
