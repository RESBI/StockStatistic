"""Local compute backend — V3 Phase 1 default implementation.

Implements the :class:`ComputeBackend` protocol by directly calling
the stockstat core computation logic (BacktestEngine / ComputeEngine /
grid_search / etc.) in a background thread. This preserves the
synchronous semantics of v2.1 while exposing the V3 TaskRef API.

When :class:`StockStatClient` and :class:`V2Client` default to this
backend, their behavior is **identical to v2.1** — all 491 existing
frontend tests pass without modification. The remote()/cluster_info()
V3 entry points are also functional (cluster_info returns a single
in-process "worker").

This backend is also used by RemoteComputeBackend's InProcessTransport
mode (Phase 1 single-process simulation), allowing the full
Client -> Dispatcher -> Worker protocol path to be exercised without
spawning any processes.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..contracts.compute import (
    ComputeBackend, TaskInfo, TaskRef, TaskState,
)
from ..contracts.task import TaskSpec, ComputeSpec
from ..errors import TaskCancelledError, TaskError, TaskNotReadyError, TaskTimeoutError


@dataclass
class _LocalTaskState:
    """Internal mutable state for a locally-executed task."""
    spec: TaskSpec
    info: TaskInfo
    thread: Optional[threading.Thread] = None
    result: Any = None
    error: Optional[BaseException] = None
    partials: list = field(default_factory=list)
    cancel_requested: bool = False


class LocalComputeBackend:
    """In-process compute backend — V3 default.

    Submits execute in a daemon thread; ``wait()`` blocks on the
    thread join; ``result()`` raises if not yet complete.

    The actual dispatch logic lives in :func:`_dispatch_to_handler`
    (this module), which routes by ``compute_spec.task_type`` to the
    appropriate stockstat core function. Adding a new task type
    requires only registering a handler there.
    """

    name = "local"

    def __init__(self, *, client: Any = None, data_client: Any = None,
                 storage: Any = None, mode: str = "online"):
        """
        Args:
            client: optional StockStatClient / V2Client reference for
                handlers that need data access (e.g. fetching OHLCV)
            data_client: optional DataClient for HTTP data access
            storage: optional StorageBackend for offline mode
            mode: "online" / "offline" — affects how handlers fetch data
        """
        self._client = client
        self._data_client = data_client
        self._storage = storage
        self._mode = mode
        self._tasks: dict[str, _LocalTaskState] = {}
        self._lock = threading.Lock()

    # ── ComputeBackend protocol ────────────────────────────────

    def submit(self, spec: TaskSpec) -> TaskRef:
        """Submit a task; returns immediately with a TaskRef."""
        state = _LocalTaskState(
            spec=spec,
            info=TaskInfo(
                task_id=spec.task_id,
                state=TaskState.PENDING,
                created_at=spec.created_at,
            ),
        )
        with self._lock:
            self._tasks[spec.task_id] = state

        # Start execution in a daemon thread
        t = threading.Thread(
            target=self._run_local,
            args=(state,),
            daemon=True,
            name=f"local-task-{spec.task_id[:8]}",
        )
        state.thread = t
        t.start()
        return TaskRef(task_id=spec.task_id, backend=self)

    def get(self, task_id: str) -> TaskInfo:
        state = self._get_state(task_id)
        return state.info

    def result(self, task_id: str) -> Any:
        state = self._get_state(task_id)
        if state.info.state == TaskState.COMPLETED:
            return state.result
        if state.info.state == TaskState.FAILED:
            raise TaskError(state.info.error or "task failed",
                            context={"task_id": task_id})
        if state.info.state == TaskState.CANCELLED:
            raise TaskCancelledError(
                context={"task_id": task_id},
            )
        # PENDING or RUNNING
        raise TaskNotReadyError(
            context={"task_id": task_id, "state": state.info.state.value},
        )

    def wait(self, task_id: str, timeout: Optional[float] = None) -> Any:
        state = self._get_state(task_id)
        if state.thread is not None:
            state.thread.join(timeout=timeout)
        if state.thread is not None and state.thread.is_alive():
            raise TaskTimeoutError(
                f"Task {task_id} not finished in {timeout}s",
                context={"task_id": task_id, "timeout": timeout},
            )
        if state.info.state == TaskState.FAILED:
            raise TaskError(
                state.info.error or "task failed",
                context={
                    "task_id": task_id,
                    "error_code": state.info.error_code,
                    "worker_id": state.info.worker_id,
                },
            )
        if state.info.state == TaskState.CANCELLED:
            raise TaskCancelledError(context={"task_id": task_id})
        return state.result

    def cancel(self, task_id: str) -> bool:
        state = self._tasks.get(task_id)
        if state is None:
            return False
        if state.info.state in (TaskState.PENDING, TaskState.RUNNING):
            state.cancel_requested = True
            state.info.state = TaskState.CANCELLED
            state.info.finished_at = datetime.utcnow()
            return True
        return False

    def cluster_info(self, **kwargs) -> dict:
        """Return a single-worker in-process cluster topology."""
        active = sum(
            1 for s in self._tasks.values()
            if s.info.state == TaskState.RUNNING
        )
        return {
            "dispatcher": {
                "id": "local",
                "alias": "in-process",
                "status": "online",
                "uptime_s": 0,
                "queue_depth": 0,
                "cache_size_mb": 0.0,
                "cache_hit_rate": 0.0,
            },
            "workers": [{
                "worker_id": "local",
                "alias": "in-process",
                "address": "127.0.0.1:0",
                "status": "online",
                "concurrency": 1,
                "active_tasks": active,
                "completed_tasks": sum(
                    1 for s in self._tasks.values()
                    if s.info.state == TaskState.COMPLETED
                ),
                "failed_tasks": sum(
                    1 for s in self._tasks.values()
                    if s.info.state == TaskState.FAILED
                ),
                "capabilities": [
                    "indicator", "backtest", "grid_search",
                    "batch_backtest", "monte_carlo", "custom",
                ],
                "stockstat_version": _get_stockstat_version(),
            }],
            "stats": {
                "total_workers": 1,
                "online_workers": 1,
                "offline_workers": 0,
                "total_concurrency": 1,
                "available_concurrency": max(0, 1 - active),
                "active_tasks": active,
                "total_completed": sum(
                    1 for s in self._tasks.values()
                    if s.info.state == TaskState.COMPLETED
                ),
                "total_failed": sum(
                    1 for s in self._tasks.values()
                    if s.info.state == TaskState.FAILED
                ),
                "queue_depth": 0,
                "avg_queue_wait_s": 0.0,
            },
        }

    def stream_results(self, task_id: str):
        """Yield partial results, then the final result.

        For local backend, partials are collected during execution
        (handlers may call ``publish_partial``). If no partials were
        published, yields only the final result.
        """
        state = self._get_state(task_id)
        # Wait for completion first
        self.wait(task_id)

        for p in state.partials:
            yield p
        # Final result is yielded only if different from last partial
        if not state.partials or state.partials[-1] is not state.result:
            yield state.result

    # ── Public helpers for handlers ────────────────────────────

    def publish_partial(self, task_id: str, partial: Any) -> None:
        """Handler can call this to publish intermediate results."""
        state = self._tasks.get(task_id)
        if state is not None:
            state.partials.append(partial)

    # ── Internal ───────────────────────────────────────────────

    def _get_state(self, task_id: str) -> _LocalTaskState:
        state = self._tasks.get(task_id)
        if state is None:
            from ..errors import TaskNotFoundError
            raise TaskNotFoundError(
                f"Unknown task_id: {task_id}",
                context={"task_id": task_id},
            )
        return state

    def _run_local(self, state: _LocalTaskState) -> None:
        """Background thread entry point — runs the task to completion."""
        try:
            # Check for early cancel (between submit and thread start)
            if state.cancel_requested:
                state.info.state = TaskState.CANCELLED
                state.info.finished_at = datetime.utcnow()
                return

            state.info.state = TaskState.RUNNING
            state.info.started_at = datetime.utcnow()
            state.info.worker_id = "local"

            result = _dispatch_to_handler(
                spec=state.spec,
                backend=self,
                client=self._client,
                data_client=self._data_client,
                storage=self._storage,
                mode=self._mode,
            )
            # Re-check cancel after long-running compute
            if state.cancel_requested:
                state.info.state = TaskState.CANCELLED
                state.info.finished_at = datetime.utcnow()
                return

            state.result = result
            state.info.state = TaskState.COMPLETED
            state.info.progress = 1.0
        except BaseException as e:  # noqa: BLE001
            state.error = e
            state.info.state = TaskState.FAILED
            state.info.error = f"{type(e).__name__}: {e}"
            state.info.error_code = type(e).__name__
            import traceback
            state.info.error = state.info.error + "\n" + traceback.format_exc()
        finally:
            state.info.finished_at = datetime.utcnow()


def _get_stockstat_version() -> str:
    try:
        from ... import __version__  # type: ignore
        return __version__
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════
# Task dispatch — route TaskSpec to the right stockstat core function
# ═══════════════════════════════════════════════════════════════


def _dispatch_to_handler(
    *,
    spec: TaskSpec,
    backend: LocalComputeBackend,
    client: Any = None,
    data_client: Any = None,
    storage: Any = None,
    mode: str = "online",
) -> Any:
    """Route a TaskSpec to the appropriate stockstat core function.

    This is the single dispatch point for local execution. Adding a
    new task type means adding a branch here (and optionally a handler
    module under :mod:`stockstat._core.compute.handlers`).
    """
    cs = spec.compute_spec
    task_type = cs.task_type

    # Resolve data — fetch from client / storage / data_client
    data = _resolve_data(spec, client=client, data_client=data_client,
                         storage=storage, mode=mode)

    if task_type == "indicator":
        return _handle_indicator(spec, data)
    if task_type == "backtest":
        return _handle_backtest(spec, data)
    if task_type == "grid_search":
        return _handle_grid_search(spec, data, backend=backend)
    if task_type == "batch_backtest":
        return _handle_batch_backtest(spec, data, backend=backend)
    if task_type == "monte_carlo":
        return _handle_monte_carlo(spec, data, backend=backend)
    if task_type == "custom":
        # Custom tasks: support optional _sleep_seconds for testing
        # cancellation / timing; otherwise just acknowledge
        sleep_s = cs.params.get("_sleep_seconds", 0)
        if sleep_s:
            import time as _time
            deadline = _time.time() + sleep_s
            while _time.time() < deadline:
                if state := getattr(backend, "_tasks", {}).get(spec.task_id):
                    if state.cancel_requested:
                        return {"cancelled": True, "slept": _time.time() - (deadline - sleep_s)}
                _time.sleep(0.05)
        return {"task_type": "custom", "params": {k: v for k, v in cs.params.items() if k != "_sleep_seconds"}, "data_keys": list(data.keys())}
    raise ValueError(f"Unknown task_type: {task_type!r}")


def _resolve_data(
    spec: TaskSpec,
    *,
    client: Any = None,
    data_client: Any = None,
    storage: Any = None,
    mode: str = "online",
) -> dict:
    """Fetch the OHLCV data described by ``spec.data_spec``.

    Returns ``{symbol: {timeframe: pd.DataFrame}}`` — the standard
    backtest data format.

    For LocalComputeBackend:
    - If a ``client`` is provided, use ``client.ohlcv()`` (online HTTP
      or offline Storage access)
    - If ``data_client`` is provided, use it directly
    - If ``storage`` is provided (offline mode), query storage
    - Otherwise raise — local backend needs a data source
    """
    import pandas as pd
    ds = spec.data_spec
    result: dict = {}

    for sym in ds.symbols:
        df: Optional[pd.DataFrame] = None

        if client is not None and hasattr(client, "ohlcv"):
            df = client.ohlcv(
                symbol=sym,
                source=ds.source,
                start=ds.start,
                end=ds.end,
                timeframe=ds.timeframe,
            )
        elif data_client is not None and hasattr(data_client, "ohlcv"):
            df = data_client.ohlcv(
                symbol=sym,
                source=ds.source,
                start=ds.start,
                end=ds.end,
                timeframe=ds.timeframe,
            )
        elif storage is not None:
            filters = {"symbol": sym, "timeframe": ds.timeframe}
            if ds.source:
                filters["source"] = ds.source
            df = storage.query(
                "ohlcv", filters=filters, start=ds.start, end=ds.end,
            )
            if df is not None and not df.empty and "ts" in df.columns:
                df = df.set_index("ts")
        else:
            # No data source — return empty DataFrame, handler can decide
            df = pd.DataFrame()

        result[sym] = {ds.timeframe: df if df is not None else pd.DataFrame()}

    return result


def _deserialize_strategy(strategy_ref: Optional[str], codec: str = "cloudpickle"):
    """Decode a strategy_ref into a Strategy instance.

    ``strategy_ref`` may be:
    - ``"cloudpickle:base64..."`` — cloudpickle-encoded bytes (default)
    - ``"json:{...}"`` — JSON dict (for simple registered strategies)
    - ``None`` — return None (handler decides what to do)
    """
    if strategy_ref is None:
        return None

    if strategy_ref.startswith("cloudpickle:"):
        import base64
        from ..codec import CloudpickleCodec
        raw = base64.b64decode(strategy_ref[len("cloudpickle:"):])
        return CloudpickleCodec().decode(raw)

    if strategy_ref.startswith("json:"):
        import json
        return json.loads(strategy_ref[len("json:"):])

    # Fall back: treat as a registered name (future: registry lookup)
    raise ValueError(
        f"Cannot deserialize strategy_ref (prefix unknown). "
        f"Expected 'cloudpickle:' or 'json:' prefix."
    )


def _resolve_cost_model(name: Optional[str]):
    """Resolve a registered cost model name to an instance."""
    if name is None:
        return None
    from ...backtest.cost_model import (
        PercentCost, FixedCost, TieredCost, MinCost, StampDutyCost,
        ZeroCost, MakerTakerCost, BinanceCost,
        BINANCE_SPOT, BINANCE_SPOT_BNB, BINANCE_FUTURES, BINANCE_FUTURES_BNB,
    )
    registry = {
        "percent": PercentCost,
        "fixed": FixedCost,
        "tiered": TieredCost,
        "min": MinCost,
        "stamp_duty": StampDutyCost,
        "zero": ZeroCost,
        "maker_taker": MakerTakerCost,
        "binance_spot": BINANCE_SPOT,
        "binance_spot_bnb": BINANCE_SPOT_BNB,
        "binance_futures": BINANCE_FUTURES,
        "binance_futures_bnb": BINANCE_FUTURES_BNB,
        "binance": BinanceCost,
    }
    if name in registry:
        cls_or_inst = registry[name]
        if isinstance(cls_or_inst, type):
            return cls_or_inst()
        return cls_or_inst  # already an instance (the BINANCE_* presets)
    raise ValueError(f"Unknown cost_model: {name!r}")


def _resolve_fill_model(name: Optional[str]):
    """Resolve a registered fill model name to an instance."""
    if name is None:
        return None
    from ...backtest.fill_model import (
        NextOpenFill, NextCloseFill, ThisCloseFill, VWAPFill,
        WorstPriceFill, IntrabarLimitFill, IntrabarFillModel,
    )
    registry = {
        "next_open": NextOpenFill,
        "next_close": NextCloseFill,
        "this_close": ThisCloseFill,
        "vwap": VWAPFill,
        "worst_price": WorstPriceFill,
        "intrabar_limit": IntrabarLimitFill,
        "intrabar_fill": IntrabarFillModel,
    }
    if name in registry:
        return registry[name]()
    raise ValueError(f"Unknown fill_model: {name!r}")


def _resolve_execution_model(name: Optional[str]):
    """Resolve a registered execution model name to an instance."""
    if name is None:
        return None
    from ...backtest.execution_model import NextBarExecution, IntrabarExecution
    registry = {
        "next_bar": NextBarExecution,
        "intrabar": IntrabarExecution,
    }
    if name in registry:
        return registry[name]()
    raise ValueError(f"Unknown execution_model: {name!r}")


# ── Task handlers ──────────────────────────────────────────────


def _handle_indicator(spec: TaskSpec, data: dict) -> Any:
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

    # Pull the close series from the first symbol's first timeframe
    sym = spec.data_spec.symbols[0]
    tf = spec.data_spec.timeframe
    df = data.get(sym, {}).get(tf)
    if df is None or df.empty:
        raise ValueError(f"No data for {sym} {tf}")

    column = cs.params.get("column", "close")
    series = df[column] if column in df.columns else df["close"]
    kwargs = cs.params.get("kwargs", {})
    return method(series, **kwargs)


def _handle_backtest(spec: TaskSpec, data: dict) -> Any:
    """Backtest task — call BacktestEngine(...).run() directly.

    Zero refactoring of v1.7 backtest logic — same code path as
    StockStatClient.backtest().
    """
    from ...backtest import BacktestEngine
    from ...compute.engine import ComputeEngine

    cs = spec.compute_spec
    strategy = _deserialize_strategy(cs.strategy_ref, cs.strategy_codec)
    if strategy is None:
        raise ValueError("compute_spec.strategy_ref is required for backtest tasks")

    cost_model = _resolve_cost_model(cs.cost_model) or PercentCost_default()
    fill_model = _resolve_fill_model(cs.fill_model)
    execution_model = _resolve_execution_model(cs.execution_model)

    kwargs = dict(
        data=data,
        strategy=strategy,
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


def PercentCost_default():
    from ...backtest.cost_model import PercentCost
    return PercentCost()


def _handle_grid_search(spec: TaskSpec, data: dict, *, backend) -> Any:
    """Grid search task — call optimizer.grid_search().

    For LocalComputeBackend, runs serially in-process. For
    RemoteComputeBackend (Phase 3+), Dispatcher shards the param_grid
    and each Worker runs a slice in parallel.
    """
    from itertools import product
    from ...backtest import BacktestEngine
    from ...compute.engine import ComputeEngine

    cs = spec.compute_spec
    if not cs.param_grid:
        raise ValueError("compute_spec.param_grid is required for grid_search tasks")

    strategy_ref = cs.strategy_ref
    cost_model = _resolve_cost_model(cs.cost_model) or PercentCost_default()
    fill_model = _resolve_fill_model(cs.fill_model)
    execution_model = _resolve_execution_model(cs.execution_model)

    keys = list(cs.param_grid.keys())
    grids = [dict(zip(keys, vals)) for vals in product(*[cs.param_grid[k] for k in keys])]

    results = []
    total = len(grids)
    for i, params in enumerate(grids):
        # Re-deserialize strategy per iteration (strategies may carry state)
        strategy = _deserialize_strategy(strategy_ref, cs.strategy_codec)
        kwargs = dict(
            data=data,
            strategy=strategy,
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
        # Apply grid params to strategy if it supports update()
        if hasattr(strategy, "update_params"):
            strategy.update_params(params)

        engine = BacktestEngine(**kwargs)
        res = engine.run()
        m = res.metrics()
        val = m.get(cs.metric, float("-inf"))
        results.append({"params": params, cs.metric: val, "result": res})

        # Publish progress as partials
        backend.publish_partial(
            spec.task_id,
            {"completed": i + 1, "total": total, "progress": (i + 1) / total},
        )

    # Sort best-first if maximizing
    results.sort(key=lambda x: x[cs.metric], reverse=cs.maximize)
    return results


def _handle_batch_backtest(spec: TaskSpec, data: dict, *, backend) -> Any:
    """Batch backtest task — call StrategyBatchRunner.run_all_fees()."""
    from ...backtest.batch_runner import StrategyBatchRunner

    cs = spec.compute_spec
    if not cs.strategies or not cs.fee_models:
        raise ValueError(
            "compute_spec.strategies and compute_spec.fee_models are required "
            "for batch_backtest tasks"
        )

    # Deserialize strategies
    strategies = {
        name: _deserialize_strategy(ref, cs.strategy_codec)
        for name, ref in cs.strategies.items()
    }
    # Resolve fee models
    fee_models = {
        name: _resolve_cost_model(name_or_ref)
        for name, name_or_ref in cs.fee_models
    } if all(isinstance(f, str) for f in cs.fee_models) else {
        f"model_{i}": _resolve_cost_model(None) or PercentCost_default()
        for i, _ in enumerate(cs.fee_models)
    }

    # StrategyBatchRunner.run_all_fees expects a {name: CostModel} dict
    runner = StrategyBatchRunner(
        data=data,
        initial_cash=cs.initial_cash,
        benchmark=cs.benchmark,
        trade_on=cs.trade_on,
        allow_short=cs.allow_short,
        periods_per_year=cs.periods_per_year,
    )
    results = runner.run_all_fees(strategies, fee_models)
    return results.to_dataframe()


def _handle_monte_carlo(spec: TaskSpec, data: dict, *, backend) -> Any:
    """Monte Carlo simulation task."""
    from ...backtest import BacktestEngine
    from ...backtest.montecarlo import monte_carlo_equity
    from ...compute.engine import ComputeEngine

    cs = spec.compute_spec
    strategy = _deserialize_strategy(cs.strategy_ref, cs.strategy_codec)
    if strategy is None:
        raise ValueError("compute_spec.strategy_ref is required for monte_carlo tasks")

    # Run a baseline backtest to get returns
    cost_model = _resolve_cost_model(cs.cost_model) or PercentCost_default()
    fill_model = _resolve_fill_model(cs.fill_model)
    kwargs = dict(
        data=data,
        strategy=strategy,
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
    engine = BacktestEngine(**kwargs)
    baseline = engine.run()
    returns = baseline.returns

    # Run Monte Carlo
    curves = monte_carlo_equity(
        returns, initial=cs.initial_cash,
        n_samples=cs.n_simulations, seed=cs.seed,
    )
    return {
        "baseline": baseline,
        "equity_curves": curves,
        "n_simulations": cs.n_simulations,
    }
