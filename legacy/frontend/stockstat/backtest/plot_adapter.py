from __future__ import annotations

from typing import Optional

import pandas as pd

from ..plot.base import PlotSpec
from .chart_spec import BacktestChartSpec, ChartSeries, SubplotSpec
from .chart_registry import register_chart
from .result import BacktestResult


# ── Generic PlotSpec builders (back-compat, no matplotlib needed) ──

def plot_equity(result: BacktestResult, benchmark: bool = True) -> PlotSpec:
    spec = PlotSpec(
        title="Equity Curve",
        x_label="Date",
        y_label="Equity",
    )
    spec.add_series(name="strategy", data=result.equity, kind="line")
    if benchmark and result.benchmark is not None:
        spec.add_series(name="benchmark", data=result.benchmark, kind="line", color="gray")
    return spec


def plot_drawdown(result: BacktestResult) -> PlotSpec:
    spec = PlotSpec(
        title="Drawdown",
        x_label="Date",
        y_label="Drawdown",
    )
    spec.add_series(name="drawdown", data=result.drawdown, kind="line", color="red")
    return spec


def plot_trades(result: BacktestResult) -> PlotSpec:
    spec = PlotSpec(
        title="Trades on Equity",
        x_label="Date",
        y_label="Equity",
    )
    spec.add_series(name="equity", data=result.equity, kind="line")
    buys = [f for f in result.fills if str(getattr(f.side, "value", f.side)) == "buy"]
    sells = [f for f in result.fills if str(getattr(f.side, "value", f.side)) == "sell"]
    if buys:
        ts = pd.DatetimeIndex([f.ts for f in buys])
        spec.add_series(name="buy", data=pd.Series([result.equity.reindex([t], method="ffill").iloc[0] for t in ts], index=ts), kind="scatter", color="green")
    if sells:
        ts = pd.DatetimeIndex([f.ts for f in sells])
        spec.add_series(name="sell", data=pd.Series([result.equity.reindex([t], method="ffill").iloc[0] for t in ts], index=ts), kind="scatter", color="red")
    return spec


# ── BacktestChartSpec builders (richer, BT-V series) ──

@register_chart("equity_curve")
def _equity_curve(result: BacktestResult, **kw) -> BacktestChartSpec:
    spec = BacktestChartSpec(
        title=kw.get("title", "Equity Curve"),
        x_label="Date",
        layout=(1, 1),
        figsize=(12, 6),
        source_result=result,
        chart_type="equity_curve",
    )
    sp = spec.add_subplot(y_label="Equity")
    sp.add_series(name="strategy", data=result.equity, kind="line", color="steelblue", linewidth=2.0)
    if result.benchmark is not None:
        sp.add_series(name="benchmark", data=result.benchmark, kind="line", color="gray", linewidth=1.0)
    return spec


@register_chart("drawdown")
def _drawdown(result: BacktestResult, **kw) -> BacktestChartSpec:
    spec = BacktestChartSpec(
        title=kw.get("title", "Drawdown"),
        x_label="Date",
        layout=(1, 1),
        figsize=(12, 4),
        source_result=result,
        chart_type="drawdown",
    )
    sp = spec.add_subplot(y_label="Drawdown")
    sp.add_series(name="drawdown", data=result.drawdown, kind="fill",
                  color="salmon", alpha=0.5, fill_to=0.0)
    sp.add_series(name="drawdown_line", data=result.drawdown, kind="line",
                  color="red", linewidth=1.0)
    return spec


