"""Task specification — V2 §12.5 three-section TaskSpec.

A TaskSpec describes "what to compute" without describing "how to
transmit it". Three independent sections:

- ``data_spec``: what data is needed (symbols/tf/range). Generic across
  all task types.
- ``compute_spec``: what computation to run (strategy/params/config).
  Specific per ``task_type``.
- ``dispatch_spec``: how to dispatch (split strategy / worker count /
  data transfer mode). Generic across all task types.

Adding a new task type requires only:
1. Define a new ``task_type`` string
2. Define the ``compute_spec`` schema for it
3. Implement a Worker-side TaskHandler

Protocol, envelope, and transport layers need zero changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class DataSpec:
    """Describes what data a task needs — V2 §12.5 ``data_spec``.

    Generic across all task types. Resolved by Dispatcher into actual
    OHLCV data fetched from Storage (one fetch, cached for all workers).
    """

    symbols: list[str]
    timeframe: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "start": self.start,
            "end": self.end,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DataSpec":
        return cls(
            symbols=list(d.get("symbols", [])),
            timeframe=d.get("timeframe", "1d"),
            start=d.get("start"),
            end=d.get("end"),
            source=d.get("source"),
        )

    def cache_key(self) -> str:
        """Stable hash for Dispatcher data cache (V2 §9.5)."""
        import hashlib
        h = hashlib.sha256()
        h.update("|".join(self.symbols).encode("utf-8"))
        h.update(b"|")
        h.update(self.timeframe.encode("utf-8"))
        h.update(b"|")
        h.update((self.start or "").encode("utf-8"))
        h.update(b"|")
        h.update((self.end or "").encode("utf-8"))
        h.update(b"|")
        h.update((self.source or "").encode("utf-8"))
        return h.hexdigest()


@dataclass
class DispatchSpec:
    """Describes how to dispatch a task — V2 §12.5 ``dispatch_spec``.

    Generic across all task types. Controls sharding, worker selection,
    data transfer strategy, priority, timeout, retries, preemption.
    """

    split_strategy: str = "auto"  # auto / param_wise / symbol_wise / time_wise / none
    max_workers: Optional[int] = None
    data_dispatch: str = "auto"  # auto / inline / shared_memory / stream / storage_ref
    priority: int = 0  # 0 normal / -1 high / 1 low
    timeout: int = 3600  # seconds
    retry_count: int = 0
    preemptable: bool = False  # V2 §13.3: allow preemption by higher-priority tasks

    def to_dict(self) -> dict:
        return {
            "split_strategy": self.split_strategy,
            "max_workers": self.max_workers,
            "data_dispatch": self.data_dispatch,
            "priority": self.priority,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "preemptable": self.preemptable,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DispatchSpec":
        return cls(
            split_strategy=d.get("split_strategy", "auto"),
            max_workers=d.get("max_workers"),
            data_dispatch=d.get("data_dispatch", "auto"),
            priority=int(d.get("priority", 0)),
            timeout=int(d.get("timeout", 3600)),
            retry_count=int(d.get("retry_count", 0)),
            preemptable=bool(d.get("preemptable", False)),
        )


@dataclass
class ComputeSpec:
    """Describes what computation to run — V2 §12.5 ``compute_spec``.

    Fields are dispatched by ``task_type`` to the corresponding
    TaskHandler on the Worker side. Common fields are listed here;
    task-type-specific fields go in ``params``.

    Supported task types (V3 initial set):
    - ``indicator``: remote indicator calculation
    - ``backtest``: single backtest run
    - ``grid_search``: parameter grid search (sharded across workers)
    - ``batch_backtest``: batch strategies x fee models
    - ``monte_carlo``: Monte Carlo simulation (sharded by simulation count)
    - ``custom``: user-defined task type (register handler on Worker)
    """

    task_type: str
    # ── Generic fields ──
    strategy_ref: Optional[str] = None  # cloudpickle:base64... or registered name
    strategy_codec: str = "cloudpickle"  # cloudpickle / json / none
    params: dict = field(default_factory=dict)  # task-type-specific params
    # ── Backtest-related ──
    initial_cash: float = 1_000_000.0
    cost_model: Optional[str] = None  # registered name, e.g. "binance_spot"
    fill_model: Optional[str] = None
    execution_model: Optional[str] = None
    benchmark: Optional[str] = None
    trade_on: str = "open"
    allow_short: bool = False
    periods_per_year: Optional[int] = None
    # ── grid_search ──
    param_grid: Optional[dict] = None
    metric: str = "sharpe"
    maximize: bool = True
    # ── batch_backtest ──
    strategies: Optional[dict] = None  # {name: strategy_ref}
    fee_models: Optional[list] = None
    # ── monte_carlo ──
    n_simulations: int = 1000
    seed: int = 0

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "strategy_ref": self.strategy_ref,
            "strategy_codec": self.strategy_codec,
            "params": self.params,
            "initial_cash": self.initial_cash,
            "cost_model": self.cost_model,
            "fill_model": self.fill_model,
            "execution_model": self.execution_model,
            "benchmark": self.benchmark,
            "trade_on": self.trade_on,
            "allow_short": self.allow_short,
            "periods_per_year": self.periods_per_year,
            "param_grid": self.param_grid,
            "metric": self.metric,
            "maximize": self.maximize,
            "strategies": self.strategies,
            "fee_models": self.fee_models,
            "n_simulations": self.n_simulations,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ComputeSpec":
        return cls(
            task_type=d.get("task_type", "custom"),
            strategy_ref=d.get("strategy_ref"),
            strategy_codec=d.get("strategy_codec", "cloudpickle"),
            params=d.get("params", {}) or {},
            initial_cash=float(d.get("initial_cash", 1_000_000.0)),
            cost_model=d.get("cost_model"),
            fill_model=d.get("fill_model"),
            execution_model=d.get("execution_model"),
            benchmark=d.get("benchmark"),
            trade_on=d.get("trade_on", "open"),
            allow_short=bool(d.get("allow_short", False)),
            periods_per_year=d.get("periods_per_year"),
            param_grid=d.get("param_grid"),
            metric=d.get("metric", "sharpe"),
            maximize=bool(d.get("maximize", True)),
            strategies=d.get("strategies"),
            fee_models=d.get("fee_models"),
            n_simulations=int(d.get("n_simulations", 1000)),
            seed=int(d.get("seed", 0)),
        )


@dataclass
class TaskSpec:
    """Complete task specification — V2 §12.5 three-section TaskSpec.

    The unit of work submitted by a Client to a ComputeBackend. The
    spec itself is JSON-serializable (all bytes/binary payloads go in
    Envelope.payload, not in TaskSpec).
    """

    task_id: str
    data_spec: DataSpec
    compute_spec: ComputeSpec
    dispatch_spec: DispatchSpec = field(default_factory=DispatchSpec)
    trace_id: str = ""  # distributed tracing ID (V2 §12.13)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""  # client identifier

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "data_spec": self.data_spec.to_dict(),
            "compute_spec": self.compute_spec.to_dict(),
            "dispatch_spec": self.dispatch_spec.to_dict(),
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskSpec":
        return cls(
            task_id=d["task_id"],
            data_spec=DataSpec.from_dict(d.get("data_spec", {})),
            compute_spec=ComputeSpec.from_dict(d.get("compute_spec", {})),
            dispatch_spec=DispatchSpec.from_dict(d.get("dispatch_spec", {})),
            trace_id=d.get("trace_id", ""),
            created_at=_parse_dt(d.get("created_at")) or datetime.utcnow(),
            created_by=d.get("created_by", ""),
        )


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def new_task_id() -> str:
    """Generate a fresh UUID v4 task ID."""
    import uuid
    return str(uuid.uuid4())
