#!/usr/bin/env python3
"""StockStat V3 前后端通讯性能测试

测量指标：
  1. 健康检查延迟 (RTT)
  2. 空查询延迟 (404 响应时间)
  3. 数据查询延迟 vs 数据量 (1 / 10 / 100 / 500 / 1000 行)
  4. 传输速度 (bytes/s)
  5. 采集 (ingest) 延迟
  6. 连续请求抖动 (jitter)
  7. 原始 HTTP 延迟 (httpx 直连)
  8. V3: LocalComputeBackend vs 直调 BacktestEngine 开销
  9. V3: TaskSpec 提交 + 等待的总开销
 10. V3: cloudpickle 编码策略的耗时
 11. V3: Envelope 编解码开销 (JSON vs Msgpack)
 12. V3: cluster_info() 调用开销

用法：
  python test_perf.py                          # 默认 localhost:8000
  python test_perf.py --host 192.168.1.100     # 远程后端
  python test_perf.py --host 192.168.1.100 --rounds 50
  python test_perf.py --skip-v3                # 跳过 V3 步骤
"""
from __future__ import annotations

import argparse
import base64
import json
import statistics
import sys
import time
import os

# ── 解析参数 ──
parser = argparse.ArgumentParser(description="StockStat V3 backend communication performance test")
parser.add_argument("--host", default="localhost", help="Backend host")
parser.add_argument("--port", type=int, default=8000, help="Backend port")
parser.add_argument("--https", action="store_true", help="Use HTTPS")
parser.add_argument("--rounds", type=int, default=20, help="Number of rounds for latency test (default: 20)")
parser.add_argument("--symbol", default="BTC/USDT", help="Symbol to test with (must be pre-ingested)")
parser.add_argument("--timeframe", default="1h", help="Timeframe to test with")
parser.add_argument("--skip-v3", action="store_true", help="Skip V3-specific steps")
args = parser.parse_args()

# ── 导入 ──
try:
    from stockstat import StockStatClient
except ImportError:
    frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
    sys.path.insert(0, frontend_path)
    from stockstat import StockStatClient

import httpx
import functools

# Force flush print
print = functools.partial(print, flush=True)

BASE_URL = f"{'https' if args.https else 'http'}://{args.host}:{args.port}"
client = StockStatClient(host=args.host, port=args.port, use_https=args.https)
ROUNDS = args.rounds

# ── 工具函数 ──
def measure(func, n=ROUNDS):
    """执行 n 次并返回 (latencies_ms, results)"""
    latencies = []
    results = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = func()
        latencies.append((time.perf_counter() - t0) * 1000)
        results.append(r)
    return latencies, results

def stats(latencies):
    """返回统计摘要"""
    return {
        "min": min(latencies),
        "max": max(latencies),
        "mean": statistics.mean(latencies),
        "median": statistics.median(latencies),
        "stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        "p95": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies),
    }

def fmt_ms(v):
    return f"{v:.1f} ms"

def fmt_us(v):
    return f"{v:.1f} μs"

def fmt_size(n):
    if n < 1024: return f"{n} B"
    if n < 1024*1024: return f"{n/1024:.1f} KB"
    return f"{n/1024/1024:.2f} MB"

def fmt_speed(bps):
    if bps < 1024: return f"{bps:.0f} B/s"
    if bps < 1024*1024: return f"{bps/1024:.1f} KB/s"
    return f"{bps/1024/1024:.2f} MB/s"

def print_stats(name, s, extra=""):
    print(f"  {name:40s}  min={fmt_ms(s['min']):>10s}  mean={fmt_ms(s['mean']):>10s}  "
          f"median={fmt_ms(s['median']):>10s}  p95={fmt_ms(s['p95']):>10s}  "
          f"max={fmt_ms(s['max']):>10s}  {extra}")

SEP = "─" * 110
V3_TAG = "\033[95m[V3]\033[0m"

# ═══════════════════════════════════════════════════════
print(f"\n{'═'*110}")
print(f"StockStat V3 通讯性能测试")
print(f"目标: {BASE_URL}")
print(f"轮次: {ROUNDS}")
print(f"标的: {args.symbol} ({args.timeframe})")
print(f"V3 步骤: {'跳过' if args.skip_v3 else '启用'}")
print(f"{'═'*110}")

# ═══════════════════════════════════════════════════════
# 1. 健康检查延迟 (RTT)
# ═══════════════════════════════════════════════════════
print(f"\n{SEP}")
print("1. 健康检查延迟 (Health Check RTT)")
print(SEP)

