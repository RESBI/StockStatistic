"""Post-hoc analysis of backtest results: sub-period, regime, rolling, exit reason."""
from __future__ import annotations

from typing import Optional
import pandas as pd
import numpy as np

from .result import BacktestResult
from .metrics import compute_all_metrics, _periods_per_year


class BacktestAnalyzer:
    """Post-hoc analysis of a BacktestResult."""

    @staticmethod
    def subperiod_metrics(result: BacktestResult,
                           split_dates: list[pd.Timestamp]) -> dict[str, dict]:
        """Split equity curve at each split date and compute metrics per segment."""
        eq = result.equity
        if eq.empty:
            return {}

        boundaries = [eq.index[0]] + sorted(split_dates) + [eq.index[-1]]
        results = {}
        for i in range(len(boundaries) - 1):
            start, end = boundaries[i], boundaries[i + 1]
            if i < len(boundaries) - 2:
                segment = eq[(eq.index >= start) & (eq.index < end)]
            else:
                segment = eq[(eq.index >= start) & (eq.index <= end)]
            if len(segment) < 2:
                continue
            ppy = _periods_per_year(segment.index)
            m = compute_all_metrics(segment, periods_per_year=ppy)
            results[f"{pd.Timestamp(start).date()}_{pd.Timestamp(end).date()}"] = m
        return results

    @staticmethod
    def regime_conditional_metrics(result: BacktestResult,
                                    regime_series: pd.Series,
                                    labels: Optional[dict] = None) -> dict[str, dict]:
        """Compute metrics conditioned on a regime series."""
        eq = result.equity
        returns = eq.pct_change().dropna()

        aligned = regime_series.reindex(returns.index, method="ffill").dropna()
        common = returns.index.intersection(aligned.index)
        rets = returns.loc[common]
        regimes = aligned.loc[common]

        results = {}
        for regime_val in regimes.unique():
            mask = regimes == regime_val
            label = labels.get(regime_val, str(regime_val)) if labels else str(regime_val)
            regime_rets = rets[mask]
            if len(regime_rets) < 2:
                continue
            regime_eq = (1 + regime_rets).cumprod() * result.equity.iloc[0]
            ppy = _periods_per_year(regime_eq.index)
            m = compute_all_metrics(regime_eq, periods_per_year=ppy)
            m["n_bars"] = int(mask.sum())
            results[label] = m
        return results

    @staticmethod
    def rolling_metric(result: BacktestResult, metric: str = "sharpe",
                        window: int = 52) -> pd.Series:
        """Compute rolling metric over a window."""
        eq = result.equity
        rets = eq.pct_change().dropna()
        ppy = _periods_per_year(eq.index)

        if metric == "sharpe":
            rolling_mean = rets.rolling(window).mean()
            rolling_std = rets.rolling(window).std()
            return (rolling_mean / rolling_std * np.sqrt(ppy)).dropna()
        elif metric == "volatility":
            return (rets.rolling(window).std() * np.sqrt(ppy)).dropna()
        elif metric == "max_drawdown":
            def _mdd(s):
                peak = s.cummax()
                return float(((s - peak) / peak).min())
            return eq.rolling(window).apply(_mdd).dropna()
        elif metric == "return":
            return (eq / eq.shift(window) - 1).dropna()
        else:
            raise ValueError(f"Unknown metric: {metric}")

    @staticmethod
    def trade_analysis_by_exit(result: BacktestResult) -> pd.DataFrame:
        """Analyze trades grouped by exit_reason."""
        if not result.realized_history:
            return pd.DataFrame()

        rows = []
        for ts, sym, pnl in result.realized_history:
            matching = [f for f in result.fills if f.ts == ts and f.symbol == sym]
            reason = matching[-1].exit_reason if matching else "unknown"
            rows.append({"exit_reason": reason, "pnl": pnl})

        df = pd.DataFrame(rows)
        if df.empty:
            return df
        summary = df.groupby("exit_reason").agg(
            count=("pnl", "count"),
            win_rate=("pnl", lambda x: (x > 0).mean()),
            avg_pnl=("pnl", "mean"),
            total_pnl=("pnl", "sum"),
        ).reset_index()
        return summary
