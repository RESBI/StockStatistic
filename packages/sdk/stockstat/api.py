from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc
from stockstat_contracts import (
    BacktestParameters,
    ComponentRef,
    DatasetSelector,
    IndicatorParameters,
    InstrumentRef,
    JobSpec,
    OperationSpec,
    OutputPolicy,
    StrategyRef,
)


class DataAPI:
    def __init__(self, session):
        self.session = session

    def ingest(
        self,
        instrument,
        *,
        source="synthetic",
        venue="synthetic",
        asset_class="synthetic",
        timeframe="1d",
        start,
        end,
    ):
        reference = InstrumentRef(asset_class=asset_class, symbol=instrument, venue=venue)
        if self.session._local:
            return self.session._local.ingestion.ingest(
                reference, source, timeframe, _time(start), _time(end)
            )
        return self.session._artifacts.ingest(
            reference, source, timeframe, _time(start), _time(end)
        )

    def selector(
        self,
        instrument,
        *,
        venue="synthetic",
        asset_class="synthetic",
        timeframe="1d",
        start,
        end,
        source="synthetic",
    ):
        from stockstat_contracts import SourcePolicy

        return DatasetSelector(
            instruments=(InstrumentRef(asset_class=asset_class, symbol=instrument, venue=venue),),
            timeframe=timeframe,
            start=_time(start),
            end=_time(end),
            source_policy=SourcePolicy(mode="exact", source=source),
        )

    def ohlcv(
        self,
        instrument,
        *,
        venue="synthetic",
        asset_class="synthetic",
        timeframe="1d",
        start,
        end,
        source="synthetic",
    ):
        selector = self.selector(
            instrument,
            venue=venue,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
        )
        if not self.session._local:
            raise NotImplementedError("remote direct OHLCV materialization uses DatasetHandle")
        result = self.session._local.repository.query_ohlcv(
            selector.instruments,
            selector.timeframe,
            selector.start,
            selector.end,
            source,
        )
        if result.empty:
            return result
        return result.set_index("ts")


class IndicatorAPI:
    def __init__(self, session):
        self.session = session

    def submit(self, indicator, input, *, columns=("close",), **arguments):
        binding = self.session._binding(input, "input")
        spec = JobSpec(
            name=f"indicator:{indicator}",
            operation=OperationSpec(
                capability_id=(
                    "finance.timeseries.analyze"
                    if indicator in _TIMESERIES
                    else "finance.indicator.compute"
                ),
                capability_version="1.0",
                parameters=IndicatorParameters(
                    indicator=indicator, arguments=arguments, columns=tuple(columns)
                ).model_dump(mode="json"),
                result_schema="stockstat.result.indicator/1",
            ),
            inputs=(binding,),
            outputs=OutputPolicy(detail_level="standard"),
        )
        return self.session._submit(spec)

    def run(self, indicator, input, *, columns=("close",), **arguments):
        return self.submit(indicator, input, columns=columns, **arguments).wait().as_indicator()

    def ma(self, input, window=20, column="close"):
        return self.run("ma", input, columns=(column,), window=window).as_series()

    def rsi(self, input, window=14, column="close"):
        return self.run("rsi", input, columns=(column,), window=window).as_series()


class BacktestAPI:
    def __init__(self, session):
        self.session = session

    def submit(
        self,
        data,
        strategy: StrategyRef,
        *,
        initial_cash=1_000_000,
        allow_short=False,
        random_seed=0,
        cost_model=None,
        fill_model=None,
        execution_model=None,
        periods_per_year=None,
    ):
        binding = self.session._binding(data, "market_data")
        parameters = BacktestParameters(
            strategy=strategy,
            initial_cash=initial_cash,
            allow_short=allow_short,
            random_seed=random_seed,
            periods_per_year=periods_per_year,
            cost_model=cost_model or ComponentRef(id="cost.percent"),
            fill_model=fill_model or ComponentRef(id="fill.next_open"),
            execution_model=execution_model or ComponentRef(id="execution.next_bar"),
        )
        spec = JobSpec(
            name=f"backtest:{strategy.name}",
            operation=OperationSpec(
                capability_id="finance.backtest.run",
                capability_version="1.0",
                parameters=parameters.model_dump(mode="json"),
                result_schema="stockstat.result.backtest/1",
            ),
            inputs=(binding,),
            outputs=OutputPolicy(detail_level="standard"),
        )
        return self.session._submit(spec)

    def run(self, *args, **kwargs):
        return self.submit(*args, **kwargs).wait().as_backtest()


class StrategyAPI:
    def builtin(self, name, entrypoint, config=None):
        return StrategyRef(
            kind="builtin",
            name=name,
            version="1.0.0",
            entrypoint=entrypoint,
            config=config or {},
        )


class ExperimentAPI:
    def __init__(self, session):
        self.session = session

    def grid_search(
        self,
        data,
        *,
        base_backtest,
        parameter_space,
        objective=None,
        batch_size=8,
    ):
        return self._submit(
            "finance.experiment.search",
            data,
            {
                "base_backtest": _backtest_payload(base_backtest),
                "parameter_space": parameter_space,
                "objective": objective or {"metric": "sharpe", "direction": "maximize"},
                "batch_size": batch_size,
            },
            "stockstat.result.search/1",
        )

    def batch(self, data, *, runs, batch_size=8):
        payload = [{**run, "backtest": _backtest_payload(run["backtest"])} for run in runs]
        return self._submit(
            "finance.experiment.batch",
            data,
            {"runs": payload, "batch_size": batch_size},
            "stockstat.result.batch/1",
        )

    def _submit(self, capability_id, data, parameters, result_schema):
        binding = self.session._binding(data, "market_data")
        spec = JobSpec(
            name=capability_id,
            operation=OperationSpec(
                capability_id=capability_id,
                capability_version="1.0",
                parameters=parameters,
                result_schema=result_schema,
            ),
            inputs=(binding,),
        )
        return self.session._submit(spec)


class SimulationAPI(ExperimentAPI):
    def bootstrap(
        self,
        data,
        *,
        base_backtest,
        n_samples=1000,
        shards=4,
        random_seed=0,
    ):
        return self._submit(
            "finance.simulation.resample",
            data,
            {
                "base_backtest": _backtest_payload(base_backtest),
                "n_samples": n_samples,
                "shards": shards,
                "random_seed": random_seed,
                "method": "iid_bootstrap",
            },
            "stockstat.result.simulation/1",
        )


class ValidationAPI(ExperimentAPI):
    def walk_forward(self, data, *, base_backtest, windows, batch_size=4):
        return self._submit(
            "finance.validation.walk_forward",
            data,
            {
                "base_backtest": _backtest_payload(base_backtest),
                "windows": windows,
                "batch_size": batch_size,
            },
            "stockstat.result.walk-forward/1",
        )


def dataframe_to_arrow(frame: pd.DataFrame, path: Path):
    table = pa.Table.from_pandas(frame, preserve_index=True)
    with path.open("wb") as stream:
        with ipc.new_stream(stream, table.schema) as writer:
            writer.write_table(table)


def _time(value):
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    return timestamp.to_pydatetime()


_TIMESERIES = {
    "wavelet_decompose",
    "spectral_entropy",
    "grey_relation",
    "gm11_predict",
    "transfer_entropy",
    "hurst_dfa",
    "sample_entropy",
    "permutation_entropy",
}


def _backtest_payload(value):
    if isinstance(value, BacktestParameters):
        return value.model_dump(mode="json")
    return BacktestParameters.model_validate(value).model_dump(mode="json")
