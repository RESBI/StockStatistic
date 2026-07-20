# PAXG Weekend-Monday Law v1-v7 全量迁移至 StockStat V3.1 任务规划书

> 目标目录：`working/PAXG-Weekend-Monday-Law_All_v3.1/`
>
> 规划日期：2026-07-21
>
> 当前阶段：规划与验收基线冻结，尚未开始实现
>
> 对应清单：`RUN_CHECKLIST_CN.md`

## 1. 目标与完成定义

本任务将 PAXG Weekend-Monday Law v1-v7 的数据构造、指标计算、经典统计、稳健性检验、回测、机器学习、绘图和报告统一迁移到 StockStat V3.1 主路径下。

迁移完成必须满足：

1. 迁移后的研究代码、配置、运行状态和结果统一位于目标目录；若需补充可复用的 V3.1 通用能力，则改动放在现有 `packages/`/`services/` 及 `tests_v31/`，目标目录只引用这些能力，不复制实现。
2. 不导入旧 `frontend/`、`backend/`、`worker/`、`stockstat_backend` 或 `stockstat_compute`。
3. OHLCV 校验、Indicator Catalog、Job/Artifact/Arrow、Backtest、Intrabar、Binance Cost、Search、Batch、Simulation、Walk-forward 等任务优先调用 V3.1。
4. V3.1 没有原生实现的统计、机器学习和绘图可保留为研究扩展，但输入输出必须遵循 V3.1 Artifact 和可复现性约束，不得复制 V3.1 已有算法。
5. v1-v7 共用一份不可变市场数据和一份统一主研究数据集，禁止每个版本独立重建口径。
6. 每项任务都有稳定任务 ID，并产生 `succeeded`、`failed`、`skipped_gate`、`skipped_missing_input`、`insufficient_sample` 或 `awaiting_human_assessment` 状态。
7. 历史复现结果与 V3.1 规范结果分开保存。不得为匹配旧数字而引入前视、伪造样本或隐藏语义差异。
8. 后续可从任一已完成阶段恢复，不要求每次从数据导入开始重跑。

## 2. 研究范围

### 2.1 源研究映射

| 逻辑版本 | 源目录 | 迁移范围 |
|---|---|---|
| v1 | `working/PAXG-Weekend-Monday-Law/` | 按信号方向选择周一极值、Pearson、方向分组、52 周滚动和选择偏差演示 |
| v2 | `working/PAXG-Weekend-Monday-Law-v2/` | 独立 `max_gain/max_loss`、相关、t 检验、KS、分布图和共识对比 |
| v3 | `working/PAXG-Weekend-Monday-Law-v3/` | 高低点先后、第一/第二波动、极值时刻、卡方和路径图 |
| v4 | `working/PAXG-Weekend-Monday-Law-v4/` | A-F：排列、Bootstrap、信号/结果扩展、机制、断点、状态、衰减和非线性 |
| v5 | `working/PAXG-Weekend-Monday-Law-v5/` | 52 策略、4 费率、B1/B2 两个账户基准、B3 价格参考、36 个图表 ID、参数敏感性和经济意义 |
| v5 执行修正参考 | `working/PAXG-Weekend-Monday-Law-v5-redo/` | V3/V3.1 Intrabar 语义、不可变数据、旧结果对比协议 |
| v6 | `working/PAXG-Weekend-Monday-Law-v6/` | M1-M8 时序分析、18 个图表 ID、条件性 6 策略回测 |
| v7 | `working/PAXG-Weekend-Monday-Law-v7/` | W/E/G/N/F 全路线、27 个图表 ID、决策门和条件性 4 策略回测 |

旧综合报告只用于核对研究叙事和图表覆盖，不作为新代码运行依赖。

### 2.2 必须覆盖的任务类型

- 数据导入、快照、校验、血缘和质量报告。
- 周末-周一配对、6 个核心信号、周一结果、路径、时序和多尺度路径数组。
- v1-v4、v6 的全部经典统计和稳健性任务。
- v4-B3 规划中写明但旧代码未真正实现的二次路径形态任务。
- v5 52 个策略在 F1-F4 下的 208 次回测，以及 B1/B2 两个账户基准和 B3 价格参考。
- v5 所列 20 个研究问题、13 个对比维度和全部参数敏感性。
- v6 M1-M8、盲检材料生成及条件性 v6-S1 至 v6-S6。
- v7 W1-W4、E1-E4、G1-G4、N1-N5、F1-F4 和条件性 v7-S1 至 v7-S4。
- 已实现图表与规划中列出但未实现图表。
- 逐阶段机器可读摘要、中文总报告、历史差异报告和运行报告。

### 2.3 明确不做

- 不新增 v8 研究假设。
- 不把实时网络采集设为首次离线跑通的前置条件。
- 不因 XAUT、BTC 1h 或 PAXG 15min 数据不足而伪造样本。
- 不将 Matplotlib 绘图代码放入金融 Kernel。
- 不将旧报告结论硬编码为新结果。
- 不以“代码已迁移但任务没有状态产物”视为完成。

## 3. 输入基线与数据治理

