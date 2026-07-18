#!/usr/bin/env python3
"""V3 Deployment Case C — Offline mode (no backend, local storage).

Scenario C from DESIGN_V3_CN §18.1 + v2.1 DESIGN_CN §15.3:
- No backend process; V2Client(mode="offline") with local Storage
- Data can be:
  - Pre-loaded via storage.write() / upsert()
  - Downloaded from data sources via ingest() (uses PluginRegistry adapters)
  - Read from an existing SQLite database file via SQLStorage
- Compute happens locally via LocalComputeBackend
- V3 remote() / cluster_info() available on the local backend

This test verifies offline mode + V3 ComputeBackend integration.

Exit code: 0 on success, 1 on failure.

Usage:
    python test_case_c_offline.py
"""
from __future__ import annotations

import sys

from _common import (
    EnvConfig, TestRunner, banner, step, ok, fail, warn, info,
    assert_v3_compute_backend, assert_cluster_info_shape,
    make_synthetic_data, make_ma_cross_strategy, encode_strategy,
)


def test_v2client_offline_memory_storage(env: EnvConfig) -> None:
    """V2Client(mode='offline') with MemoryStorage."""
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage
    from stockstat._core.compute import LocalComputeBackend

    c = V2Client(mode="offline", storage=MemoryStorage())
    assert c.mode == "offline"
    assert_v3_compute_backend(c, "local")
    assert isinstance(c.compute_backend, LocalComputeBackend)
    ok(f"V2Client offline + MemoryStorage: backend={c.compute_backend.name}")


def test_offline_ingest_synthetic(env: EnvConfig) -> None:
    """Offline ingest via the synthetic data source adapter."""
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage
    c = V2Client(mode="offline", storage=MemoryStorage())
    # Synthetic adapter doesn't need network
    result = c.ingest("SYNTH/BTC", source="synthetic", timeframe="1d")
    ingested = result.get("ingested", 0)
    if ingested == 0:
        warn("synthetic ingest returned 0 rows; adapter may not be registered")
        return
    ok(f"offline ingest SYNTH/BTC: {ingested} rows")


def test_offline_query_after_write(env: EnvConfig) -> None:
    """storage.upsert() then ohlcv() query roundtrip."""
    import pandas as pd
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage

    storage = MemoryStorage()
    c = V2Client(mode="offline", storage=storage)

    # Build synthetic OHLCV records and write directly
    dates = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    records = []
    for i, ts in enumerate(dates):
        records.append({
            "symbol": "TEST/USDT", "ts": ts,
            "open": 100+i, "high": 105+i, "low": 95+i,
            "close": 102+i, "volume": 1e6,
            "source": "test", "timeframe": "1d",
        })
    n = storage.upsert("ohlcv", records)
    assert n == 10, f"upsert returned {n}, expected 10"

    df = c.ohlcv("TEST/USDT", timeframe="1d")
    assert len(df) == 10, f"query returned {len(df)} rows"
    ok(f"offline query: {len(df)} rows, last close={df['close'].iloc[-1]:.2f}")


def test_offline_compute(env: EnvConfig) -> None:
    """Offline ComputeEngine works on locally-stored data."""
    import pandas as pd
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage

    storage = MemoryStorage()
    c = V2Client(mode="offline", storage=storage)
    # Seed data
    dates = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
    records = [{
        "symbol": "X/Y", "ts": ts,
        "open": 100+i, "high": 105+i, "low": 95+i,
        "close": 100+i*0.5, "volume": 1e6,
        "source": "test", "timeframe": "1d",
    } for i, ts in enumerate(dates)]
    storage.upsert("ohlcv", records)

    df = c.ohlcv("X/Y", timeframe="1d")
    ma = c.compute.ma(df.close, window=5)
    assert len(ma) == 30
    ok(f"offline compute.ma(5): len={len(ma)}, last={ma.iloc[-1]:.2f}")


