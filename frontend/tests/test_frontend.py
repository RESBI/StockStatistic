"""
Frontend tests: indicators, DSL, and integration with backend.
Requires the backend to be running (or uses TestClient).
"""
import os
import sys

import pytest
import pandas as pd
import numpy as np

# Ensure both frontend and backend are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

os.environ["DATABASE_URL"] = "sqlite:///test_frontend.db"

from stockstat import StockStatClient
from stockstat.indicators import trend, oscillator, volatility, statistics
from stockstat.plot.base import PlotSpec, get_renderer, NullRenderer, RendererFactory


# ── Synthetic test data ──
def make_test_data(n=250, seed=42):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.uniform(1e6, 5e7, n)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": volume
    }, index=dates)


@pytest.fixture
def data():
    return make_test_data()


# ═══════════════════════════════════════════════════
# P1: Indicator tests (pure computation, no backend)
# ═══════════════════════════════════════════════════

class TestTrendIndicators:
    def test_ma(self, data):
        result = trend.ma(data.close, window=20)
        assert len(result) == len(data)
        assert result.isna().sum() == 19
        assert not result.dropna().empty

    def test_ema(self, data):
        result = trend.ema(data.close, window=12)
        assert len(result) == len(data)
        assert result.isna().sum() == 0  # EMA has no NaN

    def test_macd(self, data):
        macd_line, signal_line, hist = trend.macd(data.close)
        assert len(macd_line) == len(data)
        assert len(signal_line) == len(data)
        assert len(hist) == len(data)

    def test_ma_values_reasonable(self, data):
        ma20 = trend.ma(data.close, window=20)
        # MA should be close to the mean of the last 20 values
        expected = data.close.iloc[:20].mean()
        assert abs(ma20.iloc[19] - expected) < 0.01


class TestOscillatorIndicators:
    def test_rsi_range(self, data):
        result = oscillator.rsi(data.close, window=14)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_nan_count(self, data):
        result = oscillator.rsi(data.close, window=14)
        # RSI uses ewm with min_periods, first 14 should be NaN
        assert result.isna().sum() >= 13

    def test_kdj(self, data):
        k, d, j = oscillator.kdj(data.high, data.low, data.close)
        assert len(k) == len(data)
        assert len(d) == len(data)
        assert len(j) == len(data)


class TestVolatilityIndicators:
    def test_std(self, data):
        result = volatility.std(data.close, window=20)
        assert result.isna().sum() == 19
        assert (result.dropna() >= 0).all()

    def test_atr(self, data):
        result = volatility.atr(data.high, data.low, data.close, window=14)
        assert len(result) == len(data)
        assert (result.dropna() >= 0).all()

    def test_bollinger_ordering(self, data):
        upper, mid, lower = volatility.bollinger(data.close, window=20, k=2.0)
        valid_idx = upper.dropna().index
        assert (upper.loc[valid_idx] >= mid.loc[valid_idx]).all()
        assert (mid.loc[valid_idx] >= lower.loc[valid_idx]).all()


class TestStatisticsIndicators:
    def test_corr(self, data):
        x = statistics.returns(data.close)
        y = statistics.returns(data.close.shift(-1))
        c = statistics.corr(x, y)
        assert -1.0 <= c <= 1.0

    def test_beta(self, data):
        asset_ret = statistics.returns(data.close)
        bench_ret = statistics.returns(data.close + np.random.RandomState(1).normal(0, 0.01, len(data)))
        b = statistics.beta(asset_ret, bench_ret, window=60)
        valid = b.dropna()
        assert len(valid) > 0

    def test_sharpe(self, data):
        rets = statistics.returns(data.close).dropna()
        s = statistics.sharpe(rets, risk_free=0.02, annualize=True)
        assert isinstance(s, float)
        assert -10 < s < 10

    def test_max_drawdown(self, data):
        dd = statistics.max_drawdown(data.close)
        assert dd <= 0
        assert dd >= -1

    def test_var(self, data):
        rets = statistics.returns(data.close).dropna()
        v = statistics.var_historical(rets, confidence=0.95)
        assert isinstance(v, float)

    def test_returns(self, data):
        r = statistics.returns(data.close)
        assert r.isna().sum() == 1  # first value is NaN

    def test_log_returns(self, data):
        lr = statistics.log_returns(data.close)
        assert lr.isna().sum() == 1


# ═══════════════════════════════════════════════════
# P2: DSL tests
# ═══════════════════════════════════════════════════

