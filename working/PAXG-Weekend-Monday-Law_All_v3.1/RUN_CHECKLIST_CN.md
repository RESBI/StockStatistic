# PAXG Weekend-Monday Law v1-v7 V3.1 跑通与验收清单

> 对应规划：`MIGRATION_PLAN_CN.md`
>
> 使用方式：实现和运行过程中逐项勾选。`[x]` 仅表示已经验证，不表示“已写代码”。
>
> 当前状态：规划阶段，以下项目均待执行。

## 0. 验收规则

- [ ] 每个任务有唯一 `task_id`，并出现在 `task_registry.yaml`。
- [ ] 每个任务最终状态只能是 `succeeded`、`failed`、`skipped_gate`、`skipped_missing_input`、`insufficient_sample` 或 `awaiting_human_assessment`。
- [ ] 任何 `failed` 都阻塞对应阶段完成。
- [ ] 任何 `skipped` 都包含结构化 `skip_reason`、依赖任务和缺失输入/未满足门槛。
- [ ] 所有表格主产物为 Arrow 或 Parquet；CSV 只作为人类查看副本。
- [ ] 所有 Artifact 有 schema_ref、SHA-256、输入 lineage、任务版本和随机种子。
- [ ] 相同输入、配置和种子的重复运行产生相同数值表 digest。
- [ ] `historical` 与 `canonical` 结果分目录保存，不互相覆盖。
- [ ] 报告只读取落盘结果，不在报告或绘图阶段重新计算统计/回测。
- [ ] 不存在旧 runtime import：`frontend`、`backend`、`worker`、`stockstat_backend`、`stockstat_compute`。

## P00：预检与范围冻结

### P00-A 目录和文档

- [ ] `working/PAXG-Weekend-Monday-Law_All_v3.1/` 是唯一新研究目标目录。
- [ ] `MIGRATION_PLAN_CN.md` 存在并与本清单版本一致。
- [ ] `README.md` 说明环境、输入、CLI、运行模式、阶段恢复和产物目录。
- [ ] `config/study.yaml` 固定 UTC、日期范围、样本视图、根种子 42 和默认 `both` 模式。
- [ ] `task_registry.yaml` 覆盖 P00-P90、v1-v7、回测、图表和报告任务。
- [ ] `legacy_semantic_differences.arrow` 已创建。

### P00-B 源研究清册

- [ ] v1 源目录登记为 `working/PAXG-Weekend-Monday-Law/`。
- [ ] v2-v7 各源目录均已登记。
- [ ] v5 原版和 v5-redo 的角色分开登记。
- [ ] 旧综合报告只登记为参考，不是运行依赖。
- [ ] v1-v7 脚本、计划、报告、数据和旧图表均进入 `source_inventory.arrow`。
- [ ] v5 52 个策略 S1-S52 均有名称、组别、信号、入场、出场、仓位、做空、数据周期和语义状态。
- [ ] v5 20 个研究问题和 13 个对比维度均有任务映射。
- [ ] v6 M1-M8、v6-S1-S6 均有任务映射。
- [ ] v7 W1-W4、E1-E4、G1-G4、N1-N5、F1-F4、v7-S1-S4 均有任务映射。

### P00-C 已知矛盾登记

- [ ] v5 “208 次”与旧 `all_metrics.csv` 210 行的关系登记为 208 策略费率结果 + B1/B2。
- [ ] B3 被登记为价格参考，而不是第三个独立账户回测。
- [ ] v5-redo 旧结果只有 33 个策略×4+B1，明确不能作为全量完成基线。
- [ ] v5 规划“26 类图”但实际枚举 36 个唯一图表 ID 的矛盾已登记。
- [ ] v6 规划 18 图与旧代码缺 G16 的情况已登记。
- [ ] v7 规划 27 图与旧实现 14 图的差距已登记。
- [ ] v7 旧 W01 如使用占位图，已标记不可作为 golden 像素基线。
- [ ] v5 S13/S18/S30/S37-S52 的文字与旧实现差异已逐项登记。
- [ ] historical/canonical/both 的数量口径已登记：下文数量默认按单一模式验收，both 另验收综合索引。

### P00-D 环境

- [ ] Python 版本为 3.11 或 3.12。
- [ ] 根 V3.1 依赖安装成功。
- [ ] `PyWavelets` 和 `matplotlib` 可导入。
- [ ] scikit-learn 作为研究 optional 依赖固定版本并可导入。
- [ ] Matplotlib backend 为 `Agg`。
- [ ] `StockStat.local()` 可创建 session。
- [ ] V3.1 Indicator Catalog、Backtest 和 Experiment API 可导入。

