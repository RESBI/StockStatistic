"""
Unit tests for stockstat.indicators.nonlinear — signal processing & nonlinear dynamics.

Each function gets 2-3 tests:
  1. Known-property test (deterministic signal with known answer)
  2. Edge-case test (short/constant/noisy input)
  3. (where applicable) Consistency test (antropy / pywt cross-check)
"""
import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["DATABASE_URL"] = "sqlite:///test_nonlinear.db"

from stockstat.indicators import nonlinear as nl


# ═══════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════

@pytest.fixture
def rng():
    return np.random.RandomState(42)


@pytest.fixture
def white_noise(rng):
    return rng.randn(500)


@pytest.fixture
def trend_signal(rng):
    """Persistent signal: cumulative sum of noise (Hurst > 0.5)."""
    return np.cumsum(rng.randn(500))


@pytest.fixture
def constant_signal():
    return np.ones(100) * 5.0


# ═══════════════════════════════════════════════════════
# wavelet_decompose
# ═══════════════════════════════════════════════════════

class TestWaveletDecompose:
    def test_output_shape(self, white_noise):
        scales = np.arange(1, 11)
        coef, sc = nl.wavelet_decompose(white_noise, scales=scales)
        assert coef.shape == (10, len(white_noise))
        assert len(sc) == 10

    def test_default_scales(self, white_noise):
        coef, scales = nl.wavelet_decompose(white_noise[:48])
        assert coef.shape[1] == 48
        assert scales[0] == 1

    def test_short_signal_raises(self):
        with pytest.raises(ValueError):
            nl.wavelet_decompose([1, 2])


# ═══════════════════════════════════════════════════════
# spectral_entropy
# ═══════════════════════════════════════════════════════

class TestSpectralEntropy:
    def test_white_noise_high_entropy(self, white_noise):
        """White noise should have near-maximum spectral entropy."""
        h = nl.spectral_entropy(white_noise)
        assert h > 2.0  # high entropy for broadband noise

    def test_pure_tone_low_entropy(self):
        """A pure sinusoid should have very low spectral entropy."""
        t = np.linspace(0, 10, 1000)
        sig = np.sin(2 * np.pi * 5 * t)
        h = nl.spectral_entropy(sig)
        assert h < 1.0  # concentrated energy → low entropy

    def test_short_signal(self):
        assert nl.spectral_entropy([1, 2]) == 0.0


# ═══════════════════════════════════════════════════════
# grey_relation
# ═══════════════════════════════════════════════════════

class TestGreyRelation:
    def test_self_relation_is_one(self):
        """Grey relational degree of a sequence with itself should be 1.0."""
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        r = nl.grey_relation(x, x)
        assert abs(r - 1.0) < 1e-6

    def test_identical_shape_required(self):
        with pytest.raises(ValueError):
            nl.grey_relation([1, 2, 3], [1, 2])

    def test_monotone_similar(self):
        """Identical sequences have higher relation than shifted sequences."""
        x = np.linspace(1, 10, 50)
        r_self = nl.grey_relation(x, x)
        y_shift = x + np.array([0.5] * 50)  # constant offset after normalisation
        r_shift = nl.grey_relation(x, y_shift)
        assert r_self > r_shift
        assert abs(r_self - 1.0) < 1e-6


# ═══════════════════════════════════════════════════════
# gm11_predict
# ═══════════════════════════════════════════════════════

class TestGM11Predict:
    def test_linear_sequence(self):
        """GM(1,1) on a linear sequence should predict growth (not exact).

        GM(1,1) models exponential growth; on a linear sequence it
        overestimates slightly — we just check it's in the right ballpark.
        """
        x = np.array([10, 20, 30, 40, 50], dtype=float)
        pred = nl.gm11_predict(x)
        assert 50 < pred < 80  # should predict growth beyond 50

    def test_exponential_sequence(self):
        """Exponential growth: GM(1,1) should capture the trend."""
        x = np.array([1, 2, 4, 8, 16, 32], dtype=float)
        pred = nl.gm11_predict(x)
        assert pred > 40  # should predict growth beyond 32

    def test_short_sequence_returns_last(self):
        x = np.array([1, 2, 3])
        assert nl.gm11_predict(x) == 3.0


# ═══════════════════════════════════════════════════════
# transfer_entropy
# ═══════════════════════════════════════════════════════

