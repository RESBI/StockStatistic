"""BacktestEngine — 回测引擎主体。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

import numpy as np
import pandas as pd

from stockstat_foundation.errors import ComputeError

from .broker import Broker
from .cost_model import CostModel, get_cost_model
from .execution_model import ExecutionModel, get_execution_model
from .fill_model import FillModel, get_fill_model
from .metrics import calculate_metrics
from .portfolio import Portfolio
from .result import BacktestResult, BacktestMetrics, EquityPoint
from .strategy import StrategyBase, Strategy, Signal


class BacktestEngine:
    """回测引擎 — 事件驱动，按 bar 推进。

    用法：
        engine = BacktestEngine(data, strategy, initial_cash=10000)
        result = engine.run()
    """

    def __init__(
        self,
        data: pd.DataFrame,
        strategy: Union[StrategyBase, callable],
        *,
        initial_cash: float = 1_000_000.0,
        cost_model=None,
        fill_model=None,
        execution_model=None,
        benchmark: Optional[str] = None,
        trade_on: str = "open",
        allow_short: bool = False,
        periods_per_year: Optional[int] = None,
        symbol: str = "",
        timeframe: str = "",
        strategy_name: str = "",
        **kwargs,
    ):
        if data is None or len(data) == 0:
            raise ComputeError("BacktestEngine requires non-empty data")
        self._data = self._normalize_data(data)
        if isinstance(strategy, StrategyBase):
            self._strategy = strategy
        elif callable(strategy):
            self._strategy = Strategy(strategy, name=strategy_name or "func")
        else:
            raise ComputeError(f"Invalid strategy type: {type(strategy).__name__}")

        self._initial_cash = float(initial_cash)
        self._portfolio = Portfolio(initial_cash=self._initial_cash,
                                     allow_short=allow_short)
        self._cost_model = self._resolve_cost_model(cost_model)
        self._fill_model = self._resolve_fill_model(fill_model) if fill_model else get_fill_model("next_open")
        self._execution_model = get_execution_model(execution_model) if execution_model else get_execution_model("next_bar")
        self._benchmark = benchmark
        self._trade_on = trade_on
        self._allow_short = allow_short
        self._symbol = symbol or "default"
        self._timeframe = timeframe
        self._strategy_name = strategy_name or getattr(self._strategy, "name", "strategy")
        self._periods_per_year = periods_per_year or self._infer_periods_per_year()
        self._broker = Broker(self._portfolio, self._cost_model, self._fill_model)

    def _normalize_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """规范化数据：确保有 timestamp/open/high/low/close/volume 列。"""
        df = data.copy()
        col_map = {
            "Date": "timestamp", "Datetime": "timestamp", "Time": "timestamp",
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "timestamp" not in df.columns:
            df["timestamp"] = df.index
        for col in ["open", "high", "low", "close"]:
            if col not in df.columns:
                raise ComputeError(f"BacktestEngine requires column: {col}")
        if "volume" not in df.columns:
            df["volume"] = 0.0
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def _resolve_cost_model(self, cost_model) -> CostModel:
        if cost_model is None:
            return get_cost_model("default")
        if isinstance(cost_model, CostModel):
            return cost_model
        if isinstance(cost_model, str):
            return get_cost_model(cost_model)
        if isinstance(cost_model, dict):
            return CostModel(**cost_model)
        return get_cost_model("default")

    def _resolve_fill_model(self, fill_model) -> FillModel:
        if isinstance(fill_model, FillModel):
            return fill_model
        if isinstance(fill_model, str):
            return get_fill_model(fill_model)
        if isinstance(fill_model, dict):
            return FillModel(**fill_model)
        return get_fill_model("next_open")

    def _infer_periods_per_year(self) -> int:
        if not self._timeframe:
            return 252
        tf = self._timeframe.lower()
        if tf in ("1d", "d", "daily", "day"):
            return 252
        if tf in ("1w", "w", "weekly"):
            return 52
        if tf in ("1h", "h", "hourly"):
            return 252 * 24
        if tf in ("4h",):
            return 252 * 6
        if tf in ("1m", "m", "min", "minute"):
            return 252 * 24 * 60
        return 252

    def run(self) -> BacktestResult:
        """执行回测，返回 BacktestResult。"""
        started_at = datetime.utcnow()
        try:
            self._portfolio.reset()
            self._broker.reset()
            context = {
                "initial_cash": self._initial_cash,
                "symbol": self._symbol,
                "timeframe": self._timeframe,
            }
            self._strategy.on_init(self._data, context)

            equity_points = []
            n = len(self._data)
            for i in range(n):
                bar = self._data.iloc[i]
                ts = bar.get("timestamp")

                # 当前权益
                prices = {self._symbol: float(bar["close"])}
                current_equity = self._portfolio.total_value(prices)

                # 调用策略
                sig = self._strategy.on_bar(i, bar, self._data, context)

                # 执行信号
                if sig is not None and sig.side != "hold":
                    # 强制 signal.symbol 与 engine symbol 一致
                    sig.symbol = self._symbol
                    if not sig.timestamp:
                        sig.timestamp = ts
                    self._broker.execute_signal(sig, i, self._data, current_equity)
                    # 重新计算权益
                    current_equity = self._portfolio.total_value(prices)

                # 记录权益点
                cummax = max([p.equity for p in equity_points] + [self._initial_cash])
                drawdown = (current_equity - cummax) / cummax if cummax > 0 else 0.0
                ep = EquityPoint(
                    timestamp=ts,
                    equity=current_equity,
                    cash=self._portfolio.cash,
                    position_value=current_equity - self._portfolio.cash,
                    drawdown=drawdown,
                )
                equity_points.append(ep)

            self._strategy.on_finish(self._data, context)

            # 构造结果
            equity_df = pd.DataFrame([ep.to_dict() for ep in equity_points])
            if "timestamp" in equity_df.columns:
                equity_df = equity_df.set_index("timestamp")
            metrics = calculate_metrics(
                equity_df.reset_index() if "timestamp" in equity_df.columns else equity_df,
                self._broker.trades,
                self._initial_cash,
                self._periods_per_year,
            )
            finished_at = datetime.utcnow()
            return BacktestResult(
                metrics=metrics,
                trades=list(self._broker.trades),
                equity_curve=equity_df,
                strategy_name=self._strategy_name,
                symbol=self._symbol,
                timeframe=self._timeframe,
                initial_cash=self._initial_cash,
                final_equity=metrics.final_equity,
                started_at=started_at,
                finished_at=finished_at,
                metadata={"n_bars": n, "periods_per_year": self._periods_per_year},
            )
        except Exception as e:
            if isinstance(e, ComputeError):
                raise
            return BacktestResult(
                metrics=BacktestMetrics(initial_cash=self._initial_cash),
                trades=list(self._broker.trades),
                strategy_name=self._strategy_name,
                symbol=self._symbol,
                initial_cash=self._initial_cash,
                started_at=started_at,
                finished_at=datetime.utcnow(),
                error=str(e),
            )


__all__ = ["BacktestEngine"]
