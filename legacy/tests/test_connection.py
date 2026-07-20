#!/usr/bin/env python3
"""StockStat V3 远程后端连接通路测试

完整测试流程（V3 适配版）：
  1. 健康检查
  2. 下载标的数据（AAPL + BTC/USDT）
  3. 查询数据并验证
  4. 计算指标（MA / RSI / 布林带）
  5. DSL 查询
  6. 回测（双均线策略）—— v2.1 同步路径
  7. 回测结果可视化
  8. V3 ComputeBackend 检查（cluster_info / 默认 LocalComputeBackend）
  9. V3 compute.remote('backtest') 异步提交
 10. V3 compute.remote('indicator') 远程指标

用法：
  python test_connection.py                          # 默认 localhost:8000
  python test_connection.py --host 192.168.1.100     # 指定远程后端
  python test_connection.py --host 192.168.1.100 --port 9000
  python test_connection.py --skip-v3                # 跳过 V3 新增步骤
"""
from __future__ import annotations

import argparse
import base64
import sys
import time
import traceback

# ── 解析命令行参数 ──
parser = argparse.ArgumentParser(description="StockStat V3 remote backend connection test")
parser.add_argument("--host", default="localhost", help="Backend host (default: localhost)")
parser.add_argument("--port", type=int, default=8000, help="Backend port (default: 8000)")
parser.add_argument("--https", action="store_true", help="Use HTTPS")
parser.add_argument("--skip-v3", action="store_true", help="Skip V3-specific steps")
args = parser.parse_args()

# ── 导入前端库 ──
try:
    from stockstat import StockStatClient
