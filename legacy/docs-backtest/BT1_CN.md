# BT-1: 单标的单 timeframe MVP

> **阶段**: BT-1
> **状态**: 已完成
> **日期**: 2026-07-16
> **测试**: `tests/test_backtest_mvp.py` (13 passed)

## 目标

实现可完整运行的回测主循环：DataFeed → Context → Strategy → Broker → Portfolio → BacktestResult，并在双均线交叉策略上验证。

## 产出

### 主循环设计（事件驱动）

```
for each bar t in master_index:
    1. 匹配上一 bar 提交的待挂订单（在 t 的 open 成交）
    2. 策略 on_bar(t) — 读取 ≤ t 切片、调用 compute、提交新订单
    3. mark_to_market(t.close) — 更新权益曲线
    4. on_bar_close(t)
末 bar 冲刷剩余市价单
```

关键时序保证：订单在 t 提交 → t+1 的 open 成交（NextOpenFill 默认），成交记录于 t+1，权益曲线在每个 bar 的 close 估值，**无未来函数**。

### 集成验证

- `ctx.compute` 代理 `ComputeEngine`，策略内可调用 `rsi/bollinger/macd/atr` 等全部内置指标
- `ctx.compute.register()` 可在 `on_bar` 内注册自定义指标（如 Donchian 通道）
- `BacktestResult.metrics()` 给出 total_return/sharpe/sortino/max_drawdown/calmar/volatility + 交易统计
- `result.plot_equity()/plot_drawdown()/plot_trades()` 返回 `PlotSpec`，可被 matplotlib renderer 渲染
- `result.to_dict()/to_csv()/summary()` 导出

### 双均线策略示例

```python
from stockstat.backtest import BacktestEngine, strategy, Order

@strategy
def ma_cross(ctx):
    d = ctx.get("X", "1d", lookback=30)
    if len(d) < 21:
        return
    ma5 = d.close.rolling(5).mean().iloc[-1]
    ma20 = d.close.rolling(20).mean().iloc[-1]
    pos = ctx.portfolio.get_position("X")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("X", "buy", 10))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("X", "sell", pos.qty))

res = BacktestEngine(data={"X": {"1d": df}}, strategy=ma_cross,
                     initial_cash=100000).run()
print(res.summary())
```

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_mvp.py -v
# 13 passed
```

覆盖：MA 交叉运行、生成买卖单、指标合理、权益非负、compute 集成、自定义指标注册、NextOpenFill 无未来函数、成本降低收益、trades_df/to_dict、PlotSpec 生成。

## 下一阶段

BT-2：扩展到多标的组合、做空、限价/止损/移动止损单、仓位算法。
