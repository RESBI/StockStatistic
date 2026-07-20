"""Fee sensitivity sweep tools."""
from __future__ import annotations

from typing import Optional
import pandas as pd

from .engine import BacktestEngine
from .cost_model import CostModel, PercentCost, MakerTakerCost


def fee_sweep(data: dict, strategy, fee_rates: list[float],
              initial_cash: float = 1_000_000.0,
              fill_model=None,
              benchmark: Optional[str] = None,
              allow_short: bool = False) -> pd.DataFrame:
    """Sweep a range of uniform fee rates and return metrics for each.

    Args:
        data: Backtest data universe.
        strategy: Strategy to run.
        fee_rates: List of commission rates to test (e.g., [0.0, 0.001, 0.002]).
        initial_cash: Starting capital.
        fill_model: Optional fill model.
        benchmark: Optional benchmark symbol.
        allow_short: Allow short selling.

    Returns:
        DataFrame with one row per fee rate, columns = all metrics + fee_rate.
    """
    results = []
    for rate in fee_rates:
        eng = BacktestEngine(
            data=data, strategy=strategy,
            initial_cash=initial_cash,
            cost_model=PercentCost(commission=rate, slippage=0.0),
            fill_model=fill_model,
            benchmark=benchmark,
            allow_short=allow_short,
        )
        res = eng.run()
        m = res.metrics()
        m["fee_rate"] = rate
        results.append(m)
    return pd.DataFrame(results).set_index("fee_rate")


def maker_taker_sweep(data: dict, strategy,
                      maker_rates: list[float],
                      taker_rates: list[float],
                      initial_cash: float = 1_000_000.0,
                      fill_model=None,
                      allow_short: bool = False) -> pd.DataFrame:
    """Sweep a grid of maker × taker rates and return metrics for each combination.

    Returns DataFrame with MultiIndex (maker_rate, taker_rate).
    """
    results = []
    for mr in maker_rates:
        for tr in taker_rates:
            eng = BacktestEngine(
                data=data, strategy=strategy,
                initial_cash=initial_cash,
                cost_model=MakerTakerCost(maker_rate=mr, taker_rate=tr, slippage=0.0),
                fill_model=fill_model,
                allow_short=allow_short,
            )
            res = eng.run()
            m = res.metrics()
            m["maker_rate"] = mr
            m["taker_rate"] = tr
            results.append(m)
    return pd.DataFrame(results).set_index(["maker_rate", "taker_rate"])
