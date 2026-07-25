from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from .chart_spec import BacktestChartSpec, ChartSeries, SubplotSpec


class MatplotlibBacktestChartRenderer:
    """Renders BacktestChartSpec via matplotlib (lazy import).

    Supports: line, bar, scatter, fill, histogram, heatmap, and multi-subplot
    layouts. Trade annotations are drawn when `spec.annotate_trades` is True.
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

    def render(self, spec: BacktestChartSpec) -> Any:
        import matplotlib.pyplot as plt

        n = max(spec.n_subplots, 1)
        rows, cols = spec.layout
        if rows * cols < n:
            # auto-fit layout
            rows = 1 if n == 1 else (n + 1) // 2
            cols = 1 if n == 1 else 2

        fig, axes = plt.subplots(rows, cols, figsize=spec.figsize, squeeze=False)
        self._fig = fig
        self._axes = axes

        flat_axes = axes.flatten()
        for i in range(rows * cols):
            if i < n:
                self._render_subplot(flat_axes[i], spec, i)
            else:
                flat_axes[i].set_visible(False)

        if spec.title:
            fig.suptitle(spec.title, fontsize=14)

        if spec.annotate_trades and spec.source_result is not None:
            # annotate trades on the first subplot
            self._annotate_trades(flat_axes[0], spec.source_result)

        fig.tight_layout(rect=(0, 0, 1, 0.96) if spec.title else (0, 0, 1, 1))
        return fig

    def _render_subplot(self, ax, spec: BacktestChartSpec, idx: int):
        if idx >= len(spec.subplots):
            return
        sp: SubplotSpec = spec.subplots[idx]
        ax2 = None

        for s in sp.series:
            if s.secondary_y and ax2 is None:
                ax2 = ax.twinx()

            target = ax2 if s.secondary_y else ax
            data = s.data
            if isinstance(data, pd.DataFrame):
                self._render_dataframe(target, s, data)
                continue

            data = data.dropna() if isinstance(data, pd.Series) else data
            self._render_series(target, s, data)

        if sp.title:
            ax.set_title(sp.title)
        if sp.y_label:
            ax.set_ylabel(sp.y_label)
        if sp.x_label:
            ax.set_xlabel(sp.x_label)
        if sp.log_y:
            ax.set_yscale("log")

        # legend
        handles, labels = ax.get_legend_handles_labels()
        if ax2 is not None:
            h2, l2 = ax2.get_legend_handles_labels()
            handles += h2
            labels += l2
        if handles:
            ax.legend(handles, labels, loc="best")

    def _render_series(self, ax, s: ChartSeries, data):
        color = s.color
        alpha = s.alpha
        label = s.name

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
            ax.hist(data.values, bins=s.bins, label=label, color=color, alpha=alpha)

    def _render_dataframe(self, ax, s: ChartSeries, df: pd.DataFrame):
        if s.kind == "heatmap":
            import matplotlib.pyplot as plt
            # rows = index, cols = columns
            arr = df.values
            im = ax.imshow(arr, aspect="auto", cmap=s.cmap or "RdYlGn",
                           origin="lower")
            ax.set_xticks(range(len(df.columns)))
            ax.set_xticklabels([str(c) for c in df.columns])
            ax.set_yticks(range(len(df.index)))
            ax.set_yticklabels([str(i) for i in df.index])
            if s.name:
                ax.set_title(s.name)
            # colorbar
            self._fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    def _annotate_trades(self, ax, result):
        import matplotlib.pyplot as plt
        equity = result.equity
        for f in result.fills:
            ts = f.ts
            if ts not in equity.index:
                # reindex to nearest
                if equity.index.min() <= ts <= equity.index.max():
                    val = equity.reindex([ts], method="ffill").iloc[0]
                else:
                    continue
            else:
                val = equity.loc[ts]
            side = str(getattr(f.side, "value", f.side))
            if side == "buy":
                ax.annotate("B", (ts, val), color="green", fontsize=8,
                            ha="center", va="bottom",
                            arrowprops=dict(arrowstyle="->", color="green", lw=0.5))
            else:
                ax.annotate("S", (ts, val), color="red", fontsize=8,
                            ha="center", va="top",
                            arrowprops=dict(arrowstyle="->", color="red", lw=0.5))

    def show(self) -> None:
        import matplotlib.pyplot as plt
        if self._fig is not None:
            plt.show()

    def savefig(self, path: str, dpi: int = 150) -> None:
        if self._fig is not None:
            self._fig.savefig(path, dpi=dpi, bbox_inches="tight")
