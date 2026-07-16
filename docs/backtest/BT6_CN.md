# BT-6: 参数优化 + 走样 + 蒙特卡洛

> **阶段**: BT-6 | **状态**: 已完成 | **日期**: 2026-07-16
> **测试**: `tests/test_backtest_optimize.py` (8 passed)
> **依赖**: 核心无额外依赖；`optuna` 走 `[optimize]` extras

## 产出

### 网格搜索（`optimizer.py`）

```python
from stockstat.backtest.optimizer import grid_search

results = grid_search(make_engine, {"short": [3, 5, 8], "long": [10, 20]},
                      metric="sharpe")
best_params, best_val, best_result = results[0]
```

- 穷举所有参数组合，按指定 metric 排序（默认最大化）
- 返回 `(params, metric_value, BacktestResult)` 列表

### optuna 搜索（可选 extras）

```python
from stockstat.backtest.optimizer import optuna_search

def param_space(trial):
    return {"short": trial.suggest_int("short", 2, 10),
            "long": trial.suggest_int("long", 15, 40)}

study = optuna_search(make_engine, param_space, n_trials=50, metric="sharpe")
```

- 缺失 optuna 时抛清晰的 `ImportError`，提示 `pip install stockstat[optimize]`

### 走样分析（`walkforward.py`）

```python
from stockstat.backtest.walkforward import walk_forward

segments = walk_forward(make_engine, index, train_size=100, test_size=50, step=50)
for test_start, test_end, result in segments:
    print(test_start, test_end, result.metrics()["sharpe"])
```

- 滚动训练窗 → 测试窗，避免过拟合

### 蒙特卡洛（`montecarlo.py`）

- `bootstrap_returns(returns, n_samples)`：收益率有放回重采样
- `monte_carlo_equity(returns, initial, n_samples)`：生成多条备选权益曲线 DataFrame
- `shuffle_orders(fills, seed)`：订单时序打乱，评估顺序鲁棒性

## 验收

```bash
cd frontend && python -m pytest tests/test_backtest_optimize.py -v
# 8 passed
```

覆盖：网格搜索排序/最佳首位/全组合、走样分段、bootstrap 长度、蒙特卡洛权益 DataFrame、订单打乱保序、optuna 导入错误提示。

## 下一阶段

BT-7：DSL 集成 + 12 个策略全套测试 + 文档。