## P10：数据导入、快照和质量

### P10-A 固定输入校验

- [ ] `paxg_1d.parquet` 行数为 2,148。
- [ ] `paxg_1d.parquet` SHA-256 为 `2525B80B6F0FF2E634F35176FF0A008662B6A1C2F0E5E011B04C9FEC07E61BEA`。
- [ ] `paxg_1h.parquet` 行数为 51,520。
- [ ] `paxg_1h.parquet` SHA-256 为 `13447A51CDD5E4A3D1E456C52CE6EB17BA16E9356D7F0D13400CB0C25CC250C5`。
- [ ] `btc_1d.parquet` 行数为 2,151。
- [ ] `btc_1d.parquet` SHA-256 为 `617B8E9AB4E0DDB2497CF622B90958BDD06CE815559B71D6327BDA12CF417823`。
- [ ] 三个输入的 index 均转为 UTC tz-aware，且无重复。
- [ ] 输入列至少包含 `open,high,low,close,volume`。

### P10-B V3.1 市场数据契约

- [ ] PAXG 1d/1h 和 BTC 1d 已转成长表 `market.arrow`。
- [ ] 长表字段为 `ts,instrument,timeframe,open,high,low,close,volume`。
- [ ] `MarketDataset.from_arrow()` 成功加载全部固定输入。
- [ ] `Universe` OHLC 高低关系、有限值和非负值校验通过。
- [ ] V3.1 Artifact manifest 记录输入原路径、source=`legacy_binance_snapshot` 和 SHA-256。
- [ ] 每个 instrument/timeframe 有单独覆盖范围、行数和缺失统计。
- [ ] 新的 Binance 网络数据如被采集，使用新 snapshot ID，不覆盖固定输入。

### P10-C 数据质量报告

- [ ] 质量报告列出重复时间戳数量。
- [ ] 质量报告列出 OHLC 关系异常数量。
- [ ] 质量报告列出非有限值和负 volume 数量。
- [ ] 质量报告列出每个周末和周一的小时 K 线数量。
- [ ] 精确识别 307 个周一。
- [ ] 精确识别 303 个完整 48h+24h 配对。
- [ ] 不完整日期和条数与规划书列出的四个日期一致。
- [ ] 缺失 K 线未被插值或静默填充。

### P10-D 条件输入

- [ ] BTC 1h 输入状态为 `succeeded` 或 `skipped_missing_input`。
- [ ] PAXG 15min 输入状态为 `succeeded` 或 `skipped_missing_input`。
- [ ] XAUT 输入状态为 `succeeded`、`insufficient_sample` 或 `skipped_missing_input`。
- [ ] 使用 `paths_v7.parquet` 作为 BTC 路径降级输入时，lineage 标记 `legacy_derived=true`。
- [ ] 条件输入不存在时，没有伪造或从 PAXG 替代的数据。

## P20：统一数据集

### P20-A 样本视图

- [ ] `pairs_daily` 构建成功，基线行数为 307。
- [ ] `pairs_intraday_legacy` 构建成功，基线行数为 307。
- [ ] `pairs_intraday_strict` 构建成功，基线行数为 303。
- [ ] 每行包含 `sample_view` 和 `quality_flags`。
- [ ] 所有统计结果均记录实际使用的视图和 n。
- [ ] historical 与 canonical 的 Artifact/图表目录分区，未互相覆盖。

### P20-B 核心信号

- [ ] `x1_return` 公式和边界单元测试通过。
- [ ] `x2_slope` 通过 V3.1 `linear_slope@1.0` 计算。
- [ ] `x3_mid_slope` 通过同一 V3.1 指标计算。
- [ ] `x4_range` 公式测试通过。
- [ ] `x5_realized_vol` 使用小时 close 对数收益平方和开根。
- [ ] `x6_volume` 使用周末总量 / 两倍 30 日日均量。
- [ ] v4-B3 二次系数、曲率、R2 和形态分类已生成。
- [ ] 所有信号的 known-at 时间不晚于周一 00:00 UTC。

### P20-C 周一结果与路径

- [ ] `max_gain`、`max_loss`、`open_gap`、`full_day_return`、`intraday_vol`、`range` 已生成。
- [ ] `high_hour`、`low_hour`、`first_extreme_hour`、`second_extreme_hour` 已生成。
- [ ] `path`、`first_move`、`second_move` 已生成。
- [ ] W0-W4 窗口分类边界测试通过。
- [ ] `range_W0`、`range_W3`、`volatility_W0/W1`、`directional_move_W0` 已生成。
- [ ] historical 同 bar 规则和 canonical `same_bar_ambiguous` 都有结果。

