# StockStat — 可编程金融标的统计计算平台

用户可编程的股票 / 加密货币统计计算平台，**计算-存储分离**架构，支持本地 / 远程 / 离线三种部署模式，为未来分布式计算预留。

- **统一数据接入**：yfinance 直连（85 精选标的 + 任意 ticker 手动输入）/ ccxt（Binance 4,498、Coinbase 1,183 交易对）/ 合成数据
- **可编程计算**：Python 库 + SQL-like DSL（v2.0 从 `PluginRegistry` 自动反射 23 个指标）
- **回测子系统**：多标的 / 多时间尺度 / 可插拔执行模型 / 9 种可视化图表 / intrabar 撮合
- **计算-存储分离**：存储后端独立部署，前端库通过 HTTP 或本地 Storage 接入；**离线模式可直接从数据源下载数据或读取现有 SQLite 文件**
- **零硬依赖**：核心仅依赖 pandas / numpy / scipy；matplotlib / lark / PyWavelets / rich 走可选 extras
- **可视化管理**：网页 SPA（懒加载 K 线图 + 下载模态框 + 数据源范围实测）+ TUI 终端界面

## 快速开始

### 本地开发（SQLite，无需 Docker）

```bash
# 1. 安装后端
cd backend && pip install -e .

# 2.（可选）开启代理
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889

# 3. 启动 API 服务（默认 sqlite:///stockstat.db，数据持久化；含 Admin Plugin）
stockstat serve --host 0.0.0.0 --port 8000

# 4. 安装前端库（另一个终端）
cd frontend && pip install -e .

# 5.（可选）安装 extras
pip install -e "frontend/[matplotlib]"          # 可视化
pip install -e "frontend/[dsl]"                 # DSL 解析（lark）
pip install -e "frontend/[signal_processing]"   # 小波变换（PyWavelets）
pip install -e "frontend/[backtest_full]"       # 回测全套
pip install rich                                # TUI 彩色表格
```

启动后浏览器访问 `http://localhost:8000/admin/` 即可使用网页管理界面。

### 存储-计算分离部署

后端独立部署在网络中的任意机器上，前端通过 HTTP 访问：

```python
from stockstat import StockStatClient
client = StockStatClient(host="192.168.1.100", port=8000)

client.ingest("BTC/USDT", source="binance", start="2024-01-01")
data = client.ohlcv("BTC/USDT")
symbols = client.symbols()
```

也可通过 CLI / TUI / 浏览器访问同一后端。

### 离线模式（无需后端）

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage, SQLStorage

# 方式1：离线下载到内存
client = V2Client(mode="offline", storage=MemoryStorage())
client.ingest("BTC/USDT", source="binance", start="2024-01-01")  # 直接从 Binance 下载
df = client.ohlcv("BTC/USDT")

# 方式2：读取现有 SQLite 数据库文件
client = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///stockstat.db"))
df = client.ohlcv("BTC/USDT")

# 方式3：离线下载 + 持久化到 SQLite
client = V2Client(mode="offline", storage=SQLStorage(database_url="sqlite:///my_data.db"))
client.ingest("AAPL", source="yfinance", start="2024-01-01")
```

### Docker 生产部署

```bash
docker compose up -d
# API 可通过 http://localhost:8000 访问
```

## 使用方式

StockStat 提供三种使用入口（共享同一后端服务和数据）：

- **Python 库**：`StockStatClient` — 全功能编程接口，支持指标计算、回测、DSL、可视化
- **CLI 命令行**：`stockstat` — 无需写 Python 即可采集、查询、管理插件
- **DSL 查询**：SQL-like 声明式查询语言 — 一行完成数据查询 + 指标计算

### 采集数据

支持多数据源（yfinance / Binance / Coinbase / 合成数据），自动检测数据源类型（含 `/` → 加密货币，否则 → 股票）。每个数据源支持多种时间粒度（Binance 16 种：1s ~ 1M；yfinance 12 种：1m ~ 3mo）。采集前可通过 `probe_range()` 实测数据源中该标的的实际可用时间范围。

```python
from stockstat import StockStatClient
client = StockStatClient(host="localhost", port=8000)

# 股票（Yahoo Finance 直连，支持任意 ticker：AAPL / ^GSPC / 600519.SS / GC=F / JPY=X）
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")

