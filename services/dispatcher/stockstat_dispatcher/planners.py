from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Protocol

from stockstat_contracts import (
    ArtifactInput,
    DatasetInput,
    ExecutorRole,
    JobSpec,
    PartitionSpec,
    ResourceSpec,
    WorkUnitSpec,
    canonical_digest,
    new_id,
)


class SnapshotCoordinator(Protocol):
    def resolve(self, dataset_input: DatasetInput): ...


@dataclass(frozen=True)
class PlannedStage:
    stage_id: str
    name: str
    position: int
    work_units: tuple[WorkUnitSpec, ...]


@dataclass(frozen=True)
class Plan:
    stages: tuple[PlannedStage, ...]
    digest: str


class CapabilityPlanner(Protocol):
    capability_id: str
    capability_version: str

    def plan(self, job_id: str, spec: JobSpec, snapshots: SnapshotCoordinator) -> Plan: ...


def _artifact_inputs(spec: JobSpec, snapshots: SnapshotCoordinator):
    artifacts = []
    for binding in spec.inputs:
        if isinstance(binding, DatasetInput):
            artifacts.append(snapshots.resolve(binding).artifact)
        elif isinstance(binding, ArtifactInput):
            artifacts.append(binding.artifact)
    return tuple(artifacts)


class IndicatorPlanner:
    capability_id = "finance.indicator.compute"
    capability_version = "1.0"

    def plan(self, job_id, spec, snapshots):
        stage_id = new_id()
        work = WorkUnitSpec(
            work_unit_id=new_id(),
            job_id=job_id,
            stage_id=stage_id,
            capability_id=self.capability_id,
            capability_version=spec.operation.capability_version,
            executor_role=ExecutorRole.EXECUTE,
            parameters=spec.operation.parameters,
            inputs=_artifact_inputs(spec, snapshots),
            partition=PartitionSpec(index=0, count=1),
            resources=spec.execution.resources or ResourceSpec(),
            random_seed=0,
            deadline_at=spec.execution.deadline_at,
            output_schema=spec.operation.result_schema or "stockstat.result.indicator/1",
        )
        stage = PlannedStage(stage_id, "indicator", 0, (work,))
        return Plan((stage,), canonical_digest([work.model_dump(mode="json")]))


class TimeseriesPlanner(IndicatorPlanner):
    capability_id = "finance.timeseries.analyze"


class BacktestPlanner:
    capability_id = "finance.backtest.run"
    capability_version = "1.0"

    def plan(self, job_id, spec, snapshots):
        stage_id = new_id()
        work = WorkUnitSpec(
            work_unit_id=new_id(),
            job_id=job_id,
            stage_id=stage_id,
            capability_id=self.capability_id,
            capability_version=spec.operation.capability_version,
            executor_role=ExecutorRole.EXECUTE,
            parameters=spec.operation.parameters,
            inputs=_artifact_inputs(spec, snapshots),
            partition=PartitionSpec(index=0, count=1),
            resources=spec.execution.resources
            or ResourceSpec(cpu_cores=1, memory_bytes=1_073_741_824),
            random_seed=int(spec.operation.parameters.get("random_seed", 0)),
            deadline_at=spec.execution.deadline_at,
            output_schema=spec.operation.result_schema or "stockstat.result.backtest/1",
        )
        stage = PlannedStage(stage_id, "backtest", 0, (work,))
        return Plan((stage,), canonical_digest([work.model_dump(mode="json")]))


