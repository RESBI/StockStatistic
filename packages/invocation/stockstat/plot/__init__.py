"""plot — 绘图基础。"""
from __future__ import annotations


def plot_equity_curve(equity_df, title: str = "Equity Curve"):
    """绘制权益曲线。"""
    from .._viz import ChartSpec, MatplotlibRenderer, NullRenderer
    spec = ChartSpec(title=title, chart_type="line", data=equity_df,
                     params={"xlabel": "Date", "ylabel": "Equity"})
    try:
        return MatplotlibRenderer().render(spec)
    except ImportError:
        return NullRenderer().render(spec)


def plot_drawdown(equity_df, title: str = "Drawdown"):
    """绘制回撤曲线。"""
    from .._viz import ChartSpec, MatplotlibRenderer, NullRenderer
    if "drawdown" in equity_df.columns:
        dd = equity_df[["drawdown"]]
    else:
        import pandas as pd
        cummax = equity_df["equity"].cummax()
        dd = pd.DataFrame({"drawdown": (equity_df["equity"] - cummax) / cummax})
    spec = ChartSpec(title=title, chart_type="line", data=dd,
                     params={"xlabel": "Date", "ylabel": "Drawdown"})
    try:
        return MatplotlibRenderer().render(spec)
    except ImportError:
        return NullRenderer().render(spec)


__all__ = ["plot_equity_curve", "plot_drawdown"]