latencies, _ = measure(lambda: client.health())
s = stats(latencies)
jitter = s["stdev"]
print_stats("GET /api/v1/health", s, f"jitter={fmt_ms(jitter)}")

# ═══════════════════════════════════════════════════════
# 2. 空查询延迟 (404 响应)
# ═══════════════════════════════════════════════════════
print(f"\n{SEP}")
print("2. 空查询延迟 (404 — 不存在的标的)")
print(SEP)

def query_404():
    try:
        client.ohlcv("__NONEXISTENT__", limit=1)
    except (KeyError, Exception):
        pass

latencies_404, _ = measure(query_404)
s404 = stats(latencies_404)
print_stats("GET /api/v1/ohlcv (404)", s404)

# ═══════════════════════════════════════════════════════
# 3. 数据查询延迟 vs 数据量
# ═══════════════════════════════════════════════════════
print(f"\n{SEP}")
print(f"3. 数据查询延迟 vs 数据量 ({args.symbol} {args.timeframe})")
print(SEP)

try:
    test_df = client.ohlcv(args.symbol, timeframe=args.timeframe, limit=1)
    if test_df.empty:
        print(f"  ⚠ 标的 {args.symbol} 无数据，尝试下载...")
        client.ingest(args.symbol, source="binance" if "/" in args.symbol else "yfinance",
                       start="2024-01-01", end="2024-12-31", timeframe=args.timeframe)
except Exception as e:
    print(f"  ⚠ 无法获取 {args.symbol} 数据: {e}")
    print(f"  请先下载: client.ingest('{args.symbol}', ...)")
    if not args.skip_v3:
        print(f"  V3 步骤将使用合成数据进行本地性能测试")
    sys.exit(1) if not args.skip_v3 else None

total_rows = len(client.ohlcv(args.symbol, timeframe=args.timeframe))
test_limits = [l for l in [1, 10, 100, 500, 1000, 5000, 10000] if l <= total_rows]
if not test_limits:
    test_limits = [1]

print(f"\n  {'查询':40s}  {'延迟统计':>60s}  {'大小':>10s}  {'速度':>12s}")
print(f"  {'':40s}  {'min':>10s} {'mean':>10s} {'median':>10s} {'p95':>10s} {'max':>10s}")

for limit in test_limits:
    try:
        client.ohlcv(args.symbol, timeframe=args.timeframe, limit=limit)
    except:
        break

    n_rounds = min(ROUNDS, 5 if limit >= 5000 else (10 if limit >= 1000 else ROUNDS))
    sizes = []
    latencies = []
    for _ in range(n_rounds):
        t0 = time.perf_counter()
        df = client.ohlcv(args.symbol, timeframe=args.timeframe, limit=limit)
        latencies.append((time.perf_counter() - t0) * 1000)
        sizes.append(len(json.dumps(df.reset_index().to_dict(orient="records"),
                                     default=str)))

    s = stats(latencies)
    avg_size = statistics.mean(sizes)
    avg_latency_s = s["mean"] / 1000
    speed = avg_size / avg_latency_s if avg_latency_s > 0 else 0

    print(f"  limit={limit:<33d}  {fmt_ms(s['min']):>10s} {fmt_ms(s['mean']):>10s} "
          f"{fmt_ms(s['median']):>10s} {fmt_ms(s['p95']):>10s} {fmt_ms(s['max']):>10s}  "
          f"{fmt_size(avg_size):>10s}  {fmt_speed(speed):>12s}")

# ═══════════════════════════════════════════════════════
# 4. order 参数对比 (asc vs desc)
# ═══════════════════════════════════════════════════════
print(f"\n{SEP}")
print(f"4. order 参数对比 (asc vs desc, limit=100)")
print(SEP)

lat_asc, _ = measure(
    lambda: client.ohlcv(args.symbol, timeframe=args.timeframe, limit=100, order="asc"),
    n=min(ROUNDS, 15)
)
lat_desc, _ = measure(
    lambda: client.ohlcv(args.symbol, timeframe=args.timeframe, limit=100, order="desc"),
    n=min(ROUNDS, 15)
)
s_asc = stats(lat_asc)
s_desc = stats(lat_desc)
print_stats("order=asc  (最旧 100 行)", s_asc)
print_stats("order=desc (最近 100 行)", s_desc)

