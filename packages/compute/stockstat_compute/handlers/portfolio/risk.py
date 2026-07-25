"""risk_metrics handler — 风险度量。"""
from __future__ import annotations
from typing import Any, Optional, Callable
import numpy as np
from stockstat_foundation import TaskSpec
from .._base import register


@register("risk_metrics")
def handle_risk_metrics(spec: TaskSpec, data: Any, *, on_progress: Optional[Callable] = None) -> Any:
    cs = spec.compute_spec
    confidence = cs.params.get("confidence", 0.95)
    returns = np.asarray(data if data is not None else cs.params.get("returns"), dtype=float)
    var = np.percentile(returns, (1 - confidence) * 100)
    cvar = returns[returns <= var].mean() if len(returns[returns <= var]) > 0 else var
    cumulative = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - peak) / peak
    max_dd = float(drawdown.min())
    sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0
    downside = returns[returns < 0]
    sortino = float(returns.mean() / downside.std() * np.sqrt(252)) if len(downside) > 0 and downside.std() > 0 else 0.0
    calmar = float((cumulative[-1] ** (252 / len(returns)) - 1) / abs(max_dd)) if max_dd < 0 else 0.0
    return {"var": float(var), "cvar": float(cvar), "max_drawdown": max_dd,
            "sharpe": sharpe, "sortino": sortino, "calmar": calmar,
            "volatility": float(returns.std() * np.sqrt(252)),
            "confidence": confidence}
