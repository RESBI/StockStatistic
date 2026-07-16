# BT-5: Performance Metrics + Reporting + Visualization

> **Phase**: BT-5 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_metrics.py` (21 passed)

## Deliverables

### Performance metrics (`metrics.py`, reuses `indicators.statistics`)

| Category | Metrics |
|----------|---------|
| Return | total_return / annualized_return |
| Risk-adjusted | sharpe / sortino / calmar / omega / information_ratio |
| Drawdown | max_drawdown / drawdown_series |
| Volatility | volatility (annualized) |
| Trades | num_trades / num_fills / win_rate / avg_pnl / profit_factor / max_win_streak / max_loss_streak / expectancy |

### Reporting & export

- `result.summary()`: one-line text summary (all key metrics)
- `result.to_dict()`: metrics + config + equity + trades
- `result.to_csv(path)`: trade ledger export
- `result.trades_df()` / `fills_df()`: DataFrame form

### Visualization (`plot_adapter.py`, reuses `plot` protocol)

- `result.plot_equity()`: equity curve + benchmark comparison
- `result.plot_drawdown()`: drawdown curve
- `result.plot_trades()`: equity curve + buy/sell scatter markers
- All return backend-agnostic `PlotSpec`, renderable by matplotlib/plotly/null

### Benchmark comparison

- `benchmark="X"` auto-generates buy-and-hold equity curve
- `information_ratio` auto-computed
- `buy_and_hold()` helper

### Reproducibility

- `BacktestResult.config` records initial_cash / seed / symbols / cost_model / fill_model / primary_tf
- Same seed + same strategy + same data → identical equity curve

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_metrics.py -v
# 21 passed
```

Covers: metric functions, full metrics key set, summary, returns, drawdown property, benchmark comparison, buy_and_hold, to_dict/to_csv, three PlotSpecs, optional matplotlib render, config recording, seed reproducibility.

## Next phase

BT-6: parameter optimization, walk-forward, Monte Carlo (optional extras).
