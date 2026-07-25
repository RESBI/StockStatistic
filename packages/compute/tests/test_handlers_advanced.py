"""test_handlers_advanced.py — Tier 2-7 高级 handler 测试 (60 项)。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
from stockstat_compute.handlers import dispatch, ALL_TASK_TYPES


def make_spec(task_type, data=None, **params):
    cs_params = dict(params)
    if data is not None:
        cs_params["_inline_data"] = data
    return TaskSpec(
        task_id=f"test-{task_type}",
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type=task_type, params=cs_params),
    )


@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def price_series(rng):
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 200))))


@pytest.fixture
def returns(rng):
    return rng.normal(0.001, 0.02, 500)


# ── Tier 2 统计 (15 项) ──

class TestStatsHandlers:
    def test_correlation(self, price_series):
        x = price_series.values
        y = price_series.shift(1).fillna(100).values
        result = dispatch(make_spec("correlation", x=x, y=y, method="pearson"))
        assert "r" in result and "p_value" in result

    def test_correlation_spearman(self, price_series):
        x = price_series.values
        y = price_series.shift(1).fillna(100).values
        result = dispatch(make_spec("correlation", x=x, y=y, method="spearman"))
        assert "r" in result

    def test_hypothesis_test_chi2(self):
        table = [[10, 20], [30, 40]]
        result = dispatch(make_spec("hypothesis_test", test="chi2_independence", table=table))
        assert "statistic" in result and "p_value" in result

    def test_hypothesis_test_t(self, rng):
        x = rng.normal(0, 1, 100)
        result = dispatch(make_spec("hypothesis_test", test="t_test", x=x, popmean=0))
        assert "p_value" in result

    def test_bootstrap(self, rng):
        data = rng.normal(5, 2, 200)
        result = dispatch(make_spec("bootstrap", data, n_resamples=100))
        assert "ci_lower" in result and "ci_upper" in result

    def test_permutation_test(self, rng):
        x = rng.normal(0, 1, 50)
        y = rng.normal(0.5, 1, 50)
        result = dispatch(make_spec("permutation_test", {"x": x, "y": y}, n_permutations=50))
        assert "p_value" in result

    def test_chow_test(self, rng):
        data = np.concatenate([rng.normal(0, 1, 50), rng.normal(1, 1, 50)])
        result = dispatch(make_spec("chow_test", data, breakpoint=50))
        assert "F_stat" in result

    def test_survival_analysis(self):
        data = {"duration": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "event": [1, 1, 0, 1, 1, 0, 1, 1, 0, 1]}
        result = dispatch(make_spec("survival_analysis", data))
        assert "survival_curve" in result

    def test_ecdf(self, rng):
        data = rng.normal(0, 1, 100)
        result = dispatch(make_spec("ecdf", data))
        assert "x" in result and "ecdf" in result

    def test_multiple_testing(self):
        p_values = [0.001, 0.01, 0.04, 0.03, 0.5]
        result = dispatch(make_spec("multiple_testing", p_values=p_values, method="bh_fdr"))
        assert len(result) == 5
        assert "adjusted_p" in result.columns

    def test_multiple_testing_bonferroni(self):
        result = dispatch(make_spec("multiple_testing", p_values=[0.01, 0.02], method="bonferroni"))
        assert result["adjusted_p"].iloc[0] == 0.02

    def test_hypothesis_test_shapiro(self, rng):
        x = rng.normal(0, 1, 100)
        result = dispatch(make_spec("hypothesis_test", test="shapiro", x=x))
        assert "p_value" in result

    def test_correlation_kendall(self, price_series):
        x = price_series.values[:50]
        y = price_series.shift(1).fillna(100).values[:50]
        result = dispatch(make_spec("correlation", x=x, y=y, method="kendall"))
        assert "r" in result

    def test_ecdf_groups(self):
        data = {"A": [1, 2, 3], "B": [4, 5, 6]}
        result = dispatch(make_spec("ecdf", data, groups=data))
        assert "A" in result

    def test_bootstrap_ci_method(self, rng):
        data = rng.normal(0, 1, 100)
        result = dispatch(make_spec("bootstrap", data, n_resamples=50, ci_method="percentile"))
        assert "se" in result


# ── Tier 3 信号 (10 项) ──

class TestSignalHandlers:
    def test_spectral_analysis(self, rng):
        signal = np.sin(np.linspace(0, 20, 500))
        result = dispatch(make_spec("spectral_analysis", signal, method="welch", nperseg=128))
        assert "frequencies" in result and "psd" in result

    def test_spectral_analysis_fft(self, rng):
        signal = np.sin(np.linspace(0, 20, 256))
        result = dispatch(make_spec("spectral_analysis", signal, method="fft"))
        assert "psd" in result

    def test_wavelet(self, rng):
        signal = np.sin(np.linspace(0, 10, 200))
        result = dispatch(make_spec("wavelet", signal, method="cwt", scales=[1, 2, 4, 8]))
        assert "coefficients" in result and "power" in result

    def test_spectral_entropy(self, rng):
        signal = np.sin(np.linspace(0, 20, 500))
        result = dispatch(make_spec("spectral_entropy", signal))
        assert "spectral_entropy" in result

    def test_cross_spectrum(self, rng):
        x = np.sin(np.linspace(0, 20, 500))
        y = np.sin(np.linspace(0, 20, 500) + 0.5)
        result = dispatch(make_spec("cross_spectrum", {"x": x, "y": y}))
        assert "coherence" in result

    def test_filter_design(self, rng):
        signal = np.sin(np.linspace(0, 10, 200)) + rng.normal(0, 0.1, 200)
        result = dispatch(make_spec("filter_design", signal, filter_type="butterworth", cutoff=0.1))
        assert isinstance(result, list)

    def test_spectral_analysis_has_peak(self):
        signal = np.sin(np.linspace(0, 20 * np.pi, 1000))
        result = dispatch(make_spec("spectral_analysis", signal, method="welch", nperseg=256))
        assert result["peak_freq"] != 0

    def test_wavelet_fallback(self, rng):
        # 测试自实现 Morlet（如果 pywt 未装）
        signal = np.sin(np.linspace(0, 10, 200))
        result = dispatch(make_spec("wavelet", signal, method="cwt", scales=[1, 2, 4]))
        assert "method" in result

    def test_spectral_entropy_normalized(self, rng):
        signal = rng.normal(0, 1, 500)
        result = dispatch(make_spec("spectral_entropy", signal, normalize=True))
        assert 0 <= result["spectral_entropy"] <= 1

    def test_filter_savgol(self, rng):
        signal = np.sin(np.linspace(0, 10, 200)) + rng.normal(0, 0.1, 200)
        result = dispatch(make_spec("filter_design", signal, filter_type="savitzky_golay"))
        assert isinstance(result, list)


# ── Tier 4 非线性 (15 项) ──

class TestNonlinearHandlers:
    def test_mutual_information(self, rng):
        x = rng.normal(0, 1, 200)
        y = x + rng.normal(0, 0.5, 200)
        result = dispatch(make_spec("mutual_information", {"x": x, "y": y}, estimator="binning"))
        assert "mutual_information" in result

    def test_transfer_entropy(self, rng):
        x = rng.normal(0, 1, 100)
        y = np.roll(x, 1)  # y 滞后于 x
        result = dispatch(make_spec("transfer_entropy", {"x": x, "y": y}, n_permutations=20))
        assert "te_forward" in result and "p_value" in result

    def test_hurst_dfa(self, rng):
        x = np.cumsum(rng.normal(0, 1, 1000))
        result = dispatch(make_spec("hurst_exponent", x, method="dfa"))
        assert "hurst" in result

    def test_hurst_rs(self, rng):
        x = np.cumsum(rng.normal(0, 1, 1000))
        result = dispatch(make_spec("hurst_exponent", x, method="rs"))
        assert "hurst" in result

    def test_sample_entropy(self, rng):
        x = rng.normal(0, 1, 100)
        result = dispatch(make_spec("sample_entropy", x, m=2, r=0.2))
        assert "sample_entropy" in result

    def test_permutation_entropy(self, rng):
        x = rng.normal(0, 1, 100)
        result = dispatch(make_spec("permutation_entropy", x, m=4, tau=1))
        assert "permutation_entropy" in result

    def test_rqa(self, rng):
        x = np.sin(np.linspace(0, 20, 200))
        result = dispatch(make_spec("rqa", x, m=3, tau=1))
        assert "RR" in result and "DET" in result

    def test_recurrence_plot(self, rng):
        x = np.sin(np.linspace(0, 20, 100))
        result = dispatch(make_spec("recurrence_plot", x, m=3, tau=1))
        assert "recurrence_plot" in result

    def test_transfer_entropy_independent(self, rng):
        # 独立序列 TE 应接近 0
        x = rng.normal(0, 1, 100)
        y = rng.normal(0, 1, 100)
        result = dispatch(make_spec("transfer_entropy", {"x": x, "y": y}, n_permutations=10))
        assert abs(result["te_forward"]) < 1.0  # 宽松

    def test_hurst_white_noise(self, rng):
        x = rng.normal(0, 1, 1000)
        result = dispatch(make_spec("hurst_exponent", x, method="rs"))
        # 白噪声 H ≈ 0.5
        assert abs(result["hurst"] - 0.5) < 0.3

    def test_mutual_information_independent(self, rng):
        x = rng.normal(0, 1, 500)
        y = rng.normal(0, 1, 500)
        result = dispatch(make_spec("mutual_information", {"x": x, "y": y}))
        assert result["mutual_information"] < 0.5

    def test_sample_entropy_constant(self):
        x = np.ones(100)
        result = dispatch(make_spec("sample_entropy", x, m=2, r=0.1))
        # 常数序列熵应很低或 inf
        assert result["sample_entropy"] >= 0 or np.isinf(result["sample_entropy"])

    def test_rqa_structure(self, rng):
        x = np.sin(np.linspace(0, 20, 200))
        result = dispatch(make_spec("rqa", x, m=2, tau=1))
        assert 0 <= result["RR"] <= 1
        assert 0 <= result["DET"] <= 1

    def test_recurrence_plot_shape(self, rng):
        x = np.sin(np.linspace(0, 20, 100))
        result = dispatch(make_spec("recurrence_plot", x, m=3, tau=1))
        assert len(result["shape"]) == 2

    def test_permutation_entropy_constant(self):
        x = np.ones(100)
        result = dispatch(make_spec("permutation_entropy", x, m=3, tau=1))
        assert result["permutation_entropy"] >= 0


# ── Tier 5 灰色 (6 项) ──

class TestGreyHandlers:
    def test_grey_relation(self):
        data = {"reference": [1, 2, 3, 4, 5],
                "sequences": [[1, 2, 3, 4, 5], [2, 3, 4, 5, 6], [5, 4, 3, 2, 1]]}
        result = dispatch(make_spec("grey_relation", data, rho=0.5))
        assert "relation_degrees" in result and len(result["relation_degrees"]) == 3

    def test_gm11_predict(self):
        x = [1, 2, 4, 8, 16, 32]
        result = dispatch(make_spec("gm11_predict", x, n_ahead=2))
        assert "predicted" in result and len(result["predicted"]) == 2

    def test_gm11_exponential(self):
        x = np.exp(np.linspace(0, 5, 10))
        result = dispatch(make_spec("gm11_predict", x, n_ahead=3))
        assert "mape" in result

    def test_grey_relation_rank(self):
        data = {"reference": [1, 2, 3, 4, 5],
                "sequences": [[1, 2, 3, 4, 5], [5, 4, 3, 2, 1]]}
        result = dispatch(make_spec("grey_relation", data))
        assert "rank" in result

    def test_gm11_insufficient_data(self):
        result = dispatch(make_spec("gm11_predict", [1, 2], n_ahead=1))
        assert "error" in result or len(result.get("predicted", [])) == 0

    def test_grey_cluster(self, rng):
        X = rng.normal(0, 1, (50, 3))
        result = dispatch(make_spec("grey_cluster", X, n_clusters=3))
        assert "labels" in result


# ── Tier 6 ML (10 项) ──

class TestMLHandlers:
    def test_ml_train_rf(self, rng):
        X = rng.normal(0, 1, (100, 5))
        y = X[:, 0] * 2 + rng.normal(0, 0.1, 100)
        result = dispatch(make_spec("ml_train", {"X": X, "y": y}, model_type="random_forest"))
        assert "model_ref" in result and "cv_scores" in result

    def test_ml_predict(self, rng):
        from stockstat_foundation import cloudpickle_dumps
        from sklearn.ensemble import RandomForestRegressor
        X = rng.normal(0, 1, (50, 3))
        y = X[:, 0]
        model = RandomForestRegressor(n_estimators=10, random_state=42)
        model.fit(X, y)
        result = dispatch(make_spec("ml_predict", X[:5],
                                     model_ref=f"cloudpickle:{cloudpickle_dumps(model)}"))
        assert "predictions" in result

    def test_feature_importance(self, rng):
        X = rng.normal(0, 1, (100, 5))
        y = X[:, 0] * 2 + rng.normal(0, 0.1, 100)
        result = dispatch(make_spec("feature_importance", {"X": X, "y": y}, method="gini"))
        assert "importance" in result.columns

    def test_walkforward_cv(self, rng):
        X = rng.normal(0, 1, (200, 3))
        y = np.cumsum(rng.normal(0, 1, 200))
        result = dispatch(make_spec("walkforward_cv", {"X": X, "y": y}, n_folds=3))
        assert "fold_scores" in result

    def test_clustering_kmeans(self, rng):
        X = np.vstack([rng.normal(0, 1, (50, 2)), rng.normal(5, 1, (50, 2))])
        result = dispatch(make_spec("clustering", X, method="kmeans", n_clusters=2))
        assert "labels" in result and len(result["labels"]) == 100

    def test_dimension_reduction_pca(self, rng):
        X = rng.normal(0, 1, (50, 5))
        result = dispatch(make_spec("dimension_reduction", X, method="pca", n_components=2))
        assert "transformed" in result and "explained_variance" in result

    def test_classification_metrics(self):
        y_true = [0, 1, 0, 1, 0, 1]
        y_pred = [0, 1, 1, 1, 0, 0]
        result = dispatch(make_spec("classification_metrics",
                                     {"y_true": y_true, "y_pred": y_pred}))
        assert "accuracy" in result and "f1" in result

    def test_ml_train_ridge(self, rng):
        X = rng.normal(0, 1, (100, 5))
        y = X[:, 0] * 2
        result = dispatch(make_spec("ml_train", {"X": X, "y": y}, model_type="ridge"))
        assert "model_ref" in result

    def test_clustering_hierarchical(self, rng):
        X = np.vstack([rng.normal(0, 1, (20, 2)), rng.normal(5, 1, (20, 2))])
        result = dispatch(make_spec("clustering", X, method="hierarchical", n_clusters=2))
        assert "labels" in result

    def test_feature_importance_permutation(self, rng):
        X = rng.normal(0, 1, (100, 5))
        y = X[:, 0] * 2 + rng.normal(0, 0.1, 100)
        result = dispatch(make_spec("feature_importance", {"X": X, "y": y}, method="permutation"))
        assert "importance" in result.columns


# ── Tier 7 组合 (4 项) ──

class TestPortfolioHandlers:
    def test_risk_metrics(self, rng):
        returns = rng.normal(0.001, 0.02, 500)
        result = dispatch(make_spec("risk_metrics", returns, confidence=0.95))
        assert "var" in result and "sharpe" in result

    def test_regime_detection(self, rng):
        x = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 200)))
        result = dispatch(make_spec("regime_detection", x, method="change_point", n_regimes=2))
        assert "labels" in result

    def test_risk_metrics_has_drawdown(self, rng):
        returns = rng.normal(-0.001, 0.02, 500)
        result = dispatch(make_spec("risk_metrics", returns))
        assert result["max_drawdown"] <= 0

    def test_regime_detection_stats(self, rng):
        x = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 200)))
        result = dispatch(make_spec("regime_detection", x, n_regimes=3))
        assert "regime_stats" in result