except ImportError:
    import os
    frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
    sys.path.insert(0, frontend_path)
    from stockstat import StockStatClient

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[96mℹ\033[0m"
V3_TAG = "\033[95m[V3]\033[0m"


def step(name: str):
    print(f"\n{INFO} {name}")


def ok(msg: str):
    print(f"  {PASS} {msg}")


def fail(msg: str, detail: str = ""):
    print(f"  {FAIL} {msg}")
    if detail:
        print(f"       {detail}")


def v3_step(name: str):
    print(f"\n{V3_TAG} {INFO} {name}")


# ═══════════════════════════════════════════════════════
#  1. 建立连接 + 健康检查
# ═══════════════════════════════════════════════════════
step("1. 连接后端 + 健康检查")
print(f"   目标: {'https' if args.https else 'http'}://{args.host}:{args.port}")

client = StockStatClient(host=args.host, port=args.port, use_https=args.https)
try:
    t0 = time.perf_counter()
    healthy = client.health()
    latency_ms = (time.perf_counter() - t0) * 1000
    if healthy:
        ok(f"后端在线 (健康检查延迟: {latency_ms:.1f} ms)")
    else:
        fail("后端健康检查返回 False")
        sys.exit(1)
except Exception as e:
    fail(f"无法连接后端: {e}")
    print(f"\n   请确认后端已启动: stockstat serve --host 0.0.0.0 --port {args.port}")
    sys.exit(1)

try:
    sources = client.sources()
    ok(f"可用数据源: {[s['name'] for s in sources]}")
except Exception as e:
    fail(f"获取数据源列表失败: {e}")


# ═══════════════════════════════════════════════════════
#  2. 下载标的数据
# ═══════════════════════════════════════════════════════
step("2. 下载标的数据 (ingest)")

try:
    t0 = time.perf_counter()
    result = client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
    ingest_ms = (time.perf_counter() - t0) * 1000
    ok(f"AAPL 日线: {result['ingested']} 行 (耗时 {ingest_ms:.0f} ms)")
except Exception as e:
    fail(f"AAPL 采集失败: {e}")
    print("       (如果在中国大陆，可能需要配置代理)")

try:
    t0 = time.perf_counter()
    result = client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
    ingest_ms = (time.perf_counter() - t0) * 1000
    ok(f"BTC/USDT 日线: {result['ingested']} 行 (耗时 {ingest_ms:.0f} ms)")
except Exception as e:
    fail(f"BTC/USDT 采集失败: {e}")

try:
    result = client.ingest("ETH/USDT", source="binance", start="2024-01-01", end="2024-12-31")
    ok(f"ETH/USDT 日线: {result['ingested']} 行")
except Exception as e:
    fail(f"ETH/USDT 采集失败: {e}")


# ═══════════════════════════════════════════════════════
#  3. 查询数据
# ═══════════════════════════════════════════════════════
step("3. 查询数据 (ohlcv)")

btc = None
try:
    t0 = time.perf_counter()
    aapl = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d", limit=5)
    query_ms = (time.perf_counter() - t0) * 1000
    if len(aapl) > 0:
        ok(f"AAPL 查询: {len(aapl)} 行 (延迟 {query_ms:.1f} ms)")
        print(f"       最新收盘: {aapl['close'].iloc[-1]:.2f}  ({aapl.index[-1].date()})")
    else:
        fail("AAPL 查询返回空数据")
except Exception as e:
    fail(f"AAPL 查询失败: {e}")

try:
    btc = client.ohlcv("BTC/USDT", start="2024-01-01", timeframe="1d")
    ok(f"BTC/USDT 查询: {len(btc)} 行")
    print(f"       最新收盘: {btc['close'].iloc[-1]:.2f}")
except Exception as e:
    fail(f"BTC/USDT 查询失败: {e}")

try:
    recent = client.ohlcv("BTC/USDT", limit=10, order="desc")
    ok(f"双向分页 (order=desc): 最近 {len(recent)} 根")
    print(f"       日期范围: {recent.index[0].date()} ~ {recent.index[-1].date()}")
except Exception as e:
    fail(f"双向分页查询失败: {e}")

try:
    symbols = client.symbols()
    ok(f"已注册标的: {len(symbols)} 个")
    for s in symbols[:5]:
        print(f"       {s['unified_symbol']:15s} {s['asset_type']:8s} {s['sources']}")
except Exception as e:
    fail(f"符号列表失败: {e}")


# ═══════════════════════════════════════════════════════
#  4. 计算指标
# ═══════════════════════════════════════════════════════
step("4. 计算指标 (compute)")

if btc is not None and len(btc) > 0:
    try:
        ma20 = client.compute.ma(btc.close, window=20)
        ok(f"MA(20): {ma20.iloc[-1]:.2f}")
    except Exception as e:
        fail(f"MA 计算失败: {e}")

    try:
        rsi = client.compute.rsi(btc.close, window=14)
        ok(f"RSI(14): {rsi.iloc[-1]:.2f}  (超买天数: {(rsi > 70).sum()}, 超卖天数: {(rsi < 30).sum()})")
    except Exception as e:
        fail(f"RSI 计算失败: {e}")

    try:
        upper, mid, lower = client.compute.bollinger(btc.close, window=20, k=2.0)
        ok(f"布林带: 上轨 {upper.iloc[-1]:.2f} / 中轨 {mid.iloc[-1]:.2f} / 下轨 {lower.iloc[-1]:.2f}")
    except Exception as e:
        fail(f"布林带计算失败: {e}")

    try:
        sharpe = client.compute.sharpe(
            client.compute.returns(btc.close).dropna(),
            risk_free=0.02, annualize=True
        )
        ok(f"Sharpe 比率 (年化): {sharpe:.4f}")
    except Exception as e:
        fail(f"Sharpe 计算失败: {e}")

    try:
        dd = client.compute.max_drawdown(btc.close)
        ok(f"最大回撤: {dd*100:.2f}%")
    except Exception as e:
        fail(f"最大回撤计算失败: {e}")


# ═══════════════════════════════════════════════════════
#  5. DSL 查询
# ═══════════════════════════════════════════════════════
step("5. DSL 查询")

try:
    result = client.run_dsl('''
        SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
        FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
        LIMIT 5
    ''')
    ok(f"DSL 查询成功: {len(result)} 行")
    print(result[["close", "ma20", "rsi"]].tail(3).to_string())
except Exception as e:
    fail(f"DSL 查询失败: {e}")
    print("       (需要 pip install stockstat[dsl])")


# ═══════════════════════════════════════════════════════
#  6. 回测（v2.1 同步路径）
# ═══════════════════════════════════════════════════════
step("6. 回测 (双均线策略, v2.1 同步路径)")

from stockstat.backtest import BacktestEngine, strategy, Order, ZeroCost

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21:
        return
    ma5 = d.close.rolling(5).mean().iloc[-1]
    ma20 = d.close.rolling(20).mean().iloc[-1]
    pos = ctx.portfolio.get_position("BTC/USDT")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1, tag="entry"))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty, tag="exit"))

