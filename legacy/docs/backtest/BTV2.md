# BT-V2: Advanced Charts (Heatmap / Distribution / Parameter Grid)

> **Phase**: BT-V2 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_viz_advanced.py` (17 passed)

## Deliverables

### Advanced chart types

| Chart | kind | Data shape | Rendering |
|-------|------|------------|-----------|
| `returns_distribution` | histogram | 1-D Series | `ax.hist(bins)` |
| `monthly_heatmap` | heatmap | 2-D DataFrame (year × month pivot) | `ax.imshow` + colorbar |
| `yearly_returns` | bar | 1-D Series (annual aggregate) | `ax.bar` |
| `parameter_heatmap` | heatmap | 2-D DataFrame (parameter grid) | `ax.imshow` + colorbar |

### `parameter_heatmap` builder

Accepts `grid_results` (list of `(params, metric_value, result)` from `optimizer.grid_search`), auto-extracts two parameter keys to build a pivot matrix:

```python
results = grid_search(make_engine, {"short": [3,5,8], "long": [10,20,30]}, metric="sharpe")
spec = res.chart("parameter_heatmap", grid_results=results, metric="sharpe")
renderer.render(spec)  # heatmap: x=short, y=long, color=sharpe
```

### monthly_heatmap data processing

- Returns `resample("ME").sum()` for monthly aggregation
- `pivot_table(index="year", columns="month")` builds year×month matrix
- Backward-compatible with older pandas `M`/`A` aliases (try/except)

### Multi-subplot combo validation

`BacktestChartSpec(layout=(2,1))` with two SubplotSpecs (equity + drawdown) renders successfully.

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_viz_advanced.py -v
# 17 passed
```

Covers: returns_distribution spec+render+savefig+custom bins, monthly_heatmap spec+render+savefig+long-data pivot, yearly_returns spec+render+savefig, parameter_heatmap spec+render+savefig+empty grid+grid_search integration, multi-subplot layout.

## Next phase

BT-V3: dashboard combo + trade annotations + batch savefig + graceful degradation.