### 3.1 首轮离线输入

| 输入 | 基线 | SHA-256 |
|---|---:|---|
| `paxg_1d.parquet` | 2,148 行，2020-08-28 至 2026-07-15 | `2525B80B6F0FF2E634F35176FF0A008662B6A1C2F0E5E011B04C9FEC07E61BEA` |
| `paxg_1h.parquet` | 51,520 行，至 2026-07-15 23:00 UTC | `13447A51CDD5E4A3D1E456C52CE6EB17BA16E9356D7F0D13400CB0C25CC250C5` |
| `btc_1d.parquet` | 2,151 行，至 2026-07-18 | `617B8E9AB4E0DDB2497CF622B90958BDD06CE815559B71D6327BDA12CF417823` |
| `signals.parquet` | 307 行历史派生数据 | `6A1545A7FEA18A7B925E2ECA0959E8B1AECB280AB23F5A64AC2CE1F2DC396383` |
| `dataset_v6.parquet` | 307 行历史派生数据 | `858921F96AB3C3CA5A4E0C890767F1F864C65A0180188F117265525A60F6C3DD` |
| `paths_v7.parquet` | 307 行历史派生路径数据 | `AEC1996FCE5E5667F911B27970AE0591D3D5FCD69920F686A946FF1DD405D456` |

前三项来自 `working/PAXG-Weekend-Monday-Law-v5-redo/results/`。后三项只作为 golden 和缺失原始数据时的有血缘降级输入，不能替代主数据重建。

### 3.2 样本视图

现有数据有 307 个周一，其中 303 个同时具有完整 48 根周末 1h 和 24 根周一 1h。四个不完整日期为：

- 2020-11-30：周一 23 根。
- 2020-12-21：周一 20 根。
- 2021-03-08：周末 47 根。
- 2021-04-26：周末 45 根。

统一构建三类视图：

| 视图 | 条件 | 主要用途 |
|---|---|---|
| `pairs_daily` | 日线字段完整 | v1、v2、v4-A、v4-D 日线部分和基准，预期 307 行 |
| `pairs_intraday_legacy` | 周末至少 10 根、周一至少 6 根 | 历史复现和旧结果差异定位，预期 307 行 |
| `pairs_intraday_strict` | 周末恰好 48 根、周一恰好 24 根 | V3.1 规范的 v3、v4-B/C/E/F、v6、v7，预期 303 行 |

报告必须同时列出视图名和 `n`，不得只写“307 个样本”而忽略任务实际使用的样本。

### 3.3 冻结的数据语义

- 时区统一为 UTC，输入必须为 tz-aware `DatetimeIndex`。
- 周末窗口为周六 00:00 含至周一 00:00 不含。
- `x3` 窗口为周六 12:00 含至周日 12:00 不含。
- 周一窗口为周一 00:00 含至周二 00:00 不含。
- 收益率统一使用小数存储，图表和报告再格式化为百分比。
- OHLCV 必须通过 `MarketDataset.from_arrow()` / `Universe` 的唯一索引、有限值、非负值和 OHLC 关系校验。
- 缺失 K 线不插值。严格视图排除，历史视图保留并标记 `quality_flags`。
- 若最高价和最低价出现在同一根 1h bar，历史模式按旧逻辑归为 `up_first`；规范模式标记为 `same_bar_ambiguous`，不强行推断 bar 内先后。
- 所有滚动阈值、回归和 ML 训练只使用当时可获得的数据。当前周末已结束后的 `x4` 可用于周一决策，当前周一结果不可用于阈值或模型拟合。
- 随机任务的默认根种子固定为 `42`；每个任务由 `SeedSequence([42, task_id_hash])` 派生，避免并行顺序改变结果。

### 3.4 当前数据缺口

- V3.1 Local runtime 当前没有 Binance source adapter，首轮采用不可变 Parquet Artifact。
- 没有独立 BTC 1h 快照。v6/v7 BTC 路径对照可暂用 `paths_v7.parquet` 的 `legacy_derived` 数据；获取真实快照后必须重跑。
- 没有 PAXG 15min 快照，v6-M8 必须条件性跳过，直到真实数据可用。
- XAUT 历史样本旧研究仅约 16 对，低于正式推断门槛 50；任务需保留并产出 `insufficient_sample` 状态。

## 4. V3.1 能力使用策略

### 4.1 直接调用的原生能力

