from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any, Union

import pandas as pd
import numpy as np


@dataclass
class SeriesSpec:
    name: str
    data: Union[pd.Series, pd.DataFrame, np.ndarray]
    kind: str = "line"
    color: Optional[str] = None
    secondary_y: bool = False
    alpha: float = 1.0
    fill_to: Optional[float] = None
    bins: int = 50
    cmap: Optional[str] = None
    marker: Optional[str] = None
    linewidth: float = 1.5


@dataclass
class MarkerSpec:
    ts: pd.Timestamp
    label: str
    direction: str = "up"


@dataclass
class SubplotSpec:
    """A subplot within a multi-panel PlotSpec.

    When ``PlotSpec.subplots`` is non-empty, the renderer creates a
    multi-panel layout; otherwise it renders a single axis from the
    top-level ``series`` list (backward-compatible).
    """
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    series: list[SeriesSpec] = field(default_factory=list)
    log_x: bool = False
    log_y: bool = False
    share_x: bool = True

    def add_series(self, name: str, data=None, kind: str = "line",
                   color: Optional[str] = None, secondary_y: bool = False,
                   alpha: float = 1.0, fill_to: Optional[float] = None,
                   bins: int = 50, cmap: Optional[str] = None,
                   marker: Optional[str] = None, linewidth: float = 1.5):
        s = SeriesSpec(name=name, data=data, kind=kind, color=color,
                       secondary_y=secondary_y, alpha=alpha, fill_to=fill_to,
                       bins=bins, cmap=cmap, marker=marker, linewidth=linewidth)
        self.series.append(s)
        return s


@dataclass
class PlotSpec:
    """Backend-agnostic plot specification.

    Supports two modes:
    1. **Simple mode** (backward-compatible): populate ``series`` directly.
    2. **Subplot mode**: populate ``subplots`` for multi-panel layouts.

    Supported ``kind`` values: ``line``, ``bar``, ``scatter``, ``fill``,
    ``histogram``, ``heatmap``.

    For ``heatmap``, ``data`` should be a 2-D array or DataFrame;
    ``cmap`` controls the colour map.
    """
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    series: list[SeriesSpec] = field(default_factory=list)
    markers: list[MarkerSpec] = field(default_factory=list)
    x_type: str = "datetime"
    # ── New fields (v1.7) ──
    subplots: list[SubplotSpec] = field(default_factory=list)
    layout: tuple[int, int] = (1, 1)
    figsize: tuple[float, float] = (12.0, 6.0)
    log_x: bool = False
    log_y: bool = False

    def add_series(self, name: str, data=None, kind: str = "line",
                   color: Optional[str] = None, secondary_y: bool = False,
                   alpha: float = 1.0, fill_to: Optional[float] = None,
                   bins: int = 50, cmap: Optional[str] = None,
                   marker: Optional[str] = None, linewidth: float = 1.5):
        s = SeriesSpec(name=name, data=data, kind=kind, color=color,
                       secondary_y=secondary_y, alpha=alpha, fill_to=fill_to,
                       bins=bins, cmap=cmap, marker=marker, linewidth=linewidth)
        self.series.append(s)
        return self

    def add_subplot(self, title: str = "", x_label: str = "",
                    y_label: str = "", log_x: bool = False,
                    log_y: bool = False, share_x: bool = True) -> SubplotSpec:
        sp = SubplotSpec(title=title, x_label=x_label, y_label=y_label,
                         log_x=log_x, log_y=log_y, share_x=share_x)
        self.subplots.append(sp)
        return sp

    @property
    def n_subplots(self) -> int:
        return len(self.subplots)

    def to_dict(self) -> dict:
        def _series_to_list(data):
            if isinstance(data, pd.DataFrame):
                return data.reset_index().values.tolist()
            if isinstance(data, pd.Series):
                return [[str(t), v] if not isinstance(v, float) else [str(t), v]
                        for t, v in data.items()]
            if isinstance(data, np.ndarray):
                return data.tolist()
            return list(data) if data is not None else []

        return {
            "title": self.title,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "x_type": self.x_type,
            "layout": list(self.layout),
            "figsize": list(self.figsize),
            "log_x": self.log_x,
            "log_y": self.log_y,
            "series": [
                {
                    "name": s.name,
                    "data": _series_to_list(s.data),
                    "kind": s.kind,
                    "color": s.color,
                    "secondary_y": s.secondary_y,
                    "alpha": s.alpha,
                    "fill_to": s.fill_to,
                    "bins": s.bins,
                    "cmap": s.cmap,
                    "marker": s.marker,
                    "linewidth": s.linewidth,
                }
                for s in self.series
            ],
            "markers": [
                {"ts": str(m.ts), "label": m.label, "direction": m.direction}
                for m in self.markers
            ],
            "subplots": [
                {
                    "title": sp.title,
                    "x_label": sp.x_label,
                    "y_label": sp.y_label,
                    "log_x": sp.log_x,
                    "log_y": sp.log_y,
                    "share_x": sp.share_x,
                    "series": [
                        {
                            "name": s.name,
                            "data": _series_to_list(s.data),
                            "kind": s.kind,
                            "color": s.color,
                            "secondary_y": s.secondary_y,
                            "alpha": s.alpha,
                            "fill_to": s.fill_to,
                            "bins": s.bins,
                            "cmap": s.cmap,
                            "marker": s.marker,
                            "linewidth": s.linewidth,
                        }
                        for s in sp.series
                    ],
                }
                for sp in self.subplots
            ],
        }


class PlotRenderer:
    def render(self, spec: PlotSpec) -> Any:
        raise NotImplementedError

    def show(self) -> None:
        raise NotImplementedError

    def savefig(self, path: str) -> None:
        raise NotImplementedError

    def available(self) -> bool:
        return False


class NullRenderer(PlotRenderer):
    def render(self, spec: PlotSpec) -> None:
        import warnings
        warnings.warn(
            "No plotting backend available. Install matplotlib via "
            "`pip install stockstat[matplotlib]` to enable plotting.",
            UserWarning,
            stacklevel=2,
        )
        return None

    def show(self) -> None:
        pass

    def savefig(self, path: str) -> None:
        import warnings
        warnings.warn("No plotting backend available for savefig.", UserWarning)

    def available(self) -> bool:
        return False


class RendererFactory:
    @staticmethod
    def detect() -> str:
        for name in ["matplotlib", "plotly"]:
            try:
                __import__(name)
                return name
            except ImportError:
                continue
        return "null"

    @staticmethod
    def get_renderer(name: Optional[str] = None) -> PlotRenderer:
        if name is None:
            name = RendererFactory.detect()
        if name == "matplotlib":
            from .matplotlib_backend import MatplotlibRenderer
            return MatplotlibRenderer()
        if name == "plotly":
            try:
                from .plotly_backend import PlotlyRenderer
                return PlotlyRenderer()
            except ImportError:
                return NullRenderer()
        return NullRenderer()


def get_renderer(name: Optional[str] = None) -> PlotRenderer:
    return RendererFactory.get_renderer(name)
