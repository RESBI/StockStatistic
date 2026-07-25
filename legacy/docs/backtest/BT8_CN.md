# BT-8: 回测引擎增强 P0 — 致命修复

> **阶段**: BT-8 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_p0.py` (17 passed)

## 目标

修复 v5 研究暴露的三项致命缺陷：限价单 intrabar 成交、Maker/Taker 费率区分、OCO 订单。

## 产出

### 新增组件

| 组件 | 文件 | 说明 |
|------|------|------|
| `IntrabarLimitFill` | `fill_model.py` | 限价单在盘中价格穿越限价水平时成交 |
| `MakerTakerCost` | `cost_model.py` | LIMIT→maker 费率，MARKET/STOP→taker 费率 |
| `BinanceCost` | `cost_model.py` | Binance 现货/合约 × BNB 抵扣四组合 |
| `submit_oco()` | `broker.py` | OCO 订单对，任一成交则撤销另一方 |
| `exit_reason` | `orders.py` | `Order`/`Fill` 新增退出原因字段 |

### 预设常量

```python
BINANCE_SPOT        # 现货无 BNB
BINANCE_SPOT_BNB    # 现货+BNB (-25%)
BINANCE_FUTURES     # 合约无 BNB
BINANCE_FUTURES_BNB # 合约+BNB (-10%)
```

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_p0.py -v
# 17 passed
```

测试覆盖：IntrabarLimitFill（6）、MakerTakerCost（3）、BinanceCost（4）、OCO 订单（2）、exit_reason（2）。
