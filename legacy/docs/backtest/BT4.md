# BT-4: Cost & Fill Model Realism

> **Phase**: BT-4 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_cost.py` (11 passed)

## Deliverables

### Cost models (`cost_model.py`)

| Model | Description |
|-------|-------------|
| `PercentCost` | Percentage commission + percentage slippage (default) |
| `FixedCost` | Fixed per-fill fee + slippage |
| `TieredCost` | Tiered rate by gross trade value |
| `MinCost` | Percentage rate with minimum fee floor |
| `StampDutyCost` | Equity: commission both sides + sell-side stamp duty |
| `ZeroCost` | Zero cost (baseline) |

### Fill models (`fill_model.py`)

| Model | Fill price |
|-------|------------|
| `NextOpenFill` | Next bar open (default, strongest lookahead protection) |
| `NextCloseFill` | Next bar close |
| `ThisCloseFill` | Current bar close (warned) |
| `VWAPFill` | (O+H+L+C)/4 weighted |
| `WorstPriceFill` | Buy at high, sell at low (conservative impact) |

### Order lifecycle

- `DAY` orders auto-cancel if unfilled (including failed limit conditions)
- `TRAILING_STOP` tracks historical extremum, fills at stop_price offset when triggered
- Insufficient funds / short-disallowed orders are silently rejected without crashing

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_cost.py -v
# 11 passed
```

Covers: zero vs percent cost comparison, fixed fee amount, stamp duty sell-only, tiered three-tier, min-cost floor, NextOpen vs NextClose, VWAP, WorstPrice buy at high, expensive order rejection, DAY order expiry cancel, trailing-stop fill.

## Next phase

BT-5: performance metrics, reporting, and visualization.