res = None
if btc is not None and len(btc) > 0:
    try:
        t0 = time.perf_counter()
        res = client.backtest(
            {"BTC/USDT": {"1d": btc}},
            ma_cross,
            initial_cash=10000,
            benchmark="BTC/USDT"
        )
        bt_ms = (time.perf_counter() - t0) * 1000
        metrics = res.metrics()
        ok(f"回测完成 (耗时 {bt_ms:.0f} ms)")
        print(f"       总收益:     {metrics['total_return']*100:.2f}%")
        print(f"       Sharpe:     {metrics['sharpe']:.4f}")
        print(f"       最大回撤:   {metrics['max_drawdown']*100:.2f}%")
        print(f"       交易次数:   {metrics['num_trades']}")
        print(f"       胜率:       {metrics['win_rate']*100:.1f}%")
    except Exception as e:
        fail(f"回测失败: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════
#  7. 回测可视化 (可选，需要 matplotlib)
# ═══════════════════════════════════════════════════════
step("7. 回测可视化 (可选)")

if res is not None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        res.render("equity_curve", path="test_equity.png")
        ok("资金曲线图: test_equity.png")

        res.render("dashboard", path="test_dashboard.png")
        ok("综合仪表盘: test_dashboard.png")

        import os
        for f in ["test_equity.png", "test_dashboard.png"]:
            if os.path.exists(f):
                print(f"       {f}: {os.path.getsize(f) / 1024:.0f} KB")
    except ImportError:
        print(f"  {INFO} matplotlib 未安装，跳过可视化 (pip install stockstat[matplotlib])")
    except Exception as e:
        fail(f"可视化失败: {e}")


# ═══════════════════════════════════════════════════════
#  8. V3: ComputeBackend 检查
# ═══════════════════════════════════════════════════════
if not args.skip_v3:
    v3_step("8. V3 ComputeBackend 检查 (默认 LocalComputeBackend)")

    try:
        from stockstat._core.compute import LocalComputeBackend
        backend = client.compute_backend
        if isinstance(backend, LocalComputeBackend):
            ok(f"默认 compute_backend = LocalComputeBackend (name={backend.name})")
        else:
            fail(f"compute_backend 类型异常: {type(backend).__name__}")
    except Exception as e:
        fail(f"V3 ComputeBackend 检查失败: {e}")

    try:
        info = client.compute.cluster_info()
        workers = info.get("workers", [])
        stats = info.get("stats", {})
        ok(f"cluster_info(): {stats.get('total_workers', 0)} workers, "
           f"{stats.get('online_workers', 0)} online")
        if workers:
            w = workers[0]
            print(f"       worker: id={w.get('worker_id')}, alias={w.get('alias')}, "
                  f"status={w.get('status')}")
            print(f"       capabilities: {w.get('capabilities', [])[:5]}...")
    except Exception as e:
        fail(f"cluster_info 失败: {e}")


# ═══════════════════════════════════════════════════════
#  9. V3: compute.remote('backtest') 异步提交
# ═══════════════════════════════════════════════════════
if not args.skip_v3 and btc is not None and len(btc) > 0:
    v3_step("9. V3 compute.remote('backtest') 异步提交")

    try:
        from stockstat._core.codec import CloudpickleCodec
        from stockstat._core.contracts.compute import TaskRef
        from stockstat.backtest import BacktestResult

        # cloudpickle 编码策略
        strategy_ref = "cloudpickle:" + base64.b64encode(
            CloudpickleCodec().encode(ma_cross)
        ).decode("ascii")

        # 注入 stub data client（复用已查询的 btc 数据，避免再次 HTTP 请求）
        class StubClient:
            def ohlcv(self, symbol, **kw):
                return btc
        client.compute_backend._client = StubClient()

        t0 = time.perf_counter()
        task = client.compute.remote(
            "backtest",
            symbols=["BTC/USDT"], timeframe="1d",
            strategy_ref=strategy_ref,
            initial_cash=10000,
            benchmark="BTC/USDT",
            timeout=120,
        )
        submit_ms = (time.perf_counter() - t0) * 1000
        ok(f"提交完成: task_id={task.id[:8]}..., status={task.status} ({submit_ms:.0f} ms)")

        t0 = time.perf_counter()
        v3_result = task.wait(timeout=120)
        wait_ms = (time.perf_counter() - t0) * 1000
        if isinstance(v3_result, BacktestResult):
            v3_metrics = v3_result.metrics()
            ok(f"V3 远程回测完成 (等待 {wait_ms:.0f} ms)")
            print(f"       总收益:     {v3_metrics['total_return']*100:.2f}%")
            print(f"       Sharpe:     {v3_metrics['sharpe']:.4f}")
            print(f"       交易次数:   {v3_metrics['num_trades']}")

            # 与 v2.1 同步路径结果对比
            if res is not None:
                import numpy as np
                diff = abs(v3_metrics['total_return'] - metrics['total_return'])
                ok(f"V3 vs v2.1 总收益差异: {diff:.2e}")
                if diff < 1e-9:
                    print(f"       {PASS} 数值完全一致")
                else:
                    print(f"       {FAIL} 数值有差异（可能因策略实例状态不同）")
        else:
            fail(f"V3 返回类型异常: {type(v3_result).__name__}")
    except Exception as e:
        fail(f"V3 compute.remote('backtest') 失败: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 10. V3: compute.remote('indicator') 远程指标
# ═══════════════════════════════════════════════════════
if not args.skip_v3 and btc is not None and len(btc) > 0:
    v3_step("10. V3 compute.remote('indicator') 远程指标")

    try:
        import pandas as pd
        task = client.compute.remote(
            "indicator",
            symbols=["BTC/USDT"], timeframe="1d",
            method="rsi", kwargs={"window": 14},
        )
        result = task.wait(timeout=30)
        if isinstance(result, pd.Series):
            ok(f"V3 远程 RSI(14): len={len(result)}, last={result.iloc[-1]:.2f}")
        else:
            fail(f"V3 返回类型异常: {type(result).__name__}")
    except Exception as e:
        fail(f"V3 compute.remote('indicator') 失败: {e}")


# ═══════════════════════════════════════════════════════
#  总结
# ═══════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"测试完成: {'https' if args.https else 'http'}://{args.host}:{args.port}")
if not args.skip_v3:
    print(f"V3 步骤: 已执行 (8/9/10)")
print(f"{'='*60}")