class TestDSL:
    def test_parse_simple(self):
        from stockstat.dsl.parser import parse
        q = parse('SELECT close FROM ohlcv("AAPL", "1d")')
        assert q.source.symbol == "AAPL"
        assert q.source.timeframe == "1d"
        assert len(q.select_list) == 1

    def test_parse_with_dates(self):
        from stockstat.dsl.parser import parse
        q = parse('SELECT close, ma(close, 20) AS ma20 FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")')
        assert q.source.symbol == "BTC/USDT"
        assert q.source.start == "2024-01-01"
        assert q.source.end == "2024-12-31"
        assert len(q.select_list) == 2
        assert q.select_list[1].alias == "ma20"

    def test_parse_with_limit(self):
        from stockstat.dsl.parser import parse
        q = parse('SELECT close FROM ohlcv("AAPL", "1d") LIMIT 10')
        assert q.limit == 10

    def test_parse_with_where(self):
        from stockstat.dsl.parser import parse
        q = parse('SELECT close FROM ohlcv("AAPL", "1d") WHERE close > 150')
        assert q.condition is not None

    def test_evaluator_with_mock_data(self, data):
        from stockstat.dsl.evaluator import Evaluator

        class MockClient:
            def ohlcv(self, symbol, **kwargs):
                return data

        evaluator = Evaluator(client=MockClient())
        result = evaluator.eval('SELECT close, ma(close, 20) AS ma20 FROM ohlcv("TEST", "1d")')
        assert "close" in result.columns
        assert "ma20" in result.columns
        assert len(result) == len(data)

    def test_evaluator_rsi(self, data):
        from stockstat.dsl.evaluator import Evaluator

        class MockClient:
            def ohlcv(self, symbol, **kwargs):
                return data

        evaluator = Evaluator(client=MockClient())
        result = evaluator.eval('SELECT rsi(close, 14) AS rsi_val FROM ohlcv("TEST", "1d")')
        assert "rsi_val" in result.columns
        valid = result["rsi_val"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_evaluator_returns(self, data):
        from stockstat.dsl.evaluator import Evaluator

        class MockClient:
            def ohlcv(self, symbol, **kwargs):
                return data

        evaluator = Evaluator(client=MockClient())
        result = evaluator.eval('SELECT returns(close) AS ret FROM ohlcv("TEST", "1d")')
        assert "ret" in result.columns
        assert result["ret"].isna().sum() == 1


# ═══════════════════════════════════════════════════
# P4: Visualization tests
# ═══════════════════════════════════════════════════

class TestVisualization:
    def test_plot_spec_creation(self, data):
        spec = PlotSpec(title="Test")
        spec.add_series(name="close", data=data.close, kind="line")
        spec.add_series(name="ma20", data=data.close.rolling(20).mean(), kind="line")
        assert len(spec.series) == 2
        assert spec.title == "Test"

    def test_plot_spec_to_dict(self, data):
        spec = PlotSpec(title="Test")
        spec.add_series(name="close", data=data.close)
        d = spec.to_dict()
        assert d["title"] == "Test"
        assert len(d["series"]) == 1
        assert d["series"][0]["name"] == "close"

    def test_null_renderer(self):
        renderer = NullRenderer()
        assert renderer.available() == False
        spec = PlotSpec(title="Test")
        result = renderer.render(spec)  # should not raise
        assert result is None

    def test_renderer_detection(self):
        name = RendererFactory.detect()
        assert name in ("matplotlib", "plotly", "null")

    def test_matplotlib_renderer(self, data):
        renderer = get_renderer("matplotlib")
        if not renderer.available():
            pytest.skip("matplotlib not available")
        spec = PlotSpec(title="Close Price", x_label="Date", y_label="Price")
        spec.add_series(name="close", data=data.close, kind="line")
        spec.add_series(name="ma20", data=data.close.rolling(20).mean(), kind="line", color="red")
        fig = renderer.render(spec)
        assert fig is not None

    def test_matplotlib_savefig(self, data, tmp_path):
        renderer = get_renderer("matplotlib")
        if not renderer.available():
            pytest.skip("matplotlib not available")
        spec = PlotSpec(title="Test Save")
        spec.add_series(name="close", data=data.close)
        renderer.render(spec)
        path = str(tmp_path / "test_plot.png")
        renderer.savefig(path)
        assert os.path.exists(path)

    def test_client_plot_api(self, data):
        client = StockStatClient.__new__(StockStatClient)
        from stockstat.client import PlotAPI
        client._plot = PlotAPI()
        spec = client.plot.spec(
            title="Test",
            series=[{"name": "close", "data": data.close, "kind": "line"}],
        )
        assert spec.title == "Test"
        assert len(spec.series) == 1
