# BT-0: 回测接口与数据结构冻结

> **阶段**: BT-0
> **状态**: 已完成
> **日期**: 2026-07-16
> **测试**: `tests/test_backtest_iface.py` (37 passed)

## 目标

冻结回测子系统的所有核心 dataclass 与抽象基类签名，建立可被后续阶段填充的稳定接口骨架。

## 产出

### 新增包
`frontend/stockstat/backtest/`，包含 16 个模块：

| 模块 | 职责 |
|------|------|
| `orders.py` | `Order` / `Fill` 数据类 + 枚举（OrderSide/OrderType/TimeInForce/OrderStatus） |
| `portfolio.py` | `Portfolio` / `Position`：现金、持仓、apply_fill、mark_to_market |
| `cost_model.py` | `CostModel` 抽象 + PercentCost/FixedCost/TieredCost/MinCost/StampDutyCost/ZeroCost |
| `fill_model.py` | `FillModel` 抽象 + NextOpenFill/NextCloseFill/ThisCloseFill/VWAPFill/WorstPriceFill + LookaheadError |
| `data_feed.py` | `Universe` + `DataFeed`：多标的多 tf 对齐与切片 |
| `context.py` | `BacktestContext` + `ContextHistory`：策略可见世界 + 未来函数防护 |
| `strategy.py` | `Strategy` 基类 + `FunctionStrategy` + `@strategy` 装饰器 + `Signal` |
| `broker.py` | `SimulatedBroker`：撮合引擎 |
| `sizing.py` | 仓位规模算法 |
| `metrics.py` | 绩效聚合函数 |
| `result.py` | `BacktestResult` |
| `benchmark.py` | 买入持有基准 |
| `plot_adapter.py` | equity/trades → PlotSpec |
| `engine.py` | `BacktestEngine` 主循环 |
| `optimizer.py` / `walkforward.py` / `montecarlo.py` | 可选优化模块 |

### 关键设计决策

1. **Fill 现金流符号约定**：`net_value` 为进入账户的现金流（买入为负、卖出为正），`cash += net_value`。
2. **枚举化**：OrderSide/OrderType/TimeInForce 均为 `str, Enum`，支持字符串构造。
3. **持仓成本**：`Position.apply_fill` 处理加仓/减仓/翻转，返回已实现盈亏。
4. **多 tf 对齐**：`DataFeed` 以最低粒度 tf 为主索引，高 tf 用 `reindex(method="ffill")` 对齐。

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_iface.py -v
# 37 passed
```

覆盖：订单数据类、持仓、6 种成本模型、6 种成交模型、Universe/DataFeed 对齐与切片、Portfolio 现金/做空、策略装饰器、仓位算法、基准、引擎构造签名。

## 下一阶段

BT-1：基于此接口实现单标的单 timeframe MVP 主循环与双均线策略。