# ═══════════════════════════════════════════════════════
# 5. symbols 列表查询
# ═══════════════════════════════════════════════════════
print(f"\n{SEP}")
print("5. 符号列表查询 (GET /api/v1/symbols)")
print(SEP)

lat_syms, _ = measure(lambda: client.symbols(), n=min(ROUNDS, 10))
s_syms = stats(lat_syms)
print_stats("GET /api/v1/symbols", s_syms)

# ═══════════════════════════════════════════════════════
# 6. 采集延迟 (ingest) — 只测一次
# ═══════════════════════════════════════════════════════
print(f"\n{SEP}")
print("6. 采集延迟 (POST /api/v1/ingest) — 单次测试")
print(SEP)

try:
    t0 = time.perf_counter()
    result = client.ingest(
        args.symbol,
        source="binance" if "/" in args.symbol else "yfinance",
        start="2024-06-01", end="2024-06-07",
        timeframe=args.timeframe
    )
    ingest_ms = (time.perf_counter() - t0) * 1000
    print(f"  ingest {args.symbol} 7天 {args.timeframe}: {result['ingested']} 行, {fmt_ms(ingest_ms)}")
    print(f"  (含网络下载 + 标准化 + 存储，非纯通讯延迟)")
except Exception as e:
    print(f"  ⚠ ingest 测试跳过: {e}")
    print(f"  (如需测试 ingest 延迟，请确保数据源可访问或配置代理)")

# ═══════════════════════════════════════════════════════
# 7. 连续请求抖动 (Jitter) — 50 次快速查询
# ═══════════════════════════════════════════════════════
print(f"\n{SEP}")
print(f"7. 连续请求抖动 (50 次快速查询, limit=10)")
print(SEP)

JITTER_ROUNDS = 50
latencies_j = []
for _ in range(JITTER_ROUNDS):
    t0 = time.perf_counter()
    client.ohlcv(args.symbol, timeframe=args.timeframe, limit=10)
    latencies_j.append((time.perf_counter() - t0) * 1000)

s_j = stats(latencies_j)
print_stats(f"50 次连续查询", s_j, f"jitter={fmt_ms(s_j['stdev'])}")

buckets = {"<5ms": 0, "5-10ms": 0, "10-25ms": 0, "25-50ms": 0, "50-100ms": 0, ">100ms": 0}
for lat in latencies_j:
    if lat < 5: buckets["<5ms"] += 1
    elif lat < 10: buckets["5-10ms"] += 1
    elif lat < 25: buckets["10-25ms"] += 1
    elif lat < 50: buckets["25-50ms"] += 1
    elif lat < 100: buckets["50-100ms"] += 1
    else: buckets[">100ms"] += 1

print(f"\n  延迟分布:")
for bucket, count in buckets.items():
    pct = count / JITTER_ROUNDS * 100
    bar = "█" * int(pct / 2)
    print(f"    {bucket:>10s}: {count:3d} ({pct:5.1f}%) {bar}")

# ═══════════════════════════════════════════════════════
# 8. 原始 HTTP 延迟 (绕过 DataClient，直接 httpx)
# ═══════════════════════════════════════════════════════
print(f"\n{SEP}")
print("8. 原始 HTTP 延迟 (httpx 直连，绕过前端库)")
print(SEP)

latencies_raw = []
for _ in range(min(ROUNDS, 20)):
    t0 = time.perf_counter()
    r = httpx.get(f"{BASE_URL}/api/v1/health", timeout=10)
    latencies_raw.append((time.perf_counter() - t0) * 1000)
s_raw = stats(latencies_raw)
print_stats("httpx.get /api/v1/health", s_raw, "(原始 TCP+HTTP 开销)")

# ═══════════════════════════════════════════════════════════════════════
# V3 性能测试（仅在 --skip-v3 未指定时执行）
# ═══════════════════════════════════════════════════════════════════════

