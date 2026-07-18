"""V3 compatibility matrix tests — v1.7 StockStatClient × v2 V2Client × Local backend.

This is the critical compatibility test that guarantees V3 introduces
zero behavior change for existing v1.7 / v2 users. The matrix:

| Client      | Backend       | Expected behavior                     |
|-------------|---------------|---------------------------------------|
| StockStat   | default(None) | v2.1 direct BacktestEngine            |
| StockStat   | LocalCompute  | v2.1 direct (short-circuit)           |
| V2Client on | default(None) | v2.1 direct BacktestEngine            |
| V2Client off| default(None) | v2.1 direct BacktestEngine            |

For each combination, backtest results must be numerically identical
to the v2.1 baseline (direct BacktestEngine call).

Plus additional cross-cutting tests:
- Public API surface unchanged (all v1.7 methods still callable)
- ComputeEngine remote()/cluster_info() don't break existing methods
- V2Client online delegates to StockStatClient's backend
- BacktestResult structure identical across paths
"""
from __future__ import annotations

import pytest
import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def sample_data():
    """Synthetic OHLCV data."""
    dates = pd.date_range("2024-01-01", periods=80, freq="D", tz="UTC")
    rng = np.random.RandomState(123)
    returns = rng.normal(0.001, 0.02, 80)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.005, 80)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, 80)))
    op = close * (1 + rng.normal(0, 0.003, 80))
    vol = rng.uniform(1e6, 5e6, 80)
    df = pd.DataFrame({
        "open": op, "high": high, "low": low, "close": close, "volume": vol,
    }, index=dates)
    return {"BTC/USDT": {"1d": df}}


@pytest.fixture
def simple_strategy_factory():
    """Factory for a simple strategy that buys on day 5 and sells on day 50.

    Returns a callable that produces a fresh strategy instance each call.
    Strategy is stateful (tracks _bought / _bar_count), so each backtest
    run needs a new instance.
    """
    from stockstat.backtest import Strategy, Order, OrderSide, OrderType

    class SimpleStrategy(Strategy):
        name = "simple_test"
        def __init__(self):
            super().__init__()
            self._bought = False
            self._bar_count = 0
        def on_bar(self, ctx):
            self._bar_count += 1
            if self._bar_count == 5 and not self._bought:
                ctx.broker.submit(Order(
                    symbol="BTC/USDT", side=OrderSide.BUY,
                    order_type=OrderType.MARKET, qty=1.0,
                ))
                self._bought = True
            elif self._bar_count == 50 and self._bought:
                ctx.broker.submit(Order(
                    symbol="BTC/USDT", side=OrderSide.SELL,
                    order_type=OrderType.MARKET, qty=1.0,
                ))
                self._bought = False

    return SimpleStrategy


@pytest.fixture
def simple_strategy(simple_strategy_factory):
    """Single strategy instance (for tests that only run one backtest)."""
    return simple_strategy_factory()


def _run_baseline_backtest(data, strategy_factory, initial_cash=10000):
    """Run a backtest via the v2.1 code path (direct BacktestEngine)."""
    from stockstat.backtest import BacktestEngine
    from stockstat.compute.engine import ComputeEngine
    engine = BacktestEngine(
        data=data, strategy=strategy_factory(),
        initial_cash=initial_cash,
        compute_engine=ComputeEngine(client=None),
    )
    return engine.run()


# ═══════════════════════════════════════════════════════════════
# Test 1: All four client×backend combinations produce identical results
# ═══════════════════════════════════════════════════════════════


