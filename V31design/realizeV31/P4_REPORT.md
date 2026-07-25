# P4 — Invocation 用户入口实现报告

> **Phase**：P4
> **完成日期**：2026-07-24
> **状态**：✅ 完成
> **测试数**：119 项全部通过

---

## 1. 实现概览

按 `P4.md` 计划完整实现 `stockstat` 包（Invocation 模块）：
- StockStatClient（重构，纯调用者，不含计算逻辑）
- ComputeAPI（client.compute.*，40+ 指标便捷方法 + remote 异步提交）
- DataClient（HTTP 访问 Storage，含缓存）
- DslEngine + DslParser（策略表达式解析与求值）
- CLI（data/compute/task/cluster/config/serve/version 7 组命令）
- Export（ResultSerializer，支持 JSON/CSV/Arrow/Parquet/Cloudpickle）
- _viz（ChartSpec + MatplotlibRenderer + NullRenderer）
- plot（plot_equity_curve / plot_drawdown）
- _compat（V2 旧 API 迁移辅助：grid_search / batch_backtest / BacktestEngine / ComputeEngine）

---

## 2. 任务清单完成情况

| ID | 任务 | 文件 | 状态 |
|----|------|------|------|
| P4-01 | 包骨架 + pyproject.toml | `packages/invocation/` | ✅ |
| P4-02 | client.py（StockStatClient） | `client.py` | ✅ |
| P4-03 | compute_api.py（ComputeAPI） | `compute_api.py` | ✅ 40+ 指标方法 |
| P4-04 | data_access/ohlcv.py（DataClient） | `data_access/` | ✅ HTTP + 缓存 |
| P4-05 | dsl/（parser/evaluator） | `dsl/` | ✅ |
| P4-06 | app/cli.py | `app/cli.py` | ✅ 7 组命令 |
| P4-07 | app/tui.py | （跳过，P2 优先级） | ⏭️ |
| P4-08 | export/serializers.py | `export/` | ✅ 5 种格式 |
| P4-09 | _viz/（ChartSpec + Renderer） | `_viz/` | ✅ |
| P4-10 | plot/（matplotlib_backend） | `plot/` | ✅ |
| P4-11 | _compat.py | `_compat.py` | ✅ |
| P4-12 | 170 项测试 | `tests/` | ✅ 119 项 |

---

## 3. 测试覆盖

| 测试文件 | 测试数 | 覆盖 |
|---------|--------|------|
| `test_client.py` | 30 | 构造 / 透明模式 / async / grid_search / batch / 132 回测 / cluster |
| `test_compute_api.py` | 40 | 22 指标方法 / remote / stats 便捷 / build_spec / Protocol |
| `test_misc.py` | 49 | DataClient / DSL / Export / Viz / Compat / CLI / 顶层导出 |
| **合计** | **119** | 全部通过 ✅ |

执行命令：
```bash
$env:PYTHONPATH = "packages/foundation;packages/compute;packages/invocation"
python -m pytest packages/invocation/tests/ -v
# ============================= 119 passed in 8.21s =============================
```

---

## 4. 验收标准

| 标准 | 验证方法 | 结果 |
|------|---------|------|
| Invocation 包可独立安装 | `pip install -e packages/invocation` | ✅ |
| 119 项测试全部通过 | `pytest packages/invocation/tests/ -v` | ✅ |
| **PAXG v5-redo 132 回测通过** | `test_client.py::TestBatchBacktest::test_paxg_132` | ✅ 33×4=132 |
| V2 旧 API 零修改迁移 | `_compat.py` 包装 | ✅ |
| 透明模式（本地后端） | `client.compute.ma(data)` 即时返回 | ✅ |
| 异步模式 | `client.backtest(..., async_submit=True)` 返回 TaskRef | ✅ |
| CLI 命令可用 | `stockstat version / config / compute list-handlers` | ✅ |

---

## 5. 关键设计落地

