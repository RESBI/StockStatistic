# BT-2: Multi-Asset Portfolio + Short Selling + Order Extensions

> **Phase**: BT-2 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_portfolio.py` (12 passed)

## Deliverables

- **Multi-asset Universe**: `{symbol: {tf: df}}` natively supports multiple instruments; `DataFeed` unions time indices
- **Short selling**: `allow_short=True` permits negative positions; `allow_short=False` rejects and silently drops the order
- **Order type extensions**: `LIMIT`, `STOP`, `STOP_LIMIT`, `TRAILING_STOP` (broker tracks extremum state)
- **TimeInForce**: `GTC` / `DAY` (auto-cancel if unfilled) / `IOC`
- **Position sizing** (`sizing.py`): `fixed_size / fixed_amount / percent_equity / kelly_fraction / atr_risk_budget`
- **Pair-trading validation**: BTC/ETH log-spread z-score triggers long/short hedge
- **Risk-parity validation**: 3-asset inverse-volatility weighted periodic rebalance

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_portfolio.py -v
# 12 passed
```

Covers: two-symbol universe, multi-symbol context.get, simultaneous buys, short enabled/disabled, short profit in decline, limit-buy fills on dip / never fills in uptrend, stop-loss trigger, ATR sizing, pair trading, risk-parity rebalance.

## Next phase

BT-3: multi-timeframe alignment and lookahead audit.
