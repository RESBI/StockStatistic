# BT-V0: 回测可视化接口冻结

> **阶段**: BT-V0 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_viz_iface.py` (28 passed, 合成数据) + `tests/test_backtest_viz_online.py` (17 passed, 真实数据)

## 目标

冻结回测可视化子系统的核心数据结构与协议：`BacktestChartSpec` / `SubplotSpec` / `ChartSeries`、`BacktestChartRenderer` 协议、`NullBacktestChartRenderer` 兜底、`chart_factory` 检测器，以及 7 个基础图表类型的 spec 构建器。**不依赖 matplotlib**。

## 产出

### 新增模块

| 模块 | 职责 |
|------|------|
| `chart_spec.py` | `BacktestChartSpec` + `SubplotSpec` + `ChartSeries` 数据类，支持 line/bar/scatter/fill/histogram/heatmap 六种 kind、多子图 layout、to_dict 序列化 |
| `chart_registry.py` | `@register_chart` 装饰器 + `build_chart(name, result)` 工厂 |
| `null_charts.py` | `NullBacktestChartRenderer`：render/savefig 均发 UserWarning，available()=False |
| `chart_factory.py` | `detect()` 自动探测 matplotlib；`get_chart_renderer(name)` 工厂 |

### 扩展模块

- `plot_adapter.py`：新增 7 个 `@register_chart` 构建器（equity_curve/drawdown/trades_overlay/returns_distribution/monthly_heatmap/yearly_returns/underwater_curve），保留原 `plot_equity/plot_drawdown/plot_trades`（通用 PlotSpec，向后兼容）
- `result.py`：新增 `result.chart(name)` / `result.render(name, path)` / `result.available_chart_types`

### 关键设计

- **零硬依赖**：`import stockstat.backtest` 不触发 matplotlib；仅当调用 `get_chart_renderer()` 且 matplotlib 已安装时才延迟导入
- **专用 spec 层**：`BacktestChartSpec` 与通用 `PlotSpec` 平行，互不污染
- **延迟注册**：`@register_chart` 在首次调用 `result.chart()` 时触发 `plot_adapter` 导入，避免循环依赖

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_viz_iface.py -v
# 28 passed
```

覆盖：ChartSpec/SubplotSpec/ChartSeries 数据类与 kind、to_dict 序列化、registry 注册/查询/构建、Null 渲染器告警、factory 探测、result.chart() 7 种类型、result.render() Null 降级、向后兼容 PlotSpec。

## 下一阶段

BT-V1：matplotlib backend 基础渲染（line/fill/scatter/多子图）。

## 在线真实数据验证

BT-V0 ~ BT-V3 的接口在 `tests/test_backtest_viz_online.py` 中以**真实市场数据**（Binance BTC/USDT + ETH/USDT 2023-2024，Yahoo Finance AAPL/^GSPC 2023-2024，经代理获取）完整验证：

| 测试类 | 数据 | 验证内容 |
|--------|------|---------|
| `TestBTCDoubleMAViz` | BTC/USDT 2023-2024 日线 | 双均线回测 + 9 种图表 PNG 生成 + render_all 批量 |
| `TestPairTradingViz` | BTC+ETH 2023-2024 日线 | 配对交易回测 + equity/dashboard PNG |
| `TestParameterHeatmapViz` | AAPL 2023-2024 日线 | 4×5 网格搜索 + 参数热力图 + 含热力图仪表盘 |
| `TestMultiTFViz` | BTC 2024 日线+小时线 | 多 tf 回测 + 仪表盘 PNG |

13 张真实数据图像生成至 `docs/images/backtest_*.png`。
