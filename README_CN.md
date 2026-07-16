# StockStat — 可编程金融标的统计计算平台

用户可编程的股票/加密货币统计计算平台，存储后端与计算前端分离。

## 快速开始

### 方式 A：本地开发（SQLite，无需 Docker）

```bash
# 1. 安装后端
cd backend
pip install -e .

# 2.（可选）开启代理以访问真实数据源
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http
export STOCKSTAT_PROXY_URL=http://127.0.0.1:8889

# 3. 启动 API 服务
python -m uvicorn stockstat_backend.app:app --host 0.0.0.0 --port 8000

# 4. 安装前端库（另一个终端）
cd frontend
pip install -e .
```

### 方式 B：Docker（生产部署）

```bash
docker compose up -d
# API 可通过 http://localhost:8000 访问
```

## 代理配置

后端支持 HTTP/SOCKS5 代理访问真实数据源。**默认关闭**。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `STOCKSTAT_PROXY_ENABLED` | `false` | 是否启用代理 |
| `STOCKSTAT_PROXY_TYPE` | `http` | 代理类型：`http` 或 `socks5` |
| `STOCKSTAT_PROXY_URL` | 按类型自动 | HTTP: `http://127.0.0.1:8889`，SOCKS5: `socks5://127.0.0.1:1089` |

```bash
# HTTP 代理（默认地址）
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=http

# SOCKS5 代理（默认地址）
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_TYPE=socks5

# 自定义代理
export STOCKSTAT_PROXY_ENABLED=true
export STOCKSTAT_PROXY_URL=http://192.168.1.100:8080
```

## 使用方式

### 1. 采集数据

```python
from stockstat import StockStatClient

client = StockStatClient(host="localhost", port=8000)

# 股票数据（Yahoo Finance）
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

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')
```

## 可用指标

| 类别 | 函数 | 说明 |
|------|------|------|
| 趋势 | `ma(x, window)` | 简单移动平均 |
| | `ema(x, window)` | 指数移动平均 |
| | `macd(x, fast, slow, signal)` | MACD（返回3条线） |
| 震荡 | `rsi(x, window)` | 相对强弱指数 |
| | `kdj(high, low, close, window)` | KDJ（返回3条线） |
| 波动 | `std(x, window)` | 滚动标准差 |
| | `atr(high, low, close, window)` | 平均真实波幅 |
| | `bollinger(x, window, k)` | 布林带（返回3条线） |
| 统计 | `corr(x, y)` | Pearson 相关系数 |
| | `beta(asset, benchmark, window)` | 滚动 Beta |
| | `sharpe(returns, risk_free, annualize)` | 夏普比率 |
| | `max_drawdown(close)` | 最大回撤 |
| | `var(returns, confidence)` | 历史在险价值 |
| 变换 | `returns(x)` | 收益率 |
| | `log_returns(x)` | 对数收益率 |

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
                     initial_cash=10000,
                     benchmark="BTC/USDT").run()

print(res.summary())
spec = res.plot_equity()  # 返回 PlotSpec，可被 matplotlib 渲染
```

### 自定义指标 + 多标的配对交易

```python
from stockstat.backtest import strategy, Order, BacktestEngine

@strategy
def pair_trade(ctx):
    if not ctx.history.get("init"):
        # 注册自定义指标
        def donchian(high, low, window=20):
            return high.rolling(window).max(), low.rolling(window).min()
        ctx.compute.register("donchian", donchian)
        ctx.history["init"] = True

    btc = ctx.get("BTC/USDT", "1d", lookback=60)
    eth = ctx.get("ETH/USDT", "1d", lookback=60)
    if len(btc) < 40:
        return
    spread = np.log(btc.close) - np.log(eth.close)
    z = (spread - spread.rolling(20).mean()) / spread.rolling(20).std()
    last = z.iloc[-1]
    if last > 1.5:
        ctx.broker.submit(Order("BTC/USDT", "sell", 0.1))
        ctx.broker.submit(Order("ETH/USDT", "buy", 0.1))
    # ... 平仓逻辑

res = BacktestEngine(data=data, strategy=pair_trade,
                     initial_cash=10000, allow_short=True).run()
```

### Intrabar 执行：同 bar 入场 + TP/SL 退出

`IntrabarExecution` 模型支持在 parent bar（如日线）内部用子 bar（如 1h）模拟订单撮合全生命周期——同 bar 入场 + 退出扫描 + OCO 互斥 + 订单优先级。

```python
from stockstat.backtest import (
    BacktestEngine, Strategy, IntrabarMixin, Order,
    IntrabarExecution, BinanceCost,
)