if not args.skip_v3:
    print(f"\n{'═'*110}")
    print(f"{V3_TAG} V3 性能测试（本地 LocalComputeBackend）")
    print(f"{'═'*110}")

    # ── 准备合成数据（避免依赖网络）──
    import pandas as pd
    import numpy as np
    dates = pd.date_range("2024-01-01", periods=200, freq="D", tz="UTC")
    rng = np.random.RandomState(42)
    returns = rng.normal(0.001, 0.02, 200)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.005, 200)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, 200)))
    op = close * (1 + rng.normal(0, 0.003, 200))
    vol = rng.uniform(1e6, 5e6, 200)
    df_synthetic = pd.DataFrame({
        "open": op, "high": high, "low": low, "close": close, "volume": vol,
    }, index=dates)
    data = {"BTC/USDT": {"1d": df_synthetic}}

    from stockstat.backtest import BacktestEngine, Strategy, Order, OrderSide, OrderType
    from stockstat.compute.engine import ComputeEngine
    from stockstat._core.compute import LocalComputeBackend
    from stockstat._core.codec import CloudpickleCodec
    from stockstat._core.contracts.task import TaskSpec, DataSpec, ComputeSpec, new_task_id
    from stockstat._core.protocol import Envelope, Headers

    class MaStrategy(Strategy):
        name = "perf_test"
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
                        order_type=OrderType.MARKET, qty=1.0,
                    ))
                    self._bought = True
                elif ma5 < ma20 and self._bought:
                    ctx.broker.submit(Order(
                        symbol="BTC/USDT", side=OrderSide.SELL,
                        order_type=OrderType.MARKET, qty=1.0,
                    ))
                    self._bought = False
            except Exception:
                pass

    # ── 9. V3: LocalComputeBackend vs 直调 BacktestEngine 开销 ──
    print(f"\n{SEP}")
    print(f"{V3_TAG} 9. LocalComputeBackend vs 直调 BacktestEngine 开销")
    print(SEP)

    def run_direct():
        engine = BacktestEngine(
            data=data, strategy=MaStrategy(),
            initial_cash=10000,
            compute_engine=ComputeEngine(client=None),
        )
        return engine.run()

    lat_direct, _ = measure(run_direct, n=10)
    s_direct = stats(lat_direct)
    print_stats("直调 BacktestEngine (v2.1 路径)", s_direct)

    # V3 路径：构建 TaskSpec + submit + wait
    strategy_ref = "cloudpickle:" + base64.b64encode(
        CloudpickleCodec().encode(MaStrategy())
    ).decode("ascii")

    backend = LocalComputeBackend()
    class StubClient:
        def ohlcv(self, symbol, **kw):
            return data[symbol][kw.get("timeframe", "1d")]
    backend._client = StubClient()

    def run_v3():
        spec = TaskSpec(
            task_id=new_task_id(),
            data_spec=DataSpec(symbols=["BTC/USDT"], timeframe="1d"),
            compute_spec=ComputeSpec(
                task_type="backtest", strategy_ref=strategy_ref, initial_cash=10000,
            ),
        )
        return backend.submit(spec).wait(timeout=30)

    lat_v3, _ = measure(run_v3, n=10)
    s_v3 = stats(lat_v3)
    print_stats("V3 TaskSpec 提交+等待", s_v3)

    overhead_ms = s_v3["mean"] - s_direct["mean"]
    overhead_pct = overhead_ms / s_direct["mean"] * 100 if s_direct["mean"] > 0 else 0
    print(f"\n  V3 开销: +{overhead_ms:.1f} ms ({overhead_pct:+.1f}%)")
    print(f"  (开销来自 TaskSpec 构建 + cloudpickle 解码 + 后台线程调度)")

    # ── 10. V3: cloudpickle 编码策略耗时 ──
    print(f"\n{SEP}")
    print(f"{V3_TAG} 10. cloudpickle 编码策略耗时")
    print(SEP)

    strat = MaStrategy()
    lat_encode = []
    for _ in range(20):
        t0 = time.perf_counter()
        CloudpickleCodec().encode(strat)
        lat_encode.append((time.perf_counter() - t0) * 1_000_000)  # μs
    s_enc = stats(lat_encode)
    print(f"  cloudpickle.dumps(strategy):  mean={fmt_us(s_enc['mean'])}  "
          f"min={fmt_us(s_enc['min'])}  max={fmt_us(s_enc['max'])}")

    raw_bytes = CloudpickleCodec().encode(strat)
    print(f"  编码大小: {fmt_size(len(raw_bytes))}")

    lat_decode = []
    for _ in range(20):
        t0 = time.perf_counter()
        CloudpickleCodec().decode(raw_bytes)
        lat_decode.append((time.perf_counter() - t0) * 1_000_000)
    s_dec = stats(lat_decode)
    print(f"  cloudpickle.loads(strategy):  mean={fmt_us(s_dec['mean'])}  "
          f"min={fmt_us(s_dec['min'])}  max={fmt_us(s_dec['max'])}")

    # ── 11. V3: Envelope 编解码开销 ──
    print(f"\n{SEP}")
    print(f"{V3_TAG} 11. Envelope 编解码开销 (JSON vs Msgpack)")
    print(SEP)

    env_json = Envelope(
        type="task.submit",
        headers=Headers(encoding="json", trace_id="perf-test"),
        payload={"task_id": "t1", "symbols": ["BTC/USDT"], "n": 42, "list": list(range(20))},
    )
    lat_json_enc = []
    for _ in range(50):
        t0 = time.perf_counter()
        env_json.encode()
        lat_json_enc.append((time.perf_counter() - t0) * 1_000_000)
    s_json_enc = stats(lat_json_enc)
    json_size = len(env_json.encode())
    print(f"  Envelope.encode (JSON):        mean={fmt_us(s_json_enc['mean'])}  "
          f"size={fmt_size(json_size)}")

    raw_json = env_json.encode()
    lat_json_dec = []
    for _ in range(50):
        t0 = time.perf_counter()
        Envelope.decode(raw_json)
        lat_json_dec.append((time.perf_counter() - t0) * 1_000_000)
    s_json_dec = stats(lat_json_dec)
    print(f"  Envelope.decode (JSON):        mean={fmt_us(s_json_dec['mean'])}")

    try:
        import msgpack  # noqa: F401
        env_mp = Envelope(
            type="task.submit",
            headers=Headers(encoding="msgpack", trace_id="perf-test"),
            payload=env_json.payload,
        )
        lat_mp_enc = []
        for _ in range(50):
            t0 = time.perf_counter()
            env_mp.encode()
            lat_mp_enc.append((time.perf_counter() - t0) * 1_000_000)
        s_mp_enc = stats(lat_mp_enc)
        mp_size = len(env_mp.encode())
        print(f"  Envelope.encode (Msgpack):     mean={fmt_us(s_mp_enc['mean'])}  "
              f"size={fmt_size(mp_size)}")

        raw_mp = env_mp.encode()
        lat_mp_dec = []
        for _ in range(50):
            t0 = time.perf_counter()
            Envelope.decode(raw_mp)
            lat_mp_dec.append((time.perf_counter() - t0) * 1_000_000)
        s_mp_dec = stats(lat_mp_dec)
        print(f"  Envelope.decode (Msgpack):     mean={fmt_us(s_mp_dec['mean'])}")

        size_reduction = (1 - mp_size / json_size) * 100
        print(f"\n  Msgpack vs JSON: 体积减少 {size_reduction:.1f}% "
              f"({fmt_size(json_size)} -> {fmt_size(mp_size)})")
    except ImportError:
        print(f"  {V3_TAG} msgpack 未安装，跳过 Msgpack 测试")

    # ── 12. V3: cluster_info() 调用开销 ──
    print(f"\n{SEP}")
    print(f"{V3_TAG} 12. cluster_info() 调用开销")
    print(SEP)

    lat_ci, _ = measure(lambda: client.compute.cluster_info(), n=20)
    s_ci = stats(lat_ci)
    print_stats("client.compute.cluster_info()", s_ci)