### P20-D 滚动与状态字段

- [ ] x4 rolling median、Q4、Q5 阈值已生成。
- [ ] 30d ATR 优先通过 V3.1 `atr` 指标生成。
- [ ] ATR 25/75 分位已生成。
- [ ] 52 周 x4 z-score 已生成。
- [ ] 所有用于策略的滚动统计通过无前视测试。
- [ ] `period`、`is_post_2024`、`vol_regime` 已生成。

### P20-E 路径契约

- [ ] `paths.arrow` 使用长表，不以 pickle 或 object-list 作为主结果。
- [ ] PAXG 周末路径每完整样本 48 个 offset。
- [ ] PAXG 周一路径每完整样本 24 个 offset。
- [ ] BTC 路径记录原始或 legacy-derived 来源。
- [ ] normalized close 和 log return 数值有限。

### P20-F Golden 差异

- [ ] 新数据集与旧 `signals.parquet` 逐列比较。
- [ ] 新数据集与旧 `dataset_v6.parquet` 逐列比较。
- [ ] 新路径与旧 `paths_v7.parquet` 比较。
- [ ] 差异分类为 `exact/expected_semantic/source_data/implementation`。
- [ ] 不存在未解释的 `implementation` 差异。

## P30：V3.1 通用能力

### P30-A Indicator

- [ ] `linear_slope@1.0` 注册到 V3.1 Indicator Catalog。
- [ ] `linear_slope` 对线性序列返回已知斜率。
- [ ] `linear_slope` 对短序列、常数和 NaN 行为有测试。
- [ ] `spectral_features@1.0` 注册并输出 PSD/frequency/LF/MF/HF/centroid/peak。
- [ ] `wavelet_coherence@1.0` 注册并输出 coherence、scale/frequency 和 phase。
- [ ] `wavelet_coherence` 的同序列高相干、独立噪声低相干和 AR(1) 基准测试通过。
- [ ] `wavelet_decompose` 通过 `finance.timeseries.analyze` Job 路径集成测试。
- [ ] v7 其余 7 个 V3.1 高级指标各至少一个 Job 集成测试。

### P30-B Backtest

- [ ] 周一开盘入场、周一收盘退出测试通过。
- [ ] 指定小时 12:00 退出测试通过。
- [ ] 周五至周一、周一至周三跨日持仓测试通过。
- [ ] 限价成交 `sub_bar_ts` 正确。
- [ ] 退出扫描从 entry fill 后开始，不能使用成交前 sub-bar。
- [ ] OCO 任一成交撤另一测试通过。
- [ ] 双边同日都触发时的确定性规则测试通过。
- [ ] TP/SL 同一小时都触发时按 `priority` 保守执行。
- [ ] Trailing stop 多空方向测试通过。
- [ ] 多档网格、部分未成交和收盘撤单测试通过。
- [ ] maker/taker 费用由订单类型正确决定。
- [ ] F1-F4 的费率数字与 BinanceCost 配置一致。
- [ ] historical 场景滑点为 0，canonical 敏感性场景为 0.05%。

### P30-C 绩效与实验

- [ ] 从 equity/fills 派生 total return、CAGR、Sharpe、Sortino、Calmar、MaxDD。
- [ ] 派生 win rate、profit factor、avg trade/win/loss、trade count、exposure。
- [ ] 周策略 Sharpe 年化因子固定 52。
- [ ] 年度和月度收益表由真实 equity 生成。
- [ ] Search 成功返回每个 trial 状态和完整指标。
- [ ] Batch 对失败 run 保留错误行。
- [ ] Simulation 相同 seed 可重复。
- [ ] Walk-forward 按时间窗口切片，无训练/测试重叠。

### P30-D Artifact 与绘图契约

- [ ] 研究统计 capability/runner 输出 Arrow + manifest。
- [ ] Batch full-detail 能索引到每个 backtest 的 equity/fills/positions。
- [ ] `PlotSpec` 可序列化，包含 plot ID 和输入 digest。
- [ ] Agg renderer 不导入研究模块的计算入口。
- [ ] 单独绘图命令可只读取已有 Artifact 重建图表。

## P40：v1-v4 统计分析

### P40-V1

- [ ] V1-01：x1/x2/x3 的方向选择 Pearson r、p、R2 已输出。
- [ ] V1-02：信号正负组均值、标准差、SEM、95% CI 已输出。
- [ ] V1-03：三条 52 周 rolling r 已输出。
- [ ] V1-04：独立零模型选择偏差 Monte Carlo 已输出。
- [ ] V1-05：结果标记 `known_biased_estimator=true`。
- [ ] v1 historical 结果量级可解释地接近 r=0.53-0.60。

