# StockStat — 可编程金融标的统计计算平台

用户可编程的股票/加密货币统计计算平台，存储后端与计算前端分离。v2.0 采用五层架构（通用核心 / 金融领域 / 可视化 / 接口 / 应用），插件化扩展，支持 CLI 与离线模式。

## 快速开始

### 方式 A：本地开发（SQLite，无需 Docker）

```bash
# 1. 安装后端
cd backend && pip install -e .

# 2.（可选）开启代理以访问真实数据源
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889

# 3. 启动 API 服务（默认 sqlite:///stockstat.db，数据持久化到文件）
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
# 或使用 v2.0 CLI:
stockstat serve --host 0.0.0.0 --port 8000

# 4. 安装前端库（另一个终端）
cd frontend && pip install -e .

# 5.（可选）安装 extras
pip install -e "frontend/[matplotlib]"          # 可视化
pip install -e "frontend/[dsl]"                 # DSL 解析（lark）
pip install -e "frontend/[signal_processing]"   # 小波变换（PyWavelets）
pip install -e "frontend/[backtest_full]"       # 回测全套（matplotlib + optuna）
```

### 方式 B：网络远程部署（storage 服务单独在一台机器上）

后端可独立部署在网络中的任意机器上，其他机器通过 HTTP 访问：

```bash
# === 在 storage 服务器上（如 192.168.1.100）===
cd backend && pip install -e .
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000
# 数据持久化到 stockstat.db 文件，关闭后重启自动读取
```

```python
# === 在用户机器上 ===
from stockstat import StockStatClient
client = StockStatClient(host="192.168.1.100", port=8000)

client.ingest("BTC/USDT", source="binance", start="2024-01-01")  # 通过 API 下载
data = client.ohlcv("BTC/USDT")                                   # 通过 API 查询
symbols = client.symbols()                                        # 列出已下载标的
```

### 方式 C：离线模式（无需后端）

v2.0 的 `V2Client` 支持纯离线模式，直接使用本地 Storage：

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage

client = V2Client(mode="offline", storage=MemoryStorage())
# ohlcv / compute / run_dsl / backtest / plot 全部本地运行，无需 HTTP
```

### 方式 D：Docker（生产部署）

```bash
docker compose up -d
# API 可通过 http://localhost:8000 访问
```

## CLI 命令行（v2.0 新增）

```bash
stockstat serve --host 0.0.0.0 --port 8000      # 启动 API 服务器
stockstat ingest BTC/USDT --source binance       # 命令行采集
stockstat query BTC/USDT --limit 5               # 查询并输出
stockstat plugins --namespace indicators         # 列出已注册插件
stockstat indicators --category nonlinear        # 按类别列出指标
```

## 可选 extras

| extras | 安装命令 | 用途 |
|--------|---------|------|
| `matplotlib` | `pip install stockstat[matplotlib]` | 协议化可视化（延迟导入，核心零依赖） |
| `dsl` | `pip install stockstat[dsl]` | DSL 解析器（lark） |
| `signal_processing` | `pip install stockstat[signal_processing]` | PyWavelets（CWT 完整实现） |
| `backtest_full` | `pip install stockstat[backtest_full]` | 回测全套（matplotlib + optuna） |

## 代理配置

后端支持 HTTP/SOCKS5 代理访问真实数据源。**默认关闭**。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `STOCKSTAT_PROXY_ENABLED` | `false` | 是否启用代理 |
| `STOCKSTAT_PROXY_TYPE` | `http` | 代理类型：`http` 或 `socks5` |
| `STOCKSTAT_PROXY_URL` | 按类型自动 | HTTP: `http://127.0.0.1:8889`，SOCKS5: `socks5://127.0.0.1:1089` |

## 使用方式

### 1. 采集数据

```python
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)

# 股票数据（Yahoo Finance 直连）
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
client.ingest("^GSPC", source="yfinance", start="2023-01-01", end="2024-12-31")

# 加密货币数据（Binance）
client.ingest("BTC/USDT", source="binance", start="2024-01-01", end="2024-12-31")
client.ingest("ETH/USDT", source="binance", start="2024-01-01", end="2024-12-31")
client.ingest("PAXG/USDT", source="binance", start="2022-01-01", end="2024-12-31")

# 自动检测数据源（股票→yfinance，加密货币→binance）
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")
```

### 2. 查询 OHLCV 数据

```python
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")
#                    open    high     low   close     volume
# ts
# 2024-01-02  187.15  188.44  183.89  184.25  82488700
# 2024-01-03  184.22  185.88  183.43  184.40  58414500
```

