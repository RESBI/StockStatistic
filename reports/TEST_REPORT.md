# StockStat 测试报告 v2 — 真实数据 + 代理

> **日期**: 2026-07-16 (v2.3 新增回测可视化在线真实数据测试)  
> **测试环境**: Windows / Python 3.10.11 / SQLite / HTTP Proxy (http://127.0.0.1:8889)  
> **数据源**: Yahoo Finance (股票) + Binance (加密货币)，通过代理访问真实市场数据

---

## 测试总览

| 测试套件 | 测试数 | 通过 | 失败 | 耗时 |
|----------|--------|------|------|------|
| P0: 后端存储 (真实数据 + 代理) | 15 | 15 | 0 | ~17s |
| P1-P4: 前端计算 (指标+DSL+可视化) | 31 | 31 | 0 | ~3s |
| P5: 集成测试 (真实数据经典统计+PAXG) | 19 | 19 | 0 | ~13s |
| P5: matplotlib 图表测试 (经典+PAXG) | 10 | 10 | 0 | ~50s |
| BT: 回测子系统 (BT-0~BT-7, 合成数据) | 124 | 124 | 0 | ~12s |
| BT-V: 回测可视化子系统 (BT-V0~V3, 合成数据) | 76 | 76 | 0 | ~20s |
| BT-V-Online: 回测可视化在线真实数据 | 17 | 17 | 0 | ~30s |
| **合计** | **292** | **292** | **0** | **~145s** |

---

## P0: 存储后端测试 — 真实数据 (15 passed)

### 代理验证

| # | 测试名 | 验证内容 | 结果 |
|---|--------|----------|------|
| 1 | `test_health` | 健康检查返回代理状态 enabled=true | PASS |
| 2 | `test_proxy_config` | /api/v1/proxy 返回正确配置 | PASS |
| 3 | `test_sources` | 数据源列表含 yfinance/binance | PASS |

### 真实数据采集

| # | 测试名 | 数据源 | 标的 | 采集量 | 结果 |
|---|--------|--------|------|--------|------|
| 4 | `test_ingest_yfinance` | Yahoo Finance | AAPL | >200 条 (252交易日) | PASS |
| 5 | `test_ingest_ccxt_btc` | Binance/ccxt | BTC/USDT | >300 条 (366天) | PASS |
| 6 | `test_ingest_ccxt_eth` | Binance/ccxt | ETH/USDT | >300 条 | PASS |
| 7 | `test_ingest_ccxt_paxg` | Binance/ccxt | PAXG/USDT | >700 条 (1096天) | PASS |
| 8 | `test_ingest_yfinance_index` | Yahoo Finance | ^GSPC | >400 条 (501天) | PASS |
| 15 | `test_auto_detect_source` | 自动检测 | MSFT→yfinance | — | PASS |

### 查询与缓存

| # | 测试名 | 验证内容 | 结果 |
|---|--------|----------|------|
| 9 | `test_query_ohlcv_json` | JSON 格式返回正确 OHLCV | PASS |
| 10 | `test_query_ohlcv_csv` | CSV 格式返回正确行数 | PASS |
| 11 | `test_query_date_filter` | 日期范围过滤 (6月: 20-31条) | PASS |
| 12 | `test_query_not_found` | 不存在标的返回 404 | PASS |
| 13 | `test_query_cache` | 缓存命中更快 | PASS |
| 14 | `test_symbols` | 符号列表含 AAPL/BTC/PAXG | PASS |

### 关键发现
- **YahooDirectAdapter** 绕过 yfinance 的 cookie/crumb 机制，直接调用 Yahoo API，通过代理稳定获取真实股票数据
- **ccxt + 代理** 通过 `exchange.proxies` 配置，稳定获取 Binance 加密货币数据
- 代理配置对上层完全透明，适配器实例化时注入

---

## P1-P4: 前端计算库测试 (31 passed)

> 纯计算单元测试，使用本地合成数据验证算法正确性，不依赖网络。

### P1: 指标库 (17 passed)

| 类别 | 测试数 | 结果 |
|------|--------|------|
| 趋势 (MA/EMA/MACD) | 4 | ALL PASS |
| 震荡 (RSI/KDJ) | 3 | ALL PASS |
| 波动 (STD/ATR/Bollinger) | 3 | ALL PASS |
| 统计 (Corr/Beta/Sharpe/DD/VaR/Returns) | 7 | ALL PASS |

### P2: DSL 解析器 (7 passed)

| 测试 | 验证点 | 结果 |
|------|--------|------|
| 基础解析 | SELECT...FROM ohlcv() | PASS |
| 日期范围 | 带 start/end 参数 | PASS |
| LIMIT 子句 | 分页查询 | PASS |
| WHERE 条件 | 条件过滤 | PASS |
| MA 执行 | DSL→DataFrame | PASS |
| RSI 执行 | 值域 [0,100] | PASS |
| returns 执行 | 收益率计算 | PASS |

### P4: 可视化 (7 passed)

| 测试 | 验证点 | 结果 |
|------|--------|------|
| PlotSpec 创建 | 多 series 构建 | PASS |
| PlotSpec 序列化 | to_dict() JSON | PASS |
| NullRenderer | 优雅降级 (告警不报错) | PASS |
| 渲染器检测 | 自动检测 matplotlib | PASS |
| matplotlib 渲染 | 折线图绘制 | PASS |
| matplotlib 保存 | PNG 文件输出 | PASS |
| client.plot API | spec() 接口 | PASS |

---

## P5: 集成测试 — 真实数据 (21 passed)

### 经典统计测试 (11 passed)

| # | 测试用例 | 数据源 | 验证内容 | 结果 |
|---|---------|--------|----------|------|
| 1 | MA 金叉死叉 | AAPL 真实数据 | golden/death cross 信号 | PASS |
| 2 | RSI 超买超卖 | BTC/USDT 真实数据 | RSI∈[0,100]，有>70或<30读数 | PASS |
| 3 | Beta 系数 | AAPL vs ^GSPC 真实 | Beta 均值 ∈ [0.5, 2.0] | PASS |
| 4 | 最大回撤 | BTC/USDT 真实 | 回撤 ∈ [-1, 0] | PASS |
| 5 | 夏普比率 | BTC/USDT 真实 | Sharpe ∈ [-5, 10] | PASS |
| 6 | 布林带 | ETH/USDT 真实 | upper≥mid≥lower，突破<15% | PASS |
| 7 | 跨资产相关性 | BTC vs ETH 真实 | corr > 0.6 | PASS |
| 8 | DSL MA 查询 | AAPL 真实 | 端到端 DSL→DataFrame | PASS |
| 9 | DSL RSI 查询 | BTC/USDT 真实 | DSL + LIMIT | PASS |
| 10 | DSL returns | ETH/USDT 真实 | 收益率计算 | PASS |
| 11 | 可视化 | AAPL 真实 | 绘图 + 保存 PNG | PASS |

### PAXG 周末涨跌与周一独立涨跌幅分析 (8 passed) — 真实数据

> **指标定义**：对每个周一同时记录最大涨幅 `(最高-开盘)/开盘` 和最大跌幅 `(最低-开盘)/开盘`，与周末涨跌幅独立相关。避免按信号方向选择极值导致的选择偏差。

| # | 测试 | 验证内容 | 结果 |
|---|------|--------|------|
| 1 | 数据量 | PAXG 真实数据 >700 条 | PASS |
| 2 | 周末数据 | 周六/周日均有 >100 条 | PASS |
| 3 | 样本数 | 周末-周一配对 >50 | PASS (156) |
| 4 | Pearson 范围 | r(gain) 和 r(loss) ∈ [-1, 1] | PASS |
| 5 | p 值范围 | ∈ [0, 1] | PASS |
| 6 | 涨跌幅合理性 | PAXG 周一涨跌幅 <5% | PASS |
| 7 | 结果输出 | 完整统计报告 | PASS |
| 8 | 散点图 | 绘制并保存 | PASS |

### PAXG 相关性分析结果（真实数据）

```
============================================================
PAXG Weekend Return vs Monday Independent Gain/Loss (REAL DATA)
============================================================
  Samples:    156 (up=76, dn=65)
  r(gain):    0.2303  p=0.0038  sig=True
  r(loss):    -0.2004  p=0.0121  sig=True
  Sig>0: gain=0.7099%±0.7559%, loss=-0.9070%±0.9424%
  Sig<0: gain=0.5940%±0.3944%, loss=-0.7435%±0.8261%
  t-test(up vs dn): gain t=1.114 p=0.2673, loss t=-1.086 p=0.2792
============================================================
```

### 真实数据结论

**PAXG 周末涨跌幅对周一涨幅和跌幅有适度但统计显著的独立预测力**：

- **r(涨幅) = 0.23** (p=0.004)：弱但显著的正相关 — 周末正向涨跌幅适度预测周一最大涨幅
- **r(跌幅) = -0.20** (p=0.012)：弱但显著的负相关 — 周末正向涨跌幅适度预测周一最大跌幅较小
- **涨组 vs 跌组**：涨幅和跌幅均值在两组间无显著差异 (t 检验 p > 0.26)
- **结论**：周末涨跌幅对周一涨幅和跌幅的独立预测力真实但较弱 (r ≈ 0.2)。高个体波动性（标准差 ≈ 均值）限制了单笔交易的可预测性。

### 方法论说明

早期版本采用"方向选择"方法（v1：按周末方向选极值），得到 r≈0.58，但该结果源于选择偏差。当前版本（v2：独立记录涨跌幅）消除了该偏差，得到更可靠的弱相关结论。

### matplotlib 图表测试 (10 passed)

| # | 图表 | 文件 | 结果 |
|---|------|------|------|
| 1 | BTC 布林带 | btc_bollinger.png | PASS |
| 2 | BTC RSI | btc_rsi.png | PASS |
| 3 | ETH MACD | eth_macd.png | PASS |
| 4 | BTC 回撤 | btc_drawdown.png | PASS |
| 5 | AAPL Beta 散点 | aapl_beta_scatter.png | PASS |
| 6 | BTC/ETH 滚动相关性 | btc_eth_corr.png | PASS |
| 7 | 标准化价格对比 | price_comparison.png | PASS |
| 8 | PAXG 涨跌幅散点图 | paxg_weekend_scatter.png | PASS |
| 9 | PAXG 涨跌幅分布直方图 | paxg_directional.png | PASS |
| 10 | PAXG 周末涨跌幅分布 | paxg_weekend_hist.png | PASS |

### 指标演进对比

| 版本 | 指标定义 | Pearson | p 值 | 显著性 | 说明 |
|------|---------|---------|------|--------|------|
| v1 (旧) | (High-Low)/Low 总振幅 | 0.32 | 0.000042 | 是 | 总振幅，无方向 |
| v1-dir (旧) | 按周末方向选极值 | 0.58 | ≈0 | 是 | **选择偏差伪象** |
| **v2 (当前)** | **独立记录涨跌幅** | **r(gain)=0.23, r(loss)=-0.20** | **0.004 / 0.012** | **是** | **消除选择偏差，弱但真实** |

当前版本（v2）消除了方向选择偏差，得到更可靠的结论：周末涨跌幅对周一涨跌幅有弱但统计显著的独立预测力。

---

## 测试覆盖的标的（仅获取所需标的）

| 标的 | 数据源 | 时间范围 | 用途 |
|------|--------|---------|------|
| AAPL | Yahoo Finance | 2023-2024 | MA金叉、Beta、可视化 |
| ^GSPC | Yahoo Finance | 2023-2024 | Beta 基准 |
| MSFT | Yahoo Finance | 2024 H1 | 自动检测测试 |
| BTC/USDT | Binance | 2023-2024 | RSI、回撤、Sharpe |
| ETH/USDT | Binance | 2024 | 布林带、跨资产相关性 |
| PAXG/USDT | Binance | 2022-2024 | 周末相关性分析 |

---

## BT: 回测子系统测试 (124 passed)

回测子系统分 8 个阶段实现，每阶段独立测试。所有测试在合成数据上运行（无需后端/代理）。

| 阶段 | 测试文件 | 测试数 | 验证内容 |
|------|---------|--------|---------|
| BT-0 | `test_backtest_iface.py` | 37 | 接口骨架：订单/持仓/成本/成交/Universe/DataFeed/Portfolio/策略/仓位/基准 |
| BT-1 | `test_backtest_mvp.py` | 13 | 单标的 MVP：双均线、compute 集成、自定义指标、成本影响、导出、PlotSpec |
| BT-2 | `test_backtest_portfolio.py` | 12 | 多标的、做空、限价/止损/移动止损、仓位算法、配对交易、风险平价 |
| BT-3 | `test_backtest_multitf.py` | 8 | 多 tf 对齐、primary_tf 选择、ffill、lookback、未来函数审计 |
| BT-4 | `test_backtest_cost.py` | 11 | 6 种成本模型、5 种成交模型、DAY 订单到期、移动止损、资金不足拒绝 |
| BT-5 | `test_backtest_metrics.py` | 21 | 指标函数、完整 metrics、summary、基准、导出、PlotSpec、可复现性 |
| BT-6 | `test_backtest_optimize.py` | 8 | 网格搜索、走样分析、蒙特卡洛、订单打乱、optuna 导入错误 |
| BT-7 | `test_backtest_strategies.py` | 14 | 12 个策略全套 + DSL 信号 + client 集成 |

**运行命令**：
```bash
cd frontend && python -m pytest tests/test_backtest_*.py -v --ignore=tests/test_backtest_viz_iface.py --ignore=tests/test_backtest_viz_mpl.py --ignore=tests/test_backtest_viz_advanced.py --ignore=tests/test_backtest_viz_dashboard.py
# 124 passed
```

---

## BT-V: 回测可视化子系统测试 (93 passed)

回测可视化子系统分 4 个阶段实现，另含在线真实数据验证。**核心零 matplotlib 硬依赖**——安装 matplotlib 后自动激活。

### BT-V 合成数据测试 (76 passed)

| 阶段 | 测试文件 | 测试数 | 验证内容 |
|------|---------|--------|---------|
| BT-V0 | `test_backtest_viz_iface.py` | 28 | BacktestChartSpec/SubplotSpec/ChartSeries 数据类、registry、Null 渲染器、factory、result.chart() 9 种类型 |
| BT-V1 | `test_backtest_viz_mpl.py` | 16 | matplotlib 渲染 line/fill/scatter、equity/drawdown/trades/underwater、savefig |
| BT-V2 | `test_backtest_viz_advanced.py` | 17 | histogram/heatmap/bar、returns_distribution/monthly_heatmap/yearly/parameter_heatmap、grid_search 集成 |
| BT-V3 | `test_backtest_viz_dashboard.py` | 15 | dashboard 2×2 组合、交易标注、render_all 批量、Null 优雅降级、端到端 |

### BT-V 在线真实数据测试 (17 passed)

使用真实市场数据（Binance BTC/USDT + ETH/USDT 2023-2024，Yahoo Finance AAPL/^GSPC 2023-2024，经代理获取）验证回测可视化全流程，并生成 13 张真实数据 PNG 图像到 `docs/images/`。

| 测试类 | 数据 | 测试数 | 验证内容 | 生成图像 |
|--------|------|--------|---------|---------|
| TestBTCDoubleMAViz | BTC/USDT 日线 2023-2024 | 10 | 双均线回测 + 9 种图表 + render_all | 9 张 |
| TestPairTradingViz | BTC+ETH 日线 2023-2024 | 3 | 配对交易回测 + equity/dashboard | 2 张 |
| TestParameterHeatmapViz | AAPL 日线 2023-2024 | 3 | 4×5 网格搜索 + 参数热力图 + 含热力图仪表盘 | 2 张 |
| TestMultiTFViz | BTC 日线+小时线 2024 | 1 | 多 tf 回测 + 仪表盘 | 1 张 |

**生成图像清单**（`docs/images/backtest_*.png`）：
`backtest_btc_equity/drawdown/trades/returns_dist/monthly_heatmap/yearly/underwater/dashboard.png`、`backtest_pair_equity/dashboard.png`、`backtest_param_heatmap.png`、`backtest_aapl_dashboard_params.png`、`backtest_multitf_dashboard.png`

**运行命令**：
```bash
cd frontend && python -m pytest tests/test_backtest_viz_iface.py tests/test_backtest_viz_mpl.py \
    tests/test_backtest_viz_advanced.py tests/test_backtest_viz_dashboard.py -v
# 76 passed (合成数据)

cd frontend && python -m pytest tests/test_backtest_viz_online.py -v
# 17 passed (在线真实数据，需代理 http://127.0.0.1:8889)
```

---

## 代理实现说明

### 新增文件
- `backend/stockstat_backend/adapters/yahoo_direct.py` — Yahoo Finance 直连 API 适配器（绕过 yfinance cookie/crumb 限制）
- `frontend/stockstat/backtest/` — 回测子系统（21 个模块，含可视化）
  - 核心回测：`engine/context/data_feed/strategy/orders/broker/portfolio/cost_model/fill_model/sizing/metrics/result/benchmark/optimizer/walkforward/montecarlo/plot_adapter`
  - 可视化：`chart_spec/chart_registry/chart_factory/null_charts/matplotlib_charts`

### 修改文件
- `backend/stockstat_backend/config.py` — 新增 `ProxyConfig` 数据类
- `backend/stockstat_backend/adapters/yfinance.py` — 支持代理注入
- `backend/stockstat_backend/adapters/ccxt_adapter.py` — 支持 `proxies` 参数
- `backend/stockstat_backend/api/routes.py` — 适配器工厂注入代理配置，新增 `/api/v1/proxy` 端点
- `frontend/stockstat/client.py` — 新增 `backtest()` 便捷方法
- `frontend/pyproject.toml` — 新增 `backtest` / `optimize` / `backtest_viz` / `backtest_full` extras

### 代理架构

```
ProxyConfig (env vars)
    ↓ proxies dict
YahooDirectAdapter → requests.Session.proxies → Yahoo API
CcxtAdapter        → exchange.proxies         → Binance API
SyntheticAdapter   → (无需代理)
```

---

*全部 292 项测试通过（原 75 + 回测 124 + 回测可视化 76 + 在线真实数据 17），真实数据验证成功。PAXG 周末涨跌幅对周一涨跌幅有弱但统计显著的独立预测力 (r≈0.2, p<0.02)，已消除方向选择偏差。回测子系统支持自定义策略、多标的、多时间尺度、成本/滑点模型、做空、参数优化与未来函数防护；可视化子系统提供 9 种图表（含仪表盘/热力图/直方图），核心零 matplotlib 硬依赖，已用真实数据（BTC/ETH/AAPL 2023-2024）生成 13 张图像验证。*