# 加密货币（Binance，支持 16 种时间粒度：1s/1m/3m/5m/15m/30m/1h/2h/4h/6h/8h/12h/1d/3d/1w/1M）
client.ingest("BTC/USDT", source="binance", start="2024-01-01", timeframe="1h")

# 自动检测数据源（股票→yfinance，加密货币→binance）
client.ingest("MSFT", start="2024-01-01", end="2024-06-30")
```

```bash
# CLI 等价命令
stockstat ingest AAPL --source yfinance --start 2024-01-01 --end 2024-12-31
stockstat ingest BTC/USDT --source binance --start 2024-01-01 --tf 1h
```

### 查询数据

支持时间范围过滤、时间粒度选择、返回条数限制，以及 `order=asc/desc` 双向分页（用于 K 线图懒加载场景）。查询结果为 pandas DataFrame，时间索引按升序排列。支持 JSON / CSV 两种输出格式。

```python
data = client.ohlcv("AAPL", start="2024-01-01", timeframe="1d")
# 双向分页（懒加载场景）
recent = client.ohlcv("BTC/USDT", limit=500, order="desc")  # 最近 500 根
earlier = client.ohlcv("BTC/USDT", end="2024-01-01", limit=1000, order="desc")  # 更早的 1000 根

# 批量查询多个标的
batch = client.ohlcv_batch(["BTC/USDT", "ETH/USDT"], start="2024-01-01")
```

```bash
stockstat query BTC/USDT --limit 5
stockstat query AAPL --start 2024-01-01 --format csv
```

### 计算指标

内置 23 个技术指标，涵盖趋势（MA / EMA / MACD）、震荡（RSI / KDJ）、波动率（布林带 / ATR / STD）、统计（Beta / Sharpe / 最大回撤 / VaR / 相关性）、变换（收益率 / 对数收益率）五大类别。所有指标接受 pandas Series 输入，返回 Series 或标量。

```python
# 趋势指标
sma = client.compute.ma(data.close, window=20)
ema = client.compute.ema(data.close, window=12)
macd_line, signal_line, hist = client.compute.macd(data.close)

# 震荡指标
rsi = client.compute.rsi(data.close, window=14)
k, d, j = client.compute.kdj(data.high, data.low, data.close, window=9)

# 波动率指标
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
atr = client.compute.atr(data.high, data.low, data.close, window=14)

# 统计指标
beta = client.compute.beta(stock_returns, market_returns, window=60)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
dd = client.compute.max_drawdown(data.close)
var_95 = client.compute.var(returns, confidence=0.95)

# 注册自定义指标
@client.compute.register("volatility_regime", category="custom")
def volatility_regime(data, window=20, threshold=0.04):
    vol = data.close.pct_change().rolling(window).std()
    return vol.apply(lambda v: "high" if v > threshold else "low")
```

### DSL 查询（v2.0 自动反射）

SQL-like 声明式查询语言，一行完成数据查询 + 指标计算。v2.0 的 `DslEngine` 从 `PluginRegistry` 自动反射全部 23 个已注册指标（含 8 个非线性指标），比 v1.7 的 15 个硬编码函数更丰富。支持 `SELECT ... FROM ... WHERE ... LIMIT` 语法，支持关键字参数。

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')

# 带 WHERE 过滤
result = client.run_dsl('''
    SELECT close, volume
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    WHERE close > 100000
''')
```

> 注册新指标到 `PluginRegistry` 后，调用 `engine.refresh()` 即可 DSL 自动可用，无需手动维护函数映射表。

### 回测

功能完整的量化回测引擎，支持：多标的交易组、多时间尺度 K 线（最细 tf 为主索引，高 tf ffill 对齐）、6 种订单类型（市价 / 限价 / 止损 / 移动止损 / OCO / 互斥 OCO）、8 种成本模型（含 Binance 现货/合约 + BNB 折扣 4 预设）、7 种成交模型、可插拔执行模型（`NextBarExecution` 默认 / `IntrabarExecution` 同 bar 入场+出场）、做空、未来函数防护、参数网格搜索、批量回测、退出原因分析、子期间/状态分析、DCA 基准、费率扫描。策略内可通过 `ctx.compute` 复用全部 23 个指标。

