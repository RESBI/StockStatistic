from __future__ import annotations

from typing import Optional, Union

import pandas as pd

from .broker import SimulatedBroker
from .context import BacktestContext
from .cost_model import CostModel, PercentCost
from .data_feed import DataFeed, Universe
from .fill_model import FillModel, NextOpenFill
from .portfolio import Portfolio
from .result import BacktestResult
from .strategy import Strategy
from ..compute.engine import ComputeEngine


class BacktestEngine:
    """Main backtest loop: iterate bars, dispatch strategy hooks, match orders."""

    def __init__(self,
                 data: dict,
                 strategy: Strategy,
                 initial_cash: float = 1_000_000.0,
                 cost_model: Optional[CostModel] = None,
                 fill_model: Optional[FillModel] = None,
                 benchmark: Optional[str] = None,
                 trade_on: str = "open",
                 allow_short: bool = False,
                 lookahead_audit: bool = False,
                 seed: int = 0,
                 compute_engine: Optional[ComputeEngine] = None):
        if trade_on not in ("open", "close"):
            raise ValueError("trade_on must be 'open' or 'close'")

        if isinstance(data, Universe):
            universe = data
        else:
            universe = Universe(data)

        self.universe = universe
        self.data_feed = DataFeed(universe)
        self.strategy = strategy
        self.trade_on = trade_on
        self.allow_short = allow_short
        self.lookahead_audit = lookahead_audit
        self.seed = seed

        self.portfolio = Portfolio(initial_cash=initial_cash, allow_short=allow_short)
        self.cost_model = cost_model or PercentCost()
        self.fill_model = fill_model or NextOpenFill()
        self.broker = SimulatedBroker(
            self.portfolio, self.cost_model, self.fill_model, allow_short=allow_short
        )

        self._compute = compute_engine if compute_engine is not None else ComputeEngine(client=None)
        self._benchmark_symbol = benchmark

    def run(self) -> BacktestResult:
        import numpy as np
        np.random.seed(self.seed)

        master = self.data_feed.master_index
        symbols = self.universe.symbols
        primary_tf = self.data_feed.primary_tf

        all_fills = []
        # on_start hook (before any bar; portfolio equity seeded inside the loop)
        if len(master):
            ctx0 = self._make_ctx(master[0], {})
            self.strategy.on_start(ctx0)

        for i, t in enumerate(master):
            current_bar = {}
            prices = {}
            for sym in symbols:
                bar = self.data_feed.bar_at(sym, primary_tf, t)
                if bar is not None:
                    current_bar[sym] = bar
                    prices[sym] = float(bar["close"])

            ctx = self._make_ctx(t, current_bar)

            # 1. Match pending orders (submitted at prior bars) at the OPEN of bar t.
            #    For NextOpenFill this fills at t.open; fill ts = t. This keeps
            #    equity-at-t consistent: a fill at t's open is valued at t's close.
            prev_bar_map = {}
            if i > 0:
                t_prev = master[i - 1]
                for sym in symbols:
                    pb = self.data_feed.bar_at(sym, primary_tf, t_prev)
                    if pb is not None:
                        prev_bar_map[sym] = pb

            for sym in symbols:
                pb = prev_bar_map.get(sym)
                bar = current_bar.get(sym)
                if bar is None:
                    continue
                fills = self.broker.process_bar(
                    sym, pb if pb is not None else pd.Series(), bar, t,
                )
                for f in fills:
                    all_fills.append(f)
                    self.strategy.on_fill(f, self._make_ctx(t, current_bar))

            # 2. Strategy decides at bar t (orders submitted here fill at t+1)
            self.strategy.on_bar(ctx)

            # 3. Mark to market at this bar close
            self.portfolio.mark_to_market(prices, ts=t)
            self.strategy.on_bar_close(ctx)

        # flush any remaining pending market orders at the last bar's close
        if len(master):
            last_t = master[-1]
            for sym in symbols:
                bar = self.data_feed.bar_at(sym, primary_tf, last_t)
                if bar is None:
                    continue
                fills = self.broker.process_bar(sym, bar, bar, last_t)
                for f in fills:
                    all_fills.append(f)

        # on_end
        if len(master):
            last_ctx = self._make_ctx(master[-1], {})
            self.strategy.on_end(last_ctx)

        equity = self.portfolio.equity_curve
        if equity.empty:
            equity = pd.Series([self.portfolio.initial_cash])

        bench_series = None
        if self._benchmark_symbol and self._benchmark_symbol in symbols:
            close = self.data_feed.close_series(self._benchmark_symbol, primary_tf)
            bench_series = buy_and_hold_equity(self.portfolio.initial_cash, close.reindex(equity.index, method="ffill"))

        positions_snapshot = {
            sym: {"qty": p.qty, "avg_cost": p.avg_cost, "realized_pnl": p.realized_pnl}
            for sym, p in self.portfolio.positions.items()
        }

        config = {
            "initial_cash": self.portfolio.initial_cash,
            "allow_short": self.allow_short,
            "trade_on": self.trade_on,
            "seed": self.seed,
            "primary_tf": primary_tf,
            "symbols": symbols,
            "cost_model": type(self.cost_model).__name__,
            "fill_model": type(self.fill_model).__name__,
        }

        return BacktestResult(
            equity=equity,
            fills=all_fills,
            positions_snapshot=positions_snapshot,
            trades=all_fills,
            benchmark=bench_series,
            realized_history=self.portfolio.realized_history,
            config=config,
        )

    def _make_ctx(self, t: pd.Timestamp, current_bar: dict) -> BacktestContext:
        return BacktestContext(
            data_feed=self.data_feed,
            portfolio=self.portfolio,
            broker=self.broker,
            compute_engine=self._compute,
            now=t,
            current_bar=current_bar,
            lookahead_audit=self.lookahead_audit,
        )


def buy_and_hold_equity(initial_cash: float, prices: pd.Series) -> pd.Series:
    if prices.empty:
        return pd.Series(dtype=float)
    first_valid = prices.dropna().iloc[0] if not prices.dropna().empty else prices.iloc[0]
    shares = initial_cash / first_valid
    return shares * prices
