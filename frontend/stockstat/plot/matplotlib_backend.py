from __future__ import annotations

from typing import Optional, Any

from .base import PlotRenderer, PlotSpec


class MatplotlibRenderer(PlotRenderer):
    def __init__(self):
        self._fig = None
        self._ax = None
        self._ax2 = None

    def available(self) -> bool:
        try:
            import matplotlib  # noqa: F401
            return True
        except ImportError:
            return False

    def render(self, spec: PlotSpec) -> Any:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 6))
        self._fig = fig
        self._ax = ax
        self._ax2 = None

        for s in spec.series:
            if s.secondary_y and self._ax2 is None:
                self._ax2 = ax.twinx()

            target_ax = self._ax2 if s.secondary_y else self._ax
            data = s.data.dropna()

            if s.kind == "line":
                target_ax.plot(data.index, data.values, label=s.name, color=s.color)
            elif s.kind == "bar":
                target_ax.bar(data.index, data.values, label=s.name, color=s.color)
            elif s.kind == "scatter":
                target_ax.scatter(data.index, data.values, label=s.name, color=s.color)

        if spec.title:
            ax.set_title(spec.title)
        if spec.x_label:
            ax.set_xlabel(spec.x_label)
        if spec.y_label:
            ax.set_ylabel(spec.y_label)

        lines1, labels1 = ax.get_legend_handles_labels()
        if self._ax2:
            lines2, labels2 = self._ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2)
        else:
            ax.legend()

        fig.tight_layout()
        return fig

    def show(self) -> None:
        import matplotlib.pyplot as plt
        if self._fig is not None:
            plt.show()

    def savefig(self, path: str) -> None:
        if self._fig is not None:
            self._fig.savefig(path, dpi=150, bbox_inches="tight")