| 任务 | V3.1 实现 |
|---|---|
| 市场数据规范化 | `stockstat_kernel.market.MarketDataset`、`Universe` |
| 常规指标 | `returns`、`log_returns`、`std`、`atr`、`corr`、`sharpe`、`max_drawdown` |
| v7 高级指标 | `wavelet_decompose`、`spectral_entropy`、`grey_relation`、`gm11_predict`、`transfer_entropy`、`hurst_dfa`、`sample_entropy`、`permutation_entropy` |
| 指标 Job | `finance.indicator.compute`、`finance.timeseries.analyze` |
| 单次回测 | `finance.backtest.run`、`BacktestEngine`、`StrategyRef` |
| Intrabar | `execution.intrabar`、`IntrabarExecution`、`IntrabarLimitFill`、`Fill.sub_bar_ts` |
| 订单与优先级 | Market/Limit/Stop/Stop-limit、`Order.priority`；Trailing-stop 目前只有订单类型，完整撮合语义需 K05 补齐 |
| 费率 | `cost.binance`、`BinanceCost(venue, bnb_discount, slippage)` |
| 实验 | `finance.experiment.search`、`finance.experiment.batch` |
| 重采样 | `finance.simulation.resample` |
| 前向窗口 | `finance.validation.walk_forward` |
| 结果 | Backtest `equity`、`fills`、`positions` Arrow Artifact 和 manifest digest |
| 执行入口 | `StockStat.local()`；远程环境可切换 `StockStat.connect()` |

### 4.2 需要补充的通用 V3.1 能力

这些改动应是可复用的框架能力，不写成 PAXG 专用分支：

| ID | 缺口 | 计划 |
|---|---|---|
| K01 | `x2/x3` OLS 斜率未注册 | 增加 `linear_slope@1.0` Indicator，并注册 catalog、SDK 和测试 |
| K02 | Welch 只有谱熵，没有频带特征 | 增加 `spectral_features@1.0`，输出 PSD、LF/MF/HF、重心和峰频 |
| K03 | Backtest 基础 metrics 不完整 | 增加 CAGR、Sortino、Calmar、胜率、盈亏比、平均交易收益、持仓时间和年度/月度收益派生层 |
| K04 | Batch 只保留摘要 | 支持 full detail 索引，或由项目编排提交独立 `finance.backtest.run` 并统一聚合 |
| K05 | Intrabar 复杂退出需验证 | 补充时间退出、入场后扫描、同 bar SL/TP 优先、双向触发、撤单和多日持仓测试；缺能力时做最小通用扩展 |
| K06 | 通用研究统计 Job 缺失 | 增加通用表格研究 capability，或统一研究 runner；输出必须是 Arrow + manifest |
| K07 | 绘图契约缺失 | 项目内先定义可序列化 `PlotSpec` 和 Agg renderer；不宣称是现有平台能力 |
| K08 | 本地真实数据导入缺口 | 增加 Parquet-to-Artifact 导入器；Binance 网络 adapter 作为非阻塞增强 |
| K09 | 小波相干/相位未实现 | 增加通用 `wavelet_coherence@1.0` 时序能力，输出相干矩阵、尺度/频率和相位，并以 AR(1) 测试验证 |

### 4.3 项目级研究扩展

以下能力不应为迁移而硬塞进核心金融 Kernel：

- SciPy：Pearson/Spearman、t、KS、卡方、F、排列、Bootstrap、Chow、log-rank 等。
- NumPy/Pandas：CMH、Wilson CI、BH-FDR、log-linear、RQA 和派生表格。
- scikit-learn：互信息、KMeans、轮廓系数、随机森林和分类。当前 V3.1 核心依赖未声明该库，需在项目 `requirements-research.txt` 或独立可选 extra 中固定版本。
- Matplotlib Agg：消费 Artifact 生成 PNG；图中不得重新进行隐藏的核心统计或回测。
- Markdown 报告生成：只读取已落盘的 summary/table/plot manifest。

## 5. 目标目录与产物契约

```text
working/PAXG-Weekend-Monday-Law_All_v3.1/
├── MIGRATION_PLAN_CN.md
├── RUN_CHECKLIST_CN.md
├── README.md
├── task_registry.yaml
├── semantic_decisions.md
├── source_inventory.arrow
├── legacy_semantic_differences.arrow
├── pyproject.toml                  # 仅项目包配置，若采用现有根配置则不重复
├── requirements-research.txt      # sklearn 等研究可选依赖
├── config/
│   ├── study.yaml                 # 日期、时区、视图、随机种子、模式
│   ├── fees.yaml                  # F1-F4
│   ├── strategies_v5.yaml         # S1-S52 注册表
│   └── plots.yaml                 # 全图表 ID 和依赖
├── src/paxg_weekend_monday/
│   ├── cli.py
│   ├── pipeline.py
│   ├── data.py
│   ├── dataset.py
│   ├── statistics.py
│   ├── artifacts.py
│   ├── performance.py
│   ├── plotting.py
│   ├── reporting.py
│   ├── studies/v1.py ... v7.py
│   └── strategies/v5.py, v6.py, v7.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── golden/
├── artifacts/<mode>/
│   ├── inputs/
│   ├── datasets/
│   ├── studies/v1/ ... v7/
│   ├── backtests/v5/ ...
│   └── manifests/
├── charts/<mode>/v1/ ... v7/
├── reports/
└── runs/<run_id>/
    ├── run_manifest.json
    ├── task_status.jsonl
    ├── warnings.json
    └── difference_report.json
```

### 5.1 统一表格契约

