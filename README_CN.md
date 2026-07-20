# StockStat V3.1

StockStat V3.1 是基于显式 Contracts、确定性金融 Kernel、不可变 Arrow Artifact、持久化 Dispatcher 状态机、spawn 隔离 Worker 和统一 SDK 构建的金融计算平台。

V3.1 是对已归档 V3 runtime 的破坏式替换。新代码只应使用 `StockStat.local()` 或 `StockStat.connect()`，不得导入 `legacy/` 下的包。

## 目录

- `packages/contracts`：轻量 Pydantic 协议与领域契约。
- `packages/kernel`：指标、时序分析、回测和复合实验执行。
- `packages/sdk`：公共 `stockstat` 包、Session API、DSL、迁移扫描和策略包工具。
- `packages/local`：单进程嵌入式组合。
- `services/storage`：OHLCV、Snapshot、Artifact 元数据、LocalFS 和 S3-compatible Blob。
- `services/dispatcher`：持久 Job/Stage/Work/Attempt 状态机与 HTTP/SSE 控制面。
- `services/worker`：spawn 隔离执行器和 Artifact 缓存。
- `tests_v31`：V3.1 契约、架构、Kernel、服务、E2E、故障、安全和性能测试。

大数据不经过 Dispatcher 控制消息。Storage 发布不可变 Arrow Artifact，Dispatcher 只持久化元数据和引用，Worker 直接从 Storage 获取输入。

## 安装

要求 Python 3.11 或 3.12。

```powershell
scripts\install_v31.ps1
```

## 本地使用

```python
from stockstat import StockStat

ss = StockStat.local(".stockstat-v31")
try:
    ss.data.ingest(
        "PAXG/USDT",
        source="synthetic",
        venue="synthetic",
        asset_class="crypto",
        timeframe="1d",
        start="2024-01-01",
        end="2024-06-01",
    )
    data = ss.data.selector(
        "PAXG/USDT",
        source="synthetic",
        venue="synthetic",
        asset_class="crypto",
        timeframe="1d",
        start="2024-01-01",
        end="2024-06-01",
    )
    ma20 = ss.indicators.ma(data, window=20)
finally:
    ss.close()
```

## 网络使用

```powershell
stockstat-storage --database-url sqlite:///market.db --artifact-root .stockstat-v31/artifacts
stockstat-dispatcher --database-url sqlite:///tasks.db --storage-url http://127.0.0.1:8101
stockstat-worker --dispatcher-url http://127.0.0.1:8100 --storage-url http://127.0.0.1:8101
```

```python
from stockstat import StockStat

ss = StockStat.connect(
    "http://127.0.0.1:8100",
    storage_url="http://127.0.0.1:8101",
    token="client-token",
)
```

生产环境应使用独立 Client/Worker token、PostgreSQL 和 S3-compatible Artifact Store，详见 `docs/DEPLOYMENT_CN.md` 与 `docs/OPERATIONS_CN.md`。

## 复合任务

- `ss.experiments.grid_search(...)`
- `ss.experiments.batch(...)`
- `ss.simulations.bootstrap(...)`
- `ss.validation.walk_forward(...)`

Dispatcher 持久化 fan-out/fan-in WorkUnit；Reducer 只接收上游 ArtifactRef。固定 seed 在不同 shard 数和重试顺序下保持稳定。

## DSL 与迁移

```powershell
stockstat dsl-explain "SELECT close, ma(close, 20) AS ma20 FROM ohlcv('PAXG/USDT','1d','2024-01-01','2024-02-01')"
stockstat migrate-scan path\to\old_project
stockstat strategy-package strategy.py strategy:build strategy.zip
stockstat strategy-verify strategy.zip --trusted-key PUBLIC_KEY_HEX
```

网络协议不反序列化 pickle/cloudpickle。远程 Python 策略必须是可导入或签名的模块/包。

## PAXG 迁移

`working/PAXG-Weekend-Monday-Law-v5-v31` 已完成 V3.1 原生迁移：

- 307 个真实 Binance 周一/周末样本。
- 52 策略迁移矩阵。
- 45 个 V3.1-native 策略，7 个跨 session/精确定时退出策略明确标记为 analysis-only。
- 180/180 次原生策略 × 费率回测成功。
- Search、确定性 Monte Carlo、Walk-forward 均成功。
- 新目录迁移扫描为 0 个 legacy API finding。

详见 `working/PAXG-Weekend-Monday-Law-v5-v31/RUN_REPORT.md`。

## 测试

```powershell
scripts\run_v31_tests.ps1
```

真实 PostgreSQL 测试：

```powershell
$env:STOCKSTAT_V31_POSTGRES_URL = "postgresql://user:password@host:5432/stockstat"
.venv-v31\Scripts\python.exe -m pytest tests_v31 -q
```

## 发布状态

仓库入口已切换为仅 V3.1。本机已通过 SQLite、认证网络、故障、安全、性能基线、PAXG 和真实 PostgreSQL 测试。最终验证期间 Redis/MinIO 不可达且未安装 Docker，因此生产发布仍为 **No-Go**；必须先完成 `V31design/realizeV31/P9_REPORT.md` 中的外部 S3/MinIO、部署和备份恢复演练。

## License

GNU GPL v3.0，详见 `LICENSE`。本项目仅供研究和学习，不构成投资建议。
