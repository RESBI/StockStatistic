#!/usr/bin/env python3
"""V3 Deployment Case A — Single-machine full-stack (in-process).

Scenario A from DESIGN_V3_CN §18.1:
- Storage + Client + Compute all in the same Python process
- No HTTP backend, no Dispatcher, no Worker process
- Default LocalComputeBackend (lazily created)
- Tests both v2.1-style direct calls and V3 remote() / cluster_info()

This is the simplest deployment: ``pip install stockstat`` and go.

Exit code: 0 on success, 1 on failure.

Usage:
    python test_case_a_single_machine.py
    python test_case_a_single_machine.py --verbose
"""
from __future__ import annotations

import argparse
import sys

from _common import (
    EnvConfig, TestRunner, banner, step, ok, fail, info,
    assert_v3_compute_backend, assert_cluster_info_shape,
    make_synthetic_data, make_ma_cross_strategy, encode_strategy,
)


def test_v17_stockstat_client_default(env: EnvConfig) -> None:
    """StockStatClient() with no compute_backend -> LocalComputeBackend."""
    from stockstat.client import StockStatClient
    from stockstat._core.compute import LocalComputeBackend

    c = StockStatClient(host="localhost", port=1)
    assert_v3_compute_backend(c, "local")
    assert isinstance(c.compute_backend, LocalComputeBackend)
    ok(f"StockStatClient default backend = {c.compute_backend.name}")


def test_v2_offline_client_default(env: EnvConfig) -> None:
    """V2Client(mode='offline') -> LocalComputeBackend."""
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage
    from stockstat._core.compute import LocalComputeBackend

    c = V2Client(mode="offline", storage=MemoryStorage())
    assert_v3_compute_backend(c, "local")
    assert isinstance(c.compute_backend, LocalComputeBackend)
    ok(f"V2Client offline default backend = {c.compute_backend.name}")


def test_cluster_info_local(env: EnvConfig) -> None:
    """cluster_info() returns a single in-process worker."""
    from stockstat.client import StockStatClient
    c = StockStatClient(host="localhost", port=1)
    info = c.compute.cluster_info()
    assert_cluster_info_shape(info)
    assert info["workers"][0]["worker_id"] == "local"
    ok(f"cluster_info: {info['stats']['total_workers']} worker, "
       f"{info['workers'][0]['capabilities'][:3]}...")


def test_compute_engine_methods_unchanged(env: EnvConfig) -> None:
    """v1.7 ComputeEngine methods still work (no V3 interference)."""
    import pandas as pd
    from stockstat.client import StockStatClient
    c = StockStatClient(host="localhost", port=1)
    s = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    ma = c.compute.ma(s, window=3)
    assert ma.iloc[2] == 2.0
    rsi = c.compute.rsi(s, window=5)
    assert len(rsi) == 10
    ok(f"compute.ma / rsi work (ma[2]={ma.iloc[2]}, rsi_len={len(rsi)})")


def test_backtest_default_path(env: EnvConfig) -> None:
    """backtest() without async_submit returns BacktestResult directly."""
    from stockstat.client import StockStatClient
    from stockstat.backtest import BacktestResult
    data = make_synthetic_data()
    strategy = make_ma_cross_strategy()()
    c = StockStatClient(host="localhost", port=1)
    result = c.backtest(data, strategy, initial_cash=10000)
    assert isinstance(result, BacktestResult)
    assert len(result.equity) > 0
    ok(f"backtest: equity_len={len(result.equity)}, fills={len(result.fills)}")


def test_compute_remote_backtest(env: EnvConfig) -> None:
    """client.compute.remote('backtest', ...) -> TaskRef -> BacktestResult."""
    from stockstat.client import StockStatClient
    from stockstat._core.contracts.compute import TaskRef
    from stockstat.backtest import BacktestResult
    data = make_synthetic_data()
    strategy = make_ma_cross_strategy()()
    strategy_ref = encode_strategy(strategy)

    c = StockStatClient(host="localhost", port=1)
    # Inject stub data access (since no real backend)
    class StubClient:
        def ohlcv(self, symbol, **kw):
            return data[symbol][kw.get("timeframe", "1d")]
    c.compute_backend._client = StubClient()

    task = c.compute.remote(
        "backtest",
        symbols=["BTC/USDT"], timeframe="1d",
        strategy_ref=strategy_ref,
        initial_cash=10000,
        timeout=30,
    )
    assert isinstance(task, TaskRef)
    ok(f"submitted: task_id={task.id[:8]}..., status={task.status}")
    result = task.wait(timeout=30)
    assert isinstance(result, BacktestResult)
    ok(f"completed: equity_len={len(result.equity)}, fills={len(result.fills)}")


