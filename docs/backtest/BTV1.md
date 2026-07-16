# BT-V1: matplotlib Backend Basic Rendering

> **Phase**: BT-V1 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_viz_mpl.py` (16 passed)

## Deliverables

### `matplotlib_charts.py`

`MatplotlibBacktestChartRenderer` implements the `BacktestChartRenderer` protocol:

- **Lazy import**: `render()` imports `matplotlib.pyplot` internally; `available()` uses try/except
- **Multi-subplot layout**: creates subplots per `spec.layout` (rows, cols); auto-fits 1×1 or 2-col when insufficient
- **6 kind renderers**:
  - `line` → `ax.plot`
  - `bar` → `ax.bar`
  - `scatter` → `ax.scatter` (supports `marker`)
  - `fill` → `ax.fill_between` (supports `fill_to` baseline)
  - `histogram` → `ax.hist` (supports `bins`)
  - `heatmap` → `ax.imshow` + colorbar + tick labels (DataFrame input)
- **Dual y-axis**: `secondary_y=True` auto `ax.twinx()`
- **Log y-axis**: `SubplotSpec.log_y=True` → `ax.set_yscale("log")`
- **Trade annotations**: B/S arrow markers on first subplot when `spec.annotate_trades=True`
- **savefig**: `savefig(path, dpi=150)` + `show()`

### Three basic charts fully validated

| Chart | Validates |
|-------|-----------|
| equity_curve | dual series (strategy + benchmark), savefig produces file |
| drawdown | fill area + line overlay |
| trades_overlay | scatter buy/sell + B/S annotations |
| underwater_curve | fill area |

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_viz_mpl.py -v
# 16 passed
```

Covers: renderer available/detect/factory, equity dual series + savefig, drawdown fill + savefig, trades annotation + savefig, result.render one-liner, no-benchmark single series, empty result (no fills), underwater.

## Next phase

BT-V2: advanced charts (histogram/heatmap/bar rendering validation + parameter_heatmap).