class SearchPlanner:
    capability_id = "finance.experiment.search"
    capability_version = "1.0"

    def plan(self, job_id, spec, snapshots):
        parameters = spec.operation.parameters
        space = parameters["parameter_space"]
        keys = list(space)
        candidates = [
            dict(zip(keys, values, strict=True))
            for values in product(*(space[key] for key in keys))
        ]
        batch_size = max(1, int(parameters.get("batch_size", 8)))
        input_artifacts = _artifact_inputs(spec, snapshots)
        execute_stage_id = new_id()
        execute_units = []
        batches = [
            candidates[index : index + batch_size]
            for index in range(0, len(candidates), batch_size)
        ]
        for index, batch in enumerate(batches):
            execute_units.append(
                WorkUnitSpec(
                    work_unit_id=new_id(),
                    job_id=job_id,
                    stage_id=execute_stage_id,
                    capability_id=self.capability_id,
                    capability_version=spec.operation.capability_version,
                    executor_role=ExecutorRole.EXECUTE,
                    parameters={
                        "base_backtest": parameters["base_backtest"],
                        "candidates": batch,
                        "objective": parameters.get(
                            "objective", {"metric": "sharpe", "direction": "maximize"}
                        ),
                    },
                    inputs=input_artifacts,
                    partition=PartitionSpec(index=index, count=len(batches)),
                    resources=spec.execution.resources
                    or ResourceSpec(cpu_cores=1, memory_bytes=1_073_741_824),
                    random_seed=int(parameters.get("random_seed", 0)) + index,
                    deadline_at=spec.execution.deadline_at,
                    output_schema="stockstat.result.search-shard/1",
                )
            )
        reduce_stage_id = new_id()
        reducer = WorkUnitSpec(
            work_unit_id=new_id(),
            job_id=job_id,
            stage_id=reduce_stage_id,
            capability_id=self.capability_id,
            capability_version=spec.operation.capability_version,
            executor_role=ExecutorRole.REDUCE,
            parameters={
                "objective": parameters.get(
                    "objective", {"metric": "sharpe", "direction": "maximize"}
                )
            },
            inputs=(),
            partition=PartitionSpec(),
            resources=ResourceSpec(cpu_cores=1, memory_bytes=1_073_741_824),
            output_schema="stockstat.result.search/1",
        )
        stages = (
            PlannedStage(execute_stage_id, "search-trials", 0, tuple(execute_units)),
            PlannedStage(reduce_stage_id, "search-reduce", 1, (reducer,)),
        )
        return Plan(
            stages,
            canonical_digest(
                [work.model_dump(mode="json") for stage in stages for work in stage.work_units]
            ),
        )


class BatchPlanner:
    capability_id = "finance.experiment.batch"
    capability_version = "1.0"

    def plan(self, job_id, spec, snapshots):
        parameters = spec.operation.parameters
        runs = parameters["runs"]
        batch_size = max(1, int(parameters.get("batch_size", 8)))
        input_artifacts = _artifact_inputs(spec, snapshots)
        execute_stage_id = new_id()
        batches = [runs[index : index + batch_size] for index in range(0, len(runs), batch_size)]
        execute_units = tuple(
            WorkUnitSpec(
                work_unit_id=new_id(),
                job_id=job_id,
                stage_id=execute_stage_id,
                capability_id=self.capability_id,
                capability_version=spec.operation.capability_version,
                executor_role=ExecutorRole.EXECUTE,
                parameters={"runs": batch},
                inputs=input_artifacts,
                partition=PartitionSpec(index=index, count=len(batches)),
                resources=spec.execution.resources
                or ResourceSpec(cpu_cores=1, memory_bytes=1_073_741_824),
                random_seed=index,
                deadline_at=spec.execution.deadline_at,
                output_schema="stockstat.result.batch-shard/1",
            )
            for index, batch in enumerate(batches)
        )
        reduce_stage_id = new_id()
        reducer = WorkUnitSpec(
            work_unit_id=new_id(),
            job_id=job_id,
            stage_id=reduce_stage_id,
            capability_id=self.capability_id,
            capability_version=spec.operation.capability_version,
            executor_role=ExecutorRole.REDUCE,
            parameters={},
            inputs=(),
            partition=PartitionSpec(),
            resources=ResourceSpec(),
            output_schema="stockstat.result.batch/1",
        )
        stages = (
            PlannedStage(execute_stage_id, "batch-runs", 0, execute_units),
            PlannedStage(reduce_stage_id, "batch-reduce", 1, (reducer,)),
        )
        return Plan(
            stages,
            canonical_digest(
                [work.model_dump(mode="json") for stage in stages for work in stage.work_units]
            ),
        )


