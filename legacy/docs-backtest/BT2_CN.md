# BT-2: 多标的组合 + 做空 + 订单扩展

> **阶段**: BT-2 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_portfolio.py` (12 passed)

## 产出

- **Universe 多标的**：`{symbol: {tf: df}}` 自然支持多标的；`DataFeed` 取并集时间索引
- **做空**：`allow_short=True` 时 `Portfolio.apply_fill` 允许负持仓；`allow_short=False` 时拒绝并静默移除订单
- **订单类型扩展**：`OrderType.LIMIT`（限价）、`STOP`（止损）、`STOP_LIMIT`、`TRAILING_STOP`（移动止损，broker 维护极值状态）
- **TimeInForce**：`GTC` / `DAY`（当日未成交自动撤销）/ `IOC`
- **仓位算法**（`sizing.py`）：`fixed_size / fixed_amount / percent_equity / kelly_fraction / atr_risk_budget`
- **配对交易策略验证**：BTC/ETH 对数价差 z-score 触发多空对冲
- **风险平价策略验证**：3 标的反波动率加权定期再平衡

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_portfolio.py -v
# 12 passed
```

覆盖：双标的 universe、context.get 多标的、同时买入两标的、做空启用/禁用、下跌市场做空盈利、限价买单价格下穿成交/上涨永不成交、止损触发、ATR 仓位、配对交易、风险平价再平衡。

## 下一阶段

BT-3：多 timeframe 对齐与未来函数审计。
