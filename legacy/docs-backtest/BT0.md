# BT-0: Backtest Interface Freeze

> **Phase**: BT-0
> **Status**: Complete
> **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_iface.py` (37 passed)

## Goal

Freeze all core dataclasses and abstract base class signatures for the backtest subsystem, establishing a stable interface skeleton to be filled by subsequent phases.

## Deliverables

### New package
`frontend/stockstat/backtest/` with 16 modules:

| Module | Responsibility |
|--------|----------------|
| `orders.py` | `Order` / `Fill` dataclasses + enums |
| `portfolio.py` | `Portfolio` / `Position` |
| `cost_model.py` | `CostModel` abstract + 6 implementations |
| `fill_model.py` | `FillModel` abstract + 5 implementations + `LookaheadError` |
| `data_feed.py` | `Universe` + `DataFeed` multi-tf alignment |
| `context.py` | `BacktestContext` + `ContextHistory` + lookahead guard |
| `strategy.py` | `Strategy` base + `@strategy` decorator + `Signal` |
| `broker.py` | `SimulatedBroker` |
| `sizing.py` | position sizing algorithms |
| `metrics.py` | performance aggregation |
| `result.py` | `BacktestResult` |
| `benchmark.py` | buy-and-hold benchmark |
| `plot_adapter.py` | equity/trades → PlotSpec |
| `engine.py` | `BacktestEngine` main loop |
| `optimizer.py` / `walkforward.py` / `montecarlo.py` | optional optimization |

### Key design decisions

1. **Cash-flow sign convention**: `net_value` is cash flowing into the account (negative for buys, positive for sells); `cash += net_value`.
2. **Enums**: OrderSide/OrderType/TimeInForce are `str, Enum`, constructible from strings.
3. **Position cost tracking**: `Position.apply_fill` handles add/reduce/reversal, returns realized PnL.
4. **Multi-tf alignment**: `DataFeed` uses the finest tf as master index; higher tfs reindex with `ffill`.

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_iface.py -v
# 37 passed
```

Covers: order dataclasses, positions, 6 cost models, 6 fill models, Universe/DataFeed alignment & slicing, Portfolio cash/short, strategy decorator, sizing, benchmark, engine construction signature.

## Next phase

BT-1: implement single-asset single-timeframe MVP loop and MA crossover strategy on top of this interface.
