# BT-3: Multi-Timeframe Alignment + Lookahead Audit

> **Phase**: BT-3 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_multitf.py` (8 passed)

## Deliverables

### Multi-tf alignment

- `DataFeed` auto-selects the **finest timeframe** as `primary_tf` (ordered 1m<5m<15m<1h<4h<1d<1w)
- `master_index` = union of all symbols' timestamps at primary_tf
- Higher-tf DataFrames are aligned via `reindex(master_index, method="ffill")` — `bar_at(sym, tf, t)` returns the most recent higher-tf bar as of t
- `get_slice(sym, tf, t, lookback)` returns a `≤ t` closed-interval slice

### Lookahead protection

- `on_bar(t)` via `Context.get` can only access data `≤ t`
- With `lookahead_audit=True`, runtime checks `index.max() > now` and raises `LookaheadError`
- Default `NextOpenFill` (fill at t+1 open) provides double protection

### Multi-tf resonance validation

Daily MA20 direction filter + hourly breakout entry — validates high-tf signal driving low-tf entries.

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_multitf.py -v
# 8 passed
```

Covers: primary_tf picks finest, master index is hourly, daily ffill-aligned to hourly, lookback slice, daily-filter-hourly-breakout strategy, normal access OK, lookahead error caught, single-tf still works.

## Next phase

BT-4: cost and fill model realism.
