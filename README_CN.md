# StockStat — 可编程金融标的统计计算平台

用户可编程的股票 / 加密货币统计计算平台，**计算-存储分离 + V3 分布式计算 offload** 架构，支持本地 / 远程 / 离线 / 分布式四种部署模式。

- **统一数据接入**：yfinance 直连（85 精选标的 + 任意 ticker）/ ccxt（Binance 4,498、Coinbase 1,183 交易对）/ 合成数据
- **可编程计算**：Python 库 + SQL-like DSL（v2.0 从 `PluginRegistry` 自动反射 23 个指标）
- **回测子系统**：多标的 / 多时间尺度 / 可插拔执行模型 / 9 种可视化图表 / intrabar 撮合
- **V3 分布式计算**：`ComputeBackend` 协议透明替换；Dispatcher + Worker 跨进程；多级 Dispatcher 拓扑；抢占 / 弹性 / Autoscaler
- **三层协议栈**：Codec（JSON/Arrow/Cloudpickle/Msgpack）+ Message（Envelope）+ Transport（HTTP/InProcess/SHM/Redis）
- **零核心修改**：`BacktestEngine` / `ComputeEngine` 等零修改；Worker 直接复用；599 项原有测试零回归
- **可视化管理**：网页 SPA + TUI 终端界面 + V3 Task 监控 API

---

## V3 新增能力（P0-P7 全部完成）

| 阶段 | 内容 | 测试数 |
|------|------|--------|
| P0 | 协议骨架（Envelope / TaskSpec / Codec / Errors） | 50 |
| P1 | LocalComputeBackend + InProcessTransport | 58 |
| P2 | Dispatcher + Worker 跨进程（HTTP + 内存队列） | 83 |
| P3 | HttpTransport + RemoteComputeBackend + AutoComputeBackend | 22 |
| P4 | SharedMemoryTransport + Stream + dispatch.partial + data_dispatch | 34 |
| P5 | RedisTaskQueue + RedisTransport + MessagePack | 17 |
| P6 | 抢占 / Drain / Discover / Autoscaler / RetryPolicy | 36 |
| P7 | 多级 Dispatcher + Admin 监控 + 任务历史 | 23 |

**累计**：922 项测试通过 + 6 项 Redis 跳过

详见 [DESIGN_V3_CN.md](DESIGN_V3_CN.md)（完整设计）、[DESIGN_ARCHITECTURE_CN.md](DESIGN_ARCHITECTURE_CN.md)（架构）、[DESIGN_PROTOCOL_CN.md](DESIGN_PROTOCOL_CN.md)（协议）。

---

## 快速开始

### 1. 安装

```bash
# 后端（存储 + Dispatcher）
cd backend && pip install -e .

# 前端（计算库 + V3 协议层）
cd frontend && pip install -e .

# V3 分布式计算（可选）
pip install -e "frontend/[compute]"          # cloudpickle + psutil
pip install -e "frontend/[distributed]"      # + redis + msgpack
pip install -e worker/                       # stockstat-compute Worker 包

# 其他可选 extras
pip install -e "frontend/[matplotlib]"       # 可视化
pip install -e "frontend/[dsl]"              # DSL 解析（lark）
pip install -e "frontend/[backtest_full]"    # 回测全套
pip install rich                              # TUI 彩色表格
```

### 2. 启动后端

```bash
# 基础启动（仅 Storage）
stockstat serve --host 0.0.0.0 --port 8000

# V3 启用 Dispatcher（P2+）
STOCKSTAT_DISPATCHER_ENABLED=true stockstat serve --host 0.0.0.0 --port 8000
```

浏览器访问 `http://localhost:8000/admin/` 查看管理界面。

### 3. 启动 Worker（V3 分布式）

```bash
# 在另一台机器（或同机另一进程）
stockstat-compute worker \
    --dispatcher-url http://storage:8000 \
    --concurrency 8 \
    --alias "gpu-box-alpha" \
    --label rack=A-12
```

### 4. 使用 Client

