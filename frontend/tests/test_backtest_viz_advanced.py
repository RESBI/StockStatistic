"""BT-V2: Advanced chart tests — histogram, heatmap, bar, parameter heatmap.

Validates that the matplotlib renderer correctly handles histogram (returns
distribution), heatmap (monthly returns, parameter grid), and bar (yearly
returns) chart kinds. Skipped if matplotlib is not installed.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost
from stockstat.backtest.matplotlib_charts import MatplotlibBacktestChartRenderer
from stockstat.backtest.optimizer import grid_search

mpl = pytest.importorskip("matplotlib")
mpl.use("Agg")


def _make_result(n=250, seed=0):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": 1e6}, index=dates)

    @strategy
    def s(ctx):
        d = ctx.get("X", "1d", lookback=30)
        if len(d) < 21:
            return
        ma5 = d.close.rolling(5).mean().iloc[-1]
        ma20 = d.close.rolling(20).mean().iloc[-1]
        pos = ctx.portfolio.get_position("X")
        if ma5 > ma20 and pos.qty == 0:
            ctx.broker.submit(Order("X", "buy", 10))
        elif ma5 < ma20 and pos.qty > 0:
            ctx.broker.submit(Order("X", "sell", pos.qty))

    eng = BacktestEngine(data={"X": {"1d": df}}, strategy=s,
                         initial_cash=100000, cost_model=ZeroCost(),
                         benchmark="X")
    return eng.run()


@pytest.fixture
def result():
    return _make_result()


@pytest.fixture
def renderer():
    return MatplotlibBacktestChartRenderer()


class TestReturnsDistribution:
    def test_spec_has_histogram(self, result):
        spec = result.chart("returns_distribution")
        assert spec.subplots[0].series[0].kind == "histogram"

    def test_renders_figure(self, result, renderer):
        spec = result.chart("returns_distribution")
        fig = renderer.render(spec)
        assert fig is not None

    def test_savefig(self, result, renderer, tmp_path):
        spec = result.chart("returns_distribution")
        renderer.render(spec)
        path = str(tmp_path / "dist.png")
        renderer.savefig(path)
        assert os.path.exists(path)

    def test_custom_bins(self, result, renderer):
        spec = result.chart("returns_distribution", bins=20)
        assert spec.subplots[0].series[0].bins == 20
        fig = renderer.render(spec)
        assert fig is not None


class TestMonthlyHeatmap:
    def test_spec_has_heatmap(self, result):
        spec = result.chart("monthly_heatmap")
        # may be empty if data too short, but if present must be heatmap
        if spec.subplots[0].series:
            assert spec.subplots[0].series[0].kind == "heatmap"

    def test_renders_figure(self, result, renderer):
        spec = result.chart("monthly_heatmap")
        fig = renderer.render(spec)
        assert fig is not None

    def test_savefig(self, result, renderer, tmp_path):
        spec = result.chart("monthly_heatmap")
        renderer.render(spec)
        path = str(tmp_path / "monthly.png")
        renderer.savefig(path)
        assert os.path.exists(path)

    def test_long_data_produces_pivot(self):
        # need >= 2 months of data
        res = _make_result(n=400)
        spec = res.chart("monthly_heatmap")
        if spec.subplots[0].series:
            data = spec.subplots[0].series[0].data
            assert isinstance(data, pd.DataFrame)


class TestYearlyReturns:
    def test_spec_has_bar(self, result):
        spec = result.chart("yearly_returns")
        if spec.subplots[0].series:
            assert spec.subplots[0].series[0].kind == "bar"

    def test_renders_figure(self, result, renderer):
        spec = result.chart("yearly_returns")
        fig = renderer.render(spec)
        assert fig is not None

    def test_savefig(self, result, renderer, tmp_path):
        spec = result.chart("yearly_returns")
        renderer.render(spec)
        path = str(tmp_path / "yearly.png")
        renderer.savefig(path)
        assert os.path.exists(path)


class TestParameterHeatmap:
    def test_spec_with_grid_results(self, result):
        # build a fake grid result
        grid = [
            ({"short": 5, "long": 20}, 1.2, result),
            ({"short": 5, "long": 30}, 0.8, result),
            ({"short": 10, "long": 20}, 1.5, result),
            ({"short": 10, "long": 30}, 0.9, result),
        ]
        spec = result.chart("parameter_heatmap", grid_results=grid, metric="sharpe")
        assert spec.chart_type == "parameter_heatmap"
        assert len(spec.subplots) == 1
        assert spec.subplots[0].series[0].kind == "heatmap"

    def test_renders_figure(self, result, renderer):
        grid = [
            ({"short": 5, "long": 20}, 1.2, result),
            ({"short": 10, "long": 30}, 0.9, result),
        ]
        spec = result.chart("parameter_heatmap", grid_results=grid)
        fig = renderer.render(spec)
        assert fig is not None

    def test_savefig(self, result, renderer, tmp_path):
        grid = [
            ({"short": 5, "long": 20}, 1.2, result),
            ({"short": 10, "long": 30}, 0.9, result),
        ]
        spec = result.chart("parameter_heatmap", grid_results=grid)
        renderer.render(spec)
        path = str(tmp_path / "param_heat.png")
        renderer.savefig(path)
        assert os.path.exists(path)

    def test_empty_grid_no_crash(self, result, renderer):
        spec = result.chart("parameter_heatmap", grid_results=[])
        fig = renderer.render(spec)
        assert fig is not None

    def test_integration_with_grid_search(self, result):
        """End-to-end: run grid search then chart the result."""
        def make_engine(params):
            @strategy
            def s(ctx):
                d = ctx.get("X", "1d", lookback=params["long"] + 5)
                if len(d) < params["long"] + 1:
                    return
                ma_s = d.close.rolling(params["short"]).mean().iloc[-1]
                ma_l = d.close.rolling(params["long"]).mean().iloc[-1]
                pos = ctx.portfolio.get_position("X")
                if ma_s > ma_l and pos.qty == 0:
                    ctx.broker.submit(Order("X", "buy", 10))
                elif ma_s < ma_l and pos.qty > 0:
                    ctx.broker.submit(Order("X", "sell", pos.qty))
            df = _make_result().equity.to_frame("close")  # reuse
            return BacktestEngine(data={"X": {"1d": _make_df()}}, strategy=s,
                                  initial_cash=100000, cost_model=ZeroCost())

        def _make_df():
            rng = np.random.RandomState(99)
            n = 120
            dates = pd.date_range("2024-01-01", periods=n, freq="D")
            close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
            return pd.DataFrame({"open": close, "high": close * 1.01,
                                 "low": close * 0.99, "close": close,
                                 "volume": 1e6}, index=dates)

        results = grid_search(make_engine, {"short": [3, 5], "long": [10, 20]},
                              metric="sharpe")
        spec = result.chart("parameter_heatmap", grid_results=results,
                            metric="sharpe")
        assert spec.subplots[0].series[0].kind == "heatmap"


class TestMultiSubplotLayout:
    def test_two_subplots_renders(self, result, renderer):
        from stockstat.backtest.chart_spec import BacktestChartSpec
        spec = BacktestChartSpec(title="multi", layout=(2, 1), figsize=(10, 8))
        sp1 = spec.add_subplot(title="Equity", y_label="$")
        sp1.add_series(name="eq", data=result.equity, kind="line")
        sp2 = spec.add_subplot(title="Drawdown", y_label="dd")
        sp2.add_series(name="dd", data=result.drawdown, kind="fill",
                       fill_to=0.0, color="salmon", alpha=0.5)
        fig = renderer.render(spec)
        assert fig is not None