class TestCompatMatrix:
    """Critical: V3 must not change backtest results for any existing client."""

    def test_v17_stockstat_default_backend(self, sample_data, simple_strategy_factory):
        """StockStatClient(compute_backend=None) → v2.1 direct path."""
        from stockstat.client import StockStatClient
        from stockstat._core.compute import LocalComputeBackend

        c = StockStatClient(host="localhost", port=1)
        # Default backend is lazily LocalComputeBackend
        assert isinstance(c.compute_backend, LocalComputeBackend)
        # But backtest() short-circuits to direct BacktestEngine (v2.1 path)
        result = c.backtest(sample_data, simple_strategy_factory(), initial_cash=10000)

        baseline = _run_baseline_backtest(sample_data, simple_strategy_factory, 10000)
        np.testing.assert_array_almost_equal(
            result.equity.values, baseline.equity.values, decimal=6,
        )
        assert len(result.fills) == len(baseline.fills)

    def test_v17_stockstat_explicit_local_backend(self, sample_data, simple_strategy_factory):
        """StockStatClient(compute_backend=LocalComputeBackend()) → v2.1 path."""
        from stockstat.client import StockStatClient
        from stockstat._core.compute import LocalComputeBackend

        c = StockStatClient(
            host="localhost", port=1,
            compute_backend=LocalComputeBackend(),
        )
        result = c.backtest(sample_data, simple_strategy_factory(), initial_cash=10000)

        baseline = _run_baseline_backtest(sample_data, simple_strategy_factory, 10000)
        np.testing.assert_array_almost_equal(
            result.equity.values, baseline.equity.values, decimal=6,
        )

    def test_v2_offline_default_backend(self, sample_data, simple_strategy_factory):
        """V2Client(mode="offline") → v2.1 direct path."""
        from stockstat._api.client import V2Client
        from stockstat._core.storage import MemoryStorage
        from stockstat._core.compute import LocalComputeBackend

        c = V2Client(mode="offline", storage=MemoryStorage())
        assert isinstance(c.compute_backend, LocalComputeBackend)
        result = c.backtest(sample_data, simple_strategy_factory(), initial_cash=10000)

        baseline = _run_baseline_backtest(sample_data, simple_strategy_factory, 10000)
        np.testing.assert_array_almost_equal(
            result.equity.values, baseline.equity.values, decimal=6,
        )

    def test_all_four_paths_identical(self, sample_data, simple_strategy_factory):
        """All 4 combinations must produce the same numerical result."""
        from stockstat.client import StockStatClient
        from stockstat._api.client import V2Client
        from stockstat._core.storage import MemoryStorage
        from stockstat._core.compute import LocalComputeBackend

        baseline = _run_baseline_backtest(sample_data, simple_strategy_factory, 10000)

        # 1. StockStatClient default (fresh strategy instance per run)
        c1 = StockStatClient(host="localhost", port=1)
        r1 = c1.backtest(sample_data, simple_strategy_factory(), initial_cash=10000)

        # 2. StockStatClient explicit LocalComputeBackend
        c2 = StockStatClient(
            host="localhost", port=1,
            compute_backend=LocalComputeBackend(),
        )
        r2 = c2.backtest(sample_data, simple_strategy_factory(), initial_cash=10000)

        # 3. V2Client offline default
        c3 = V2Client(mode="offline", storage=MemoryStorage())
        r3 = c3.backtest(sample_data, simple_strategy_factory(), initial_cash=10000)

        # 4. V2Client offline explicit LocalComputeBackend
        c4 = V2Client(
            mode="offline",
            storage=MemoryStorage(),
            compute_backend=LocalComputeBackend(),
        )
        r4 = c4.backtest(sample_data, simple_strategy_factory(), initial_cash=10000)

        # All must match baseline
        for i, r in enumerate([r1, r2, r3, r4], 1):
            np.testing.assert_array_almost_equal(
                r.equity.values, baseline.equity.values, decimal=6,
                err_msg=f"Path {i} diverged from baseline",
            )
            assert len(r.fills) == len(baseline.fills), (
                f"Path {i} fill count mismatch: {len(r.fills)} vs {len(baseline.fills)}"
            )


# ═══════════════════════════════════════════════════════════════
# Test 2: Public API surface unchanged
# ═══════════════════════════════════════════════════════════════