@register_chart("trades_overlay")
def _trades_overlay(result: BacktestResult, **kw) -> BacktestChartSpec:
    spec = BacktestChartSpec(
        title=kw.get("title", "Trades on Equity"),
        x_label="Date",
        layout=(1, 1),
        figsize=(12, 6),
        annotate_trades=True,
        source_result=result,
        chart_type="trades_overlay",
    )
    sp = spec.add_subplot(y_label="Equity")
    sp.add_series(name="equity", data=result.equity, kind="line", color="steelblue", linewidth=1.5)
    buys = [f for f in result.fills if str(getattr(f.side, "value", f.side)) == "buy"]
    sells = [f for f in result.fills if str(getattr(f.side, "value", f.side)) == "sell"]
    if buys:
        ts = pd.DatetimeIndex([f.ts for f in buys])
        vals = pd.Series([result.equity.reindex([t], method="ffill").iloc[0] for t in ts], index=ts)
        sp.add_series(name="buy", data=vals, kind="scatter", color="green", marker="^")
    if sells:
        ts = pd.DatetimeIndex([f.ts for f in sells])
        vals = pd.Series([result.equity.reindex([t], method="ffill").iloc[0] for t in ts], index=ts)
        sp.add_series(name="sell", data=vals, kind="scatter", color="red", marker="v")
    return spec


@register_chart("returns_distribution")
def _returns_distribution(result: BacktestResult, **kw) -> BacktestChartSpec:
    spec = BacktestChartSpec(
        title=kw.get("title", "Returns Distribution"),
        x_label="Return",
        layout=(1, 1),
        figsize=(10, 5),
        source_result=result,
        chart_type="returns_distribution",
    )
    sp = spec.add_subplot(y_label="Frequency")
    sp.add_series(name="returns", data=result.returns, kind="histogram",
                  color="steelblue", alpha=0.7, bins=kw.get("bins", 50))
    return spec


@register_chart("monthly_heatmap")
def _monthly_heatmap(result: BacktestResult, **kw) -> BacktestChartSpec:
    spec = BacktestChartSpec(
        title=kw.get("title", "Monthly Returns Heatmap"),
        layout=(1, 1),
        figsize=(10, 5),
        source_result=result,
        chart_type="monthly_heatmap",
    )
    rets = result.returns
    if not rets.empty:
        monthly = rets.resample("ME").sum() if hasattr(rets.index, "freq") or True else rets.resample("M").sum()
        try:
            monthly = rets.resample("ME").sum()
        except (ValueError, TypeError):
            monthly = rets.resample("M").sum()
        if not monthly.empty:
            df = monthly.to_frame("ret")
            df["year"] = df.index.year
            df["month"] = df.index.month
            pivot = df.pivot_table(index="year", columns="month", values="ret", aggfunc="sum")
            sp = spec.add_subplot()
            sp.add_series(name="monthly", data=pivot, kind="heatmap", cmap="RdYlGn")
    return spec


@register_chart("yearly_returns")
def _yearly_returns(result: BacktestResult, **kw) -> BacktestChartSpec:
    spec = BacktestChartSpec(
        title=kw.get("title", "Yearly Returns"),
        x_label="Year",
        layout=(1, 1),
        figsize=(10, 5),
        source_result=result,
        chart_type="yearly_returns",
    )
    rets = result.returns
    if not rets.empty:
        try:
            yearly = rets.resample("YE").sum()
        except (ValueError, TypeError):
            yearly = rets.resample("A").sum()
        sp = spec.add_subplot(y_label="Return")
        sp.add_series(name="yearly", data=yearly, kind="bar", color="steelblue")
    return spec


@register_chart("underwater_curve")
def _underwater(result: BacktestResult, **kw) -> BacktestChartSpec:
    spec = BacktestChartSpec(
        title=kw.get("title", "Underwater Curve"),
        x_label="Date",
        layout=(1, 1),
        figsize=(12, 4),
        source_result=result,
        chart_type="underwater_curve",
    )
    sp = spec.add_subplot(y_label="Drawdown")
    sp.add_series(name="underwater", data=result.drawdown, kind="fill",
                  color="lightblue", alpha=0.6, fill_to=0.0)
    return spec