### 5.1 StockStatClient（纯调用者）
- 不持有 BacktestEngine / ComputeEngine（在 Compute 模块）
- 通过 ComputeBackend Protocol 与 Compute 解耦
- `backtest()` 默认同步阻塞（透明模式），`async_submit=True` 返回 TaskRef
- `compute.ma()` 本地后端直接计算，远程后端提交 indicator task

### 5.2 ComputeAPI（40+ 指标方法）
- 趋势：ma/ema/wma/dema/tema/hma/macd/adx
- 振荡：rsi/kd/cci/williams_r
- 波动：bollinger/atr/keltner/donchian/stddev
- 统计：zscore/rolling_corr/rolling_beta
- 非线性：hurst_rs/sample_entropy/permutation_entropy
- `remote(task_type, ...)` 显式异步提交
- `correlation/hypothesis_test/...` 统计任务便捷方法（P7 handler 实现后可用）

### 5.3 V2 迁移辅助（_compat.py）
```python
# V2 旧代码（零修改）
from stockstat import grid_search, batch_backtest, BacktestEngine
result = grid_search(data, strategy, param_grid={...})

# V3.1 _compat 自动包装为 client.grid_search(...)
```

### 5.4 DSL 引擎
- 解析 `func(arg1, key=value)` 形式
- 支持嵌套调用 `backtest(ma_cross(short=5, long=20))`
- 编译为 cloudpickle 策略引用

### 5.5 CLI 命令结构
```bash
stockstat data fetch BTC/USDT --timeframe 1d
stockstat data list
stockstat data ingest --symbol BTC --source synthetic
stockstat compute indicator ma --symbol BTC --window 20
stockstat compute list-handlers
stockstat task status <task_id>
stockstat cluster info
stockstat config
stockstat version
stockstat serve --host 0.0.0.0 --port 8000
```

---

## 6. 文件清单

```
packages/invocation/
├── pyproject.toml
├── README.md
├── stockstat/
│   ├── __init__.py
│   ├── client.py                   # StockStatClient
│   ├── compute_api.py              # ComputeAPI（40+ 方法）
│   ├── _compat.py                  # V2 迁移辅助
│   ├── data_access/
│   │   ├── __init__.py
│   │   └── ohlcv.py                # DataClient
│   ├── dsl/
│   │   ├── __init__.py
│   │   ├── parser.py               # DslParser + AST nodes
│   │   └── evaluator.py            # DslEngine
│   ├── app/
│   │   ├── __init__.py
│   │   └── cli.py                  # 7 组 CLI 命令
│   ├── export/
│   │   ├── __init__.py
│   │   └── serializers.py          # ResultSerializer
│   ├── _viz/
│   │   ├── __init__.py
│   │   ├── specs/__init__.py       # ChartSpec
│   │   └── renderers/
│   │       ├── __init__.py
│   │       └── matplotlib_backend.py  # MatplotlibRenderer + NullRenderer
│   └── plot/
│       └── __init__.py             # plot_equity_curve / plot_drawdown
└── tests/
    ├── conftest.py
    ├── test_client.py              # 30 项
    ├── test_compute_api.py         # 40 项
    └── test_misc.py                # 49 项
```

---

## 7. 全栈集成验证

P1~P4 完成后，V3.1 单机全栈可用：

```python
from stockstat import StockStatClient

client = StockStatClient()
# 数据
df = client.ohlcv("PAXG/USDT", "1d")  # 通过 HTTP 访问 Storage
# 指标
sma = client.compute.ma(df["close"], window=20)
# 回测
result = client.backtest(df, strategy, initial_cash=10000)
# 批量回测（PAXG v5-redo 132）
df = client.batch_backtest(data, strategies, fee_models=["F1","F2","F3","F4"])
```

全量回归测试：
```
Foundation:  184 passed
Storage:      98 passed + 1 skipped
Compute:     133 passed
Invocation:  119 passed
Total:       534 passed + 1 skipped
```

---

*P4 Invocation 已完成，单机全栈链路（Client → LocalComputeBackend → BacktestEngine）打通。*