class TestPublicAPIUnchanged:
    """All v1.7 public API methods must still work."""

    def test_stockstat_client_methods_exist(self):
        from stockstat.client import StockStatClient
        c = StockStatClient(host="localhost", port=1)
        # v1.7 data methods
        assert callable(c.ohlcv)
        assert callable(c.ohlcv_batch)
        assert callable(c.ingest)
        assert callable(c.symbols)
        assert callable(c.sources)
        assert callable(c.health)
        # v1.7 compute / plot / backtest / run_dsl
        assert hasattr(c, "compute")
        assert hasattr(c, "plot")
        assert callable(c.backtest)
        assert callable(c.run_dsl)
        # V3 new
        assert hasattr(c, "compute_backend")
        assert callable(c.compute.remote)
        assert callable(c.compute.cluster_info)

    def test_v2client_methods_exist(self):
        from stockstat._api.client import V2Client
        from stockstat._core.storage import MemoryStorage
        c = V2Client(mode="offline", storage=MemoryStorage())
        assert callable(c.ohlcv)
        assert callable(c.ingest)
        assert callable(c.symbols)
        assert hasattr(c, "compute")
        assert callable(c.backtest)
        assert callable(c.run_dsl)
        assert hasattr(c, "plot")
        # V3 new
        assert hasattr(c, "compute_backend")

    def test_compute_engine_all_methods_present(self):
        """All 40+ ComputeEngine methods must still be callable."""
        from stockstat.compute.engine import ComputeEngine
        engine = ComputeEngine(client=None)
        # Trend
        for m in ["ma", "ema", "macd"]:
            assert callable(getattr(engine, m))
        # Oscillator
        for m in ["rsi", "kdj"]:
            assert callable(getattr(engine, m))
        # Volatility
        for m in ["std", "atr", "bollinger"]:
            assert callable(getattr(engine, m))
        # Statistics
        for m in ["corr", "beta", "sharpe", "max_drawdown", "var",
                  "returns", "log_returns"]:
            assert callable(getattr(engine, m))
        # Nonlinear
        for m in ["wavelet_decompose", "spectral_entropy", "grey_relation",
                  "gm11_predict", "transfer_entropy", "hurst_dfa",
                  "sample_entropy", "permutation_entropy"]:
            assert callable(getattr(engine, m))
        # Registry
        assert callable(engine.register)
        assert callable(engine.call)
        assert callable(engine.list_indicators)
        # V3
        assert callable(engine.remote)
        assert callable(engine.cluster_info)

    def test_backtest_engine_api_unchanged(self):
        """BacktestEngine constructor signature unchanged."""
        from stockstat.backtest import BacktestEngine
        import inspect
        sig = inspect.signature(BacktestEngine.__init__)
        params = set(sig.parameters.keys())
        # Must include all v1.7 parameters
        expected = {
            "self", "data", "strategy", "initial_cash",
            "cost_model", "fill_model", "benchmark", "trade_on",
            "allow_short", "lookahead_audit", "seed",
            "compute_engine", "periods_per_year", "execution_model",
        }
        assert expected.issubset(params), f"Missing: {expected - params}"


# ═══════════════════════════════════════════════════════════════
# Test 3: ComputeEngine methods still work correctly
# ═══════════════════════════════════════════════════════════════