### 3. 计算指标

```python
sma = client.compute.ma(data.close, window=20)
rsi = client.compute.rsi(data.close, window=14)
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
beta = client.compute.beta(asset_returns, benchmark_returns, window=60)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
dd = client.compute.max_drawdown(data.close)
```

### 4. DSL 查询

> DSL 基于 lark，需 `pip install stockstat[dsl]`。v2.0 支持从 PluginRegistry 自动反射所有已注册指标。

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')
```

### 5. 信号处理与非线性动力学

```python
import numpy as np

# 周末 48h 收盘价路径
path = data.close.values[-48:]

# 小波多尺度分解
coef, scales = client.compute.wavelet_decompose(path, scales=np.arange(1, 25))

# 谱熵（频域复杂度）
h_spec = client.compute.spectral_entropy(np.diff(np.log(path)))

# 灰色关联度（路径形态相似性）
gr = client.compute.grey_relation(path, reference_path)

# Hurst 指数（路径持久性）
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))

# 传递熵（周末→周一信息流）
te = client.compute.transfer_entropy(weekend_returns, monday_returns)
```

## 可用指标

### 内置技术指标（Python 库 + DSL 通用）

| 类别 | 函数 | 说明 | DSL 可用 |
|------|------|------|---------|
| 趋势 | `ma(x, window)` | 简单移动平均 | ✅ |
| | `ema(x, window)` | 指数移动平均 | ✅ |
| | `macd(x, fast, slow, signal)` | MACD（返回3条线） | ✅ |
| 震荡 | `rsi(x, window)` | 相对强弱指数 | ✅ |
| | `kdj(high, low, close, window)` | KDJ（返回3条线） | ❌ 仅 Python |
| 波动 | `std(x, window)` | 滚动标准差 | ✅ |
| | `atr(high, low, close, window)` | 平均真实波幅 | ✅ |
| | `bollinger(x, window, k)` | 布林带（返回3条线） | ✅ |
| 统计 | `corr(x, y)` | Pearson 相关系数 | ✅ |
| | `beta(asset, benchmark, window)` | 滚动 Beta | ❌ 仅 Python |
| | `sharpe(returns, risk_free, annualize)` | 夏普比率 | ❌ 仅 Python |
| | `max_drawdown(close)` | 最大回撤 | ❌ 仅 Python |
| | `var(returns, confidence)` | 历史在险价值 | ❌ 仅 Python |
| 变换 | `returns(x)` | 收益率 | ✅ |
| | `log_returns(x)` | 对数收益率 | ✅ |

### 信号处理与非线性动力学（仅 Python 库）

| 类别 | 函数 | 说明 |
|------|------|------|
| 信号处理 | `wavelet_decompose(signal, scales, wavelet)` | 连续小波变换（CWT） |
| | `spectral_entropy(signal, fs, nperseg)` | 谱熵（频域复杂度） |
| | `grey_relation(x0, xi, rho)` | 灰色关联度（路径形态相似性） |
| | `gm11_predict(sequence)` | GM(1,1) 灰色预测 |
| 非线性动力学 | `transfer_entropy(x, y, k, n_bins)` | 传递熵（有向信息流） |
| | `hurst_dfa(signal)` | Hurst 指数（DFA 法） |
| | `sample_entropy(signal, m, r)` | 样本熵 |
| | `permutation_entropy(signal, m, tau)` | 排列熵 |
| PlotSpec 工厂 | `wavelet_scalogram(coef, scales, title, cmap)` | CWT 时频热力图（返回 PlotSpec） |
| | `dfa_fit(signal, title)` | DFA 双对数拟合图（返回 PlotSpec） |
| | `psd_plot(signal, fs, nperseg, title)` | 功率谱密度图（返回 PlotSpec） |

> **信号处理与非线性动力学**模块需要可选依赖 `pip install stockstat[signal_processing]`（安装 PyWavelets）。未安装时 CWT 自动降级为基于 FFT 的自实现 Morlet 小波。

## v2.0 插件系统

v2.0 的所有可扩展点统一注册到 `PluginRegistry`，可通过 CLI 或代码查询：

```bash
$ stockstat plugins
Namespace            Name                      Category
--------------------------------------------------------------------
sources              yfinance                  sources
sources              binance                   sources
sources              coinbase                  sources
sources              synthetic                 sources
indicators           ma                        trend
indicators           rsi                       oscillator
indicators           hurst_dfa                 nonlinear
...
cost_models          percent                   cost
cost_models          binance                   cost
fill_models          next_open                 fill
execution_models     next_bar                  execution
renderers            matplotlib                renderers

