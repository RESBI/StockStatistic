# BT-1: Single-Asset Single-Timeframe MVP

> **Phase**: BT-1
> **Status**: Complete
> **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_mvp.py` (13 passed)

## Goal

Implement a fully runnable backtest main loop — DataFeed → Context → Strategy → Broker → Portfolio → BacktestResult — validated on an MA crossover strategy.

## Deliverables

### Main loop design (event-driven)

```
for each bar t in master_index:
    1. match pending orders submitted at the previous bar (fill at t's open)
    2. strategy on_bar(t) — read ≤ t slice, call compute, submit new orders
    3. mark_to_market(t.close) — update equity curve
    4. on_bar_close(t)
flush remaining market orders at the last bar
```

Key timing guarantee: an order submitted at t fills at t+1's open (default NextOpenFill), recorded at t+1; the equity curve is valued at each bar's close — **no lookahead**.

### Integration validation

- `ctx.compute` proxies `ComputeEngine` — strategies can call `rsi/bollinger/macd/atr` and all built-in indicators
- `ctx.compute.register()` allows registering custom indicators inside `on_bar` (e.g. Donchian channel)
- `BacktestResult.metrics()` returns total_return/sharpe/sortino/max_drawdown/calmar/volatility + trade stats
- `result.plot_equity()/plot_drawdown()/plot_trades()` return `PlotSpec`, renderable by matplotlib
- `result.to_dict()/to_csv()/summary()` exports

### MA crossover example

```python
from stockstat.backtest import BacktestEngine, strategy, Order

@strategy
def ma_cross(ctx):
    d = ctx.get("X", "1d", lookback=30)
    if len(d) < 21:
        return
    ma5 = d.close.rolling(5).mean().iloc[-1]
    ma20 = d.close.rolling(20).mean().iloc[-1]
    pos = ctx.portfolio.get_position("X")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("X", "buy", 10))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("X", "sell", pos.qty))

res = BacktestEngine(data={"X": {"1d": df}}, strategy=ma_cross,
                     initial_cash=100000).run()
print(res.summary())
```

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_mvp.py -v
# 13 passed
```

Covers: MA crossover run, buy/sell fills, reasonable metrics, non-negative equity, compute integration, custom indicator registration, NextOpenFill no-lookahead, cost reduces return, trades_df/to_dict, PlotSpec generation.

## Next phase

BT-2: extend to multi-asset portfolios, short selling, limit/stop/trailing-stop orders, sizing algorithms.
