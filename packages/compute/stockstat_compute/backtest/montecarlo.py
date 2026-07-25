"""MonteCarloEngine — 蒙特卡洛模拟。"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .engine import BacktestEngine
from .result import BacktestResult


class MonteCarloEngine:
    """蒙特卡洛回测引擎 — 通过重采样收益率序列评估策略稳健性。"""

    def __init__(self, data: pd.DataFrame, strategy,
                 *, initial_cash: float = 1_000_000.0,
                 n_simulations: int = 1000,
                 seed: int = 0,
                 **engine_kwargs):
        self._data = data
        self._strategy = strategy
        self._initial_cash = initial_cash
        self._n_simulations = int(n_simulations)
        self._seed = int(seed)
        self._engine_kwargs = engine_kwargs
        self._rng = np.random.default_rng(self._seed)

    def run(self, on_progress=None) -> pd.DataFrame:
        """运行 N 次蒙特卡洛模拟。"""
        # 先用原始数据跑一次回测，得到基线收益率序列
        baseline_engine = BacktestEngine(
            self._data, self._strategy,
            initial_cash=self._initial_cash,
            **self._engine_kwargs,
        )
        baseline = baseline_engine.run()
        if baseline.error:
            return pd.DataFrame([{"simulation": 0, "error": baseline.error}])

        returns = baseline.equity_curve["equity"].pct_change().dropna().values
        if len(returns) < 2:
            return pd.DataFrame([{"simulation": 0, "final_equity": baseline.final_equity,
                                  "total_return": baseline.metrics.total_return}])

        results = []
        for i in range(self._n_simulations):
            sampled = self._rng.choice(returns, size=len(returns), replace=True)
            equity = self._initial_cash * np.cumprod(1 + sampled)
            final = float(equity[-1])
            total_ret = final / self._initial_cash - 1
            # 计算指标
            max_dd = float(np.min((equity - np.maximum.accumulate(equity)) / np.maximum.accumulate(equity)))
            sharpe = float(np.mean(sampled) / np.std(sampled) * np.sqrt(252)) if np.std(sampled) > 0 else 0.0
            results.append({
                "simulation": i,
                "final_equity": final,
                "total_return": total_ret,
                "max_drawdown": max_dd,
                "sharpe": sharpe,
            })
            if on_progress:
                on_progress(i + 1, self._n_simulations)

        return pd.DataFrame(results)

    def summary(self) -> dict:
        """运行模拟并返回汇总统计。"""
        df = self.run()
        if len(df) == 0 or "error" in df.columns:
            return {"n_simulations": 0}
        return {
            "n_simulations": len(df),
            "mean_return": float(df["total_return"].mean()),
            "median_return": float(df["total_return"].median()),
            "std_return": float(df["total_return"].std()),
            "p5_return": float(df["total_return"].quantile(0.05)),
            "p95_return": float(df["total_return"].quantile(0.95)),
            "mean_sharpe": float(df["sharpe"].mean()),
            "prob_loss": float((df["total_return"] < 0).mean()),
        }


__all__ = ["MonteCarloEngine"]