class TPStrategy(Strategy, IntrabarMixin):
    """市价入场 → intrabar 扫描 TP 限价 → 收盘兜底。"""
    def on_bar(self, ctx):
        o = ctx.current_price("PAXG/USDT", "open")
        if o is None: return
        ctx.intrabar_submit(Order("PAXG/USDT", "buy", 10.0, tag="entry"))
        ctx.history["tp"] = o * 1.01  # 1% 止盈

    def define_exits(self, entry_fill, ctx):
        tp = ctx.history.get("tp")
        return [
            Order("PAXG/USDT", "sell", entry_fill.qty,
                  order_type="limit", limit_price=tp,
                  tag="tp", exit_reason="tp", priority=1),
            Order("PAXG/USDT", "sell", entry_fill.qty,
                  order_type="market", tag="close",
                  exit_reason="close", priority=99),
        ]

res = BacktestEngine(
    data={"PAXG/USDT": {"1d": paxg_1d, "1h": paxg_1h}},
    strategy=TPStrategy(),
    initial_cash=10000,
    cost_model=BinanceCost(venue="spot"),
    execution_model=IntrabarExecution(intrabar_tf="1h", parent_tf="1d"),  # ← 显式启用
).run()
```

> 默认 `execution_model=None` 等价于 `NextBarExecution`（现有行为，完全兼容）。

### 回测能力一览

| 能力 | 说明 |
|------|------|
| 自定义策略 | `Strategy` 基类 / `@strategy` 函数装饰器 / **`IntrabarMixin`** |
| 多标的交易组 | `{symbol: {tf: df}}` Universe |
| 多时间尺度 | 自动以最细 tf 为主索引，高 tf ffill 对齐 |
| 计算库指标 | `ctx.compute` 代理 `ComputeEngine`，含 `register()` |
| 订单类型 | 市价 / 限价 / 止损 / 移动止损 / **OCO 挂单对** / **互斥 OCO** |
| 成本模型 | 比例 / 固定 / 阶梯 / 印花税 / 零成本 / **Maker/Taker 区分** / **Binance 现货合约+BNB** |
| 做空 | `allow_short=True` |
| 绩效 | Sharpe / Sortino / Calmar / 回撤 / 胜率 / 盈亏比 |
| 可视化 | `plot_equity/plot_drawdown/plot_trades` 返回 PlotSpec |
| **高级可视化** | `result.chart(name)` 返回 BacktestChartSpec；dashboard/heatmap/histogram；零 matplotlib 硬依赖 |
| 参数优化 | 网格搜索 / optuna（extras）/ 走样 / 蒙特卡洛 |
| 未来函数防护 | 默认 NextOpenFill + lookahead_audit |
| **intrabar 限价成交** | `IntrabarLimitFill`：盘中价格穿越限价即成交 |
| **intrabar 模拟器** | `IntrabarSimulator`：用更细 K 线模拟限价单成交时序 |
| **可插拔执行模型** | `ExecutionModel`：`NextBarExecution`（默认）/ `IntrabarExecution`（intrabar 子 bar 撮合） |
| **同 bar 入场+出场** | `IntrabarExecution`：parent bar 内完成入场→退出扫描全生命周期 |
| **成交后退出扫描** | `IntrabarMixin.define_exits()`：入场成交后定义 TP/SL/条件退出 |
| **订单优先级** | `Order(priority=...)`：同 bar 内 SL 优先于 TP |
| **批量回测** | `StrategyBatchRunner`：多策略/多费率并行回测 |
| **退出原因标记** | `Order(exit_reason=...)` + `result.exit_reason_stats()` |
| **DCA 基准** | `dca_equity()` 定投基准 |
| **子期间分析** | `BacktestAnalyzer.subperiod_metrics()` |
| **状态条件分析** | `BacktestAnalyzer.regime_conditional_metrics()` |
| **费率扫描** | `fee_sweep()` / `maker_taker_sweep()` |

回测设计详见 [DESIGN_CN.md §12-15](DESIGN_CN.md#12-回测子系统设计)，阶段实现文档见 [docs/backtest/](docs/backtest/)。回测可视化示例见下文 [matplotlib 可视化](#matplotlib-可视化) 章节。

## matplotlib 可视化

核心库**零硬依赖** matplotlib。可选安装：

```bash
pip install -e "frontend/[matplotlib]"
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

核心分析：PAXG（黄金锚定代币）周末涨跌幅（横轴：周五收盘→周日收盘）与周一的**最大涨幅** `(最高-开盘)/开盘` 和**最大跌幅** `(最低-开盘)/开盘`，**独立记录**（不按信号方向选择）。真实数据 2022-2024。

#### 散点图 — 涨幅与跌幅同图显示
![PAXG 周末散点图](docs/images/paxg_weekend_scatter.png)

**结果**：r(涨幅)=0.23 (p=0.004)，r(跌幅)=-0.20 (p=0.012)。均显著但较弱——周末涨跌幅对周一涨幅和跌幅有适度的独立预测力。涨组 vs 跌组均值无显著差异 (t 检验 p>0.26)。

#### 按周末涨跌方向的涨跌幅分布
![PAXG 方向性](docs/images/paxg_directional.png)

