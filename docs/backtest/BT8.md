# BT-8: Backtest Engine Enhancement P0 — Critical Fixes

> **Phase**: BT-8 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_p0.py` (17 passed)

## Goal

Fix three critical deficiencies exposed by v5 research: intrabar limit fills, Maker/Taker fee differentiation, and OCO orders.

## Deliverables

### New Components

| Component | File | Description |
|-----------|------|-------------|
| `IntrabarLimitFill` | `fill_model.py` | Fills limit orders when intrabar price crosses the limit level |
| `MakerTakerCost` | `cost_model.py` | LIMIT→maker rate, MARKET/STOP→taker rate |
| `BinanceCost` | `cost_model.py` | Binance spot/futures × BNB discount four combinations |
| `submit_oco()` | `broker.py` | OCO order pair; filling one cancels the other |
| `exit_reason` | `orders.py` | `Order`/`Fill` gained exit reason field |

### Preset Constants

```python
BINANCE_SPOT        # Spot, no BNB
BINANCE_SPOT_BNB    # Spot + BNB (-25%)
BINANCE_FUTURES     # Futures, no BNB
BINANCE_FUTURES_BNB # Futures + BNB (-10%)
```

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_p0.py -v
# 17 passed
```

Test coverage: IntrabarLimitFill (6), MakerTakerCost (3), BinanceCost (4), OCO orders (2), exit_reason (2).
