from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field

from .artifacts import ArtifactRef
from .base import ContractModel
from .errors import ErrorInfo
from .market import DatasetSelector
from .work import ResourceSpec


class OperationSpec(ContractModel):
    capability_id: str
    capability_version: str = "1.0"
    parameters: dict[str, Any] = Field(default_factory=dict)
    result_schema: str | None = None


class DatasetInput(ContractModel):
    kind: Literal["dataset"] = "dataset"
    name: str
    dataset: DatasetSelector


class ArtifactInput(ContractModel):
    kind: Literal["artifact"] = "artifact"
    name: str
    artifact: ArtifactRef


InputBinding = Annotated[DatasetInput | ArtifactInput, Field(discriminator="kind")]


class RetryBackoff(ContractModel):
    initial_seconds: float = Field(default=1.0, ge=0)
    factor: float = Field(default=2.0, ge=1)
    max_seconds: float = Field(default=60.0, ge=0)


class ExecutionPolicy(ContractModel):
    priority: int = Field(default=50, ge=0, le=100)
    deadline_at: datetime | None = None
    max_attempts: int = Field(default=3, ge=1, le=100)
    retry_backoff: RetryBackoff = RetryBackoff()
    resources: ResourceSpec | None = None
    worker_labels: dict[str, str] = Field(default_factory=dict)
    partitioning: dict[str, Any] = Field(default_factory=lambda: {"mode": "auto"})


class OutputPolicy(ContractModel):
    retain_for_seconds: int = Field(default=2_592_000, ge=0)
    detail_level: Literal["summary", "standard", "full"] = "standard"
    emit_partials: bool = False


class JobSpec(ContractModel):
    name: str = Field(min_length=1, max_length=200)
    operation: OperationSpec
    inputs: tuple[InputBinding, ...] = ()
    execution: ExecutionPolicy = ExecutionPolicy()
    outputs: OutputPolicy = OutputPolicy()
    tags: dict[str, str] = Field(default_factory=dict)


class JobState(StrEnum):
    ACCEPTED = "accepted"
    PLANNING = "planning"
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class JobProgress(ContractModel):
    fraction: float = Field(default=0.0, ge=0, le=1)
    completed_weight: float = 0.0
    total_weight: float = 0.0
    message: str = ""


class JobResultManifest(ContractModel):
    job_id: str
    capability_id: str
    capability_version: str
    result_schema: str
    created_at: datetime
    summary: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactRef] = Field(default_factory=dict)
    reproducibility: dict[str, Any] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class JobStatus(ContractModel):
    job_id: str
    state: JobState
    revision: int
    progress: JobProgress = JobProgress()
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: ErrorInfo | None = None
    result: JobResultManifest | None = None