#### 周末涨跌幅分布
![PAXG 周末直方图](docs/images/paxg_weekend_hist.png)

### 回测可视化

回测可视化子系统提供 9 种图表类型，核心**零 matplotlib 硬依赖**——安装 matplotlib 后自动激活。以下图表使用真实市场数据（Binance BTC/USDT 2023-2024）生成。

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
res.render("drawdown", path="drawdown.png")

# 组合仪表盘（2×2 四面板）
res.render("dashboard", path="dashboard.png")

# 批量保存全部图表
res.render_all("./charts")

# 高级图表
res.render("returns_distribution", path="dist.png")   # 收益分布直方图
res.render("monthly_heatmap", path="monthly.png")      # 月度收益热力图
res.render("yearly_returns", path="yearly.png")        # 年度收益柱状图

# 参数网格热力图（配合 grid_search）
from stockstat.backtest.optimizer import grid_search
results = grid_search(make_engine, {"short": [3,5,8], "long": [10,20,30]}, metric="sharpe")
res.chart("parameter_heatmap", grid_results=results)  # 返回 BacktestChartSpec
res.render("parameter_heatmap", grid_results=results, path="param.png")
```

无 matplotlib 时自动降级为 `NullBacktestChartRenderer`（发告警、不崩溃）。

## 数据源

| 数据源 | 类型 | 需联网 | 标的数目 | 说明 |
|--------|------|--------|---------|------|
| `yfinance` | 股票 | 是 | 按需获取 | Yahoo Finance 直连 API，用户传入任意股票代码（AAPL、MSFT、^GSPC、…） |
| `binance` | 加密货币 | 是 | 4,498（其中 1,479 个 USDT 交易对） | Binance via ccxt |
| `coinbase` | 加密货币 | 是 | 1,183（其中 528 个 USD 交易对） | Coinbase via ccxt |
| `synthetic` | 混合 | 否 | — | 合成数据，用于离线测试 |

### 数据大小估算

| 范围 | 时间框架 | 1年行数 | 存储大小 |
|------|---------|--------|---------|
| 1 个标的 | 日线 | ~250 | ~2 KB |
| 1 个标的 | 1分钟 | ~525,000 | ~15 MB |
| Binance USDT 交易对（1,479） | 日线 | ~370,000 | ~3 MB |
| Binance USDT 交易对（1,479） | 1分钟 | ~776M | ~22 GB |
| Coinbase USD 交易对（528） | 日线 | ~132,000 | ~1 MB |
| Coinbase USD 交易对（528） | 1分钟 | ~277M | ~8 GB |

## REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/health` | GET | 健康检查（含代理状态） |
| `/api/v1/proxy` | GET | 查询代理配置 |
| `/api/v1/sources` | GET | 数据源列表 |
| `/api/v1/ingest` | POST | 采集标的数据 |
| `/api/v1/ohlcv` | GET | 查询 OHLCV 数据（json/csv） |
| `/api/v1/symbols` | GET | 已注册符号列表 |

## 运行测试

```bash
# 后端测试（真实数据 + 代理）
cd backend && python -m pytest tests/test_backend.py -v

# 前端单元测试（指标、DSL、可视化）
cd frontend && python -m pytest tests/test_frontend.py -v

# 回测测试（接口、MVP、组合、多 tf、成本、绩效、优化、12 策略、可视化、在线真实数据、引擎增强）
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

# matplotlib 图表测试（生成图片到 docs/images/）
cd frontend && python -m pytest tests/test_matplotlib_charts.py -v
```

## 文档

- [使用文档](docs/USAGE_CN.md) — 详细示例与预期结果
- [设计报告](DESIGN_CN.md) — 完整架构设计（含 [§12 回测子系统](DESIGN_CN.md#12-回测子系统设计) · [§13 回测可视化](DESIGN_CN.md#13-回测可视化子系统设计) · [§15 引擎增强与可插拔执行模型](DESIGN_CN.md#15-回测引擎增强与可插拔执行模型)）
- [回测阶段文档](docs/backtest/) — BT-0 ~ BT-14 + BT-V0 ~ V3 + 在线验证报告
- [测试报告](reports/TEST_REPORT.md) — 测试结果（361 项）
- PAXG 周末规律研究（`working/` 目录，未纳入版本控制）— v1~v5 完整研究 + 引擎改进报告，阶段报告已提取至 [docs/backtest/BT11_BT14_CN.md](docs/backtest/BT11_BT14_CN.md)

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | 数据库连接字符串 |
| `STOCKSTAT_PROXY_ENABLED` | `false` | 启用代理 |
| `STOCKSTAT_PROXY_TYPE` | `http` | `http` 或 `socks5` |
| `STOCKSTAT_PROXY_URL` | 自动 | 代理地址 |
| `STOCKSTAT_HOST` | `localhost` | 前端默认主机 |
| `STOCKSTAT_PORT` | `8000` | 前端默认端口 |

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
