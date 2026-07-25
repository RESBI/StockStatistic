"""TaskSpec 三段式 — DataSpec + ComputeSpec + DispatchSpec。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional


@dataclass
class DataSpec:
    """描述需要什么数据 — 任何任务类型通用。"""
    symbols: list = field(default_factory=list)
    timeframe: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    source: Optional[str] = None

    def cache_key(self) -> str:
        """sha256(symbols + timeframe + start + end + source) 前 32 字节。"""
        raw = "|".join([
            ",".join(sorted(self.symbols)),
            self.timeframe,
            self.start or "",
            self.end or "",
            self.source or "",
        ]).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

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


@dataclass
class DispatchSpec:
    """描述如何分发 — 任何任务类型通用。"""
    split_strategy: str = "auto"
    max_workers: Optional[int] = None
    data_dispatch: str = "auto"
    priority: int = 0
    timeout: int = 3600
    retry_count: int = 0
    preemptable: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

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
    """描述做什么计算 — 按 task_type 分发到对应 handler。"""
    task_type: str
    strategy_ref: Optional[str] = None
    strategy_codec: str = "cloudpickle"
    params: dict = field(default_factory=dict)
    # ── 回测类共用字段 ──
    initial_cash: float = 1_000_000.0
    cost_model: Optional[str] = None
    fill_model: Optional[str] = None
    execution_model: Optional[str] = None
    benchmark: Optional[str] = None
    trade_on: str = "open"
    allow_short: bool = False
    periods_per_year: Optional[int] = None
    # ── grid_search/batch_backtest 共用 ──
    param_grid: Optional[dict] = None
    metric: str = "sharpe"
    maximize: bool = True
    strategies: Optional[dict] = None
    fee_models: Optional[list] = None
    # ── monte_carlo 共用 ──
    n_simulations: int = 1000
    seed: int = 0

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "strategy_ref": self.strategy_ref,
            "strategy_codec": self.strategy_codec,
            "params": dict(self.params) if self.params else {},
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
            "fee_models": list(self.fee_models) if self.fee_models else None,
            "n_simulations": self.n_simulations,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ComputeSpec":
        return cls(
            task_type=d.get("task_type", "custom"),
            strategy_ref=d.get("strategy_ref"),
            strategy_codec=d.get("strategy_codec", "cloudpickle"),
            params=dict(d.get("params", {}) or {}),
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
            fee_models=list(d.get("fee_models")) if d.get("fee_models") else None,
            n_simulations=int(d.get("n_simulations", 1000)),
            seed=int(d.get("seed", 0)),
        )


@dataclass
class TaskSpec:
    """完整任务规范 — 三段式。"""
    task_id: str
    data_spec: DataSpec
    compute_spec: ComputeSpec
    dispatch_spec: DispatchSpec = field(default_factory=DispatchSpec)
    trace_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "data_spec": self.data_spec.to_dict(),
            "compute_spec": self.compute_spec.to_dict(),
            "dispatch_spec": self.dispatch_spec.to_dict(),
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskSpec":
        created_at = d.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = datetime.utcnow()
        elif created_at is None:
            created_at = datetime.utcnow()
        return cls(
            task_id=d["task_id"],
            data_spec=DataSpec.from_dict(d.get("data_spec", {})),
            compute_spec=ComputeSpec.from_dict(d.get("compute_spec", {})),
            dispatch_spec=DispatchSpec.from_dict(d.get("dispatch_spec", {})),
            trace_id=d.get("trace_id", ""),
            created_at=created_at,
            created_by=d.get("created_by", ""),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_json(cls, s: str) -> "TaskSpec":
        return cls.from_dict(json.loads(s))


__all__ = ["TaskSpec", "DataSpec", "ComputeSpec", "DispatchSpec"]