- `market.arrow`：`ts,instrument,timeframe,open,high,low,close,volume`。
- `weekend_monday_pairs.arrow`：每行一个周一，含 6 信号、6 结果、路径/时序、质量标志、样本视图字段。
- `paths.arrow`：`date,asset,segment,offset,open,high,low,close,volume,normalized_close,log_return` 长表，不使用 pickle/list object 作为主契约。
- `statistics.arrow`：`task_id,test_id,version,signal,outcome,group,n,estimate,effect_size,p_value,p_adjusted,ci_low,ci_high,status`。
- `backtest_index.arrow`：`strategy_id,fee_id,job_id,status,artifact_refs,metrics...`。
- `plot_manifest.arrow`：`plot_id,version,status,path,input_digests,width,height,renderer_version,skip_reason`。
- `task_status.jsonl`：每个任务一行，至少含状态、开始/结束时间、输入 digest、输出 refs、种子和异常。

### 5.2 运行模式

- `historical`：尽量复现旧脚本选择、容错和同 bar 规则。
- `canonical`：使用严格样本、显式模糊类别和无前视规范。
- `both`：默认验收模式，两套结果分区生成并输出差异原因。下文的回测和图表数量默认均为“每个模式”的数量；综合索引另记录两种模式合计数。

## 6. 阶段 DAG

```text
P00 预检与语义冻结
  -> P10 数据导入与快照
  -> P20 统一数据集与 golden 对比
  -> P30 V3.1 通用能力补齐
  -> P40 v1-v4 统计迁移
  -> P50 v5 回测迁移
  -> P60 v6 时序迁移
  -> P70 v7 多尺度迁移
  -> P80 全量绘图
  -> P90 报告、差异、测试与最终验收
```

P40 可在 P20 后与 P30 的非相关能力并行；P50 必须等待 Intrabar 语义测试完成；P60/P70 的统计部分可先运行，条件性回测等待 P50 基线可用。

## 7. 分阶段实施任务

### 7.1 P00：预检、清册与语义冻结

1. 建立 `source_inventory.arrow`，列出 v1-v7 的脚本、计划、报告、数据、旧结果和图表。
2. 建立 `task_registry.yaml`，为本文所有任务和清单项分配稳定 ID。
3. 建立 `semantic_decisions.md`，至少冻结：样本视图、时区、边界、同 bar 冲突、随机种子、年化因子、手续费、滑点和比较容差。
4. 对旧规划、代码、报告之间的冲突建立 `legacy_semantic_differences.arrow`。已知重点包括：
   - v5 规划称 52×4=208，旧 CSV 实际为 208 个策略费率结果加 B1/B2 两行，共 210 行。
   - B3 是价格收益参考，不应伪装成第三个独立资金账户回测。
   - v5-redo 旧结果只有 33 个策略×4加 B1，不是全量 52 策略。
   - v5 S13、S18、S30 及核心 B 的文字定义与部分旧实现存在执行差异。
   - v7 规划包含 27 个图表 ID，旧实现只有 14 张；W01 旧实现还存在占位绘图风险。
5. 冻结依赖：Python 3.11/3.12、根 V3.1 依赖、研究 optional 依赖和 Matplotlib `Agg`。

### 7.2 P10：数据导入与 V3.1 快照

1. 校验基线文件 digest、行数、schema、时区和日期范围。
2. 将 PAXG 1d/1h、BTC 1d 转为 V3.1 长表，使用 `MarketDataset.from_arrow()` 验证。
3. 通过 V3.1 Storage/Artifact 或项目 Parquet importer 注册不可变输入，manifest 记录原路径、digest、source=`legacy_binance_snapshot` 和导入时间。
4. 生成缺失条、重复条、OHLC 异常、日/小时覆盖、周末完整性和周一完整性质量报告。
5. 可选接入真实 Binance source adapter。其结果必须与固定快照分开版本化，不能覆盖基线。
6. XAUT、BTC 1h、PAXG 15min 作为独立可选输入登记；不可用时状态为 `skipped_missing_input`。

### 7.3 P20：统一研究数据集

1. 使用 V3.1 指标作业计算可直接复用的 returns、log_returns、std、ATR 等。
2. 使用新增 `linear_slope@1.0` 计算 `x2`、`x3`；`x1/x4/x5/x6` 和结果变量由统一 dataset builder 组合。
3. 构造核心信号：
   - `x1_return`：周五收盘至周日收盘收益。
   - `x2_slope`：48h 收盘 OLS 斜率。
   - `x3_mid_slope`：周六 12:00 至周日 12:00 收盘 OLS 斜率。
   - `x4_range`：周末 high-low 相对周五收盘。
   - `x5_realized_vol`：周末小时对数收益平方和开根。
   - `x6_volume`：周末成交量相对 30 日日均量的两日比值。
   - v4-B3 二次拟合系数、曲率、拟合优度和形态分类。
4. 构造周一结果：`max_gain,max_loss,open_gap,full_day_return,intraday_vol,range`。
5. 构造路径字段：high/low 时刻、`path`、`first_move`、`second_move`、首/第二极值时刻、W0-W4、窗口振幅/波动率。
6. 构造回测阈值：历史滚动 x4 中位数/Q4/Q5、ATR 分位、x4 z-score。所有 rolling 值必须显式 `shift(1)` 或证明当前值在下单前已知。
7. 构造 PAXG、BTC 周末/周一路径长表和 v7 所需 48/24 长度数组视图。
8. 输出 daily/legacy/strict 三视图和 column-level lineage。
9. 与旧 `signals.parquet`、`dataset_v6.parquet`、`paths_v7.parquet` 做逐列差异，分类为口径修正、数据修正、浮点误差或实现错误。

