"""Tests for v2.0 domain layer (Layer 1)."""
from __future__ import annotations

import pandas as pd
import pytest


# ═══════════════════════════════════════════════════════════════
# Phase 2.1: Domain Models
# ═══════════════════════════════════════════════════════════════

class TestDomainModels:

    def test_ohlcv_creation(self):
        from stockstat._domain.models import OHLCV
        bar = OHLCV(
            symbol="BTC/USDT", ts=pd.Timestamp("2024-01-01", tz="UTC"),
            open=100, high=105, low=95, close=102, volume=1000,
            source="binance", timeframe="1d",
        )
        assert bar.symbol == "BTC/USDT"
        assert bar.close == 102
        d = bar.to_dict()
        assert d["symbol"] == "BTC/USDT"
        assert d["close"] == 102

    def test_symbol_creation(self):
        from stockstat._domain.models import Symbol
        s = Symbol(unified_symbol="BTC/USDT", asset_type="crypto",
                   base_asset="BTC", quote_asset="USDT")
        assert s.base_asset == "BTC"
        assert s.sources == []
        d = s.to_dict()
        assert d["unified_symbol"] == "BTC/USDT"

    def test_quote_mid_auto(self):
        from stockstat._domain.models import Quote
        q = Quote(symbol="BTC", ts=pd.Timestamp("2024-01-01", tz="UTC"),
                  bid=100, ask=102)
        assert q.mid == 101.0

    def test_trade(self):
        from stockstat._domain.models import Trade
        t = Trade(symbol="BTC", ts=pd.Timestamp("2024-01-01", tz="UTC"),
                  price=100, qty=0.5, side="buy")
        assert t.side == "buy"

    def test_df_to_ohlcv_list_roundtrip(self):
        from stockstat._domain.models import df_to_ohlcv_list, ohlcv_list_to_df
        df = pd.DataFrame(
            {"open": [100, 101], "high": [105, 106], "low": [95, 96],
             "close": [102, 103], "volume": [1000, 1100]},
            index=pd.date_range("2024-01-01", periods=2, freq="D", tz="UTC"),
        )
        records = df_to_ohlcv_list(df, "BTC/USDT", "binance", "1d")
        assert len(records) == 2
        assert records[0].symbol == "BTC/USDT"
        df2 = ohlcv_list_to_df(records)
        assert len(df2) == 2
        assert list(df2.columns) == ["open", "high", "low", "close", "volume"]


# ═══════════════════════════════════════════════════════════════
# Phase 2.2: Source Plugins
# ═══════════════════════════════════════════════════════════════