### P40-V2

- [ ] V2-01：3×2 Pearson 结果完整。
- [ ] V2-01：3×2 Spearman 结果完整。
- [ ] V2-02：Welch t、KS 和效应量完整。
- [ ] V2-03：方向一致率和三信号共识完整。
- [ ] V2-04：v1-v2 坍塌比较完整。
- [ ] historical 主相关量级不超过约 0.12，若超过已排查。

### P40-V3

- [ ] V3-01：historical/canonical 路径数据都已生成。
- [ ] V3-02：3 个 2×2 卡方、p、Cramér's V 已输出。
- [ ] V3-03：first_move/path 相关和分组统计已输出。
- [ ] V3-04：极值时刻与 same-bar 模糊性已输出。
- [ ] historical 路径 p 量级接近旧值 0.51-1.00，差异有解释。

### P40-V4A

- [ ] A1 10,000 次双侧排列检验完成。
- [ ] A2 10,000 次 paired bootstrap 完成。
- [ ] A3 三期分割固定且行数报告完整。
- [ ] A4 52 周 rolling 结果完整。
- [ ] 分布 Artifact 保存全部样本，不只保存摘要。
- [ ] V3.1 回测 bootstrap 未被错误用于相关性检验。

### P40-V4BC

- [ ] 6×6 Pearson 矩阵完整。
- [ ] 6×6 Spearman 矩阵完整。
- [ ] 36 对 p、Bonferroni、BH-FDR 和效应量完整。
- [ ] B3 二次形态任务真实实现，不只是规划文字。
- [ ] `x1-open_gap` 被标记为机械同义/高重合，不解释为新 alpha。
- [ ] historical `x4-range` r 量级接近约 0.42，差异有解释。

### P40-V4D

- [ ] PAXG 同口径结果完成。
- [ ] BTC daily 阴性对照完成。
- [ ] BTC 1h 波动率对照完成或明确跳过。
- [ ] XAUT 结果完成或标记 `insufficient_sample/skipped_missing_input`。
- [ ] 跨资产三期比较完成。
- [ ] 未以 XAUT 小样本给出确认性结论。

### P40-V4EF

- [ ] E1 固定 2024-01-01 Chow test 完成。
- [ ] E2 x5/ATR 状态分析完成。
- [ ] E3 Mon/Tue/Wed 衰减使用同一周末窗口并通过边界测试。
- [ ] F1 五分位结果和趋势检验完成。
- [ ] F2 方向/波动率/全共识三层完成。
- [ ] F3 固定和 rolling 阈值完成，极端组 n 显示。

## P50：v5 全量回测

### P50-A 注册与静态审计

- [ ] 策略注册数精确为 52。
- [ ] S1-S52 无缺号、重号或重复 entrypoint。
- [ ] 每个策略有 group、data timeframe、allow_short、position sizing 和 execution tier。
- [ ] F1-F4 配置数精确为 4。
- [ ] `stockstat migrate-scan` 为 0 findings，或每个 finding 有批准豁免。
- [ ] 所有策略工厂返回 V3.1 `Strategy`。

### P50-B 策略组执行

- [ ] S1-S6 全部执行 4 费率。
- [ ] S7-S8 全部执行 4 费率。
- [ ] S9-S12 全部执行 4 费率。
- [ ] S13-S16 全部执行 4 费率。
- [ ] S17-S19 全部执行 4 费率。
- [ ] S20-S22 全部执行 4 费率。
- [ ] S23-S25 全部执行 4 费率。
- [ ] S26-S29 全部执行 4 费率。
- [ ] S30-S36 全部执行 4 费率。
- [ ] S37-S44 全部执行 4 费率。
- [ ] S45-S52 全部执行 4 费率。
- [ ] historical `strategy_fee_metrics.arrow` 精确包含 208 行。
- [ ] canonical `strategy_fee_metrics.arrow` 精确包含 208 行。
- [ ] `both` 综合策略费率索引精确包含 416 行。
- [ ] 每个模式的 208 行状态全部 `succeeded`，否则阶段不通过。

### P50-C 基准

- [ ] B1 买入持有 equity 和指标完整。
- [ ] B2 周一定投 equity、现金流和指标完整。
- [ ] B3 价格曲线参考完整并标记 `reference_only=true`。
- [ ] historical B1 总收益量级接近 +101.75%，差异有解释。
- [ ] historical B2 总收益量级接近 +79.67%，差异有解释。
- [ ] B1/B2/B3 没有混入任一模式的 208 行策略费率结果。
- [ ] historical/canonical 各有 3 行基准/参考索引，both 综合索引为 6 行。

