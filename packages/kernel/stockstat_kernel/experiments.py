from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc
from stockstat_contracts import BacktestParameters, canonical_digest

from .backtest import BacktestEngine, component_from_ref, load_strategy
from .market import MarketDataset, Universe
from .serialization import SerializedOutput, write_arrow


def run_backtest(
    market: MarketDataset,
    parameters: BacktestParameters,
    window: dict | None = None,
):
    universe = market.universe
    if window:
        start = _utc_timestamp(window["start"])
        end = _utc_timestamp(window["end"])
        data = {}
        for instrument in universe.instruments:
            data[instrument] = {}
            for timeframe in universe.timeframes(instrument):
                frame = universe.frame(instrument, timeframe)
                data[instrument][timeframe] = frame.loc[
                    (frame.index >= start) & (frame.index < end)
                ]
        universe = Universe(data)
    return BacktestEngine(
        universe,
        load_strategy(parameters.strategy),
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
    ).run()


def execute_search_shard(market, parameters, output_dir: Path):
    objective = parameters["objective"]
    base = BacktestParameters.model_validate(parameters["base_backtest"])
    rows = []
    for candidate in parameters["candidates"]:
        candidate_id = canonical_digest(candidate)
        strategy = base.strategy.model_copy(
            update={"config": {**base.strategy.config, **candidate}}
        )
        try:
            result = run_backtest(market, base.model_copy(update={"strategy": strategy}))
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "parameter_json": json.dumps(candidate, sort_keys=True),
                    "objective": float(result.metrics.get(objective["metric"], np.nan)),
                    "status": "succeeded",
                    **{f"metric_{name}": value for name, value in result.metrics.items()},
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "parameter_json": json.dumps(candidate, sort_keys=True),
                    "objective": np.nan,
                    "status": "failed",
                    "error": str(exc),
                }
            )
    return table_output(rows, output_dir, "trials", "stockstat.result.search-shard/1")


def execute_batch_shard(market, parameters, output_dir: Path):
    rows = []
    for run in parameters["runs"]:
        try:
            result = run_backtest(
                market,
                BacktestParameters.model_validate(run["backtest"]),
                run.get("window"),
            )
            rows.append(
                {
                    "run_id": run["run_id"],
                    "status": "succeeded",
                    "window_json": json.dumps(run.get("window"), sort_keys=True),
                    **result.metrics,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "run_id": run["run_id"],
                    "status": "failed",
                    "error": str(exc),
                }
            )
    return table_output(rows, output_dir, "runs", "stockstat.result.batch-shard/1")


def execute_simulation_shard(market, parameters, output_dir: Path):
    baseline = run_backtest(market, BacktestParameters.model_validate(parameters["base_backtest"]))
    returns = baseline.equity.equity.pct_change(fill_method=None).dropna().to_numpy()
    initial = float(baseline.equity.equity.iloc[0])
    rows = []
    base_seed = int(parameters.get("random_seed", 0))
    start = int(parameters["simulation_start"])
    count = int(parameters["simulation_count"])
    for simulation_index in range(start, start + count):
        rng = np.random.default_rng(np.random.SeedSequence([base_seed, simulation_index]))
        sampled = rng.choice(returns, size=len(returns), replace=True)
        path = initial * np.cumprod(1 + sampled)
        running = np.maximum.accumulate(path)
        rows.append(
            {
                "simulation_index": simulation_index,
                "terminal_equity": float(path[-1]),
                "total_return": float(path[-1] / initial - 1),
                "max_drawdown": float(np.min((path - running) / running)),
            }
        )
    return table_output(
        rows,
        output_dir,
        "simulations",
        "stockstat.result.simulation-shard/1",
    )


def reduce_tables(input_paths, output_dir: Path, capability_id: str, parameters):
    frames = []
    for path in input_paths:
        with Path(path).open("rb") as stream:
            frames.append(ipc.open_stream(stream).read_all().to_pandas())
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if capability_id == "finance.experiment.search":
        direction = parameters["objective"].get("direction", "maximize")
        combined = combined.drop_duplicates("candidate_id", keep="last")
        combined = combined.sort_values(
            ["objective", "candidate_id"],
            ascending=[direction != "maximize", True],
            na_position="last",
        ).reset_index(drop=True)
        best = combined.loc[combined.status == "succeeded"].head(1)
        summary = {
            "best_parameters": (json.loads(best.iloc[0].parameter_json) if len(best) else None),
            "best_objective": float(best.iloc[0].objective) if len(best) else None,
            "total_trials": len(combined),
            "succeeded_trials": int((combined.status == "succeeded").sum()),
        }
        name = "ranking"
        schema = "stockstat.result.search/1"
    elif capability_id == "finance.simulation.resample":
        combined = combined.sort_values("simulation_index").drop_duplicates("simulation_index")
        summary = {
            "n_samples": len(combined),
            "return_quantiles": {
                str(quantile): float(combined.total_return.quantile(quantile))
                for quantile in (0.01, 0.05, 0.5, 0.95, 0.99)
            },
            "drawdown_95": float(combined.max_drawdown.quantile(0.05)),
        }
        name = "simulations"
        schema = "stockstat.result.simulation/1"
    else:
        combined = combined.sort_values("run_id").drop_duplicates("run_id")
        summary = {
            "total_runs": len(combined),
            "succeeded_runs": int((combined.status == "succeeded").sum()),
        }
        if capability_id == "finance.validation.walk_forward":
            name = "windows"
            schema = "stockstat.result.walk-forward/1"
        else:
            name = "summary"
            schema = "stockstat.result.batch/1"
    output = table_output(combined.to_dict("records"), output_dir, name, schema)
    output.manifest["summary"] = summary
    return output


def table_output(rows, output_dir, name, result_schema):
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    path = output_dir / f"{name}.arrow"
    write_arrow(pa.Table.from_pandas(frame, preserve_index=False), path)
    return SerializedOutput(
        {"result_schema": result_schema, "summary": {"row_count": len(frame)}},
        {name: path},
    )


def _utc_timestamp(value):
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tz is None else timestamp.tz_convert("UTC")
