# BT-V0: Backtest Visualization Interface Freeze

> **Phase**: BT-V0 | **Status**: Complete | **Date**: 2026-07-16
> **Tests**: `tests/test_backtest_viz_iface.py` (28 passed)

## Goal

Freeze the core data structures and protocols for the backtest visualization subsystem: `BacktestChartSpec` / `SubplotSpec` / `ChartSeries`, the `BacktestChartRenderer` protocol, `NullBacktestChartRenderer` fallback, `chart_factory` detector, and 7 basic chart-type spec builders. **No matplotlib dependency**.

## Deliverables

### New modules

| Module | Responsibility |
|--------|----------------|
| `chart_spec.py` | `BacktestChartSpec` + `SubplotSpec` + `ChartSeries` dataclasses; supports line/bar/scatter/fill/histogram/heatmap kinds, multi-subplot layout, to_dict serialization |
| `chart_registry.py` | `@register_chart` decorator + `build_chart(name, result)` factory |
| `null_charts.py` | `NullBacktestChartRenderer`: render/savefig emit UserWarning, available()=False |
| `chart_factory.py` | `detect()` auto-detects matplotlib; `get_chart_renderer(name)` factory |

### Extended modules

- `plot_adapter.py`: 7 new `@register_chart` builders (equity_curve/drawdown/trades_overlay/returns_distribution/monthly_heatmap/yearly_returns/underwater_curve); keeps original `plot_equity/plot_drawdown/plot_trades` (generic PlotSpec, back-compat)
- `result.py`: new `result.chart(name)` / `result.render(name, path)` / `result.available_chart_types`

### Key design

- **Zero hard dependency**: `import stockstat.backtest` never triggers matplotlib; lazy import only when `get_chart_renderer()` is called AND matplotlib is installed
- **Dedicated spec layer**: `BacktestChartSpec` parallel to generic `PlotSpec`, no mutual pollution
- **Lazy registration**: `@register_chart` triggers `plot_adapter` import on first `result.chart()` call, avoiding circular imports

## Acceptance

```bash
cd frontend && python -m pytest tests/test_backtest_viz_iface.py -v
# 28 passed
```

Covers: ChartSpec/SubplotSpec/ChartSeries dataclasses & kinds, to_dict serialization, registry register/query/build, Null renderer warnings, factory detection, result.chart() 7 types, result.render() Null degradation, back-compat PlotSpec.

## Next phase

BT-V1: matplotlib backend basic rendering (line/fill/scatter/subplots).