```python
from stockstat import StockStatClient

# v1.7 行为（默认 LocalComputeBackend）
client = StockStatClient(host="localhost", port=8000)
client.ingest("BTC/USDT", source="binance", start="2024-01-01")
data = client.ohlcv("BTC/USDT")
result = client.backtest(data, strategy, initial_cash=10000)

# V3 远程计算（透明同步）
from stockstat._core.compute import RemoteComputeBackend
client = StockStatClient(
    host="localhost", port=8000,
    compute_backend=RemoteComputeBackend("http://localhost:8000"),
)
result = client.backtest(data, strategy)  # 内部 submit + wait

# V3 显式异步
task = client.compute.remote(
    "grid_search",
    symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01",
    strategy_ref=strategy_ref,
    param_grid={"short": [3, 5, 8], "long": [10, 20, 30]},
    metric="sharpe",
)
print(task.id, task.status)
result = task.wait(timeout=3600)

# V3 自动路由
from stockstat._core.compute import AutoComputeBackend, LocalComputeBackend
client = StockStatClient(compute_backend=AutoComputeBackend(
    local=LocalComputeBackend(),
    remote=RemoteComputeBackend("http://dispatch:9000"),
))
# 重型任务自动走远程，轻型走本地
```

### 5. 离线模式（无需后端）

```python
from stockstat._api.client import V2Client
from stockstat._core.storage import MemoryStorage, SQLStorage

# 内存离线
client = V2Client(mode="offline", storage=MemoryStorage())
client.ingest("BTC/USDT", source="binance", start="2024-01-01")

# 读取现有 SQLite
client = V2Client(mode="offline",
                  storage=SQLStorage(database_url="sqlite:///stockstat.db"))
```

### 6. Docker 部署

```bash
docker compose up -d
# 启动 db + redis + api + dispatcher + 4 个 worker
```

---

## 部署场景

| 场景 | Client | Dispatcher | Storage | Worker | 配置 |
|------|--------|-----------|---------|--------|------|
| A 单机全栈 | 同进程 | — | — | — | 默认 |
| B 存储分离 | 远程HTTP | — | 独立 | Client本地 | v2.1 |
| C 离线 | 本地 | — | 本地 | Client本地 | v2.1 |
| D Dispatcher+Worker | 远程HTTP | Storage同机 | 独立 | 远程 | `--enable-dispatcher` |
| E 独立Dispatcher | 远程HTTP | 独立 | 独立 | 多节点 | `stockstat-dispatcher` |
| F 多级Dispatcher | 远程HTTP | 主+子 | 独立 | 多级 | P7 |

每个场景对应一个部署测试：[tests/deployments/](tests/deployments/)

```bash
# 运行部署测试
tests/deployments/run_case_a_single_machine.bat   # Windows
./tests/deployments/run_case_a_single_machine.sh  # Linux/macOS

# V3 分布式
tests/deployments/run_case_e_dispatcher_worker.bat
tests/deployments/run_case_f_multilevel.bat
```

---

## 使用方式

StockStat 提供四种使用入口：

- **Python 库**：`StockStatClient` / `V2Client` — 全功能编程接口
- **CLI 命令行**：`stockstat` — 采集、查询、管理插件
- **DSL 查询**：SQL-like 声明式查询语言
- **V3 远程计算**：`client.compute.remote()` 异步提交 + `TaskRef`

### 采集数据

```python
client.ingest("AAPL", source="yfinance", start="2024-01-01", end="2024-12-31")
client.ingest("BTC/USDT", source="binance", start="2024-01-01", timeframe="1h")
client.ingest("MSFT", start="2024-01-01")  # 自动检测数据源
```

### 计算指标

23 个技术指标 + 8 个非线性动力学函数：

```python
sma = client.compute.ma(data.close, window=20)
rsi = client.compute.rsi(data.close, window=14)
upper, mid, lower = client.compute.bollinger(data.close, window=20, k=2.0)
sharpe = client.compute.sharpe(returns, risk_free=0.02, annualize=True)
hurst = client.compute.hurst_dfa(np.diff(np.log(path)))  # DFA Hurst 指数
```

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

<details open>
<summary>📊 经典统计图表（真实数据生成）</summary>

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

<details open>
<summary>🔬 PAXG 周末涨跌 vs 周一涨跌幅（真实数据 2022-2024）</summary>

PAXG（黄金锚定代币）周末涨跌幅（周五收盘→周日收盘）与周一的**最大涨幅**和**最大跌幅**，**独立记录**。

#### 散点图 — 涨幅与跌幅同图显示
![PAXG 周末散点图](docs/images/paxg_weekend_scatter.png)

**结果**：r(涨幅)=0.23 (p=0.004)，r(跌幅)=-0.20 (p=0.012)。均显著但较弱——周末涨跌幅对周一涨幅和跌幅有适度的独立预测力。

#### 按周末涨跌方向的涨跌幅分布
![PAXG 方向性](docs/images/paxg_directional.png)

