# BT-V1: matplotlib backend 基础渲染

> **阶段**: BT-V1 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_viz_mpl.py` (16 passed)

## 产出

### `matplotlib_charts.py`

`MatplotlibBacktestChartRenderer` 实现 `BacktestChartRenderer` 协议：

- **延迟导入**：`render()` 内部才 `import matplotlib.pyplot`，`available()` 用 try/except 探测
- **多子图 layout**：按 `spec.layout` (rows, cols) 创建 subplots；不足时自动 1×1 或 2 列布局
- **6 种 kind 渲染**：
  - `line` → `ax.plot`
  - `bar` → `ax.bar`
  - `scatter` → `ax.scatter`（支持 `marker` 参数）
  - `fill` → `ax.fill_between`（支持 `fill_to` 基线）
  - `histogram` → `ax.hist`（支持 `bins`）
  - `heatmap` → `ax.imshow` + colorbar + 刻度标签（DataFrame 输入）
- **双 y 轴**：`secondary_y=True` 自动 `ax.twinx()`
- **对数 y 轴**：`SubplotSpec.log_y=True` → `ax.set_yscale("log")`
- **交易标注**：`spec.annotate_trades=True` 时在首子图标注 B/S 箭头
- **savefig**：`savefig(path, dpi=150)` + `show()`

### 三种基础图完整验证

| 图表 | 验证点 |
|------|--------|
| equity_curve | 双 series（strategy + benchmark）、savefig 生成文件 |
| drawdown | fill 填充区 + line 叠加 |
| trades_overlay | scatter 买卖点 + B/S 标注 |
| underwater_curve | fill 填充 |

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_viz_mpl.py -v
# 16 passed
```

覆盖：renderer available/detect/factory、equity 双 series + savefig、drawdown fill + savefig、trades 标注 + savefig、result.render 一行式、无基准单 series、空结果（无 fills）、underwater。

## 下一阶段

BT-V2：高级图表（histogram/heatmap/bar 的渲染验证 + parameter_heatmap）。
