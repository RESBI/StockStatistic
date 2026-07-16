# BT-5: 绩效统计 + 报告 + 可视化

> **阶段**: BT-5 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_metrics.py` (21 passed)

## 产出

### 绩效指标（`metrics.py`，复用 `indicators.statistics`）

| 类别 | 指标 |
|------|------|
| 收益 | total_return / annualized_return |
| 风险调整 | sharpe / sortino / calmar / omega / information_ratio |
| 回撤 | max_drawdown / drawdown_series |
| 波动 | volatility（年化） |
| 交易 | num_trades / num_fills / win_rate / avg_pnl / profit_factor / max_win_streak / max_loss_streak / expectancy |

### 报告与导出

- `result.summary()`：一行式文本摘要（含全部关键指标）
- `result.to_dict()`：metrics + config + equity + trades
- `result.to_csv(path)`：交易明细导出
- `result.trades_df()` / `fills_df()`：DataFrame 形式

### 可视化（`plot_adapter.py`，复用 `plot` 协议）

- `result.plot_equity()`：资金曲线 + 基准对比（双 series）
- `result.plot_drawdown()`：回撤曲线
- `result.plot_trades()`：资金曲线 + 买/卖散点标记
- 全部返回后端无关 `PlotSpec`，可被 matplotlib/plotly/null renderer 渲染

### 基准对比

- `benchmark="X"` 参数自动生成买入持有权益曲线
- `information_ratio` 自动计算
- `buy_and_hold()` 辅助函数

### 可复现性

- `BacktestResult.config` 记录 initial_cash / seed / symbols / cost_model / fill_model / primary_tf
- 相同 seed + 相同策略 + 相同数据 → 完全一致权益曲线

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_metrics.py -v
# 21 passed
```

覆盖：指标函数（total_return/max_drawdown/drawdown_series/sharpe/omega/information_ratio/trade_stats）、完整 metrics 键集、summary、returns、drawdown 属性、基准对比、buy_and_hold、to_dict/to_csv、三种 PlotSpec、matplotlib 可选渲染、config 记录、seed 可复现。

## 下一阶段

BT-6：参数优化、走样分析、蒙特卡洛（可选 extras）。