### P50-D 重点语义验证

- [ ] S9 OCO 行为有成交/撤单统计。
- [ ] S13 historical/canonical 定义均运行并比较。
- [ ] S18 精确 12:00 退出。
- [ ] S23 动态 stop 方向正确。
- [ ] S24 trailing stop 方向和更新正确。
- [ ] S25 12:00 盈利判断只用当时可知数据。
- [ ] S30 波动率共识只用周末已知信息。
- [ ] S34 周五布网格至周一开盘的跨日语义正确。
- [ ] S38 rolling regression 无前视。
- [ ] S40 同 bar SL 优先于 TP。
- [ ] S45-S52 双向订单、退出原因和费用分解可审计。
- [ ] S48 profit exit 触发后未成交单被撤销。
- [ ] S52 六档订单的下单、成交和收盘清理完整。

### P50-E 聚合和对比

- [ ] 每次回测都有 equity/fills/positions/manifest。
- [ ] 10 项主绩效指标完整。
- [ ] 毛收益、手续费、滑点和净收益可对账。
- [ ] 17 个策略组汇总完整。
- [ ] 13 个预注册对比维度完整。
- [ ] 2020-2023 vs 2024-2026 子期间完整。
- [ ] 高/低状态对比完整。
- [ ] 每策略相对 B1/B2/B3 的差异完整。
- [ ] F1-F4 费用边际比较完整。
- [ ] F1/F2 现货做空标记为理论；F3/F4 1×且未计资金费率的限制已披露。
- [ ] Top-5 只在对应模式的 208 次全部结束后选取。

### P50-F Search、Simulation 和 Walk-forward

- [ ] P14 x4 threshold sweep 完成。
- [ ] P15 S9 k sweep 完成。
- [ ] P15b grid density sweep 完成。
- [ ] P15c stop multiplier sweep 完成。
- [ ] P15d S39 TP coefficient sweep 完成。
- [ ] P15e core-B k sweep 完成。
- [ ] 每个 Search trial 有参数、状态、目标和完整指标。
- [ ] 候选策略 V3.1 Simulation 至少 1,000 样本。
- [ ] Simulation quantile 和 drawdown 摘要完整。
- [ ] 可训练策略的 V3.1 Walk-forward 窗口完整。
- [ ] 参数选择只使用训练窗口。

### P50-G 历史差异

- [ ] 旧 F1 Top 策略 S24 的排名差异已检查。
- [ ] 旧方向组整体失败的结论差异已检查。
- [ ] 旧“无策略击败 B1”结论差异已检查。
- [ ] S48 F4 的差异已检查，但不以强行复刻旧 bug 为通过条件。
- [ ] 所有差异均归类，无 unexplained implementation difference。

## P60：v6 M1-M8 与条件回测

### P60-A M1-M4

- [ ] M1 3 个 2×5 全表卡方完整。
- [ ] M1 15 个单窗口检验完整。
- [ ] M1 log OR、Wilson CI、Cramér's V 完整。
- [ ] M1 Bonferroni 与 BH-FDR 完整。
- [ ] M2 x1/x2/x3 KM 曲线数据完整。
- [ ] M2 3 个 log-rank、HR 和 CI 完整。
- [ ] M3 三组方向/幅度/交互/x4 模型完整。
- [ ] M4 x4 五分位分层、CMH 和偏相关完整。

### P60-B M5-M8

- [ ] M5 三期分析完整。
- [ ] M5 高低波动状态完整。
- [ ] M5 52 周 rolling effect 完整。
- [ ] M6 三元列联和 log-linear 完整。
- [ ] M7 BTC 原始或 legacy-derived 对照有明确 lineage。
- [ ] M8 15min 对照完成或 `skipped_missing_input`。
- [ ] 所有显著主结果 10,000 次排列完成。
- [ ] 所有效应量 10,000 次 Bootstrap CI 完成。
- [ ] 100 个盲检材料与密钥已生成。
- [ ] 无人工盲检结果时状态为 `awaiting_human_assessment`。

### P60-C 决策门和策略

- [ ] v6 gate 输入、规则和结论写入 `decision_gates.arrow`。
- [ ] gate 规则满足：M1 全表 p<0.05，且至少一个单窗或 M2 经校正显著，并且 M4 不支持完全 x4 混淆。
- [ ] gate 通过时 v6-S1-S6 各运行 F1-F4，共 24 次。
- [ ] gate 未通过时生成 24 行 `skipped_gate` 索引。
- [ ] historical/canonical 各有 24 行策略索引，不因跳过而缺行。
- [ ] both 综合 v6 策略索引为 48 行。
- [ ] v6-S1 对比 S45。
- [ ] v6-S2 对比 S48。
- [ ] v6-S3 对比 S51。
- [ ] v6-S6 对比 S10。
- [ ] 经济结论同时报告绝对收益和相对改进。