### 7.4 P30：V3.1 通用能力补齐

1. 实现并测试 K01-K09。
2. 高级指标必须通过 `StockStat.local().indicators` 的 Job 路径至少集成测试一次，而不仅直接调用 Python 函数。
3. 复杂回测能力必须覆盖：
   - 周一开盘入场、指定小时退出、周一收盘兜底。
   - 周五入场到周一/周三退出。
   - 限价触发时间、入场后才允许退出扫描。
   - OCO 任一成交撤另一与双方同日触发的确定性规则。
   - TP/SL 同一小时内均触发时按保守优先级处理。
   - Trailing stop、网格多订单、maker/taker 区分和成交后费用。
4. 完整绩效派生必须以 equity/fills 为唯一来源，并固定周策略年化因子为 52；B1/B2 日频基准可使用 365/252，但报告须注明。
5. 在通用能力测试通过前，不允许开始全量 208 次 v5 回测。

## 8. v1-v4 统计迁移矩阵

### 8.1 v1：方向选择与偏差演示

| ID | 任务 | 输出 |
|---|---|---|
| V1-01 | 对 x1/x2/x3 按信号符号选择 `max_gain` 或 `max_loss` | 三组 Pearson r/p、R2 |
| V1-02 | 信号正负组的选择结果均值、标准差、SEM、95% CI | 分组统计表 |
| V1-03 | 52 周滚动相关 | 滚动序列表 |
| V1-04 | 选择偏差蒙特卡洛演示：独立 X/G/L 经同样选择后产生伪相关 | 零模型分布和经验位置 |
| V1-05 | 生成每信号散点、方向分组、滚动图及三信号总比较 | 10 个图表 ID |

V1 的目的不是恢复错误结论，而是可重复演示其构造性偏差。报告必须加 `known_biased_estimator=true`。

### 8.2 v2：独立涨跌幅

| ID | 任务 | 输出 |
|---|---|---|
| V2-01 | 3 信号分别与 max_gain/max_loss 做 Pearson 与 Spearman | 6 对主结果 |
| V2-02 | 信号正负组描述统计、Welch t 检验、KS 检验和效应量 | 检验表 |
| V2-03 | 信号方向与实际方向/收益的一致率、三信号共识 | 共识表 |
| V2-04 | v1 与 v2 相关性坍塌对比 | cross comparison |
| V2-05 | 每信号散点、直方、箱线、ECDF，加相关矩阵、共识和总比较 | 15 个图表 ID |

### 8.3 v3：路径顺序

| ID | 任务 | 输出 |
|---|---|---|
| V3-01 | 严格与历史模式构造 path/first_move/second_move | 路径数据表 |
| V3-02 | 信号符号×路径的 2×2 卡方、Cramér's V | 3 组检验 |
| V3-03 | 信号与 first_move/path 的相关及分组统计 | 结果表 |
| V3-04 | high/low/first extreme 时刻分布与 same-bar 模糊性分析 | timing 表 |
| V3-05 | 每信号 5 图，加跨信号比较、路径比例、相关矩阵 | 18 个图表 ID |

### 8.4 v4-A：弱效应稳健性

- A1：`x1 -> max_gain` 双侧 10,000 次排列检验。
- A2：10,000 次 paired bootstrap 相关 95% CI。
- A3：预注册三期分割，不按结果重新选断点。
- A4：52 周滚动相关和正值比例。
- 追加效应量、随机种子、完整分布 Artifact 和四张图。

V3.1 `finance.simulation.resample` 当前只对回测 equity 做 IID bootstrap，因此 A1/A2 应由通用研究 resampling capability 执行，不能误用回测 bootstrap。

### 8.5 v4-B/C：信号与结果扩展

- 计算 6×6 Pearson/Spearman 相关矩阵、p 值、多重校正和效应量。
- 实现旧代码未完成的 B3 二次形态信号，并单独标记为 `planned_now_implemented`。
- 检验 `x1-open_gap` 的机械同义关系，防止将其解释为 alpha。
- 输出全矩阵、显著项、最佳对、散点和剂量响应。
- 至少生成 `bc_corr_heatmap`、`bc_sig_bars`；二次形态增加专用图。

### 8.6 v4-D：机制与跨资产

- 对 PAXG、BTC、XAUT 执行同口径 daily 分析。
- BTC 为阴性对照；至少比较 x1-max_gain/loss，并在有 1h 输入时扩展 x4-range。
- XAUT `n<50` 时不做确认性结论，保留描述统计并输出 `insufficient_sample`。
- 三期资产对比、资产效应量差和置换式差异检验。
- 生成资产总比较和子期间图。

### 8.7 v4-E/F：时间和非线性

