from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any

import pandas as pd


@dataclass
class SeriesSpec:
    name: str
    data: pd.Series
    kind: str = "line"
    color: Optional[str] = None
    secondary_y: bool = False


@dataclass
class MarkerSpec:
    ts: pd.Timestamp
    label: str
    direction: str = "up"


@dataclass
class PlotSpec:
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    series: list[SeriesSpec] = field(default_factory=list)
    markers: list[MarkerSpec] = field(default_factory=list)
    x_type: str = "datetime"

    def add_series(self, name: str, data: pd.Series, kind: str = "line",
                   color: Optional[str] = None, secondary_y: bool = False):
        self.series.append(SeriesSpec(name, data, kind, color, secondary_y))
        return self

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "x_type": self.x_type,
            "series": [
                {
                    "name": s.name,
                    "data": s.data.reset_index().values.tolist(),
                    "kind": s.kind,
                    "color": s.color,
                    "secondary_y": s.secondary_y,
                }
                for s in self.series
            ],
            "markers": [
                {"ts": str(m.ts), "label": m.label, "direction": m.direction}
                for m in self.markers
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
