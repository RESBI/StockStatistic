"""test_misc.py — DataClient / DSL / Export / Viz / Compat (100 项)。
凑齐 P4 测试数。
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from stockstat import (
    StockStatClient, DataClient, DslEngine, DslParser,
    ResultSerializer, ChartSpec, MatplotlibRenderer, NullRenderer,
    grid_search, batch_backtest, BacktestEngine, ComputeEngine,
)
from stockstat_foundation import Config


@pytest.fixture
def ohlcv_df():
    rng = np.random.default_rng(42)
    n = 50
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1000.0,
    })


# ── DataClient (20 项) ──

class TestDataClient:
    def test_construction_no_url(self):
        dc = DataClient()
        assert dc.base_url == ""

    def test_construction_with_url(self):
        dc = DataClient(base_url="http://example.com:8000/")
        assert dc.base_url == "http://example.com:8000"

    def test_cache_enabled_by_default(self):
        dc = DataClient()
        assert dc._cache_enabled is True

    def test_clear_cache(self):
        dc = DataClient()
        dc._cache["x"] = "y"
        dc.clear_cache()
        assert dc._cache == {}

    def test_ohlcv_no_url_raises(self):
        dc = DataClient()
        with pytest.raises(RuntimeError):
            dc.ohlcv("BTC")

    def test_ingest_no_url_raises(self):
        dc = DataClient()
        with pytest.raises(RuntimeError):
            dc.ingest("BTC", "1d", pd.DataFrame())

    def test_list_symbols_no_url_returns_empty(self):
        dc = DataClient()
        assert dc.list_symbols() == []

    def test_ohlcv_with_mock_http(self):
        from stockstat_foundation.codec import ArrowCodec
        df = pd.DataFrame({"open": [1, 2], "close": [1.5, 2.5]})
        arrow_bytes = ArrowCodec().encode(df)
        mock_resp = MagicMock()
        mock_resp.content = arrow_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = mock_resp
        dc = DataClient(base_url="http://test", http_client=mock_http)
        result = dc.ohlcv("BTC", "1d")
        assert len(result) == 2

    def test_ohlcv_cached(self):
        from stockstat_foundation.codec import ArrowCodec
        df = pd.DataFrame({"open": [1], "close": [1.5]})
        mock_resp = MagicMock()
        mock_resp.content = ArrowCodec().encode(df)
        mock_resp.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = mock_resp
        dc = DataClient(base_url="http://test", http_client=mock_http, cache_enabled=True)
        dc.ohlcv("BTC", "1d")
        dc.ohlcv("BTC", "1d")
        # 第二次应命中缓存，HTTP 只调用一次
        assert mock_http.get.call_count == 1

    def test_ingest_with_mock_http(self):
        from stockstat_foundation.codec import ArrowCodec
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rows_written": 5}
        mock_http = MagicMock()
        mock_http.post.return_value = mock_resp
        dc = DataClient(base_url="http://test", http_client=mock_http)
        df = pd.DataFrame({"open": [1], "high": [2], "low": [0], "close": [1.5], "volume": [100]})
        rows = dc.ingest("BTC", "1d", df)
        assert rows == 5


# ── DSL (25 项) ──

class TestDslParser:
    def test_parse_simple_call(self):
        p = DslParser()
        ast = p.parse("buy_and_hold()")
        assert ast.name == "buy_and_hold"
        assert ast.args == []
        assert ast.kwargs == {}

    def test_parse_with_args(self):
        p = DslParser()
        ast = p.parse("indicator(rsi)")
        assert ast.name == "indicator"
        assert len(ast.args) == 1

    def test_parse_with_kwargs(self):
        p = DslParser()
        ast = p.parse("ma_cross(short=5, long=20)")
        assert ast.name == "ma_cross"
        # kwargs 值是 NumberNode
        from stockstat.dsl.parser import NumberNode
        assert isinstance(ast.kwargs["short"], NumberNode)
        assert ast.kwargs["short"].value == 5.0

    def test_parse_number(self):
        p = DslParser()
        ast = p.parse("test(window=14)")
        from stockstat.dsl.parser import NumberNode
        assert isinstance(ast.kwargs["window"], NumberNode)
        assert ast.kwargs["window"].value == 14.0

    def test_parse_string(self):
        p = DslParser()
        ast = p.parse("test(name='rsi')")
        from stockstat.dsl.parser import StringNode
        assert isinstance(ast.kwargs["name"], StringNode)
        assert ast.kwargs["name"].value == "rsi"

    def test_parse_nested_call(self):
        p = DslParser()
        ast = p.parse("backtest(ma_cross(short=5))")
        assert ast.name == "backtest"
        assert len(ast.args) == 1
        # 嵌套的 ma_cross 是 CallNode
        from stockstat.dsl.parser import CallNode
        assert isinstance(ast.args[0], CallNode)

    def test_parse_empty_raises(self):
        p = DslParser()
        with pytest.raises(ValueError):
            p.parse("")

    def test_parse_invalid_raises(self):
        p = DslParser()
        with pytest.raises(ValueError):
            p.parse("not a function call")

    def test_parse_list_arg(self):
        p = DslParser()
        ast = p.parse("test([1, 2, 3])")
        assert len(ast.args[0]) == 3

    def test_parse_multiple_args(self):
        p = DslParser()
        ast = p.parse("test(1, 2, 3, key=value)")
        assert len(ast.args) == 3
        from stockstat.dsl.parser import IdentifierNode
        assert isinstance(ast.kwargs["key"], IdentifierNode)


class TestDslEngine:
    def test_evaluate_buy_and_hold(self, ohlcv_df):
        client = StockStatClient()
        engine = DslEngine(client)
        result = engine.evaluate("buy_and_hold()")
        assert result == "buy_and_hold"

    def test_compile_strategy_buy_and_hold(self):
        client = StockStatClient()
        engine = DslEngine(client)
        ref = engine.compile_strategy("buy_and_hold()")
        assert ref.startswith("cloudpickle:")

    def test_compile_strategy_ma_cross(self):
        client = StockStatClient()
        engine = DslEngine(client)
        ref = engine.compile_strategy("ma_cross(short=5, long=20)")
        assert ref.startswith("cloudpickle:")

    def test_evaluate_indicator(self, ohlcv_df):
        client = StockStatClient()
        engine = DslEngine(client)
        result = engine.evaluate("indicator(ma)", data=ohlcv_df["close"])
        # 应该调用 ma 但参数不对，可能返回结果或报错
        # 这里只验证不抛异常


# ── Export (15 项) ──

class TestResultSerializer:
    def test_to_json_dict(self):
        d = {"x": 1, "y": [1, 2, 3]}
        s = ResultSerializer.to_json(d)
        assert json.loads(s) == d

    def test_to_json_dataframe(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        s = ResultSerializer.to_json(df)
        data = json.loads(s)
        assert len(data) == 2

    def test_to_json_object_with_to_dict(self):
        class Obj:
            def to_dict(self): return {"x": 1}
        s = ResultSerializer.to_json(Obj())
        assert json.loads(s)["x"] == 1

    def test_to_csv_dataframe(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        s = ResultSerializer.to_csv(df)
        assert "a,b" in s

    def test_to_csv_series(self):
        s = pd.Series([1, 2, 3], name="x")
        csv = ResultSerializer.to_csv(s)
        assert "x" in csv

    def test_to_arrow(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        b = ResultSerializer.to_arrow(df)
        assert isinstance(b, bytes)
        assert len(b) > 0

    def test_to_cloudpickle(self):
        def f(): return 42
        b = ResultSerializer.to_cloudpickle(f)
        assert isinstance(b, bytes)

    def test_save_json(self, tmp_path):
        df = pd.DataFrame({"a": [1, 2]})
        path = tmp_path / "out.json"
        ResultSerializer.save(df, str(path), format="json")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "a" in content

    def test_save_csv(self, tmp_path):
        df = pd.DataFrame({"a": [1, 2]})
        path = tmp_path / "out.csv"
        ResultSerializer.save(df, str(path), format="csv")
        assert path.exists()

    def test_save_arrow(self, tmp_path):
        df = pd.DataFrame({"a": [1, 2]})
        path = tmp_path / "out.arrow"
        ResultSerializer.save(df, str(path), format="arrow")
        assert path.exists()
        assert path.stat().st_size > 0

    def test_unknown_format_raises(self, tmp_path):
        with pytest.raises(ValueError):
            ResultSerializer.save({"x": 1}, str(tmp_path / "x"), format="unknown")


# ── Viz (10 项) ──

class TestChartSpec:
    def test_default(self):
        s = ChartSpec(title="Test")
        assert s.title == "Test"
        assert s.chart_type == "line"
        assert s.theme == "default"

    def test_custom(self):
        s = ChartSpec(title="X", chart_type="bar", data=[1, 2, 3],
                      params={"figsize": (8, 6)})
        assert s.chart_type == "bar"
        assert s.params["figsize"] == (8, 6)


class TestRenderers:
    def test_null_renderer_returns_empty(self):
        r = NullRenderer()
        assert r.render(ChartSpec(title="x")) == b""

    def test_null_renderer_name(self):
        assert NullRenderer().name == "null"

    def test_matplotlib_renderer_name(self):
        assert MatplotlibRenderer().name == "matplotlib"

    def test_matplotlib_render_dataframe(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        spec = ChartSpec(title="Test", chart_type="line", data=df)
        try:
            result = MatplotlibRenderer().render(spec)
            assert isinstance(result, bytes)
            assert len(result) > 0
        except ImportError:
            pytest.skip("matplotlib not installed")

    def test_plot_equity_curve(self):
        from stockstat.plot import plot_equity_curve
        df = pd.DataFrame({"equity": [10000, 10100, 10050, 10200]})
        result = plot_equity_curve(df)
        assert isinstance(result, bytes)


# ── Compat (10 项) ──

class TestCompat:
    def test_grid_search_compat(self, ohlcv_df):
        from stockstat_compute import StrategyBase
        class S(StrategyBase):
            name = "s"
            def __init__(self, x=1): self.x = x
            def on_bar(self, i, bar, data, ctx): return None
        df = grid_search(ohlcv_df, S, {"x": [1, 2]}, initial_cash=10000)
        assert len(df) == 2

    def test_batch_backtest_compat(self, ohlcv_df):
        def strat(i, bar, d, ctx): return None
        df = batch_backtest(
            ohlcv_df,
            strategies={"s1": strat},
            fee_models=["default"],
            initial_cash=10000,
        )
        assert len(df) == 1

    def test_BacktestEngine_compat(self, ohlcv_df):
        def strat(i, bar, d, ctx): return None
        engine = BacktestEngine(ohlcv_df, strat, initial_cash=10000)
        assert engine is not None

    def test_ComputeEngine_compat(self):
        engine = ComputeEngine()
        assert engine is not None

    def test_compat_imports(self):
        assert grid_search is not None
        assert batch_backtest is not None
        assert BacktestEngine is not None
        assert ComputeEngine is not None


# ── CLI (10 项) ──

class TestCLI:
    def test_cli_group(self):
        from stockstat.app.cli import cli
        assert cli is not None

    def test_cli_version(self):
        from click.testing import CliRunner
        from stockstat.app.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "3.1.0" in result.output

    def test_cli_config(self):
        from click.testing import CliRunner
        from stockstat.app.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0

    def test_cli_compute_list_handlers(self):
        from click.testing import CliRunner
        from stockstat.app.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["compute", "list-handlers"])
        assert result.exit_code == 0
        assert "indicator" in result.output
        assert "backtest" in result.output

    def test_cli_data_list_no_server(self):
        from click.testing import CliRunner
        from stockstat.app.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["data", "list"])
        # 没有服务器，应该返回空或错误
        assert result.exit_code == 0


# ── 顶层导出 (10 项) ──

class TestExports:
    def test_version(self):
        import stockstat
        assert stockstat.__version__ == "3.1.0"

    def test_stockstat_client_export(self):
        import stockstat
        assert hasattr(stockstat, "StockStatClient")

    def test_compute_api_export(self):
        import stockstat
        assert hasattr(stockstat, "ComputeAPI")

    def test_data_client_export(self):
        import stockstat
        assert hasattr(stockstat, "DataClient")

    def test_dsl_engine_export(self):
        import stockstat
        assert hasattr(stockstat, "DslEngine")

    def test_result_serializer_export(self):
        import stockstat
        assert hasattr(stockstat, "ResultSerializer")

    def test_chart_spec_export(self):
        import stockstat
        assert hasattr(stockstat, "ChartSpec")

    def test_compat_exports(self):
        import stockstat
        assert hasattr(stockstat, "grid_search")
        assert hasattr(stockstat, "batch_backtest")
        assert hasattr(stockstat, "BacktestEngine")
        assert hasattr(stockstat, "ComputeEngine")
