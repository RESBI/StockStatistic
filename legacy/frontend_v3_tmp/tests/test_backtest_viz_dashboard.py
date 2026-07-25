"""BT-V3: Dashboard, trade annotations, batch savefig, graceful degradation.

Validates the combined dashboard (2x2 subplots), trade annotation markers on
the equity curve, batch render_all to a directory, and that the Null renderer
degrades gracefully without crashing.
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
from stockstat.backtest.chart_factory import get_chart_renderer
from stockstat.backtest.matplotlib_charts import MatplotlibBacktestChartRenderer
from stockstat.backtest.null_charts import NullBacktestChartRenderer
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
            ctx.broker.submit(Order("X", "buy", 10, tag="entry"))
        elif ma5 < ma20 and pos.qty > 0:
            ctx.broker.submit(Order("X", "sell", pos.qty, tag="exit"))

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


class TestDashboard:
    def test_dashboard_has_four_subplots(self, result):
        spec = result.chart("dashboard")
        assert spec.chart_type == "dashboard"
        assert spec.layout == (2, 2)
        assert spec.n_subplots == 4

    def test_dashboard_renders(self, result, renderer):
        spec = result.chart("dashboard")
        fig = renderer.render(spec)
        assert fig is not None

    def test_dashboard_savefig(self, result, renderer, tmp_path):
        spec = result.chart("dashboard")
        renderer.render(spec)
        path = str(tmp_path / "dashboard.png")
        renderer.savefig(path)
        assert os.path.exists(path)
        assert os.path.getsize(path) > 1000  # non-trivial size

    def test_dashboard_with_parameter_heatmap(self, result, renderer):
        grid = [
            ({"short": 5, "long": 20}, 1.2, result),
            ({"short": 10, "long": 30}, 0.9, result),
        ]
        spec = result.chart("dashboard", grid_results=grid)
        fig = renderer.render(spec)
        assert fig is not None

    def test_dashboard_custom_panels(self, result, renderer):
        spec = result.chart("dashboard",
                            panels=["equity", "drawdown"])
        assert spec.n_subplots == 2
        fig = renderer.render(spec)
        assert fig is not None


class TestTradeAnnotations:
    def test_trades_overlay_annotates(self, result, renderer):
        spec = result.chart("trades_overlay")
        fig = renderer.render(spec)
        # the first axes should have text annotations (B/S markers)
        ax = fig.axes[0]
        texts = [t.get_text() for t in ax.texts]
        # at least some "B" or "S" annotations
        annotations = [t for t in texts if t in ("B", "S")]
        assert len(annotations) > 0 or len(result.fills) == 0

    def test_dashboard_no_annotation_by_default(self, result, renderer):
        spec = result.chart("dashboard")
        assert spec.annotate_trades is False


class TestBatchRenderAll:
    def test_render_all_creates_files(self, result, tmp_path):
        out = result.render_all(str(tmp_path))
        assert len(out) > 0
        for name, path in out.items():
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

    def test_render_all_custom_names(self, result, tmp_path):
        out = result.render_all(str(tmp_path), names=["equity_curve", "drawdown"])
        assert set(out.keys()) == {"equity_curve", "drawdown"}

    def test_render_all_skips_unknown(self, result, tmp_path):
        out = result.render_all(str(tmp_path),
                                names=["equity_curve", "nonexistent"])
        assert "equity_curve" in out
        assert "nonexistent" not in out


class TestGracefulDegradation:
    def test_null_render_all_warns(self, result, tmp_path):
        null_r = NullBacktestChartRenderer()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            out = result.render_all(str(tmp_path), renderer=null_r)
            assert out == {}
            assert len(w) == 1
            assert "backtest_viz" in str(w[0].message)

    def test_null_render_no_crash(self, result):
        null_r = NullBacktestChartRenderer()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            fig = result.render("equity_curve", renderer=null_r)
            assert fig is None

    def test_render_skips_savefig_when_unavailable(self, result, tmp_path):
        path = str(tmp_path / "skipped.png")
        null_r = NullBacktestChartRenderer()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result.render("equity_curve", path=path, renderer=null_r)
            assert not os.path.exists(path)


class TestFullWorkflow:
    def test_end_to_end_backtest_then_visualize(self, tmp_path):
        """End-to-end: run backtest, build dashboard, save."""
        res = _make_result()
        spec = res.chart("dashboard")
        r = MatplotlibBacktestChartRenderer()
        fig = r.render(spec)
        path = str(tmp_path / "full_workflow.png")
        r.savefig(path)
        assert os.path.exists(path)

    def test_grid_search_then_heatmap(self, tmp_path):
        def _df():
            rng = np.random.RandomState(7)
            n = 120
            dates = pd.date_range("2024-01-01", periods=n, freq="D")
            close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
            return pd.DataFrame({"open": close, "high": close * 1.01,
                                 "low": close * 0.99, "close": close,
                                 "volume": 1e6}, index=dates)

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
            return BacktestEngine(data={"X": {"1d": _df()}}, strategy=s,
                                  initial_cash=100000, cost_model=ZeroCost())

        results = grid_search(make_engine,
                              {"short": [3, 5, 8], "long": [10, 20, 30]},
                              metric="sharpe")
        # build a dummy result for chart() (uses first result)
        res = results[0][2]
        spec = res.chart("parameter_heatmap", grid_results=results, metric="sharpe")
        r = MatplotlibBacktestChartRenderer()
        fig = r.render(spec)
        path = str(tmp_path / "grid_heatmap.png")
        r.savefig(path)
        assert os.path.exists(path)