## P70：v7 W/E/G/N/F 与条件回测

### P70-W

- [ ] W1 对全部可用严格周末路径执行 CWT。
- [ ] W1 系数来自 V3.1 `wavelet_decompose` Job。
- [ ] W2 w1-w5 五个信号完整。
- [ ] W3 coherence、相位和 AR(1) 基准完整。
- [ ] W3 使用 `wavelet_coherence@1.0`，未以普通 Fourier coherence 冒充。
- [ ] W4 控制 x4 的回归和偏相关完整。
- [ ] 未用占位随机图代替真实 scalogram。

### P70-E

- [ ] historical 307 个、canonical 303 个 Welch PSD 和六个频谱特征完整。
- [ ] E1 谱熵来自 V3.1 `spectral_entropy`。
- [ ] E2 6×6 Pearson/Spearman/MI 完整。
- [ ] E3 K=3-5、silhouette、最优 K 和簇行为比较完整。
- [ ] E3 t-SNE 完整；UMAP 不可用时可明确跳过。
- [ ] E4 交叉谱、coherence 和 AR(1) 基准完整。

### P70-G

- [ ] historical 307×307、canonical 303×303 灰色关联矩阵完整且对角线为 1。
- [ ] G1 调用 V3.1 `grey_relation`。
- [ ] G1 层次聚类、KMeans 和典型路径完整。
- [ ] G2 四个参考模式信号完整。
- [ ] G3 6h/12h/24h GM(1,1) 预测完整。
- [ ] G3 调用 V3.1 `gm11_predict`。
- [ ] G3 MAPE/MAE/RMSE 和 Diebold-Mariano 完整。
- [ ] G4 控制 x4 和增量 R2 完整。

### P70-N

- [ ] N1 36 对 MI 和 1,000 次置换完整。
- [ ] N2 k=1/2/3 双向和净 TE 完整。
- [ ] N2 调用 V3.1 `transfer_entropy`。
- [ ] N2 estimator 明确标为 quantile-bin，不误写 KSG。
- [ ] N2 1,000 次配对置换完整。
- [ ] N3 V3.1 Hurst DFA 完整。
- [ ] N4 V3.1 Sample/Permutation Entropy 完整。
- [ ] N5 RR、DET、LAM、ENTR 完整；未实现指标不填 0。

### P70-F

- [ ] F1 特征数精确为 28，除非缺失模块有明确状态。
- [ ] F1 相关矩阵和冗余诊断完整。
- [ ] F2 x4 基线和逐步增量 R2 完整。
- [ ] F2 特征选择只在训练窗内完成。
- [ ] F3 随机森林 expanding/rolling forward validation 完整。
- [ ] F3 每窗 train/test 日期、n、R2 完整。
- [ ] F3 聚合 out-of-sample R2 完整。
- [ ] F4 分类 accuracy、macro-F1、ROC-AUC 和 confusion matrix 完整。
- [ ] 未使用随机 5-fold 混洗时间序列。

### P70-Gate 与经济意义

- [ ] v7 decision gate 规则和实际输入落盘。
- [ ] 经济门规则固定为 out-of-sample 回归 R2 > 0.20 且高于同窗口 x4 单变量基线。
- [ ] 基础 W1/E1/G1/N1/N2 无论 gate 结果都有状态。
- [ ] 深度模块被跳过时均有 `skipped_gate` 行。
- [ ] 回测 gate 通过时 v7-S1-S4 各运行 F1-F4，共 16 次。
- [ ] 回测 gate 未通过时生成 16 行 `skipped_gate` 索引。
- [ ] historical/canonical 各有 16 行策略索引，both 综合索引为 32 行。
- [ ] v7 策略仅使用当时训练窗模型，预测值为 out-of-sample。
- [ ] v7 策略与对应 v5 基线做配对比较。

## P80：绘图验收

### P80-A v1 图表 10

- [ ] `v1_1_weekend_return_sign_scatter`
- [ ] `v1_1_weekend_return_sign_directional`
- [ ] `v1_1_weekend_return_sign_rolling`
- [ ] `v1_2_sat_sun_slope_scatter`
- [ ] `v1_2_sat_sun_slope_directional`
- [ ] `v1_2_sat_sun_slope_rolling`
- [ ] `v1_3_satmid_sunmid_slope_scatter`
- [ ] `v1_3_satmid_sunmid_slope_directional`
- [ ] `v1_3_satmid_sunmid_slope_rolling`
- [ ] `v1_comparison_all_three`

