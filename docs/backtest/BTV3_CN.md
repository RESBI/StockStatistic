# BT-V3: 组合仪表盘 + 交易标注 + 批量 savefig + 优雅降级

> **阶段**: BT-V3 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_viz_dashboard.py` (15 passed)

## 产出

### `dashboard` 图表

2×2 组合仪表盘，默认四面板：

| 面板 | 内容 |
|------|------|
| 左上 | equity_curve（strategy + benchmark） |
| 右上 | drawdown（fill 填充） |
| 左下 | returns_distribution（histogram） |
| 右下 | monthly_heatmap（或 parameter_heatmap 当传入 grid_results） |

支持 `panels=` 自定义面板列表；`grid_results=` 时第 4 面板切换为参数热力图。

### 交易标注

`trades_overlay` 图表 `annotate_trades=True` 时，`MatplotlibBacktestChartRenderer._annotate_trades` 在首子图的每个 fill 时点绘制：
- 买入：绿色 "B" + 上箭头
- 卖出：红色 "S" + 下箭头

### 批量 savefig

`result.render_all(directory, names=None)` 一键渲染多种图表到目录：

```python
out = res.render_all("./charts")
# {'equity_curve': './charts/equity_curve.png',
#  'drawdown': './charts/drawdown.png', ...}
```

- 默认渲染 7 种图表
- 自动跳过未知图表名
- 每张图渲染后 `plt.close(fig)` 释放内存

### 优雅降级

- `NullBacktestChartRenderer` 的 `render_all` 返回空 dict + 单一聚合告警
- `render(path=...)` 在 renderer 不可用时跳过 savefig（文件不创建）
- 全程不抛异常，保证回测核心在无 matplotlib 环境下正常工作

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_viz_dashboard.py -v
# 15 passed
```

覆盖：dashboard 四子图+渲染+savefig+parameter_heatmap 面板+自定义 panels、交易标注 B/S 文本、render_all 批量+自定义 names+跳过未知、Null 降级 render_all 告警+render 不 crash+savefig 跳过、端到端回测→仪表盘→保存、grid_search→参数热力图。

## 阶段总结

回测可视化子系统 BT-V0 ~ BT-V3 全部完成：

| 阶段 | 测试数 |
|------|--------|
| BT-V0 | 28 |
| BT-V1 | 16 |
| BT-V2 | 17 |
| BT-V3 | 15 |
| **合计** | **76** |

加上回测核心 124 + 前端 31 = **共 231 个测试全部通过**。回测可视化功能已可用，且核心零 matplotlib 硬依赖。
