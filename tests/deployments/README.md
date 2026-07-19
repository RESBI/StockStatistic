# V3 部署场景测试（Deployment Case Tests）

> **位置**：`tests/deployments/`
> **关联**：[DESIGN_V3_CN.md §18 部署场景](../../DESIGN_V3_CN.md#18-部署场景)

每个部署场景对应 **一 `.py` 测试 + 一 `.bat` + 一 `.sh` 启动器**：

- `.py`：测试主体，独立可运行，退出码 0=成功 / 1=失败
- `.bat`：Windows 启动器，配置环境变量 + 启动后端（如需）+ 调用 `.py`
- `.sh`：Linux/macOS 启动器，同上

## 场景清单

| Case | 场景 | 需要 backend？ | 需要 Worker？ | 文件 |
|------|------|---------------|--------------|------|
| **A** | 单机全栈（in-process） | 否 | 否 | `test_case_a_single_machine.py` + `run_case_a_*.bat/.sh` |
| **B** | 存储-计算分离（HTTP backend） | 是 | 否 | `test_case_b_storage_separated.py` + `run_case_b_*.bat/.sh` |
| **C** | 离线模式（local Storage） | 否 | 否 | `test_case_c_offline.py` + `run_case_c_*.bat/.sh` |
| **D** | 显式 LocalComputeBackend（V3 API 全覆盖） | 否 | 否 | `test_case_d_local_compute_backend.py` + `run_case_d_*.bat/.sh` |
| **E** | Dispatcher + Worker（跨进程） | 否（同进程模拟） | 是（后台线程） | `test_case_e_dispatcher_worker.py` + `run_case_e_*.bat/.sh` |
| **F** | 多级 Dispatcher + 监控（P7） | 否（同进程模拟） | 否 | `test_case_f_multilevel.py` + `run_case_f_*.bat/.sh` |

## 运行方式

### Windows

```cmd
:: Case A — 最快，无任何外部依赖
tests\deployments\run_case_a_single_machine.bat

:: Case B — 自动启动 backend
tests\deployments\run_case_b_storage_separated.bat

:: Case C — 离线模式
tests\deployments\run_case_c_offline.bat

:: Case D — V3 API 全覆盖
tests\deployments\run_case_d_local_compute_backend.bat

:: Case E — Dispatcher + Worker 跨进程
tests\deployments\run_case_e_dispatcher_worker.bat

:: Case F — 多级 Dispatcher + 监控
tests\deployments\run_case_f_multilevel.bat
```

### Linux / macOS

```bash
./tests/deployments/run_case_a_single_machine.sh
./tests/deployments/run_case_b_storage_separated.sh
./tests/deployments/run_case_c_offline.sh
./tests/deployments/run_case_d_local_compute_backend.sh
./tests/deployments/run_case_e_dispatcher_worker.sh
./tests/deployments/run_case_f_multilevel.sh
```

### 直接运行 Python（跳过启动器）

```bash
cd tests/deployments
python test_case_a_single_machine.py
python test_case_b_storage_separated.py --host 192.168.1.100 --port 8000
python test_case_c_offline.py
python test_case_d_local_compute_backend.py
python test_case_e_dispatcher_worker.py
python test_case_f_multilevel.py
```

## 环境变量

启动器和 `.py` 都读取以下环境变量（启动器优先级更高）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKSTAT_HOST` | `localhost` | Backend 主机 |
| `STOCKSTAT_PORT` | `8000` | Backend 端口 |
| `STOCKSTAT_USE_HTTPS` | （空） | `1`/`true` 启用 HTTPS |
| `STOCKSTAT_TRANSPORT` | `in_process` | V3 传输类型（P3+ 支持 `http`） |
| `STOCKSTAT_DISPATCHER_ENABLED` | `false` | 是否启用 Dispatcher 插件 |
| `STOCKSTAT_DISPATCHER_URL` | （空） | Dispatcher URL（P3+） |
| `STOCKSTAT_SKIP_NETWORK` | `false` | `true` 跳过网络相关步骤 |
| `STOCKSTAT_TEST_SYMBOL` | `BTC/USDT` | 测试用标的 |
| `STOCKSTAT_TEST_START` | `2024-01-01` | 测试数据起始日期 |
| `STOCKSTAT_TEST_END` | `2024-12-31` | 测试数据结束日期 |

## 测试覆盖

### Case A：单机全栈

- `StockStatClient` 默认 `LocalComputeBackend`
- `V2Client(mode="offline")` 默认 `LocalComputeBackend`
- `cluster_info()` 返回单 worker in-process 拓扑
- `ComputeEngine` 40+ 指标方法不变（v1.7 兼容）
- `backtest()` 默认同步路径返回 `BacktestResult`
- `compute.remote("backtest")` → `TaskRef` → `BacktestResult`
- `compute.remote("indicator")` → `pd.Series`
- `compute.remote("custom")` → 确认响应
- LocalComputeBackend 与直调 `BacktestEngine` 数值一致
- `InProcessTransport.make_pair()` 双向通信

### Case B：存储-计算分离

- Backend 健康检查（RTT 测量）
- 数据源列表
- Ingest + query 往返
- 本地 compute 用 HTTP 拉的数据
- 本地 backtest 用 HTTP 拉的数据
- V3 `compute.remote()` 用 HTTP 拉的数据
- `cluster_info()` 显示本地 worker

### Case C：离线模式

- `V2Client(mode="offline", storage=MemoryStorage())`
- 离线 ingest 通过 synthetic 适配器
- `storage.upsert()` + `ohlcv()` 查询往返
- 离线 `ComputeEngine` 用本地数据
- 离线 backtest（默认 LocalComputeBackend）
- 离线 V3 `compute.remote()`
- 离线 `cluster_info()`
- `SQLStorage` 读取现有 SQLite 文件

### Case D：显式 LocalComputeBackend（V3 API 全覆盖）

- 显式注入 `LocalComputeBackend` 到 `StockStatClient` / `V2Client`
- `TaskRef` 完整生命周期（submit / get / wait / result / ready / status）
- 任务取消（`cancel()`）
- 流式结果（`stream_results()`）
- `async_submit=True` 透明模式
- 4 种任务类型 via `compute.remote()`（indicator / backtest / grid_search / custom）
- `InProcessTransport` request/reply 模式
- `Envelope` 编解码（JSON + Msgpack）

### Case E：Dispatcher + Worker（跨进程）

- 启动 Dispatcher（FastAPI TestClient + DispatcherPlugin）
- 启动 Worker（后台线程，HTTP 轮询 assign）
- `RemoteComputeBackend` via `HttpTransport` 提交任务
- Custom / Backtest / Indicator 三种任务类型 e2e
- 远程回测与直调 `BacktestEngine` 数值一致（精度 1e-6）
- `async_submit=True` 透明模式
- Dispatcher `/dispatch/tasks/stats` 端点可用

### Case F：多级 Dispatcher + 监控（P7）

- 启动父 Dispatcher（admin + dispatcher 双启用）
- 注册子 Dispatcher（`POST /dispatch/sub/register`）
- `cluster_info()` 包含 `sub_dispatchers` 拓扑
- 任务历史记录 + 状态/类型统计
- Autoscaler 指标端点
- Admin `/admin/api/dispatcher/*` 路由可用
- `cluster.discover` 服务发现端点

## 共享辅助模块

`_common.py` 提供：

- `EnvConfig` — 环境变量解析
- `TestRunner` — 步骤化测试运行器（pass/fail/skip 计数）
- `assert_v3_compute_backend(client, expected_name)` — V3 断言
- `assert_cluster_info_shape(info)` — cluster_info 结构断言
- `make_synthetic_data()` — 合成 OHLCV 数据（无网络）
- `make_ma_cross_strategy()` — 测试用 MA cross 策略工厂
- `encode_strategy(strategy)` — cloudpickle 编码为 `strategy_ref`
- 彩色打印辅助：`banner` / `step` / `ok` / `fail` / `warn` / `info`

## 设计原则

1. **零外部依赖**：Case A/C/D 不需要任何 backend 进程，`pip install stockstat` 即可运行
2. **网络容忍**：所有网络相关步骤在 `STOCKSTAT_SKIP_NETWORK=true` 时优雅跳过
3. **跨平台**：每个 Case 都有 `.bat`（Windows）和 `.sh`（Linux/macOS）启动器
4. **独立可运行**：`.py` 脚本不依赖 pytest，直接 `python xxx.py` 即可
5. **退出码语义**：0=全部通过，1=有失败（CI 友好）
6. **V3 全覆盖**：Case D 专门测试 V3 新增的 API 表面

## 与 pytest 测试的关系

`frontend/tests/test_v3_*.py` 是 pytest 单元/集成测试（用于 CI）。
`tests/deployments/` 是**部署场景验证**（用于人工或 CI 部署后验证）：

| 维度 | `frontend/tests/test_v3_*.py` | `tests/deployments/` |
|------|------------------------------|---------------------|
| 类型 | pytest 单元/集成测试 | 部署场景验证脚本 |
| 运行方式 | `pytest tests/` | `python test_case_xxx.py` 或 `run_case_xxx.bat` |
| 退出码 | pytest 控制 | 0/1 |
| 外部依赖 | 无 | Case B 需 backend |
| 覆盖重点 | 协议正确性 / 兼容性矩阵 | 端到端部署可用性 |
| 适用场景 | 开发期 CI | 部署后冒烟测试 |