#### 周末涨跌幅分布
![PAXG 周末直方图](docs/images/paxg_weekend_hist.png)

</details>

### DSL 查询

```python
result = client.run_dsl('''
    SELECT close, ma(close, 20) AS ma20, rsi(close, 14) AS rsi
    FROM ohlcv("BTC/USDT", "1d", "2024-01-01", "2024-12-31")
    LIMIT 30
''')
```

### 回测

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
print(res.summary())
res.render("dashboard", path="dashboard.png")
```

回测可视化提供 9 种图表类型：资金曲线、回撤、交易标注、收益分布、月度热力图、年度收益、参数网格热力图、水下曲线、综合仪表盘（2×2）。无 matplotlib 时自动降级为 `NullBacktestChartRenderer`（发告警、不崩溃）。

<details open>
<summary>📊 经典统计图表（真实数据生成）</summary>

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

<details open>
<summary>📈 回测可视化图表（真实数据生成）</summary>

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

### V3 分布式计算

```python
# 显式异步提交
task = client.compute.remote(
    "grid_search",
    symbols=["BTC/USDT"], timeframe="1d", start="2024-01-01",
    strategy_ref=strategy_ref,
    param_grid={"short": list(range(2, 22)), "long": list(range(20, 70))},
    metric="sharpe",
    dispatch_spec=DispatchSpec(split_strategy="param_wise", max_workers=4),
)
print(task.id, task.status)  # UUID + "pending" / "running" / "completed"

# 轮询 / 等待
result = task.wait(timeout=3600)
print(f"Best params: {result[0]['params']}, sharpe: {result[0]['sharpe']}")

# 流式结果（grid_search 进度）
for partial in task.stream_results():
    print(f"Progress: {partial.get('progress', 0):.0%}")

# 集群拓扑
info = client.compute.cluster_info()
for w in info["workers"]:
    print(f"  {w['alias']:20s}  {w['status']:8s}  "
          f"CPU {w['hardware']['cpu']['cores_logical']}核  "
          f"负载 {w['load'].get('cpu_percent', 0):.1f}%")
```

### V3 集群管理

```bash
# 查看集群
stockstat cluster info
stockstat cluster workers
stockstat cluster stats

# Autoscaler 指标
curl http://dispatch:8000/dispatch/autoscaler
# {"queue_depth": 15, "scale_up_recommended": true, ...}

# 任务历史
curl http://dispatch:8000/dispatch/tasks/history?limit=10
curl http://dispatch:8000/dispatch/tasks/stats
```

---

## 管理界面

### TUI 终端界面

```bash
stockstat tui                    # 连接本地服务器
stockstat tui --host 192.168.1.100
```

### 网页管理界面

浏览器访问 `http://storage-server:8000/admin/`：

| 页面 | 功能 |
|------|------|
| 概览仪表盘 | 标的数、行数、磁盘、数据覆盖甘特图、最近采集记录 |
| 数据源浏览 | 分页 + 搜索 + 批量下载 + 手动输入任意标的 |
| 本地标的 | K 线图（缩放时懒加载）+ 截选范围补全 + 导出 CSV |
| 配置 | 数据库 / 代理 / 缓存 / 磁盘 |
| 日志 | 采集历史（分页 + 过滤） |

### V3 Dispatcher 监控（P7）

启用 `STOCKSTAT_DISPATCHER_ENABLED=true` + `STOCKSTAT_ADMIN_ENABLED=true` 后：

| 端点 | 说明 |
|------|------|
| `GET /admin/api/dispatcher/cluster` | 完整集群拓扑（含 sub_dispatchers） |
| `GET /admin/api/dispatcher/tasks` | 任务历史 |
| `GET /admin/api/dispatcher/stats` | 任务统计（by_state / by_type / avg_duration） |
| `GET /admin/api/dispatcher/autoscaler` | Autoscaler 指标 + 扩缩容建议 |

---

## 数据源

| 数据源 | 类型 | 标的数目 | 时间粒度 | 范围探测 |
|--------|------|---------|---------|---------|
| `yfinance` | 股票/ETF/指数/商品/FX | 85 精选 + 手动输入 | 12 种 | ✅ Yahoo API 实测 |
| `binance` | 加密货币 | 4,498（1,479 USDT 对） | 16 种 | ✅ 首末 K 线实测 |
| `coinbase` | 加密货币 | 1,183（528 USD 对） | 7 种 | ✅ 首末 K 线实测 |
| `synthetic` | 混合 | 5 个示例 | 9 种 | ✅ 固定范围 |