```python
from stockstat.backtest import BacktestEngine, strategy, Order

@strategy
def ma_cross(ctx):
    d = ctx.get("BTC/USDT", "1d", lookback=30)
    if len(d) < 21: return
    ma5, ma20 = d.close.rolling(5).mean().iloc[-1], d.close.rolling(20).mean().iloc[-1]
    pos = ctx.portfolio.get_position("BTC/USDT")
    if ma5 > ma20 and pos.qty == 0:
        ctx.broker.submit(Order("BTC/USDT", "buy", 0.1))
    elif ma5 < ma20 and pos.qty > 0:
        ctx.broker.submit(Order("BTC/USDT", "sell", pos.qty))

res = client.backtest({"BTC/USDT": {"1d": data}}, ma_cross, initial_cash=10000)
print(res.summary())  # Sharpe / Sortino / Calmar / 回撤 / 胜率 / 盈亏比
res.render("dashboard", path="dashboard.png")  # 9 种图表，安装 matplotlib 后自动激活
```

回测可视化提供 9 种图表类型：资金曲线、回撤、交易标注、收益分布、月度热力图、年度收益、参数网格热力图、水下曲线、综合仪表盘（2×2）。无 matplotlib 时自动降级为 `NullBacktestChartRenderer`（发告警、不崩溃）。

<details>
<summary>📊 经典统计图表（真实数据生成，点击展开）</summary>

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

</details>

<details>
<summary>📈 回测可视化图表（真实数据生成，点击展开）</summary>

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

</details>

### 信号处理与非线性动力学

8 个高级分析函数，涵盖信号处理（连续小波变换 CWT / 谱熵 / 灰色关联度 / GM(1,1) 灰色预测）和非线性动力学（传递熵 / Hurst 指数 DFA / 样本熵 / 排列熵）。未安装 PyWavelets 时 CWT 自动降级为基于 FFT 的自实现 Morlet 小波。还提供 3 个 PlotSpec 工厂函数（CWT 时频热力图 / DFA 拟合图 / 功率谱密度图）。

```python
import numpy as np
path = data.close.values[-48:]

# 信号处理
coef, scales = client.compute.wavelet_decompose(path, scales=np.arange(1, 25))  # 连续小波变换
h_spec = client.compute.spectral_entropy(np.diff(np.log(path)))                  # 谱熵（频域复杂度）
gr = client.compute.grey_relation(path_a, path_b, rho=0.5)                       # 灰色关联度（形态相似性）
forecast = client.compute.gm11_predict(sequence)                                  # GM(1,1) 灰色预测

# 非线性动力学
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))    # Hurst 指数（≈0.5 随机 | >0.5 持久 | <0.5 反持久）
te = client.compute.transfer_entropy(btc_rets, eth_rets)   # 传递熵（有向信息流）
sampen = client.compute.sample_entropy(signal, m=2)         # 样本熵
permen = client.compute.permutation_entropy(signal, m=3)    # 排列熵

# 可视化
spec = client.compute.wavelet_scalogram(coef, scales, title="CWT Scalogram")
renderer = client.plot.get_renderer()
renderer.render(spec)
```

<details>
<summary>🔬 PAXG 周末涨跌 vs 周一涨跌幅（真实数据 2022-2024，点击展开）</summary>

PAXG（黄金锚定代币）周末涨跌幅（周五收盘→周日收盘）与周一的**最大涨幅**和**最大跌幅**，**独立记录**。

#### 散点图 — 涨幅与跌幅同图显示
![PAXG 周末散点图](docs/images/paxg_weekend_scatter.png)

**结果**：r(涨幅)=0.23 (p=0.004)，r(跌幅)=-0.20 (p=0.012)。均显著但较弱——周末涨跌幅对周一涨幅和跌幅有适度的独立预测力。

#### 按周末涨跌方向的涨跌幅分布
![PAXG 方向性](docs/images/paxg_directional.png)

#### 周末涨跌幅分布
![PAXG 周末直方图](docs/images/paxg_weekend_hist.png)

</details>

## 管理界面

### TUI 终端界面

```bash
stockstat tui                    # 连接本地服务器
stockstat tui --host 192.168.1.100
```

提供 6 项交互式菜单：浏览标的 / 查询 OHLCV / 采集数据 / 数据统计 / 列出数据源 / 查看代理配置。基于 `rich`（可选安装），未安装时降级为纯文本菜单。

### 网页管理界面

浏览器访问 `http://storage-server:8000/admin/`：

