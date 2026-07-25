# BT-V2: 高级图表（热力 / 分布 / 参数网格）

> **阶段**: BT-V2 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_viz_advanced.py` (17 passed)

## 产出

### 高级图表类型

| 图表 | kind | 数据形态 | 渲染方式 |
|------|------|---------|---------|
| `returns_distribution` | histogram | 1-D Series | `ax.hist(bins)` |
| `monthly_heatmap` | heatmap | 2-D DataFrame（year × month pivot） | `ax.imshow` + colorbar |
| `yearly_returns` | bar | 1-D Series（年聚合） | `ax.bar` |
| `parameter_heatmap` | heatmap | 2-D DataFrame（参数网格） | `ax.imshow` + colorbar |

### `parameter_heatmap` builder

接收 `grid_results`（来自 `optimizer.grid_search` 的 `(params, metric_value, result)` 列表），自动提取两个参数键构建 pivot 矩阵：

```python
results = grid_search(make_engine, {"short": [3,5,8], "long": [10,20,30]}, metric="sharpe")
spec = res.chart("parameter_heatmap", grid_results=results, metric="sharpe")
renderer.render(spec)  # 热力图：x=short, y=long, color=sharpe
```

### monthly_heatmap 数据处理

- 收益率 `resample("ME").sum()` 按月聚合
- `pivot_table(index="year", columns="month")` 构建年×月矩阵
- 兼容旧版 pandas 的 `M`/`A` 别名（try/except）

### 多子图组合验证

`BacktestChartSpec(layout=(2,1))` 含两个 SubplotSpec（equity + drawdown）成功渲染。

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_viz_advanced.py -v
# 17 passed
```

覆盖：returns_distribution spec+渲染+savefig+自定义 bins、monthly_heatmap spec+渲染+savefig+长数据 pivot、yearly_returns spec+渲染+savefig、parameter_heatman spec+渲染+savefig+空 grid+grid_search 集成、多子图 layout。

## 下一阶段

BT-V3：组合仪表盘 + 交易标注 + 批量 savefig + 优雅降级。
