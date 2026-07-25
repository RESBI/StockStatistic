#!/usr/bin/env python3
"""V3 Deployment Case B — Storage-compute separation (HTTP backend).

Scenario B from DESIGN_V3_CN §18.1:
- Storage backend (stockstat_backend) runs as a separate process
- Client connects via HTTP for data access (ohlcv / ingest)
- Computation happens locally (default LocalComputeBackend)
- V3 ComputeBackend layer is in place but transparent (data via HTTP,
  compute via local BacktestEngine)

This test requires a running backend. The launcher script starts one
automatically if needed.

Exit code: 0 on success, 1 on failure.

Usage:
    python test_case_b_storage_separated.py                       # localhost:8000
    python test_case_b_storage_separated.py --host 192.168.1.100  # remote backend
"""
from __future__ import annotations

import argparse
import sys
import time

from _common import (
    EnvConfig, TestRunner, banner, step, ok, fail, warn, info,
    assert_v3_compute_backend, assert_cluster_info_shape,
    make_ma_cross_strategy, encode_strategy,
)


def test_backend_health(env: EnvConfig) -> None:
    """Backend must respond to /api/v1/health."""
    from stockstat.client import StockStatClient
    c = StockStatClient(host=env.host, port=env.port, use_https=env.use_https)
    t0 = time.perf_counter()
    healthy = c.health()
    latency_ms = (time.perf_counter() - t0) * 1000
    if not healthy:
        raise AssertionError(f"backend not healthy at {env.base_url}")
    ok(f"backend online ({latency_ms:.1f} ms RTT)")


def test_data_sources(env: EnvConfig) -> None:
    """Backend exposes data source list."""
    from stockstat.client import StockStatClient
    c = StockStatClient(host=env.host, port=env.port, use_https=env.use_https)
    sources = c.sources()
    names = [s["name"] for s in sources]
    if "binance" not in names and "yfinance" not in names:
        raise AssertionError(f"expected data sources missing: {names}")
    ok(f"sources: {names}")


def test_ingest_query_roundtrip(env: EnvConfig) -> None:
    """Ingest a small symbol range and query it back."""
    from stockstat.client import StockStatClient
    c = StockStatClient(host=env.host, port=env.port, use_https=env.use_https)
    symbol = env.symbol
    source = "binance" if "/" in symbol else "yfinance"

    # Use a short range to keep test fast
    try:
        result = c.ingest(
            symbol, source=source,
            start=env.start_date, end=env.end_date,
            timeframe="1d",
        )
        ingested = result.get("ingested", 0)
        ok(f"ingest {symbol}: {ingested} rows")
    except Exception as e:
        if env.skip_network:
            warn(f"ingest failed (network skipped): {e}")
            return
        raise

    df = c.ohlcv(symbol, timeframe="1d", limit=5)
    if df.empty:
        raise AssertionError(f"query returned empty DataFrame for {symbol}")
    ok(f"query: {len(df)} rows, last close={df['close'].iloc[-1]:.2f}")


def test_compute_local_with_remote_data(env: EnvConfig) -> None:
    """Local compute (LocalComputeBackend) on data fetched via HTTP."""
    from stockstat.client import StockStatClient
    c = StockStatClient(host=env.host, port=env.port, use_https=env.use_https)
    assert_v3_compute_backend(c, "local")

    df = c.ohlcv(env.symbol, timeframe="1d", limit=100)
    if df.empty:
        warn(f"no data for {env.symbol}; skipping compute test")
        return
    ma = c.compute.ma(df.close, window=20)
    rsi = c.compute.rsi(df.close, window=14)
    ok(f"compute.ma(20)={ma.iloc[-1]:.2f}, rsi(14)={rsi.iloc[-1]:.2f}")


def test_backtest_via_http_data(env: EnvConfig) -> None:
    """Backtest using data fetched from the HTTP backend."""
    from stockstat.client import StockStatClient
    from stockstat.backtest import BacktestResult
    c = StockStatClient(host=env.host, port=env.port, use_https=env.use_https)
    df = c.ohlcv(env.symbol, timeframe="1d", limit=200)
    if df.empty:
        warn(f"no data for {env.symbol}; skipping backtest test")
        return

    data = {env.symbol: {"1d": df}}
    strategy = make_ma_cross_strategy()()
    result = c.backtest(data, strategy, initial_cash=10000)
    assert isinstance(result, BacktestResult)
    ok(f"backtest: equity_len={len(result.equity)}, fills={len(result.fills)}")


def test_compute_remote_with_http_data(env: EnvConfig) -> None:
    """V3 compute.remote('backtest') using HTTP-fetched data.

    The data access goes through the client's HTTP DataClient; the
    compute happens on LocalComputeBackend.
    """
    from stockstat.client import StockStatClient
    from stockstat._core.contracts.compute import TaskRef
    from stockstat.backtest import BacktestResult
    c = StockStatClient(host=env.host, port=env.port, use_https=env.use_https)
    df = c.ohlcv(env.symbol, timeframe="1d", limit=200)
    if df.empty:
        warn(f"no data for {env.symbol}; skipping V3 remote test")
        return

    # Inject stub client for data access (since LocalComputeBackend
    # would try to fetch via HTTP again — we already have the data)
    class StubClient:
        def ohlcv(self, symbol, **kw):
            return df
    c.compute_backend._client = StubClient()

    strategy = make_ma_cross_strategy()()
    strategy_ref = encode_strategy(strategy)
    task = c.compute.remote(
        "backtest",
        symbols=[env.symbol], timeframe="1d",
        strategy_ref=strategy_ref,
        initial_cash=10000,
    )
    assert isinstance(task, TaskRef)
    result = task.wait(timeout=60)
    assert isinstance(result, BacktestResult)
    ok(f"V3 remote backtest: task={task.id[:8]}..., fills={len(result.fills)}")


def test_cluster_info_local(env: EnvConfig) -> None:
    """cluster_info() shows single local worker even with HTTP backend."""
    from stockstat.client import StockStatClient
    c = StockStatClient(host=env.host, port=env.port, use_https=env.use_https)
    info = c.compute.cluster_info()
    assert_cluster_info_shape(info)
    assert info["workers"][0]["worker_id"] == "local"
    ok(f"cluster_info: {info['stats']['online_workers']} local worker")


def main() -> int:
    parser = argparse.ArgumentParser(description="V3 Case B: storage-compute separation")
    parser.add_argument("--host", default=None, help="Backend host (overrides env)")
    parser.add_argument("--port", type=int, default=None, help="Backend port (overrides env)")
    parser.add_argument("--https", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    banner("V3 Deployment Case B: Storage-compute separation (HTTP backend)")
    env = EnvConfig()
    if args.host:
        env.host = args.host
    if args.port:
        env.port = args.port
    if args.https:
        env.use_https = True
    info(f"target: {env.base_url}")

    runner = TestRunner(env)
    runner.run("Backend health check", test_backend_health, critical=True)
    runner.run("Data source list", test_data_sources)
    runner.run("Ingest + query roundtrip", test_ingest_query_roundtrip)
    runner.run("Local compute on HTTP-fetched data", test_compute_local_with_remote_data)
    runner.run("Backtest via HTTP data", test_backtest_via_http_data)
    runner.run("V3 compute.remote() with HTTP data", test_compute_remote_with_http_data)
    runner.run("cluster_info() (local backend, HTTP data)", test_cluster_info_local)

    return runner.summarize()


if __name__ == "__main__":
    sys.exit(main())
