# BT-10: 回测引擎增强 P2 — 分析工具

> **阶段**: BT-10 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_p2.py` (11 passed)

## 目标

补充年化因子推断、DCA 基准、子期间/状态分析、手续费敏感性扫描等分析工具。

## 产出

### 新增模块

| 模块 | 类/函数 | 说明 |
|------|---------|------|
| `engine.py` | `periods_per_year` 参数 | 显式指定年化因子 |
| `benchmark.py` | `dca_equity()` | 定投基准（支持 auto/weekly/monthly） |
| `analyzer.py` | `BacktestAnalyzer` | 子期间/状态/滚动/退出分析 |
| `fee_sweep.py` | `fee_sweep()` | 均匀费率扫描 |
| `fee_sweep.py` | `maker_taker_sweep()` | Maker×Taker 网格扫描 |

### BacktestAnalyzer 能力

| 方法 | 用途 |
|------|------|
| `subperiod_metrics()` | 按 split_dates 分割资金曲线计算子期间指标 |
| `regime_conditional_metrics()` | 按状态序列分组计算指标 |
| `rolling_metric()` | 滚动 Sharpe/波动率/回撤/收益 |
| `trade_analysis_by_exit()` | 按退出原因分组统计交易 |

### 使用示例

```python
from stockstat.backtest import BacktestAnalyzer, fee_sweep

# 子期间分析
sub = BacktestAnalyzer.subperiod_metrics(res, [pd.Timestamp("2024-01-01")])

# 费率扫描
df = fee_sweep(data, strategy, fee_rates=[0.0, 0.001, 0.002])
```

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_p2.py -v
# 11 passed
```

测试覆盖：periods_per_year（2）、DCA（3）、BacktestAnalyzer（4）、fee_sweep（2）。

## 阶段总结

BT-8 ~ BT-10 全部完成。新增 37 个测试（P0: 17 + P1: 9 + P2: 11），累计 189 个回测测试全部通过。回测引擎增强子系统完成，原生支持 intrabar 限价单、Maker/Taker 费率、OCO 订单、批量回测、退出分析等高级功能。
