# BT-9: 回测引擎增强 P1 — 重要增强

> **阶段**: BT-9 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_p1.py` (9 passed)

## 目标

补充 intrabar 模拟、批量回测、退出原因统计等实战能力。

## 产出

### 新增模块

| 模块 | 类/函数 | 说明 |
|------|---------|------|
| `intrabar.py` | `IntrabarSimulator` | 用更细 K 线模拟限价单盘中成交时序 |
| `batch_runner.py` | `StrategyBatchRunner` | 批量运行多策略并汇总 |
| `batch_runner.py` | `BatchResults` | 批量结果容器，含 to_dataframe/rank/best_by |
| `result.py` | `exit_reason_stats()` | 按退出原因分组的交易统计 |

### 使用示例

```python
from stockstat.backtest import StrategyBatchRunner, IntrabarSimulator

# 批量回测
runner = StrategyBatchRunner(
    data={"PAXG/USDT": {"1d": df, "1h": df_1h}},
    initial_cash=10000,
    cost_model=BINANCE_FUTURES_BNB,
)
results = runner.run_all({"s1": strat1, "s2": strat2})
df = results.to_dataframe()  # 汇总 DataFrame
```

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_p1.py -v
# 9 passed
```

测试覆盖：IntrabarSimulator（3）、StrategyBatchRunner（5）、exit_reason_stats（1）。
