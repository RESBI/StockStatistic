from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .base import ContractModel
from .work import ExecutorRole, ResourceSpec

CAPABILITY_IDS = (
    "finance.data.ingest",
    "finance.indicator.compute",
    "finance.timeseries.analyze",
    "finance.backtest.run",
    "finance.simulation.resample",
    "finance.experiment.search",
    "finance.experiment.batch",
    "finance.validation.walk_forward",
    "finance.label.generate",
    "finance.factor.evaluate",
    "finance.portfolio.construct",
    "finance.risk.evaluate",
)


class InputMode(StrEnum):
    MATERIALIZED = "materialized"
    RECORD_BATCH_STREAM = "record_batch_stream"
    EITHER = "either"


class CheckpointMode(StrEnum):
    NONE = "none"
    BATCH = "batch"


class CapabilityDescriptor(ContractModel):
    capability_id: str
    capability_version: str
    parameter_schema: str
    result_schema: str
    input_modes: tuple[InputMode, ...] = (InputMode.MATERIALIZED,)
    executor_roles: tuple[ExecutorRole, ...] = (ExecutorRole.EXECUTE,)
    checkpoint_mode: CheckpointMode = CheckpointMode.NONE
    deterministic: bool = True
    partitioning_modes: tuple[str, ...] = ("none",)
    default_resources: ResourceSpec = ResourceSpec()
    supported_kernel_versions: tuple[str, ...] = ("3.1",)
    metadata: dict[str, str] = Field(default_factory=dict)
