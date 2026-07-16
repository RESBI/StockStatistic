# BT-4: 成本与成交模型完善

> **阶段**: BT-4 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_cost.py` (11 passed)

## 产出

### 成本模型（`cost_model.py`）

| 模型 | 说明 |
|------|------|
| `PercentCost` | 比例手续费 + 比例滑点（默认） |
| `FixedCost` | 固定每笔费用 + 滑点 |
| `TieredCost` | 按成交额阶梯费率 |
| `MinCost` | 比例费率 + 最小手续费兜底 |
| `StampDutyCost` | 股票：双边佣金 + 卖方印花税 |
| `ZeroCost` | 零成本（对照基准） |

### 成交模型（`fill_model.py`）

| 模型 | 成交价 |
|------|--------|
| `NextOpenFill` | 下一 bar open（默认，最强防未来函数） |
| `NextCloseFill` | 下一 bar close |
| `ThisCloseFill` | 当前 bar close（告警） |
| `VWAPFill` | (O+H+L+C)/4 加权 |
| `WorstPriceFill` | 买按 high、卖按 low（保守冲击） |

### 订单生命周期

- `DAY` 订单当日未成交（含限价条件未满足）自动撤销
- `TRAILING_STOP` 维护历史极值，触发后按 stop_price 偏移成交
- 资金不足/做空受限时订单被静默拒绝，不崩溃

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_cost.py -v
# 11 passed
```

覆盖：零成本 vs 比例成本对比、固定费金额、印花税仅卖方、阶梯费率三档、最小手续费兜底、NextOpen vs NextClose、VWAP、WorstPrice 买按 high、昂贵订单拒绝、DAY 订单到期撤销、移动止损成交。

## 下一阶段

BT-5：绩效统计、报告与可视化。
