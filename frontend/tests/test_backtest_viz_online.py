"""Online backtest visualization tests with real market data.

Uses Yahoo Finance + Binance via proxy to fetch real OHLCV, run backtests,
and render visualization charts. Generates PNGs to docs/images/ for README.
Requires proxy enabled at http://127.0.0.1:8889.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

os.environ["STOCKSTAT_PROXY_ENABLED"] = "true"
os.environ["STOCKSTAT_PROXY_TYPE"] = "http"
os.environ["STOCKSTAT_PROXY_URL"] = "http://127.0.0.1:8889"
os.environ["DATABASE_URL"] = "sqlite:///test_backtest_viz_online.db"

import matplotlib
matplotlib.use("Agg")

from fastapi.testclient import TestClient
from stockstat_backend.app import create_app
from stockstat_backend.storage.database import reset_engine, get_engine
from stockstat_backend.models.ohlcv import Base
from stockstat_backend.config import settings
from stockstat import StockStatClient
from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost, PercentCost
from stockstat.backtest.optimizer import grid_search
from stockstat.backtest.matplotlib_charts import MatplotlibBacktestChartRenderer

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


@pytest.fixture(scope="module")
def test_http_client():
    settings.reload()
    reset_engine()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app = create_app()
    with TestClient(app) as c:
        symbols = [
            ("BTC/USDT", "binance", "2023-01-01", "2024-12-31", "1d"),
            ("BTC/USDT", "binance", "2024-01-01", "2024-12-31", "1h"),
            ("ETH/USDT", "binance", "2023-01-01", "2024-12-31", "1d"),
            ("AAPL", "yfinance", "2023-01-01", "2024-12-31", "1d"),
            ("^GSPC", "yfinance", "2023-01-01", "2024-12-31", "1d"),
        ]
        for sym, source, start, end, tf in symbols:
            c.post("/api/v1/ingest", params={
                "symbol": sym, "source": source,
                "start": start, "end": end, "timeframe": tf,
            })
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="module")
def client(test_http_client):
    return StockStatClient(http_client=test_http_client)


# ── Online backtest + visualization with real BTC data ──

class TestBTCDoubleMAViz:
    """Run MA crossover on real BTC data and render all chart types."""

    @pytest.fixture(scope="class")
    def btc_result(self, client):
        df = client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")

        @strategy
        def ma_cross(ctx):
            d = ctx.get("BTC/USDT", "1d", lookback=30)
            if len(d) < 21:
                return
            ma5 = d.close.rolling(5).mean().iloc[-1]
            ma20 = d.close.rolling(20).mean().iloc[-1]
            pos = ctx.portfolio.get_position("BTC/USDT")
            if ma5 > ma20 and pos.qty == 0:
                ctx.broker.submit(Order("BTC/USDT", "buy", 0.5, tag="entry"))
            elif ma5 < ma20 and pos.qty > 0:
                ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty, tag="exit"))

        eng = BacktestEngine(
            data={"BTC/USDT": {"1d": df}},
            strategy=ma_cross,
            initial_cash=50000,
            cost_model=PercentCost(commission=0.0002, slippage=0.0003),
            benchmark="BTC/USDT",
        )
        return eng.run()

    def test_backtest_ran_with_real_data(self, btc_result):
        assert len(btc_result.equity) > 400  # ~2 years of daily bars
        assert btc_result.equity.iloc[0] == pytest.approx(50000, rel=1e-6)
        assert len(btc_result.fills) > 0
        m = btc_result.metrics()
        assert -1.0 < m["total_return"] < 10.0
        assert m["max_drawdown"] <= 0

    def test_equity_curve_png(self, btc_result):
        path = os.path.join(IMAGES_DIR, "backtest_btc_equity.png")
        btc_result.render("equity_curve", path=path)
        assert os.path.exists(path)
        assert os.path.getsize(path) > 5000

    def test_drawdown_png(self, btc_result):
        path = os.path.join(IMAGES_DIR, "backtest_btc_drawdown.png")
        btc_result.render("drawdown", path=path)
        assert os.path.exists(path)

    def test_trades_overlay_png(self, btc_result):
        path = os.path.join(IMAGES_DIR, "backtest_btc_trades.png")
        btc_result.render("trades_overlay", path=path)
        assert os.path.exists(path)

    def test_returns_distribution_png(self, btc_result):
        path = os.path.join(IMAGES_DIR, "backtest_btc_returns_dist.png")
        btc_result.render("returns_distribution", path=path, bins=40)
        assert os.path.exists(path)

    def test_monthly_heatmap_png(self, btc_result):
        path = os.path.join(IMAGES_DIR, "backtest_btc_monthly_heatmap.png")
        btc_result.render("monthly_heatmap", path=path)
        assert os.path.exists(path)

    def test_yearly_returns_png(self, btc_result):
        path = os.path.join(IMAGES_DIR, "backtest_btc_yearly.png")
        btc_result.render("yearly_returns", path=path)
        assert os.path.exists(path)

    def test_underwater_png(self, btc_result):
        path = os.path.join(IMAGES_DIR, "backtest_btc_underwater.png")
        btc_result.render("underwater_curve", path=path)
        assert os.path.exists(path)

    def test_dashboard_png(self, btc_result):
        path = os.path.join(IMAGES_DIR, "backtest_btc_dashboard.png")
        btc_result.render("dashboard", path=path)
        assert os.path.exists(path)
        assert os.path.getsize(path) > 10000

    def test_render_all_to_dir(self, btc_result, tmp_path):
        out = btc_result.render_all(str(tmp_path))
        assert len(out) >= 7
        for name, p in out.items():
            assert os.path.exists(p)


# ── Pair trading on real BTC/ETH data with visualization ──

class TestPairTradingViz:
    @pytest.fixture(scope="class")
    def pair_result(self, client):
        btc = client.ohlcv("BTC/USDT", start="2023-01-01", timeframe="1d")
        eth = client.ohlcv("ETH/USDT", start="2023-01-01", timeframe="1d")
        data = {"BTC/USDT": {"1d": btc}, "ETH/USDT": {"1d": eth}}

        @strategy
        def pair(ctx):
            b = ctx.get("BTC/USDT", "1d", lookback=60)
            e = ctx.get("ETH/USDT", "1d", lookback=60)
            if len(b) < 40:
                return
            spread = np.log(b.close) - np.log(e.close)
            z = (spread - spread.rolling(20).mean()) / spread.rolling(20).std()
            last = z.iloc[-1]
            if np.isnan(last):
                return
            pb = ctx.portfolio.get_position("BTC/USDT")
            pe = ctx.portfolio.get_position("ETH/USDT")
            if last > 1.5 and pb.qty == 0:
                ctx.broker.submit(Order("BTC/USDT", "sell", 0.3))
                ctx.broker.submit(Order("ETH/USDT", "buy", 3.0))
            elif last < -1.5 and pb.qty == 0:
                ctx.broker.submit(Order("BTC/USDT", "buy", 0.3))
                ctx.broker.submit(Order("ETH/USDT", "sell", 3.0))
            elif abs(last) < 0.3 and pb.qty != 0:
                if pb.qty > 0:
                    ctx.broker.submit(Order("BTC/USDT", "sell", abs(pb.qty)))
                else:
                    ctx.broker.submit(Order("BTC/USDT", "buy", abs(pb.qty)))
                if pe.qty > 0:
                    ctx.broker.submit(Order("ETH/USDT", "sell", abs(pe.qty)))
                else:
                    ctx.broker.submit(Order("ETH/USDT", "buy", abs(pe.qty)))

        eng = BacktestEngine(
            data=data, strategy=pair, initial_cash=50000,
            allow_short=True, cost_model=ZeroCost(),
        )
        return eng.run()

    def test_pair_backtest_ran(self, pair_result):
        assert len(pair_result.equity) > 400
        assert len(pair_result.fills) > 0

    def test_pair_equity_png(self, pair_result):
        path = os.path.join(IMAGES_DIR, "backtest_pair_equity.png")
        pair_result.render("equity_curve", path=path)
        assert os.path.exists(path)

    def test_pair_dashboard_png(self, pair_result):
        path = os.path.join(IMAGES_DIR, "backtest_pair_dashboard.png")
        pair_result.render("dashboard", path=path)
        assert os.path.exists(path)


# ── Parameter grid search + heatmap on real AAPL data ──

class TestParameterHeatmapViz:
    @pytest.fixture(scope="class")
    def grid_results(self, client):
        df = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")

        def make_engine(params):
            @strategy
            def s(ctx):
                d = ctx.get("AAPL", "1d", lookback=params["long"] + 5)
                if len(d) < params["long"] + 1:
                    return
                ma_s = d.close.rolling(params["short"]).mean().iloc[-1]
                ma_l = d.close.rolling(params["long"]).mean().iloc[-1]
                pos = ctx.portfolio.get_position("AAPL")
                if ma_s > ma_l and pos.qty == 0:
                    ctx.broker.submit(Order("AAPL", "buy", 50))
                elif ma_s < ma_l and pos.qty > 0:
                    ctx.broker.submit(Order("AAPL", "sell", pos.qty))
            return BacktestEngine(
                data={"AAPL": {"1d": df}}, strategy=s,
                initial_cash=100000, cost_model=ZeroCost(),
                benchmark="AAPL",
            )

        return grid_search(make_engine,
                           {"short": [5, 10, 15, 20], "long": [20, 30, 40, 50, 60]},
                           metric="sharpe")

    def test_grid_search_ran(self, grid_results):
        assert len(grid_results) == 20  # 4 x 5
        # best result has a valid sharpe
        _, best_val, _ = grid_results[0]
        assert isinstance(best_val, float)

    def test_parameter_heatmap_png(self, grid_results, client):
        df = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")
        # use a dummy result for the chart() call
        @strategy
        def noop(ctx):
            pass
        res = BacktestEngine(data={"AAPL": {"1d": df}}, strategy=noop,
                             initial_cash=100000, cost_model=ZeroCost()).run()
        path = os.path.join(IMAGES_DIR, "backtest_param_heatmap.png")
        res.render("parameter_heatmap", grid_results=grid_results,
                   metric="sharpe", path=path)
        assert os.path.exists(path)
        assert os.path.getsize(path) > 3000

    def test_dashboard_with_param_heatmap(self, grid_results, client):
        df = client.ohlcv("AAPL", start="2023-01-01", timeframe="1d")

        @strategy
        def s(ctx):
            d = ctx.get("AAPL", "1d", lookback=65)
            if len(d) < 61:
                return
            ma_s = d.close.rolling(10).mean().iloc[-1]
            ma_l = d.close.rolling(50).mean().iloc[-1]
            pos = ctx.portfolio.get_position("AAPL")
            if ma_s > ma_l and pos.qty == 0:
                ctx.broker.submit(Order("AAPL", "buy", 50))
            elif ma_s < ma_l and pos.qty > 0:
                ctx.broker.submit(Order("AAPL", "sell", pos.qty))

        res = BacktestEngine(data={"AAPL": {"1d": df}}, strategy=s,
                             initial_cash=100000, cost_model=ZeroCost(),
                             benchmark="AAPL").run()
        path = os.path.join(IMAGES_DIR, "backtest_aapl_dashboard_params.png")
        res.render("dashboard", grid_results=grid_results, path=path)
        assert os.path.exists(path)


# ── Multi-timeframe backtest with real BTC hourly + daily ──

class TestMultiTFViz:
    def test_multitf_backtest_and_dashboard(self, client):
        hourly = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1h")
        daily = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
        data = {"BTC/USDT": {"1h": hourly, "1d": daily}}

        @strategy
        def multi_tf(ctx):
            h = ctx.get("BTC/USDT", "1h", lookback=50)
            d = ctx.get("BTC/USDT", "1d", lookback=30)
            if len(d) < 21 or len(h) < 2:
                return
            trend_up = d.close.iloc[-1] > d.close.rolling(20).mean().iloc[-1]
            breakout = h.close.iloc[-1] > h.close.iloc[-2]
            pos = ctx.portfolio.get_position("BTC/USDT")
            if trend_up and breakout and pos.qty == 0:
                ctx.broker.submit(Order("BTC/USDT", "buy", 0.2))
            elif not trend_up and pos.qty > 0:
                ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

        eng = BacktestEngine(data=data, strategy=multi_tf,
                             initial_cash=50000, cost_model=ZeroCost())
        res = eng.run()
        assert len(res.equity) > 1000  # hourly bars

        path = os.path.join(IMAGES_DIR, "backtest_multitf_dashboard.png")
        res.render("dashboard", path=path)
        assert os.path.exists(path)
