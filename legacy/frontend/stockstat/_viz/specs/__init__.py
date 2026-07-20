"""Unified Spec system — backend-agnostic plot specifications.

v2.0 unifies the v1.7 ``PlotSpec`` and ``BacktestChartSpec`` into a
single ``PlotSpec``. Backtest-specific charts are defined as
``ChartProfile`` presets (named configurations that build a PlotSpec
from a BacktestResult).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

import numpy as np
import pandas as pd


@dataclass
class SeriesSpec:
    """Specification for a single data series in a plot."""
    name: str
    data: Union[pd.Series, pd.DataFrame, np.ndarray, list]
    kind: str = "line"  # line|bar|scatter|fill|histogram|heatmap
    color: Optional[str] = None
    secondary_y: bool = False
    alpha: float = 1.0
    fill_to: Optional[float] = None
    bins: int = 50
    cmap: Optional[str] = None
    marker: Optional[str] = None
    linewidth: float = 1.5


@dataclass
class MarkerSpec:
    """A point marker on a plot."""
    ts: Any  # pd.Timestamp
    label: str
    direction: str = "up"  # up|down


@dataclass
class SubplotSpec:
    """A subplot within a multi-panel PlotSpec."""
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    series: list[SeriesSpec] = field(default_factory=list)
    log_x: bool = False
    log_y: bool = False
    share_x: bool = True

    def add_series(self, **kwargs) -> "SubplotSpec":
        self.series.append(SeriesSpec(**kwargs))
        return self


@dataclass
class PlotSpec:
    """Backend-agnostic plot specification (unified).

    Supports two modes:
    1. **Simple mode**: populate ``series`` directly.
    2. **Subplot mode**: populate ``subplots`` for multi-panel layouts.

    Supported ``kind`` values: ``line``, ``bar``, ``scatter``, ``fill``,
    ``histogram``, ``heatmap``.
    """
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    series: list[SeriesSpec] = field(default_factory=list)
    markers: list[MarkerSpec] = field(default_factory=list)
    x_type: str = "datetime"
    subplots: list[SubplotSpec] = field(default_factory=list)
    layout: tuple[int, int] = (1, 1)
    figsize: tuple[float, float] = (12.0, 6.0)
    log_x: bool = False
    log_y: bool = False
    theme: str = "default"

    def add_series(self, name: str, data=None, kind: str = "line", **kwargs) -> "PlotSpec":
        self.series.append(SeriesSpec(name=name, data=data, kind=kind, **kwargs))
        return self

    def add_subplot(self, title: str = "", **kwargs) -> SubplotSpec:
        sp = SubplotSpec(title=title, **kwargs)
        self.subplots.append(sp)
        return sp

    @property
    def n_subplots(self) -> int:
        return len(self.subplots)

    def to_dict(self) -> dict:
        def _series_to_list(data):
            if isinstance(data, pd.DataFrame):
                return data.reset_index().values.tolist()
            if isinstance(data, pd.Series):
                return [[str(t), v] if not isinstance(v, float) else [str(t), v]
                        for t, v in data.items()]
            if isinstance(data, np.ndarray):
                return data.tolist()
            return list(data) if data is not None else []

        return {
            "title": self.title, "x_label": self.x_label,
            "y_label": self.y_label, "x_type": self.x_type,
            "layout": list(self.layout), "figsize": list(self.figsize),
            "log_x": self.log_x, "log_y": self.log_y, "theme": self.theme,
            "series": [{"name": s.name, "data": _series_to_list(s.data),
                        "kind": s.kind, "color": s.color} for s in self.series],
            "markers": [{"ts": str(m.ts), "label": m.label, "direction": m.direction}
                        for m in self.markers],
            "subplots": [{"title": sp.title, "series": [
                {"name": s.name, "kind": s.kind} for s in sp.series
            ]} for sp in self.subplots],
        }


@dataclass
class ChartProfile:
    """A named preset that builds a PlotSpec from a result object.

    v2.0 replaces v1.7's ``BacktestChartSpec`` with ChartProfile —
    a declarative description of how to build a chart from a
    BacktestResult (or any result with equity/fills/metrics).
    """
    name: str
    description: str = ""
    builder: Optional[Any] = None  # callable(result, **kwargs) -> PlotSpec

    def build(self, result: Any, **kwargs) -> PlotSpec:
        if self.builder is None:
            raise ValueError(f"ChartProfile '{self.name}' has no builder")
        return self.builder(result, **kwargs)


# ── Built-in backtest chart profiles ───────────────────────────

def _build_equity_curve(result: Any, **kwargs) -> PlotSpec:
    spec = PlotSpec(title="Equity Curve", x_label="Date", y_label="Equity")
    spec.add_series(name="equity", data=result.equity, kind="line")
    if hasattr(result, "_benchmark_equity") and result._benchmark_equity is not None:
        spec.add_series(name="benchmark", data=result._benchmark_equity,
                        kind="line", color="orange")
    return spec


def _build_drawdown(result: Any, **kwargs) -> PlotSpec:
    equity = result.equity
    drawdown = equity / equity.cummax() - 1
    spec = PlotSpec(title="Drawdown", x_label="Date", y_label="Drawdown")
    spec.add_series(name="drawdown", data=drawdown, kind="fill", fill_to=0,
                    color="red", alpha=0.3)
    return spec


def _build_trades(result: Any, **kwargs) -> PlotSpec:
    spec = PlotSpec(title="Trades", x_label="Date", y_label="Price")
    # Trades as markers on the equity curve
    for fill in result.fills:
        spec.markers.append(MarkerSpec(
            ts=fill.ts, label=f"{fill.side.value} {fill.qty:.2f}",
            direction="up" if fill.side.value == "buy" else "down",
        ))
    spec.add_series(name="equity", data=result.equity, kind="line")
    return spec


def _build_returns_distribution(result: Any, **kwargs) -> PlotSpec:
    returns = result.equity.pct_change().dropna()
    spec = PlotSpec(title="Returns Distribution", x_label="Return", y_label="Frequency")
    spec.add_series(name="returns", data=returns, kind="histogram", bins=50)
    return spec


def _build_monthly_heatmap(result: Any, **kwargs) -> PlotSpec:
    returns = result.equity.pct_change().dropna()
    monthly = returns.resample("M").apply(lambda x: (1 + x).prod() - 1)
    # Pivot to year x month
    monthly_df = pd.DataFrame({
        "year": monthly.index.year,
        "month": monthly.index.month,
        "return": monthly.values,
    })
    pivot = monthly_df.pivot(index="year", columns="month", values="return")
    spec = PlotSpec(title="Monthly Returns Heatmap", x_label="Month", y_label="Year")
    spec.add_series(name="monthly", data=pivot, kind="heatmap", cmap="RdYlGn")
    return spec


def _build_dashboard(result: Any, **kwargs) -> PlotSpec:
    spec = PlotSpec(title="Backtest Dashboard", layout=(2, 2), figsize=(14, 10))
    # Panel 1: equity
    sp1 = spec.add_subplot(title="Equity Curve")
    sp1.add_series(name="equity", data=result.equity, kind="line")
    # Panel 2: drawdown
    equity = result.equity
    drawdown = equity / equity.cummax() - 1
    sp2 = spec.add_subplot(title="Drawdown")
    sp2.add_series(name="drawdown", data=drawdown, kind="fill", fill_to=0, color="red")
    # Panel 3: returns distribution
    returns = equity.pct_change().dropna()
    sp3 = spec.add_subplot(title="Returns Distribution")
    sp3.add_series(name="returns", data=returns, kind="histogram", bins=30)
    # Panel 4: monthly heatmap
    monthly = returns.resample("M").apply(lambda x: (1 + x).prod() - 1)
    monthly_df = pd.DataFrame({
        "year": monthly.index.year, "month": monthly.index.month,
        "return": monthly.values,
    })
    pivot = monthly_df.pivot(index="year", columns="month", values="return")
    sp4 = spec.add_subplot(title="Monthly Returns")
    sp4.add_series(name="monthly", data=pivot, kind="heatmap", cmap="RdYlGn")
    return spec


# Registry of built-in chart profiles
BUILTIN_PROFILES: dict[str, ChartProfile] = {
    "equity_curve": ChartProfile("equity_curve", "Equity curve + benchmark", _build_equity_curve),
    "drawdown": ChartProfile("drawdown", "Drawdown fill area", _build_drawdown),
    "trades_overlay": ChartProfile("trades_overlay", "Trade markers on equity", _build_trades),
    "returns_distribution": ChartProfile("returns_distribution", "Return histogram", _build_returns_distribution),
    "monthly_heatmap": ChartProfile("monthly_heatmap", "Monthly returns heatmap", _build_monthly_heatmap),
    "dashboard": ChartProfile("dashboard", "2x2 dashboard", _build_dashboard),
}


def get_profile(name: str) -> Optional[ChartProfile]:
    return BUILTIN_PROFILES.get(name)


def list_profiles() -> list[str]:
    return list(BUILTIN_PROFILES.keys())
