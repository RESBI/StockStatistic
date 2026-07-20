from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd
import pyarrow as pa
from stockstat_contracts import BacktestParameters, IndicatorParameters

from .backtest import BacktestEngine, component_from_ref, load_strategy
from .catalog import INDICATORS
from .market import MarketDataset
from .serialization import SerializedOutput, serialize_backtest, write_arrow


class ProgressReporter(Protocol):
    def report(self, fraction: float, message: str = "") -> None: ...


class NullReporter:
    def report(self, fraction: float, message: str = "") -> None:
        pass


@dataclass(frozen=True)
class ExecutionContext:
    output_dir: Path
    random_seed: int = 0


def execute_indicator(
    context: ExecutionContext,
    table: pa.Table,
    parameters: IndicatorParameters,
    reporter: ProgressReporter | None = None,
) -> SerializedOutput:
    reporter = reporter or NullReporter()
    reporter.report(0.1, "decoding input")
    frame = table.to_pandas()
    arguments = [frame[column] for column in parameters.columns]
    result = INDICATORS.compute(parameters.indicator, *arguments, **parameters.arguments)
    values = result if isinstance(result, tuple) else (result,)
    descriptor = INDICATORS.descriptor(parameters.indicator)
    columns = {}
    scalars = {}
    for name, value in zip(descriptor.outputs, values, strict=True):
        if isinstance(value, pd.Series):
            columns[name] = value
        else:
            array = getattr(value, "ndim", 0)
            if array == 1 and len(value) == len(frame):
                columns[name] = value
            else:
                scalars[name] = value.tolist() if hasattr(value, "tolist") else value
    context.output_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    if columns:
        output = pd.DataFrame(columns)
        timestamps = frame["ts"] if "ts" in frame else frame.index
        output.insert(0, "ts", timestamps)
        path = context.output_dir / "indicator.arrow"
        write_arrow(pa.Table.from_pandas(output, preserve_index=False), path)
        files["values"] = path
    reporter.report(1.0, "complete")
    return SerializedOutput(
        {
            "result_schema": "stockstat.result.indicator/1",
            "indicator": parameters.indicator,
            "scalars": scalars,
        },
        files,
    )


def execute_backtest(
    context: ExecutionContext,
    market: MarketDataset,
    parameters: BacktestParameters,
    reporter: ProgressReporter | None = None,
) -> SerializedOutput:
    reporter = reporter or NullReporter()
    reporter.report(0.1, "loading strategy")
    strategy = load_strategy(parameters.strategy)
    engine = BacktestEngine(
        market.universe,
        strategy,
        initial_cash=parameters.initial_cash,
        cost_model=component_from_ref(parameters.cost_model),
        fill_model=component_from_ref(parameters.fill_model),
        benchmark=parameters.benchmark,
        trade_on=parameters.trade_on,
        allow_short=parameters.allow_short,
        lookahead_audit=parameters.lookahead_audit,
        seed=parameters.random_seed,
        periods_per_year=parameters.periods_per_year,
        execution_model=component_from_ref(parameters.execution_model),
    )
    reporter.report(0.2, "running backtest")
    result = engine.run()
    reporter.report(0.9, "serializing result")
    output = serialize_backtest(result, context.output_dir)
    reporter.report(1.0, "complete")
    return output