- E1：固定 2024-01-01 的 Chow test，另以预注册三期结果佐证，不做事后最优断点搜索。
- E2：按 x5 中位数及 ATR 状态分析 `x4 -> range`。
- E3：用同一周末信号预测 Mon/Tue/Wed 各日振幅，修复旧循环中窗口含义易漂移的问题。
- F1：x4 五分位下 max_gain/max_loss/range 的单调剂量响应和趋势检验。
- F2：方向共识、波动率共识和全共识三层，不只保留旧“全部同号 vs mixed”。
- F3：预注册阈值与滚动阈值，报告极端组样本不足。
- 生成 Chow、状态、衰减、五分位、共识和阈值图。

## 9. v5 回测迁移

### 9.1 原则

- 52 个策略全部通过 `StrategyRef` + `finance.backtest.run` / V3.1 Batch 执行。
- 不复制旧自建 Backtester。
- 每个模式下，每个策略对 F1-F4 全部运行，共 208 次；`both` 模式综合索引共 416 行。失败也必须留有行和错误信息。
- 保存每次回测的 equity、fills、positions、metrics、config 和 manifest，不只保存聚合 CSV。
- B1 买入持有、B2 周一定投、B3 价格参考独立计算；B3 不计入 208 次。
- historical 模式对 Intrabar 策略使用 307 行 legacy 视图；canonical 模式按策略数据需求使用 daily 307 行或 strict 303 行，并在结果中记录实际样本数。

### 9.2 费率与执行场景

| ID | V3.1 配置 | Maker | Taker |
|---|---|---:|---:|
| F1 | `cost.binance(venue=spot,bnb_discount=false,slippage=0)` | 0.100% | 0.100% |
| F2 | `cost.binance(venue=spot,bnb_discount=true,slippage=0)` | 0.075% | 0.075% |
| F3 | `cost.binance(venue=futures,bnb_discount=false,slippage=0)` | 0.020% | 0.050% |
| F4 | `cost.binance(venue=futures,bnb_discount=true,slippage=0)` | 0.018% | 0.045% |

历史主结果的滑点为 0。规范结果另跑 0.05% 滑点敏感性，不得将 V3.1 `BinanceCost` 默认 0.01% 滑点混入历史复现。

### 9.3 策略组清单

| 组 | 策略 | 主要能力 |
|---|---|---|
| G1 方向 | S1-S6 | 开收盘市价、做空、共识 |
| G2 周末漂移 | S7-S8 | 跨周末持仓 |
| G3 波动率 | S9-S12 | OCO 限价、门槛、动态仓位 |
| G4-G6 | S13-S16 | 多日衰减、组合、BTC 对照 |
| G7 日内 | S17-S19 | 指定小时、网格、Intrabar |
| G8 跳空 | S20-S22 | 反转/延续 |
| G9 风控 | S23-S25 | 动态 stop、trailing、时间止损 |
| G10-G11 | S26-S29 | 跨资产信号、ATR 状态 |
| G12-G15 | S30-S36 | 共识、偏度、周末/周一网格、z-score |
| G16 核心 A | S37-S44 | 方向+TP、滚动回归、TP/SL |
| G17 核心 B | S45-S52 | 双向挂单、时间/打平/利润退出、网格 |

### 9.4 防前视要求

- S13 必须明确是三段独立仓位还是单笔递减持仓；历史与规范定义都保留，报告差异。
- S18 的“12:00 平仓”必须通过精确 sub-bar 时间实现，不能用最近 bar 静默替代。
- S30 只使用周一前已知的 x4/x5/x6 共识。
- S38 的 52 周回归、S43/S44 历史分布只用当前周一之前样本。
- S36 rolling z-score 不包含当前观测自身，除非明确证明周日收盘后已全部可知且定义就是包含当前信号。
- 所有以“最佳”“Top-5”为输入的图只在全部回测完成后选取，不反馈至策略参数。
- F1/F2 的现货做空结果必须标记为理论场景；F3/F4 合约场景按 1×、不计资金费率处理并披露限制。

### 9.5 聚合与实验

1. 每个模式生成 208 行 `strategy_fee_metrics.arrow`，另加 3 行基准/参考索引；`both` 的综合索引分别为 416 行和 6 行。
2. 计算 v5 规定的 10 项绩效及毛收益/费用/净收益分解。
3. 执行 13 个对比维度、2020-2023 vs 2024-2026、状态分层和 alpha over B1/B2/B3。
4. 使用 V3.1 Search 执行：
   - P14 x4 分位门槛。
   - P15 S9 `k`。
   - P15b 网格数。
   - P15c S23 stop multiplier。
   - P15d S39 TP 系数。
   - P15e 核心 B `k`。
5. 使用 V3.1 Simulation 对候选策略做至少 1,000 次 equity bootstrap；这是 v5 稳健性增强，不替代历史指标。
6. 使用 V3.1 Walk-forward 对可训练策略和参数做预注册窗口验证。
7. 对 52 个策略运行 `stockstat migrate-scan`，findings 必须归零或有批准豁免。

## 10. v6 时序迁移

### 10.1 M1-M8

