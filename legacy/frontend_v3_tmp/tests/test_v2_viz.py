"""Tests for v2.0 visualization layer (Layer 2)."""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest


class TestUnifiedSpec:

    def test_plot_spec_creation(self):
        from stockstat._viz.specs import PlotSpec, SeriesSpec
        spec = PlotSpec(title="Test", x_label="X", y_label="Y")
        spec.add_series(name="line1", data=pd.Series([1, 2, 3]), kind="line")
        assert len(spec.series) == 1
        assert spec.series[0].name == "line1"
        assert spec.n_subplots == 0

    def test_plot_spec_subplots(self):
        from stockstat._viz.specs import PlotSpec
        spec = PlotSpec(title="Dashboard", layout=(2, 2))
        sp1 = spec.add_subplot(title="Panel 1")
        sp1.add_series(name="a", data=pd.Series([1, 2]), kind="line")
        sp2 = spec.add_subplot(title="Panel 2")
        assert spec.n_subplots == 2
        assert len(sp1.series) == 1

    def test_plot_spec_to_dict(self):
        from stockstat._viz.specs import PlotSpec
        spec = PlotSpec(title="Test")
        spec.add_series(name="x", data=pd.Series([1, 2]), kind="line")
        d = spec.to_dict()
        assert d["title"] == "Test"
        assert len(d["series"]) == 1
        assert d["series"][0]["name"] == "x"

    def test_series_spec_kinds(self):
        from stockstat._viz.specs import SeriesSpec
        for kind in ["line", "bar", "scatter", "fill", "histogram", "heatmap"]:
            s = SeriesSpec(name="test", data=[1, 2], kind=kind)
            assert s.kind == kind

    def test_marker_spec(self):
        from stockstat._viz.specs import MarkerSpec
        m = MarkerSpec(ts=pd.Timestamp("2024-01-01"), label="BUY", direction="up")
        assert m.direction == "up"


class TestChartProfiles:

    def _make_fake_result(self):
        """Create a minimal result-like object for profile testing."""
        class FakeResult:
            def __init__(self):
                self.equity = pd.Series(
                    [10000, 10100, 10050, 10200, 10100],
                    index=pd.date_range("2024-01-01", periods=5, freq="D"),
                )
                self.fills = []
                class Fill:
                    class Side:
                        def __init__(self, v): self.value = v
                    def __init__(self, ts, side, qty, price):
                        self.ts = ts
                        self.side = self.Side(side)
                        self.qty = qty
                        self.price = price
                self.fills.append(Fill(pd.Timestamp("2024-01-02"), "buy", 0.1, 100))

        return FakeResult()

    def test_list_profiles(self):
        from stockstat._viz.specs import list_profiles
        profiles = list_profiles()
        assert "equity_curve" in profiles
        assert "drawdown" in profiles
        assert "dashboard" in profiles

    def test_equity_curve_profile(self):
        from stockstat._viz.specs import get_profile
        result = self._make_fake_result()
        profile = get_profile("equity_curve")
        assert profile is not None
        spec = profile.build(result)
        assert spec.title == "Equity Curve"
        assert len(spec.series) >= 1

    def test_drawdown_profile(self):
        from stockstat._viz.specs import get_profile
        result = self._make_fake_result()
        profile = get_profile("drawdown")
        spec = profile.build(result)
        assert spec.title == "Drawdown"
        assert spec.series[0].kind == "fill"

    def test_trades_profile(self):
        from stockstat._viz.specs import get_profile
        result = self._make_fake_result()
        profile = get_profile("trades_overlay")
        spec = profile.build(result)
        assert len(spec.markers) == 1
        assert spec.markers[0].direction == "up"

    def test_returns_distribution_profile(self):
        from stockstat._viz.specs import get_profile
        result = self._make_fake_result()
        profile = get_profile("returns_distribution")
        spec = profile.build(result)
        assert spec.series[0].kind == "histogram"

    def test_monthly_heatmap_profile(self):
        from stockstat._viz.specs import get_profile
        result = self._make_fake_result()
        profile = get_profile("monthly_heatmap")
        spec = profile.build(result)
        assert spec.series[0].kind == "heatmap"

    def test_dashboard_profile(self):
        from stockstat._viz.specs import get_profile
        result = self._make_fake_result()
        profile = get_profile("dashboard")
        spec = profile.build(result)
        assert spec.n_subplots == 4
        assert spec.layout == (2, 2)

    def test_profile_without_builder_raises(self):
        from stockstat._viz.specs import ChartProfile
        p = ChartProfile("empty", "")
        with pytest.raises(ValueError):
            p.build(None)


class TestRendererPlugins:

    def test_register_default_renderers(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._viz.renderers import register_default_renderers

        reg = PluginRegistry()
        count = register_default_renderers(reg)
        assert count >= 1  # at least null
        assert reg.get("renderers", "null") is not None

    def test_get_renderer_auto(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._viz.renderers import register_default_renderers, get_renderer

        reg = PluginRegistry()
        register_default_renderers(reg)
        r = get_renderer(reg)
        assert r is not None
        assert r.available() in (True, False)  # null returns False, mpl returns True

    def test_get_renderer_by_name(self):
        from stockstat._core.plugin import PluginRegistry
        from stockstat._viz.renderers import register_default_renderers, get_renderer

        reg = PluginRegistry()
        register_default_renderers(reg)
        r = get_renderer(reg, "null")
        assert r is not None
        assert r.available() is False


class TestThemes:

    def test_default_theme(self):
        from stockstat._viz.themes import get_theme
        t = get_theme("default")
        assert t.name == "default"
        assert t.background == "white"

    def test_dark_theme(self):
        from stockstat._viz.themes import get_theme
        t = get_theme("dark")
        assert t.background == "#1e1e1e"

    def test_publication_theme(self):
        from stockstat._viz.themes import get_theme
        t = get_theme("publication")
        assert t.font_size == 10

    def test_list_themes(self):
        from stockstat._viz.themes import list_themes
        names = list_themes()
        assert "default" in names
        assert "dark" in names
        assert "publication" in names

    def test_register_custom_theme(self):
        from stockstat._viz.themes import Theme, register_theme, get_theme
        custom = Theme("custom", background="black", primary="cyan")
        register_theme(custom)
        t = get_theme("custom")
        assert t.primary == "cyan"

    def test_unknown_theme_falls_back(self):
        from stockstat._viz.themes import get_theme
        t = get_theme("nonexistent")
        assert t.name == "default"

    def test_theme_to_dict(self):
        from stockstat._viz.themes import get_theme
        t = get_theme("default")
        d = t.to_dict()
        assert "name" in d
        assert "primary" in d