Total: 45 plugin(s)
```

```python
# 代码中查询
from stockstat._core.plugin import PluginRegistry
from stockstat._domain.indicators import register_default_indicators, list_indicators

reg = PluginRegistry()
register_default_indicators(reg)
print(list_indicators(reg, category="nonlinear"))
```

## 回测

回测子系统（`stockstat.backtest`）支持自定义策略、多标的交易组、多时间尺度 K 线，并在策略内直接复用计算库的全部指标。

### 快速示例：双均线交叉

```python
from stockstat import StockStatClient
from stockstat.backtest import BacktestEngine, strategy, Order

client = StockStatClient(host="localhost", port=8000)
data = {"BTC/USDT": {"1d": client.ohlcv("BTC/USDT", start="2024-01-01")}}

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21:
        return
    ma5  = d.close.rolling(5).mean().iloc[-1]
    ma20 = d.close.rolling(20).mean().iloc[-1]
    pos  = ctx.portfolio.get_position("BTC/USDT")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

# 方式 A：通过 client 便捷入口（自动注入 ComputeEngine）
res = client.backtest(data, ma_cross, initial_cash=10000)

# 方式 B：直接构造引擎
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

print(res.summary())
spec = res.plot_equity()  # 返回 PlotSpec，可被 matplotlib 渲染
```

### 回测能力一览

| 能力 | 说明 |
|------|------|
| 自定义策略 | `Strategy` 基类 / `@strategy` 函数装饰器 / `IntrabarMixin` |
| 多标的交易组 | `{symbol: {tf: df}}` Universe |
| 多时间尺度 | 最细 tf 为主索引，高 tf ffill 对齐 |
| 订单类型 | 市价 / 限价 / 止损 / 移动止损 / OCO / 互斥 OCO |
| 成本模型 | 比例 / 固定 / 阶梯 / 印花税 / 零成本 / Maker/Taker / Binance 现货合约+BNB |
| 做空 | `allow_short=True` |
| 绩效 | Sharpe / Sortino / Calmar / 回撤 / 胜率 / 盈亏比 |
| 可视化 | 9 种图表 + dashboard；零 matplotlib 硬依赖 |
| 参数优化 | 网格搜索 / optuna（extras）/ 走样 / 蒙特卡洛 |
| 未来函数防护 | 默认 NextOpenFill + lookahead_audit |
| 可插拔执行 | `NextBarExecution`（默认）/ `IntrabarExecution`（intrabar 子 bar 撮合） |
| 同 bar 入场+出场 | `IntrabarExecution`：parent bar 内完成全生命周期 |
| 订单优先级 | `Order(priority=...)`：SL 优先于 TP |
| 批量回测 | `StrategyBatchRunner`：多策略/多费率并行 |
| 退出原因标记 | `Order(exit_reason=...)` + `result.exit_reason_stats()` |
| DCA 基准 | `dca_equity()` |
| 子期间/状态分析 | `BacktestAnalyzer.subperiod_metrics()` / `regime_conditional_metrics()` |
| 费率扫描 | `fee_sweep()` / `maker_taker_sweep()` |

回测设计详见 [DESIGN_CN.md §11](DESIGN_CN.md#11-回测子系统设计)，阶段文档见 [docs/backtest/](docs/backtest/)。

## matplotlib 可视化

核心库**零硬依赖** matplotlib。可选安装：

```bash
pip install stockstat[matplotlib]
```

### 协议化绘图

```python
spec = client.plot.spec(
    title="BTC Close + MA20",
    x_label="日期", y_label="价格",
    series=[
        {"name": "close", "data": data.close, "kind": "line"},
        {"name": "ma20", "data": data.close.rolling(20).mean(), "kind": "line", "color": "red"},
    ],
)
renderer = client.plot.get_renderer()  # 自动检测 matplotlib
renderer.render(spec)
renderer.savefig("btc.png")
```

### 经典统计图表（真实数据生成）

#### 收盘价 + MA + 布林带
![BTC 布林带](docs/images/btc_bollinger.png)

#### RSI 超买超卖区域
![BTC RSI](docs/images/btc_rsi.png)

#### MACD 柱状图 + 信号线
![ETH MACD](docs/images/eth_macd.png)

#### 回撤图
![BTC 回撤](docs/images/btc_drawdown.png)

#### Beta 散点图（AAPL vs 标普500）
![AAPL Beta](docs/images/aapl_beta_scatter.png)

#### BTC vs ETH 滚动相关性
![BTC ETH 相关性](docs/images/btc_eth_corr.png)

#### 标准化价格对比
![价格对比](docs/images/price_comparison.png)

### PAXG 周末涨跌 vs 周一涨跌幅（独立分析）

PAXG（黄金锚定代币）周末涨跌幅（周五收盘→周日收盘）与周一的**最大涨幅** `(最高-开盘)/开盘` 和**最大跌幅** `(最低-开盘)/开盘`，**独立记录**。真实数据 2022-2024。

#### 散点图 — 涨幅与跌幅同图显示
![PAXG 周末散点图](docs/images/paxg_weekend_scatter.png)

**结果**：r(涨幅)=0.23 (p=0.004)，r(跌幅)=-0.20 (p=0.012)。均显著但较弱——周末涨跌幅对周一涨幅和跌幅有适度的独立预测力。

#### 按周末涨跌方向的涨跌幅分布
![PAXG 方向性](docs/images/paxg_directional.png)

#### 周末涨跌幅分布
![PAXG 周末直方图](docs/images/paxg_weekend_hist.png)

### 回测可视化

回测可视化提供 9 种图表，安装 matplotlib 后自动激活。以下图表使用真实市场数据（Binance BTC/USDT 2023-2024）生成。

#### 综合仪表盘（2×2：资金曲线 + 回撤 + 收益分布 + 月度热力）
![BTC 回测仪表盘](docs/images/backtest_btc_dashboard.png)

#### 资金曲线 + 基准对比
![BTC 资金曲线](docs/images/backtest_btc_equity.png)

#### 回撤（填充区）
![BTC 回撤](docs/images/backtest_btc_drawdown.png)

#### 交易点标注（B/S 箭头）
![BTC 交易标注](docs/images/backtest_btc_trades.png)

#### 月度收益热力图
![BTC 月度热力](docs/images/backtest_btc_monthly_heatmap.png)

#### 参数网格热力图（AAPL 双均线 short × long → Sharpe）
![参数热力图](docs/images/backtest_param_heatmap.png)

#### 配对交易仪表盘（BTC/ETH）
![配对交易仪表盘](docs/images/backtest_pair_dashboard.png)

```python
res = BacktestEngine(data=data, strategy=ma_cross,
                     initial_cash=10000, benchmark="BTC/USDT").run()