| 页面 | 功能 |
|------|------|
| 概览仪表盘 | 标的数、行数、磁盘、数据覆盖甘特图、最近采集记录 |
| 数据源浏览 | 分页 + 搜索 + 批量下载 + **手动输入任意标的** |
| 本地标的 | K 线图（**缩放时懒加载**）+ 截选范围补全 + 导出 CSV |
| 配置 | 数据库 / 代理（在线修改）/ 缓存 / 磁盘 |
| 日志 | 采集历史（分页 + 过滤） |

**K 线图懒加载**：初始加载最近 500 根 → 缩放时自动加载窗口外数据（300ms 防抖 + 时间戳去重 + 加载进度显示）

**下载模态框**：自动实测数据源范围（`probe_range` 拉首末 K 线）→ 日期预填最大范围 → 动态时间粒度下拉 → 存储估算提示

## 数据源

| 数据源 | 类型 | 标的数目 | 时间粒度 | 范围探测 |
|--------|------|---------|---------|---------|
| `yfinance` | 股票/ETF/指数/商品/FX | 85 精选 + 手动输入 | 12 种 | ✅ Yahoo API 实测 |
| `binance` | 加密货币 | 4,498（1,479 USDT 对） | 16 种 | ✅ 首末 K 线实测 |
| `coinbase` | 加密货币 | 1,183（528 USD 对） | 7 种 | ✅ 首末 K 线实测 |
| `synthetic` | 混合 | 5 个示例 | 9 种 | ✅ 固定范围 |

## 可选 extras

| extras | 用途 |
|--------|------|
| `matplotlib` | 协议化可视化（延迟导入，核心零依赖） |
| `dsl` | DSL 解析器（lark） |
| `signal_processing` | PyWavelets（CWT 完整实现） |
| `backtest_full` | 回测全套（matplotlib + optuna） |
| `rich` | TUI 彩色表格 |

## 运行测试

```bash
cd backend && python -m pytest tests/ -v          # 后端 15 项
cd frontend && python -m pytest tests/ -v          # 前端 491 项
```

**总计 506 项测试，全部通过。**

### 连接与性能测试

项目附带两个集成测试脚本，用于验证前后端通讯通路和测量通讯性能：

```bash
# 连接通路测试：健康检查 → 下载标的数据 → 查询 → 计算指标 → DSL → 回测 → 可视化
python tests/test_connection.py --host localhost --port 8000
python tests/test_connection.py --host 192.168.1.100 --port 8000   # 远程后端

# 通讯性能测试：RTT 延迟 → 查询延迟 vs 数据量 → 传输速度 → 抖动分布
python tests/test_perf.py --host localhost --port 8000 --rounds 10
```

详见 [使用文档 §17](docs/USAGE_CN.md#17-连接与性能测试)。

## 启动脚本

后端提供极简启动脚本和完整配置脚本：

```bash
# 极简启动（改环境变量后直接运行）
backend/start.bat            # Windows
backend/start.sh             # Linux/macOS

# 完整配置（命令行参数 + 交互式配置）
backend/serve.bat --config   # Windows
backend/serve.sh --config    # Linux/macOS
```

## 文档

- [使用文档](docs/USAGE_CN.md) — 详细示例与预期结果
- [设计报告](DESIGN_CN.md) — 完整架构设计（含分布式计算预留）
- [回测阶段文档](docs/backtest/) — BT-0 ~ BT-14 + BT-V0 ~ V3
- [计算卸载规划](reports/COMPUTE_OFFLOAD_PLAN_V2_CN.md) — 分布式计算架构设计

## 配置

### 后端环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | 数据库连接字符串 |
| `STOCKSTAT_PROXY_ENABLED` | `false` | 启用代理 |
| `STOCKSTAT_ADMIN_ENABLED` | `true` | 启用网页管理界面 |

### 前端环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKSTAT_HOST` | `localhost` | 前端默认主机 |
| `STOCKSTAT_PORT` | `8000` | 前端默认端口 |

---

## 开源许可证

本项目基于 **GNU General Public License v3.0** 开源 — 详见 [LICENSE](LICENSE)。

Copyright (C) 2026 RESBI

## 声明与免责声明

本项目——包括所有源代码、文档、测试用例和图表——均由 **GLM-5.2**（AI 助手）完整设计、实现和编写。

本软件仅供**学习和研究目的**使用，**不构成**任何财务、投资或交易建议。用户对自己的投资决策负全部责任，在做出任何投资前应咨询合格的财务专业人士。
