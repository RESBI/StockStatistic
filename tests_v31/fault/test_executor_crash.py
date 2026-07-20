import errno

import pandas as pd
import pytest
from stockstat import StockStat
from stockstat_contracts import (
    BacktestParameters,
    ComponentRef,
    ExecutionPolicy,
    JobSpec,
    OperationSpec,
    OutputPolicy,
    StrategyRef,
)
from stockstat_worker.execution import _error_info


def test_executor_crash_does_not_kill_agent(tmp_path):
    session = StockStat.local(tmp_path / "runtime")
    try:
        session.data.ingest(
            "PAXG/USDT",
            source="synthetic",
            venue="synthetic",
            asset_class="crypto",
            timeframe="1d",
            start="2024-01-01",
            end="2024-01-10",
        )
        selector = session.data.selector(
            "PAXG/USDT",
            venue="synthetic",
            asset_class="crypto",
            timeframe="1d",
            start="2024-01-01",
            end="2024-01-10",
        )
        parameters = BacktestParameters(
            strategy=StrategyRef(
                kind="python_module",
                name="crash",
                entrypoint="tests_v31.fixtures.crash_strategy:build_strategy",
            ),
            initial_cash=10_000,
            cost_model=ComponentRef(id="cost.zero"),
        )
        job = session._submit(
            JobSpec(
                name="crash",
                operation=OperationSpec(
                    capability_id="finance.backtest.run",
                    parameters=parameters.model_dump(mode="json"),
                    result_schema="stockstat.result.backtest/1",
                ),
                inputs=(session._binding(selector, "market_data"),),
                execution=ExecutionPolicy(max_attempts=1),
                outputs=OutputPolicy(),
            )
        )
        with pytest.raises(RuntimeError, match="EXECUTOR_CRASHED"):
            job.wait(timeout=30)
        frame = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        result = session.indicators.submit("ma", frame, window=2).wait(timeout=30)
        assert result.as_indicator().as_series().iloc[-1] == 2.5
    finally:
        session.close()


def test_resource_errors_are_classified():
    assert _error_info(MemoryError())["code"] == "EXECUTOR_OOM"
    assert _error_info(OSError(errno.ENOSPC, "disk full"))["code"] == "DISK_FULL"