class SimulationPlanner:
    capability_id = "finance.simulation.resample"
    capability_version = "1.0"

    def plan(self, job_id, spec, snapshots):
        parameters = spec.operation.parameters
        total = int(parameters["n_samples"])
        shards = max(1, min(int(parameters.get("shards", 4)), total))
        base, remainder = divmod(total, shards)
        execute_stage_id = new_id()
        inputs = _artifact_inputs(spec, snapshots)
        execute_units = []
        cursor = 0
        for index in range(shards):
            count = base + (1 if index < remainder else 0)
            execute_units.append(
                WorkUnitSpec(
                    work_unit_id=new_id(),
                    job_id=job_id,
                    stage_id=execute_stage_id,
                    capability_id=self.capability_id,
                    capability_version=spec.operation.capability_version,
                    executor_role=ExecutorRole.EXECUTE,
                    parameters={
                        **parameters,
                        "simulation_start": cursor,
                        "simulation_count": count,
                    },
                    inputs=inputs,
                    partition=PartitionSpec(index=index, count=shards),
                    resources=spec.execution.resources or ResourceSpec(),
                    random_seed=int(parameters.get("random_seed", 0)),
                    output_schema="stockstat.result.simulation-shard/1",
                )
            )
            cursor += count
        reduce_stage_id = new_id()
        reducer = WorkUnitSpec(
            work_unit_id=new_id(),
            job_id=job_id,
            stage_id=reduce_stage_id,
            capability_id=self.capability_id,
            capability_version=spec.operation.capability_version,
            executor_role=ExecutorRole.REDUCE,
            parameters=parameters,
            inputs=(),
            partition=PartitionSpec(),
            resources=ResourceSpec(),
            output_schema="stockstat.result.simulation/1",
        )
        stages = (
            PlannedStage(execute_stage_id, "simulation-shards", 0, tuple(execute_units)),
            PlannedStage(reduce_stage_id, "simulation-reduce", 1, (reducer,)),
        )
        return Plan(
            stages,
            canonical_digest(
                [work.model_dump(mode="json") for stage in stages for work in stage.work_units]
            ),
        )


class WalkForwardPlanner(BatchPlanner):
    capability_id = "finance.validation.walk_forward"

    def plan(self, job_id, spec, snapshots):
        parameters = spec.operation.parameters
        runs = [
            {
                "run_id": f"window-{index}",
                "backtest": parameters["base_backtest"],
                "window": window,
            }
            for index, window in enumerate(parameters["windows"])
        ]
        rewritten = spec.model_copy(
            update={
                "operation": spec.operation.model_copy(
                    update={
                        "parameters": {"runs": runs, "batch_size": parameters.get("batch_size", 4)}
                    }
                )
            }
        )
        plan = super().plan(job_id, rewritten, snapshots)
        stages = tuple(
            PlannedStage(
                stage.stage_id,
                stage.name.replace("batch", "walk-forward"),
                stage.position,
                tuple(
                    work.model_copy(update={"capability_id": self.capability_id})
                    for work in stage.work_units
                ),
            )
            for stage in plan.stages
        )
        return Plan(
            stages,
            canonical_digest(
                [work.model_dump(mode="json") for stage in stages for work in stage.work_units]
            ),
        )


class PlannerRegistry:
    def __init__(self):
        self._planners = {}

    def register(self, planner):
        self._planners[(planner.capability_id, planner.capability_version)] = planner

    def get(self, capability_id, capability_version):
        try:
            return self._planners[(capability_id, capability_version)]
        except KeyError as exc:
            raise LookupError("CAPABILITY_VERSION_UNAVAILABLE") from exc


DEFAULT_PLANNERS = PlannerRegistry()
for _planner in (
    IndicatorPlanner(),
    TimeseriesPlanner(),
    BacktestPlanner(),
    SearchPlanner(),
    BatchPlanner(),
    SimulationPlanner(),
    WalkForwardPlanner(),
):
    DEFAULT_PLANNERS.register(_planner)