@register_chart("parameter_heatmap")
def _parameter_heatmap(result: BacktestResult, **kw) -> BacktestChartSpec:
    """Render a parameter grid heatmap.

    Requires `grid_results`: list of (params_dict, metric_value, BacktestResult)
    as produced by `optimizer.grid_search`. Pass via kw:
        result.chart("parameter_heatmap", grid_results=results, metric="sharpe")
    """
    grid_results = kw.get("grid_results", [])
    metric = kw.get("metric", "sharpe")
    spec = BacktestChartSpec(
        title=kw.get("title", f"Parameter Heatmap ({metric})"),
        layout=(1, 1),
        figsize=(8, 6),
        source_result=result,
        chart_type="parameter_heatmap",
    )
    if grid_results:
        # extract two param keys
        first_params = grid_results[0][0]
        keys = list(first_params.keys())
        if len(keys) >= 2:
            kx, ky = keys[0], keys[1]
            rows = sorted({p[ky] for p, _, _ in grid_results})
            cols = sorted({p[kx] for p, _, _ in grid_results})
            mat = pd.DataFrame(index=rows, columns=cols, dtype=float)
            for p, v, _ in grid_results:
                mat.loc[p[ky], p[kx]] = v
            sp = spec.add_subplot()
            sp.add_series(name=metric, data=mat, kind="heatmap", cmap="RdYlGn")
    return spec


@register_chart("dashboard")
def _dashboard(result: BacktestResult, **kw) -> BacktestChartSpec:
    """Combined dashboard: equity + drawdown + returns distribution.

    Layout 2x2 with four subplots. Pass `grid_results` to swap the 4th panel
    for a parameter heatmap.
    """
    grid_results = kw.get("grid_results")
    panels = kw.get("panels", ["equity", "drawdown", "returns_distribution",
                               "monthly_heatmap" if not grid_results else "parameter_heatmap"])
    spec = BacktestChartSpec(
        title=kw.get("title", "Backtest Dashboard"),
        layout=(2, 2),
        figsize=(14, 10),
        source_result=result,
        chart_type="dashboard",
    )
    for panel in panels:
        if panel == "equity":
            sp = spec.add_subplot(title="Equity Curve", y_label="Equity")
            sp.add_series(name="strategy", data=result.equity, kind="line",
                          color="steelblue", linewidth=1.5)
            if result.benchmark is not None:
                sp.add_series(name="benchmark", data=result.benchmark, kind="line",
                              color="gray", linewidth=1.0)
        elif panel == "drawdown":
            sp = spec.add_subplot(title="Drawdown", y_label="Drawdown")
            sp.add_series(name="dd", data=result.drawdown, kind="fill",
                          color="salmon", alpha=0.5, fill_to=0.0)
        elif panel == "returns_distribution":
            sp = spec.add_subplot(title="Returns Distribution", y_label="Freq")
            sp.add_series(name="rets", data=result.returns, kind="histogram",
                          color="steelblue", alpha=0.7, bins=kw.get("bins", 30))
        elif panel == "monthly_heatmap":
            rets = result.returns
            if not rets.empty:
                try:
                    monthly = rets.resample("ME").sum()
                except (ValueError, TypeError):
                    monthly = rets.resample("M").sum()
                if not monthly.empty:
                    df = monthly.to_frame("ret")
                    df["year"] = df.index.year
                    df["month"] = df.index.month
                    pivot = df.pivot_table(index="year", columns="month",
                                           values="ret", aggfunc="sum")
                    sp = spec.add_subplot(title="Monthly Returns")
                    sp.add_series(name="monthly", data=pivot, kind="heatmap",
                                  cmap="RdYlGn")
        elif panel == "parameter_heatmap" and grid_results:
            first_params = grid_results[0][0]
            keys = list(first_params.keys())
            if len(keys) >= 2:
                kx, ky = keys[0], keys[1]
                rows = sorted({p[ky] for p, _, _ in grid_results})
                cols = sorted({p[kx] for p, _, _ in grid_results})
                mat = pd.DataFrame(index=rows, columns=cols, dtype=float)
                for p, v, _ in grid_results:
                    mat.loc[p[ky], p[kx]] = v
                sp = spec.add_subplot(title="Parameter Heatmap")
                sp.add_series(name="sharpe", data=mat, kind="heatmap", cmap="RdYlGn")
    return spec
