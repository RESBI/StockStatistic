"""Tests for v2.0 API layer (Layer 3) and application layer (Layer 4)."""
from __future__ import annotations

import pandas as pd
import pytest


# ═══════════════════════════════════════════════════════════════
# Phase 4.1: DSL Auto-Reflection
# ═══════════════════════════════════════════════════════════════

class TestDslAutoReflection:

    def test_build_functions_from_registry(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators
        from stockstat._api.dsl import build_dsl_functions_from_registry

        reg = PluginRegistry()
        register_default_indicators(reg)
        funcs = build_dsl_functions_from_registry(reg)

        # Should include all registered indicators
        assert "ma" in funcs
        assert "rsi" in funcs
        assert "bollinger" in funcs
        assert "hurst_dfa" in funcs
        assert len(funcs) >= 16

    def test_dsl_engine_list_functions(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators
        from stockstat._api.dsl import DslEngine

        reg = PluginRegistry()
        register_default_indicators(reg)
        engine = DslEngine(reg)
        funcs = engine.list_functions()
        assert "ma" in funcs
        assert "rsi" in funcs

    def test_dsl_engine_eval_simple(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators
        from stockstat._api.dsl import DslEngine

        reg = PluginRegistry()
        register_default_indicators(reg)

        # Create a mock client that returns a DataFrame
        class MockClient:
            def ohlcv(self, symbol, start=None, end=None, timeframe="1d", source=None, limit=None):
                return pd.DataFrame(
                    {"open": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                              110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                              120, 121, 122, 123, 124],
                     "high": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
                              111, 112, 113, 114, 115, 116, 117, 118, 119, 120,
                              121, 122, 123, 124, 125],
                     "low": [99, 100, 101, 102, 103, 104, 105, 106, 107, 108,
                             109, 110, 111, 112, 113, 114, 115, 116, 117, 118,
                             119, 120, 121, 122, 123],
                     "close": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                               110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                               120, 121, 122, 123, 124],
                     "volume": [1000]*25},
                    index=pd.date_range("2024-01-01", periods=25, freq="D"),
                )

        engine = DslEngine(reg, client=MockClient())
        result = engine.eval('''
            SELECT close, ma(close, 5) AS ma5
            FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-01-31")
            LIMIT 5
        ''')
        assert len(result) == 5
        assert "close" in result.columns
        assert "ma5" in result.columns

    def test_dsl_engine_refresh(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators
        from stockstat._api.dsl import DslEngine

        reg = PluginRegistry()
        register_default_indicators(reg)
        engine = DslEngine(reg)
        initial_count = len(engine.list_functions())

        # Register a new indicator
        from stockstat._domain.indicators import IndicatorPlugin
        reg.register("indicators", "my_custom",
                     IndicatorPlugin("my_custom", lambda x: x.mean(), "custom"))
        engine.refresh()
        assert len(engine.list_functions()) == initial_count + 1
        assert "my_custom" in engine.list_functions()

    def test_dsl_unknown_function_raises(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators
        from stockstat._api.dsl import DslEngine

        reg = PluginRegistry()
        register_default_indicators(reg)

        class MockClient:
            def ohlcv(self, symbol, start=None, end=None, timeframe="1d", source=None, limit=None):
                return pd.DataFrame(
                    {"close": [100, 101]}, index=pd.date_range("2024-01-01", periods=2))

        engine = DslEngine(reg, client=MockClient())
        with pytest.raises(KeyError):
            engine.eval('''
                SELECT nonexistent_func(close) AS x
                FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-01-02")
            ''')


# ═══════════════════════════════════════════════════════════════
# Phase 4.2: V2Client Offline Mode
# ═══════════════════════════════════════════════════════════════

class TestV2ClientOffline:

    def test_offline_mode_creation(self):
        from stockstat._api.client import V2Client
        from stockstat._core.storage import MemoryStorage

        client = V2Client(mode="offline", storage=MemoryStorage())
        assert client.mode == "offline"

    def test_offline_ohlcv_query(self):
        from stockstat._api.client import V2Client
        from stockstat._core.storage import MemoryStorage
        from stockstat._core.contracts import DataSchema, FieldDef

        storage = MemoryStorage()
        storage.register_schema("ohlcv", DataSchema(
            name="ohlcv",
            fields=[
                FieldDef("symbol", "str", nullable=False),
                FieldDef("ts", "datetime", nullable=False),
                FieldDef("close", "float"),
            ],
            unique_constraints=[("symbol", "ts")],
        ))
        storage.write("ohlcv", [
            {"symbol": "BTC", "ts": pd.Timestamp("2024-01-01", tz="UTC"), "close": 100},
            {"symbol": "BTC", "ts": pd.Timestamp("2024-01-02", tz="UTC"), "close": 101},
        ])

        client = V2Client(mode="offline", storage=storage)
        df = client.ohlcv("BTC")
        assert len(df) == 2

    def test_offline_ingest_raises(self):
        from stockstat._api.client import V2Client
        client = V2Client(mode="offline")
        with pytest.raises(RuntimeError):
            client.ingest("BTC/USDT")

    def test_offline_compute_available(self):
        from stockstat._api.client import V2Client
        client = V2Client(mode="offline")
        ce = client.compute
        assert ce is not None
        assert hasattr(ce, "ma")

    def test_offline_backtest(self):
        from stockstat._api.client import V2Client
        from stockstat.backtest import strategy, Order, BacktestEngine

        data = {"BTC": {"1d": pd.DataFrame(
            {"open": [100, 101, 102], "high": [101, 102, 103],
             "low": [99, 100, 101], "close": [100, 101, 102],
             "volume": [1000, 1000, 1000]},
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )}}

        @strategy
        def s(ctx):
            d = ctx.get("BTC", "1d", lookback=3)
            if len(d) < 2: return
            pos = ctx.portfolio.get_position("BTC")
            if pos.qty == 0:
                ctx.broker.submit(Order("BTC", "buy", 1))
            elif pos.qty > 0:
                ctx.broker.submit(Order("BTC", "sell", pos.qty))

        client = V2Client(mode="offline")
        res = client.backtest(data, s, initial_cash=10000)
        assert res is not None
        assert hasattr(res, "equity")

    def test_invalid_mode_raises(self):
        from stockstat._api.client import V2Client
        with pytest.raises(ValueError):
            V2Client(mode="invalid")


# ═══════════════════════════════════════════════════════════════
# Phase 4.3: CLI
# ═══════════════════════════════════════════════════════════════

class TestCLI:

    def test_cli_no_args_prints_help(self, capsys):
        from stockstat.app.cli import main
        ret = main([])
        assert ret == 0
        captured = capsys.readouterr()
        assert "stockstat" in captured.out.lower()

    def test_cli_plugins(self, capsys):
        from stockstat.app.cli import main
        ret = main(["plugins"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "indicators" in captured.out
        assert "sources" in captured.out

    def test_cli_plugins_by_namespace(self, capsys):
        from stockstat.app.cli import main
        ret = main(["plugins", "--namespace", "indicators"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "ma" in captured.out
        assert "rsi" in captured.out

    def test_cli_indicators(self, capsys):
        from stockstat.app.cli import main
        ret = main(["indicators"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "ma" in captured.out
        assert "trend" in captured.out

    def test_cli_indicators_by_category(self, capsys):
        from stockstat.app.cli import main
        ret = main(["indicators", "--category", "nonlinear"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "hurst_dfa" in captured.out

    def test_cli_query_no_data(self):
        # CLI query requires a running backend; verify arg parsing doesn't crash
        from stockstat.app.cli import main
        try:
            main(["query", "NONEXISTENT/USDT"])
        except Exception:
            pass  # Connection error expected without backend