# 一行渲染（自动检测 matplotlib）
res.render("equity_curve", path="equity.png")
res.render("dashboard", path="dashboard.png")

# 批量保存全部图表
res.render_all("./charts")

# 参数网格热力图
from stockstat.backtest.optimizer import grid_search
results = grid_search(make_engine, {"short": [3,5,8], "long": [10,20,30]}, metric="sharpe")
res.render("parameter_heatmap", grid_results=results, path="param.png")
```

无 matplotlib 时自动降级为 `NullBacktestChartRenderer`（发告警、不崩溃）。

## 数据源

| 数据源 | 类型 | 需联网 | 标的数目 | 说明 |
|--------|------|--------|---------|------|
| `yfinance` | 股票 | 是 | 按需获取 | Yahoo Finance 直连 API |
| `binance` | 加密货币 | 是 | 4,498（1,479 USDT 对） | Binance via ccxt |
| `coinbase` | 加密货币 | 是 | 1,183（528 USD 对） | Coinbase via ccxt |
| `synthetic` | 混合 | 否 | — | 合成数据（固定种子），离线测试 |

### 数据大小估算

| 范围 | 时间框架 | 1年行数 | 存储大小 |
|------|---------|--------|---------|
| 1 个标的 | 日线 | ~250 | ~2 KB |
| 1 个标的 | 1分钟 | ~525,000 | ~15 MB |
| Binance USDT 对（1,479） | 日线 | ~370,000 | ~3 MB |
| Binance USDT 对（1,479） | 1分钟 | ~776M | ~22 GB |

> SQLite 适合单机小规模；GB 级建议切换 TimescaleDB + Hypertable 压缩。

## REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/health` | GET | 健康检查（含代理状态） |
| `/api/v1/proxy` | GET | 查询代理配置 |
| `/api/v1/sources` | GET | 数据源列表（含代理状态） |
| `/api/v1/ingest` | POST | 采集标的数据 |
| `/api/v1/ohlcv` | GET | 查询 OHLCV 数据（json/csv） |
| `/api/v1/symbols` | GET | 已注册符号列表 |
| `/api/v1/symbols/{symbol}` | GET | 符号详情 |

## 运行测试