# ═══════════════════════════════════════════════════════
# 总结
# ═══════════════════════════════════════════════════════
print(f"\n{'═'*110}")
print(f"测试总结")
print(f"{'═'*110}")
print(f"  目标:          {BASE_URL}")
print(f"  健康检查 RTT:  {fmt_ms(s['mean'])} (±{fmt_ms(s['stdev'])})")
print(f"  原始 HTTP RTT: {fmt_ms(s_raw['mean'])} (±{fmt_ms(s_raw['stdev'])})")
print(f"  查询延迟 (100行): {fmt_ms(stats(lat_asc)['mean'])}")
print(f"  抖动 (50次):   {fmt_ms(s_j['stdev'])}")
print(f"  抖动占比:      {s_j['stdev']/s_j['mean']*100:.1f}%")
if not args.skip_v3:
    print(f"  V3 开销:       +{overhead_ms:.1f} ms ({overhead_pct:+.1f}%)")
    print(f"  cloudpickle 编码: {fmt_us(s_enc['mean'])}")
    print(f"  Envelope JSON 编码: {fmt_us(s_json_enc['mean'])}")
print()

if s["mean"] < 10:
    print("  评估: 🟢 延迟极低，适合本地开发")
elif s["mean"] < 50:
    print("  评估: 🟡 延迟正常，局域网典型水平")
elif s["mean"] < 200:
    print("  评估: 🟠 延迟较高，跨城/跨网段连接")
else:
    print("  评估: 🔴 延迟很高，建议检查网络或使用更近的后端")

print()