### P80-B v2 图表 15

- [ ] x1/x2/x3 各自 `scatter_both`，共 3。
- [ ] x1/x2/x3 各自 `histograms`，共 3。
- [ ] x1/x2/x3 各自 `boxplot`，共 3。
- [ ] x1/x2/x3 各自 `ecdf`，共 3。
- [ ] `v2_cross_comparison`。
- [ ] `v2_corr_matrix`。
- [ ] `v2_consensus`。

### P80-C v3 图表 18

- [ ] x1/x2/x3 各自 path scatter， 共 3。
- [ ] x1/x2/x3 各自 path stacked，共 3。
- [ ] x1/x2/x3 各自 first-move boxplot，共 3。
- [ ] x1/x2/x3 各自 first-move bar，共 3。
- [ ] x1/x2/x3 各自 path timing，共 3。
- [ ] `v3_cross_comparison`。
- [ ] `v3_path_proportion_all`。
- [ ] `v3_corr_matrix`。

### P80-D v4 图表

- [ ] A1 permutation。
- [ ] A2 bootstrap。
- [ ] A3 subperiod。
- [ ] A4 rolling。
- [ ] BC correlation heatmap。
- [ ] BC significant bars。
- [ ] B3 quadratic-shape 专用图。
- [ ] D asset comparison。
- [ ] D asset subperiod。
- [ ] E1 Chow/break 专用图。
- [ ] E2 regime。
- [ ] E3 decay。
- [ ] F1 quintile。
- [ ] F2 agreement。
- [ ] F3 threshold。

### P80-E v5 图表 36

- [ ] P01 equity all。
- [ ] P02 equity direction。
- [ ] P03 equity volatility。
- [ ] P04 equity top5。
- [ ] P04b equity new groups。
- [ ] P04c equity core A。
- [ ] P04d equity core B。
- [ ] P05 drawdown。
- [ ] P06 risk-return。
- [ ] P07 Sharpe bar。
- [ ] P08 yearly heatmap。
- [ ] P09 monthly top3。
- [ ] P10 trades S11。
- [ ] P11 returns distribution。
- [ ] P11b grid S35 sequence。
- [ ] P11c core A TP hit。
- [ ] P11d core B sequence。
- [ ] P12 subperiod。
- [ ] P13 regime。
- [ ] P13b filter compare。
- [ ] P13c consensus compare。
- [ ] P13d core A vs B。
- [ ] P13e TP methods。
- [ ] P13f exit mechanisms。
- [ ] P14 threshold sweep。
- [ ] P15 k sweep。
- [ ] P15b grid sweep。
- [ ] P15c stop sweep。
- [ ] P15d core A TP c。
- [ ] P15e core B k。
- [ ] P16 long-short symmetry。
- [ ] P17 gap directions。
- [ ] P18 fee Sharpe。
- [ ] P19 BNB uplift。
- [ ] P20 spot vs futures。
- [ ] P21 fee breakdown。

### P80-F v6 图表 G01-G18

- [ ] G01 window stacked。
- [ ] G02 chi-square heatmap。
- [ ] G03 log OR forest。
- [ ] G04 ECDF。
- [ ] G05 violin。
- [ ] G06 KM x1。
- [ ] G07 KM x2。
- [ ] G08 KM x3。
- [ ] G09 HR forest。
- [ ] G10 stratified x4。
- [ ] G11 subperiod。
- [ ] G12 rolling。
- [ ] G13 regime。
- [ ] G14 three-way。
- [ ] G15 BTC vs PAXG 或明确跳过。
- [ ] G16 1h vs 15min 或明确跳过。
- [ ] G17 x3 focus。
- [ ] G18 master summary。

### P80-G v7 图表 27

- [ ] W01-W05 五个小波图全部有状态。
- [ ] E01-E06 六个频谱图全部有状态。
- [ ] G01-G05 五个灰色系统图全部有状态。
- [ ] N01-N06 六个信息论/RQA 图全部有状态。
- [ ] F01-F05 五个融合图全部有状态。
- [ ] gate 跳过图有 manifest 记录，不生成假内容。

### P80-H 图表质量

