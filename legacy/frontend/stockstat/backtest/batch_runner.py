"""Batch strategy runner for multi-strategy / multi-fee backtesting."""
from __future__ import annotations

from typing import Callable, Optional
import pandas as pd

from .engine import BacktestEngine
from .cost_model import CostModel, PercentCost
from .fill_model import FillModel, NextOpenFill
from .result import BacktestResult
from .metrics import _periods_per_year, compute_all_metrics


class StrategyBatchRunner:
    """Run multiple strategies under shared data/config, collect metrics.

    Usage:
        runner = StrategyBatchRunner(
            data={"BTC/USDT": {"1d": df}},
            initial_cash=10000,
            cost_model=BinanceCost(venue="futures", bnb_discount=True),
            fill_model=IntrabarLimitFill(),
        )
        results = runner.run_all({
            "ma_cross": ma_cross_strategy,
            "rsi_reversal": rsi_strategy,
        })
        df = results.to_dataframe()
    """

    def __init__(self, data: dict,
                 initial_cash: float = 1_000_000.0,
                 cost_model: Optional[CostModel] = None,
                 fill_model: Optional[FillModel] = None,
                 benchmark: Optional[str] = None,
                 allow_short: bool = False,
                 trade_on: str = "open",
                 periods_per_year: Optional[int] = None):
        self.data = data
        self.initial_cash = initial_cash
        self.cost_model = cost_model or PercentCost()
        self.fill_model = fill_model or NextOpenFill()
        self.benchmark = benchmark
        self.allow_short = allow_short
        self.trade_on = trade_on
        self.periods_per_year = periods_per_year

    def run_single(self, strategy, name: str = None) -> BacktestResult:
        eng = BacktestEngine(
            data=self.data, strategy=strategy,
            initial_cash=self.initial_cash,
            cost_model=self.cost_model,
            fill_model=self.fill_model,
            benchmark=self.benchmark,
            allow_short=self.allow_short,
            trade_on=self.trade_on,
        )
        res = eng.run()
        if name:
            res._batch_name = name
        return res

    def run_all(self, strategies: dict) -> "BatchResults":
        results = {}
        for name, strat in strategies.items():
            results[name] = self.run_single(strat, name)
        return BatchResults(results, self.periods_per_year)

    def run_all_fees(self, strategies: dict[str, object],
                     cost_models: dict[str, CostModel]) -> "BatchResults":
        results = {}
        for sname, strat in strategies.items():
            for fname, cm in cost_models.items():
                key = f"{sname}__{fname}"
                eng = BacktestEngine(
                    data=self.data, strategy=strat,
                    initial_cash=self.initial_cash,
                    cost_model=cm,
                    fill_model=self.fill_model,
                    benchmark=self.benchmark,
                    allow_short=self.allow_short,
                    trade_on=self.trade_on,
                )
                res = eng.run()
                res._batch_name = key
                res._strategy_name = sname
                res._fee_name = fname
                results[key] = res
        return BatchResults(results, self.periods_per_year)


class BatchResults:
    """Container for batch backtest results with analysis helpers."""

    def __init__(self, results: dict[str, BacktestResult],
                 periods_per_year: Optional[int] = None):
        self.results = results
        self._ppy = periods_per_year

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for name, res in self.results.items():
            ppy = self._ppy or _periods_per_year(res.equity.index)
            m = compute_all_metrics(
                res.equity, fills=res.fills,
                realized_history=res.realized_history,
                benchmark=res.benchmark,
                periods_per_year=ppy,
            )
            m["name"] = name
            rows.append(m)
        return pd.DataFrame(rows).set_index("name")

    def equity_curves(self) -> dict[str, pd.Series]:
        return {name: res.equity for name, res in self.results.items()}

    def best_by(self, metric: str = "sharpe", maximize: bool = True) -> tuple[str, float]:
        df = self.to_dataframe()
        col = df[metric]
        idx = col.idxmax() if maximize else col.idxmin()
        return idx, float(col.loc[idx])

    def rank(self, metric: str = "sharpe", ascending: bool = False) -> pd.DataFrame:
        df = self.to_dataframe()
        return df.sort_values(metric, ascending=ascending)
