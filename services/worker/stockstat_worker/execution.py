from __future__ import annotations

import errno
import multiprocessing as mp
import os
import queue
import shutil
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path

import pyarrow.ipc as ipc
from stockstat_contracts import BacktestParameters, IndicatorParameters, WorkLease, WorkUnitSpec
from stockstat_kernel.capabilities import (
    ExecutionContext,
    execute_backtest,
    execute_indicator,
)
from stockstat_kernel.experiments import (
    execute_batch_shard,
    execute_search_shard,
    execute_simulation_shard,
    reduce_tables,
)
from stockstat_kernel.market import MarketDataset


@dataclass(frozen=True)
class ProcessResult:
    success: bool
    manifest: dict | None = None
    files: dict[str, str] | None = None
    error: dict | None = None
    stdout: str = ""
    stderr: str = ""


def _execute_child(work_json: str, input_paths: list[str], output_dir: str, result_queue) -> None:
    try:
        work = WorkUnitSpec.model_validate_json(work_json)
        context = ExecutionContext(Path(output_dir), work.random_seed)
        if work.executor_role.value == "reduce":
            output = reduce_tables(
                input_paths,
                context.output_dir,
                work.capability_id,
                work.parameters,
            )
        else:
            with Path(input_paths[0]).open("rb") as stream:
                table = ipc.open_stream(stream).read_all()
        if work.executor_role.value == "reduce":
            pass
        elif work.capability_id in {
            "finance.indicator.compute",
            "finance.timeseries.analyze",
        }:
            parameters = IndicatorParameters.model_validate(work.parameters)
            output = execute_indicator(context, table, parameters)
        elif work.capability_id == "finance.backtest.run":
            market = MarketDataset.from_arrow(table)
            parameters = BacktestParameters.model_validate(work.parameters)
            output = execute_backtest(context, market, parameters)
        elif work.capability_id == "finance.experiment.search":
            market = MarketDataset.from_arrow(table)
            output = execute_search_shard(market, work.parameters, context.output_dir)
        elif work.capability_id in {
            "finance.experiment.batch",
            "finance.validation.walk_forward",
        }:
            market = MarketDataset.from_arrow(table)
            output = execute_batch_shard(market, work.parameters, context.output_dir)
        elif work.capability_id == "finance.simulation.resample":
            market = MarketDataset.from_arrow(table)
            output = execute_simulation_shard(market, work.parameters, context.output_dir)
        else:
            raise LookupError(f"unsupported capability: {work.capability_id}")
        result_queue.put(
            {
                "success": True,
                "manifest": output.manifest,
                "files": {name: str(path) for name, path in output.files.items()},
            }
        )
    except BaseException as exc:
        result_queue.put(
            {
                "success": False,
                "error": {
                    **_error_info(exc),
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=20),
                },
            }
        )


class ProcessSupervisor:
    def __init__(self, scratch_root: str | Path, timeout_seconds: float = 3600):
        self.scratch_root = Path(scratch_root)
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.context = mp.get_context("spawn")

    def execute(
        self, lease: WorkLease, input_paths: list[Path], timeout_seconds: float | None = None
    ) -> ProcessResult:
        attempt_dir = Path(
            tempfile.mkdtemp(prefix=f"attempt-{lease.attempt_id}-", dir=self.scratch_root)
        )
        output_dir = attempt_dir / "output"
        result_queue = self.context.Queue(maxsize=1)
        process = self.context.Process(
            target=_execute_child,
            args=(
                lease.work.model_dump_json(),
                [str(path) for path in input_paths],
                str(output_dir),
                result_queue,
            ),
            daemon=False,
        )
        previous = {name: os.environ.get(name) for name in _THREAD_VARIABLES}
        for name in _THREAD_VARIABLES:
            os.environ[name] = str(max(1, int(lease.work.resources.cpu_cores)))
        try:
            process.start()
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        process.join(timeout_seconds or self.timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(5)
            shutil.rmtree(attempt_dir, ignore_errors=True)
            return ProcessResult(
                False,
                error={
                    "code": "DEADLINE_EXCEEDED",
                    "category": "infrastructure",
                    "message": "executor process exceeded its timeout",
                    "retryable": True,
                },
            )
        try:
            payload = result_queue.get(timeout=1)
        except queue.Empty:
            shutil.rmtree(attempt_dir, ignore_errors=True)
            return ProcessResult(
                False,
                error={
                    "code": "EXECUTOR_CRASHED",
                    "category": "infrastructure",
                    "message": f"executor exited with code {process.exitcode}",
                    "retryable": True,
                },
            )
        if not payload["success"]:
            shutil.rmtree(attempt_dir, ignore_errors=True)
            return ProcessResult(False, error=payload["error"])
        return ProcessResult(True, manifest=payload["manifest"], files=payload["files"])


_THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def _error_info(exc):
    if isinstance(exc, MemoryError):
        return {"code": "EXECUTOR_OOM", "category": "resource", "retryable": True}
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return {"code": "DISK_FULL", "category": "resource", "retryable": False}
    return {"code": "COMPUTE_FAILED", "category": "compute", "retryable": False}
