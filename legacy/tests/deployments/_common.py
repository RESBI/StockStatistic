"""Common helpers for V3 deployment case tests.

Each deployment case test (test_case_*.py) is a standalone script that
exits 0 on success, non-zero on failure. The accompanying .bat / .sh
scripts set environment variables and launch the .py.

This module centralises:
- Environment-variable parsing
- Frontend path setup (so tests work without `pip install`)
- Pretty printing helpers (step / ok / fail / warn)
- V3-specific assertions (compute_backend type, cluster_info shape, etc.)
- Sample strategy / data factories reused across cases

Design goal: each test_case_*.py is runnable standalone via
``python test_case_xxx.py`` OR via the launcher scripts.
"""
from __future__ import annotations

import os
import sys
import time
import functools
import traceback
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════
# Path bootstrap — find frontend/ regardless of where we run from
# ═══════════════════════════════════════════════════════════════

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_FRONTEND = os.path.join(_PROJECT_ROOT, "frontend")
_BACKEND = os.path.join(_PROJECT_ROOT, "backend")

if _FRONTEND not in sys.path:
    sys.path.insert(0, _FRONTEND)


# ═══════════════════════════════════════════════════════════════
# Pretty printing (terminal-colour aware)
# ═══════════════════════════════════════════════════════════════

if sys.stdout.isatty():
    _GREEN = "\033[92m"
    _RED = "\033[91m"
    _YELLOW = "\033[93m"
    _CYAN = "\033[96m"
    _BOLD = "\033[1m"
    _NC = "\033[0m"
else:
    _GREEN = _RED = _YELLOW = _CYAN = _BOLD = _NC = ""

PASS = f"{_GREEN}✓{_NC}"
FAIL = f"{_RED}✗{_NC}"
WARN = f"{_YELLOW}⚠{_NC}"
INFO = f"{_CYAN}ℹ{_NC}"

# Force line-buffered output so launcher scripts see progress in real time
print = functools.partial(print, flush=True)


def banner(title: str) -> None:
    bar = "═" * 70
    print(f"\n{bar}")
    print(f"{_BOLD}{title}{_NC}")
    print(f"{bar}")


def step(name: str) -> None:
    print(f"\n{INFO} {_BOLD}{name}{_NC}")


def ok(msg: str, detail: str = "") -> None:
    print(f"  {PASS} {msg}" + (f"  ({detail})" if detail else ""))


def fail(msg: str, detail: str = "") -> None:
    print(f"  {FAIL} {msg}")
    if detail:
        for line in detail.splitlines():
            print(f"       {line}")


def warn(msg: str, detail: str = "") -> None:
    print(f"  {WARN} {msg}" + (f"  ({detail})" if detail else ""))


def info(msg: str) -> None:
    print(f"  {INFO} {msg}")


# ═══════════════════════════════════════════════════════════════
# Environment-variable configuration
# ═══════════════════════════════════════════════════════════════


class EnvConfig:
    """Configuration parsed from environment variables.

    All deployment case tests share the same env var schema so that
    launcher scripts only need to set the relevant subset.

    V3 additions:
        STOCKSTAT_DISPATCHER_URL  — Dispatcher URL for RemoteComputeBackend
        STOCKSTAT_DISPATCHER_ENABLED — "true" to enable Dispatcher plugin
        STOCKSTAT_TRANSPORT       — "in_process" / "http" (default: in_process)
    """

    def __init__(self) -> None:
        self.host: str = os.environ.get("STOCKSTAT_HOST", "localhost")
        self.port: int = int(os.environ.get("STOCKSTAT_PORT", "8000"))
        self.use_https: bool = os.environ.get("STOCKSTAT_USE_HTTPS", "").lower() in ("1", "true", "yes")
        self.proxy_enabled: bool = os.environ.get("STOCKSTAT_PROXY_ENABLED", "false").lower() == "true"
        self.proxy_url: str = os.environ.get("STOCKSTAT_PROXY_URL", "")
        # V3
        self.dispatcher_url: Optional[str] = os.environ.get("STOCKSTAT_DISPATCHER_URL") or None
        self.dispatcher_enabled: bool = os.environ.get("STOCKSTAT_DISPATCHER_ENABLED", "false").lower() == "true"
        self.transport: str = os.environ.get("STOCKSTAT_TRANSPORT", "in_process")
        # Test options
        self.skip_network: bool = os.environ.get("STOCKSTAT_SKIP_NETWORK", "false").lower() == "true"
        self.symbol: str = os.environ.get("STOCKSTAT_TEST_SYMBOL", "BTC/USDT")
        self.start_date: str = os.environ.get("STOCKSTAT_TEST_START", "2024-01-01")
        self.end_date: str = os.environ.get("STOCKSTAT_TEST_END", "2024-12-31")

    @property
    def base_url(self) -> str:
        scheme = "https" if self.use_https else "http"
        return f"{scheme}://{self.host}:{self.port}"

    def __repr__(self) -> str:
        return (
            f"EnvConfig(base_url={self.base_url!r}, "
            f"transport={self.transport!r}, "
            f"dispatcher_url={self.dispatcher_url!r})"
        )


# ═══════════════════════════════════════════════════════════════
# V3 assertion helpers
# ═══════════════════════════════════════════════════════════════


def assert_v3_compute_backend(client, expected_name: str = "local") -> None:
    """Assert that a client's compute_backend matches expected type."""
    backend = client.compute_backend
    actual = getattr(backend, "name", type(backend).__name__)
    if actual != expected_name:
        raise AssertionError(
            f"compute_backend.name mismatch: expected {expected_name!r}, got {actual!r}"
        )