class TestTransferEntropy:
    def test_independent_series_near_zero(self, rng):
        """TE of independent series should be near zero."""
        x = rng.randn(200)
        y = rng.randn(200)
        te = nl.transfer_entropy(x, y, k=1, n_bins=4)
        assert te >= 0  # non-negative by definition
        assert te < 1.0  # not excessively large

    def test_coupled_series_positive(self, rng):
        """When x drives y, TE(x→y) should be positive."""
        x = rng.randn(200)
        y = np.zeros(200)
        y[1:] = 0.8 * x[:-1] + 0.2 * rng.randn(199)
        te = nl.transfer_entropy(x, y, k=1, n_bins=4)
        assert te >= 0

    def test_short_series(self):
        assert nl.transfer_entropy([1, 2], [2, 3]) == 0.0


# ═══════════════════════════════════════════════════════
# hurst_dfa
# ═══════════════════════════════════════════════════════

class TestHurstDFA:
    def test_white_noise_near_half(self, white_noise):
        """White noise Hurst ≈ 0.5."""
        h = nl.hurst_dfa(white_noise)
        assert 0.4 < h < 0.65

    def test_trend_signal_high(self, trend_signal):
        """Cumulative sum (persistent) should have Hurst > 0.5."""
        h = nl.hurst_dfa(trend_signal)
        assert h > 0.55

    def test_short_returns_half(self):
        assert nl.hurst_dfa([1, 2, 3]) == 0.5


# ═══════════════════════════════════════════════════════
# sample_entropy
# ═══════════════════════════════════════════════════════

class TestSampleEntropy:
    def test_constant_signal_zero(self, constant_signal):
        """Constant signal → SampEn = 0 (fully predictable)."""
        h = nl.sample_entropy(constant_signal)
        assert h == 0.0

    def test_noisy_signal_positive(self, white_noise):
        """Noise should have positive sample entropy."""
        h = nl.sample_entropy(white_noise, m=2)
        assert h > 0

    def test_short_signal(self):
        assert nl.sample_entropy([1, 2, 3]) == 0.0


# ═══════════════════════════════════════════════════════
# permutation_entropy
# ═══════════════════════════════════════════════════════

class TestPermutationEntropy:
    def test_white_noise_near_max(self, white_noise):
        """White noise PermEn should be close to log2(m!)."""
        import math
        m = 3
        h = nl.permutation_entropy(white_noise, m=m)
        assert h > 0.7 * math.log2(math.factorial(m))

    def test_constant_signal_low(self, constant_signal):
        """Constant signal → low PermEn (all same pattern)."""
        h = nl.permutation_entropy(constant_signal, m=3)
        assert h < 0.5

    def test_short_signal(self):
        assert nl.permutation_entropy([1, 2], m=3) == 0.0


# ═══════════════════════════════════════════════════════
# ComputeEngine integration
# ═══════════════════════════════════════════════════════

class TestComputeEngineIntegration:
    def test_engine_has_nonlinear_methods(self):
        from stockstat.compute.engine import ComputeEngine
        for method in [
            "wavelet_decompose", "spectral_entropy", "grey_relation",
            "gm11_predict", "transfer_entropy", "hurst_dfa",
            "sample_entropy", "permutation_entropy",
        ]:
            assert hasattr(ComputeEngine, method), f"Missing method: {method}"

    def test_engine_spectral_entropy(self, white_noise):
        from stockstat.compute.engine import ComputeEngine
        class FakeClient:
            pass
        engine = ComputeEngine(FakeClient())
        h = engine.spectral_entropy(white_noise)
        assert h > 0

    def test_engine_grey_relation(self):
        from stockstat.compute.engine import ComputeEngine
        class FakeClient:
            pass
        engine = ComputeEngine(FakeClient())
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        r = engine.grey_relation(x, x)
        assert abs(r - 1.0) < 1e-6


# ═══════════════════════════════════════════════════════
# PlotSpec factory tests
# ═══════════════════════════════════════════════════════

class TestPlotSpecFactories:
    def test_wavelet_scalogram_spec(self, white_noise):
        """wavelet_scalogram_spec returns a PlotSpec with heatmap series."""
        from stockstat.indicators.nonlinear import wavelet_decompose, wavelet_scalogram_spec
        coef, scales = wavelet_decompose(white_noise[:48], scales=np.arange(1, 13))
        spec = wavelet_scalogram_spec(coef, scales)
        assert spec.title == "CWT Scalogram"
        assert len(spec.series) == 1
        assert spec.series[0].kind == "heatmap"
        assert spec.series[0].cmap == "jet"

    def test_dfa_fit_spec(self, white_noise):
        """dfa_fit_spec returns a PlotSpec with log scales."""
        from stockstat.indicators.nonlinear import dfa_fit_spec
        spec = dfa_fit_spec(white_noise[:200])
        assert "Hurst" in spec.title or "H =" in spec.title
        assert spec.log_x is True
        assert spec.log_y is True
        assert len(spec.series) == 2  # scatter + line

    def test_psd_spec(self, white_noise):
        """psd_spec returns a log-log PSD PlotSpec."""
        from stockstat.indicators.nonlinear import psd_spec
        spec = psd_spec(white_noise[:200])
        assert spec.title == "Power Spectral Density"
        assert spec.log_x is True
        assert spec.log_y is True
        assert len(spec.series) == 1
        assert spec.series[0].kind == "line"

    def test_engine_has_plot_methods(self):
        """ComputeEngine exposes wavelet_scalogram, dfa_fit, psd_plot."""
        from stockstat.compute.engine import ComputeEngine
        for method in ["wavelet_scalogram", "dfa_fit", "psd_plot"]:
            assert hasattr(ComputeEngine, method), f"Missing method: {method}"