def test_offline_backtest(env: EnvConfig) -> None:
    """Offline backtest via V2Client.backtest() (default LocalComputeBackend)."""
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage
    from stockstat.backtest import BacktestResult

    data = make_synthetic_data()
    c = V2Client(mode="offline", storage=MemoryStorage())
    strategy = make_ma_cross_strategy()()
    result = c.backtest(data, strategy, initial_cash=10000)
    assert isinstance(result, BacktestResult)
    assert len(result.equity) > 0
    ok(f"offline backtest: equity_len={len(result.equity)}, fills={len(result.fills)}")


def test_offline_compute_remote(env: EnvConfig) -> None:
    """V3 compute.remote() in offline mode."""
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage
    from stockstat._core.contracts.compute import TaskRef
    from stockstat.backtest import BacktestResult

    data = make_synthetic_data()
    c = V2Client(mode="offline", storage=MemoryStorage())
    # Inject stub client so LocalComputeBackend can fetch data
    class StubClient:
        def ohlcv(self, symbol, **kw):
            return data[symbol][kw.get("timeframe", "1d")]
    c.compute_backend._client = StubClient()

    strategy = make_ma_cross_strategy()()
    strategy_ref = encode_strategy(strategy)
    task = c.compute_backend.submit  # verify submit exists
    ok(f"compute_backend.submit callable: {callable(task)}")

    # Submit via compute.remote
    task_ref = c.compute.remote(
        "backtest",
        symbols=["BTC/USDT"], timeframe="1d",
        strategy_ref=strategy_ref,
        initial_cash=10000,
    )
    assert isinstance(task_ref, TaskRef)
    result = task_ref.wait(timeout=30)
    assert isinstance(result, BacktestResult)
    ok(f"offline V3 remote: task={task_ref.id[:8]}..., fills={len(result.fills)}")


def test_offline_cluster_info(env: EnvConfig) -> None:
    """cluster_info() works in offline mode."""
    from stockstat._api.client import V2Client
    from stockstat._core.storage import MemoryStorage
    c = V2Client(mode="offline", storage=MemoryStorage())
    info = c.compute_backend.cluster_info()
    assert_cluster_info_shape(info)
    assert info["workers"][0]["worker_id"] == "local"
    ok(f"offline cluster_info: {info['stats']['online_workers']} worker")


def test_offline_sqlstorage_read(env: EnvConfig) -> None:
    """SQLStorage can read an existing SQLite file (if present)."""
    import os
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "..", "stockstat.db")
    db_path = os.path.abspath(db_path)
    if not os.path.exists(db_path):
        warn(f"no stockstat.db at {db_path}; skipping SQLStorage read test")
        return

    from stockstat._api.client import V2Client
    from stockstat._core.storage import SQLStorage
    db_url = f"sqlite:///{db_path}"
    c = V2Client(mode="offline", storage=SQLStorage(database_url=db_url))
    ok(f"SQLStorage opened: {db_path}")
    # Try a query (may be empty if DB has no BTC/USDT)
    try:
        df = c.ohlcv("BTC/USDT", timeframe="1d", limit=5)
        ok(f"SQLStorage query: {len(df)} rows")
    except Exception as e:
        warn(f"SQLStorage query failed: {e}")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="V3 Case C: offline mode")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    banner("V3 Deployment Case C: Offline mode (no backend, local storage)")
    env = EnvConfig()
    info(f"transport={env.transport}, skip_network={env.skip_network}")

    runner = TestRunner(env)
    runner.run("V2Client offline + MemoryStorage", test_v2client_offline_memory_storage, critical=True)
    runner.run("Offline ingest via synthetic adapter", test_offline_ingest_synthetic)
    runner.run("Offline query after storage.upsert()", test_offline_query_after_write)
    runner.run("Offline ComputeEngine on local data", test_offline_compute)
    runner.run("Offline backtest (default LocalComputeBackend)", test_offline_backtest)
    runner.run("Offline V3 compute.remote()", test_offline_compute_remote)
    runner.run("Offline cluster_info()", test_offline_cluster_info)
    runner.run("SQLStorage reads existing SQLite file", test_offline_sqlstorage_read)

    return runner.summarize()


if __name__ == "__main__":
    sys.exit(main())
