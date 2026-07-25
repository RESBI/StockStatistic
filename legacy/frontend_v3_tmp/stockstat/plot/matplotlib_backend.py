from __future__ import annotations

from typing import Optional, Any

import numpy as np
import pandas as pd

from .base import PlotRenderer, PlotSpec, SeriesSpec, SubplotSpec


class MatplotlibRenderer(PlotRenderer):
    """Renders PlotSpec via matplotlib (lazy import).

    Supports: line, bar, scatter, fill, histogram, heatmap, subplots,
    log scales.  Matplotlib is imported lazily on first ``render()``.
    """

    def __init__(self):
        self._fig = None
        self._axes = None

    def available(self) -> bool:
        try:
            import matplotlib  # noqa: F401
            return True
        except ImportError:
            return False

    def render(self, spec: PlotSpec) -> Any:
        import matplotlib.pyplot as plt

        if spec.subplots:
            return self._render_subplots(spec)
        return self._render_single(spec)

    # ── Single-axis mode (backward-compatible) ──

    def _render_single(self, spec: PlotSpec) -> Any:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=spec.figsize)
        self._fig = fig
        self._axes = ax
        ax2 = None

        for s in spec.series:
            if s.secondary_y and ax2 is None:
                ax2 = ax.twinx()
            target_ax = ax2 if s.secondary_y else ax
            self._render_series(target_ax, s)

        self._apply_axis_style(ax, spec.title or "", spec.x_label, spec.y_label,
                                spec.log_x, spec.log_y)

        handles, labels = ax.get_legend_handles_labels()
        if ax2 is not None:
            h2, l2 = ax2.get_legend_handles_labels()
            handles += h2
            labels += l2
        if handles:
            ax.legend(handles, labels)

        fig.tight_layout()
        return fig

    # ── Multi-subplot mode ──

    def _render_subplots(self, spec: PlotSpec) -> Any:
        import matplotlib.pyplot as plt

        n = max(spec.n_subplots, 1)
        rows, cols = spec.layout
        if rows * cols < n:
            rows = 1 if n == 1 else (n + 1) // 2
            cols = 1 if n == 1 else 2

        fig, axes = plt.subplots(rows, cols, figsize=spec.figsize, squeeze=False)
        self._fig = fig
        self._axes = axes
        flat = axes.flatten()

        for i in range(rows * cols):
            if i < n:
                self._render_subplot(flat[i], spec.subplots[i])
            else:
                flat[i].set_visible(False)

        if spec.title:
            fig.suptitle(spec.title, fontsize=14)
        fig.tight_layout(rect=(0, 0, 1, 0.96) if spec.title else (0, 0, 1, 1))
        return fig

    def _render_subplot(self, ax, sp: SubplotSpec):
        ax2 = None
        for s in sp.series:
            if s.secondary_y and ax2 is None:
                ax2 = ax.twinx()
            target = ax2 if s.secondary_y else ax
            self._render_series(target, s)

        self._apply_axis_style(ax, sp.title, sp.x_label, sp.y_label,
                                sp.log_x, sp.log_y)

        handles, labels = ax.get_legend_handles_labels()
        if ax2 is not None:
            h2, l2 = ax2.get_legend_handles_labels()
            handles += h2
            labels += l2
        if handles:
            ax.legend(handles, labels)

    # ── Series rendering ──

    def _render_series(self, ax, s: SeriesSpec):
        data = s.data
        color = s.color
        alpha = s.alpha
        label = s.name

        # Heatmap (2-D data)
        if s.kind == "heatmap":
            self._render_heatmap(ax, s, data)
            return

        # DataFrame fallback (treat as heatmap)
        if isinstance(data, pd.DataFrame):
            self._render_heatmap(ax, s, data)
            return

        # 1-D data
        if isinstance(data, pd.Series):
            data = data.dropna()

        if s.kind == "line":
            ax.plot(data.index, data.values, label=label, color=color,
                    alpha=alpha, linewidth=s.linewidth)
        elif s.kind == "bar":
            ax.bar(data.index, data.values, label=label, color=color, alpha=alpha)
        elif s.kind == "scatter":
            ax.scatter(data.index, data.values, label=label, color=color,
                       alpha=alpha, marker=s.marker or "o")
        elif s.kind == "fill":
            baseline = s.fill_to if s.fill_to is not None else 0.0
            ax.fill_between(data.index, data.values, baseline,
                            label=label, color=color, alpha=alpha)
        elif s.kind == "histogram":
            vals = data.values if isinstance(data, pd.Series) else np.asarray(data)
            ax.hist(vals, bins=s.bins, label=label, color=color, alpha=alpha)

    def _render_heatmap(self, ax, s: SeriesSpec, data):
        if isinstance(data, pd.DataFrame):
            arr = data.values
            xlabels = [str(c) for c in data.columns]
            ylabels = [str(i) for i in data.index]
        elif isinstance(data, np.ndarray):
            arr = data
            xlabels = ylabels = None
        else:
            arr = np.asarray(data)
            xlabels = ylabels = None

        im = ax.imshow(arr, aspect="auto", cmap=s.cmap or "RdYlGn",
                        origin="lower")
        if xlabels is not None:
            ax.set_xticks(range(len(xlabels)))
            ax.set_xticklabels(xlabels, fontsize=6)
        if ylabels is not None:
            ax.set_yticks(range(len(ylabels)))
            ax.set_yticklabels(ylabels, fontsize=6)
        if s.name:
            ax.set_title(s.name)
        self._fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    # ── Axis styling ──

    @staticmethod
    def _apply_axis_style(ax, title, x_label, y_label, log_x, log_y):
        if title:
            ax.set_title(title)
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)
        if log_x:
            ax.set_xscale("log")
        if log_y:
            ax.set_yscale("log")

    def show(self) -> None:
        import matplotlib.pyplot as plt
        if self._fig is not None:
            plt.show()

    def savefig(self, path: str) -> None:
        if self._fig is not None:
            self._fig.savefig(path, dpi=150, bbox_inches="tight")
