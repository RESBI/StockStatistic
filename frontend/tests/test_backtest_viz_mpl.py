"""BT-V1: matplotlib backend basic rendering tests.

Validates that MatplotlibBacktestChartRenderer renders equity/drawdown/trades
specs into actual matplotlib Figure objects, and that savefig produces files.
Skipped if matplotlib is not installed.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost
from stockstat.backtest.chart_factory import get_chart_renderer, detect
from stockstat.backtest.matplotlib_charts import MatplotlibBacktestChartRenderer

mpl = pytest.importorskip("matplotlib")
mpl.use("Agg")


def _make_result(n=150, seed=0, benchmark=True):
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
                         benchmark="X" if benchmark else None)
    return eng.run()


@pytest.fixture
def result():
    return _make_result()


@pytest.fixture
def renderer():
    return MatplotlibBacktestChartRenderer()


class TestRendererAvailability:
    def test_available_true(self, renderer):
        assert renderer.available() is True

    def test_detect_matplotlib(self):
        assert detect() == "matplotlib"

    def test_factory_returns_mpl(self):
        r = get_chart_renderer("matplotlib")
        assert isinstance(r, MatplotlibBacktestChartRenderer)


class TestEquityCurve:
    def test_renders_figure(self, result, renderer):
        spec = result.chart("equity_curve")
        fig = renderer.render(spec)
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_has_two_series_with_benchmark(self, result, renderer):
        spec = result.chart("equity_curve")
        assert len(spec.subplots[0].series) == 2  # strategy + benchmark

    def test_savefig_creates_file(self, result, renderer, tmp_path):
        spec = result.chart("equity_curve")
        renderer.render(spec)
        path = str(tmp_path / "equity.png")
        renderer.savefig(path)
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0


class TestDrawdown:
    def test_renders_with_fill(self, result, renderer):
        spec = result.chart("drawdown")
        fig = renderer.render(spec)
        assert fig is not None
        # the spec must contain a fill series
        kinds = [s.kind for s in spec.subplots[0].series]
        assert "fill" in kinds

    def test_savefig(self, result, renderer, tmp_path):
        spec = result.chart("drawdown")
        renderer.render(spec)
        path = str(tmp_path / "drawdown.png")
        renderer.savefig(path)
        assert os.path.exists(path)


class TestTradesOverlay:
    def test_renders_with_annotations(self, result, renderer):
        spec = result.chart("trades_overlay")
        fig = renderer.render(spec)
        assert fig is not None
        assert spec.annotate_trades is True

    def test_savefig(self, result, renderer, tmp_path):
        spec = result.chart("trades_overlay")
        renderer.render(spec)
        path = str(tmp_path / "trades.png")
        renderer.savefig(path)
        assert os.path.exists(path)


class TestRenderViaResult:
    def test_result_render_one_liner(self, result, tmp_path):
        path = str(tmp_path / "one.png")
        fig = result.render("equity_curve", path=path)
        assert fig is not None
        assert os.path.exists(path)

    def test_result_render_no_path(self, result):
        fig = result.render("drawdown")
        assert fig is not None

    def test_result_render_custom_renderer(self, result, tmp_path):
        r = MatplotlibBacktestChartRenderer()
        path = str(tmp_path / "custom.png")
        fig = result.render("trades_overlay", path=path, renderer=r)
        assert fig is not None
        assert os.path.exists(path)


class TestNoBenchmark:
    def test_equity_without_benchmark(self, renderer):
        res = _make_result(benchmark=False)
        spec = res.chart("equity_curve")
        # only one series (strategy, no benchmark)
        assert len(spec.subplots[0].series) == 1
        fig = renderer.render(spec)
        assert fig is not None


class TestEmptyResult:
    def test_renders_without_fills(self, renderer):
        # strategy that never trades
        rng = np.random.RandomState(1)
        n = 50
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = 100 + rng.normal(0, 1, n).cumsum()
        df = pd.DataFrame({"open": close, "high": close, "low": close,
                           "close": close, "volume": 1e6}, index=dates)

        @strategy
        def noop(ctx):
            pass

        eng = BacktestEngine(data={"X": {"1d": df}}, strategy=noop,
                             initial_cash=100000, cost_model=ZeroCost())
        res = eng.run()
        spec = res.chart("equity_curve")
        fig = renderer.render(spec)
        assert fig is not None


class TestUnderwaterCurve:
    def test_renders(self, result, renderer, tmp_path):
        spec = result.chart("underwater_curve")
        fig = renderer.render(spec)
        assert fig is not None
        path = str(tmp_path / "underwater.png")
        renderer.savefig(path)
        assert os.path.exists(path)