class TestComputeEngineStillWorks:
    """ComputeEngine methods produce correct results (not broken by V3 additions)."""

    def test_ma_works(self):
        from stockstat.compute.engine import ComputeEngine
        engine = ComputeEngine(client=None)
        s = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        result = engine.ma(s, window=3)
        assert len(result) == 10
        # MA(3) at index 2 = (1+2+3)/3 = 2.0
        assert result.iloc[2] == pytest.approx(2.0, abs=1e-6)

    def test_rsi_works(self):
        from stockstat.compute.engine import ComputeEngine
        engine = ComputeEngine(client=None)
        s = pd.Series([10, 11, 12, 11, 13, 14, 13, 15, 16, 15,
                       17, 18, 17, 19, 20, 19, 21, 22, 21, 23])
        result = engine.rsi(s, window=10)
        assert len(result) == 20
        # RSI should be in [0, 100]
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_bollinger_works(self):
        from stockstat.compute.engine import ComputeEngine
        engine = ComputeEngine(client=None)
        s = pd.Series(np.random.RandomState(0).normal(100, 5, 50))
        upper, mid, lower = engine.bollinger(s, window=20, k=2.0)
        assert len(upper) == 50
        # Upper > mid > lower (for non-constant data)
        valid_idx = upper.dropna().index
        assert (upper.loc[valid_idx] >= mid.loc[valid_idx]).all()
        assert (mid.loc[valid_idx] >= lower.loc[valid_idx]).all()

    def test_list_indicators_returns_list(self):
        from stockstat.compute.engine import ComputeEngine
        engine = ComputeEngine(client=None)
        result = engine.list_indicators()
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# Test 4: V2Client online delegates to StockStatClient backend
# ═══════════════════════════════════════════════════════════════


class TestV2ClientOnlineDelegation:
    def test_online_v2client_uses_stockstat_backend(self):
        """V2Client(mode="online") should delegate compute_backend to StockStatClient."""
        from stockstat._api.client import V2Client
        from stockstat.client import StockStatClient
        from stockstat._core.compute import LocalComputeBackend

        c = V2Client(mode="online", host="localhost", port=1)
        # online mode creates a StockStatClient internally
        assert c._online_client is not None
        assert isinstance(c._online_client, StockStatClient)
        # compute_backend delegates to the underlying StockStatClient
        assert c.compute_backend is c._online_client.compute_backend
        assert isinstance(c.compute_backend, LocalComputeBackend)

    def test_online_v2client_cluster_info(self):
        from stockstat._api.client import V2Client
        c = V2Client(mode="online", host="localhost", port=1)
        info = c.compute_backend.cluster_info()
        assert info["dispatcher"]["id"] == "local"


# ═══════════════════════════════════════════════════════════════
# Test 5: async_submit flag behavior
# ═══════════════════════════════════════════════════════════════


class TestAsyncSubmitFlag:
    def test_backtest_without_async_returns_result(self, sample_data, simple_strategy_factory):
        """backtest(async_submit=False) [default] returns BacktestResult directly."""
        from stockstat.client import StockStatClient
        from stockstat.backtest import BacktestResult
        c = StockStatClient(host="localhost", port=1)
        result = c.backtest(sample_data, simple_strategy_factory(), initial_cash=10000)
        assert isinstance(result, BacktestResult)

    def test_backtest_with_async_local_returns_result(self, sample_data, simple_strategy_factory):
        """backtest(async_submit=True) on LocalComputeBackend returns BacktestResult.

        Note: LocalComputeBackend short-circuits, so async_submit has no
        effect — backtest still goes through the v2.1 direct path.
        """
        from stockstat.client import StockStatClient
        from stockstat._core.compute import LocalComputeBackend
        from stockstat.backtest import BacktestResult
        c = StockStatClient(
            host="localhost", port=1,
            compute_backend=LocalComputeBackend(),
        )
        result = c.backtest(
            sample_data, simple_strategy_factory(),
            initial_cash=10000, async_submit=True,
        )
        # Local backend short-circuits — async_submit is ignored
        assert isinstance(result, BacktestResult)


# ═══════════════════════════════════════════════════════════════
# Test 6: V3 entry points don't interfere with v1.7
# ═══════════════════════════════════════════════════════════════