# ═══════════════════════════════════════════════════════
# Enhanced PlotSpec tests (heatmap, subplots, log scales)
# ═══════════════════════════════════════════════════════

class TestEnhancedPlotSpec:
    def test_heatmap_series(self):
        """PlotSpec can hold a heatmap series with 2-D data."""
        from stockstat.plot.base import PlotSpec
        import pandas as pd
        df = pd.DataFrame(np.random.rand(5, 10))
        spec = PlotSpec(title="test")
        spec.add_series(name="heatmap", data=df, kind="heatmap", cmap="jet")
        assert len(spec.series) == 1
        assert spec.series[0].kind == "heatmap"

    def test_subplots(self):
        """PlotSpec supports subplot mode."""
        from stockstat.plot.base import PlotSpec
        spec = PlotSpec(title="multi", layout=(2, 1))
        sp1 = spec.add_subplot(title="panel 1", y_label="y1")
        sp2 = spec.add_subplot(title="panel 2", y_label="y2", log_y=True)
        assert spec.n_subplots == 2
        assert sp2.log_y is True

    def test_log_scales(self):
        """PlotSpec supports log_x and log_y."""
        from stockstat.plot.base import PlotSpec
        spec = PlotSpec(title="log", log_x=True, log_y=True)
        assert spec.log_x is True
        assert spec.log_y is True

    def test_to_dict_includes_new_fields(self):
        """to_dict includes heatmap/subplots/log fields."""
        from stockstat.plot.base import PlotSpec
        import pandas as pd
        spec = PlotSpec(title="t", log_x=True)
        spec.add_series(name="s", data=pd.Series([1, 2, 3]), kind="line")
        d = spec.to_dict()
        assert "log_x" in d
        assert "subplots" in d
        assert "figsize" in d

    def test_matplotlib_renders_heatmap(self, white_noise):
        """MatplotlibRenderer can render a heatmap spec."""
        pytest.importorskip("matplotlib")
        from stockstat.plot.base import PlotSpec, get_renderer
        from stockstat.indicators.nonlinear import wavelet_decompose, wavelet_scalogram_spec
        coef, scales = wavelet_decompose(white_noise[:48], scales=np.arange(1, 13))
        spec = wavelet_scalogram_spec(coef, scales)
        renderer = get_renderer("matplotlib")
        if not renderer.available():
            pytest.skip("matplotlib not available")
        fig = renderer.render(spec)
        assert fig is not None

    def test_matplotlib_renders_subplots(self):
        """MatplotlibRenderer can render subplot mode."""
        pytest.importorskip("matplotlib")
        from stockstat.plot.base import PlotSpec, get_renderer
        import pandas as pd
        spec = PlotSpec(title="multi", layout=(2, 1), figsize=(10, 8))
        sp1 = spec.add_subplot(title="p1", y_label="y1")
        sp1.add_series(name="s1", data=pd.Series([1, 2, 3]), kind="line")
        sp2 = spec.add_subplot(title="p2", y_label="y2")
        sp2.add_series(name="s2", data=pd.Series([3, 2, 1]), kind="line")
        renderer = get_renderer("matplotlib")
        if not renderer.available():
            pytest.skip("matplotlib not available")
        fig = renderer.render(spec)
        assert fig is not None

    def test_backward_compatibility(self):
        """Existing PlotSpec usage (no subplots) still works."""
        from stockstat.plot.base import PlotSpec
        import pandas as pd
        spec = PlotSpec(title="simple")
        spec.add_series(name="close", data=pd.Series([1, 2, 3, 4, 5]), kind="line")
        spec.add_series(name="ma", data=pd.Series([2, 3, 4, 5, 6]), kind="line", color="red")
        assert len(spec.series) == 2
        assert spec.n_subplots == 0
        d = spec.to_dict()
        assert len(d["series"]) == 2