def assert_cluster_info_shape(info: dict) -> None:
    """Assert that cluster_info() returns the expected top-level shape."""
    required_top = {"dispatcher", "workers", "stats"}
    missing = required_top - set(info.keys())
    if missing:
        raise AssertionError(f"cluster_info missing keys: {missing}")

    disp = info["dispatcher"]
    for k in ("id", "alias", "status"):
        if k not in disp:
            raise AssertionError(f"dispatcher missing key: {k!r}")

    if not isinstance(info["workers"], list):
        raise AssertionError(f"workers must be list, got {type(info['workers'])}")
    if not info["workers"]:
        raise AssertionError("workers list is empty")
    w = info["workers"][0]
    for k in ("worker_id", "alias", "status", "capabilities"):
        if k not in w:
            raise AssertionError(f"worker missing key: {k!r}")

    stats = info["stats"]
    for k in ("total_workers", "online_workers", "total_concurrency"):
        if k not in stats:
            raise AssertionError(f"stats missing key: {k!r}")


def assert_task_ref_completed(task_ref, timeout: float = 60.0) -> Any:
    """Wait for a TaskRef and return its result; raise on failure."""
    result = task_ref.wait(timeout=timeout)
    if task_ref.status != "completed":
        raise AssertionError(
            f"Task did not complete: status={task_ref.status}"
        )
    return result


# ═══════════════════════════════════════════════════════════════
# Sample strategy / data factories (no network)
# ═══════════════════════════════════════════════════════════════


def make_synthetic_data(n_bars: int = 100, seed: int = 42):
    """Build synthetic OHLCV data — no network required."""
    import pandas as pd
    import numpy as np
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="D", tz="UTC")
    rng = np.random.RandomState(seed)
    returns = rng.normal(0.001, 0.02, n_bars)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n_bars)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n_bars)))
    op = close * (1 + rng.normal(0, 0.003, n_bars))
    vol = rng.uniform(1e6, 5e6, n_bars)
    df = pd.DataFrame({
        "open": op, "high": high, "low": low, "close": close, "volume": vol,
    }, index=dates)
    return {"BTC/USDT": {"1d": df}}


def make_ma_cross_strategy():
    """A simple MA-cross strategy for backtest tests."""
    from stockstat.backtest import Strategy, Order, OrderSide, OrderType

    class MaCrossStrategy(Strategy):
        name = "ma_cross_v3"
        def __init__(self):
            super().__init__()
            self._bought = False
            self._bar_count = 0
        def on_bar(self, ctx):
            self._bar_count += 1
            if self._bar_count < 25:
                return
            t = ctx.now
            try:
                closes = ctx.data_feed.close_series("BTC/USDT", "1d")
                if t not in closes.index:
                    return
                idx = closes.index.get_loc(t)
                if idx < 20:
                    return
                ma5 = closes.iloc[max(0, idx-5):idx+1].mean()
                ma20 = closes.iloc[max(0, idx-20):idx+1].mean()
                pos = ctx.portfolio.get_position("BTC/USDT")
                if ma5 > ma20 and pos.qty == 0 and not self._bought:
                    ctx.broker.submit(Order(
                        symbol="BTC/USDT", side=OrderSide.BUY,
                        order_type=OrderType.MARKET, qty=1.0, tag="entry",
                    ))
                    self._bought = True
                elif ma5 < ma20 and self._bought:
                    ctx.broker.submit(Order(
                        symbol="BTC/USDT", side=OrderSide.SELL,
                        order_type=OrderType.MARKET, qty=1.0, tag="exit",
                    ))
                    self._bought = False
            except Exception:
                pass

    return MaCrossStrategy


def encode_strategy(strategy) -> str:
    """cloudpickle-encode a strategy, return 'cloudpickle:base64...' ref."""
    import base64
    from stockstat._core.codec import CloudpickleCodec
    raw = CloudpickleCodec().encode(strategy)
    return "cloudpickle:" + base64.b64encode(raw).decode("ascii")


# ═══════════════════════════════════════════════════════════════
# Test runner — runs a sequence of step functions, returns exit code
# ═══════════════════════════════════════════════════════════════


class TestRunner:
    """Run a list of step callables; collect pass/fail counts.

    Each step is a callable ``(env: EnvConfig) -> None`` that either
    returns normally (pass) or raises (fail). Steps are independent —
    failure in one does not stop subsequent steps unless critical.
    """

    def __init__(self, env: EnvConfig) -> None:
        self.env = env
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self._failures: list[str] = []

    def run(self, name: str, fn, *, critical: bool = False) -> bool:
        step(name)
        t0 = time.perf_counter()
        try:
            fn(self.env)
            elapsed = (time.perf_counter() - t0) * 1000
            ok(f"completed ({elapsed:.0f} ms)")
            self.passed += 1
            return True
        except KeyboardInterrupt:
            raise
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            tb = traceback.format_exc()
            fail(f"{type(e).__name__}: {e}", tb)
            self.failed += 1
            self._failures.append(f"{name}: {e}")
            if critical:
                self.summarize()
                sys.exit(1)
            return False

    def skip(self, name: str, reason: str = "") -> None:
        step(name)
        warn(f"skipped — {reason}")
        self.skipped += 1

    def summarize(self) -> int:
        banner("Summary")
        total = self.passed + self.failed + self.skipped
        print(f"  Passed:  {self.passed}/{total}")
        print(f"  Failed:  {self.failed}/{total}")
        print(f"  Skipped: {self.skipped}/{total}")
        if self._failures:
            print(f"\n  Failures:")
            for f in self._failures:
                print(f"    - {f}")
        print()
        return 0 if self.failed == 0 else 1
