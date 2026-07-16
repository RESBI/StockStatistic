from __future__ import annotations

from typing import Optional

import pandas as pd

from . import metrics as M


class BacktestResult:
    """Aggregated result of a backtest run."""

    def __init__(self, equity: pd.Series, fills: list,
                 positions_snapshot: dict, trades: list,
                 benchmark: Optional[pd.Series] = None,
                 realized_history: Optional[list] = None,
                 config: Optional[dict] = None):
        self.equity = equity
        self.fills = fills
        self.positions_snapshot = positions_snapshot
        self.trades = trades
        self.benchmark = benchmark
        self.realized_history = realized_history or []
        self.config = config or {}

    @property
    def returns(self) -> pd.Series:
        return self.equity.pct_change().dropna()

    @property
    def drawdown(self) -> pd.Series:
        return M.drawdown_series(self.equity)

    def metrics(self, risk_free: float = 0.02, periods_per_year: int = 252) -> dict:
        ppy = periods_per_year
        if ppy is None or ppy == 252:
            cfg_ppy = self.config.get("periods_per_year") if self.config else None
            if cfg_ppy is not None:
                ppy = cfg_ppy
        return M.compute_all_metrics(
            self.equity, fills=self.fills,
            realized_history=self.realized_history,
            benchmark=self.benchmark,
            risk_free=risk_free, periods_per_year=ppy,
        )

    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = []
        for t in self.trades:
            rows.append({
                "symbol": t.symbol,
                "side": getattr(t.side, "value", t.side),
                "qty": t.qty,
                "price": t.price,
                "ts": t.ts,
                "commission": t.commission,
                "slippage_cost": t.slippage_cost,
                "tag": t.tag,
            })
        return pd.DataFrame(rows)

    def fills_df(self) -> pd.DataFrame:
        return self.trades_df()

    def exit_reason_stats(self) -> dict[str, dict]:
        """Statistics grouped by exit reason.

        Returns {reason: {"count": n, "avg_pnl": float, "total_pnl": float}}.
        """
        from collections import defaultdict
        stats = defaultdict(lambda: {"count": 0, "total_pnl": 0.0})
        for ts, sym, pnl in self.realized_history:
            matching = [f for f in self.fills if f.ts == ts and f.symbol == sym]
            reason = matching[-1].exit_reason if matching else "unknown"
            stats[reason]["count"] += 1
            stats[reason]["total_pnl"] += pnl
        for r in stats.values():
            r["avg_pnl"] = r["total_pnl"] / r["count"] if r["count"] else 0.0
        return dict(stats)

    def summary(self) -> str:
        m = self.metrics()
        lines = ["=== Backtest Summary ==="]
        lines.append(f"Total Return:      {m['total_return']:.2%}")
        lines.append(f"Annualized Return: {m['annualized_return']:.2%}")
        lines.append(f"Sharpe:            {m['sharpe']:.3f}")
        lines.append(f"Sortino:           {m['sortino']:.3f}")
        lines.append(f"Max Drawdown:      {m['max_drawdown']:.2%}")
        lines.append(f"Calmar:            {m['calmar']:.3f}")
        lines.append(f"Volatility:        {m['volatility']:.2%}")
        if "win_rate" in m:
            lines.append(f"Win Rate:          {m['win_rate']:.2%}")
            lines.append(f"Profit Factor:     {m['profit_factor']:.3f}")
            lines.append(f"# Trades:          {m['num_trades']}")
        if "information_ratio" in m:
            lines.append(f"Information Ratio: {m['information_ratio']:.3f}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        m = self.metrics()
        return {
            "metrics": m,
            "config": self.config,
            "equity": self.equity.to_dict(),
            "trades": self.trades_df().to_dict(orient="records"),
        }

    def to_csv(self, path: str) -> None:
        self.trades_df().to_csv(path, index=False)

    def plot_equity(self):
        from .plot_adapter import plot_equity
        return plot_equity(self)

    def plot_drawdown(self):
        from .plot_adapter import plot_drawdown
        return plot_drawdown(self)

    def plot_trades(self):
        from .plot_adapter import plot_trades
        return plot_trades(self)

    # ── BacktestChartSpec API (BT-V series) ──

    def chart(self, name: str, **kwargs):
        """Build a `BacktestChartSpec` by chart type name.

        Available types: equity_curve, drawdown, trades_overlay,
        returns_distribution, monthly_heatmap, yearly_returns, underwater_curve,
        dashboard (BT-V3).
        """
        # Importing plot_adapter triggers @register_chart decorators.
        from . import plot_adapter  # noqa: F401  (registers builders)
        from .chart_registry import build_chart
        return build_chart(name, self, **kwargs)

    def render(self, name: str, path: Optional[str] = None,
               renderer=None, **kwargs):
        """One-liner: build chart `name` and render it (optionally savefig)."""
        from .chart_factory import get_chart_renderer
        spec = self.chart(name, **kwargs)
        r = renderer if renderer is not None else get_chart_renderer()
        fig = r.render(spec)
        if path is not None and r.available():
            r.savefig(path)
        return fig

    def render_all(self, directory: str, names: Optional[list] = None,
                   renderer=None, **kwargs) -> dict:
        """Batch-render multiple charts to PNGs in `directory`.

        Returns dict {chart_name: file_path}. Charts whose renderer is
        unavailable are skipped (with a single aggregated warning).
        """
        import os
        from .chart_factory import get_chart_renderer
        r = renderer if renderer is not None else get_chart_renderer()
        if not r.available():
            import warnings
            warnings.warn(
                "No backtest chart backend available; render_all skipped. "
                "Install matplotlib via `pip install stockstat[backtest_viz]`.",
                UserWarning, stacklevel=2,
            )
            return {}
        names = names or ["equity_curve", "drawdown", "trades_overlay",
                          "returns_distribution", "monthly_heatmap",
                          "yearly_returns", "underwater_curve"]
        os.makedirs(directory, exist_ok=True)
        out = {}
        for nm in names:
            try:
                spec = self.chart(nm, **kwargs)
            except KeyError:
                continue
            fig = r.render(spec)
            path = os.path.join(directory, f"{nm}.png")
            r.savefig(path)
            out[nm] = path
            import matplotlib.pyplot as plt
            plt.close(fig)
        return out

    @property
    def available_chart_types(self) -> list:
        from . import plot_adapter  # noqa: F401  (registers builders)
        from .chart_registry import list_chart_types
        return list_chart_types()