---

## 可选 extras

| extras | 用途 |
|--------|------|
| `matplotlib` | 协议化可视化（延迟导入，核心零依赖） |
| `dsl` | DSL 解析器（lark） |
| `signal_processing` | PyWavelets（CWT 完整实现） |
| `backtest_full` | 回测全套（matplotlib + optuna） |
| `rich` | TUI 彩色表格 |
| `compute` | V3 本地后端（cloudpickle + psutil） |
| `distributed` | V3 分布式（compute + redis + msgpack） |

---

## 运行测试

```bash
# 后端测试
cd backend && python -m pytest tests/ -v          # 15 项

# 前端测试（含 V3）
cd frontend && python -m pytest tests/ -v          # 814 项 + 6 跳过

# 部署场景测试（6 个 Case）
cd tests/deployments
python test_case_a_single_machine.py              # 单机
python test_case_e_dispatcher_worker.py           # V3 分布式
python test_case_f_multilevel.py                  # V3 多级

# PAXG 研究验证
cd working/PAXG-Weekend-Monday-Law-v5-redo/phase2_backtest
python run_redo.py                                 # 132 次回测
python compare_v3.py                               # V3 与直调对比
```

**总计 922 项测试通过 + 6 项 Redis 跳过 + 132 次 PAXG 回测字节级一致。**

### 连接与性能测试

```bash
# 连接通路测试
python tests/test_connection.py --host localhost --port 8000

# 通讯性能测试
python tests/test_perf.py --host localhost --port 8000 --rounds 10
```

---

## 文档

- [使用文档](docs/USAGE_CN.md) — 详细示例与预期结果
- [V3 设计报告](DESIGN_V3_CN.md) — 完整设计（3057 行）
- [V3 架构设计](DESIGN_ARCHITECTURE_CN.md) — 四角色 + 三包 + 五层 + ComputeBackend
- [V3 协议设计](DESIGN_PROTOCOL_CN.md) — Envelope + TaskSpec + Codec + Transport
- [V3 阶段文档](docs/v3/) — P0-P7 每阶段实施详情
- [V3 完整总结](docs/v3/SUMMARY_FULL_CN.md) — P0-P7 全部完成总结
- [v2.1 设计报告](DESIGN_CN.md) — 原始架构（保留）
- [回测阶段文档](docs/backtest/) — BT-0 ~ BT-14 + BT-V0 ~ V3
- [部署测试](tests/deployments/README.md) — Case A-F 部署场景测试

---

## 配置

### 后端环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///stockstat.db` | 数据库连接字符串 |
| `STOCKSTAT_PROXY_ENABLED` | `false` | 启用代理 |
| `STOCKSTAT_ADMIN_ENABLED` | `true` | 启用网页管理界面 |
| `STOCKSTAT_DISPATCHER_ENABLED` | `false` | **V3** 启用 Dispatcher 插件 |
| `STOCKSTAT_DISPATCHER_QUEUE` | `memory` | **V3** 队列后端（memory/redis） |
| `STOCKSTAT_DISPATCHER_CACHE_MB` | `512` | **V3** DataCache 最大尺寸 |
| `REDIS_URL` | — | **V3** Redis 连接（queue=redis 时） |

### 前端环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKSTAT_HOST` | `localhost` | 前端默认主机 |
| `STOCKSTAT_PORT` | `8000` | 前端默认端口 |
| `STOCKSTAT_DISPATCHER_URL` | — | **V3** Worker / Client 连接 Dispatcher |
| `STOCKSTAT_TRANSPORT` | `in_process` | **V3** 传输类型（in_process/http） |

---

## 启动脚本

```bash
# 极简启动
backend/start.bat            # Windows
backend/start.sh             # Linux/macOS

# 完整配置（命令行参数 + 交互式配置）
backend/serve.bat --config   # Windows
backend/serve.sh --config    # Linux/macOS

# V3 Worker
stockstat-compute worker --dispatcher-url http://localhost:8000
```

---

## 开源许可证

本项目基于 **GNU General Public License v3.0** 开源 — 详见 [LICENSE](LICENSE)。

Copyright (C) 2026 RESBI

## 声明与免责声明

本项目——包括所有源代码、文档、测试用例和图表——均由 **GLM-5.2**（AI 助手）完整设计、实现和编写。

本软件仅供**学习和研究目的**使用，**不构成**任何财务、投资或交易建议。用户对自己的投资决策负全部责任，在做出任何投资前应咨询合格的财务专业人士。
