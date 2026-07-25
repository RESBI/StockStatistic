# StockStat V3.1 金融计算任务通用化清单

> **版本**：v3.1（设计稿）
> **日期**：2026-07-24
> **状态**：设计讨论
> **目的**：紧贴 PAXG-Weekend-Monday-Law v1~v7 研究所需功能，列举量化研究中常见的、以及先进手段中需要用到的**与指标计算、回测同等级别的基础原子计算任务**，作为 V3.1 Compute 模块 handler 注册表的设计基线。
> **原则**：
> 1. 不 overgeneralize —— 仅列入量化金融研究中真实需要的原子任务
> 2. 保留当前功能需求 —— PAXG v1~v7 全部功能必须有对应原子任务
> 3. 预留未来扩展 —— 先进/前沿任务以"预留接口"形式列出，不强行实现
> 4. 原子任务粒度 —— 一个 task_type 对应一个 handler，输入数据 + 参数 → 输出结果，可独立调度

---

## 目录

1. [设计理念](#1-设计理念)
2. [原子任务分级体系](#2-原子任务分级体系)
3. [Tier 1 — 交易回测类（已实现，重构迁移）](#3-tier-1--交易回测类已实现重构迁移)
4. [Tier 2 — 经典统计检验类（PAXG v1~v6 所需）](#4-tier-2--经典统计检验类paxg-v1v6-所需)
5. [Tier 3 — 信号处理与频域分析（PAXG v7 W/E 路线）](#5-tier-3--信号处理与频域分析paxg-v7-we-路线)
6. [Tier 4 — 非线性动力学与信息论（PAXG v7 N 路线）](#6-tier-4--非线性动力学与信息论paxg-v7-n-路线)
7. [Tier 5 — 灰色系统与软计算（PAXG v7 G 路线）](#7-tier-5--灰色系统与软计算paxg-v7-g-路线)
8. [Tier 6 — 机器学习与数据挖掘](#8-tier-6--机器学习与数据挖掘)
9. [Tier 7 — 投资组合与风险管理（量化核心扩展）](#9-tier-7--投资组合与风险管理量化核心扩展)
10. [Tier 8 — 前沿与预留（未来扩展）](#10-tier-8--前沿与预留未来扩展)
11. [task_type 注册表汇总](#11-task_type-注册表汇总)
12. [ComputeSpec 扩展策略](#12-computespec-扩展策略)
13. [与 PAXG v1~v7 的映射矩阵](#13-与-paxg-v1v7-的映射矩阵)

---

## 1. 设计理念

### 1.1 为什么要"原子任务化"

V2/V3 的计算调用是**方法级**的：`client.compute.ma()`、`client.backtest()`、`grid_search()`。这种方式在单进程下自然，但在分布式架构下有三个问题：

1. **粒度不均**：`ma()` 是毫秒级，`grid_search()` 是分钟级，无法用同一调度策略
2. **序列化困难**：方法签名各异，策略闭包、DataFrame、参数字典混在一起，难以统一序列化
3. **扩展无规可循**：新增一个"蒙特卡洛"方法需要改 Client/Engine/Worker 三处

V3.1 的核心思路是**原子任务化**：所有计算调用最终归约为一个 `TaskSpec`，通过 `task_type` 路由到对应 handler。新增计算能力 = 新增一个 task_type + 一个 handler，**协议、传输、调度零改动**。

### 1.2 原子任务的判定标准

一个计算能力是否值得作为独立 task_type，需满足：

| 标准 | 说明 |
|------|------|
| **可独立调度** | 有明确的输入数据 + 参数 + 输出结果，可作为一个分片单元 |
| **粒度相当** | 计算量与"一次回测""一次指标计算"相当（秒级~分钟级） |
| **序列化清晰** | 输入输出可用 Arrow/cloudpickle/JSON 表达 |
| **复用价值** | 至少被 2 个研究场景使用，或属于标准量化工具箱 |
| **无状态或可 checkpoint** | 抢占后可恢复（或可重算） |

毫秒级轻量指标（如 `ma(window=20)`）**不作为独立 task_type**，而是通过 `indicator` task_type 的 `params.indicator_name` 字段分发——它们共享同一个 handler，只是参数不同。这与 V3 的设计一致，避免了协议层被海量小任务淹没。

### 1.3 与 V3 task_type 的关系

V3 已有 6 个 task_type：`indicator` / `backtest` / `grid_search` / `batch_backtest` / `monte_carlo` / `custom`。

V3.1 在此基础上**新增统计检验、信号处理、非线性动力学、灰色系统、机器学习、组合风险**等类别，使 task_type 总数从 6 扩展到 ~30，覆盖 PAXG v1~v7 全部功能 + 量化常见需求 + 先进手段预留。

---

## 2. 原子任务分级体系

按"实现紧迫度 + 功能成熟度"分 8 个 Tier：

| Tier | 主题 | 来源 | task_type 数 | V3.1 实现状态 |
|------|------|------|-------------|--------------|
| 1 | 交易回测类 | V2/V3 已实现 | 6 | 重构迁移 |
| 2 | 经典统计检验 | PAXG v1~v6 | 8 | 新增 |
| 3 | 信号处理与频域 | PAXG v7 W/E | 5 | 新增 |
| 4 | 非线性动力学与信息论 | PAXG v7 N | 7 | 新增 |
| 5 | 灰色系统与软计算 | PAXG v7 G | 3 | 新增 |
| 6 | 机器学习与数据挖掘 | PAXG v7 F + 量化通用 | 7 | 新增 |
| 7 | 投资组合与风险管理 | 量化核心扩展 | 6 | 新增（部分预留） |
| 8 | 前沿与预留 | 未来扩展 | 5 | 接口预留 |
| **合计** | | | **47** | |

**说明**：47 个 task_type 中，Tier 1~6 共 36 个是 PAXG v1~v7 + 量化通用**必须实现**的；Tier 7~8 共 11 个是**预留接口**（协议层支持，handler 可后补）。

---

## 3. Tier 1 — 交易回测类（已实现，重构迁移）

V2/V3 已实现的 6 个核心 task_type，V3.1 完全保留语义，仅重构 handler 位置（移至 Compute 模块）。

### 3.1 `indicator` — 技术指标计算

| 字段 | 值 |
|------|-----|
| **task_type** | `"indicator"` |
| **输入** | `data_spec`（OHLCV）+ `params.indicator_name` + `params.{window, ...}` |
| **输出** | `pd.Series` / `pd.DataFrame` / `float` |
| **handler** | `compute.handlers.indicator_handler` |
| **分片策略** | `none`（单次计算） |
| **典型耗时** | 毫秒~秒级 |
| **V2 对应** | `ComputeEngine.ma/rsi/macd/bollinger/atr/...`（40+ 方法） |

**支持的指标族**（通过 `indicator_name` 路由）：
- 趋势：MA/EMA/WMA/DEMA/TEMA/HMA/MACD/ADX/DPO/Trix
- 振荡：RSI/KD/Williams%R/CCI/STOCH
- 波动：Bollinger/ATR/Keltner/Donchian/StdDev
- 成交量：OBV/VWAP/MFI/CMF/A/D Line
- 统计：rolling_corr/rolling_beta/zscore/percentile

**CloudpickleCodec 不需要**：指标参数均为 JSON 可序列化。

### 3.2 `backtest` — 单次策略回测

| 字段 | 值 |
|------|-----|
| **task_type** | `"backtest"` |
| **输入** | `data_spec` + `compute_spec.strategy_ref`（cloudpickle）+ 回测参数 |
| **输出** | `BacktestResult`（含 trades/equity/metrics） |
| **handler** | `compute.handlers.backtest_handler` |
| **分片策略** | `none` |
| **典型耗时** | 秒级 |
| **V2 对应** | `BacktestEngine(data, strategy, **kw).run()` |

**关键参数**（`compute_spec`）：
- `initial_cash`、`cost_model`、`fill_model`、`execution_model`
- `trade_on`、`allow_short`、`periods_per_year`、`benchmark`

### 3.3 `grid_search` — 参数网格搜索

| 字段 | 值 |
|------|-----|
| **task_type** | `"grid_search"` |
| **输入** | `data_spec` + `strategy_ref` + `param_grid` + `metric` |
| **输出** | `pd.DataFrame`（每组参数 + 指标值） |
| **handler** | `compute.handlers.grid_search_handler` |
| **分片策略** | `param_wise`（推荐） |
| **典型耗时** | 分钟~小时级 |
| **V2 对应** | `grid_search(...)` |

**分片**：1000 组参数 → N 个 chunk，每 Worker 处理一个 chunk，结果合并为完整 DataFrame。

### 3.4 `batch_backtest` — 批量策略回测

| 字段 | 值 |
|------|-----|
| **task_type** | `"batch_backtest"` |
| **输入** | `data_spec` + `strategies`（多策略）+ `fee_models`（多费率） |
| **输出** | `pd.DataFrame`（每策略 × 每费率一行） |
| **handler** | `compute.handlers.batch_backtest_handler` |
| **分片策略** | `param_wise`（按 strategy × fee_model 笛卡尔积） |
| **典型耗时** | 分钟级 |
| **V2 对应** | `batch_backtest(...)` |

**PAXG v5-redo 直接对应**：33 策略 × 4 费率 = 132 次回测。

### 3.5 `monte_carlo` — 蒙特卡洛模拟

| 字段 | 值 |
|------|-----|
| **task_type** | `"monte_carlo"` |
| **输入** | `data_spec` + `strategy_ref` + `n_simulations` + `seed` |
| **输出** | `pd.DataFrame`（每次模拟的指标分布） |
| **handler** | `compute.handlers.monte_carlo_handler` |
| **分片策略** | `param_wise`（按 simulation index 切分） |
| **典型耗时** | 分钟级 |
| **V2 对应** | `MonteCarloEngine` |

### 3.6 `walkforward` — 前向验证回测

| 字段 | 值 |
|------|-----|
| **task_type** | `"walkforward"` |
| **输入** | `data_spec` + `strategy_ref` + `train_window` + `test_window` + `step` |
| **输出** | `pd.DataFrame`（每窗口的 train/test 表现） |
| **handler** | `compute.handlers.walkforward_handler` |
| **分片策略** | `time_wise`（按时间窗口切分） |
| **典型耗时** | 分钟级 |
| **V2 对应** | `WalkForward` |

---

## 4. Tier 2 — 经典统计检验类（PAXG v1~v6 所需）

PAXG v1~v6 大量使用经典统计工具，V3.1 将其原子化为独立 task_type，避免每个研究脚本重新实现。

### 4.1 `correlation` — 相关分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"correlation"` |
| **输入** | `data_spec` 或内联数据 + `params.method` + `params.signals` + `params.targets` |
| **输出** | `dict`（r / p / CI / n）或 `pd.DataFrame`（矩阵） |
| **handler** | `compute.handlers.stats.correlation_handler` |
| **支持方法** | `pearson` / `spearman` / `kendall` / `partial`（偏相关）/ `cross_corr`（互相关） |
| **PAXG 对应** | v1（Pearson r=0.59）、v4（6×6 相关矩阵）、v7（偏相关 r(w_k, Range|x_4)） |

### 4.2 `hypothesis_test` — 假设检验

| 字段 | 值 |
|------|-----|
| **task_type** | `"hypothesis_test"` |
| **输入** | 数据 + `params.test` + `params.{alpha, alternative, ...}` |
| **输出** | `dict`（statistic / p_value / effect_size / CI） |
| **handler** | `compute.handlers.stats.hypothesis_handler` |
| **支持检验** | `t_test`（单样本/双样本/配对）/ `chi2_independence` / `chi2_goodness` / `ks_test` / `anderson_darling` / `f_test` / `levene` / `shapiro` / `mannwhitney` / `wilcoxon` |
| **PAXG 对应** | v3（2×2 卡方）、v6（5 窗口卡方 + Cramér's V） |

### 4.3 `bootstrap` — 自助法

| 字段 | 值 |
|------|-----|
| **task_type** | `"bootstrap"` |
| **输入** | 数据 + `params.stat_func`（cloudpickle）+ `params.n_resamples` + `params.ci_method` |
| **输出** | `dict`（estimate / ci_lower / ci_upper / bias / se） |
| **handler** | `compute.handlers.stats.bootstrap_handler` |
| **支持 CI** | `percentile` / `bc`（偏差校正）/ `bca` |
| **PAXG 对应** | v4-B（bootstrap 置信区间） |

### 4.4 `permutation_test` — 排列检验

| 字段 | 值 |
|------|-----|
| **task_type** | `"permutation_test"` |
| **输入** | 数据 + `params.stat_func` + `params.n_permutations` + `params.alternative` |
| **输出** | `dict`（observed_stat / null_distribution / p_value / effect_size） |
| **handler** | `compute.handlers.stats.permutation_handler` |
| **PAXG 对应** | v4-A（排列检验）、v7（MI 置换检验、TE 置换检验） |

### 4.5 `chow_test` — Chow 断点检验

| 字段 | 值 |
|------|-----|
| **task_type** | `"chow_test"` |
| **输入** | 时序数据 + `params.breakpoint`（时间点或索引） |
| **输出** | `dict`（F_stat / p_value / rss_before / rss_after） |
| **handler** | `compute.handlers.stats.chow_handler` |
| **PAXG 对应** | v4（Chow 断点检验稳定性） |

### 4.6 `survival_analysis` — 生存分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"survival_analysis"` |
| **输入** | `data_spec`（含 duration + event）+ `params.method` + `params.groups` |
| **输出** | `dict`（survival_curve / median_survival / log_rank_p / HR / CI） |
| **handler** | `compute.handlers.stats.survival_handler` |
| **支持方法** | `kaplan_meier` / `log_rank` / `cox_ph` / `nelson_aalen` |
| **PAXG 对应** | v6（Kaplan-Meier + log-rank + HR 森林图） |

### 4.7 `ecdf` — 经验累积分布

| 字段 | 值 |
|------|-----|
| **task_type** | `"ecdf"` |
| **输入** | 数据 + `params.groups`（可选分组） |
| **输出** | `pd.DataFrame`（x / ecdf / group） |
| **handler** | `compute.handlers.stats.ecdf_handler` |
| **PAXG 对应** | v6（Signal>0 vs Signal<0 的 ECDF + KS 检验） |

### 4.8 `multiple_testing` — 多重检验校正

| 字段 | 值 |
|------|-----|
| **task_type** | `"multiple_testing"` |
| **输入** | `params.p_values`（list）+ `params.method` + `params.alpha` |
| **输出** | `pd.DataFrame`（index / p_value / adjusted_p / reject） |
| **handler** | `compute.handlers.stats.multiple_testing_handler` |
| **支持方法** | `bonferroni` / `bh_fdr` / `by_fdr` / `holm` / `hochberg` |
| **PAXG 对应** | v4（30+ 检验 Bonferroni）、v6（15 检验 BH-FDR）、v7（168 检验双轨） |

---

## 5. Tier 3 — 信号处理与频域分析（PAXG v7 W/E 路线）

PAXG v7 的 W（小波）和 E（能量频谱）路线需要信号处理能力，V3.1 将其原子化。

### 5.1 `spectral_analysis` — 频谱分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"spectral_analysis"` |
| **输入** | 时序数据 + `params.method` + `params.{nperseg, noverlap, window}` |
| **输出** | `dict`（frequencies / psd / total_energy / band_energies / spectral_centroid / peak_freq） |
| **handler** | `compute.handlers.signal.spectral_handler` |
| **支持方法** | `welch` / `fft` / `stft` / `periodogram` |
| **PAXG 对应** | v7-E1（Welch PSD）、E4（交叉谱） |

### 5.2 `wavelet` — 小波分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"wavelet"` |
| **输入** | 时序数据 + `params.wavelet` + `params.scales` + `params.method` |
| **输出** | `dict`（coefficients / power / band_energies / coherence / phase） |
| **handler** | `compute.handlers.signal.wavelet_handler` |
| **支持方法** | `cwt`（连续小波）/ `dwt`（离散小波）/ `coherence`（小波相干）/ `cross_spectrum` |
| **依赖** | `PyWavelets>=1.1`（可选，fallback 自实现 Morlet） |
| **PAXG 对应** | v7-W1（CWT 多尺度分解）、W3（小波相干）、W2（频带能量） |

### 5.3 `spectral_entropy` — 谱熵

| 字段 | 值 |
|------|-----|
| **task_type** | `"spectral_entropy"` |
| **输入** | 时序数据 + `params.{nperseg, normalize}` |
| **输出** | `float`（谱熵值） |
| **handler** | `compute.handlers.signal.spectral_entropy_handler` |
| **PAXG 对应** | v7-E2（谱熵作为路径复杂度度量） |

### 5.4 `cross_spectrum` — 交叉谱分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"cross_spectrum"` |
| **输入** | 两列时序数据 + `params.{nperseg, noverlap}` |
| **输出** | `dict`（frequencies / csd / coherence / phase） |
| **handler** | `compute.handlers.signal.cross_spectrum_handler` |
| **PAXG 对应** | v7-E4（周末-周一收益率交叉谱相干） |

### 5.5 `filter_design` — 滤波器设计与应用

| 字段 | 值 |
|------|-----|
| **task_type** | `"filter_design"` |
| **输入** | 时序数据 + `params.filter_type` + `params.{cutoff, order}` |
| **输出** | `pd.Series`（滤波后数据） |
| **handler** | `compute.handlers.signal.filter_handler` |
| **支持类型** | `butterworth` / `kalman` / `savitzky_golay` / `hp_filter`（Hodrick-Prescott） |
| **应用** | 趋势分离、噪声去除 |

---

## 6. Tier 4 — 非线性动力学与信息论（PAXG v7 N 路线）

PAXG v7 的 N 路线（互信息、传递熵、Hurst、熵、RQA）是 V3.1 必须支持的核心能力。

### 6.1 `mutual_information` — 互信息

| 字段 | 值 |
|------|-----|
| **task_type** | `"mutual_information"` |
| **输入** | 两列数据 + `params.{estimator, k, n_neighbors}` |
| **输出** | `float`（MI 值，bits 或 nats） |
| **handler** | `compute.handlers.nonlinear.mi_handler` |
| **支持估计器** | `ksg`（Kraskov）/ `binning`（分箱）/ `sklearn`（封装） |
| **PAXG 对应** | v7-N1（36 对 MI 检测非线性依赖） |

### 6.2 `transfer_entropy` — 传递熵

| 字段 | 值 |
|------|-----|
| **task_type** | `"transfer_entropy"` |
| **输入** | 两列时序 + `params.{k, l, bins}` |
| **输出** | `dict`（te_forward / te_backward / net_te / significance） |
| **handler** | `compute.handlers.nonlinear.te_handler` |
| **实现** | 自实现分箱估计器（~60 行 numpy），未来可替换为 KSG 变体 |
| **PAXG 对应** | v7-N2（**关键假设**：周末→周一信息流向） |

### 6.3 `hurst_exponent` — Hurst 指数

| 字段 | 值 |
|------|-----|
| **task_type** | `"hurst_exponent"` |
| **输入** | 时序数据 + `params.method` |
| **输出** | `dict`（hurst / log_R / log_n / fit_r2） |
| **handler** | `compute.handlers.nonlinear.hurst_handler` |
| **支持方法** | `dfa`（去趋势波动分析）/ `rs`（重标极差） |
| **依赖** | 自实现（~40 行 numpy），可选 `nolds` |
| **PAXG 对应** | v7-N3（周末路径持久性） |

### 6.4 `sample_entropy` — 样本熵

| 字段 | 值 |
|------|-----|
| **task_type** | `"sample_entropy"` |
| **输入** | 时序数据 + `params.{m, r}` |
| **输出** | `float`（SampEn 值） |
| **handler** | `compute.handlers.nonlinear.sample_entropy_handler` |
| **依赖** | 自实现（~20 行），可选 `antropy` |
| **PAXG 对应** | v7-N4（路径复杂度） |

### 6.5 `permutation_entropy` — 排列熵

| 字段 | 值 |
|------|-----|
| **task_type** | `"permutation_entropy"` |
| **输入** | 时序数据 + `params.{m, tau}` |
| **输出** | `float`（PE 值） |
| **handler** | `compute.handlers.nonlinear.permutation_entropy_handler` |
| **依赖** | 自实现（~15 行），可选 `antropy` |
| **PAXG 对应** | v7-N4（路径复杂度） |

### 6.6 `rqa` — 递归定量分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"rqa"` |
| **输入** | 时序数据 + `params.{m, tau, epsilon}` |
| **输出** | `dict`（RR / DET / LAM / ENTR / L_max / recurrence_plot） |
| **handler** | `compute.handlers.nonlinear.rqa_handler` |
| **依赖** | 自实现简化版（~80 行），可选 `PyRQA`（需 JVM） |
| **PAXG 对应** | v7-N5（递归结构） |

### 6.7 `recurrence_plot` — 递归图

| 字段 | 值 |
|------|-----|
| **task_type** | `"recurrence_plot"` |
| **输入** | 时序数据 + `params.{m, tau, epsilon}` |
| **输出** | `np.ndarray`（2D 二值矩阵） |
| **handler** | `compute.handlers.nonlinear.recurrence_plot_handler` |
| **PAXG 对应** | v7-N5（3 个典型周末的递归图） |

---

## 7. Tier 5 — 灰色系统与软计算（PAXG v7 G 路线）

PAXG v7 的 G 路线（灰色关联、GM(1,1)）需要灰色系统理论支持。

### 7.1 `grey_relation` — 灰色关联分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"grey_relation"` |
| **输入** | 参考序列 + 比较序列（list）+ `params.{rho, normalize}` |
| **输出** | `dict`（relation_degrees / relation_matrix / rank） |
| **handler** | `compute.handlers.grey.grey_relation_handler` |
| **实现** | 自实现（< 50 行 numpy） |
| **PAXG 对应** | v7-G1（307×307 灰色关联矩阵）、G2（与参考模式关联度）、G4（偏相关） |

### 7.2 `gm11_predict` — GM(1,1) 灰色预测

| 字段 | 值 |
|------|-----|
| **task_type** | `"gm11_predict"` |
| **输入** | 时序数据 + `params.n_ahead` + `params.{alpha, ...}` |
| **输出** | `dict`（predicted / params_a_b / mape / mae / rmse） |
| **handler** | `compute.handlers.grey.gm11_handler` |
| **实现** | 自实现（< 30 行 numpy） |
| **PAXG 对应** | v7-G3（GM(1,1) 周一开盘预测） |

### 7.3 `grey_cluster` — 灰色聚类

| 字段 | 值 |
|------|-----|
| **task_type** | `"grey_cluster"` |
| **输入** | 数据矩阵 + `params.n_clusters` + `params.linkage` |
| **输出** | `dict`（labels / centroids / silhouette） |
| **handler** | `compute.handlers.grey.grey_cluster_handler` |
| **依赖** | 灰色关联 + `scipy.cluster.hierarchy` |
| **PAXG 对应** | v7-G1（周末路径灰色关联聚类） |

---

## 8. Tier 6 — 机器学习与数据挖掘

PAXG v7 的 F 路线（ML 融合）+ 量化通用 ML 需求。

### 8.1 `ml_train` — 机器学习训练

| 字段 | 值 |
|------|-----|
| **task_type** | `"ml_train"` |
| **输入** | 特征矩阵 + 标签 + `params.model_type` + `params.{hyperparams, cv}` |
| **输出** | `dict`（model_ref（cloudpickle）/ cv_scores / feature_importance / best_params） |
| **handler** | `compute.handlers.ml.train_handler` |
| **支持模型** | `random_forest` / `gbdt` / `xgboost` / `lightgbm` / `logistic` / `ridge` / `lasso` |
| **PAXG 对应** | v7-F3（RF 回归前向验证） |

### 8.2 `ml_predict` — 机器学习预测

| 字段 | 值 |
|------|-----|
| **task_type** | `"ml_predict"` |
| **输入** | 特征矩阵 + `model_ref`（cloudpickle） |
| **输出** | `np.ndarray`（预测值/类别） |
| **handler** | `compute.handlers.ml.predict_handler` |

### 8.3 `feature_importance` — 特征重要性

| 字段 | 值 |
|------|-----|
| **task_type** | `"feature_importance"` |
| **输入** | 特征矩阵 + 标签 + `params.method` |
| **输出** | `pd.DataFrame`（feature / importance / rank） |
| **handler** | `compute.handlers.ml.feature_importance_handler` |
| **支持方法** | `permutation` / `shap` / `gini` / `gain` / `mutual_info` |
| **PAXG 对应** | v7-F3（特征重要性排序） |

### 8.4 `walkforward_cv` — 前向验证交叉验证

| 字段 | 值 |
|------|-----|
| **task_type** | `"walkforward_cv"` |
| **输入** | 时序数据 + 模型 + `params.{train_size, test_size, step}` |
| **输出** | `dict`（fold_scores / mean / std / oos_performance） |
| **handler** | `compute.handlers.ml.walkforward_cv_handler` |
| **PAXG 对应** | v7-F3（5-fold 前向验证，保持时间顺序） |

### 8.5 `clustering` — 聚类分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"clustering"` |
| **输入** | 数据矩阵 + `params.method` + `params.n_clusters` |
| **输出** | `dict`（labels / centroids / silhouette / inertia） |
| **handler** | `compute.handlers.ml.clustering_handler` |
| **支持方法** | `kmeans` / `hierarchical` / `dbscan` / `gmms` |
| **PAXG 对应** | v7-E3（频谱 K-means 聚类） |

### 8.6 `dimension_reduction` — 降维

| 字段 | 值 |
|------|-----|
| **task_type** | `"dimension_reduction"` |
| **输入** | 数据矩阵 + `params.method` + `params.n_components` |
| **输出** | `dict`（transformed / explained_variance / components） |
| **handler** | `compute.handlers.ml.dim_reduction_handler` |
| **支持方法** | `pca` / `ica` / `tsne` / `umap` / `kpca` |
| **PAXG 对应** | v7-E3（t-SNE 频谱空间可视化） |

### 8.7 `classification_metrics` — 分类评估

| 字段 | 值 |
|------|-----|
| **task_type** | `"classification_metrics"` |
| **输入** | y_true + y_pred + `params.{labels, average}` |
| **输出** | `dict`（accuracy / precision / recall / f1 / roc_auc / confusion_matrix） |
| **handler** | `compute.handlers.ml.classification_metrics_handler` |
| **PAXG 对应** | v7-F4（ML 分类评估） |

---

## 9. Tier 7 — 投资组合与风险管理（量化核心扩展）

量化研究通用能力，部分 PAXG 间接需要，部分为标准量化工具箱。

### 9.1 `portfolio_optimization` — 投资组合优化

| 字段 | 值 |
|------|-----|
| **task_type** | `"portfolio_optimization"` |
| **输入** | 收益率矩阵 + `params.method` + `params.{target_return, risk_free}` |
| **输出** | `dict`（weights / expected_return / volatility / sharpe） |
| **handler** | `compute.handlers.portfolio.opt_handler` |
| **支持方法** | `markowitz` / `black_litterman` / `risk_parity` / `min_variance` / `max_sharpe` |

### 9.2 `risk_metrics` — 风险度量

| 字段 | 值 |
|------|-----|
| **task_type** | `"risk_metrics"` |
| **输入** | 收益率序列 + `params.{confidence, window}` |
| **输出** | `dict`（var / cvar / max_drawdown / sharpe / sortino / calmar / information_ratio / volatility） |
| **handler** | `compute.handlers.portfolio.risk_handler` |
| **支持风险** | `historical_var` / `parametric_var` / `monte_carlo_var` / `cvar` |

### 9.3 `factor_analysis` — 因子分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"factor_analysis"` |
| **输入** | 收益率 + 因子矩阵 + `params.method` |
| **输出** | `dict`（factor_returns / t_stats / r_squared / residuals） |
| **handler** | `compute.handlers.portfolio.factor_handler` |
| **支持方法** | `capm` / `fama_french_3` / `fama_french_5` / `carhart_4` / `custom` |

### 9.4 `cointegration` — 协整检验

| 字段 | 值 |
|------|-----|
| **task_type** | `"cointegration"` |
| **输入** | 两列价格序列 + `params.method` |
| **输出** | `dict`（test_stat / p_value / hedge_ratio / half_life / is_cointegrated） |
| **handler** | `compute.handlers.portfolio.cointegration_handler` |
| **支持方法** | `engle_granger` / `johansen` / `phillips_ouliaris` |
| **应用** | 配对交易、统计套利 |

### 9.5 `regime_detection` — 市场状态识别

| 字段 | 值 |
|------|-----|
| **task_type** | `"regime_detection"` |
| **输入** | 时序数据 + `params.method` + `params.n_regimes` |
| **输出** | `dict`（labels / transition_matrix / regime_stats） |
| **handler** | `compute.handlers.portfolio.regime_handler` |
| **支持方法** | `hmm` / `change_point` / `markov_switching` |
| **PAXG 对应** | v4-E（regime 切换分析） |

### 9.6 `stress_test` — 压力测试

| 字段 | 值 |
|------|-----|
| **task_type** | `"stress_test"` |
| **输入** | 组合 + `params.scenarios` |
| **输出** | `pd.DataFrame`（scenario / pnl / max_drawdown / var_breach） |
| **handler** | `compute.handlers.portfolio.stress_handler` |
| **支持场景** | `historical`（2008/2020/2022 等历史危机）/ `monte_carlo` / `parametric` |

---

## 10. Tier 8 — 前沿与预留（未来扩展）

以下 task_type 在 V3.1 协议层**预留接口**（注册到 task_type 表），但 handler 可后补。预留的目的是确保未来新增时**协议零改动**。

### 10.1 `bayesian_inference` — 贝叶斯推断

| 字段 | 值 |
|------|-----|
| **task_type** | `"bayesian_inference"` |
| **依赖** | `pymc` / `stan` / `numpyro` |
| **应用** | 参数不确定性量化、贝叶斯回归、层次模型 |

### 10.2 `deep_learning` — 深度学习

| 字段 | 值 |
|------|-----|
| **task_type** | `"deep_learning"` |
| **依赖** | `torch` / `tensorflow` |
| **硬件** | GPU（Worker 注册时声明 `gpu.devices`） |
| **应用** | LSTM/Transformer 时序预测、表示学习 |

### 10.3 `reinforcement_learning` — 强化学习

| 字段 | 值 |
|------|-----|
| **task_type** | `"reinforcement_learning"` |
| **依赖** | `stable-baselines3` / `ray[rllib]` |
| **应用** | 动态仓位管理、执行算法优化 |

### 10.4 `order_flow` — 订单流分析

| 字段 | 值 |
|------|-----|
| **task_type** | `"order_flow"` |
| **依赖** | L2/L3 行情数据 |
| **应用** | 微观结构、大单检测、流动性分析 |

### 10.5 `agent_based_simulation` — 基于代理的仿真

| 字段 | 值 |
|------|-----|
| **task_type** | `"agent_based_simulation"` |
| **依赖** | `mesa` / 自实现 |
| **应用** | 市场涌现行为、策略博弈、系统性风险仿真 |

---

## 11. task_type 注册表汇总

| Tier | task_type | 类别 | 状态 | 分片策略 | PAXG 对应 |
|------|-----------|------|------|---------|----------|
| 1 | `indicator` | 回测 | 迁移 | none | v1~v7 |
| 1 | `backtest` | 回测 | 迁移 | none | v5 |
| 1 | `grid_search` | 回测 | 迁移 | param_wise | v5 |
| 1 | `batch_backtest` | 回测 | 迁移 | param_wise | v5-redo |
| 1 | `monte_carlo` | 回测 | 迁移 | param_wise | v5 |
| 1 | `walkforward` | 回测 | 迁移 | time_wise | v5/v7 |
| 2 | `correlation` | 统计 | 新增 | none | v1/v4/v7 |
| 2 | `hypothesis_test` | 统计 | 新增 | none | v3/v6 |
| 2 | `bootstrap` | 统计 | 新增 | param_wise | v4 |
| 2 | `permutation_test` | 统计 | 新增 | param_wise | v4/v7 |
| 2 | `chow_test` | 统计 | 新增 | none | v4 |
| 2 | `survival_analysis` | 统计 | 新增 | none | v6 |
| 2 | `ecdf` | 统计 | 新增 | none | v6 |
| 2 | `multiple_testing` | 统计 | 新增 | none | v4/v6/v7 |
| 3 | `spectral_analysis` | 信号 | 新增 | none | v7-E1 |
| 3 | `wavelet` | 信号 | 新增 | none | v7-W1/W2/W3 |
| 3 | `spectral_entropy` | 信号 | 新增 | none | v7-E2 |
| 3 | `cross_spectrum` | 信号 | 新增 | none | v7-E4 |
| 3 | `filter_design` | 信号 | 新增 | none | — |
| 4 | `mutual_information` | 非线性 | 新增 | none | v7-N1 |
| 4 | `transfer_entropy` | 非线性 | 新增 | none | v7-N2 |
| 4 | `hurst_exponent` | 非线性 | 新增 | none | v7-N3 |
| 4 | `sample_entropy` | 非线性 | 新增 | none | v7-N4 |
| 4 | `permutation_entropy` | 非线性 | 新增 | none | v7-N4 |
| 4 | `rqa` | 非线性 | 新增 | none | v7-N5 |
| 4 | `recurrence_plot` | 非线性 | 新增 | none | v7-N5 |
| 5 | `grey_relation` | 灰色 | 新增 | none | v7-G1/G2 |
| 5 | `gm11_predict` | 灰色 | 新增 | none | v7-G3 |
| 5 | `grey_cluster` | 灰色 | 新增 | none | v7-G1 |
| 6 | `ml_train` | ML | 新增 | none | v7-F3 |
| 6 | `ml_predict` | ML | 新增 | none | v7-F3 |
| 6 | `feature_importance` | ML | 新增 | none | v7-F3 |
| 6 | `walkforward_cv` | ML | 新增 | time_wise | v7-F3 |
| 6 | `clustering` | ML | 新增 | none | v7-E3 |
| 6 | `dimension_reduction` | ML | 新增 | none | v7-E3 |
| 6 | `classification_metrics` | ML | 新增 | none | v7-F4 |
| 7 | `portfolio_optimization` | 组合 | 预留 | none | — |
| 7 | `risk_metrics` | 组合 | 新增 | none | 通用 |
| 7 | `factor_analysis` | 组合 | 预留 | none | — |
| 7 | `cointegration` | 组合 | 预留 | none | — |
| 7 | `regime_detection` | 组合 | 新增 | none | v4-E |
| 7 | `stress_test` | 组合 | 预留 | none | — |
| 8 | `bayesian_inference` | 前沿 | 预留 | none | — |
| 8 | `deep_learning` | 前沿 | 预留 | none | — |
| 8 | `reinforcement_learning` | 前沿 | 预留 | none | — |
| 8 | `order_flow` | 前沿 | 预留 | none | — |
| 8 | `agent_based_simulation` | 前沿 | 预留 | none | — |

---

## 12. ComputeSpec 扩展策略

V3.1 的 `ComputeSpec` 在 V3 基础上**扁平化**为 `task_type` + `params` 两层，避免为每个 task_type 新增专用字段：

```python
@dataclass
class ComputeSpec:
    task_type: str                    # 见 §11 注册表
    strategy_ref: Optional[str] = None  # cloudpickle:base64...（回测类需要）
    strategy_codec: str = "cloudpickle"
    params: dict = field(default_factory=dict)  # 任务类型特定参数（JSON 可序列化）
    # ── 回测类共用字段（从 V3 保留，便于 handler 直接读取）──
    initial_cash: float = 1_000_000.0
    cost_model: Optional[str] = None
    fill_model: Optional[str] = None
    execution_model: Optional[str] = None
    benchmark: Optional[str] = None
    trade_on: str = "open"
    allow_short: bool = False
    periods_per_year: Optional[int] = None
    # ── 网格搜索/批量共用 ──
    param_grid: Optional[dict] = None
    metric: str = "sharpe"
    maximize: bool = True
    strategies: Optional[dict] = None
    fee_models: Optional[list] = None
    # ── 蒙特卡洛共用 ──
    n_simulations: int = 1000
    seed: int = 0
```

**新增 task_type 的扩展规则**：
1. 优先将参数放入 `params` dict（如 `params.method="welch"`, `params.nperseg=24`）
2. 仅当某字段被多个 task_type 共用且语义明确时，才提升为 ComputeSpec 顶层字段
3. 所有新字段必须有默认值（前向兼容）
4. handler 通过 `spec.compute_spec.params.get("method", "default")` 读取

**`strategy_ref` 编码**：
- `cloudpickle:base64...` — Python 闭包策略（默认）
- `registry:ma_cross` — 注册表中的命名策略
- `dsl:DSL表达式` — DSL 编译的策略
- `none` — 无策略（统计/信号/非线性类任务）

---

## 13. 与 PAXG v1~v7 的映射矩阵

下表验证 V3.1 的 task_type 完整覆盖 PAXG v1~v7 全部研究功能：

| PAXG 版本 | 研究内容 | 使用的 task_type |
|----------|---------|-----------------|
| v1 | Pearson/Spearman 相关、t检验、CI、滚动 | `correlation` / `hypothesis_test` / `indicator`(rolling) |
| v2 | 独立涨跌幅相关 | `correlation` |
| v3 | 路径顺序 2×2 卡方 | `hypothesis_test`(chi2) / `ecdf` |
| v4-A | 排列检验、bootstrap、子期 | `permutation_test` / `bootstrap` |
| v4-B | 6×6 相关矩阵、Chow 断点 | `correlation`(matrix) / `chow_test` |
| v4-D | 子期对比、滚动 | `correlation` / `indicator`(rolling) |
| v4-E | regime 切换、decay | `regime_detection` |
| v5 | 132 次回测（33 策略 × 4 费率） | `batch_backtest` / `backtest` |
| v5-redo | 同上（用 BacktestEngine） | `batch_backtest` |
| v6 | 多窗口卡方、生存分析、ECDF、HR | `hypothesis_test`(chi2) / `survival_analysis` / `ecdf` |
| v7-W | CWT、小波相干、频带能量 | `wavelet` |
| v7-E | Welch PSD、谱熵、交叉谱、K-means | `spectral_analysis` / `spectral_entropy` / `cross_spectrum` / `clustering` |
| v7-G | 灰色关联、GM(1,1)、层次聚类 | `grey_relation` / `gm11_predict` / `grey_cluster` |
| v7-N1 | 互信息（KSG） | `mutual_information` |
| v7-N2 | 传递熵（信息流向） | `transfer_entropy` |
| v7-N3 | Hurst 指数（DFA） | `hurst_exponent` |
| v7-N4 | 样本熵、排列熵 | `sample_entropy` / `permutation_entropy` |
| v7-N5 | 递归定量分析 | `rqa` / `recurrence_plot` |
| v7-F1 | 28 信号相关矩阵 | `correlation`(matrix) |
| v7-F2 | 逐步回归 | `ml_train`(linear) |
| v7-F3 | 随机森林、前向验证、特征重要性 | `ml_train`(rf) / `walkforward_cv` / `feature_importance` |
| v7-F4 | ML 分类评估 | `ml_train`(classifier) / `classification_metrics` |
| v7-§12 | v7-S1~S4 策略回测 | `batch_backtest` / `backtest` |
| v7-§13 | 多重检验校正、置换检验 | `multiple_testing` / `permutation_test` |

**覆盖率验证**：PAXG v1~v7 全部研究功能均有对应 task_type，无遗漏。

---

## 14. 实现优先级

| 优先级 | Tier | task_type | 理由 |
|--------|------|-----------|------|
| **P0** | 1 | 全部 6 个 | 回测是核心，PAXG v5 直接依赖 |
| **P0** | 2 | `correlation` / `hypothesis_test` / `bootstrap` / `permutation_test` / `multiple_testing` | PAXG v1~v6 基础统计 |
| **P1** | 2 | `survival_analysis` / `ecdf` / `chow_test` | PAXG v6 专属 |
| **P1** | 3 | `spectral_analysis` / `wavelet` / `spectral_entropy` / `cross_spectrum` | PAXG v7 W/E |
| **P1** | 4 | 全部 7 个 | PAXG v7 N 路线（含关键假设 H_N2） |
| **P1** | 5 | 全部 3 个 | PAXG v7 G 路线 |
| **P2** | 6 | 全部 7 个 | PAXG v7 F 路线 + 通用 ML |
| **P2** | 7 | `risk_metrics` / `regime_detection` | 量化通用，PAXG v4 间接 |
| **P3** | 7 | `portfolio_optimization` / `factor_analysis` / `cointegration` / `stress_test` | 预留接口，handler 后补 |
| **P3** | 8 | 全部 5 个 | 前沿预留，协议支持即可 |

---

## 15. 总结

V3.1 的金融计算任务体系以 **47 个原子 task_type** 覆盖：
- PAXG v1~v7 全部研究功能（36 个必须实现）
- 量化通用工具箱（组合/风险/ML，11 个预留）

**核心设计原则**：
1. **协议零感知业务** —— 新增 task_type 只需注册 handler，协议/传输/调度零改动
2. **紧贴金融场景** —— 不 overgeneralize，每个 task_type 都有明确量化用途
3. **预留扩展点** —— Tier 7~8 接口预留，未来新增不动协议
4. **分片友好** —— 重型任务（grid_search/batch_backtest/monte_carlo/bootstrap/permutation_test/walkforward_cv）支持分片并行

**与 V3 的差异**：
- V3 的 6 个 task_type → V3.1 的 47 个（覆盖范围从"回测+指标"扩展到"量化全栈"）
- 新增统计/信号/非线性/灰色/ML/组合 6 个新类别
- `ComputeSpec.params` dict 统一承载新任务参数，避免字段爆炸

---

*本文件为 V3.1 Compute 模块 handler 注册表的设计基线。详细架构见 [DESIGN_ARCH_COMPUTE_V31.md](DESIGN_ARCH_COMPUTE_V31.md)。*