| 模块 | 任务 | V3.1/扩展 |
|---|---|---|
| M1 | 3 信号×5 窗口，全表/单窗卡方、Cramér's V、log OR、Wilson CI、Bonferroni/BH | 研究统计 Job |
| M2 | KM、log-rank、HR/CI | 研究统计 Job |
| M3 | `first_extreme_hour ~ abs(x)+sign+interaction+x4` | 研究统计 Job |
| M4 | x4 五分位、CMH、偏相关 | 研究统计 Job |
| M5 | 三期、状态、52 周滚动 | 研究统计 Job |
| M6 | signal×path×window 三元列联与 log-linear | 研究统计 Job |
| M7 | BTC 同口径阴性对照 | 有 BTC 1h 时原始重建，否则 legacy-derived 并警告 |
| M8 | 1h vs 15min 敏感性 | 缺 15min 时显式跳过 |

所有显著主结果增加 10,000 次排列和 10,000 次 Bootstrap CI。盲检任务只生成 100 张随机标签图和密钥，人工识别率属于外部输入；无人工结果时标记 `awaiting_human_assessment`，不阻塞统计主线。

### 10.2 决策门和回测

- M1/M2 均无证据时，M3-M8 仍可按“完整迁移”运行，但必须标为 secondary/exploratory；v6-S1-S6 跳过。
- v6 经济门通过需同时满足：至少一个信号的 M1 全表 p<0.05、至少一个单窗或 M2 结果经本模块多重校正后显著，且 M4 不支持“效应完全由 x4 混淆”的解释。
- 只有门通过时，才在每个模式运行 6 策略×4费率=24 次。
- v6 策略通过 V3.1 Intrabar，分别与 S45、S48、S51、S10 配对比较。
- 若跳过回测，每个模式生成 24 行 `skipped_gate` 索引，使预期数量可审计。

## 11. v7 多尺度迁移

### 11.1 路线 W

- W1：对 307/303 个周末的 48h 归一化路径调用 V3.1 `wavelet_decompose`，尺度 1-24、Morlet。
- W2：提取 LF/MF/HF、H/L、谱重心五个小波信号。
- W3：调用 K09 `wavelet_coherence` 计算小波相干和相位，并与 AR(1) 基准比较；不得用普通 Fourier coherence 冒充小波相干。
- W4：控制 x4 的回归和偏相关。

### 11.2 路线 E

- E1：V3.1 `spectral_entropy` + K02 `spectral_features` 生成 Welch 指纹。
- E2：6 频谱信号×6 结果，Pearson/Spearman/MI 三轨。
- E3：K=3-5 KMeans、silhouette 选 K、周一行为比较和 t-SNE/可选 UMAP。
- E4：交叉谱与频带 coherence，和 AR(1) 比较。

### 11.3 路线 G

- G1/G2 优先调用 V3.1 `grey_relation`，historical 生成 307×307、canonical 生成 303×303 矩阵，并完成聚类和四参考模式信号。
- G3 调用 V3.1 `gm11_predict`，用 6h/12h/24h 尾部预测周一开盘；计算 MAPE/MAE/RMSE 和 Diebold-Mariano。
- G4 控制 x4 的偏相关、回归和增量 R2。

### 11.4 路线 N

- N1：6×6 MI、1,000 次置换和 Pearson 对比。
- N2：调用 V3.1 `transfer_entropy`，k=1/2/3、双向和净 TE，1,000 次配对置换。必须明确当前实现是分箱估计器，不描述为 KSG。
- N3/N4：调用 V3.1 Hurst DFA、Sample Entropy、Permutation Entropy。
- N5：项目级 RQA 至少输出 RR、DET、LAM、ENTR；若只实现简化版，缺失指标不得填 0。

### 11.5 路线 F 和决策门

- F1：6 旧+22 新=28 特征的相关矩阵和冗余诊断。
- F2：从 x4 基线开始的增量 R2，特征选择必须在训练窗内完成。
- F3：随机森林回归，采用 expanding/rolling forward validation；输出每窗和聚合 out-of-sample R2。
- F4：低/中/高振幅分类，输出 accuracy、macro-F1、ROC-AUC 和 confusion matrix。
- 不使用随机 5-fold。
- 若 N2 不显著，仍完成基础 W1/E1/G1/N1/N2 和相应图；深度路线按预注册门选择 `skipped_gate` 或 `exploratory`。
- v7 经济门固定为：out-of-sample 回归 R2 > 0.20，且高于同窗口 x4 单变量基线。门通过时每个模式运行 v7-S1-S4 共 16 次；否则每个模式生成 16 行跳过索引。

## 12. 绘图迁移

### 12.1 架构

1. 统计和回测先输出 Arrow/JSON Artifact。
2. `PlotSpec` 只描述 plot ID、输入 Artifact、字段、过滤、布局、标签和样式。
3. Matplotlib Agg renderer 消费 PlotSpec 生成 PNG，不重新调用研究算法或回测。
4. 每张图在 `plot_manifest.arrow` 记录输入 digest、尺寸、DPI、renderer 版本和状态。
5. 图表任务支持单独重跑，不要求重做计算。

