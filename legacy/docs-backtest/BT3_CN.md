# BT-3: 多 timeframe 对齐 + 未来函数审计

> **阶段**: BT-3 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_multitf.py` (8 passed)

## 产出

### 多 tf 对齐机制

- `DataFeed` 自动选择**最低粒度 timeframe** 作为 `primary_tf`（按 1m<5m<15m<1h<4h<1d<1w 顺序）
- `master_index` = 所有标的在 primary_tf 上的时间戳并集
- 高 tf DataFrame 用 `reindex(master_index, method="ffill")` 对齐——任意时刻 `bar_at(sym, tf, t)` 返回截至 t 的最近高 tf bar
- `get_slice(sym, tf, t, lookback)` 返回 `≤ t` 闭区间切片

### 未来函数防护

- 策略 `on_bar(t)` 经 `Context.get` 只能获取 `≤ t` 数据
- `lookahead_audit=True` 时，运行时检测切片 `index.max() > now` 抛 `LookaheadError`
- 订单默认 `NextOpenFill`（t+1 open 成交），双重防护

### 多 tf 共振策略验证

日线 MA20 方向过滤 + 小时线突破入场，验证高 tf 信号驱动低 tf 入场。

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_multitf.py -v
# 8 passed
```

覆盖：primary_tf 选最细、主索引为小时、日线 ffill 对齐到小时、lookback 切片、日线过滤小时突破策略、正常访问不报错、lookahead 错误捕获、单 tf 仍正常。

## 下一阶段

BT-4：成本与成交模型完善。
