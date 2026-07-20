# BT-V3: Dashboard + Trade Annotations + Batch Savefig + Graceful Degradation

> **Phase**: BT-V3 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_viz_dashboard.py` (15 passed)

## Deliverables

### `dashboard` chart

2×2 combined dashboard with four default panels:

| Panel | Content |
|-------|---------|
| top-left | equity_curve (strategy + benchmark) |
| top-right | drawdown (fill area) |
| bottom-left | returns_distribution (histogram) |
| bottom-right | monthly_heatmap (or parameter_heatmap when grid_results passed) |

Supports `panels=` custom panel list; `grid_results=` swaps the 4th panel to parameter heatmap.

### Trade annotations

When `trades_overlay` chart has `annotate_trades=True`, `MatplotlibBacktestChartRenderer._annotate_trades` draws on the first subplot at each fill timestamp:
- Buy: green "B" + up-arrow
- Sell: red "S" + down-arrow

### Batch savefig

`result.render_all(directory, names=None)` one-shot renders multiple charts to a directory:

```python
out = res.render_all("./charts")
# {'equity_curve': './charts/equity_curve.png',
#  'drawdown': './charts/drawdown.png', ...}
```

- Default renders 7 chart types
- Auto-skips unknown chart names
- `plt.close(fig)` after each to free memory

### Graceful degradation

- `NullBacktestChartRenderer`'s `render_all` returns empty dict + single aggregated warning
- `render(path=...)` skips savefig when renderer unavailable (file not created)
- Never raises, ensuring backtest core works without matplotlib

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_viz_dashboard.py -v
# 15 passed
```

Covers: dashboard 4-subplot+render+savefig+parameter_heatmap panel+custom panels, trade annotation B/S text, render_all batch+custom names+skip unknown, Null degradation render_all warning+render no-crash+savefig skip, end-to-end backtest→dashboard→save, grid_search→parameter heatmap.

## Phase summary

The backtest visualization subsystem BT-V0 through BT-V3 is complete:

| Phase | Tests |
|-------|-------|
| BT-V0 | 28 |
| BT-V1 | 16 |
| BT-V2 | 17 |
| BT-V3 | 15 |
| **Total** | **76** |

Combined with backtest core 124 + frontend 31 = **231 tests all passing**. The backtest visualization feature is ready, with zero matplotlib hard-dependency in the core.
