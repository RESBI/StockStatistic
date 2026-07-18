#!/usr/bin/env python3
"""StockStat 前后端通讯性能测试

测量指标：
  1. 健康检查延迟 (RTT)
  2. 空查询延迟 (404 响应时间)
  3. 数据查询延迟 vs 数据量 (1 / 10 / 100 / 500 / 1000 行)
  4. 传输速度 (bytes/s)
  5. 采集 (ingest) 延迟
  6. 连续请求抖动 (jitter)

用法：
  python test_perf.py                          # 默认 localhost:8000
  python test_perf.py --host 192.168.1.100     # 远程后端
  python test_perf.py --host 192.168.1.100 --rounds 50
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import os

# ── 解析参数 ──
parser = argparse.ArgumentParser(description="StockStat backend communication performance test")
parser.add_argument("--host", default="localhost", help="Backend host")
parser.add_argument("--port", type=int, default=8000, help="Backend port")
parser.add_argument("--https", action="store_true", help="Use HTTPS")
parser.add_argument("--rounds", type=int, default=20, help="Number of rounds for latency test (default: 20)")
parser.add_argument("--symbol", default="BTC/USDT", help="Symbol to test with (must be pre-ingested)")
parser.add_argument("--timeframe", default="1h", help="Timeframe to test with")
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

def fmt_size(n):
    if n < 1024: return f"{n} B"
    if n < 1024*1024: return f"{n/1024:.1f} KB"
    return f"{n/1024/1024:.2f} MB"

def fmt_speed(bps):
    if bps < 1024: return f"{bps:.0f} B/s"
    if bps < 1024*1024: return f"{bps/1024:.1f} KB/s"
    return f"{bps/1024/1024:.2f} MB/s"

def print_stats(name, s, extra=""):
    print(f"  {name:30s}  min={fmt_ms(s['min']):>10s}  mean={fmt_ms(s['mean']):>10s}  "
          f"median={fmt_ms(s['median']):>10s}  p95={fmt_ms(s['p95']):>10s}  "
          f"max={fmt_ms(s['max']):>10s}  {extra}")

SEP = "─" * 100

# ═══════════════════════════════════════════════════════
print(f"\n{'═'*100}")
print(f"StockStat 通讯性能测试")
print(f"目标: {BASE_URL}")
print(f"轮次: {ROUNDS}")
print(f"标的: {args.symbol} ({args.timeframe})")
print(f"{'═'*100}")

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

# 确保有数据
try:
    test_df = client.ohlcv(args.symbol, timeframe=args.timeframe, limit=1)
    if test_df.empty:
        print(f"  ⚠ 标的 {args.symbol} 无数据，尝试下载...")
        client.ingest(args.symbol, source="binance" if "/" in args.symbol else "yfinance",
                       start="2024-01-01", end="2024-12-31", timeframe=args.timeframe)
except Exception as e:
    print(f"  ⚠ 无法获取 {args.symbol} 数据: {e}")
    print(f"  请先下载: client.ingest('{args.symbol}', ...)")
    sys.exit(1)

# 获取总行数以确定可用的 limit 范围
total_rows = len(client.ohlcv(args.symbol, timeframe=args.timeframe))
test_limits = [l for l in [1, 10, 100, 500, 1000, 5000, 10000] if l <= total_rows]
if not test_limits:
    test_limits = [1]

print(f"\n  {'查询':30s}  {'延迟统计':>60s}  {'大小':>10s}  {'速度':>12s}")
print(f"  {'':30s}  {'min':>10s} {'mean':>10s} {'median':>10s} {'p95':>10s} {'max':>10s}")

for limit in test_limits:
    # 预热
    try:
        client.ohlcv(args.symbol, timeframe=args.timeframe, limit=limit)
    except:
        break

    # 测量
    n_rounds = min(ROUNDS, 5 if limit >= 5000 else (10 if limit >= 1000 else ROUNDS))
    sizes = []
    latencies = []
    for _ in range(n_rounds):
        t0 = time.perf_counter()
        df = client.ohlcv(args.symbol, timeframe=args.timeframe, limit=limit)
        latencies.append((time.perf_counter() - t0) * 1000)
        # 估算传输大小 (JSON 序列化)
        sizes.append(len(json.dumps(df.reset_index().to_dict(orient="records"),
                                     default=str)))

    s = stats(latencies)
    avg_size = statistics.mean(sizes)
    avg_latency_s = s["mean"] / 1000
    speed = avg_size / avg_latency_s if avg_latency_s > 0 else 0

    print(f"  limit={limit:<23d}  {fmt_ms(s['min']):>10s} {fmt_ms(s['mean']):>10s} "
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
# 6. 采集延迟 (ingest) — 只测一次（避免重复写入）
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

# 抖动分布
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

# ═══════════════════════════════════════════════════════
# 总结
# ═══════════════════════════════════════════════════════
print(f"\n{'═'*100}")
print(f"测试总结")
print(f"{'═'*100}")
print(f"  目标:          {BASE_URL}")
print(f"  健康检查 RTT:  {fmt_ms(s['mean'])} (±{fmt_ms(s['stdev'])})")
print(f"  原始 HTTP RTT: {fmt_ms(s_raw['mean'])} (±{fmt_ms(s_raw['stdev'])})")
print(f"  查询延迟 (100行): {fmt_ms(stats(lat_asc)['mean'])}")
print(f"  抖动 (50次):   {fmt_ms(s_j['stdev'])}")
print(f"  抖动占比:      {s_j['stdev']/s_j['mean']*100:.1f}%")
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