class TestSourcePlugins:

    def test_data_source_plugin_wrapper(self):
        from stockstat._domain.sources import DataSourcePlugin

        class FakeAdapter:
            def fetch_ohlcv(self, symbol, start=None, end=None, timeframe="1d"):
                return pd.DataFrame({"close": [100]}, index=pd.date_range("2024-01-01", periods=1))
            def fetch_symbols(self): return [{"symbol": "BTC"}]
            def supports(self, symbol): return True
            def health_check(self): return True

        plugin = DataSourcePlugin("fake", FakeAdapter(), "Fake source")
        assert plugin.name == "fake"
        assert plugin.health_check() is True
        assert plugin.supports("BTC") is True
        df = plugin.fetch_ohlcv("BTC")
        assert len(df) == 1

    def test_register_default_sources(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.sources import register_default_sources, list_sources

        reg = PluginRegistry()
        register_default_sources(reg)
        sources = list_sources(reg)
        names = {s["name"] for s in sources}
        # At least synthetic should be available
        assert "synthetic" in names

    def test_get_source(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.sources import register_default_sources, get_source

        reg = PluginRegistry()
        register_default_sources(reg)
        synth = get_source(reg, "synthetic")
        assert synth is not None
        assert synth.name == "synthetic"

        # Synthetic adapter supports everything
        assert synth.supports("BTC/USDT") is True
        df = synth.fetch_ohlcv("BTC/USDT", start="2024-01-01", end="2024-01-05")
        assert len(df) > 0


# ═══════════════════════════════════════════════════════════════
# Phase 2.3: Indicator Plugins
# ═══════════════════════════════════════════════════════════════

class TestIndicatorPlugins:

    def test_indicator_plugin_wrapper(self):
        from stockstat._domain.indicators import IndicatorPlugin

        def my_func(x, window=10):
            return x.rolling(window).mean()

        plugin = IndicatorPlugin("my_ma", my_func, "trend")
        assert plugin.name == "my_ma"
        assert plugin.category == "trend"
        assert plugin.health_check() is True

        import pandas as pd
        result = plugin.compute(x=pd.Series([1, 2, 3, 4, 5]), window=2)
        assert len(result) == 5

    def test_register_default_indicators(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators, list_indicators

        reg = PluginRegistry()
        count = register_default_indicators(reg)
        assert count >= 16  # 7 trend/osc/vol + 7 stat + 8 nonlinear = 22, but at least 16

        all_inds = list_indicators(reg)
        names = {i["name"] for i in all_inds}
        assert "ma" in names
        assert "rsi" in names
        assert "bollinger" in names
        assert "hurst_dfa" in names

    def test_indicator_categories(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators, list_indicators

        reg = PluginRegistry()
        register_default_indicators(reg)

        trend = list_indicators(reg, category="trend")
        assert len(trend) == 3  # ma, ema, macd

        osc = list_indicators(reg, category="oscillator")
        assert len(osc) == 2  # rsi, kdj

        nonlinear = list_indicators(reg, category="nonlinear")
        assert len(nonlinear) == 8

    def test_get_indicator_and_compute(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators, get_indicator

        reg = PluginRegistry()
        register_default_indicators(reg)

        ma_plugin = get_indicator(reg, "ma")
        assert ma_plugin is not None

        data = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        result = ma_plugin.compute(data=data, window=3)
        assert result.iloc[-1] == 9.0  # mean of [8, 9, 10]

    def test_nonlinear_indicator_via_registry(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.indicators import register_default_indicators, get_indicator
        import numpy as np

        reg = PluginRegistry()
        register_default_indicators(reg)

        hurst_plugin = get_indicator(reg, "hurst_dfa")
        assert hurst_plugin is not None

        # White noise Hurst ≈ 0.5
        rng = np.random.RandomState(42)
        signal = rng.randn(500)  # proper white noise
        h = hurst_plugin.compute(signal=signal)
        assert 0.3 < h < 0.7


# ═══════════════════════════════════════════════════════════════
# Phase 2.4: Backtest Component Plugins
# ═══════════════════════════════════════════════════════════════

class TestBacktestPlugins:

    def test_register_default_backtest_components(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.backtest import register_default_backtest_components

        reg = PluginRegistry()
        count = register_default_backtest_components(reg)
        assert count == 17  # 8 cost + 7 fill + 2 execution

    def test_cost_models_registered(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.backtest import register_default_backtest_components, get_cost_model

        reg = PluginRegistry()
        register_default_backtest_components(reg)

        for name in ["percent", "fixed", "zero", "maker_taker", "binance"]:
            plugin = get_cost_model(reg, name)
            assert plugin is not None
            assert plugin.component_type == "cost"

    def test_fill_models_registered(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.backtest import register_default_backtest_components, get_fill_model

        reg = PluginRegistry()
        register_default_backtest_components(reg)

        for name in ["next_open", "vwap", "intrabar_limit", "intrabar"]:
            plugin = get_fill_model(reg, name)
            assert plugin is not None
            assert plugin.component_type == "fill"

    def test_execution_models_registered(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.backtest import register_default_backtest_components, get_execution_model

        reg = PluginRegistry()
        register_default_backtest_components(reg)

        for name in ["next_bar", "intrabar"]:
            plugin = get_execution_model(reg, name)
            assert plugin is not None
            assert plugin.component_type == "execution"

    def test_create_cost_model_instance(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.backtest import register_default_backtest_components, get_cost_model

        reg = PluginRegistry()
        register_default_backtest_components(reg)

        plugin = get_cost_model(reg, "zero")
        instance = plugin.create()
        assert instance is not None


# ═══════════════════════════════════════════════════════════════
# Phase 2.5: Scheduler
# ═══════════════════════════════════════════════════════════════

class TestScheduler:

    def test_trigger_now(self):
        from stockstat._domain.scheduler import Scheduler

        calls = []
        def fake_ingest(**kwargs):
            calls.append(kwargs)
            return {"ingested": 1}

        sched = Scheduler(ingest_func=fake_ingest)
        result = sched.trigger_now("BTC/USDT", source="binance")
        assert result == {"ingested": 1}
        assert len(calls) == 1
        assert calls[0]["symbol"] == "BTC/USDT"

    def test_trigger_without_func_raises(self):
        from stockstat._domain.scheduler import Scheduler
        sched = Scheduler()
        with pytest.raises(RuntimeError):
            sched.trigger_now("BTC/USDT")

    def test_schedule_cron(self):
        from stockstat._domain.scheduler import Scheduler
        sched = Scheduler()
        sid = sched.schedule_cron("BTC/USDT", "0 * * * *", source="binance")
        assert sid == 0
        schedules = sched.list_schedules()
        assert len(schedules) == 1
        assert schedules[0]["type"] == "cron"
        assert schedules[0]["cron"] == "0 * * * *"

    def test_schedule_incremental(self):
        from stockstat._domain.scheduler import Scheduler
        sched = Scheduler()
        sid = sched.schedule_incremental("BTC/USDT", interval_hours=6)
        assert sid == 0
        schedules = sched.list_schedules()
        assert schedules[0]["type"] == "incremental"
        assert schedules[0]["interval_hours"] == 6

    def test_cancel_schedule(self):
        from stockstat._domain.scheduler import Scheduler
        sched = Scheduler()
        sid = sched.schedule_cron("BTC/USDT", "0 * * * *")
        assert sched.cancel(sid) is True
        assert len(sched.list_schedules()) == 0
        assert sched.cancel(999) is False

    def test_start_stop(self):
        from stockstat._domain.scheduler import Scheduler
        sched = Scheduler()
        assert not sched.is_running
        sched.start()
        assert sched.is_running
        sched.stop()
        assert not sched.is_running

    def test_health_check(self):
        from stockstat._domain.scheduler import Scheduler
        sched = Scheduler()
        assert sched.health_check() is True


# ═══════════════════════════════════════════════════════════════
# Phase 2.6: Full registry bootstrap
# ═══════════════════════════════════════════════════════════════

class TestFullBootstrap:

    def test_bootstrap_all_namespaces(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.sources import register_default_sources
        from stockstat._domain.indicators import register_default_indicators
        from stockstat._domain.backtest import register_default_backtest_components

        reg = PluginRegistry()
        register_default_sources(reg)
        register_default_indicators(reg)
        register_default_backtest_components(reg)

        ns = set(reg.namespaces())
        assert "sources" in ns
        assert "indicators" in ns
        assert "cost_models" in ns
        assert "fill_models" in ns
        assert "execution_models" in ns

        # Total plugin count
        total = len(reg.list())
        assert total >= 40  # 4 sources + 22 indicators + 17 backtest = 43

    def test_registry_health_check(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._domain.sources import register_default_sources
        from stockstat._domain.indicators import register_default_indicators

        reg = PluginRegistry()
        register_default_sources(reg)
        register_default_indicators(reg)
        reg.initialize(context=None)

        health = reg.health_check()
        # Indicator plugins should all be healthy; source plugins may
        # fail if network is unavailable
        indicator_health = {k: v for k, v in health.items()
                            if k.startswith("indicators.")}
        assert all(v is True for v in indicator_health.values())
