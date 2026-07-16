from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

import pandas as pd


@dataclass
class ChartSeries:
    """A single series within a subplot.

    `kind` may be: line, bar, scatter, fill, histogram, heatmap.
    - `fill`: a line series whose area between data and `fill_to` is shaded.
    - `histogram`: `data` is a 1-D Series of raw values to bin.
    - `heatmap`: `data` is a 2-D DataFrame; rows=y, cols=x.
    """
    name: str
    data: Union[pd.Series, pd.DataFrame]
    kind: str = "line"
    color: Optional[str] = None
    secondary_y: bool = False
    alpha: float = 1.0
    fill_to: Optional[float] = None  # for fill kind: y baseline (e.g. 0.0)
    bins: int = 50                   # for histogram kind
    cmap: Optional[str] = None       # for heatmap kind
    marker: Optional[str] = None     # for scatter kind
    linewidth: float = 1.5


@dataclass
class SubplotSpec:
    title: str = ""
    y_label: str = ""
    x_label: str = ""
    series: list[ChartSeries] = field(default_factory=list)
    share_x: bool = True
    log_y: bool = False

    def add_series(self, **kwargs) -> "ChartSeries":
        s = ChartSeries(**kwargs)
        self.series.append(s)
        return s


@dataclass
class BacktestChartSpec:
    """Backtest-dedicated chart spec supporting subplots, fill, heatmap, histogram.

    This is parallel to (and richer than) the generic `plot.base.PlotSpec`.
    Backtest core never imports matplotlib; a `BacktestChartRenderer` interprets it.
    """
    title: str = ""
    x_label: str = ""
    subplots: list[SubplotSpec] = field(default_factory=list)
    layout: tuple[int, int] = (1, 1)
    figsize: tuple[float, float] = (12.0, 6.0)
    annotate_trades: bool = False
    source_result: object = None
    chart_type: str = "custom"

    def add_subplot(self, title: str = "", y_label: str = "",
                    x_label: str = "", share_x: bool = True,
                    log_y: bool = False) -> SubplotSpec:
        sp = SubplotSpec(title=title, y_label=y_label, x_label=x_label,
                         share_x=share_x, log_y=log_y)
        self.subplots.append(sp)
        return sp

    @property
    def n_subplots(self) -> int:
        return len(self.subplots)

    def to_dict(self) -> dict:
        """JSON-serializable representation (for web frontends)."""
        return {
            "title": self.title,
            "x_label": self.x_label,
            "chart_type": self.chart_type,
            "layout": list(self.layout),
            "figsize": list(self.figsize),
            "annotate_trades": self.annotate_trades,
            "subplots": [
                {
                    "title": sp.title,
                    "y_label": sp.y_label,
                    "x_label": sp.x_label,
                    "share_x": sp.share_x,
                    "log_y": sp.log_y,
                    "series": [
                        {
                            "name": s.name,
                            "kind": s.kind,
                            "color": s.color,
                            "secondary_y": s.secondary_y,
                            "alpha": s.alpha,
                            "fill_to": s.fill_to,
                            "bins": s.bins,
                            "cmap": s.cmap,
                            "marker": s.marker,
                            "linewidth": s.linewidth,
                            "data": _series_to_list(s.data),
                        }
                        for s in sp.series
                    ],
                }
                for sp in self.subplots
            ],
        }


def _series_to_list(data) -> list:
    if isinstance(data, pd.DataFrame):
        return data.reset_index().values.tolist()
    if isinstance(data, pd.Series):
        return [[str(t), v] if not isinstance(v, float) else [str(t), v]
                for t, v in data.items()]
    return list(data) if data is not None else []
