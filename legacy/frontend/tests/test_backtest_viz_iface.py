"""BT-V0: Backtest visualization interface skeleton tests.

Validates BacktestChartSpec, SubplotSpec, ChartSeries dataclasses, the chart
registry, NullBacktestChartRenderer fallback, and chart_factory detection —
all without requiring matplotlib.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost
from stockstat.backtest.chart_spec import (
    BacktestChartSpec, ChartSeries, SubplotSpec,
)
from stockstat.backtest.chart_registry import (
    register_chart, get_chart_builder, list_chart_types, build_chart,
)
from stockstat.backtest.chart_factory import detect, get_chart_renderer
from stockstat.backtest.null_charts import NullBacktestChartRenderer


def _make_result(n=120):
    rng = np.random.RandomState(0)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))

    @strategy
    def s(ctx):
        d = ctx.get("X", "1d", lookback=30)
        if len(d) < 21:
            return
        if d.close.rolling(5).mean().iloc[-1] > d.close.rolling(20).mean().iloc[-1]:
            if ctx.portfolio.get_position("X").qty == 0:
                ctx.broker.submit(Order("X", "buy", 10))

    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": 1e6}, index=dates)
    eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                         initial_cash=100000, cost_model=ZeroCost(),
                         benchmark="X")
    return eng.run()


# ── ChartSpec dataclasses ──

class TestChartSpec:
    def test_backtest_chart_spec_defaults(self):
        spec = BacktestChartSpec()
        assert spec.subplots == []
        assert spec.layout == (1, 1)
        assert spec.chart_type == "custom"

    def test_add_subplot_returns_subplot(self):
        spec = BacktestChartSpec(title="T")
        sp = spec.add_subplot(title="sub", y_label="y")
        assert isinstance(sp, SubplotSpec)
        assert sp.title == "sub"
        assert spec.n_subplots == 1

    def test_subplot_add_series(self):
        sp = SubplotSpec()
        s = sp.add_series(name="x", data=pd.Series([1, 2, 3]), kind="line")
        assert isinstance(s, ChartSeries)
        assert s.kind == "line"
        assert len(sp.series) == 1

    def test_chart_series_kinds(self):
        for kind in ("line", "bar", "scatter", "fill", "histogram", "heatmap"):
            s = ChartSeries(name="x", data=pd.Series([1]), kind=kind)
            assert s.kind == kind

    def test_chart_series_fill_to(self):
        s = ChartSeries(name="dd", data=pd.Series([-0.1, -0.2]),
                        kind="fill", fill_to=0.0, alpha=0.5)
        assert s.fill_to == 0.0
        assert s.alpha == 0.5

    def test_chart_series_heatmap_cmap(self):
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        s = ChartSeries(name="hm", data=df, kind="heatmap", cmap="RdYlGn")
        assert s.cmap == "RdYlGn"

    def test_to_dict_serializable(self):
        spec = BacktestChartSpec(title="T", chart_type="equity_curve")
        sp = spec.add_subplot(y_label="Equity")
        sp.add_series(name="s", data=pd.Series([1, 2], index=pd.date_range("2024-01-01", periods=2)))
        d = spec.to_dict()
        assert d["title"] == "T"
        assert d["chart_type"] == "equity_curve"
        assert len(d["subplots"]) == 1
        assert d["subplots"][0]["series"][0]["name"] == "s"


# ── Registry ──

class TestRegistry:
    def test_register_and_get(self):
        @register_chart("test_only")
        def builder(result, **kw):
            return BacktestChartSpec(chart_type="test_only")

        assert get_chart_builder("test_only") is builder
        assert "test_only" in list_chart_types()

    def test_build_chart(self):
        @register_chart("test_build")
        def builder(result, **kw):
            return BacktestChartSpec(chart_type="test_build", title=kw.get("title", "x"))

        spec = build_chart("test_build", None, title="hello")
        assert spec.chart_type == "test_build"
        assert spec.title == "hello"

    def test_build_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown chart type"):
            build_chart("does_not_exist", None)


# ── Null renderer ──

class TestNullRenderer:
    def test_available_false(self):
        r = NullBacktestChartRenderer()
        assert r.available() is False

    def test_render_warns(self):
        r = NullBacktestChartRenderer()
        spec = BacktestChartSpec()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = r.render(spec)
            assert result is None
            assert len(w) == 1
            assert "stockstat[backtest_viz]" in str(w[0].message)

    def test_savefig_warns(self):
        r = NullBacktestChartRenderer()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r.savefig("test.png")
            assert len(w) == 1


# ── Factory ──

class TestFactory:
    def test_detect_returns_string(self):
        assert detect() in ("matplotlib", "null")

    def test_get_null_renderer(self):
        r = get_chart_renderer("null")
        assert isinstance(r, NullBacktestChartRenderer)
        assert r.available() is False

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError):
            get_chart_renderer("nonexistent")


# ── BacktestResult integration ──

class TestResultChartAPI:
    def test_available_chart_types(self):
        res = _make_result()
        types = res.available_chart_types
        assert "equity_curve" in types
        assert "drawdown" in types
        assert "trades_overlay" in types

    def test_chart_returns_spec(self):
        res = _make_result()
        spec = res.chart("equity_curve")
        assert isinstance(spec, BacktestChartSpec)
        assert spec.chart_type == "equity_curve"
        assert spec.n_subplots == 1

    def test_chart_drawdown_has_fill(self):
        res = _make_result()
        spec = res.chart("drawdown")
        # drawdown spec should contain a fill series
        kinds = [s.kind for s in spec.subplots[0].series]
        assert "fill" in kinds

    def test_chart_trades_overlay(self):
        res = _make_result()
        spec = res.chart("trades_overlay")
        assert spec.annotate_trades is True
        assert spec.chart_type == "trades_overlay"

    def test_chart_returns_distribution(self):
        res = _make_result()
        spec = res.chart("returns_distribution")
        assert spec.chart_type == "returns_distribution"
        assert spec.subplots[0].series[0].kind == "histogram"

    def test_chart_monthly_heatmap(self):
        res = _make_result()
        spec = res.chart("monthly_heatmap")
        assert spec.chart_type == "monthly_heatmap"

    def test_chart_yearly_returns(self):
        res = _make_result()
        spec = res.chart("yearly_returns")
        assert spec.chart_type == "yearly_returns"

    def test_chart_underwater_curve(self):
        res = _make_result()
        spec = res.chart("underwater_curve")
        assert spec.chart_type == "underwater_curve"

    def test_render_with_null_warns(self):
        res = _make_result()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            fig = res.render("equity_curve", renderer=get_chart_renderer("null"))
            assert fig is None
            assert len(w) == 1

    def test_render_savefig_skipped_when_unavailable(self, tmp_path):
        res = _make_result()
        path = str(tmp_path / "out.png")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res.render("equity_curve", path=path, renderer=get_chart_renderer("null"))
            # savefig should be skipped (file not created) since unavailable
            assert not os.path.exists(path)


# ── Back-compat: generic PlotSpec still works ──

class TestBackCompat:
    def test_plot_equity_returns_plot_spec(self):
        from stockstat.plot.base import PlotSpec
        res = _make_result()
        spec = res.plot_equity()
        assert isinstance(spec, PlotSpec)

    def test_plot_drawdown_returns_plot_spec(self):
        from stockstat.plot.base import PlotSpec
        res = _make_result()
        spec = res.plot_drawdown()
        assert isinstance(spec, PlotSpec)