### 12.2 图表覆盖基线

| 版本 | 必须覆盖 |
|---|---:|
| v1 | 10 个历史图表 ID |
| v2 | 15 个历史图表 ID |
| v3 | 18 个历史图表 ID |
| v4 | 13 个历史图表，加 B3 和 Chow 两个规划补图，共 15 个 ID |
| v5 | 规划枚举的 36 个图表 ID，不以旧目录现有 21 张为完成标准 |
| v6 | G01-G18 共 18 个 ID；G16 缺 15min 时可跳过 |
| v7 | W01-W05、E01-E06、G01-G05、N01-N06、F01-F05，共 27 个 ID |

v5 规划标题写“26 类图”，但表格实际枚举 36 个唯一 ID。本迁移以唯一 ID 36 为准，并在差异登记中记录此矛盾。

### 12.3 图表质量门

- PNG 非空，宽高至少 800×500，除特殊矩阵外 DPI 至少 120。
- 轴标题、单位、样本 n、模式和关键阈值必须可见。
- 中文字体缺失时使用 ASCII/英文回退并记录 warning，不生成乱码。
- 资金曲线必须来自 V3.1 equity Artifact，不得用总收益插值伪造。
- 缺输入或决策门跳过时不生成假图，而在 manifest 记录状态。

## 13. 报告与差异验证

必须生成：

- `reports/V1_V4_STATISTICS_CN.md`
- `reports/V5_BACKTEST_CN.md`
- `reports/V6_TIMING_CN.md`
- `reports/V7_MULTISCALE_CN.md`
- `reports/REPORT_FULL_CN.md`
- `reports/RUN_REPORT.md`
- `runs/<run_id>/difference_report.json`

差异报告分层：

| 等级 | 含义 | 处理 |
|---|---|---|
| exact | 统计量/指标在容差内一致 | 通过 |
| expected_semantic | strict 样本、same-bar、无前视、滑点等规范修正造成 | 解释后通过 |
| source_data | 输入版本或数据覆盖不同 | 阻塞对应历史复现，规范结果可保留 |
| implementation | 不能由语义或数据解释 | 阻塞验收 |

历史数字是回归线索而非硬断言。重点 golden 包括：v1 r 约 0.53-0.60、v2 绝对 r 不超过约 0.12、v3 路径 p 大于约 0.5、v4 x4-range r 约 0.42、v5 B1 约 +101.75%、旧 v5 F1 最佳为 S24。任何明显反转都必须先排查数据、前视或执行语义。

## 14. 测试与最终验收

### 14.1 测试层级

- 单元：信号公式、边界、统计校正、指标、策略下单和绩效派生。
- Golden：固定小数据的输出和旧基线容差。
- 集成：V3.1 Local Job -> Artifact -> reader -> plot。
- 回测语义：Intrabar、费用、OCO、TP/SL、时间退出、多日持仓。
- 全流程：从固定输入到全报告和 plot manifest。

### 14.2 最终数量门

- v1-v4 所有任务状态齐全。
- v5 策略注册数 52、费率数 4、每模式回测索引 208、基准/参考 3；`both` 综合索引 416 和 6。
- v6 M1-M8 状态 8；每模式条件策略索引 24，`both` 综合索引 48（成功或可解释跳过）。
- v7 W4+E4+G4+N5+F4=21 个模块状态；每模式条件策略索引 16，`both` 综合索引 32。
- 图表 manifest 包含全部预注册 ID；成功数量与可用输入/决策门一致，任何跳过有原因。
- 每个模式的图表 manifest 固定包含 139 个 ID；`both` 综合索引包含 278 行。
- 两次相同输入和种子的运行产生相同表格 digest；PNG 如含元数据导致字节差异，则数值 PlotSpec digest 和图像像素 hash 必须一致。
- Ruff、项目测试和相关 `tests_v31` 通过。

### 14.3 完成门

只有在 `RUN_CHECKLIST_CN.md` 的 P00-P90 必做项完成、所有条件项有明确状态、没有 unexplained implementation difference、总报告与 manifest 一致时，迁移才算完成。

## 15. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Binance/XAUT/15min 数据不可用 | 固定快照离线跑；条件任务显式跳过；不伪造 |
| 307 样本与 28 特征过拟合 | 时间前向验证、训练窗内特征选择、报告 OOS |
| v5 复杂策略语义不明确 | historical/canonical 双模式和语义差异表 |
| 旧图表只保存聚合结果 | 新回测保存 full equity/fills 后再绘图 |
| 多重检验假阳性 | Bonferroni+BH-FDR、效应量、排列和 Bootstrap |
| sklearn 不在核心依赖 | 研究 optional 依赖固定版本，不污染最小 V3.1 runtime |
| 当前 TE 为粗分箱实现 | 明确 estimator，置换验证，不宣称 KSG 精度 |
| 图表任务掩盖计算 | renderer 只消费 Artifact，PlotSpec 有 digest |
| 旧数字与规范结果不同 | 差异分类，禁止为了对齐牺牲无前视和数据质量 |
