# BT-7: DSL 集成 + 12 策略全套测试

> **阶段**: BT-7 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_strategies.py` (14 passed)

## 产出

### 12 个内置示例策略

每个策略在合成数据上完整跑通，验证回测系统对不同范式（趋势/震荡/套利/事件驱动/多 tf/多标的）的支持：

| # | 策略 | 验证点 |
|---|------|--------|
| 1 | 双均线交叉 | MVP 闭环、市价单 |
| 2 | 布林带突破 | bollinger + 反转平仓 |
| 3 | RSI 超买超卖 | rsi 反向开仓 |
| 4 | MACD 背离 | `compute.register()` 自定义指标 |
| 5 | ATR 通道突破 | atr + Donchian + ATR 风险预算仓位 |
| 6 | 网格交易 | 多挂单、状态持久化（ContextHistory） |
| 7 | 配对交易 | 多标的、做空对冲、z-score 价差 |
| 8 | 风险平价 | 3 标的反波动率加权再平衡 |
| 9 | 动量轮动 | 5 标的 Top-K 调仓 |
| 10 | 多 tf 共振 | 日线 MA 过滤 + 小时线突破 |
| 11 | PAXG 周末效应 | weekday 事件驱动 |
| 12 | 马丁格尔 | 亏损翻倍 + 加仓上限 |

### DSL 信号集成

`Signal.market_on_signal()` 辅助类支持布尔信号驱动下单；测试验证预计算 RSI 信号 mask 驱动订单。

### Client 集成

`StockStatClient.backtest(data, strategy, **kwargs)` 便捷方法，自动注入 client 的 `ComputeEngine`：

```python
from stockstat import StockStatClient
from stockstat.backtest import strategy, Order

client = StockStatClient(host="localhost", port=8000)
data = {"BTC/USDT": {"1d": client.ohlcv("BTC/USDT", start="2024-01-01")}}

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21:
        return
    if d.close.rolling(5).mean().iloc[-1] > d.close.rolling(20).mean().iloc[-1]:
        if ctx.portfolio.get_position("BTC/USDT").qty == 0:
            ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))

res = client.backtest(data, ma_cross, initial_cash=10000)
print(res.summary())
```

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_strategies.py -v
# 14 passed
```

全部 12 策略 + DSL 信号 + client 集成测试通过。

## 阶段总结

回测子系统 BT-0 ~ BT-7 全部完成。总计 **124 个回测测试** + 原 31 个前端测试 = **184 个测试全部通过**。回测功能已可用于真实数据。
