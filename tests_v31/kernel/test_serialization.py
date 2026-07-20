from pathlib import Path

import numpy as np
import pandas as pd
from stockstat_kernel.backtest import BacktestEngine, Strategy
from stockstat_kernel.serialization import serialize_backtest


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


def test_backtest_result_is_arrow_and_json(tmp_path: Path):
    result = BacktestEngine(market(), Strategy(), initial_cash=1000).run()
    output = serialize_backtest(result, tmp_path)
    assert output.manifest["result_schema"] == "stockstat.result.backtest/1"
    assert (tmp_path / "manifest.json").is_file()
    assert all(path.is_file() for path in output.files.values())