```bash
# 后端测试
cd backend && python -m pytest tests/test_backend.py -v

# v2.0 核心层 + 领域层 + 可视化层 + 接口层测试
cd frontend && python -m pytest tests/test_v2_core.py tests/test_v2_domain.py tests/test_v2_viz.py tests/test_v2_api.py -v

# v1.7 前端单元测试（指标、DSL、可视化）
cd frontend && python -m pytest tests/test_frontend.py tests/test_nonlinear.py -v

# 回测全套测试
cd frontend && python -m pytest tests/test_backtest_iface.py tests/test_backtest_mvp.py \
    tests/test_backtest_portfolio.py tests/test_backtest_multitf.py \
    tests/test_backtest_cost.py tests/test_backtest_metrics.py \
    tests/test_backtest_optimize.py tests/test_backtest_strategies.py \
    tests/test_backtest_viz_iface.py tests/test_backtest_viz_mpl.py \
    tests/test_backtest_viz_advanced.py tests/test_backtest_viz_dashboard.py \
    tests/test_backtest_viz_online.py \
    tests/test_backtest_p0.py tests/test_backtest_p1.py tests/test_backtest_p2.py \
    tests/test_backtest_intrabar.py -v

# 集成测试（真实数据：经典统计 + PAXG 周末相关性）
cd frontend && python -m pytest tests/test_integration.py -v -s

# matplotlib 图表测试
cd frontend && python -m pytest tests/test_matplotlib_charts.py -v
```

**总计 489 项测试，全部通过。**

## 文档

- [使用文档](docs/USAGE_CN.md) — 详细示例与预期结果
- [设计报告](DESIGN_CN.md) — 完整 v2.0 五层架构设计
- [回测阶段文档](docs/backtest/) — BT-0 ~ BT-14 + BT-V0 ~ V3 + 在线验证报告
- [测试报告](reports/) — v2.0 各阶段实现报告 + PAXG 兼容性报告

## 配置

### 后端环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | 数据库连接字符串（可切 `postgresql://...`） |
| `REDIS_URL` | （空） | Redis 连接（可选） |
| `HOST` | `0.0.0.0` | 后端监听地址 |
| `PORT` | `8000` | 后端监听端口 |
| `STOCKSTAT_DEFAULT_SOURCE` | `yfinance` | 默认数据源 |
| `STOCKSTAT_PROXY_ENABLED` | `false` | 启用代理 |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` 或 `socks5` |
| `STOCKSTAT_PROXY_URL` | 自动 | 代理地址 |

### 前端环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `STOCKSTAT_HOST` | `localhost` | 前端默认主机 |
| `STOCKSTAT_PORT` | `8000` | 前端默认端口 |
| `STOCKSTAT_API_KEY` | （空） | 可选 API key（Bearer 认证） |
| `STOCKSTAT_TIMEOUT` | `30` | HTTP 超时秒数 |
| `STOCKSTAT_USE_HTTPS` | `false` | 是否使用 HTTPS |

---

## 开源许可证

本项目基于 **GNU General Public License v3.0** 开源 — 详见 [LICENSE](LICENSE) 文件。

Copyright (C) 2026 RESBI

本程序是自由软件：你可以根据自由软件基金会发布的 GNU 通用公共许可证（第3版或更高版本）的条款重新分发和/或修改它。

本程序的发布是希望它能有用，但不提供任何保证；甚至不提供适销性或特定用途适用性的暗示保证。详情请参阅 GNU 通用公共许可证。

---

## 声明与免责声明

本项目——包括所有源代码、文档、测试用例和图表——均由 **GLM-5.2**（AI 助手）完整设计、实现和编写。所有代码通过与用户的迭代对话生成，经自动化测试套件验证，并使用真实市场数据（Yahoo Finance + Binance）进行了验证。

本软件仅供**学习和研究目的**使用，**不构成**任何财务、投资或交易建议。

- 本项目的作者和贡献者**不是**财务顾问，对因使用本软件而产生的任何财务损失或损害不承担任何责任。
- 所有统计分析和相关性分析（包括 PAXG 周末效应）均基于历史数据，**不保证**未来结果。
- 用户对自己的投资决策负全部责任，在做出任何投资前应咨询合格的财务专业人士。
- 本软件可能包含错误或不准确之处，使用风险自负。
- 市场数据来自第三方数据源（Yahoo Finance、Binance），其准确性或可用性不做保证。

**本软件按"原样"提供，不附带任何明示或暗示的保证，包括但不限于适销性、特定用途适用性保证。在任何情况下，作者或版权持有人均不对因使用本软件而产生的任何索赔、损害或其他责任承担责任。**
