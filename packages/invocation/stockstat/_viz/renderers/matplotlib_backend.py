"""Matplotlib 渲染器（可选依赖）。"""
from __future__ import annotations

import io
from typing import Any


class NullRenderer:
    """空渲染器（matplotlib 未安装时使用）。"""
    name = "null"

    def render(self, spec: Any) -> bytes:
        return b""


class MatplotlibRenderer:
    """matplotlib 渲染器。"""
    name = "matplotlib"

    def render(self, spec: Any) -> bytes:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError as e:
            raise ImportError(
                "MatplotlibRenderer requires 'matplotlib'. "
                "Install with: pip install stockstat[viz]"
            ) from e
        import pandas as pd

        fig, ax = plt.subplots(figsize=spec.params.get("figsize", (10, 6)))
        data = spec.data
        if isinstance(data, pd.DataFrame):
            if spec.chart_type == "line":
                for col in data.select_dtypes(include="number").columns:
                    ax.plot(data.index, data[col], label=col)
                ax.legend()
            elif spec.chart_type == "bar":
                data.plot(kind="bar", ax=ax)
            elif spec.chart_type == "scatter":
                if len(data.columns) >= 2:
                    ax.scatter(data.iloc[:, 0], data.iloc[:, 1])
            elif spec.chart_type == "heatmap":
                import numpy as np
                if hasattr(data, "values"):
                    im = ax.imshow(data.values, cmap="viridis", aspect="auto")
                    fig.colorbar(im)
        elif isinstance(data, pd.Series):
            ax.plot(data.index, data.values)
        ax.set_title(spec.title)
        if spec.params.get("xlabel"):
            ax.set_xlabel(spec.params["xlabel"])
        if spec.params.get("ylabel"):
            ax.set_ylabel(spec.params["ylabel"])
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=spec.params.get("dpi", 100))
        plt.close(fig)
        return buf.getvalue()


__all__ = ["MatplotlibRenderer", "NullRenderer"]
