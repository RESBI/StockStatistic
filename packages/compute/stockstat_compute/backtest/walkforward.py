"""WalkForward — 前向验证回测。"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .engine import BacktestEngine


class WalkForward:
    """前向验证回测 — 滚动窗口训练/测试。"""

    def __init__(self, data: pd.DataFrame, strategy,
                 *,
                 train_window: int = 252,
                 test_window: int = 63,
                 step: Optional[int] = None,
                 initial_cash: float = 1_000_000.0,
                 **engine_kwargs):
        self._data = data
        self._strategy = strategy
        self._train_window = int(train_window)
        self._test_window = int(test_window)
        self._step = int(step) if step else int(test_window)
        self._initial_cash = initial_cash
        self._engine_kwargs = engine_kwargs

    def run(self, on_progress=None) -> pd.DataFrame:
        """运行前向验证。"""
        n = len(self._data)
        results = []
        windows = []
        start = self._train_window
        while start + self._test_window <= n:
            windows.append((start, start + self._test_window))
            start += self._step

        total = len(windows)
        for i, (test_start, test_end) in enumerate(windows):
            train_data = self._data.iloc[max(0, test_start - self._train_window):test_start]
            test_data = self._data.iloc[test_start:test_end]
            try:
                engine = BacktestEngine(
                    test_data, self._strategy,
                    initial_cash=self._initial_cash,
                    **self._engine_kwargs,
                )
                result = engine.run()
                m = result.metrics
                results.append({
                    "window": i,
                    "train_start": str(train_data.iloc[0]["timestamp"]) if len(train_data) > 0 else "",
                    "train_end": str(train_data.iloc[-1]["timestamp"]) if len(train_data) > 0 else "",
                    "test_start": str(test_data.iloc[0]["timestamp"]) if len(test_data) > 0 else "",
                    "test_end": str(test_data.iloc[-1]["timestamp"]) if len(test_data) > 0 else "",
                    "total_return": m.total_return,
                    "sharpe": m.sharpe,
                    "max_drawdown": m.max_drawdown,
                    "n_trades": m.n_trades,
                    "final_equity": m.final_equity,
                    "error": result.error,
                })
            except Exception as e:
                results.append({
                    "window": i, "error": str(e),
                    "total_return": 0.0, "sharpe": 0.0,
                    "max_drawdown": 0.0, "n_trades": 0,
                })
            if on_progress:
                on_progress(i + 1, total)
        return pd.DataFrame(results)


__all__ = ["WalkForward"]