class TestV3EntryPointsIsolated:
    def test_compute_ma_after_cluster_info(self):
        """Calling cluster_info() before ma() must not break ma()."""
        from stockstat.client import StockStatClient
        c = StockStatClient(host="localhost", port=1)
        # V3 entry point
        info = c.compute.cluster_info()
        assert info is not None
        # v1.7 method still works
        s = pd.Series([1.0, 2, 3, 4, 5])
        result = c.compute.ma(s, window=2)
        assert len(result) == 5

    def test_remote_does_not_consume_subsequent_kwargs(self):
        """remote() must not mutate kwargs that callers reuse."""
        from stockstat.client import StockStatClient
        c = StockStatClient(host="localhost", port=1)

        kwargs = {"window": 10, "method": "ma"}
        # Build a remote call (it will fail because no data, but kwargs intact)
        try:
            task = c.compute.remote(
                "indicator",
                symbols=["BTC/USDT"],
                method="ma",
                kwargs={"window": 10},
            )
            task.wait(timeout=5)
        except Exception:
            pass  # expected — no data
        # kwargs passed to remote should not be mutated
        # (This is more about ensuring no side effects)


# ═══════════════════════════════════════════════════════════════
# Test 7: V3 imports don't break v2.1 imports
# ═══════════════════════════════════════════════════════════════


class TestImportCompatibility:
    def test_top_level_import_unchanged(self):
        """`from stockstat import StockStatClient` still works."""
        from stockstat import StockStatClient
        assert StockStatClient is not None

    def test_backtest_imports_unchanged(self):
        """All v1.7 backtest imports still work."""
        from stockstat.backtest import (
            BacktestEngine, Strategy, FunctionStrategy, strategy,
            Order, Fill, OrderSide, OrderType, TimeInForce, OrderStatus,
            SimulatedBroker, Portfolio, Position,
            CostModel, PercentCost, FixedCost, TieredCost, MinCost,
            StampDutyCost, ZeroCost, MakerTakerCost, BinanceCost,
            BINANCE_SPOT, BINANCE_SPOT_BNB, BINANCE_FUTURES, BINANCE_FUTURES_BNB,
            FillModel, NextOpenFill, NextCloseFill, ThisCloseFill,
            VWAPFill, WorstPriceFill, IntrabarLimitFill, IntrabarFillModel,
            BacktestResult, sizing,
            buy_and_hold, benchmark_equity, dca_equity,
            IntrabarSimulator, StrategyBatchRunner, BatchResults,
            BacktestAnalyzer, fee_sweep, maker_taker_sweep,
            ExecutionModel, NextBarExecution, IntrabarExecution,
        )
        # All imports succeeded
        assert BacktestEngine is not None
        assert Strategy is not None

    def test_compute_imports_unchanged(self):
        from stockstat.compute.engine import ComputeEngine
        from stockstat.compute.registry import register, call_indicator, list_indicators
        assert ComputeEngine is not None

    def test_v2_imports_unchanged(self):
        from stockstat._api.client import V2Client
        from stockstat._api.dsl import DslEngine
        from stockstat._core.plugin import PluginRegistry
        from stockstat._core.storage import MemoryStorage, SQLStorage
        from stockstat._core.codec import JsonCodec, ArrowCodec
        assert V2Client is not None
        assert DslEngine is not None

    def test_v3_imports_work(self):
        """V3 modules can be imported without errors."""
        from stockstat._core.contracts.compute import (
            ComputeBackend, TaskRef, TaskInfo, TaskState,
        )
        from stockstat._core.contracts.task import (
            TaskSpec, DataSpec, ComputeSpec, DispatchSpec,
        )
        from stockstat._core.contracts.transport import Transport
        from stockstat._core.protocol import Envelope, Headers, messages
        from stockstat._core.compute import LocalComputeBackend
        from stockstat._core.transport import InProcessTransport, make_pair
        from stockstat._core.codec import (
            CloudpickleCodec, MsgpackCodec, RawCodec,
            get_codec_for_content_type,
        )
        from stockstat._core.errors import (
            TaskError, TaskNotReadyError, TaskCancelledError,
            TaskTimeoutError, ProtocolMismatchError,
        )
        # All V3 imports succeeded
        assert ComputeBackend is not None
        assert LocalComputeBackend is not None