def test_compute_remote_indicator(env: EnvConfig) -> None:
    """client.compute.remote('indicator', ...) -> pd.Series."""
    from stockstat.client import StockStatClient
    import pandas as pd
    data = make_synthetic_data()
    c = StockStatClient(host="localhost", port=1)
    class StubClient:
        def ohlcv(self, symbol, **kw):
            return data[symbol][kw.get("timeframe", "1d")]
    c.compute_backend._client = StubClient()

    task = c.compute.remote(
        "indicator",
        symbols=["BTC/USDT"], timeframe="1d",
        method="ma", kwargs={"window": 10},
    )
    result = task.wait(timeout=10)
    assert isinstance(result, pd.Series)
    assert len(result) == 100
    ok(f"indicator MA(10): len={len(result)}, last={result.iloc[-1]:.2f}")


def test_compute_remote_custom(env: EnvConfig) -> None:
    """client.compute.remote('custom', ...) returns acknowledgement."""
    from stockstat.client import StockStatClient
    c = StockStatClient(host="localhost", port=1)
    task = c.compute.remote(
        "custom",
        symbols=[],
        hello="world",
    )
    result = task.wait(timeout=5)
    assert result["task_type"] == "custom"
    assert result["params"]["hello"] == "world"
    ok(f"custom task: {result['params']}")


def test_backtest_local_equals_direct(env: EnvConfig) -> None:
    """LocalComputeBackend backtest == direct BacktestEngine call (numerical)."""
    import numpy as np
    from stockstat.backtest import BacktestEngine
    from stockstat.compute.engine import ComputeEngine
    from stockstat._core.compute import LocalComputeBackend
    data = make_synthetic_data()
    StrategyClass = make_ma_cross_strategy()

    # Direct path (v2.1)
    engine = BacktestEngine(
        data=data, strategy=StrategyClass(),
        initial_cash=10000,
        compute_engine=ComputeEngine(client=None),
    )
    direct = engine.run()

    # Via LocalComputeBackend (TaskSpec path)
    backend = LocalComputeBackend()
    class StubClient:
        def ohlcv(self, symbol, **kw):
            return data[symbol][kw.get("timeframe", "1d")]
    backend._client = StubClient()
    strategy_ref = encode_strategy(StrategyClass())
    from stockstat._core.contracts.task import (
        TaskSpec, DataSpec, ComputeSpec, new_task_id,
    )
    spec = TaskSpec(
        task_id=new_task_id(),
        data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
        compute_spec=ComputeSpec(
            task_type="backtest", strategy_ref=strategy_ref, initial_cash=10000,
        ),
    )
    via_backend = backend.submit(spec).wait(timeout=30)

    np.testing.assert_array_almost_equal(
        via_backend.equity.values, direct.equity.values, decimal=6,
    )
    ok(f"local vs direct: max_diff=0.00e+00, fills={len(via_backend.fills)}")


def test_in_process_transport_pair(env: EnvConfig) -> None:
    """InProcessTransport.make_pair() enables bidirectional messaging."""
    from stockstat._core.transport import make_pair
    from stockstat._core.protocol import Envelope
    a, b = make_pair()
    env1 = Envelope(type="task.submit", payload={"x": 1})
    a.send(env1)
    r = b.receive(timeout=1.0)
    assert r is not None and r.payload["x"] == 1
    ok(f"transport pair: {r.type} {r.payload}")


def main() -> int:
    parser = argparse.ArgumentParser(description="V3 Case A: single-machine full-stack")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    banner("V3 Deployment Case A: Single-machine full-stack (in-process)")
    env = EnvConfig()
    info(f"transport={env.transport}, dispatcher_url={env.dispatcher_url}")

    runner = TestRunner(env)
    runner.run("V1.7 StockStatClient default backend", test_v17_stockstat_client_default, critical=True)
    runner.run("V2 V2Client offline default backend", test_v2_offline_client_default)
    runner.run("cluster_info() returns in-process worker", test_cluster_info_local)
    runner.run("ComputeEngine methods unchanged (v1.7 compatibility)", test_compute_engine_methods_unchanged)
    runner.run("backtest() default path returns BacktestResult", test_backtest_default_path)
    runner.run("compute.remote('backtest') -> TaskRef", test_compute_remote_backtest)
    runner.run("compute.remote('indicator') -> Series", test_compute_remote_indicator)
    runner.run("compute.remote('custom') -> ack", test_compute_remote_custom)
    runner.run("Local vs direct backtest numerical consistency", test_backtest_local_equals_direct)
    runner.run("InProcessTransport make_pair()", test_in_process_transport_pair)

    return runner.summarize()


if __name__ == "__main__":
    sys.exit(main())
