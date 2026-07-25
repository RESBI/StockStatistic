"""test_demo_advanced.py — 高级分析演示测试（统计/信号/非线性/ML/组合）。

覆盖：Tier 2-7 全部 handler 类别。
图表输出：docs/images/stats_correlation.png / signal_spectral.png / signal_wavelet.png
         nonlinear_hurst.png / nonlinear_recurrence.png / ml_clustering.png / ml_pca.png
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec
from stockstat_compute.handlers import dispatch, ALL_TASK_TYPES

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(_ROOT, "docs", "images")


def make_spec(task_type, **params):
    return TaskSpec(
        task_id="demo-" + task_type,
        data_spec=DataSpec(symbols=[]),
        compute_spec=ComputeSpec(task_type=task_type, params=params),
    )


@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def signal_data():
    """合成信号：10Hz + 25Hz + 噪声。"""
    fs = 100
    t = np.arange(500) / fs
    return np.sin(2 * np.pi * 10 * t) + 0.5 * np.sin(2 * np.pi * 25 * t) + np.random.default_rng(42).normal(0, 0.3, 500)


class TestStatsHandlers:
    """Tier 2：经典统计检验。"""

    def test_correlation(self, rng):
        x = rng.normal(0, 1, 300)
        y = 0.6 * x + rng.normal(0, 0.8, 300)
        result = dispatch(make_spec("correlation", x=x.tolist(), y=y.tolist(), method="pearson"),
                          {"x": x, "y": y})
        assert "r" in result and "p_value" in result
        assert 0 < result["r"] < 1

    def test_hypothesis_test_chi2(self):
        result = dispatch(make_spec("hypothesis_test", test="chi2_independence",
                                     table=[[10, 20], [30, 40]]), None)
        assert "statistic" in result and "p_value" in result

    def test_bootstrap(self, rng):
        data = rng.normal(5, 2, 200)
        result = dispatch(make_spec("bootstrap", n_resamples=100), data)
        assert "ci_lower" in result and "ci_upper" in result

    def test_permutation_test(self, rng):
        x = rng.normal(0, 1, 50)
        y = rng.normal(0.5, 1, 50)
        result = dispatch(make_spec("permutation_test", n_permutations=50),
                          {"x": x, "y": y})
        assert "p_value" in result

    def test_survival_analysis(self):
        data = {"duration": list(range(1, 11)), "event": [1, 1, 0, 1, 1, 0, 1, 1, 0, 1]}
        result = dispatch(make_spec("survival_analysis"), data)
        assert "survival_curve" in result

    def test_ecdf(self, rng):
        data = rng.normal(0, 1, 100)
        result = dispatch(make_spec("ecdf"), data)
        assert "x" in result and "ecdf" in result

    def test_multiple_testing(self):
        result = dispatch(make_spec("multiple_testing", p_values=[0.001, 0.01, 0.04, 0.5],
                                     method="bh_fdr"), None)
        assert len(result) == 4

    def test_chow_test(self, rng):
        data = np.concatenate([rng.normal(0, 1, 50), rng.normal(1, 1, 50)])
        result = dispatch(make_spec("chow_test", breakpoint=50), data)
        assert "F_stat" in result


class TestSignalHandlers:
    """Tier 3：信号处理。"""

    def test_spectral_analysis(self, signal_data):
        result = dispatch(make_spec("spectral_analysis", method="welch", nperseg=128), signal_data)
        assert "frequencies" in result and "psd" in result

    def test_wavelet(self, signal_data):
        result = dispatch(make_spec("wavelet", method="cwt", scales=list(range(1, 25))), signal_data)
        assert "coefficients" in result and "power" in result

    def test_spectral_entropy(self, signal_data):
        result = dispatch(make_spec("spectral_entropy"), signal_data)
        assert "spectral_entropy" in result
        assert 0 <= result["spectral_entropy"] <= 1

    def test_cross_spectrum(self, rng):
        x = np.sin(np.linspace(0, 20, 500))
        y = np.sin(np.linspace(0, 20, 500) + 0.5)
        result = dispatch(make_spec("cross_spectrum"), {"x": x, "y": y})
        assert "coherence" in result

    def test_filter_design(self, rng, signal_data):
        result = dispatch(make_spec("filter_design", filter_type="butterworth", cutoff=0.1), signal_data)
        assert isinstance(result, list)


class TestNonlinearHandlers:
    """Tier 4：非线性动力学。"""

    def test_mutual_information(self, rng):
        x = rng.normal(0, 1, 200)
        y = x + rng.normal(0, 0.5, 200)
        result = dispatch(make_spec("mutual_information", estimator="binning"), {"x": x, "y": y})
        assert "mutual_information" in result

    def test_transfer_entropy(self, rng):
        x = rng.normal(0, 1, 100)
        y = np.roll(x, 1)
        result = dispatch(make_spec("transfer_entropy", n_permutations=20), {"x": x, "y": y})
        assert "te_forward" in result and "p_value" in result

    def test_hurst_dfa(self, rng):
        x = np.cumsum(rng.normal(0, 1, 2000))
        result = dispatch(make_spec("hurst_exponent", method="dfa"), x)
        assert "hurst" in result

    def test_hurst_white_noise(self, rng):
        x = rng.normal(0, 1, 2000)
        result = dispatch(make_spec("hurst_exponent", method="rs"), x)
        assert abs(result["hurst"] - 0.5) < 0.3

    def test_sample_entropy(self, rng):
        x = rng.normal(0, 1, 100)
        result = dispatch(make_spec("sample_entropy", m=2, r=0.2), x)
        assert "sample_entropy" in result

    def test_permutation_entropy(self, rng):
        x = rng.normal(0, 1, 100)
        result = dispatch(make_spec("permutation_entropy", m=4, tau=1), x)
        assert "permutation_entropy" in result

    def test_rqa(self):
        x = np.sin(np.linspace(0, 20, 200))
        result = dispatch(make_spec("rqa", m=3, tau=1), x)
        assert "RR" in result and "DET" in result

    def test_recurrence_plot(self):
        x = np.sin(np.linspace(0, 20, 200))
        result = dispatch(make_spec("recurrence_plot", m=3, tau=1), x)
        assert "recurrence_plot" in result


class TestGreyHandlers:
    """Tier 5：灰色系统。"""

    def test_grey_relation(self):
        data = {"reference": [1, 2, 3, 4, 5],
                "sequences": [[1, 2, 3, 4, 5], [5, 4, 3, 2, 1], [2, 3, 4, 5, 6]]}
        result = dispatch(make_spec("grey_relation", rho=0.5), data)
        assert "relation_degrees" in result
        assert len(result["relation_degrees"]) == 3

    def test_gm11_predict(self):
        x = [1, 2, 4, 8, 16, 32]
        result = dispatch(make_spec("gm11_predict", n_ahead=2), x)
        assert "predicted" in result and len(result["predicted"]) == 2

    def test_grey_cluster(self, rng):
        X = rng.normal(0, 1, (50, 3))
        result = dispatch(make_spec("grey_cluster", n_clusters=3), X)
        assert "labels" in result


class TestMLHandlers:
    """Tier 6：机器学习。"""

    def test_ml_train(self, rng):
        X = rng.normal(0, 1, (100, 5))
        y = X[:, 0] * 2 + rng.normal(0, 0.1, 100)
        result = dispatch(make_spec("ml_train", model_type="random_forest"), {"X": X, "y": y})
        assert "model_ref" in result and "cv_scores" in result

    def test_ml_predict(self, rng):
        from stockstat_foundation import cloudpickle_dumps
        from sklearn.ensemble import RandomForestRegressor
        X = rng.normal(0, 1, (50, 3))
        y = X[:, 0]
        model = RandomForestRegressor(n_estimators=10, random_state=42)
        model.fit(X, y)
        result = dispatch(make_spec("ml_predict", model_ref=f"cloudpickle:{cloudpickle_dumps(model)}"),
                          X[:5])
        assert "predictions" in result

    def test_feature_importance(self, rng):
        X = rng.normal(0, 1, (100, 5))
        y = X[:, 0] * 2 + rng.normal(0, 0.1, 100)
        result = dispatch(make_spec("feature_importance", method="gini"), {"X": X, "y": y})
        assert "importance" in result.columns

    def test_walkforward_cv(self, rng):
        X = rng.normal(0, 1, (200, 3))
        y = np.cumsum(rng.normal(0, 1, 200))
        result = dispatch(make_spec("walkforward_cv", n_folds=3), {"X": X, "y": y})
        assert "fold_scores" in result

    def test_clustering(self, rng):
        X = np.vstack([rng.normal(0, 1, (50, 2)), rng.normal(5, 1, (50, 2))])
        result = dispatch(make_spec("clustering", method="kmeans", n_clusters=2), X)
        assert "labels" in result and len(result["labels"]) == 100

    def test_dimension_reduction(self, rng):
        X = rng.normal(0, 1, (50, 5))
        result = dispatch(make_spec("dimension_reduction", method="pca", n_components=2), X)
        assert "transformed" in result and "explained_variance" in result

    def test_classification_metrics(self):
        result = dispatch(make_spec("classification_metrics"),
                          {"y_true": [0, 1, 0, 1], "y_pred": [0, 1, 1, 0]})
        assert "accuracy" in result and "f1" in result


class TestPortfolioHandlers:
    """Tier 7：组合风险。"""

    def test_risk_metrics(self, rng):
        returns = rng.normal(0.001, 0.02, 500)
        result = dispatch(make_spec("risk_metrics", confidence=0.95), returns)
        assert "var" in result and "sharpe" in result

    def test_regime_detection(self, rng):
        x = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 200)))
        result = dispatch(make_spec("regime_detection", method="change_point", n_regimes=2), x)
        assert "labels" in result


class TestHandlerRegistry:
    """handler 注册表完整性。"""

    def test_all_task_types_count(self):
        assert len(ALL_TASK_TYPES) >= 38

    def test_tier1_present(self):
        for t in ["indicator", "backtest", "grid_search", "batch_backtest", "monte_carlo", "walkforward"]:
            assert t in ALL_TASK_TYPES

    def test_tier2_present(self):
        for t in ["correlation", "hypothesis_test", "bootstrap", "permutation_test",
                   "chow_test", "survival_analysis", "ecdf", "multiple_testing"]:
            assert t in ALL_TASK_TYPES

    def test_tier3_present(self):
        for t in ["spectral_analysis", "wavelet", "spectral_entropy", "cross_spectrum", "filter_design"]:
            assert t in ALL_TASK_TYPES

    def test_tier4_present(self):
        for t in ["mutual_information", "transfer_entropy", "hurst_exponent",
                   "sample_entropy", "permutation_entropy", "rqa", "recurrence_plot"]:
            assert t in ALL_TASK_TYPES

    def test_tier5_present(self):
        for t in ["grey_relation", "gm11_predict", "grey_cluster"]:
            assert t in ALL_TASK_TYPES

    def test_tier6_present(self):
        for t in ["ml_train", "ml_predict", "feature_importance", "walkforward_cv",
                   "clustering", "dimension_reduction", "classification_metrics"]:
            assert t in ALL_TASK_TYPES

    def test_tier7_present(self):
        for t in ["risk_metrics", "regime_detection"]:
            assert t in ALL_TASK_TYPES


class TestPlotGeneration:
    """生成高级分析图表。"""

    def test_plot_correlation(self, rng):
        x = rng.normal(0, 1, 300)
        y = 0.6 * x + rng.normal(0, 0.8, 300)
        result = dispatch(make_spec("correlation", x=x.tolist(), y=y.tolist(), method="pearson"),
                          {"x": x, "y": y})
        fig, ax = plt.subplots(figsize=(7, 6))
        ax.scatter(x, y, alpha=0.5, s=20, color="steelblue")
        z = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 100)
        ax.plot(xs, np.polyval(z, xs), color="red", linewidth=2,
                label="r={:.3f} (p={:.4f})".format(result["r"], result["p_value"]))
        ax.set_title("Correlation Analysis (Pearson)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "stats_correlation.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "stats_correlation.png"))

    def test_plot_spectral(self, signal_data):
        result = dispatch(make_spec("spectral_analysis", method="welch", nperseg=128), signal_data)
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.semilogy(result["frequencies"], result["psd"], color="darkgreen", linewidth=1)
        ax.set_title("Spectral Analysis (Welch PSD)")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("PSD")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "signal_spectral.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "signal_spectral.png"))

    def test_plot_wavelet(self):
        t = np.arange(500) / 100
        signal = np.sin(2 * np.pi * 10 * t)
        signal[250:] = np.sin(2 * np.pi * 25 * t[250:])
        result = dispatch(make_spec("wavelet", method="cwt", scales=list(range(1, 40))), signal)
        power = np.array(result["power"])
        fig, ax = plt.subplots(figsize=(12, 5))
        im = ax.imshow(power, aspect="auto", cmap="viridis",
                       extent=[0, len(signal), 39, 1])
        ax.set_title("Wavelet CWT Scalogram")
        ax.set_xlabel("Time")
        ax.set_ylabel("Scale")
        fig.colorbar(im, ax=ax, label="Power")
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "signal_wavelet.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "signal_wavelet.png"))

    def test_plot_hurst(self, rng):
        x = np.cumsum(rng.normal(0, 1, 5000))
        result = dispatch(make_spec("hurst_exponent", method="dfa"), x)
        log_n = result["log_n"]
        log_f = result["log_F"]
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(log_n, log_f, color="steelblue", s=30)
        coeffs = np.polyfit(log_n, log_f, 1)
        xs = np.linspace(log_n[0], log_n[-1], 50)
        ax.plot(xs, np.polyval(coeffs, xs), color="red", linewidth=2,
                label="Hurst = {:.3f}".format(result["hurst"]))
        ax.set_title("Hurst Exponent (DFA)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "nonlinear_hurst.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "nonlinear_hurst.png"))

    def test_plot_recurrence(self):
        t = np.linspace(0, 20, 200)
        signal = np.sin(t) + 0.3 * np.sin(3 * t)
        result = dispatch(make_spec("recurrence_plot", m=3, tau=2), signal)
        R = np.array(result["recurrence_plot"])
        fig, ax = plt.subplots(figsize=(7, 6))
        ax.imshow(R, cmap="binary", origin="lower")
        ax.set_title("Recurrence Plot (m=3, tau=2)")
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "nonlinear_recurrence.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "nonlinear_recurrence.png"))

    def test_plot_clustering(self, rng):
        X = np.vstack([rng.normal(0, 1, (50, 2)), rng.normal(5, 1, (50, 2)), rng.normal(-3, 1, (50, 2))])
        result = dispatch(make_spec("clustering", method="kmeans", n_clusters=3), X)
        labels = np.array(result["labels"])
        fig, ax = plt.subplots(figsize=(7, 6))
        colors = ["#e41a1c", "#377eb8", "#4daf4a"]
        for k in range(3):
            mask = labels == k
            ax.scatter(X[mask, 0], X[mask, 1], c=colors[k], s=25, alpha=0.7, label="Cluster {}".format(k))
        ax.set_title("K-Means Clustering")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "ml_clustering.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "ml_clustering.png"))

    def test_plot_pca(self, rng):
        X = rng.normal(0, 1, (200, 5))
        X[:, 0] = X[:, 0] * 3 + 2
        result = dispatch(make_spec("dimension_reduction", method="pca", n_components=2), X)
        transformed = np.array(result["transformed"])
        ev = result["explained_variance"]
        fig, ax = plt.subplots(figsize=(7, 6))
        ax.scatter(transformed[:, 0], transformed[:, 1], c="steelblue", s=20, alpha=0.6)
        ax.set_title("PCA 2D Projection (PC1={:.1%}, PC2={:.1%})".format(ev[0], ev[1]))
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(IMG_DIR, "ml_pca.png"), dpi=120)
        plt.close(fig)
        assert os.path.exists(os.path.join(IMG_DIR, "ml_pca.png"))
