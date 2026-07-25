# P7 — 高级 Handlers 实现报告

> **Phase**：P7
> **完成日期**：2026-07-24
> **状态**：✅ 完成
> **测试数**：60 项新增（P7），Compute 包共 235 项通过

---

## 1. 实现概览

按 `P7.md` 计划实现 **32 个高级 handler**（Tier 2-7），覆盖 PAXG v1~v7 全部研究功能：

| Tier | 类别 | 实现数 | PAXG 对应 |
|------|------|--------|----------|
| 2 | 经典统计检验 | 8 | v1~v6 |
| 3 | 信号处理 | 5 | v7 W/E |
| 4 | 非线性动力学 | 7 | v7 N |
| 5 | 灰色系统 | 3 | v7 G |
| 6 | 机器学习 | 7 | v7 F + 通用 |
| 7 | 组合风险 | 2 | v4-E + 通用 |
| **合计** | | **32** | |

加上 Tier 1 的 6 个，**V3.1 共注册 38 个 task_type handler**（目标 36 实现 + 2 额外）。

---

## 2. 关键 handler 实现

### Tier 2 — 统计检验（8 个）
- `correlation`：Pearson/Spearman/Kendall + Fisher z CI
- `hypothesis_test`：t_test/chi2/ks/shapiro/mannwhitney/wilcoxon
- `bootstrap`：自助法 CI（percentile）
- `permutation_test`：排列检验 + null distribution
- `chow_test`：Chow 断点检验
- `survival_analysis`：Kaplan-Meier 自实现
- `ecdf`：经验累积分布（支持分组）
- `multiple_testing`：Bonferroni/BH-FDR/Holm

### Tier 3 — 信号处理（5 个）
- `spectral_analysis`：Welch/FFT/periodogram
- `wavelet`：CWT（PyWavelets + 自实现 Morlet fallback）
- `spectral_entropy`：归一化谱熵
- `cross_spectrum`：CSD + 相干 + 相位
- `filter_design`：Butterworth/Savitzky-Golay

### Tier 4 — 非线性动力学（7 个）
- `mutual_information`：分箱估计 + sklearn KSG
- `transfer_entropy`：**PAXG v7 N2 关键** — 分箱估计器 + 置换检验
- `hurst_exponent`：DFA + R/S
- `sample_entropy` / `permutation_entropy`：自实现
- `rqa`：RR/DET/LAM/ENTR/L_max
- `recurrence_plot`：递归矩阵

### Tier 5 — 灰色系统（3 个）
- `grey_relation`：灰色关联度 + 排序
- `gm11_predict`：GM(1,1) 预测 + MAPE/MAE/RMSE
- `grey_cluster`：层次聚类

### Tier 6 — 机器学习（7 个）
- `ml_train`：RF/GBDT/Ridge/Lasso + 交叉验证
- `ml_predict`：cloudpickle 模型预测
- `feature_importance`：gini/permutation/mutual_info
- `walkforward_cv`：前向验证
- `clustering`：KMeans/hierarchical/DBSCAN
- `dimension_reduction`：PCA/t-SNE/ICA
- `classification_metrics`：accuracy/precision/recall/f1/AUC

### Tier 7 — 组合风险（2 个）
- `risk_metrics`：VaR/CVaR/MaxDD/Sharpe/Sortino/Calmar
- `regime_detection`：变点检测 + HMM

---

## 3. 测试覆盖

| 测试文件 | 测试数 | 覆盖 |
|---------|--------|------|
| `test_handlers_advanced.py` | 60 | Tier 2(15) + Tier 3(10) + Tier 4(15) + Tier 5(6) + Tier 6(10) + Tier 7(4) |
| **合计** | **60** | 全部通过 ✅ |

---

## 4. 验收标准

| 标准 | 验证方法 | 结果 |
|------|---------|------|
| 32 个 handler 全部注册 | `ALL_TASK_TYPES` 38 个 | ✅ |
| 60 项测试全部通过 | `pytest test_handlers_advanced.py` | ✅ |
| **PAXG v7 N2 传递熵可用** | `test_transfer_entropy` | ✅ te_forward/p_value |
| 自实现算法验证 | 白噪声 H≈0.5 / 独立序列 MI≈0 | ✅ |
| 可选依赖优雅降级 | PyWavelets fallback / hmmlearn skip | ✅ |

---

## 5. PAXG v1~v7 功能覆盖

| PAXG 版本 | 使用的 task_type | 状态 |
|----------|-----------------|------|
| v1 | correlation / hypothesis_test | ✅ |
| v2 | correlation | ✅ |
| v3 | hypothesis_test(chi2) / ecdf | ✅ |
| v4-A | permutation_test / bootstrap | ✅ |
| v4-B | correlation / chow_test | ✅ |
| v4-E | regime_detection | ✅ |
| v5 | batch_backtest / backtest | ✅ |
| v6 | survival_analysis / ecdf / hypothesis_test | ✅ |
| v7-W | wavelet | ✅ |
| v7-E | spectral_analysis / spectral_entropy / cross_spectrum | ✅ |
| v7-G | grey_relation / gm11_predict | ✅ |
| v7-N1 | mutual_information | ✅ |
| v7-N2 | **transfer_entropy** | ✅ |
| v7-N3 | hurst_exponent | ✅ |
| v7-N4 | sample_entropy / permutation_entropy | ✅ |
| v7-N5 | rqa / recurrence_plot | ✅ |
| v7-F | ml_train / walkforward_cv / feature_importance | ✅ |

**覆盖率：100%**

---

*P7 高级 handlers 已完成，PAXG v1~v7 全部研究功能可用。*