- [ ] `plot_manifest.arrow` 包含所有预注册图表 ID。
- [ ] historical/canonical 各包含 139 个图表 ID，both 综合索引为 278 行。
- [ ] 所有成功 PNG 文件非空。
- [ ] 所有成功 PNG 至少 800×500。
- [ ] 所有成功图有 input digest 和 renderer version。
- [ ] 所有资金/回撤图来自真实 equity Artifact。
- [ ] 图表脚本可单独重跑且不触发回测。
- [ ] 同配置重复绘图的 PlotSpec digest 和像素 hash 一致。
- [ ] 中文字体问题无乱码；发生回退时 warning 已记录。

## P90：报告、测试和最终签收

### P90-A 报告

- [ ] `reports/V1_V4_STATISTICS_CN.md` 生成。
- [ ] `reports/V5_BACKTEST_CN.md` 生成。
- [ ] `reports/V6_TIMING_CN.md` 生成。
- [ ] `reports/V7_MULTISCALE_CN.md` 生成。
- [ ] `reports/REPORT_FULL_CN.md` 生成。
- [ ] `reports/RUN_REPORT.md` 生成。
- [ ] 报告中的 n、任务状态、回测数量和图表数量与 manifest 一致。
- [ ] historical/canonical 结果明确分栏或分节。
- [ ] 所有选择偏差、数据不足、决策门跳过和 estimator 限制已披露。
- [ ] 报告不将统计显著自动解释为经济显著。

### P90-B 差异报告

- [ ] `difference_report.json` 覆盖数据集、v1-v4、v5、v6、v7。
- [ ] v1 historical r 量级差异已解释。
- [ ] v2 相关坍塌差异已解释。
- [ ] v3 路径 p 差异已解释。
- [ ] v4 x4-range 结果差异已解释。
- [ ] v5 B1/B2、Top 排名和 208 次结果差异已解释。
- [ ] v6/v7 与旧 JSON/报告的差异已解释。
- [ ] 没有 `implementation` 类未解释差异。

### P90-C 自动化测试

- [ ] 项目 Ruff 通过。
- [ ] 项目 unit tests 通过。
- [ ] 项目 integration tests 通过。
- [ ] V3.1 Indicator Job 集成测试通过。
- [ ] V3.1 Backtest/Intrabar 集成测试通过。
- [ ] V3.1 Search/Batch/Simulation/Walk-forward 集成测试通过。
- [ ] 相关 `tests_v31` 全部通过。
- [ ] 无 legacy import 扫描通过。
- [ ] 两次全流程 deterministic 检查通过。

### P90-D 数量门

- [ ] v5 策略数 = 52。
- [ ] v5 费率数 = 4。
- [ ] v5 每模式回测索引行数 = 208，both 综合索引 = 416。
- [ ] v5 每模式基准/参考数 = 3，both 综合索引 = 6。
- [ ] v6 模块状态数 = 8。
- [ ] v6 每模式条件策略索引行数 = 24，both 综合索引 = 48。
- [ ] v7 模块状态数 = 21。
- [ ] v7 每模式条件策略索引行数 = 16，both 综合索引 = 32。
- [ ] 图表 manifest 含 v1 10、v2 15、v3 18、v4 15、v5 36、v6 18、v7 27 个 ID。
- [ ] 每模式图表 ID 合计 = 139，both 综合索引 = 278。
- [ ] 任何未成功图表都有允许的 skip 状态。

### P90-E 最终签收

- [ ] `run_manifest.json` 记录 git/code digest、输入 digest、配置 digest、环境和全部任务状态。
- [ ] `task_status.jsonl` 无缺失任务 ID。
- [ ] `warnings.json` 中每条 warning 已在报告披露或关闭。
- [ ] 没有 failed 必做任务。
- [ ] 没有无法解释的缺行、缺图或缺 Artifact。
- [ ] 规划书与清单中的数量、命名和条件门一致。
- [ ] 最终结论由新结果推导，没有复制旧报告结论。
- [ ] 满足以上条件后，迁移状态可标记为 `accepted`。

## 建议执行命令契约

实现后的 CLI 建议支持以下稳定入口，实际命令如有调整须同步 README 和本清单：

```powershell
python -m paxg_weekend_monday.cli preflight
python -m paxg_weekend_monday.cli run --stage data --mode both
python -m paxg_weekend_monday.cli run --stage dataset --mode both
python -m paxg_weekend_monday.cli run --stage v1-v4 --mode both
python -m paxg_weekend_monday.cli run --stage v5 --mode both
python -m paxg_weekend_monday.cli run --stage v6 --mode both
python -m paxg_weekend_monday.cli run --stage v7 --mode both
python -m paxg_weekend_monday.cli plot --all
python -m paxg_weekend_monday.cli report --all
python -m paxg_weekend_monday.cli verify --all
```
