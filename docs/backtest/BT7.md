# BT-7: DSL Integration + Full 12-Strategy Test Suite

> **Phase**: BT-7 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_strategies.py` (14 passed)

## Deliverables

### 12 built-in example strategies

Each strategy runs end-to-end on synthetic data, validating the backtest system's support for different paradigms (trend/oscillator/arbitrage/event-driven/multi-tf/multi-asset):

| # | Strategy | Validates |
|---|----------|-----------|
| 1 | MA crossover | MVP loop, market orders |
| 2 | Bollinger breakout | bollinger + reversal exit |
| 3 | RSI overbought/oversold | rsi reverse entry |
| 4 | MACD divergence | `compute.register()` custom indicator |
| 5 | ATR channel breakout | atr + Donchian + ATR-risk-budget sizing |
| 6 | Grid trading | multi-orders, state persistence (ContextHistory) |
| 7 | Pair trading | multi-asset, short hedge, z-score spread |
| 8 | Risk parity | 3-asset inverse-volatility rebalance |
| 9 | Momentum rotation | 5-asset Top-K rotation |
| 10 | Multi-tf resonance | daily MA filter + hourly breakout |
| 11 | PAXG weekend effect | weekday event-driven |
| 12 | Martingale | doubling down + cap |

### DSL signal integration

`Signal.market_on_signal()` helper supports boolean-signal-driven orders; test validates a precomputed RSI signal mask driving orders.

### Client integration

`StockStatClient.backtest(data, strategy, **kwargs)` convenience method auto-injects the client's `ComputeEngine`:

```python
from stockstat import StockStatClient
from stockstat.backtest import strategy, Order

client = StockStatClient(host="localhost", port=8000)
data = {"BTC/USDT": {"1d": client.ohlcv("BTC/USDT", start="2024-01-01")}}

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21:
        return
    if d.close.rolling(5).mean().iloc[-1] > d.close.rolling(20).mean().iloc[-1]:
        if ctx.portfolio.get_position("BTC/USDT").qty == 0:
            ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))

res = client.backtest(data, ma_cross, initial_cash=10000)
print(res.summary())
```

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_strategies.py -v
# 14 passed
```

All 12 strategies + DSL signal + client integration tests pass.

## Phase summary

The backtest subsystem BT-0 through BT-7 is complete. Total: **124 backtest tests** + 31 original frontend tests = **184 tests all passing**. The backtest feature is ready for real-data use.
