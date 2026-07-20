import numpy as np
import pandas as pd
from stockstat_kernel.backtest import (
    BacktestEngine,
    Order,
    Strategy,
    ZeroCost,
)


class BuyOnce(Strategy):
    def __init__(self):
        self.done = False

    def on_bar(self, ctx):
        if not self.done:
            ctx.broker.submit(Order("TEST", "buy", 1.0))
            self.done = True


def market():
    index = pd.date_range("2024-01-01", periods=8, tz="UTC", freq="D")
    close = np.arange(100.0, 108.0)
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        },
        index=index,
    )
    return {"TEST": {"1d": frame}}


def test_backtest_has_local_rng_without_changing_global_state():
    np.random.seed(123)
    expected = np.random.random()
    np.random.seed(123)
    result = BacktestEngine(
        market(), BuyOnce(), initial_cash=1000, cost_model=ZeroCost(), seed=42
    ).run()
    assert np.random.random() == expected
    assert len(result.equity) == 8
    assert result.metrics["num_fills"] == 1


def test_market_validation_rejects_invalid_ohlc():
    data = market()
    data["TEST"]["1d"].iloc[0, data["TEST"]["1d"].columns.get_loc("high")] = 1.0
    try:
        BacktestEngine(data, BuyOnce())
    except ValueError as exc:
        assert "high" in str(exc)
    else:
        raise AssertionError("invalid OHLC was accepted")
